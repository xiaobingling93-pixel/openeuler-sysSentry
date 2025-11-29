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
Manage mod status.
"""
import logging

from .task_map import TasksMap, ONESHOT_TYPE, PERIOD_TYPE

ONESHOT_MOD_STATUS = ("UNLOADED", "LOADED", "ERROR")
PERIOD_MOD_STATUS = ("UNLOADED", "LOADED", "ERROR")

RUNNING_STATUS = "RUNNING"
EXITED_STATUS = "EXITED"
NONZERO_EXITED_STATUS = "NONZERO_EXITED"
FAILED_STATUS = "FAILED"
WAITING_STATUS = "WAITING"

ONESHOT_RUNTIME_STATUS = (RUNNING_STATUS, EXITED_STATUS, NONZERO_EXITED_STATUS, FAILED_STATUS)
PERIOD_RUNTIME_STATUS = (RUNNING_STATUS, WAITING_STATUS, FAILED_STATUS, EXITED_STATUS)


def set_task_status(task_name, status_code):
    """set task status"""
    task_type = TasksMap.get_task_type(task_name)
    if not task_type:
        return

    if task_type == ONESHOT_TYPE and status_code in ONESHOT_MOD_STATUS:
        pass
    elif task_type == PERIOD_TYPE and status_code in PERIOD_MOD_STATUS:
        pass
    else:
        return

    TasksMap.tasks_dict.get(task_type).get(task_name).status = status_code
    return


def set_runtime_status(task_name, status_code):
    """set runtime status"""
    task_type = TasksMap.get_task_type(task_name)
    if not task_type:
        logging.error("cannot find task by task name %s", task_name)
        return

    if task_type == ONESHOT_TYPE and status_code in ONESHOT_RUNTIME_STATUS:
        pass
    elif task_type == PERIOD_TYPE and status_code in PERIOD_RUNTIME_STATUS:
        pass
    else:
        logging.error("invalid task name")
        return

    TasksMap.tasks_dict.get(task_type).get(task_name).runtime_status = status_code
    return


def get_task_by_pid(pid):
    """get task by pid"""
    for task_type in TasksMap.tasks_dict:
        for task_name in TasksMap.tasks_dict.get(task_type):
            if TasksMap.tasks_dict.get(task_type).get(task_name).pid == pid:
                return TasksMap.tasks_dict.get(task_type).get(task_name)
    return None
