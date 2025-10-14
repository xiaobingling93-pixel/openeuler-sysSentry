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
 * Description: tc ring testcase header
 * Author: lizixian
 * Create: 2025-7-10
 */

#ifndef __TC_RING_ONE_H__
#define __TC_RING_ONE_H__
#include "soc_ring_sentry.h"



/**
 * tc_ring_one_main -
 *                  测试用例总入口，该函数会为测试申请测试内存空间，为每个测试核创建测试线程，并将测试线程调度到测试核上
 * @mem_size:		用户指定的测试内存空间大小，系统每个numa节点均提供对用大小的测试空间，用于巡检测试
 * @loop_cnt:	    测试循环次数, 大于0，则按照对应的循环做巡检测试，等于0，则巡检线程持续驻留在测试核中
 * @delay:	        每个测试块扫描完成后的休眠时长,单位ms， ≤0 则不休眠。
 * @err_handle:	    用于指示是否检测到错误后，是否需要做相关后处理操作
 *                  0 - 不处理，错误处理交由上层软件进行
 *                  1 - 主动触发panic（默认处理）
 *                  2 - 关机
 *                  3 - 重启(不建议，该用例检测的失效错误为数据出错的致命错误，设备不应继续工作)
 *                  其他 - 非法输入。保持为默认处理。
 * @blacklist:     行巡检用例执行核的黑名单数组，用于指定某个核是否执行巡检测试线程，数值大小为测试核个数
 *                 NULL - 无黑名单，系统所有在线核均需要调度巡检线程
 * @core_num:      系统核总数（包含online & offline的core的总数），调用者需要保证该参数正确性
 *
 * return:          0 - 在测试块中未检出错误
 *                  -1 - 系统状态不支持巡检用例执行(系统不支持numa or 系统内存空间不足)
 *                  -2 - 检出到数据错误
 *
 */
int tc_ring_one_main(uint64_t mem_size, uint64_t loop_cnt, uint64_t delay, uint64_t err_handle, bool *blacklist, size_t core_num);

#endif /*__TC_RING_ONE_H__*/
