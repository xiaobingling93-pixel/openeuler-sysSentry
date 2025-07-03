/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.
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

#endif
