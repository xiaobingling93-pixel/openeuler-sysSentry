/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.
 * bmc_ras_sentry is licensed under Mulan PSL v2.
 * You can use this software according to the terms and conditions of the Mulan PSL v2.
 * Author: hewanhan@h-partners.com
 */

#include "cbmcrassentry.h"
#include <string>
#include <chrono>
#include <cstdint>
#include <climits>
#include <sstream>
#include <algorithm>
#include <regex>
extern "C" {
#include "register_xalarm.h"
}
#include "configure.h"
#include "logger.h"

namespace BMCRasSentryPlu {

const int RESP_HEADER_SIZE = 7;
const int EVENT_SIZE = 15;
const uint32_t BMC_BLOCK_IO_CODE = 0x02000039;
const uint8_t MAX_REQ_INDEX = 100;
const std::string BMC_TASK_NAME = "bmc_ras_sentry";
const std::string GET_BMCIP_CMD = "ipmitool lan print";
const std::string IPMI_KEY_IP_ADDR = "IP Address";
const std::string MSG_BMCIP_EMPTY = "ipmitool get bmc ip failed.";
const std::string MSG_BMC_QUERY_FAIL = "ipmitool query failed.";
const std::string MSG_EXIT_SUCCESS = "receive exit signal, task completed.";
const std::string JSON_KEY_ALARM_SOURCE = "alarm_source";
const std::string JSON_KEY_ID = "id";
const std::string JSON_KEY_BMC_ID = "bmc_id";
const std::string JSON_KEY_LEVEL = "level";
const std::string JSON_KEY_TIME = "time";
const std::string JSON_KEY_DISK_INFO = "disk_info";
const std::string JSON_KEY_PHYSICAL_DISK = "physical_disk";
const std::string JSON_KEY_LOGICAL_DISK = "logical_disk";
const std::string JSON_KEY_RAID_INFO = "raid_info";
const std::string JSON_KEY_RAID_ID = "raid_id";
const std::string JSON_KEY_RAM_INFO = "ram_info";
const std::string JSON_KEY_RAM_ID = "ram_id";
const std::string JSON_KEY_CPU_INFO = "cpu_info";
const std::string JSON_KEY_CPU_ID = "cpu_id";
const std::string JSON_KEY_MSG = "msg";
const std::string MOD_SECTION_COMMON = "common";
const std::string MOD_COMMON_ALARM_ID = "alarm_id";
const std::string ALL_BMC_EVENTS = "0000";
const std::string ALL_BMC_DEVICE_EVENTS = "00";
const std::string IPMI_REQUEST_HEAD = "ipmitool raw 0x30 0x94";
const std::string IPMI_REQUEST_KUNPENG_ID = "0xDB 0x07 0x00";
const std::string IPMI_REQUEST_GET_CONCISE_EVENT = "0x40 0x00";
const std::string IPMI_REQUEST_ALL_TYPE = "0xFF";
const std::string LSBLK_GET_SN_AND_NAME = "lsblk -o NAME,SERIAL";
const std::string STORCLI_GET_CTRL_INFO_CMD = "storcli64 /call show";
const std::string STORCLI_GET_VD_INFO_CMD = "storcli64 /c%s/v%s show all";
const std::string STORCLI_GET_PD_INFO_CMD = "storcli64 /c%s/e%s/s%s show all";
const std::string STORCLI_VD_LIST = "VD LIST :";
const std::string STORCLI_CTRL_VD = "DG/VD";
const std::string STORCLI_PD_LIST = "PDs for VD %s :";
const std::string STORCLI_ENC_SLOT = "EID:Slt";
const std::string STORCLI_VD_DETAIL_INFO = "VD%s Properties :";
const std::string STORCLI_VD_DRIVE_NAME = "OS Drive Name";
const std::string STORCLI_PD_ATTRIBUTES = "Drive /c%s/e%s/s%s Device attributes :";
const std::string STORCLI_PD_SN = "SN";
const std::string HIRAIDADM_GET_CTRL_LIST_CMD = "hiraidadm show allctrl j";
const std::string HIRAIDADM_GET_VD_LIST_CMD = "hiraidadm c%d show vdlist j";
const std::string HIRAIDADM_GET_VD_DETAIL_INFO_CMD = "hiraidadm c%d:vd%d show j";
const std::string HIRAIDADM_GET_PD_LIST_CMD = "hiraidadm c%d:vd%d show pdarray";
const std::string HIRAIDADM_GET_PD_INFO_CMD = "hiraidadm c%d:e%s:s%s show j";
const std::string HIRAIDADM_CTRL_LIST = "Controllers";
const std::string HIRAIDADM_CTRL_ID = "ControllerId";
const std::string HIRAIDADM_VD_LIST = "VirtualDrives";
const std::string HIRAIDADM_VD_ID = "VDID";
const std::string HIRAIDADM_VD_INFO = "VirtualDriveInformation";
const std::string HIRAIDADM_VD_NAME = "OSDriveLetter";
const std::string HIRAIDADM_PD_INFO = "DriveDetailInformation";
const std::string HIRAIDADM_PD_SN = "SerialNumber";
const std::string HIRAIDADM_PD_ENC = "Enc";
const std::string HIRAIDADM_PD_SLOT = "Slot";

CBMCRasSentry::CBMCRasSentry() :
    m_running(false),
    m_patrolSeconds(BMCPLU_PATROL_DEFAULT)
{
    std::map<std::string, std::map<std::string, std::string>> modConfig = parseModConfig(BMCPLU_MOD_CONFIG);
    if (modConfig.find(MOD_SECTION_COMMON) != modConfig.end()) {
        auto commonSection = modConfig[MOD_SECTION_COMMON];
        if (commonSection.find(MOD_COMMON_ALARM_ID) != commonSection.end()) {
            int alarmId = 0;
            if (IsValidNumber(commonSection[MOD_COMMON_ALARM_ID], alarmId) && alarmId > 0) {
                m_alarmId = alarmId;
            } else {
                m_alarmId = BMCPLU_DEFAULT_ALARM_ID;
                BMC_LOG_WARNING << "Invalid alarm_id in mod config, use default alarm id: " << BMCPLU_DEFAULT_ALARM_ID;
            }
        }
    }
    GetDiskPassthroughInfo();
    GetStorcliRaidInfo();
    GetHiraidadmRaidInfo();
    InitBMCEvents();
}

CBMCRasSentry::~CBMCRasSentry()
{
    for (const auto & it : m_BMCBlockIoChange) {
        if (it.second)
            CloseBMCBlockIo(it.first);
    }
}

void CBMCRasSentry::GetDiskPassthroughInfo()
{
    std::vector<std::string> result;
    if (ExecCommand(LSBLK_GET_SN_AND_NAME, result)) {
        return;
    }

    bool is_header = true;
    DiskSNToBlockName diskSNToBlockName;
    for (const auto& iter : result) {
        if (iter.empty() || is_header) {
            is_header = false;
            continue;
        }

        auto pairResult = SplitBySpace(iter);
        if (pairResult.size() < 2)
            continue;
        std::string name = pairResult[0];
        std::string serial = pairResult[1];

        if (serial.empty()) {
            continue;
        }

        SetDiskSNToBlockName(name, {serial}, diskSNToBlockName);
    }

    m_diskSNToBlockNames.push_back(diskSNToBlockName);
}

std::pair<std::string, std::vector<PhysicalDiskAddress> > CBMCRasSentry::GetStorcliVDInfo(
    const std::string& ctrlId, const std::string& VDId)
{
    std::vector<PhysicalDiskAddress> PDAddresses;
    std::string VDName;

    auto getVDInfoCmd = format_string(STORCLI_GET_VD_INFO_CMD, ctrlId.c_str(), VDId.c_str());
    auto VDInfo = ParseStorcliCmd(getVDInfoCmd);
    auto PDListHead = format_string(STORCLI_PD_LIST, VDId.c_str());
    auto PDListIt = VDInfo.find(PDListHead);
    if (PDListIt == VDInfo.end()) {
        BMC_LOG_WARNING << PDListHead << " can't be find, cmd: " << getVDInfoCmd;
        return {"", {}};
    }

    auto VDDetailInfoHead = format_string(STORCLI_VD_DETAIL_INFO, VDId.c_str());
    auto VDDetailInfoIt = VDInfo.find(VDDetailInfoHead);
    if (VDDetailInfoIt == VDInfo.end()) {
        BMC_LOG_WARNING << VDDetailInfoHead << "can't be find, cmd: " << getVDInfoCmd;
        return {"", {}};
    }
    auto VDDetailInfo = ParseStorcliKeyToValue(VDDetailInfoIt->second);
    auto VDNameIt = VDDetailInfo.find(STORCLI_VD_DRIVE_NAME);
    if (VDNameIt == VDDetailInfo.end()) {
        BMC_LOG_WARNING << VDDetailInfoHead << "get " << STORCLI_VD_DRIVE_NAME
                        << " value failed, cmd: " << getVDInfoCmd;
        return {"", {}};
    }
    auto VDNameResult = SplitString(VDNameIt->second, "/");
    VDName = VDNameResult.back();

    auto PDMap = ParseCmdMap(PDListIt->second);
    auto PDMapHead = PDMap.first;
    auto PDMapInfo = PDMap.second;
    auto EncslotNumIt = PDMapHead.find(STORCLI_ENC_SLOT);
    if (EncslotNumIt == PDMapHead.end()) {
        BMC_LOG_WARNING << "PDs map head " << STORCLI_ENC_SLOT << " can't be find, cmd: " << getVDInfoCmd;
        return {"", {}};
    }
    uint8_t EncslotNum = EncslotNumIt->second;
    for (const auto& PDLine : PDMapInfo) {
        if (EncslotNum >= PDLine.size()) {
            BMC_LOG_WARNING << "PDs map get " << STORCLI_ENC_SLOT << " value failed, cmd: " << getVDInfoCmd;
            continue;
        }
        
        auto EncSlotResult = SplitString(PDLine[EncslotNum], ":");
        if (EncSlotResult.size() < 2) {
            BMC_LOG_WARNING << "parse " << STORCLI_ENC_SLOT << " value failed, cmd: " << getVDInfoCmd;
            continue;
        }
        PhysicalDiskAddress PDAddress;
        PDAddress.encId = EncSlotResult[0];
        PDAddress.slotId = EncSlotResult[1];
        PDAddresses.push_back(PDAddress);
    }

    return {VDName, PDAddresses};
}

std::vector<std::string> CBMCRasSentry::GetStorcliPDSN(
    const std::vector<PhysicalDiskAddress>& PDAddresses, const std::string& ctrlId)
{
    std::vector<std::string> PDSNs;

    for (const auto& PDAddress : PDAddresses) {
        auto getPDInfoCmd = format_string(STORCLI_GET_PD_INFO_CMD,
            ctrlId.c_str(), PDAddress.encId.c_str(), PDAddress.slotId.c_str());
        auto PDInfo = ParseStorcliCmd(getPDInfoCmd);
        auto PDAttributesHead = format_string(STORCLI_PD_ATTRIBUTES,
            ctrlId.c_str(), PDAddress.encId.c_str(), PDAddress.slotId.c_str());
        auto PDAttributesIt = PDInfo.find(PDAttributesHead);
        if (PDAttributesIt == PDInfo.end()) {
            BMC_LOG_WARNING << PDAttributesHead << "can't be find, cmd: " << getPDInfoCmd;
            continue;
        }
        auto PDAttributes = ParseStorcliKeyToValue(PDAttributesIt->second);
        auto PDSNIt = PDAttributes.find(STORCLI_PD_SN);
        if (PDSNIt == PDAttributes.end()) {
            BMC_LOG_WARNING << PDAttributesHead << "get " << STORCLI_PD_SN <<" value failed, cmd: " << getPDInfoCmd;
            continue;
        }
        PDSNs.push_back(PDSNIt->second);
    }

    return PDSNs;
}

void CBMCRasSentry::GetStorcliRaidInfo()
{
    auto raidCtrlInfo = ParseStorcliCmd(STORCLI_GET_CTRL_INFO_CMD);
    if (raidCtrlInfo.size() == 0)
        return;

    auto VDListIt = raidCtrlInfo.find(STORCLI_VD_LIST);
    if (VDListIt == raidCtrlInfo.end()) {
        BMC_LOG_WARNING << STORCLI_VD_LIST << " can't be find, cmd: " << STORCLI_GET_CTRL_INFO_CMD;
        return;
    }

    auto VDListMap = ParseCmdMap(VDListIt->second);
    auto VDListMapHead = VDListMap.first;
    auto VDListMapInfo = VDListMap.second;
    auto ctrlVDNumIt = VDListMapHead.find(STORCLI_CTRL_VD);
    if (ctrlVDNumIt == VDListMapHead.end()) {
        BMC_LOG_WARNING << STORCLI_CTRL_VD << " can't be find, cmd: " << STORCLI_GET_CTRL_INFO_CMD;
        return;
    }

    uint8_t ctrlVDNUm = ctrlVDNumIt->second;
    DiskSNToBlockName diskSNToBlockName;
    for (const auto& VDListMapLine : VDListMapInfo) {
        if (ctrlVDNUm >= VDListMapLine.size()) {
            BMC_LOG_WARNING << STORCLI_VD_LIST << " get " << STORCLI_CTRL_VD
                           << " value failed, cmd: " << STORCLI_GET_CTRL_INFO_CMD;
            continue;
        }

        auto ctrlVDId = VDListMapLine[ctrlVDNUm];
        auto ctrlVDResult = SplitString(ctrlVDId, "/");
        if (ctrlVDResult.size() < 2) {
            BMC_LOG_WARNING << "parse " << STORCLI_CTRL_VD << " value failed, value: " << ctrlVDId
                            << ", cmd: " << STORCLI_GET_CTRL_INFO_CMD;
            continue;
        }

        auto VDInfo = GetStorcliVDInfo(ctrlVDResult[0], ctrlVDResult[1]);
        auto VDName = VDInfo.first;
        auto PDSNs = GetStorcliPDSN(VDInfo.second, ctrlVDResult[0]);
        SetDiskSNToBlockName(VDName, PDSNs, diskSNToBlockName);
    }

    m_diskSNToBlockNames.push_back(diskSNToBlockName);
}

std::pair<std::string, std::vector<PhysicalDiskAddress> > CBMCRasSentry::GetHiraidadmVdDetailInfo(int ctrlId, int VDId)
{
    std::vector<PhysicalDiskAddress> PDAddresses;
    std::string VDName;
    auto getVdInfoCmd = format_string(HIRAIDADM_GET_VD_DETAIL_INFO_CMD, ctrlId, VDId);

    auto VDInfoDataObj = ParseHiraidadmCmd(getVdInfoCmd);
    if (VDInfoDataObj == nullptr)
        return {"", {}};

    auto VDInfoObj = json_object_object_get(VDInfoDataObj, HIRAIDADM_VD_INFO.c_str());
    if (!json_object_is_type(VDInfoObj, json_type_object)) {
        BMC_LOG_WARNING << HIRAIDADM_VD_INFO << " obj can't be find, cmd: " << getVdInfoCmd;
        json_object_put(VDInfoDataObj);
        return {"", {}};
    }

    auto VDNameObj = json_object_object_get(VDInfoObj, HIRAIDADM_VD_NAME.c_str());
    if (!json_object_is_type(VDNameObj, json_type_string)) {
        BMC_LOG_WARNING << HIRAIDADM_VD_NAME << " string can't be find, cmd: " << getVdInfoCmd;
        json_object_put(VDInfoDataObj);
        return {"", {}};
    }
    auto VDNameResult = SplitString(json_object_get_string(VDNameObj), "/");
    VDName = VDNameResult.back();
    json_object_put(VDInfoDataObj);

    auto getPDListCmd = format_string(HIRAIDADM_GET_PD_LIST_CMD, ctrlId, VDId);
    std::vector<std::string> PDListInfo;

    if (ExecCommand(getPDListCmd, PDListInfo))
        return {"", {}};

    auto PDListMap = ParseCmdMap(PDListInfo);
    auto PDListMapHead = PDListMap.first;
    auto PDListMapInfo = PDListMap.second;
    auto encNumIt = PDListMapHead.find(HIRAIDADM_PD_ENC);
    auto slotNumIt = PDListMapHead.find(HIRAIDADM_PD_SLOT);
    if (encNumIt == PDListMapHead.end() || slotNumIt == PDListMapHead.end()) {
        BMC_LOG_WARNING << HIRAIDADM_PD_ENC << " or " <<HIRAIDADM_PD_SLOT << " can't be find, cmd: " << getPDListCmd;
        return {"", {}};
    }

    uint8_t encNum = encNumIt->second;
    uint8_t slotNum = slotNumIt->second;
    for (const auto& pdsLine : PDListMapInfo) {
        if (encNum >= pdsLine.size() || slotNum >= pdsLine.size()) {
            BMC_LOG_WARNING << HIRAIDADM_PD_ENC << " or " <<HIRAIDADM_PD_SLOT
                            << " get value failed, cmd: " << getPDListCmd;
            continue;
        }
        PhysicalDiskAddress PDAddress;
        PDAddress.encId = pdsLine[encNum];
        PDAddress.slotId = pdsLine[slotNum];
        PDAddresses.push_back(PDAddress);
    }

    return {VDName, PDAddresses};
}

std::map<std::string, std::vector<PhysicalDiskAddress> > CBMCRasSentry::GetHiraidadmVDInfo(int ctrlId)
{
    std::map<std::string, std::vector<PhysicalDiskAddress> > VDInfos;
    auto getVDListCmd = format_string(HIRAIDADM_GET_VD_LIST_CMD, ctrlId);

    auto dataObj = ParseHiraidadmCmd(getVDListCmd);
    if (dataObj == nullptr)
        return {};

    auto VDListObj = json_object_object_get(dataObj, HIRAIDADM_VD_LIST.c_str());
    if (!json_object_is_type(VDListObj, json_type_array)) {
        BMC_LOG_WARNING << HIRAIDADM_VD_LIST << " array can't be find, cmd: " << getVDListCmd;
        json_object_put(dataObj);
        return {};
    }

    int arrLen = json_object_array_length(VDListObj);
    for (int i = 0; i < arrLen; i++) {
        auto VDInfoObj = json_object_array_get_idx(VDListObj, i);
        if (!json_object_is_type(VDInfoObj, json_type_object))
            continue;

        auto VDIdObj = json_object_object_get(VDInfoObj, HIRAIDADM_VD_ID.c_str());
        if (!json_object_is_type(VDIdObj, json_type_int))
            continue;

        int VDId = json_object_get_int(VDIdObj);
        auto VDInfoDetail = GetHiraidadmVdDetailInfo(ctrlId, VDId);
        auto VDName = VDInfoDetail.first;
        if (VDName.empty())
            continue;
        VDInfos[VDName] = VDInfoDetail.second;
    }

    json_object_put(dataObj);
    return VDInfos;
}

std::vector<std::string> CBMCRasSentry::GetHiraidadmDiskSN(int ctrlId,
    const std::vector<PhysicalDiskAddress>& PDAddresses)
{
    std::vector<std::string> PDSNs;

    for (const auto& PDAddress : PDAddresses) {
        auto getPDInfoCmd = format_string(HIRAIDADM_GET_PD_INFO_CMD,
            ctrlId, PDAddress.encId.c_str(), PDAddress.slotId.c_str());

        auto dataObj = ParseHiraidadmCmd(getPDInfoCmd);
        if (dataObj == nullptr)
            continue;

        auto PDInfoObj = json_object_object_get(dataObj, HIRAIDADM_PD_INFO.c_str());
        if (!json_object_is_type(PDInfoObj, json_type_object)) {
            BMC_LOG_WARNING << HIRAIDADM_PD_INFO << " obj can't be find, cmd: " << getPDInfoCmd;
            json_object_put(dataObj);
            continue;
        }

        auto PDSNObj = json_object_object_get(PDInfoObj, HIRAIDADM_PD_SN.c_str());
        if (!json_object_is_type(PDSNObj, json_type_string)) {
            BMC_LOG_WARNING << HIRAIDADM_PD_SN << " string can't be find, cmd: " << getPDInfoCmd;
            json_object_put(dataObj);
            continue;
        }

        PDSNs.push_back(json_object_get_string(PDSNObj));
        json_object_put(dataObj);
    }

    return PDSNs;
}

void CBMCRasSentry::GetHiraidadmRaidInfo()
{
    auto dataObj = ParseHiraidadmCmd(HIRAIDADM_GET_CTRL_LIST_CMD);
    if (dataObj == nullptr) {
        return;
    }

    auto ctrlListObj = json_object_object_get(dataObj, HIRAIDADM_CTRL_LIST.c_str());
    if (!json_object_is_type(ctrlListObj, json_type_array)) {
        BMC_LOG_WARNING << HIRAIDADM_CTRL_LIST << " array can't be find, cmd: " << HIRAIDADM_GET_CTRL_LIST_CMD;
        json_object_put(dataObj);
        return;
    }

    DiskSNToBlockName diskSNToBlockName;
    int arrLen = json_object_array_length(ctrlListObj);
    for (int i = 0; i < arrLen; i++) {
        auto ctrlInfoObj = json_object_array_get_idx(ctrlListObj, i);
        if (!json_object_is_type(ctrlInfoObj, json_type_object))
            continue;

        auto ctrlIdObj = json_object_object_get(ctrlInfoObj, HIRAIDADM_CTRL_ID.c_str());
        if (!json_object_is_type(ctrlIdObj, json_type_int))
            continue;

        int ctrlId = json_object_get_int(ctrlIdObj);
        auto VDInfos = GetHiraidadmVDInfo(ctrlId);
        if (VDInfos.size() == 0)
            continue;

        for (const auto& VDInfoIt : VDInfos) {
            auto VDName = VDInfoIt.first;
            auto PDAddresss = VDInfoIt.second;
            auto diskSNs = GetHiraidadmDiskSN(ctrlId, PDAddresss);
            SetDiskSNToBlockName(VDName, diskSNs, diskSNToBlockName);
        }
    }

    m_diskSNToBlockNames.push_back(diskSNToBlockName);
    json_object_put(dataObj);
}

void CBMCRasSentry::SetDiskSNToBlockName(const std::string& VDName,
    const std::vector<std::string> diskSNs, DiskSNToBlockName& diskSNToBlockName)
{
    for (const auto& diskSN : diskSNs) {
        if (diskSNToBlockName.find(diskSN) == diskSNToBlockName.end()) {
            std::set<std::string> blockNames = {VDName};
            diskSNToBlockName[diskSN] = blockNames;
        } else {
            diskSNToBlockName[diskSN].insert(VDName);
        }
    }
}

void CBMCRasSentry::InitBMCEvents()
{
    BMCEventMap BMCBlockEvents = {
        {"0101", 0x02000009},
        {"0102", 0x2B000003},
        {"0103", 0x02000013},
        {"0104", 0x02000015},
        {"0105", 0x02000019},
        {"0106", 0x02000027},
        {"0107", 0x0200002D},
        {"0108", 0x02000039},
        {"0109", 0x0200003B},
        {"0110", 0x0200003D},
        {"0111", 0x02000041},
        {"0112", 0x0200001D}
    };

    BMCEventMap BMCRaidEvents = {
        {"0201", 0x0800004B},
        {"0202", 0x0200000B}
    };

    BMCEventMap BMCRamEvents = {
        {"0301", 0x01000017},
        {"0302", 0x0100003D},
        {"0303", 0x0100005B},
        {"0304", 0x01000079}
    };

    BMCEventMap BMCCpuEvents = {
        {"0401", 0x0000001D}
    };

    m_BMCEvents = {
        {"01", BMCBlockEvents},
        {"02", BMCRaidEvents},
        {"03", BMCRamEvents},
        {"04", BMCCpuEvents}
    };
}

void CBMCRasSentry::OpenAllBMCEvents()
{
    for (const auto& bmc_event_it : m_BMCEvents) {
        auto bmc_event = bmc_event_it.second;
        for (const auto& bmc_event_info_it : bmc_event) {
            m_BMCOpenEvents.emplace(bmc_event_info_it.second,
                                    bmc_event_info_it.first);
        }
    }
}

void CBMCRasSentry::OpenBMCEvents(const std::string& event_id)
{
    const int head_length = 2;
    auto it = m_BMCEvents.find(event_id.substr(0, head_length));
    if (it == m_BMCEvents.end()) {
        BMC_LOG_WARNING << "BMC Event Id not find, Event Id:" << event_id;
        return;
    }

    auto bmc_event = it->second;
    if (event_id.substr(head_length) == ALL_BMC_DEVICE_EVENTS) {
        for (const auto& bmc_event_info_it : bmc_event) {
            m_BMCOpenEvents.emplace(bmc_event_info_it.second,
                                    bmc_event_info_it.first);
        }
    } else {
        const auto bmc_event_info_it = bmc_event.find(event_id);
        if (bmc_event_info_it == bmc_event.end()) {
            BMC_LOG_WARNING << "BMC Event Id not find, Event Id:" << event_id;
            return;
        }
        m_BMCOpenEvents.emplace(bmc_event_info_it->second,
                                bmc_event_info_it->first);
    }
}

void CBMCRasSentry::PraseBMCEvents(const std::string& bmc_events_value)
{
    const std::regex event_id_regex("^\\d{4}$");
    auto result = SplitString(bmc_events_value, ",");

    for (const auto& event_id : result) {
        if (!std::regex_match(event_id, event_id_regex)) {
            BMC_LOG_ERROR << "BMC Events prase error, value: " << bmc_events_value << ", event id: " << event_id;
            return;
        }
    }

    m_BMCOpenEvents.clear();

    for (const auto& event_id : result) {
        if (event_id == ALL_BMC_EVENTS) {
            OpenAllBMCEvents();
            break;
        } else {
            OpenBMCEvents(event_id);
        }
    }
 
    if (IsOpenBMCBlockIo()) {
        for (const auto & it : m_BMCBlockIoChange) {
            OpenBMCBlockIo(it.first);
        }
    } else {
        for (const auto & it : m_BMCBlockIoChange) {
            if (it.second)
                CloseBMCBlockIo(it.first);
        }
    }
}

bool CBMCRasSentry::IsOpenBMCBlockIo()
{
    auto it = m_BMCOpenEvents.find(BMC_BLOCK_IO_CODE);
    if (it == m_BMCOpenEvents.end()) {
        return false;
    } else {
        return true;
    }
}

void CBMCRasSentry::Start()
{
    if (m_running) {
        return;
    }

    GetBMCIp();
    if (m_bmcIp.empty()) {
        BMC_LOG_ERROR << "BMC Ip is empty.";
        ReportResult(RESULT_LEVEL_FAIL, MSG_BMCIP_EMPTY);
        return;
    }
    m_running = true;
    m_worker = std::thread(&CBMCRasSentry::SentryWorker, this);
    BMC_LOG_INFO << "BMC ras sentry Start.";
}

void CBMCRasSentry::Stop()
{
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_running = false;
    }
    m_cv.notify_all();

    if (m_worker.joinable()) {
        m_worker.join();
    }
    BMC_LOG_INFO <<"BMC ras sentry Stop.";
}

void CBMCRasSentry::SetPatrolInterval(int seconds)
{
    m_patrolSeconds = seconds;
}

bool CBMCRasSentry::IsRunning()
{
    return m_running;
}

void CBMCRasSentry::SentryWorker()
{
    int ret = BMCPLU_SUCCESS;
    while (m_running) {
        std::unique_lock<std::mutex> lock(m_mutex);
        ret = QueryEvents();
        if (ret != BMCPLU_SUCCESS) {
            break;
        }
        m_cv.wait_for(lock, std::chrono::seconds(m_patrolSeconds), [this] {
            return !m_running;
        });

        if (!m_running) {
            break;
        }
    }

    if (ret == BMCPLU_SUCCESS) {
        ReportResult(RESULT_LEVEL_PASS, MSG_EXIT_SUCCESS);
    } else {
        ReportResult(RESULT_LEVEL_FAIL, MSG_BMC_QUERY_FAIL);
    }
    m_running = false;
    BMC_LOG_INFO << "BMC ras sentry SentryWorker exit.";
    return;
}

void CBMCRasSentry::GetBMCIp()
{
    std::vector<std::string> result;
    if (ExecCommand(GET_BMCIP_CMD, result)) {
        return;
    }
    for (const auto& iter: result) {
        if (iter.find(IPMI_KEY_IP_ADDR) != std::string::npos) {
            size_t eq_pos = iter.find(':');
            if (eq_pos != std::string::npos) {
                std::string key = Trim(iter.substr(0, eq_pos));
                std::string value = Trim(iter.substr(eq_pos + 1));
                if (key == IPMI_KEY_IP_ADDR) {
                    m_bmcIp = value;
                    return;
                }
            }
        }
    }
    return;
}

std::string CBMCRasSentry::BuilSetBMCBlockIoCommand(uint8_t blockType, bool openFlag)
{
    const std::string ipmiReqHead = "ipmitool raw 0x30 0x93";
    const std::string reqId = "0x3E";
    const std::string parameterSelector = "0x00 0x19";
    const std::string blcokSelector = "0xFF";
    const std::string extrenSelector = "0xFF";
    const std::string frameType = "0x00";
    const std::string writingOffset = "0x00 0x00";
    const std::string writingLength = "0x01";
    std::string parameterData;
    if (openFlag) {
        parameterData = "0x01";
    } else {
        parameterData = "0x00";
    }
    std::ostringstream cmdStream;
    cmdStream << ipmiReqHead
              << " " << IPMI_REQUEST_KUNPENG_ID
              << " " << reqId
              << " " << parameterSelector
              << " " << ByteToHex(blockType)
              << " " << blcokSelector
              << " " << extrenSelector
              << " " << frameType
              << " " << writingOffset
              << " " << writingLength
              << " " << parameterData;
    return cmdStream.str();
}

std::string CBMCRasSentry::BuilGetBMCBlockIoCommand(uint8_t blockType)
{
    const std::string ipmiReqHead = "ipmitool raw 0x30 0x93";
    const std::string reqId = "0x3D";
    const std::string parameterSelector = "0x00 0x19";
    const std::string blcokSelector = "0xFF";
    const std::string extrenSelector = "0xFF";
    const std::string readingOffset = "0x00 0x00";
    const std::string readingLength = "0xFF";
    std::ostringstream cmdStream;
    cmdStream << ipmiReqHead
              << " " << IPMI_REQUEST_KUNPENG_ID
              << " " << reqId
              << " " << parameterSelector
              << " " << ByteToHex(blockType)
              << " " << blcokSelector
              << " " << extrenSelector
              << " " << readingOffset
              << " " << readingLength;
    return cmdStream.str();
}

/***** ipml protocol *****/
/*
查询请求 字节顺序 含义
         1-3     厂商id 默认0xDB 0x07 0x00
         4       子命令 默认0x3D
         5       预留字段
         6       新增操作类型 0x19-获取SSD慢盘检测相关属性
         7       设置参数 0x00-获取NVME SSD慢盘检测参数
                          0x01-获取SAS SSD慢盘检测参数
         8       Block Selector 不涉及，默认0xFF
         9       Extern Selector 不涉及，默认0xFF
         10-11   读取数据偏移，从0开始
         12      本次读取长度
查询响应 字节顺序 含义
         1       completion code 调用成功时该字节不会显示在终端上
         2-4     厂商ID,对应请求中内容
         5       Frame type 不涉及，默认返回00
         6-N     data1: 慢盘检查使能开关，0x00-不使能，0x01-使能
                 data2-3: 平均响应时延阈值，单位为ms，小端字节序
                 data4: 平均时延超过门限的次数
                 data5: 准慢盘的平均响应时延硬盘域内的倍数
                 data6-7: 准慢盘的标准平均响应时延，单位ms，小端字节序
eg:
ipmitool raw 0x30 0x93 0xDB 0x07 0x00 0x3D 0x00 0x19 0x00 0xFF 0xFF 0x00 0x00 0xFF
db 07 00 00 01 14 00 05 05 ff ff
设置请求 字节顺序 含义
         1-3     厂商id 默认0xDB 0x07 0x00
         4       子命令 默认0x3E
         5       预留字段
         6       新增操作类型 0x19-获取SSD慢盘检测相关属性
         7       设置参数 0x00-获取NVME SSD慢盘检测参数
                          0x01-获取SAS SSD慢盘检测参数
         8       Block Selector 不涉及，默认0xFF
         9       Extern Selector 不涉及，默认0xFF
         10      Frame type 不涉及，默认0x00
         11-12   Writing Offset 不涉及，默认0x00
         13      写入长度 写入参数的长度，默认0x01
         14      写入参数 0x00-不使能，0x01-使能
设置响应 字节顺序 含义
         1       completion code 调用成功时该字节不会显示在终端上
         2-4     厂商ID,对应请求中内容
         5-8     返回值 默认返回0
eg:
ipmitool raw 0x30 0x93 0xDB 0x07 0x00 0x3E 0x00 0x19 0x00 0xFF 0xFF 0x00 0x00 0x00 0x01 0x01
dp 07 00 00 00 00 00
    */
void CBMCRasSentry::OpenBMCBlockIo(uint8_t blockType)
{
    auto getCmd = BuilGetBMCBlockIoCommand(blockType);
    auto hexBytes = ExecuteIPMICommand(getCmd);
    if (hexBytes.empty() || hexBytes.size() < 5) {
        BMC_LOG_ERROR << "get bmc block io failed, cmd: " << getCmd;
        return;
    }

    if (hexBytes[4] == "01") {
        return;
    }

    auto setCmd = BuilSetBMCBlockIoCommand(blockType, true);
    ExecuteIPMICommand(setCmd);
    m_BMCBlockIoChange[blockType] = true;
}

void CBMCRasSentry::CloseBMCBlockIo(uint8_t blockType)
{
    auto Cmd = BuilSetBMCBlockIoCommand(blockType, false);
    ExecuteIPMICommand(Cmd);
    m_BMCBlockIoChange[blockType] = false;
}

std::string CBMCRasSentry::BuildDiskSNIPMICommand(const IPMIEvent& event, uint8_t startIndex)
{
    const std::string ipmiReqHead = "ipmitool raw 0x30 0x93";
    const std::string componentType = "0x02 0x00 0x00 0x80";
    const std::string reqId = "0x90";
    const std::string groupId = "0xFF";
    const std::string parameterSelector = "0x00 0x00";
    uint8_t deviceIdHigh = static_cast<uint8_t>((event.deviceId >> 8) & 0xff);
    uint8_t deviceIdLow = static_cast<uint8_t>(event.deviceId & 0xff);
    uint8_t length = 200;
    uint16_t startLength = startIndex * length;
    uint8_t startLengthHigh = static_cast<uint8_t>((startLength >> 8) & 0xff);
    uint8_t startLengthLow = static_cast<uint8_t>(startLength & 0xff);
    std::ostringstream cmdStream;
    cmdStream << ipmiReqHead
              << " " << IPMI_REQUEST_KUNPENG_ID
              << " " << reqId
              << " " << componentType
              << " " << groupId
              << " " << ByteToHex(deviceIdLow)
              << " " << ByteToHex(deviceIdHigh)
              << " " << parameterSelector
              << " " << ByteToHex(startLengthLow)
              << " " << ByteToHex(startLengthHigh)
              << " " << ByteToHex(length);
    return cmdStream.str();
}

/***** ipml protocol *****/
/*
请求 字节顺序 含义
     1-3     厂商id 默认0xDB 0x07 0x00
     4       子命令 默认0x90
     5-8     设备类型 硬盘类型为0x02 0x00 0x00 0x80
     9       组编号 默认0xFF
     10-11   设备编号 由告警查询返回
     12-13   查询类型 部件SN为0x00 0x00
     14-15   读取数据偏移，从0开始
     16      本次读取长度
响应 字节顺序 含义
     1       completion code 调用成功时该字节不会显示在终端上
     2-4     厂商ID,对应请求中内容
     5       表示当前数据是否结束，0x00表示读完，0x01表示没有
     6-N     返回数据，长度为请求字段长度，每一位为ascii编码16位数值
厂商ID固定,其他所有多字节对象均为小端序, eg:
ipmtool raw 0x30 0x93 0xDB 0x07 0x00 0x90 0x02 0x00 0x00 0x80 0xFF 0x01 0x00 0x00 0x00 0x00 0x80
db 07 00 00 30 33 34 51 56 56 31 30 50 38 31 30 30 34 39 31
    */
std::string CBMCRasSentry::GetDiskSNByIPMI(const IPMIEvent& event)
{
    uint8_t startIndex = 0;
    std::string diskSN;
    
    while (startIndex < MAX_REQ_INDEX) {
        std::string cmd = BuildDiskSNIPMICommand(event, startIndex);
        auto hexBytes = ExecuteIPMICommand(cmd);
        if (hexBytes.empty() || hexBytes.size() < 4) {
            BMC_LOG_ERROR << "get disk SN by IPMI failed, cmd:  " << cmd;
            return "";
        }

        for (int i = 4; i < hexBytes.size(); i++) {
            std::string asciiStr;
            if (HexAsciiToChar(hexBytes[i], asciiStr)) {
                diskSN += asciiStr;
            } else {
                BMC_LOG_ERROR << "hex ascii to char failed, cmd: " << cmd;
                return "";
            }
        }

        if (hexBytes[3] == "00") {
            break;
        }
        startIndex++;
    }

    if (startIndex >= MAX_REQ_INDEX) {
        BMC_LOG_ERROR << "req index exceeded, max index: " << MAX_REQ_INDEX;
        return "";
    }

    return diskSN;
}

/***** ipml protocol *****/
/*
请求 字节顺序 含义
     1-3     厂商id 默认0xDB 0x07 0x0
     4       子命令 默认0x40
     5       请求类型 默认0x00
     6-7     需要查询的事件起始编号,某些情况下查询到的事件可能有多条,
             单次响应无法全部返回,因此需要修改该值分页查询
     8       事件严重级别 位图形式,bit0-normal,bit1-minor,bit2-major,bit3-critical,0xFF表示不指定
     9       主体类型 硬盘类型0x02,0xFF表示不指定
响应 字节顺序 含义
     1       completion code 调用成功时该字节不会显示在终端上
     2-4     厂商ID,对应请求中内容
     5-6     事件总数量
     7       本次返回中包含的事件数量
     8       占位字节,默认0
     9-12    告警类型码
     13-16   事件发生的linux时间戳
     17      事件严重级别,0-normal,1-minor,2-major,3-critical
     18      主体类型,对应请求中内容
     19      设备序号 带外编号
     20-23   占位字节,默认0
     N+1-N+15重复上面9-23中的内容,表示下一个事件
厂商ID固定,其他所有多字节对象均为小端序, eg:
ipmitool raw 0x30 0x94 0xDB 0x07 0x00 0x40 0x00 0x00 0x00 0x01 0x02
db 07 00 03 00 03 00 39 00 00 02 2f ab 91 68 00 02 04 00 00 00 00
39 00 00 02 2e ab 91 68 00 02 02 00 00 00 00 39 00 00 02 2e ab 91
68 00 02 01 00 00 00 00
    */
int CBMCRasSentry::QueryEvents()
{
    uint16_t currentIndex = 0;
    int ret = BMCPLU_SUCCESS;

    while (true) {
        std::string cmd = BuildIPMICommand(currentIndex, IPMI_REQUEST_ALL_TYPE, IPMI_REQUEST_ALL_TYPE);
        std::vector<std::string> hexBytes = ExecuteIPMICommand(cmd);
        if (hexBytes.empty()) {
            break;
        }

        ResponseHeader header = ParseResponseHeader(hexBytes);
        if (!header.valid) {
            ret = BMCPLU_FAILED;
            break;
        }

        BMC_LOG_INFO << "Total events: " << header.totalEvents
                     << ", returned: " << static_cast<int>(header.eventCount)
                     << ", current index: " << currentIndex;
        if (header.eventCount == 0) {
            break;
        }

        size_t expectedSize = RESP_HEADER_SIZE + header.eventCount * EVENT_SIZE;
        if (hexBytes.size() != expectedSize) {
            BMC_LOG_ERROR << "Response size invalid. Expected: " << expectedSize
                         << ", Actual: " << hexBytes.size();
            ret = BMCPLU_FAILED;
            break;
        }

        ProcessEvents(hexBytes, header.eventCount);
        if (header.eventCount > (UINT16_MAX - currentIndex)) {
            BMC_LOG_ERROR << "Integer overflow rish in currentIndex update, break";
            ret = BMCPLU_FAILED;
            break;
        }
        currentIndex += header.eventCount;

        if (currentIndex >= header.totalEvents) {
            break;
        }
    }

    return ret;
}

std::string CBMCRasSentry::BuildIPMICommand(uint16_t startIndex, std::string severity, std::string subjectType)
{
    uint8_t indexHigh = static_cast<uint8_t>((startIndex >> 8) & 0xff);
    uint8_t indexLow = static_cast<uint8_t>(startIndex & 0xff);
    std::ostringstream cmdStream;
    cmdStream << IPMI_REQUEST_HEAD
            << " " << IPMI_REQUEST_KUNPENG_ID
            << " " << IPMI_REQUEST_GET_CONCISE_EVENT
            << " " << ByteToHex(indexLow)
            << " " << ByteToHex(indexHigh)
            << " " << severity
            << " " << subjectType;
    return cmdStream.str();
}

std::vector<std::string> CBMCRasSentry::ExecuteIPMICommand(const std::string& cmd)
{
    BMC_LOG_DEBUG << "IPMI event query command: " << cmd;

    std::vector<std::string> cmdOut;
    if (ExecCommand(cmd, cmdOut)) {
        BMC_LOG_ERROR << "IPMI command execute failed.";
        return {};
    }

    std::ostringstream responseStream;
    for (size_t i = 0; i < cmdOut.size(); ++i) {
        std::string line = cmdOut[i];
        BMC_LOG_DEBUG << "Execute IPMI event response: " << line;
        line.erase(std::remove(line.begin(), line.end(), '\r'), line.end());
        line.erase(std::remove(line.begin(), line.end(), '\n'), line.end());
        if (i > 0 && !line.empty()) {
            responseStream << ' ';
        }
        responseStream << line;
    }
    return SplitString(responseStream.str(), " ");
}

ResponseHeader CBMCRasSentry::ParseResponseHeader(const std::vector<std::string>& hexBytes)
{
    ResponseHeader header = {0, 0, false};

    if (hexBytes.size() < RESP_HEADER_SIZE) {
        BMC_LOG_ERROR << "Invalid response length: " << hexBytes.size();
        return header;
    }

    if (hexBytes[0] != "db" || hexBytes[1] != "07" || hexBytes[2] != "00") {
        BMC_LOG_ERROR << "Unexpected manufacturer ID: "
                     << hexBytes[0] << " " << hexBytes[1] << " " << hexBytes[2];
        return header;
    }

    char* endPtr = nullptr;
    unsigned long totalLow = std::strtoul(hexBytes[3].c_str(), &endPtr, 16);
    if (endPtr == hexBytes[3].c_str() || *endPtr != '\0' || totalLow > 0xff) {
        BMC_LOG_ERROR << "Invalid totalLow byte: " << hexBytes[3];
        return header;
    }

    unsigned long totalHigh = std::strtoul(hexBytes[4].c_str(), &endPtr, 16);
    if (endPtr == hexBytes[4].c_str() || *endPtr != '\0' || totalHigh > 0xff) {
        BMC_LOG_ERROR << "Invalid totalHigh byte: " << hexBytes[4];
        return header;
    }

    header.totalEvents = static_cast<uint16_t>(totalLow) | (static_cast<uint16_t>(totalHigh) << 8);
    unsigned long count = std::strtoul(hexBytes[5].c_str(), &endPtr, 16);
    if (endPtr == hexBytes[5].c_str() || *endPtr != '\0' || count > 0xff) {
        BMC_LOG_ERROR << "Invalid event count byte: " << hexBytes[5];
        return header;
    }

    header.eventCount = static_cast<uint8_t>(count);
    header.valid = true;
    return header;
}

IPMIEvent CBMCRasSentry::ParseSingleEvent(const std::vector<std::string>& hexBytes, size_t startPos)
{
    IPMIEvent event = {0, 0, 0, 0, 0, false};
    char* endPtr = nullptr;

    for (int i = 0; i < 4; ++i) {
        unsigned long byte = std::strtoul(hexBytes[startPos + i].c_str(), &endPtr, 16);
        if (endPtr == hexBytes[startPos + i].c_str() || *endPtr != '\0' || byte > 0xff) {
            BMC_LOG_ERROR << "Invalid alarm type byte at pos " << startPos + i
                         << ": " << hexBytes[startPos + i];
            return event;
        }
        event.alarmTypeCode |= (static_cast<uint32_t>(byte) << (i * 8));
    }

    for (int i = 0; i < 4; ++i) {
        unsigned long byte = std::strtoul(hexBytes[startPos + 4 + i].c_str(), &endPtr, 16);
        if (endPtr == hexBytes[startPos + 4 + i].c_str() || *endPtr != '\0' || byte > 0xff) {
            BMC_LOG_ERROR << "Invalid timestamp byte at pos " << startPos + 4 + i
                         << ": " << hexBytes[startPos + 4 + i];
            return event;
        }
        event.timestamp |= (static_cast<uint32_t>(byte) << (i * 8));
    }

    unsigned long severity = std::strtoul(hexBytes[startPos + 8].c_str(), &endPtr, 16);
    if (endPtr == hexBytes[startPos + 8].c_str() || *endPtr != '\0' || severity > 0xff) {
        BMC_LOG_ERROR << "Invalid severity byte: " << hexBytes[startPos + 8];
        return event;
    }
    event.severity = static_cast<uint8_t>(severity);

    unsigned long subjectType = std::strtoul(hexBytes[startPos + 9].c_str(), &endPtr, 16);
    if (endPtr == hexBytes[startPos + 9].c_str() || *endPtr != '\0' || subjectType > 0xff) {
        BMC_LOG_ERROR << "Invalid subject type byte: " << hexBytes[startPos + 9];
        return event;
    }
    event.subjectType = static_cast<uint8_t>(subjectType);

    unsigned long deviceId = std::strtoul(hexBytes[startPos + 10].c_str(), &endPtr, 16);
    if (endPtr == hexBytes[startPos + 10].c_str() || *endPtr != '\0' || deviceId > 0xff) {
        BMC_LOG_ERROR << "Invalid device ID byte: " << hexBytes[startPos + 10];
        return event;
    }
    event.deviceId = static_cast<uint16_t>(deviceId);

    event.valid = true;
    return event;
}

void CBMCRasSentry::ProcessEvents(const std::vector<std::string>& hexBytes, uint8_t eventCount)
{
    for (int i = 0; i < eventCount; ++i) {
        size_t startPos = RESP_HEADER_SIZE + i * EVENT_SIZE;

        IPMIEvent event = ParseSingleEvent(hexBytes, startPos);
        if (!event.valid) {
            continue;
        }

        ReportAlarm(event);
    }
    return;
}

void CBMCRasSentry::ReportAlarm(const IPMIEvent& event)
{
    uint8_t ucAlarmLevel = MINOR_ALM;
    uint8_t ucAlarmType = ALARM_TYPE_OCCUR;

    auto it = m_BMCOpenEvents.find(event.alarmTypeCode);
    if (it == m_BMCOpenEvents.end()) {
        BMC_LOG_DEBUG << "Skipping closed ipmi id: 0x"
                      << std::hex << event.alarmTypeCode;
        return;
    }
    std::string event_id = it->second;

    json_object* jObject = json_object_new_object();
    std::string bmcId = Uint32ToHexString(event.alarmTypeCode);
    std::string time = Unit32ToLocalTime(event.timestamp);
    json_object_object_add(jObject, JSON_KEY_ALARM_SOURCE.c_str(), json_object_new_string(BMC_TASK_NAME.c_str()));
    json_object_object_add(jObject, JSON_KEY_BMC_ID.c_str(), json_object_new_string(BMC_TASK_NAME.c_str()));
    json_object_object_add(jObject, JSON_KEY_ID.c_str(), json_object_new_string(event_id.c_str()));
    json_object_object_add(jObject, JSON_KEY_BMC_ID.c_str(), json_object_new_string(bmcId.c_str()));
    json_object_object_add(jObject, JSON_KEY_LEVEL.c_str(), json_object_new_int(event.severity));
    json_object_object_add(jObject, JSON_KEY_TIME.c_str(), json_object_new_string(time.c_str()));
    SetHardwareInfo(jObject, event_id, event);
    const char *jData = json_object_to_json_string(jObject);
    int ret = xalarm_Report(m_alarmId, ucAlarmLevel, ucAlarmType, const_cast<char*>(jData));
    if (ret != RETURN_CODE_SUCCESS) {
        BMC_LOG_ERROR << "Failed to xalarm_Report, ret: " << ret;
    }
    json_object_put(jObject);
    return;
}

void CBMCRasSentry::SetHardwareInfo(json_object* jObject, const std::string& eventId, const IPMIEvent& event)
{
    const std::string eventType = eventId.substr(2);
    if (eventType == "01") {
        std::string diskSN = GetDiskSNByIPMI(event);
        std::string blockNameStr = "";
        if (diskSN == "") {
            diskSN = std::to_string(event.deviceId);
        } else {
            for (const auto& diskSNToBlockName : m_diskSNToBlockNames) {
                if (diskSNToBlockName.find(diskSN) != diskSNToBlockName.end()) {
                    auto blockNames = diskSNToBlockName.find(diskSN)->second;
                    for (const auto& blockName : blockNames) {
                        blockNameStr += blockName + ", ";
                    }
                    if (blockNameStr.size() >= 2)
                        blockNameStr.erase(blockNameStr.size() - 2);

                    break;
                }
            }
        }
        json_object* diskInfo = json_object_new_object();
        json_object_object_add(diskInfo, JSON_KEY_PHYSICAL_DISK.c_str(), json_object_new_string(diskSN.c_str()));
        json_object_object_add(diskInfo, JSON_KEY_LOGICAL_DISK.c_str(), json_object_new_string(blockNameStr.c_str()));
        json_object_object_add(jObject, JSON_KEY_DISK_INFO.c_str(), diskInfo);
        return;
    } else if (eventType == "02") {
        json_object* raidInfo = json_object_new_object();
        json_object_object_add(raidInfo, JSON_KEY_RAID_ID.c_str(),
                               json_object_new_string(std::to_string(event.deviceId).c_str()));
        json_object_object_add(jObject, JSON_KEY_RAID_INFO.c_str(), raidInfo);
        return;
    } else if (eventType == "03") {
        json_object* ramInfo = json_object_new_object();
        json_object_object_add(ramInfo, JSON_KEY_RAM_ID.c_str(),
                               json_object_new_string(std::to_string(event.deviceId).c_str()));
        json_object_object_add(jObject, JSON_KEY_RAM_INFO.c_str(), ramInfo);
        return;
    } else if (eventType == "04") {
        json_object* cpuInfo = json_object_new_object();
        json_object_object_add(cpuInfo, JSON_KEY_CPU_ID.c_str(),
                               json_object_new_string(std::to_string(event.deviceId).c_str()));
        json_object_object_add(jObject, JSON_KEY_CPU_INFO.c_str(), cpuInfo);
        return;
    }
}

void CBMCRasSentry::ReportResult(int resultLevel, const std::string& msg)
{
    RESULT_LEVEL level = static_cast<RESULT_LEVEL>(resultLevel);
    json_object* jObject = json_object_new_object();
    json_object_object_add(jObject, JSON_KEY_MSG.c_str(), json_object_new_string(msg.c_str()));
    const char *jData = json_object_to_json_string(jObject);
    int ret = report_result(BMC_TASK_NAME.c_str(), level, const_cast<char*>(jData));
    if (ret != RETURN_CODE_SUCCESS) {
        BMC_LOG_ERROR << "Failed to report_result, ret: " << ret;
    }
    json_object_put(jObject);
    return;
}
};
