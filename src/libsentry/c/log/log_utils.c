/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2023-2025. All rights reserved.
 * Description: log utils for sysSentry
 * Author: sxt1001
 * Create: 2025-2-16
 */

#include "log_utils.h"

static LogLevel currentLogLevel = LOG_INFO;

void logMessage(LogLevel level, char* file, int line, const char *format, ...)
{
    if (level >= currentLogLevel) {
        PRINT_LOG_PREFIX(level, file, line);
        va_list args;
        va_start(args, format);
        vfprintf(LOG_FD(level), format, args);
        va_end(args);
        fflush(LOG_FD(level));
    }
}

void setLogLevel()
{
    char* levelStr = getenv(LOG_LEVEL_ENV);
    if (levelStr == NULL) {
        logMessage(LOG_WARN, __FILE__, __LINE__, "getenv('%s') is NULL, use default log level : %s\n", LOG_LEVEL_ENV, LOG_LEVEL_STRING(LOG_INFO));
    } else if (strcmp(levelStr, "info") == 0) {
        currentLogLevel = LOG_INFO;
        logMessage(LOG_INFO, __FILE__, __LINE__, "Set log level : %s\n", LOG_LEVEL_STRING(LOG_INFO));
    } else if (strcmp(levelStr, "warning") == 0) { 
        currentLogLevel = LOG_WARN;
        logMessage(LOG_INFO,__FILE__, __LINE__,"Set log level : %s\n", LOG_LEVEL_STRING(LOG_WARN));
    } else if (strcmp(levelStr, "error") == 0) {
        currentLogLevel = LOG_ERROR;
        logMessage(LOG_INFO,__FILE__, __LINE__,"Set log level : %s\n", LOG_LEVEL_STRING(LOG_ERROR));
    } else if (strcmp(levelStr, "debug") == 0) { 
        currentLogLevel = LOG_DEBUG;
        logMessage(LOG_INFO,__FILE__, __LINE__,"Set log level : %s\n", LOG_LEVEL_STRING(LOG_DEBUG));
    } else {
        currentLogLevel = LOG_INFO;
        logMessage(LOG_WARN, __FILE__, __LINE__, "unknown log level : %s,  use default log level : %s\n", levelStr, LOG_LEVEL_STRING(LOG_INFO));
    }
}
