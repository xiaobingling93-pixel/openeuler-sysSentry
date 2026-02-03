/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2023-2025. All rights reserved.
 * Description: log utils for sysSentry
 * Author: sxt1001
 * Create: 2025-2-16
 */

#ifndef _SYSSENTRY_LOG_H
#define _SYSSENTRY_LOG_H

#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <libgen.h>

typedef enum {
    LOG_DEBUG = 0,
    LOG_INFO,
    LOG_WARN,
    LOG_ERROR,
} LogLevel;

#define LOG_FD(level) (level == LOG_ERROR ? stderr : stdout)

#define LOG_LEVEL_STRING(level) \
    (level == LOG_DEBUG ? "DEBUG" :   \
     level == LOG_INFO ? "INFO" :    \
     level == LOG_WARN ? "WARNING" : \
     level == LOG_ERROR ? "ERROR" :  \
     "UNKNOWN_LEVEL")

#define PRINT_LOG_PREFIX(level, file, line)                         \
    do {                                                            \
        struct timespec ts;                                         \
        clock_gettime(CLOCK_REALTIME, &ts);                         \
        struct tm *local_time = localtime(&ts.tv_sec);              \
        fprintf(LOG_FD(level), "%d-%02d-%02d %02d:%02d:%02d,%03ld - %s - [%s:%d] - ", \
            local_time->tm_year + 1900,                             \
            local_time->tm_mon + 1,                                 \
            local_time->tm_mday,                                    \
            local_time->tm_hour,                                    \
            local_time->tm_min,                                     \
            local_time->tm_sec,                                     \
            ts.tv_nsec / 1000000L,                                  \
            LOG_LEVEL_STRING(level),                                \
            basename(file),                                         \
            line);                                                  \
    } while (0)

// configure Env for log
#define LOG_LEVEL_ENV "LOG_LEVEL"

// print msg
void logMessage(LogLevel level, char* file, int line, const char *format, ...);

// set log level
void setLogLevel(void);

// log function
#define logging_debug(...)       logMessage(LOG_DEBUG, __FILE__, __LINE__, __VA_ARGS__)
#define logging_info(...)        logMessage(LOG_INFO, __FILE__, __LINE__, __VA_ARGS__)
#define logging_warn(...)        logMessage(LOG_WARN, __FILE__, __LINE__, __VA_ARGS__)
#define logging_error(...)       logMessage(LOG_ERROR, __FILE__, __LINE__, __VA_ARGS__)

#endif
