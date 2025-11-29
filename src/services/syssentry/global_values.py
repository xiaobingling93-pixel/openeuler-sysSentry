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
period task and global values.
"""
import io
import subprocess
import logging
import time
import os

from .result import ResultLevel, RESULT_LEVEL_ERR_MSG_DICT
from .utils import get_current_time_string
from .mod_status import set_runtime_status
from .mod_status import RUNNING_STATUS, EXITED_STATUS, NONZERO_EXITED_STATUS, FAILED_STATUS, WAITING_STATUS

SENTRY_RUN_DIR = "/var/run/sysSentry"
CTL_SOCKET_PATH = "/var/run/sysSentry/control.sock"
SYSSENTRY_CONF_PATH = "/etc/sysSentry"
INSPECT_CONF_PATH = "/etc/sysSentry/inspect.conf"
TASK_LOG_DIR = "/var/log/sysSentry"
DEFAULT_ALARM_CLEAR_TIME = 15

SENTRY_RUN_DIR_PERM = 0o750

TYPES_SET = ('oneshot', 'period')

# cron process obj
CRON_PROCESS_OBJ = None
# cron task queue
CRON_QUEUE = None

TASKS_STORAGE_PATH = "/etc/sysSentry/tasks"


class InspectTask:
    """oneshot task class"""
    def __init__(self, name: str, task_type: str, start_task: str, stop_task: str):
        self.name = name
        self.type = task_type
        self.status = "ERROR"
        # runtime information
        self.runtime_status = EXITED_STATUS
        self.pid = -1
        # task attribute
        self.task_start = start_task
        self.task_stop = stop_task
        # task heartbeat attribute
        self.heartbeat_interval = -1
        self.last_heartbeat = -1
        # task progress attribute
        self.cur_progress = 0
        # task log file
        self.log_file = TASK_LOG_DIR + '/' + name + '.log'
        self.period_enabled = True
        # load enabled
        self.load_enabled = True
        # init result
        self.result_info = {
            "result": "",
            "start_time": "",
            "end_time": "",
            "error_msg": "",
            "details": {}
        }
        # pull task
        self.onstart = False
        # ccnfig env_file
        self.env_file = ""
        # env conf to popen arg
        self.environ_conf = None
        # start mode
        self.conflict = "up"
        # alarm id
        self.alarm_id = -1
        self.alarm_clear_time = DEFAULT_ALARM_CLEAR_TIME

    def start(self):
        """
        start function we use async mode
        when we have called the start command, function return
        """
        self.result_info["result"] = ""
        self.result_info["start_time"] = get_current_time_string()
        self.result_info["end_time"] = ""
        self.result_info["error_msg"] = ""
        self.result_info["details"] = {}
        if not self.period_enabled:
            self.period_enabled = True
        if self.runtime_status in (EXITED_STATUS, FAILED_STATUS, NONZERO_EXITED_STATUS):

            if self.conflict != 'up':
                ret = self.check_conflict()
                if not ret:
                    return False, "check conflict failed"
            if self.env_file:
                self.load_env_file()

            cmd_list = self.task_start.split()
            try:
                logfile = open(self.log_file, 'a')
                os.chmod(self.log_file, 0o600)
            except OSError:
                self.result_info["result"] = ResultLevel.FAIL.name
                self.result_info["error_msg"] = RESULT_LEVEL_ERR_MSG_DICT.get(ResultLevel.FAIL.name)
                logging.error("task %s log_file %s open failed", self.name, self.log_file)
                logfile = subprocess.PIPE
            try:
                child = subprocess.Popen(cmd_list, stdout=logfile, stderr=subprocess.STDOUT, close_fds=True, env=self.environ_conf)
            except OSError:
                logging.error("task %s start Popen error, invalid cmd", cmd_list)
                self.result_info["result"] = ResultLevel.FAIL.name
                self.result_info["error_msg"] = RESULT_LEVEL_ERR_MSG_DICT.get(ResultLevel.FAIL.name)
                self.runtime_status = FAILED_STATUS
                return False, "start command is invalid, popen failed"
            finally:
                if isinstance(logfile, io.TextIOWrapper) and not logfile.closed:
                    logfile.close()

            self.pid = child.pid
            logging.debug("start task %s pid %d", self.name, self.pid)
            self.runtime_status = RUNNING_STATUS
            if self.heartbeat_interval > 0:
                self.last_heartbeat = time.perf_counter()
            return True, "start task success"
        return True, "task is running, please wait to finish"

    def stop(self):
        """stop"""
        self.period_enabled = False
        if self.runtime_status == RUNNING_STATUS:
            cmd_list = self.task_stop.split()
            if cmd_list[-1] == "$pid":
                cmd_list[-1] = str(self.pid)
            try:
                subprocess.Popen(cmd_list, stdout=subprocess.PIPE, close_fds=True)
            except OSError:
                logging.error("task %s stop Popen failed")
            logging.debug("stop task %s", self.name)

    def get_status(self):
        """get status"""
        return self.runtime_status

    def get_result(self):
        """get result"""
        return self.result_info

    def onstart_handle(self):
        if not self.load_enabled:
            return False
        if not self.onstart:
            return False
        res, _ = self.start()
        if not res:
            return False
        set_runtime_status(self.name, RUNNING_STATUS)

    def check_conflict(self):
        logging.debug("load_env_file detail, task_name: %s, conflict: %s, env_file: %s",
                      self.name, self.conflict, self.env_file)
        pid_list = []
        check_cmd = ["ps", "aux"]
        try:
            result = subprocess.run(check_cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            raise Exception(f"failed with return code {e.returncode}")

        output_lines = result.stdout.decode("utf-8").splitlines()
        for line in output_lines:
            if self.task_start not in line:
                continue
            pid = int(line.split()[1])
            pid_list.append(pid)
        logging.debug("current pid_list = %s", pid_list)

        if self.conflict == "kill" and pid_list:
            for pid in pid_list:
                subprocess.run(["kill", str(pid)], shell=False)
                logging.debug("the program is killed, pid=%d", pid)
        elif self.conflict == "down" and pid_list:
            logging.warning("the conflict field is set to down, so program = [%s] is exited!", self.name)
            return False
        return True

    def load_env_file(self):
        if not os.path.exists(self.env_file):
            logging.warning("env_file: %s is not exist, use default environ", self.env_file)
            return

        if not os.access(self.env_file, os.R_OK):
            logging.warning("env_file: %s is not be read, use default environ", self.env_file)
            return

        # read config
        self.environ_conf = dict(os.environ)
        with open(self.env_file, 'r') as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                value = value.strip('"')
                if not key or not value:
                    logging.error("env_file = %s format is error, use default environ", self.env_file)
                    return
                self.environ_conf[key] = value
                logging.debug("environ key=%s, value=%s", key, value)

        logging.debug("the subprocess=[%s] begin to run", self.name)
