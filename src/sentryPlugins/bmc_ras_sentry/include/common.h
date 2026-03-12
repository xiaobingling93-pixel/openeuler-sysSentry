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
#include <json-c/json.h>
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
std::vector<std::string> SplitBySpace(const std::string& str);
std::map<std::string, std::vector<std::string> > ParseStorcliCmd(const std::string& cmd);
std::pair<std::map<std::string, uint8_t>, std::vector<std::vector<std::string> > > ParseCmdMap(
    const std::vector<std::string>& inputVec);
std::map<std::string, std::string> ParseStorcliKeyToValue(const std::vector<std::string>& inputVec);
json_object* ParseHiraidadmCmd(const std::string& cmd);
std::string uint32_to_hex_string(uint32_t num);
std::string unit32_to_local_time(uint32_t timestamp);

template<typename... Args>
std::string format_string(const std::string& fmt, Args&&... args)
{
    int buf_size = std::snprintf(nullptr, 0, fmt.c_str(), std::forward<Args>(args)...);
    if (buf_size < 0) {
        return "";
    }

    std::string result(buf_size + 1, '\0');
    std::snprintf(&result[0], result.size(), fmt.c_str(), std::forward<Args>(args)...);
    result.pop_back();
    return result;
}
}

#endif
