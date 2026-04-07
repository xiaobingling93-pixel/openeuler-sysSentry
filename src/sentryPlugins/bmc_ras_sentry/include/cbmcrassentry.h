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
    uint16_t deviceId;
    bool valid;
};

struct PhysicalDiskAddress {
    std::string encId;
    std::string slotId;
};

using BMCEventMap = std::map<std::string, uint32_t>;
using DiskSNToBlockName = std::map<std::string, std::set<std::string> >;

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
    void GetDiskPassthroughInfo();
    std::pair<std::string, std::vector<PhysicalDiskAddress> > GetStorcliVDInfo(
        const std::string& ctrlId, const std::string& VDId);
    std::vector<std::string> GetStorcliPDSN(
        const std::vector<PhysicalDiskAddress>& PDAddresses, const std::string& ctrlId);
    void GetStorcliRaidInfo();
    std::pair<std::string, std::vector<PhysicalDiskAddress> > GetHiraidadmVdDetailInfo(int ctrlId, int VDId);
    std::map<std::string, std::vector<PhysicalDiskAddress> > GetHiraidadmVDInfo(int ctrlId);
    std::vector<std::string> GetHiraidadmDiskSN(int ctrlId, const std::vector<PhysicalDiskAddress>& PDAddresses);
    void GetHiraidadmRaidInfo();
    void SetDiskSNToBlockName(const std::string& blockName,
        const std::vector<std::string> diskSNs, DiskSNToBlockName& diskSNToBlockName);
    void InitBMCEvents();
    void OpenAllBMCEvents();
    void OpenBMCEvents(const std::string& event_id);
    bool IsOpenBMCBlockIo();
    void SentryWorker();
    void GetBMCIp();
    std::string BuilSetBMCBlockIoCommand(uint8_t blockType, bool openFlag);
    std::string BuilGetBMCBlockIoCommand(uint8_t blockType);
    void OpenBMCBlockIo(uint8_t blockType);
    void CloseBMCBlockIo(uint8_t blockType);
    std::string BuildDiskSNIPMICommand(const IPMIEvent& event, uint8_t startIndex);
    std::string GetDiskSNByIPMI(const IPMIEvent& event);
    void ReportAlarm(const IPMIEvent& event);
    void ReportResult(int resultLevel, const std::string& msg);
    int QueryEvents();
    std::string BuildIPMICommand(uint16_t startIndex, std::string severity, std::string subjectType);
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
    std::vector<DiskSNToBlockName> m_diskSNToBlockNames;
    std::map<uint32_t, std::string> m_BMCOpenEvents;
    BMCEventMap m_BMCBlockEvents;
    std::map<std::string, BMCEventMap> m_BMCEvents;
    std::map<uint8_t, bool> m_BMCBlockIoChange = {
        {0x00, false},
        {0x01, false}
    };
    int m_patrolSeconds;
    int m_alarmId;
};
}
#endif

