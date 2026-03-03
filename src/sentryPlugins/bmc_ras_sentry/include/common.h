/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.
 * bmc_ras_sentry is licensed under Mulan PSL v2.
 * You can use this software according to the terms and conditions of the Mulan PSL v2.
 * Author: hewanhan@h-partners.com
 */

#ifndef _BMCPLU_COMMON_H_
#define _BMCPLU_COMMON_H_

#include <string>
#include <functional>
#include <cctype>
#include <vector>
#include <map>
#include "configure.h"
#include "logger.h"

#define BMCPLU_FAILED                (-1)
#define BMCPLU_SUCCESS                (0)

struct PluConfig {
    BMCRasSentryPlu::Logger::Level logLevel;
    int patrolSeconds;
    std::string BMCEvents;
};

struct ConfigItem {
    bool required;
    bool found;
    std::function<bool(const std::string& value)> processor;
};

namespace BMCRasSentryPlu {

std::string Trim(const std::string& str);
bool IsValidNumber(const std::string& str, int& num);
int ParseConfig(const std::string& path, PluConfig& config);
std::map<std::string, std::map<std::string, std::string>> parseModConfig(const std::string& path);
std::string ExtractFileName(const std::string& path);
int ExecCommand(const std::string& cmd, std::vector<std::string>& result);
std::string ByteToHex(uint8_t byte);
std::vector<std::string> SplitString(const std::string& str, const std::string& split);
}

#endif
