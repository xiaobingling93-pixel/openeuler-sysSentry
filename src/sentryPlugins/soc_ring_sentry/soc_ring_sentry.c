/*
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * sysSentry is licensed under Mulan PSL v2.
 * You can use this software according to the terms and conditions of the Mulan PSL v2.
 * You may obtain a copy of Mulan PSL v2 at:
 *          http://license.coscl.org.cn/MulanPSL2
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
 * EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
 * MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
 *
 * See the Mulan PSL v2 for more details.
 *
 * Description: SOC Ring sentry main program
 * Author: Yihang Li
 * Create: 2025-7-10
 */

#include <argp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <unistd.h>
#include <ctype.h>
#include <stdint.h>
#include <numa.h>
#include "register_xalarm.h"
#include "log_utils.h"
#include "soc_ring_sentry.h"
#include "tc_ring_one.h"

#define DEFAULT_INTENSITY_DELAY 600
#define DEFAULT_HANDLE 1
#define DEFAULT_LOOP_CNT 0
#define LIMITE_MEM_SIZE 64
#define KB 1024
#define DEFAULT_MEM_SIZE (4 * KB * KB)

uint64_t g_intensity_delay;
uint64_t g_handle;
uint64_t g_mem_size;
uint64_t g_loop_cnt;
bool *g_blacklist;

static void print_opts_help()
{
    printf("usage: soc_ring_sentry [OPTIONS]\n"
           "\n"
           "Options:\n"
           "  -h,            Show this help message and exit.\n"
           "  -g,            Get the SOC Ring sentry case.\n");
}

static void soc_ring_sentry_case_get()
{
    printf("1. [soc stl] ring data bit line scan tescase.\n");
}

static bool soc_ring_sentry_envtoull(char *env, uint64_t *value)
{
    char *endptr;
    errno = 0;

    if (env) {
        if (*env == '-') {
            logging_error("Negative input not allowed.\n");
            return false;
        }

        *value = strtoull(env, &endptr, 10);
        if (errno == 0 && endptr != env) {
            while (isspace((unsigned char)*endptr)) {
                endptr++;
            }

            if (*endptr == '\0') {
                return true;
            }
        }
    }

    return false;
}

static void soc_ring_sentry_log_level_init()
{
    setLogLevel();
}

static void soc_ring_sentry_intensity_delay_init()
{
    char *env = getenv("SOC_RING_SENTRY_INTENSITY_DELAY");
    g_intensity_delay = DEFAULT_INTENSITY_DELAY;
    uint64_t value;

    if (soc_ring_sentry_envtoull(env, &value)) {
        g_intensity_delay = value;
        logging_info("soc_ring_sentry intensity delay set %lums\n", g_intensity_delay);
        return;
    }

    logging_warn("Environment variable SOC_RING_SENTRY_INTENSITY_DELAY invalid, using default value %lums\n", g_intensity_delay);
}

static void soc_ring_sentry_handle_init()
{
    char *env = getenv("SOC_RING_SENTRY_FAULT_HANDLING");
    g_handle = DEFAULT_HANDLE;
    uint64_t value;

    if (soc_ring_sentry_envtoull(env, &value) && value < HANDLE_LEVEL_INVALID) {
        g_handle = value;
        logging_info("soc_ring_sentry handle set %lu\n", g_handle);
        return;
    }

    logging_warn("Environment variable SOC_RING_SENTRY_FAULT_HANDLING invalid, using default value %lu\n", g_handle);
}

static void soc_ring_sentry_mem_size_init()
{
    char *env = getenv("SOC_RING_SENTRY_MEM_SIZE");
    g_mem_size = DEFAULT_MEM_SIZE;
    uint64_t value;

    if (soc_ring_sentry_envtoull(env, &value)) {
        if (value != 0 && value < (UINT64_MAX / KB) && (value % LIMITE_MEM_SIZE) == 0) {
            g_mem_size = value * KB;
            logging_info("soc_ring_sentry memory size set %luKB\n", value);
            return;
        }
    }

    logging_warn("Environment variable SOC_RING_SENTRY_MEM_SIZE invalid, using default value %luKB\n", g_mem_size / KB);
}

static void soc_ring_sentry_loop_cnt_init()
{
    char *env = getenv("SOC_RING_SENTRY_LOOP_CNT");
    g_loop_cnt = DEFAULT_LOOP_CNT;
    uint64_t value;

    if (soc_ring_sentry_envtoull(env, &value)) {
        g_loop_cnt = value;
        logging_info("soc_ring_sentry loop cnt set %lu\n", g_loop_cnt);
        return;
    }

    logging_warn("Environment variable SOC_RING_SENTRY_LOOP_CNT invalid, using default value %lu\n", g_loop_cnt);
}

static void soc_ring_sentry_blacklist_init(size_t core_num)
{
    char *env = getenv("SOC_RING_SENTRY_BLACKLIST");
    char *log_buf, *log_end_ptr;
    size_t log_buf_len, i;
    int offset;

    g_blacklist = (bool *)calloc(core_num, sizeof(bool));
    if (!g_blacklist) {
        logging_error("Failed to allocate memory for blacklist, none CPU set to blacklist\n");
        return;
    }

    if (env && strlen(env) > 0) {
        struct bitmask *cpuset = numa_parse_cpustring_all(env);

        if (!cpuset) {
            logging_error("Failed to parse environment variable SOC_RING_SENTRY_BLACKLIST: %s\n", env);
            return;
        }

        for (i = 0; i < core_num; i++) {
            if (numa_bitmask_isbitset(cpuset, i)) {
                g_blacklist[i] = true;
            }
        }

        numa_bitmask_free(cpuset);
        cpuset = NULL;
        logging_info("soc_ring_sentry blacklist set successful\n");
        log_buf_len = strlen("blacklist cores: ") + core_num * 4 + 2;
        log_buf = (char *)calloc(log_buf_len, sizeof(char));
        if (log_buf) {
            offset = snprintf(log_buf, log_buf_len * sizeof(char), "blacklist cores: ");
            log_end_ptr = log_buf + offset;
            for (i = 0; i < core_num; i++) {
                if (g_blacklist[i]) {
                    offset = snprintf(log_end_ptr, log_buf_len - (log_end_ptr - log_buf), "%ld ", i);
                    if (offset < 0 || offset >= (log_buf_len - (log_end_ptr - log_buf))) {
                        logging_error("Log buffer overflow during snprintf\n");
                        break;
                    }

                    log_end_ptr += offset;
                }
            }

            logging_info("%s\n", log_buf);
            free(log_buf);
            log_buf = NULL;
        }
    }
}

static void soc_ring_sentry_init(size_t core_num)
{
    soc_ring_sentry_log_level_init();
    soc_ring_sentry_intensity_delay_init();
    soc_ring_sentry_handle_init();
    soc_ring_sentry_mem_size_init();
    soc_ring_sentry_loop_cnt_init();
    soc_ring_sentry_blacklist_init(core_num);
}

static int soc_ring_sentry_delivery(size_t core_num)
{
    int ret;

    ret = tc_ring_one_main(g_mem_size, g_loop_cnt, g_intensity_delay, g_handle, g_blacklist, core_num);

    return ret;
}

size_t get_system_core_num(void)
{
    long core_num = sysconf(_SC_NPROCESSORS_CONF);

    return (core_num > 0) ? (size_t)core_num : 1;
}

void soc_ring_sentry_report(enum RESULT_LEVEL result_level, const char *report_data)
{
    char json_result[2048];

    snprintf(json_result, sizeof(json_result), "{\"msg\":\"%s\", \"code\":1001}", report_data);
    report_result(TOOL_NAME, result_level, json_result);
    if (result_level == RESULT_LEVEL_PASS) {
        logging_info("%s\n", report_data);
    } else {
        logging_error("%s\n", report_data);
    }
}

static void soc_ring_sentry_exec()
{
    size_t core_num = get_system_core_num();
    int ret;

    soc_ring_sentry_init(core_num);
    ret = soc_ring_sentry_delivery(core_num);
    if (ret == 0) {
        soc_ring_sentry_report(RESULT_LEVEL_PASS, "SOC STL test pass");
    }

    if (g_blacklist) {
        free(g_blacklist);
        g_blacklist = NULL;
    }
}

int main(int argc, char *argv[])
{
    int opt;

    if (argc > 2) {
        print_opts_help();
        return -1;
    } else if (argc == 2) {
        while ((opt = getopt(argc, argv, "hg")) != -1) {
            switch ((char)opt) {
                case 'h':
                    print_opts_help();
                    return 0;
                case 'g':
                    soc_ring_sentry_case_get();
                    return 0;
                default:
                    print_opts_help();
                    return -1;
            }
        }
    } else {
        soc_ring_sentry_exec();
    }

    return 0;
}

