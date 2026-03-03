/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.
 * bmc_ras_sentry is licensed under Mulan PSL v2.
 * You can use this software according to the terms and conditions of the Mulan PSL v2.
 * Author: hewanhan@h-partners.com
 */

#ifndef _BMC_RAS_SENTRY_H_
#define _BMC_RAS_SENTRY_H_

#include <atomic>
#include <thread>
#include <mutex>
#include <string>
#include <vector>
#include <cctype>
#include <set>
#include <map>
#include <condition_variable>

namespace BMCRasSentryPlu {

struct ResponseHeader {
    uint16_t totalEvents;
    uint8_t eventCount;
    bool valid;
};

struct IPMIEvent {
    uint32_t alarmTypeCode;
    uint32_t timestamp;
    uint8_t severity;
    uint8_t subjectType;
    uint8_t deviceId;
    bool valid;
};

using BMCEventMap = std::map<std::string, uint32_t>;

class CBMCRasSentry {
public:
    CBMCRasSentry();
    ~CBMCRasSentry();
    void Start();
    void Stop();
    void SetPatrolInterval(int seconds);
    bool IsRunning();
    void PraseBMCEvents(const std::string& bmc_events_value);
private:
    void InitBMCEvents();
    void OpenAllBMCEvents();
    void OpenBMCEvents(const std::string& event_id);
    void SentryWorker();
    void GetBMCIp();
    void ReportAlarm(const IPMIEvent& event);
    void ReportResult(int resultLevel, const std::string& msg);
    int QueryEvents();
    std::string BuildIPMICommand(uint16_t startIndex);
    std::vector<std::string> ExecuteIPMICommand(const std::string& cmd);
    ResponseHeader ParseResponseHeader(const std::vector<std::string>& hexBytes);
    IPMIEvent ParseSingleEvent(const std::vector<std::string>& hexBytes, size_t startPos);
    void ProcessEvents(const std::vector<std::string>& hexBytes, uint8_t eventCount);

private:
    std::atomic<bool> m_running;
    std::thread m_worker;
    std::mutex m_mutex;
    std::condition_variable m_cv;
    std::string m_bmcIp;
    std::set<uint8_t> m_lastDeviceIds;
    std::set<uint8_t> m_currentDeviceIds;
    std::map<uint32_t, std::string> m_BMCOpenEvents;
    BMCEventMap m_BMCBlockEvents;
    std::map<std::string, BMCEventMap> m_BMCEvents;
    int m_patrolSeconds;
    int m_alarmId;
};
}
#endif

