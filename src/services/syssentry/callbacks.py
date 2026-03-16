# coding: utf-8
# Copyright (c) 2023 Huawei Technologies Co., Ltd.
# sysSentry is licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#     http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
# PURPOSE.
# See the Mulan PSL v2 for more details.

"""
callback methods.
"""
import json
import logging


from .task_map import TasksMap, ONESHOT_TYPE, PERIOD_TYPE
from .mod_status import EXITED_STATUS, NONZERO_EXITED_STATUS, FAILED_STATUS, RUNNING_STATUS, WAITING_STATUS
from .mod_status import set_runtime_status
from .alarm import get_alarm_result
from .sentry_proc import (
    set_sentry_reporter_proc,
    set_remote_reporter_proc,
    set_urma_heartbeat,
    set_uvb_proc,
    set_urma_proc,
    MAX_URMA_EID_LENGTH
)


def task_get_status(mod_name):
    """get status by mod name"""
    task = TasksMap.get_task_by_name(mod_name)
    if not task:
        return "failed", "cannot find task by name"
    if not task.load_enabled:
        return "failed", "mod is not enabled"

    return "success", task.get_status()


def task_get_result(mod_name):
    """get result by mod name"""
    task = TasksMap.get_task_by_name(mod_name)
    if not task:
        return "failed", f"cannot find task by name {mod_name}"
    if not task.load_enabled:
        return "failed", f"mod {mod_name} is not enabled"

    return "success", task.get_result()

def task_get_alarm(data):
    """get alarm by mod name"""
    try:
        task_name = data['task_name']
        time_range = data['time_range']
        detailed = data['detailed']
    except KeyError:
        logging.debug("Key 'detailed' does not exist in the dictionary")
        detailed = None
    task = TasksMap.get_task_by_name(task_name)
    if not task:
        return "failed", f"cannot find task by name {task_name}"
    if not task.load_enabled:
        return "failed", f"mod {task_name} is not enabled"

    return "success", get_alarm_result(task_name, time_range, detailed)

def task_stop(mod_name):
    """stop by mod name"""
    ret = "success"
    res = ""

    task = TasksMap.get_task_by_name(mod_name)
    if task:
        if not task.load_enabled:
            return "failed", "mod is not enabled"
        logging.info("%s stop", mod_name)
        if task.runtime_status in [NONZERO_EXITED_STATUS, EXITED_STATUS, FAILED_STATUS]:
            return "success", "task already stopped"
        if task.runtime_status == WAITING_STATUS:
            set_runtime_status(task.name, EXITED_STATUS)
            return "success", ""
        task.stop()
    else:
        ret = "failed"
        res = "task not exist"

    return ret, res


def task_start(mod_name):
    """start by mod name"""
    ret = "success"
    res = ""

    task = TasksMap.get_task_by_name(mod_name)
    if task:
        if not task.load_enabled:
            return "failed", "mod is not enabled"
        if task.runtime_status == RUNNING_STATUS:
            return "failed", "task is running, please wait"
        logging.info("%s start", mod_name)
        result, msg = task.start()
        ret = "success" if result else "failed"
        res = msg
    else:
        ret = "failed"
        res = "task not exist"

    return ret, res


def mod_list_show():
    """show mod list"""
    ret = "success"
    res_dict = {ONESHOT_TYPE: [], PERIOD_TYPE: []}
    for key in res_dict:
        type_list = TasksMap.tasks_dict.get(key)
        for task_name in type_list:
            task = type_list.get(task_name)
            if not task.load_enabled:
                continue
            res_dict.get(key).append((task_name, task.runtime_status))
    res = json.dumps(res_dict)
    return ret, res


def task_set(set_data):
    """
    set plugin parameters, set_data is dict, eg:
    {
        "set_ko_name": "sentry_reporter",
        "power_off": "on",
        "oom": "off",
    }
    """
    ret_code = 0

    try:
        set_ko_name = set_data.get('set_ko_name')
        if set_ko_name == "sentry_remote_reporter":
            if set_data.get('cna') is not None:
                if int(set_data['cna']) < 0:
                    return "failed", "cna should be a number not less than 0."
                ret_code |= set_remote_reporter_proc("cna", set_data['cna'])
            if set_data.get('eid') is not None:
                eid = set_data['eid']
                num_of_semicolons = eid.count(";")
                if num_of_semicolons > 1:
                    return "failed", "invalid value for extraneous semicolon."
                eid_list = eid.split(";")
                for eid_i in eid_list:
                    if len(eid_i) != MAX_URMA_EID_LENGTH:
                        return "failed", f"The length of eid must be {MAX_URMA_EID_LENGTH}, but the detected input length is {len(eid_i)}."
                ret_code |= set_remote_reporter_proc("eid", eid)
            if set_data.get('uvb_comm') is not None:
                ret_code |= set_remote_reporter_proc("uvb_comm", set_data['uvb_comm'])
            if set_data.get('urma_comm') is not None:
                ret_code |= set_remote_reporter_proc("urma_comm", set_data['urma_comm'])
            if set_data.get('panic') is not None:
                ret_code |= set_remote_reporter_proc("panic", set_data['panic'])
            if set_data.get('panic_timeout_ms') is not None:
                ret_code |= set_remote_reporter_proc("panic_timeout", set_data['panic_timeout_ms'])
            if set_data.get('kernel_reboot') is not None:
                ret_code |= set_remote_reporter_proc("kernel_reboot", set_data['kernel_reboot'])
            if set_data.get('kernel_reboot_timeout_ms') is not None:
                ret_code |= set_remote_reporter_proc("kernel_reboot_timeout", set_data['kernel_reboot_timeout_ms'])
        elif set_ko_name == "sentry_urma_comm":
            if set_data.get('server_eid') is not None and set_data.get('client_jetty_id') is not None:
                ret_code |= set_urma_proc(set_data['server_eid'], set_data['client_jetty_id'])
            elif set_data.get('server_eid') is not None or set_data.get('client_jetty_id') is not None:
                return "failed", "Options --server_eid and --client_jetty_id need to be used together"
            if set_data.get('heartbeat') is not None:
                ret_code |= set_urma_heartbeat(set_data['heartbeat'])
        elif set_ko_name == "sentry_uvb_comm":
            if set_data.get('server_cna') is not None:
                ret_code |= set_uvb_proc(set_data['server_cna'])
        elif set_ko_name == "sentry_reporter":
            if set_data.get('ub_mem_fault_with_kill') is not None:
                ret_code |= set_sentry_reporter_proc("ub_mem_fault_with_kill", set_data['ub_mem_fault_with_kill'])
            if set_data.get('ub_mem_fault') is not None:
                ret_code |= set_sentry_reporter_proc("ub_mem_fault", set_data['ub_mem_fault'])
            if set_data.get('power_off') is not None:
                ret_code |= set_sentry_reporter_proc("power_off", set_data['power_off'])
            if set_data.get('oom') is not None:
                ret_code |= set_sentry_reporter_proc("oom", set_data['oom'])
        else:
            return "failed", "Unknown task name: %s" % set_ko_name
        if ret_code != 0:
            return "failed", "Some parameters failed to set"
        return "success", ""
    except Exception as e:
        logging.error("task_set error: %s", str(e))
        return "failed", str(e)
