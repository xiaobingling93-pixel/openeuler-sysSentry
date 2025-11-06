/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2023-2025. All rights reserved.
 * Description: hbm online repair main program
 * Author: luckky
 * Create: 2024-10-30
 */

#include <argp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "logger.h"
#include "hbm-ras-events.h"
#include "non-standard-hbm-repair.h"

#define DEFAULT_LOG_LEVEL LOG_INFO
#define DEFAULT_PAGE_ISOLATION_THRESHOLD 3355443

#define DRIVER_COMMAND_LEN 32

int global_level_setting;
int page_isolation_threshold;

int string2int(const char* str, int* value)
{
    if (!str) {
        return -1;
    }
    char *endptr;
    errno = 0;
    long val = strtol(str, &endptr, 10);
    if (errno != 0 || *endptr != '\0') {
        return -1;
    }
    *value = (int)val;
    if (val != (long)*value) {
        return -1;
    }
    return 0;
}

int execute_command(const char *command)
{
    FILE *fp;
    char buffer[128] = {0};
    int ret;
    fp = popen(command, "r");
    if (!fp) {
        log(LOG_ERROR, "popen failed\n");
        return -1;
    }

    // check return value
    if (fgets(buffer, sizeof(buffer), fp) == NULL) {
        log(LOG_DEBUG, "execute_command: no output (EOF) for '%s'\n", command);
    }
    log(LOG_DEBUG, "output of command %s is: %s\n", command, buffer);

    ret = pclose(fp);
    if (ret < 0) {
        log(LOG_ERROR, "pclose failed\n");
        return -1;
    }

    if (!WIFEXITED(ret)) {
        log(LOG_ERROR, "command %s did not terminate normally\n", command);
        return -1;
    }

    ret = -WEXITSTATUS(ret);
    log(LOG_DEBUG, "command %s exited with status: %d\n", command, ret);
    return ret;
}

int handle_driver(char* driver_name, bool load)
{
    int ret;
    char command[DRIVER_COMMAND_LEN];

    snprintf(command, DRIVER_COMMAND_LEN, "%s %s 2>&1", load ? "modprobe" : "rmmod", driver_name);
    ret = execute_command(command);
    log((ret < 0 ? LOG_ERROR : LOG_DEBUG), "%s %s %s\n", load ? "load" : "unload", driver_name, ret < 0 ? "failed" : "success");
    return ret;
}

int handle_all_drivers(bool load)
{
    int ret;

    ret = handle_driver("hisi_mem_ras", load);
    if (ret < 0)
        return ret;

    ret = handle_driver("page_eject", load);
    return ret;
}

void hbm_param_init(void)
{
    int ret;
    char *env;

    env = getenv("HBM_ONLINE_REPAIR_LOG_LEVEL");
    ret = string2int(env, &global_level_setting);
    if (ret < 0) {
        global_level_setting = DEFAULT_LOG_LEVEL;
        log(LOG_WARNING, "Get log level from config failed, set the default value %d\n", DEFAULT_LOG_LEVEL);
    } else if (global_level_setting < LOG_DEBUG || global_level_setting > LOG_ERROR) {
        log(LOG_WARNING, "The log level value %d in config is out of range, set the default value %d\n", global_level_setting, DEFAULT_LOG_LEVEL);
        global_level_setting = DEFAULT_LOG_LEVEL;
    } else {
        log(LOG_INFO, "log level: %d\n", global_level_setting);
    }

    env = getenv("PAGE_ISOLATION_THRESHOLD");
    ret = string2int(env, &page_isolation_threshold);
    if (ret < 0) {
        page_isolation_threshold = DEFAULT_PAGE_ISOLATION_THRESHOLD;
        log(LOG_WARNING, "Get page_isolation_threshold from config failed, set the default value %d\n", DEFAULT_PAGE_ISOLATION_THRESHOLD);
    } else if (page_isolation_threshold < 0) {
        log(LOG_WARNING, "The page_isolation_threshold %d in config is out of range, set the default value %d\n", page_isolation_threshold, DEFAULT_PAGE_ISOLATION_THRESHOLD);
        page_isolation_threshold = DEFAULT_PAGE_ISOLATION_THRESHOLD;
    } else {
        log(LOG_INFO, "page_isolation_threshold: %d\n", page_isolation_threshold);
    }
}


int main(int argc, char *argv[])
{
    int ret;

    hbm_param_init();

    ret = handle_all_drivers(true);
    if (ret < 0) {
        return ret;
    }

    struct ras_events *ras = init_trace_instance();
    if (!ras) {
        ret = -1;
        goto err_unload;
    }

    ret = toggle_ras_event(ras->tracing, "ras", "non_standard_event", 1);
    if (ret < 0) {
        log(LOG_WARNING, "unable to enable ras non_standard_event.\n");
        goto err_free;
    }

    get_flash_total_size();

    handle_ras_events(ras);

    ret = toggle_ras_event(ras->tracing, "ras", "non_standard_event", 0);
    if (ret < 0) {
        log(LOG_WARNING, "unable to disable ras non_standard_event.\n");
    }

err_free:
    free(ras);
err_unload:
    handle_all_drivers(false);
    return ret;
}
