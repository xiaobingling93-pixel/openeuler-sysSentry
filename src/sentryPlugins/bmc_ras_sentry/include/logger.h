/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.
 * bmc_ras_sentry is licensed under Mulan PSL v2.
 * You can use this software according to the terms and conditions of the Mulan PSL v2.
 * Author: hewanhan@h-partners.com
 */

#ifndef __BMCPLU_LOGGER_H__
#define __BMCPLU_LOGGER_H__

#include <fstream>
#include <string>
#include <mutex>
#include <ctime>
#include <sstream>
#include <sys/types.h>

namespace BMCRasSentryPlu {

class Logger {
public:
    enum class Level {
        Debug,
        Info,
        Warning,
        Error,
        Critical
    };
    static Logger& GetInstance();
    Logger(const Logger&) = delete;
    Logger& operator=(const Logger&) = delete;
    bool Initialize(const std::string& logPath, Level level = Level::Info);
    void SetLevel(Level level);
    Level GetLevel() const;
    void WriteLog(Level level, const char* file, int line, const std::string& message);
    std::string LevelToString(Level level) const;
private:
    Logger() = default;
    void OpenLogFile();
    void CheckFileState();
    void ReopenLogFile();
    std::string GetTimeStamp() const;
    std::string Format(Level level, const char* file, int line, const std::string& message) const;

private:
    std::ofstream m_logFile;
    std::string m_logPath;
    Level m_level = Level::Info;
    mutable std::mutex m_writeMutex;
    std::time_t m_checkTime = 0;
    ino_t m_inode = 0;
    dev_t m_device = 0;
    off_t m_fileSize = 0;
    bool m_fileOpen = false;
};

class LogStream {
public:
    LogStream(Logger::Level level, const char* file, int line)
        : m_level(level), m_file(file), m_line(line)
    {}
    ~LogStream()
    {
        Logger::GetInstance().WriteLog(m_level, m_file, m_line, m_stream.str());
    }
    template<typename T>
    LogStream& operator<<(const T& value)
    {
        m_stream << value;
        return *this;
    }
    LogStream& operator<<(std::ostream& (*manip)(std::ostream&)) // std::endl, std::flush...
    {
        m_stream << manip;
        return *this;
    }

private:
    Logger::Level m_level;
    const char* m_file;
    int m_line;
    std::ostringstream m_stream;
};

#define BMC_LOG_DEBUG          BMCRasSentryPlu::LogStream(BMCRasSentryPlu::Logger::Level::Debug, __FILE__, __LINE__)
#define BMC_LOG_INFO           BMCRasSentryPlu::LogStream(BMCRasSentryPlu::Logger::Level::Info, __FILE__, __LINE__)
#define BMC_LOG_WARNING        BMCRasSentryPlu::LogStream(BMCRasSentryPlu::Logger::Level::Warning, __FILE__, __LINE__)
#define BMC_LOG_ERROR          BMCRasSentryPlu::LogStream(BMCRasSentryPlu::Logger::Level::Error, __FILE__, __LINE__)
#define BMC_LOG_CRITICAL       BMCRasSentryPlu::LogStream(BMCRasSentryPlu::Logger::Level::Critical, __FILE__, __LINE__)
}
#endif
