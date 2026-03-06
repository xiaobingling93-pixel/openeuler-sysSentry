/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.
 * bmc_ras_sentry is licensed under Mulan PSL v2.
 * You can use this software according to the terms and conditions of the Mulan PSL v2.
 * Author: hewanhan@h-partners.com
 */

#include "logger.h"
#include <sys/stat.h>
#include <unistd.h>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <cstring>
#include <sstream>
#include "common.h"

namespace BMCRasSentryPlu {

Logger& Logger::GetInstance()
{
    static Logger instance;
    return instance;
}

bool Logger::Initialize(const std::string& logPath, Level level)
{
    m_logPath = logPath;
    m_level = level;
    OpenLogFile();
    return m_fileOpen;
}

void Logger::SetLevel(Level level)
{
    m_level = level;
}

Logger::Level Logger::GetLevel() const
{
    return m_level;
}

void Logger::OpenLogFile()
{
    m_logFile.open(m_logPath, std::ios::out | std::ios::app);
    if (!m_logFile.is_open()) {
        std::cerr << "Failed to open log file: " << m_logPath
            << ", error: " << strerror(errno) << std::endl;
        m_fileOpen = false;
        return;
    }

    struct stat fileStat;
    if (stat(m_logPath.c_str(), &fileStat) == 0) {
        m_inode = fileStat.st_ino;
        m_device = fileStat.st_dev;
        m_fileSize = fileStat.st_size;
    }
    m_checkTime = std::time(nullptr);

    m_fileOpen = true;
    return;
}

void Logger::CheckFileState()
{
    std::time_t timeNow = std::time(nullptr);
    if (timeNow - m_checkTime < BMCPLU_LOGFILE_CHECK_CYCLE) {
        return;
    }

    struct stat fileStat;
    if (stat(m_logPath.c_str(), &fileStat) != 0) {
        if (errno == ENOENT) { // file deleted
            std::lock_guard<std::mutex> lock(m_writeMutex);
            ReopenLogFile();
        }
        std::cerr << "Failed to get file state: " << m_logPath
                  << ", error: " << strerror(errno) << std::endl;
        return;
    }

    if (fileStat.st_ino != m_inode || fileStat.st_dev != m_device || fileStat.st_size < m_fileSize) {
        ReopenLogFile();
    } else {
        m_fileSize = fileStat.st_size;
    }

    m_checkTime = timeNow;
}

void Logger::ReopenLogFile()
{
    if (m_logFile.is_open()) {
        m_logFile.close();
    }
    OpenLogFile();
    return;
}

void Logger::WriteLog(Level level, const char* file, int line, const std::string& message)
{
    if (level < GetLevel() || message.empty()) {
        return;
    }

    CheckFileState();
    std::lock_guard<std::mutex> lock(m_writeMutex);
    if (m_fileOpen && m_logFile.good()) {
        m_logFile << Format(level, file, line, message) << std::endl;
        m_logFile.flush();
    } else {
        std::cerr << Format(level, file, line, message) << std::endl;
    }
}

std::string Logger::LevelToString(Level level) const
{
    switch (level) {
        case Level::Debug:      return std::string("DEBUG");
        case Level::Info:       return std::string("INFO");
        case Level::Warning:    return std::string("WARNING");
        case Level::Error:      return std::string("ERROR");
        case Level::Critical:   return std::string("CRITICAL");
        default:                return std::string("UNKNOWN");
    }
    return std::string("UNKNOWN");
}

std::string Logger::GetTimeStamp() const
{
    auto now = std::chrono::system_clock::now();
    auto nowTimer = std::chrono::system_clock::to_time_t(now);
    auto milliseconds = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()) % 1000;

    struct tm nowTm;
    localtime_r(&nowTimer, &nowTm);
    
    std::ostringstream oss;
    const int millisecLen = 3;
    oss << std::put_time(&nowTm, "%Y-%m-%d %H:%M:%S");
    oss << '.' << std::setfill('0') << std::setw(millisecLen) << milliseconds.count();

    return oss.str();
}

std::string Logger::Format(Level level, const char* file, int line, const std::string & message) const
{
    std::ostringstream oss;
    oss << GetTimeStamp() << " - " << LevelToString(level) << " - ["
        << ExtractFileName(file) << ":" << line << "]" << " - " << message;
    return oss.str();
}
}
