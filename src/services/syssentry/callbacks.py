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
