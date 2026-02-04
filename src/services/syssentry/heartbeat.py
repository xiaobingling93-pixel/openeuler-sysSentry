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
heartbeat for task.
"""
import signal
import time
import os
import logging
import socket

from .mod_status import set_runtime_status, RUNNING_STATUS, FAILED_STATUS
from .global_values import SENTRY_RUN_DIR
from .task_map import TasksMap
from .utils import MAX_MSG_LEN

THB_SOCKET_PATH = "/var/run/sysSentry/heartbeat.sock"
THB_MAGIC = 'THB'
THB_MSG_HEAD_LEN = 6
THB_MSG_MAGIC_LEN = 3
THB_MSG_LEN_LEN = 3


def hb_timeout_chk_interval(task):
    """heartbeat timeout check interval"""
    if task.runtime_status != RUNNING_STATUS:
        return

    if task.last_heartbeat <= 0:
        return

    cur_timestamp = time.perf_counter()
    if cur_timestamp > task.last_heartbeat + task.heartbeat_interval:
        logging.error("task %s heartbeat timeout, last heartbeat time %d", task.name, task.last_heartbeat)
        set_runtime_status(task.name, FAILED_STATUS)
        if task.pid > 0:
            logging.info("killed heartbeat timeout task %s, pid is %d", task.name, task.pid)
            try:
                os.kill(task.pid, signal.SIGTERM)
            except os.error as os_error:
                logging.error("heartbeat timeout kill failed, %s", str(os_error))


def heartbeat_timeout_chk():
    """heartbeat timeout check"""
    tasks_dict = TasksMap.tasks_dict

    for task_type in tasks_dict:
        for task_name in tasks_dict.get(task_type):
            task = tasks_dict.get(task_type).get(task_name)
            hb_timeout_chk_interval(task)


def thb_head_process(msg_head):
    """heartbeat head process"""
    ctl_magic = msg_head[:THB_MSG_MAGIC_LEN]
    if ctl_magic != THB_MAGIC:
        logging.error("recv heartbeat head magic invalid: %s", ctl_magic)
        return -1

    data_len_str = msg_head[THB_MSG_MAGIC_LEN:THB_MSG_HEAD_LEN]
    try:
        data_len = int(data_len_str)
    except ValueError:
        logging.error("heartbeat data len is invalid %s", data_len_str)
        return -1

    return data_len


def heartbeat_recv(heartbeat_socket: socket.socket):
    """heartbeat receiver"""
    try:
        client_socket, _ = heartbeat_socket.accept()
    except OSError:
        logging.error("heartbeat accept failed")
        return

    try:
        msg_head = client_socket.recv(THB_MSG_HEAD_LEN)
    except OSError:
        logging.error("heartbeat recv head failed")
        client_socket.close()
        return

    try:
        logging.debug("hb recv msg head: %s", msg_head.decode())
        data_len = thb_head_process(msg_head.decode())
    except UnicodeError:
        logging.error("heartbeat data length reading failed")
        client_socket.close()
        return

    if data_len < 0:
        logging.error("heartbeat msg head parse failed")
        client_socket.close()
        return
    if data_len > MAX_MSG_LEN:
        client_socket.close()
        logging.error("socket recv data is illegal:%d", data_len)
        return
    logging.debug("hb msg data length: %d", data_len)

    try:
        task_name = client_socket.recv(data_len).decode()
    except (OSError, UnicodeError):
        logging.error("heartbeat recv msg failed")
        client_socket.close()
        return

    logging.debug("hb msg data %s", task_name)

    task = TasksMap.get_task_by_name(task_name)
    if not task:
        logging.error("heartbeat msg: cannot find mod by name %s", task_name)
        client_socket.close()
        return

    if task.runtime_status != RUNNING_STATUS:
        logging.info("task %s is not running, but received heartbeat msg", task_name)
        client_socket.close()
        return

    if task.heartbeat_interval <= 0:
        logging.debug("%s heartbeat not enabled", task.name)
        client_socket.close()
        return

    cur_timestamp = time.perf_counter()
    task.last_heartbeat = cur_timestamp
    logging.info("task %s heartbeat upgrade success, current time is %d", task.name, cur_timestamp)

    client_socket.close()
