/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.
 * bmc_ras_sentry is licensed under Mulan PSL v2.
 * You can use this software according to the terms and conditions of the Mulan PSL v2.
 * Author: hewanhan@h-partners.com
 */

#include "common.h"
#include <fstream>
#include <algorithm>
#include <cctype>
#include <sstream>
#include <iomanip>
#include <unistd.h>
#include <sys/wait.h>
#include <unordered_map>
#include <string>

namespace BMCRasSentryPlu {

std::string Trim(const std::string& str)
{
    size_t first = str.find_first_not_of(" \t\n\r\v\f");
    if (std::string::npos == first) {
        return "";
    }
    size_t last = str.find_last_not_of(" \t\n\r\v\f");
    return str.substr(first, (last - first + 1));
}

bool IsValidNumber(const std::string& str, int& num)
{
    if (str.empty()) {
        return false;
    }
    for (const auto& iter : str) {
        if (!std::isdigit(iter)) {
            return false;
        }
    }
    std::istringstream iss(str);
    if (!(iss >> num)) {
        return false;
    }
    return true;
}

int ParseConfig(const std::string& path, PluConfig& config)
{
    std::ifstream file(path);
    if (!file.is_open()) {
        BMC_LOG_ERROR << "Failed to open config file: " << path;
        return BMCPLU_FAILED;
    }

    std::unordered_map<std::string, ConfigItem> configMap;
    configMap["log_level"] = {true, false, [&](const std::string& value) {
        if (value == "debug") {
            config.logLevel = Logger::Level::Debug;
        } else if (value == "info") {
            config.logLevel = Logger::Level::Info;
        } else if (value == "warning") {
            config.logLevel = Logger::Level::Warning;
        } else if (value == "error") {
            config.logLevel = Logger::Level::Error;
        } else if (value == "critical") {
            config.logLevel = Logger::Level::Critical;
        } else {
            BMC_LOG_ERROR << "Invalid log_level value.";
            return false;
        }
        return true;
    }};

    configMap["patrol_second"] = {true, false, [&](const std::string& value) {
        int num = 0;
        if (!IsValidNumber(value, num) || !(num >= BMCPLU_PATROL_MIN && num <= BMCPLU_PATROL_MAX)) {
            BMC_LOG_ERROR << "Invalid patrol_second value.";
            return false;
        }
        config.patrolSeconds = num;
        return true;
    }};

    std::string line;
    while (std::getline(file, line)) {
        line = Trim(line);
        if (line.empty() || line[0] == '#') {
            continue;
        }

        size_t eqPos = line.find('=');
        if (eqPos == std::string::npos || eqPos == 0) {
            BMC_LOG_ERROR << "Config file format invalid.";
            return BMCPLU_FAILED;
        }

        std::string key = Trim(line.substr(0, eqPos));
        std::string value = Trim(line.substr(eqPos + 1));
        if (value.empty()) {
            BMC_LOG_ERROR << "Config key: " << key << " cannot empty.";
            return BMCPLU_FAILED;
        }

        auto iter = configMap.find(key);
        if (iter == configMap.end()) {
            BMC_LOG_ERROR << "Config error, unknown key : " << key;
            return BMCPLU_FAILED;
        }

        if (!iter->second.processor(value)) {
            return BMCPLU_FAILED;
        }
        iter->second.found = true;
    }

    for (const auto& iter : configMap) {
        if (iter.second.required && !iter.second.found) {
            BMC_LOG_ERROR << "Config error, missing required key : " << iter.first;
            return BMCPLU_FAILED;
        }
    }
    return BMCPLU_SUCCESS;
}

std::map<std::string, std::map<std::string, std::string>> parseModConfig(const std::string& path)
{
    std::map<std::string, std::map<std::string, std::string>> result;

    std::ifstream file(path);
    if (!file.is_open()) {
        BMC_LOG_ERROR << "Failed to open mod file: " << path;
        return result;
    }

    std::string line;
    std::string currentSection;
    while (std::getline(file, line)) {
        line = Trim(line);
        if (line.empty() || line[0] == '#') {
            continue;
        }
        
        // check for section
        if (line[0] == '[' && line[line.length() - 1] == ']') {
            currentSection = Trim(line.substr(1, line.length() - 2));
            if (!currentSection.empty()) {
                result[currentSection] = std::map<std::string, std::string>();
            }
            continue;
        }

        // check for key=value
        size_t eqPos = line.find('=');
        if (eqPos != std::string::npos && !currentSection.empty()) {
            std::string key = Trim(line.substr(0, eqPos));
            std::string value = Trim(line.substr(eqPos + 1));
            if (!key.empty()) {
                result[currentSection][key] = value;
            }
        }
    }

    return result;
}

std::string ExtractFileName(const std::string& path)
{
    size_t lastSlashPos = path.find_last_of('/');
    if (lastSlashPos == std::string::npos) {
        return path;
    } else {
        return path.substr(lastSlashPos + 1);
    }
}

int ExecCommand(const std::string& cmd, std::vector<std::string>& result)
{
    FILE* pipe = popen(cmd.c_str(), "r");
    if (!pipe) {
        BMC_LOG_ERROR << "Cmd: " << cmd << ", popen failed.";
        return BMCPLU_FAILED;
    }

    char buffer[512];
    result.clear();
    while (fgets(buffer, sizeof(buffer), pipe)) {
        result.push_back(buffer);
    }

    int status = pclose(pipe);
    if (status == -1) {
        BMC_LOG_ERROR << "Cmd: " << cmd << ", pclose failed.";
         return BMCPLU_FAILED;
    } else {
        int exitCode = WEXITSTATUS(status);
        if (exitCode != 0) {
            BMC_LOG_ERROR << "Cmd: " << cmd << ", exit failed, err code: " << exitCode;
            return BMCPLU_FAILED;
        }
    }
    return BMCPLU_SUCCESS;
}

std::string ByteToHex(uint8_t byte)
{
    std::ostringstream oss;
    const int hexLen = 2;
    oss << std::hex << std::setfill('0') << std::setw(hexLen) << static_cast<int>(byte);
    return "0x" + oss.str();
}

std::vector<std::string> SplitString(const std::string& str, const std::string& split)
{
    std::vector<std::string> result;
    if (split.empty()) {
        result.push_back(str);
        return result;
    }

    size_t pos = 0;
    while (true) {
        size_t split_pos = str.find(split, pos);
        std::string substring = str.substr(pos, split_pos - pos);

        if (!substring.empty()) {
            result.push_back(substring);
        }

        if (split_pos == std::string::npos) {
            break;
        }
        pos = split_pos + split.size();
    }
    return result;
}
}
