/*
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * sysSentry is licensed under the Mulan PSL v2.
 * You can use this software according to the terms and conditions of the Mulan PSL v2.
 * You may obtain a copy of Mulan PSL v2 at:
 *     http://license.coscl.org.cn/MulanPSL2
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
 * PURPOSE.
 * See the Mulan PSL v2 for more details.

 * Description: header file for sentry msg monitor
 * Author: Luckky
 * Create: 2025-02-18
*/

#ifndef SMH_COMMON_TYPE_H
#define SMH_COMMON_TYPE_H

#include <stdint.h>

#define SMH_TYPE ('}')
#define OOM_EVENT_MAX_NUMA_NODES 8
#define EID_MAX_LEN 40 // eid str len 39 + '\0'

enum {
    SMH_CMD_MSG_ACK = 0x10,
};

#define SMH_MSG_ACK _IO(SMH_TYPE, SMH_CMD_MSG_ACK)

enum ras_err_type {
    UB_MEM_ATOMIC_DATA_ERR = 0,
    UB_MEM_READ_DATA_ERR,
    UB_MEM_FLOW_POISON,
    UB_MEM_FLOW_READ_AUTH_POISON,
    UB_MEM_FLOW_READ_AUTH_RESPERR,
    UB_MEM_TIMEOUT_POISON,
    UB_MEM_TIMEOUT_RESPERR,
    UB_MEM_READ_DATA_POISON,
    UB_MEM_READ_DATA_RESPERR,
    MAR_NOPORT_VLD_INT_ERR,
    MAR_FLUX_INT_ERR,
    MAR_WITHOUT_CXT_ERR,
    RSP_BKPRE_OVER_TIMEOUT_ERR,
    MAR_NEAR_AUTH_FAIL_ERR,
    MAR_FAR_AUTH_FAIL_ERR,
    MAR_TIMEOUT_ERR,
    MAR_ILLEGAL_ACCESS_ERR,
    REMOTE_READ_DATA_ERR_OR_WRITE_RESPONSE_ERR,
};

enum sentry_ubus_mem_err_type {
    SENTRY_MEM_ERR_ROUTE,
    SENTRY_MEM_FLUX_INT,
    SENTRY_MEM_ERR_OUTBOUND_TRANSLATION,
    SENTRY_MEM_ERR_INBOUND_TRANSLATION,
    SENTRY_MEM_ERR_TIMEOUT,
    SENTRY_MEM_ERR_BUS,
    SENTRY_MEM_ERR_UCE,
    SENTRY_MEM_ERR_NO_REPORT = 1000,
};

enum sentry_msg_helper_msg_type {
    SMH_MESSAGE_POWER_OFF,
    SMH_MESSAGE_OOM,
    SMH_MESSAGE_PANIC,
    SMH_MESSAGE_KERNEL_REBOOT,
    SMH_MESSAGE_UB_MEM_ERR,
    SMH_MESSAGE_PANIC_ACK,
    SMH_MESSAGE_KERNEL_REBOOT_ACK,
};

struct sentry_msg_helper_msg {
    enum sentry_msg_helper_msg_type type;
    uint64_t msgid;
    uint64_t start_send_time;
    uint64_t timeout_time;
    // reboot_info is empty
    union {
        struct {
            int nr_nid;
            int nid[OOM_EVENT_MAX_NUMA_NODES];
            int sync;
            int timeout;
            int reason;
        } oom_info;
        struct {
            uint32_t cna;
            char eid[EID_MAX_LEN];
        } remote_info;
	struct {
            uint64_t pa;
            enum ras_err_type raw_ubus_mem_err_type;
        } ub_mem_info;
    } helper_msg_info;
    unsigned long res;
};

#endif
