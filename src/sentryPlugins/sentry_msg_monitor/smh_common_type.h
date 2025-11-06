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

enum sentry_msg_helper_msg_type {
    SMH_MESSAGE_POWER_OFF,
    SMH_MESSAGE_OOM,
    SMH_MESSAGE_PANIC,
    SMH_MESSAGE_KERNEL_REBOOT,
    SMH_MESSAGE_MAX,
    // Add ACK events HERE (below SMH_MESSAGE_MAX)
    SMH_MESSAGE_PANIC_ACK,
    SMH_MESSAGE_KERNEL_REBOOT_ACK,
    SMH_MESSAGE_UNKNOWN,
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
    } helper_msg_info;
    unsigned long res;
};

#endif
