/*
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * sysSentry is licensed under the Mulan PSL v2.
 * You can use this software according to the terms and conditions of the Mulan PSL v2.
 * You may obtain a copy of Mulan PSL v2 at:
 *     http://license.coscl.org.cn/MulanPSL2
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
 * PURPOSE.
 * See the Mulan PSL v2 for more details.

 * Description: bmc log lib
 * Author: sxt1001
 * Create: 2025-11-24
*/

#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "log_utils.h"
#include "bmc_log_lib.h"

#define BUFFER_MAX_LEN 4096
#define SINGLE_ASCII_HEX_STR_LEN 8
#define POWER_RESULT_STR_MAX_LEN 55  // power_off,{rmrs_res_str},{rmrs_res}  max(rmrs_res_str) = 39
#define IPMITOOL_COMMAND_STR_PREFIX_REBOOT "ipmitool raw 0x30 0x92 0xdb 0x07 0x00 0x0f 0x01 "
#define IPMITOOL_COMMAND_STR_MAX_LEN \
    ((POWER_RESULT_STR_MAX_LEN * SINGLE_ASCII_HEX_STR_LEN) + sizeof(IPMITOOL_COMMAND_STR_PREFIX_REBOOT) + 1)

static const char* rmrs_result_strings[] = {
    [RMRS_SUCCESS]                      = "Memory return succeeded",
    [RMRS_IPC_ERROR]                    = "Node communication failed",
    [RMRS_MIGRATE_ERROR]                = "Memory migration failed",
    [RMRS_LACK_LOCAL_MEM_ERROR]         = "Local memory shortage error",
    [RMRS_LACK_REMOTE_MEM_ERROR]        = "Borrowed memory shortage error",
    [RMRS_RESOURCE_COLLECT_ERROR]       = "Resource acquisition failed",
    [RMRS_BORROW_MEM_ERROR]             = "Memory borrowing failed or timed out",
    [RMRS_RETURN_MEM_ERROR]             = "Memory return failed or timed out",
    [RMRS_PARTIAL_SUCCESS]              = "Partial node memory return succeeded",
    [RMRS_MIGRATE_TIMEOUT]              = "Memory migration succeeded with timeout",
};

static char* get_rmrs_result_string(enum sentry_rmrs_result_type rmrs_res_type)
{
    if (rmrs_res_type < 0 || rmrs_res_type >= RMRS_UNKNOWN_CODE) {
        return NULL;
    }

    return (char*) rmrs_result_strings[rmrs_res_type];
}

static int string_to_ascii_hex(const char* raw_string, char* ascii_string, int ascii_string_size)
{
    if (!raw_string || !ascii_string || ascii_string_size <= 0) {
        logging_error("invalid args.\n");
        return -1;
    }

    int len = strlen(raw_string);
    for (int i = 0; i < len; i++) {
        char hex[SINGLE_ASCII_HEX_STR_LEN];
        int n = snprintf(hex, sizeof(hex), "0x%02x ", (unsigned char)raw_string[i]);
        if (n <= 0 || n >= sizeof(hex)) {
            logging_error("snprintf failed, raw character is %c\n", raw_string[i]);
            return -1;
        }
        int available = ascii_string_size - strlen(ascii_string) - 1;
        if (available < SINGLE_ASCII_HEX_STR_LEN) {
            logging_error("ascii string len is too short to add new ascii character\n");
            return -1;
        }
        strncat(ascii_string, hex, SINGLE_ASCII_HEX_STR_LEN);
    }

    if (len > 0) {
        ascii_string[strlen(ascii_string) - 1] = '\0';
    }
    return 0;
}

static int execute_command(const char *command)
{
    FILE *fp;
    char buffer[BUFFER_MAX_LEN] = {0};
    int ret = 0;

    if (!command) {
        logging_error("invalid args.\n");
        return -1;
    }

    fp = popen(command, "r");
    if (!fp) {
        logging_error("popen failed\n");
        return -1;
    }

    if (!fgets(buffer, sizeof(buffer), fp)) {
        logging_warn("no output (EOF) for ipmitool command\n");
    }

    logging_debug("output of ipmitool command is : %s\n", buffer);
    ret = pclose(fp);
    if (ret < 0) {
        logging_error("pclose failed\n");
        return -1;
    }
    if (!WIFEXITED(ret)) {
        logging_error("ipmitool command did not terminate normally\n");
        return -1;
    }
    ret = -WEXITSTATUS(ret);
    logging_info("ipmitool command exited with status: %d\n", ret);
    return ret;
}

static int report_power_off_result_to_bmc(enum sentry_rmrs_result_type res)
{
    int ret = 0;

    char power_off_res_str[POWER_RESULT_STR_MAX_LEN];
    char power_off_res_hex_str[POWER_RESULT_STR_MAX_LEN * SINGLE_ASCII_HEX_STR_LEN];
    char command_ascii_str[IPMITOOL_COMMAND_STR_MAX_LEN];

    char *rmrs_result_string = get_rmrs_result_string(res);
    if (!rmrs_result_string) {
        logging_error("Undefined ACK results\n");
        return -1;
    }

    ret = snprintf(power_off_res_str, sizeof(power_off_res_str), "%s,%s,%d",
                   "power_off", rmrs_result_string, res);
    if (ret <= 0) {
        logging_error("snprintf failed\n");
        return ret;
    }

    ret = string_to_ascii_hex(power_off_res_str, power_off_res_hex_str, sizeof(power_off_res_hex_str));
    if (ret < 0) {
        logging_error("Failed to convert power off res raw string to ascii string\n");
        return ret;
    }

    ret = snprintf(command_ascii_str, sizeof(command_ascii_str),
                   "%s%s", IPMITOOL_COMMAND_STR_PREFIX_REBOOT, power_off_res_hex_str);
    if (ret <= 0) {
        logging_error("snprintf failed\n");
        return -1;
    }
    logging_debug("ipmitool cmd is [%s]\n", command_ascii_str);

    ret = execute_command(command_ascii_str);
    if (ret < 0) {
        logging_error("Failed to report BMC log\n");
        return ret;
    }
    logging_info("Success to report BMC log\n");
    return 0;
}

int report_result_to_bmc(int ack_result, int ioctl_result)
{
    if (ack_result == RMRS_SUCCESS && ioctl_result) {
        // ack success, but ioctl failed
        ack_result = RMRS_MIGRATE_TIMEOUT;
    }
    return report_power_off_result_to_bmc(ack_result);
}
