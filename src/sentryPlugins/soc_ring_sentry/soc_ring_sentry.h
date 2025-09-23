/*
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * sysSentry is licensed under Mulan PSL v2.
 * You can use this software according to the terms and conditions of the Mulan PSL v2.
 * You may obtain a copy of Mulan PSL v2 at:
 *          http://license.coscl.org.cn/MulanPSL2
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
 * EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
 * MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
 *
 * See the Mulan PSL v2 for more details.
 *
 * Description: SOC Ring sentry main header
 * Author: Yihang Li
 * Create: 2025-7-10
 */

#ifndef __SOC_RING_SENTRY_H
#define __SOC_RING_SENTRY_H

#define TOOL_NAME "soc_ring_sentry"

enum handle_level {
    HANDLE_NONE,
    HANDLE_PANIC,
    HANDLE_POWEROFF,
    HANDLE_REBOOT,
    HANDLE_LEVEL_INVALID
};

extern uint64_t g_intensity_delay;
extern uint64_t g_handle;
extern uint64_t g_mem_size;
extern uint64_t g_loop_cnt;
extern bool *g_blacklist;

void soc_ring_sentry_report(enum RESULT_LEVEL result_level, const char *report_data);

#endif
