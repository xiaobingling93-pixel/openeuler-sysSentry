# coding: utf-8
# Copyright (c) 2024 Huawei Technologies Co., Ltd.
# sysSentry is licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#     http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
# PURPOSE.
# See the Mulan PSL v2 for more details.
import json
import logging
import sys

from sentryCollector.collect_plugin import is_iocollect_valid, get_io_data, get_iodump_data, get_disk_data, \
    Result_Messages, get_disk_type, Disk_Type
from syssentry.result import ResultLevel, report_result
from xalarm.sentry_notify import xalarm_report, MINOR_ALM, ALARM_TYPE_OCCUR
from .utils import is_abnormal, get_win_data, log_slow_win


TASK_NAME = "avg_block_io"

def sig_handler(signum, _f):
    """stop avg_block_io"""
    report_result(TASK_NAME, ResultLevel.PASS, json.dumps({}))
    logging.info("Finished avg_block_io plugin running.")
    sys.exit(0)

def avg_get_io_data(io_dic):
    """get_io_data from sentryCollector"""
    logging.debug(f"send to sentryCollector get_io_data: period={io_dic['period_time']}, "
                f"disk={io_dic['disk_list']}, stage={io_dic['stage_list']}, iotype={io_dic['iotype_list']}")
    res = get_io_data(io_dic["period_time"], io_dic["disk_list"], io_dic["stage_list"], io_dic["iotype_list"])
    return check_result_validation(res, 'get io data')


def avg_get_iodump_data(io_dic):
    """avg_get_iodump_data from sentryCollector"""
    logging.debug(f"send to sentryCollector avg_get_iodump_data: period={io_dic['period_time']}, "
                f"disk={io_dic['disk_list']}, stage={io_dic['stage_list']}, iotype={io_dic['iotype_list']}")
    res = get_iodump_data(io_dic["period_time"], io_dic["disk_list"], io_dic["stage_list"], io_dic["iotype_list"])
    return check_result_validation(res, 'get io dump data')


def avg_get_disk_data(io_dic):
    """avg_get_disk_data from sentryCollector"""
    logging.debug(f"send to sentryCollector avg_get_disk_data: period={io_dic['period_time']}, "
                f"disk={io_dic['disk_list']}, stage={io_dic['stage_list']}, iotype={io_dic['iotype_list']}")
    res = get_disk_data(io_dic["period_time"], io_dic["disk_list"], io_dic["stage_list"], io_dic["iotype_list"])
    return check_result_validation(res, 'get disk data')


def avg_is_iocollect_valid(io_dic, config_disk, config_stage):
    """is_iocollect_valid from sentryCollector"""
    logging.debug(f"send to sentryCollector is_iocollect_valid: period={io_dic['period_time']}, "
                f"disk={config_disk}, stage={config_stage}")
    res = is_iocollect_valid(io_dic["period_time"], config_disk, config_stage)
    is_success, data = check_result_validation(res, 'check config validation')
    if not is_success:
        report_alarm_fail(f"{data['msg']}")
    return data


def check_result_validation(res, reason):
    """check validation of result from sentryCollector"""
    if not 'ret' in res or not 'message' in res:
        return False, {'msg': f"Failed to {reason}: Cannot connect to sentryCollector"}
    if res['ret'] != 0:
        return False, {'msg': f"Failed to {reason}: {Result_Messages[res['ret']]}"}

    try:
        json_data = json.loads(res['message'])
    except json.JSONDecodeError:
        return False, {'msg': f"Failed to {reason}: invalid return message"}

    return True, json_data


def report_alarm_fail(alarm_info):
    """report result to xalarmd"""
    report_result(TASK_NAME, ResultLevel.FAIL, json.dumps({"msg": alarm_info}))
    logging.critical(alarm_info)
    sys.exit(1)


def process_report_data(disk_name, rw, io_data):
    """check abnormal window and report to xalarm"""
    abnormal, abnormal_list = is_abnormal((disk_name, 'bio', rw), io_data)
    if not abnormal:
        return

    msg = {
        "alarm_source": TASK_NAME, "driver_name": disk_name, "io_type": rw,
        "reason": "unknown", "block_stack": "bio", "alarm_type": abnormal_list,
        "details": get_win_data(disk_name, rw, io_data)
        }

    # io press
    ctrl_stage = ['throtl', 'wbt', 'iocost', 'bfq']
    for stage_name in ctrl_stage:
        abnormal, abnormal_list = is_abnormal((disk_name, stage_name, rw), io_data)
        if not abnormal:
            continue
        msg["reason"] = "IO press"
        msg["block_stack"] = f"bio,{stage_name}"
        msg["alarm_type"] = abnormal_list
        log_slow_win(msg, "IO press")
        del msg["details"]["iodump_data"] # 极端场景下iodump_data可能过大,导致发送失败,所以只在日志中打印,不发送到告警模块
        del msg["details"]["disk_data"]
        xalarm_report(1002, MINOR_ALM, ALARM_TYPE_OCCUR, json.dumps(msg))
        return

    # driver slow
    abnormal, abnormal_list = is_abnormal((disk_name, 'rq_driver', rw), io_data)
    if abnormal:
        msg["reason"] = "driver slow"
        msg["block_stack"] = "bio,rq_driver"
        msg["alarm_type"] = abnormal_list
        log_slow_win(msg, "driver slow")
        del msg["details"]["iodump_data"] # 极端场景下iodump_data可能过大,导致发送失败,所以只在日志中打印,不发送到告警模块
        del msg["details"]["disk_data"]
        xalarm_report(1002, MINOR_ALM, ALARM_TYPE_OCCUR, json.dumps(msg))
        return

    # kernel slow
    kernel_stage = ['gettag', 'plug', 'deadline', 'hctx', 'requeue']
    for stage_name in kernel_stage:
        abnormal, abnormal_list = is_abnormal((disk_name, stage_name, rw), io_data)
        if not abnormal:
            continue
        msg["reason"] = "kernel slow"
        msg["block_stack"] = f"bio,{stage_name}"
        msg["alarm_type"] = abnormal_list
        log_slow_win(msg, "kernel slow")
        del msg["details"]["iodump_data"] # 极端场景下iodump_data可能过大,导致发送失败,所以只在日志中打印,不发送到告警模块
        del msg["details"]["disk_data"]
        xalarm_report(1002, MINOR_ALM, ALARM_TYPE_OCCUR, json.dumps(msg))
        return

    log_slow_win(msg, "unknown")
    del msg["details"]["iodump_data"] # 极端场景下iodump_data可能过大,导致发送失败,所以只在日志中打印,不发送到告警模块
    del msg["details"]["disk_data"]
    xalarm_report(1002, MINOR_ALM, ALARM_TYPE_OCCUR, json.dumps(msg))


def check_disk_list_validation(disk_list):
    valid_disk_list = []
    for disk_name in disk_list:
        is_success, _ = check_result_validation(get_disk_type(disk_name), "")
        if not is_success:
            continue
        valid_disk_list.append(disk_name)
    return valid_disk_list


def get_disk_type_by_name(disk_name):
    logging.debug(f"send to sentryCollector get_disk_type: disk_name={disk_name}")
    is_success, disk_type_str = check_result_validation(get_disk_type(disk_name), f'Invalid disk type {disk_name}')
    if not is_success:
        report_alarm_fail(f"{disk_type_str['msg']}")
    try:
        curr_disk_type = int(disk_type_str)
        if curr_disk_type not in Disk_Type:
            raise ValueError
    except ValueError:
        report_alarm_fail(f"Failed to get disk type for {disk_name}")
    
    return Disk_Type[curr_disk_type]
