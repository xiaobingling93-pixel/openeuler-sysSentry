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
#include <regex>

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

    configMap["bmc_events"] = {true, false, [&](const std::string& value) {
        config.BMCEvents = value;
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
        result.push_back(Trim(buffer));
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

bool HexAsciiToChar(const std::string& hexStr, std::string& asciiStr)
{
    if (hexStr.length() != 2) {
        BMC_LOG_ERROR << "input str length for hex ascii to char must be 2, str: " << hexStr;
        return false;
    }
    
    uint8_t asciiVal = 0;
    unsigned long temp = std::stoul(hexStr, nullptr, 16);
    if (temp > UINT8_MAX) {
        BMC_LOG_ERROR << "input str value out for 255, str: " << hexStr;
        return false;
    }
    asciiVal = static_cast<uint8_t>(temp);
    asciiStr = static_cast<char>(asciiVal);

    return true;
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

std::vector<std::string> SplitBySpace(const std::string& str)
{
    std::vector<std::string> result;
    std::regex reg("\\s+");
    std::sregex_token_iterator it(str.begin(), str.end(), reg, -1);
    std::sregex_token_iterator end;
    for(; it != end; ++it) {
        std::string token = Trim(*it);
        if (!token.empty()) {
            result.push_back(token);
        }
    }

    return result;
}

std::map<std::string, std::vector<std::string> > ParseStorcliCmd(const std::string& cmd)
{
    std::vector<std::string> cmdOut;
    if(ExecCommand(cmd, cmdOut))
        return {};

    std::map<std::string, std::vector<std::string> > result;
    int startLine = 0, endLine = 0;
    for (int i = 0; i < cmdOut.size(); i++) {
        if ((cmdOut[i].size() == 0 || cmdOut[i] != std::string(cmdOut[i].size(), '=')) && i != cmdOut.size() - 1)
            continue;

        std::string strKey;
        if (i == cmdOut.size() - 1) {
            endLine = i;
        } else {
            endLine = i - 2;
        }

        if (startLine < 0 || endLine > cmdOut.size() || startLine > endLine ) {
            BMC_LOG_ERROR << "parse storcli message failed, cmd:" << cmd;
            return {};
        }

        std::vector<std::string> storcliInfo(cmdOut.begin() + startLine, cmdOut.begin() + endLine + 1);
	if (startLine == 0) {
            strKey = "head message";
        } else {
            strKey = cmdOut[startLine - 2];
        }
        result.emplace(strKey, storcliInfo);
        startLine = i + 1;
    }

    return result;
}

std::pair<std::map<std::string, uint8_t>, std::vector<std::vector<std::string> > > ParseCmdMap(
    const std::vector<std::string>& inputVec)
{
    int i = 0;
    std::map<std::string, uint8_t> mapHead;
    std::vector<std::vector<std::string> > mapInfo;
    for (const auto& line : inputVec) {
        if (line.size() != 0 && line == std::string(line.size(), '-')) {
            ++i;
            if (i == 3)
                break;
            continue;
        }

        if (i == 1) {
            auto head = SplitBySpace(line);
            for (uint8_t j = 0; j < head.size(); j++) {
                mapHead.emplace(head[j], j);
            }
        } else if (i == 2) {
            auto value = SplitBySpace(line);
            mapInfo.push_back(value);
        }
    }

    return {mapHead, mapInfo};
}

std::map<std::string, std::string> ParseStorcliKeyToValue(const std::vector<std::string>& inputVec)
{
    std::map<std::string, std::string> result;
    for (const auto& line : inputVec) {
        size_t equal_pos = line.find('=');
        if (equal_pos == std::string::npos) {
            continue;
        }

        std::string key = Trim(line.substr(0, equal_pos));
        std::string value = Trim(line.substr(equal_pos + 1));

        result[key] = value;
    }

    return result;
}

json_object* ParseHiraidadmCmd(const std::string& cmd)
{
    std::vector<std::string> cmdOut;
    if(ExecCommand(cmd, cmdOut))
        return NULL;

    std::string jsonStr;
    for (const auto& line : cmdOut) {
        jsonStr += line;
    }

    auto rootObj = json_tokener_parse(jsonStr.c_str());
    if (rootObj == NULL) {
        BMC_LOG_WARNING << "parse json value failed, cmd: " << cmd;
        return NULL;
    }

    auto dataObj = json_object_object_get(rootObj, "CommandData");
    if (!json_object_is_type(dataObj, json_type_object)) {
        BMC_LOG_WARNING << "CommandData object can't be find, cmd: " << cmd;
        return NULL;
    }

    return dataObj;
}

std::string uint32_to_hex_string(uint32_t num)
{
    std::ostringstream oss;
    int length = 8;
    oss << std::uppercase;
    oss << "0x";
    oss << std::setw(length) << std::setfill('0') << std::hex << num;
    return oss.str();
}

std::string unit32_to_local_time(uint32_t timestamp)
{
    time_t t = static_cast<time_t>(timestamp);

    struct tm* local_tm = localtime(&t);
    if (local_tm == nullptr) {
        BMC_LOG_WARNING << "prase timestamp error, value:" << timestamp;
        return "";
    }

    char time_buf[64] = {0};
    strftime(time_buf, sizeof(time_buf), "%Y-%m-%d %H:%M:%S", local_tm);

    return std::string(time_buf);
}
}
