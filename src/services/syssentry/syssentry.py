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
main loop for syssentry.
"""
import sys
import signal
import traceback
import socket
import os
import json
import logging
import fcntl

import select

from .sentry_config import SentryConfig, get_log_level
from .task_map import TasksMap
from .global_values import SENTRY_RUN_DIR, SENTRY_RUN_DIR_PERM
from .cron_process import period_tasks_handle
from .callbacks import (
    mod_list_show,
    task_start,
    task_get_status,
    task_stop,
    task_get_result,
    task_get_alarm,
    task_set
)
from .mod_status import get_task_by_pid, set_runtime_status
from .mod_status import RUNNING_STATUS, EXITED_STATUS, NONZERO_EXITED_STATUS, FAILED_STATUS, WAITING_STATUS
from .load_mods import load_tasks, reload_single_mod
from .heartbeat import (heartbeat_timeout_chk, heartbeat_recv)
from .result import RESULT_MSG_HEAD_LEN, RESULT_MSG_MAGIC_LEN, RESULT_MAGIC
from .result import RESULT_LEVEL_ERR_MSG_DICT, ResultLevel
from .utils import get_current_time_string, MAX_MSG_LEN
from .alarm import alarm_register

from xalarm.register_xalarm import xalarm_unregister

CPU_EXIST = True
try:
    from sentryPlugins.cpu_sentry.cpu_alarm import cpu_alarm_recv
except ImportError:
    CPU_EXIST = False

BMC_EXIST = True
try:
    from .bmc_alarm import bmc_recv
except ImportError:
    BMC_EXIST = False


exit_flag = False

CTL_MSG_HEAD_LEN = 6
CTL_MSG_MAGIC_LEN = 3
CTL_MSG_LEN_LEN = 3
CTL_MAGIC = "CTL"
RES_MAGIC = "RES"
ALARM_MSG_DATA_LEN = 6

CTL_LISTEN_QUEUE_LEN = 5
SERVER_EPOLL_TIMEOUT = 0.3

# func contains one arg
type_func = {
    'start': task_start,
    'stop': task_stop,
    'get_status': task_get_status,
    'get_result': task_get_result,
    'get_alarm': task_get_alarm,
    'reload': reload_single_mod,
    'set': task_set
}

# func has no arg
type_func_void = {
    'mod_list': mod_list_show,
}

DEV_NULL_PATH = '/dev/null'
ROOT_PATH = '/'

SYSSENTRY_LOG_FILE = "/var/log/sysSentry/sysSentry.log"

SYSSENTRY_PID_FILE = "/var/run/sysSentry/sysSentry.pid"
PID_FILE_FLOCK = None

# result-specific socket
RESULT_SOCKET_PATH = "/var/run/sysSentry/result.sock"

CPU_ALARM_SOCKET_PATH = "/var/run/sysSentry/report.sock"

BMC_SOCKET_PATH = "/var/run/sysSentry/bmc.sock"

fd_list = []


def get_syssentry_systemd_sockets():
    """Get file descriptors from systemd socket activation using LISTEN_FDS"""
    # sysSentry socket fds
    global server_fd
    global server_result_fd
    global heartbeat_fd
    global cpu_alarm_fd
    global bmc_fd

    listen_pid = int(os.environ.get('LISTEN_PID', '0'))
    listen_fds = int(os.environ.get('LISTEN_FDS', '0'))
    # we have at least 5 sockets
    if listen_pid != os.getpid() or listen_fds < 5:
        logging.error("fd/pid verify failed, systemd socket activation maybe not available or invalid")
        logging.error("Please ensure sysSentry.socket is enabled and started")
        logging.error("Run: systemctl enable sysSentry.socket && systemctl start sysSentry.socket")
        return -1
    try:
        # File descriptors start from 3 (SD_LISTEN_FDS_START)
        for fd_offset in range(listen_fds):
            fd = 3 + fd_offset
            test_sock = socket.fromfd(fd, socket.AF_UNIX, socket.SOCK_STREAM)
            sock_type_val = test_sock.getsockopt(1, 3)
            test_sock.close()
            if sock_type_val == socket.SOCK_STREAM:
                stream_sock = socket.fromfd(fd, socket.AF_UNIX, socket.SOCK_STREAM)
                stream_sock.setblocking(False)
                if stream_sock.getsockname() == "/run/sysSentry/control.sock":
                    server_fd = stream_sock
                elif stream_sock.getsockname() == "/run/sysSentry/result.sock":
                    server_result_fd = stream_sock
                elif stream_sock.getsockname() == "/run/sysSentry/heartbeat.sock":
                    heartbeat_fd = stream_sock
                elif stream_sock.getsockname() == "/run/sysSentry/report.sock":
                    cpu_alarm_fd = stream_sock
                elif stream_sock.getsockname() == "/run/sysSentry/bmc.sock":
                    bmc_fd = stream_sock
                else:
                    logging.error("Found Unknown STREAM socket at FD %d (%s)", fd, stream_sock.getsockname())
                    return -1
                logging.info("Found STREAM socket at FD %d (%s)", fd, stream_sock.getsockname())
            else:
                logging.error("Unknown socket type %d at FD %d", sock_type_val, fd)
                return -1
    except (ValueError, AttributeError) as e:
        logging.warning("Failed to parse LISTEN_FDS: %s", str(e))
        return -1
    return 0


def msg_data_process(msg_data):
    """message data process"""
    logging.debug("msg_data %s", msg_data)
    try:
        data_struct = json.loads(msg_data)
    except json.JSONDecodeError:
        logging.error("msg data process: json decode error")
        return "Request message decode failed"

    if 'type' not in data_struct:
        logging.error("recv message format error, type is not exist")
        return "Request message format error"

    if 'data' not in data_struct:
        logging.error("recv message format error, data is not exist")
        return "Request message format error"

    cmd_type = data_struct['type']
    if cmd_type not in type_func and cmd_type not in type_func_void:
        logging.error("recv invalid cmd type: %s", cmd_type)
        return "Invalid cmd type"

    cmd_param = data_struct['data']
    logging.debug("msg_data_process cmd_type:%s cmd_param:%s", cmd_type, str(cmd_param))
    if cmd_type in type_func:
        ret, res_data = type_func[cmd_type](cmd_param)
    else:
        ret, res_data = type_func_void[cmd_type]()
    logging.debug("msg_data_process res_data:%s",str(res_data))
    res_msg_struct = {"ret": ret, "data": res_data}
    res_msg = json.dumps(res_msg_struct)

    return res_msg


def process_and_update_task_result(result_msg_data: dict) -> bool:
    '''
    result_msg_data format is as follows:
    {
        "task_name" : task_name, # (eg. npu_sentry),
        "result_data" : {
            "result": ResultLevel,
            "details": {},
        },
    }
    result is what 'sentryctl get-result task_name' needs to output
    '''
    try:
        data_struct = json.loads(result_msg_data)
    except json.decoder.JSONDecodeError:
        logging.error("result msg data process: json decode error")
        return False

    if 'task_name' not in data_struct:
        logging.error("recv message format error, task_name is not exist")
        return False

    if 'result_data' not in data_struct:
        logging.error("recv message format error, result is not exist")
        return False

    task = TasksMap.get_task_by_name(data_struct['task_name'])
    if not task:
        logging.error("task '%s' does not exist!!", data_struct['task_name'])
        return False

    result_data = data_struct.get("result_data", {})
    sentry_result = result_data.get("result")
    sentry_detail = result_data.get("details")
    if sentry_result not in ResultLevel.__members__:
        logging.error("recv 'result' does not belong to ResultLevel members!")
        return False
    if not isinstance(sentry_detail, dict):
        logging.debug("recv 'details' must be dict object, try to convert it to a dict obj")
        try:
            sentry_detail = json.loads(sentry_detail)
        except (json.decoder.JSONDecodeError, TypeError):
            logging.error("'details' is malformed, it should be a dictionary formatted string")
            return False
    task.result_info["result"] = sentry_result
    task.result_info["details"] = sentry_detail
    task.result_info["error_msg"] = RESULT_LEVEL_ERR_MSG_DICT.get(sentry_result, "")

    return True


def msg_head_process(msg_head):
    """message head process"""
    ctl_magic = msg_head[:CTL_MSG_MAGIC_LEN]
    if ctl_magic != CTL_MAGIC:
        logging.error("recv msg head magic invalid: %s", ctl_magic)
        return -1

    data_len_str = msg_head[CTL_MSG_LEN_LEN:CTL_MSG_HEAD_LEN]
    try:
        data_len = int(data_len_str)
    except ValueError:
        logging.error("recv msg data len is invalid %s", data_len_str)
        return -1

    return data_len


def result_msg_head_process(msg_head):
    """result message head process"""
    result_magic = msg_head[:RESULT_MSG_MAGIC_LEN]
    if result_magic != RESULT_MAGIC:
        logging.error("recv result msg head magic invalid: %s", result_magic)
        return -1

    data_len_str = msg_head[RESULT_MSG_MAGIC_LEN:RESULT_MSG_HEAD_LEN]
    try:
        data_len = int(data_len_str)
    except ValueError:
        logging.error("recv result msg data len is invalid %s", data_len_str)
        return -1
    return data_len


def server_recv(server_socket: socket.socket):
    """server receive"""
    try:
        client_socket, _ = server_socket.accept()
        logging.debug("server_fd listen ok")
    except socket.error:
        logging.error("server accept failed")
        return

    try:
        msg_head = client_socket.recv(CTL_MSG_HEAD_LEN)
        logging.debug("recv msg head: %s", msg_head.decode())
        data_len = msg_head_process(msg_head.decode())
    except (OSError, UnicodeError):
        client_socket.close()
        logging.error("server recv HEAD failed")
        return

    logging.debug("msg data length: %d", data_len)
    if data_len < 0:
        client_socket.close()
        logging.error("msg head parse failed")
        return
    if data_len > MAX_MSG_LEN:
        client_socket.close()
        logging.error("socket recv data is illegal:%d", data_len)
        return
    try:
        msg_data = client_socket.recv(data_len)
        msg_data_decode = msg_data.decode()
        logging.debug("msg data %s", msg_data_decode)
    except (OSError, UnicodeError):
        client_socket.close()
        logging.error("server recv MSG failed")
        return

    res_data = msg_data_process(msg_data_decode)
    logging.debug("res data %s", res_data)

    cmd_type = ""
    try:
        msg_data_decode_dict = json.loads(msg_data_decode)
        cmd_type = msg_data_decode_dict.get("type")
    except json.JSONDecodeError:
        client_socket.close()
        logging.error("msg data process: msg_data_decode json decode error")
        return


    res_head = RES_MAGIC
    if cmd_type == "get_result":
        res_data_len = str(len(res_data)).zfill(RESULT_MSG_HEAD_LEN - RESULT_MSG_MAGIC_LEN)
    elif cmd_type == "get_alarm":
        res_data_len = str(len(res_data)).zfill(ALARM_MSG_DATA_LEN)
    else:
        res_data_len = str(len(res_data)).zfill(CTL_MSG_MAGIC_LEN)
    res_head += res_data_len
    logging.debug("res head %s", res_head)

    res_msg = res_head + res_data
    logging.debug("res msg %s", res_msg)

    try:
        client_socket.send(res_msg.encode())
    except OSError:
        logging.error("server recv failed")
    finally:
        client_socket.close()
    return


def server_result_recv(server_socket: socket.socket):
    """server result receive"""
    try:
        client_socket, _ = server_socket.accept()
        logging.debug("server_fd listen ok")
    except socket.error:
        logging.error("server accept failed")
        return

    try:
        msg_head = client_socket.recv(RESULT_MSG_HEAD_LEN)
        logging.debug("recv msg head: %s", msg_head.decode())
        data_len = result_msg_head_process(msg_head.decode())
    except (OSError, UnicodeError):
        client_socket.close()
        logging.error("server recv HEAD failed")
        return

    logging.debug("msg data length: %d", data_len)
    if data_len < 0:
        client_socket.close()
        logging.error("msg head parse failed")
        return
    if data_len > MAX_MSG_LEN:
        client_socket.close()
        logging.error("socket recv data is illegal:%d", data_len)
        return

    try:
        msg_data = client_socket.recv(data_len)
        msg_data_decode = msg_data.decode()
        logging.info("server recv result data :\n%s\n", msg_data_decode)
    except (OSError, UnicodeError):
        client_socket.close()
        logging.error("server recv MSG failed")
        return

    # update result
    process_plugins_result = "SUCCESS"
    if not process_and_update_task_result(msg_data_decode):
        process_plugins_result = "FAILED"
        logging.error("process server recv MSG failed")

    # response to client
    logging.info("result recv msg head : %s , response ...", process_plugins_result)
    try:
        client_socket.send(process_plugins_result.encode())
    except OSError:
        logging.warning("server send response to plugins failed")
    finally:
        client_socket.close()
    return


def close_all_fd():
    for fd in fd_list:
        fd.close()


def main_loop():
    """main loop"""

    # get sockets
    ret = get_syssentry_systemd_sockets()
    if ret != 0:
        logging.error("get sysSentry sockets failed")
        return

    fd_list.append(server_fd)
    fd_list.append(server_result_fd)
    fd_list.append(heartbeat_fd)
    fd_list.append(cpu_alarm_fd)
    fd_list.append(bmc_fd)

    epoll_fd = select.epoll()
    for fd in fd_list:
        epoll_fd.register(fd.fileno(), select.EPOLLIN)

    logging.debug("start main loop")
    # onstart_tasks_handle()
    for task_type in TasksMap.tasks_dict:
        for task_name in TasksMap.tasks_dict.get(task_type):
            task = TasksMap.tasks_dict.get(task_type).get(task_name)
            if not task:
                continue
            task.onstart_handle()

    global exit_flag
    while not exit_flag:
        try:
            events_list = epoll_fd.poll(SERVER_EPOLL_TIMEOUT)
            for event_fd, _ in events_list:
                if event_fd == server_fd.fileno():
                    server_recv(server_fd)
                elif event_fd == server_result_fd.fileno():
                    server_result_recv(server_result_fd)
                elif event_fd == heartbeat_fd.fileno():
                    heartbeat_recv(heartbeat_fd)
                elif CPU_EXIST and event_fd == cpu_alarm_fd.fileno():
                    cpu_alarm_recv(cpu_alarm_fd)
                elif BMC_EXIST and event_fd == bmc_fd.fileno():
                    bmc_recv(bmc_fd)
                else:
                    continue

        except socket.error:
            pass

        # handle period task
        period_tasks_handle()
        # handle heartbeat msg
        heartbeat_timeout_chk()


def release_pidfile():
    """
    :return:
    """
    try:
        pid_file_fd = open(SYSSENTRY_PID_FILE, 'w')
        os.chmod(SYSSENTRY_PID_FILE, 0o600)
        fcntl.flock(pid_file_fd, fcntl.LOCK_UN)
        pid_file_fd.close()
        PID_FILE_FLOCK.close()
        os.unlink(SYSSENTRY_PID_FILE)
    except (IOError, FileNotFoundError):
        logging.error("Failed to release PID file lock")


def sigchld_handler(signum, _f):
    """child sig handler
    """
    while True:
        try:
            child_pid, child_status = os.waitpid(-1, os.WNOHANG)
            logging.debug("sigchld pid :%d", child_pid)
            task = get_task_by_pid(child_pid)
            if not task:
                logging.debug("pid %d cannot find task, ignore", child_pid)
                break
            logging.debug("task name %s", task.name)
            if os.WIFEXITED(child_status):
                # exit normally with exit() syscall
                logging.info("task %s exit with status %d", task.name, os.WEXITSTATUS(child_status))
                if task.type == "PERIOD":
                    if task.period_enabled:
                        set_runtime_status(task.name, WAITING_STATUS)
                    else:
                        set_runtime_status(task.name, EXITED_STATUS)
                else:
                    if os.WEXITSTATUS(child_status):
                        set_runtime_status(task.name, NONZERO_EXITED_STATUS)
                    else:
                        set_runtime_status(task.name, EXITED_STATUS)
            else:
                # exit abnormally
                logging.info("task %s terminated", task.name)
                if task.type == "PERIOD" and task.period_enabled:
                    set_runtime_status(task.name, WAITING_STATUS)
                else:
                    set_runtime_status(task.name, FAILED_STATUS)
            task.result_info["end_time"] = get_current_time_string()
        except:
            break


def sig_handler(signum, _f):
    """
    :param signum:
    :param _f:
    :return:
    """
    global exit_flag
    if signum not in (signal.SIGINT, signal.SIGTERM):
        return
    exit_flag = True


def chk_and_set_pidfile():
    """
    :return:
    """
    try:
        pid_file_fd = open(SYSSENTRY_PID_FILE, 'w')
        os.chmod(SYSSENTRY_PID_FILE, 0o600)
        fcntl.flock(pid_file_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pid_file_fd.write(str(os.getpid()))
        global PID_FILE_FLOCK
        PID_FILE_FLOCK = pid_file_fd
        return True
    except IOError:
        logging.error("Failed to get lock on pidfile")

    return False


def clean_child():
    tasks_dict = TasksMap.tasks_dict
    for task_type in tasks_dict:
        for task_name in tasks_dict[task_type]:
            task = tasks_dict[task_type][task_name]
            task.stop()
            if task.pid > 0:
                try:
                    os.kill(task.pid, signal.SIGTERM)
                except os.error as os_error:
                    logging.debug("sigterm kill error, %s", str(os_error))


def main():
    """main
    """
    if not os.path.exists(SENTRY_RUN_DIR):
        os.mkdir(SENTRY_RUN_DIR)
        os.chmod(SENTRY_RUN_DIR, mode=SENTRY_RUN_DIR_PERM)

    log_level = get_log_level()
    log_format = "%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"

    logging.basicConfig(filename=SYSSENTRY_LOG_FILE, level=log_level, format=log_format)
    os.chmod(SYSSENTRY_LOG_FILE, 0o600)

    if not chk_and_set_pidfile():
        logging.error("get pid file lock failed, exist")
        sys.exit(17)

    client_id = -1
    try:
        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)
        signal.signal(signal.SIGHUP, sig_handler)
        signal.signal(signal.SIGCHLD, sigchld_handler)

        logging.info("finish main parse_args")

        _ = SentryConfig.init_param()
        TasksMap.init_task_map()
        load_tasks()
        client_id = alarm_register()
        main_loop()

    except Exception as e:
        logging.error(traceback.format_exc())
    finally:
        if client_id != -1:
            xalarm_unregister(client_id)
        clean_child()
        release_pidfile()
