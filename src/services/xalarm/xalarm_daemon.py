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
Description: xalarm daemon
Author:
Create: 2023-11-02
"""

import os
import sys
import logging
import signal
import fcntl
import socket

from .xalarm_config import config_init, get_log_level
from .xalarm_server import server_loop, SOCK_FILE

ALARM_DIR = "/var/run/xalarm"
ALARM_DIR_PERMISSION = 0o750
ALARM_LOGFILE = '/var/log/sysSentry/xalarm.log'
XALARMD_PID_FILE = "/var/run/xalarm/xalarmd.pid"
PID_FILE_FLOCK = None


def chk_and_set_pidfile():
    """
    :return:
    """
    try:
        pid_file_fd = open(XALARMD_PID_FILE, 'w')
        os.chmod(XALARMD_PID_FILE, 0o600)
        fcntl.flock(pid_file_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pid_file_fd.write(str(os.getpid()))
        global PID_FILE_FLOCK
        PID_FILE_FLOCK = pid_file_fd
        return True
    except IOError:
        logging.error("Failed to get lock on pidfile")

    return False


def release_pidfile():
    """
    :return:
    """
    try:
        pid_file_fd = open(XALARMD_PID_FILE, 'w')
        os.chmod(XALARMD_PID_FILE, 0o600)
        fcntl.flock(pid_file_fd, fcntl.LOCK_UN)
        pid_file_fd.close()
        PID_FILE_FLOCK.close()
        os.unlink(XALARMD_PID_FILE)
    except (IOError, FileNotFoundError):
        logging.error("Failed to release PID file lock")


def signal_handler(signum, _f):
    """signal handler
    """
    if signum == signal.SIGTERM:
        try:
            os.unlink(SOCK_FILE)
        except FileNotFoundError:
            pass
        release_pidfile()
        sys.exit(0)


def daemon_init():
    """daemon initialize
    """
    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    os.chdir('/')
    os.umask(0)
    os.setsid()

    with open('/dev/null') as read_null, open('/dev/null', 'a+') as write_null:
        os.dup2(read_null.fileno(), sys.stdin.fileno())
        os.dup2(write_null.fileno(), sys.stdout.fileno())
        os.dup2(write_null.fileno(), sys.stderr.fileno())

    if not chk_and_set_pidfile():
        logging.error("get pid file lock failed, exist")
        sys.exit(17)

    logging.info("xalarm daemon init success")


def daemon_main():
    """daemon main
    """
    daemon_init()
    try:
        alarm_config = config_init()
        server_loop(alarm_config)
    except socket.error:
        release_pidfile()


def alarm_process_create():
    """alarm daemon process create
    """
    if not os.path.exists(os.path.dirname(ALARM_LOGFILE)):
        os.mkdir(os.path.dirname(ALARM_LOGFILE), 0o700)

    if not os.path.exists(ALARM_DIR):
        os.mkdir(ALARM_DIR)
        os.chmod(ALARM_DIR, ALARM_DIR_PERMISSION)

    log_level = get_log_level()
    log_format = "%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"

    logging.basicConfig(filename=ALARM_LOGFILE, level=log_level, format=log_format)

    signal.signal(signal.SIGTERM, signal_handler)

    os.chmod(ALARM_LOGFILE, 0o600)

    logging.info("xalarm daemon init")

    daemon_main()
