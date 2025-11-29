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

 * Description: header file for power off event
 * Author: sxt1001
 * Create: 2025-11-24
*/

#ifndef SENTRY_BMC_LOG_LIB_H
#define SENTRY_BMC_LOG_LIB_H

enum sentry_rmrs_result_type {
    RMRS_SUCCESS = 0,
    RMRS_IPC_ERROR,
    RMRS_MIGRATE_ERROR,
    RMRS_LACK_LOCAL_MEM_ERROR,
    RMRS_LACK_REMOTE_MEM_ERROR,
    RMRS_RESOURCE_COLLECT_ERROR,
    RMRS_BORROW_MEM_ERROR,
    RMRS_RETURN_MEM_ERROR,
    RMRS_PARTIAL_SUCCESS,
    RMRS_MIGRATE_TIMEOUT,
    RMRS_UNKNOWN_CODE, // unknown error, invalid type
};

int report_result_to_bmc(int ack_result, int ioctl_result);
#endif
