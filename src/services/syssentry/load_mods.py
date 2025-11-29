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
load mod from file.
"""
import os
import logging
import configparser
import re

from .sentry_config import SentryConfig

from .global_values import TYPES_SET, InspectTask, TASKS_STORAGE_PATH, SYSSENTRY_CONF_PATH
from .task_map import TasksMap, ONESHOT_TYPE, PERIOD_TYPE
from .cron_process import PeriodTask
from .mod_status import set_task_status

ONESHOT_CONF = 'oneshot'
PERIOD_CONF = 'period'

CONF_TASK = 'common'
CONF_NAME = 'name'
CONF_TYPE = 'type'
CONF_ENABLED = 'enabled'
CONF_TASK_PRE = "task_pre"
CONF_TASK_POST = "task_post"
CONF_TASK_START = 'task_start'
CONF_TASK_STOP = 'task_stop'
CONF_TASK_RELOAD = 'task_reload'
CONF_PERIOD_INTERVAL = 'interval'
CONF_HEARTBEAT_INTERVAL = 'heartbeat_interval'
CONF_HEARTBEAT_ACTION = 'heartbeat_action'
CONF_TASK_RESTART = 'task_restart'
CONF_ONSTART = 'onstart'
CONF_ENV_FILE = 'env_file'
CONF_CONFLICT = 'conflict'
CONF_ALARM_ID = 'alarm_id'
CONF_ALARM_CLEAR_TIME = 'alarm_clear_time'

MOD_FILE_SUFFIX = '.mod'
MOD_SUFFIX_LEN = 4

ENABLED_FLAGS_SET = ("yes", "no")
ONSTART_FLAGS_SET = ("yes", "no")


def mod_name_verify(mod_name):
    """
    :param mod_path:
    :return:
    """
    mod_path_all = os.path.join(TASKS_STORAGE_PATH, mod_name + ".mod")
    real_path = os.path.realpath(mod_path_all)
    if not real_path.startswith(TASKS_STORAGE_PATH):
        return False

    mod_base_name = os.path.basename(real_path)
    if mod_base_name != mod_name + ".mod":
        return False

    # add mod name character type check
    pattern = r'^\w+$'
    if not bool(re.match(pattern, mod_name)):
        return False

    mod_path = os.path.join(TASKS_STORAGE_PATH, mod_base_name)
    if mod_path != real_path:
        return False

    if not os.path.exists(mod_path):
        return False

    return True


def chk_enabled_conf(mod_conf):
    """
    :param mod_conf:
    :return:
    """
    if CONF_ENABLED not in mod_conf[CONF_TASK]:
        logging.error("enabled not in this mod file")
        return False
    enabled_flag = mod_conf[CONF_TASK][CONF_ENABLED]
    if enabled_flag not in ENABLED_FLAGS_SET:
        logging.error("enabled conf error %s", enabled_flag)
        return False

    return True


def chk_type_conf(mod_conf):
    """
    :param mod_conf:
    :return:
    """
    if CONF_TYPE not in mod_conf[CONF_TASK] or \
            CONF_TASK_START not in mod_conf[CONF_TASK] or \
            CONF_TASK_STOP not in mod_conf[CONF_TASK]:
        return False

    if mod_conf[CONF_TASK][CONF_TYPE] not in TYPES_SET:
        return False

    return True


def parse_heartbeat_conf(mod_conf):
    """
    :param mod_conf:
    :return:
    """
    heartbeat_interval = -1
    try:
        heartbeat_interval = int(mod_conf[CONF_TASK][CONF_HEARTBEAT_INTERVAL])
    except ValueError:
        logging.error("heartbeat interval is invalid")
        heartbeat_interval = -1

    if heartbeat_interval <= 0:
        logging.error("heartbeat interval %d is invalid", heartbeat_interval)
        heartbeat_interval = -1

    if heartbeat_interval < 60:
        logging.warning("hearbeat_interval cannot be less than 60, set to 60")
        heartbeat_interval = 60

    return heartbeat_interval


def parse_period_delay(mod_conf):
    """
    :param mod_conf:
    :return:
    """
    if CONF_PERIOD_INTERVAL not in mod_conf[CONF_TASK]:
        cron_delay = SentryConfig.inspect_delay
        logging.debug("period delay use global value %s", cron_delay)
        return cron_delay

    try:
        cron_delay = int(mod_conf[CONF_TASK][CONF_PERIOD_INTERVAL])
    except ValueError:
        logging.error("period delay is invalid")
        cron_delay = SentryConfig.inspect_delay
    if cron_delay <= 0:
        logging.error("period delay is invalid")
        cron_delay = SentryConfig.inspect_delay
    logging.debug("period delay is %s", cron_delay)

    return cron_delay


def parse_mod_conf(mod_name, mod_conf):
    """
    :param mod_name:
    :param mod_conf:
    :return:
    """
    if not mod_conf.has_section(CONF_TASK):
        logging.error("common not in this mod file")
        return None
    if not chk_enabled_conf(mod_conf):
        return None
    if not chk_type_conf(mod_conf):
        logging.error("mod %s: type conf is invalid", mod_name)
        return None

    is_enabled = (mod_conf.get(CONF_TASK, CONF_ENABLED) == 'yes')

    task_type = mod_conf.get(CONF_TASK, CONF_TYPE)
    task_pre_cmd = None
    task_post_cmd = None
    if mod_conf.has_option(CONF_TASK, CONF_TASK_PRE):
        task_pre_cmd = mod_conf.get(CONF_TASK, CONF_TASK_PRE)
    if mod_conf.has_option(CONF_TASK, CONF_TASK_POST):
        task_post_cmd = mod_conf.get(CONF_TASK, CONF_TASK_POST)
    task_start_cmd = mod_conf.get(CONF_TASK, CONF_TASK_START)
    task_stop_cmd = mod_conf.get(CONF_TASK, CONF_TASK_STOP)
    heartbeat_interval = -1
    logging.debug("task method: start: %s stop: %s", task_start_cmd, task_stop_cmd)
    if CONF_HEARTBEAT_INTERVAL in mod_conf.options(CONF_TASK):
        heartbeat_interval = parse_heartbeat_conf(mod_conf)
        logging.debug("task heartbeat is enabled, interval is %d", heartbeat_interval)

    cron_delay = None
    if task_type == PERIOD_CONF:
        logging.debug("task is a period task")
        cron_delay = parse_period_delay(mod_conf)
        task = PeriodTask(mod_name, task_type.upper(), task_pre_cmd, task_post_cmd,
                          task_start_cmd, task_stop_cmd, cron_delay)
        task.task_stop = task_stop_cmd
    else:
        task_type = ONESHOT_TYPE
        task = InspectTask(mod_name, task_type, task_pre_cmd, task_post_cmd, task_start_cmd, task_stop_cmd)
    task.heartbeat_interval = heartbeat_interval
    task.load_enabled = is_enabled

    try:
        task.alarm_id = mod_conf.get(CONF_TASK, CONF_ALARM_ID)
    except configparser.NoOptionError:
        task.alarm_id = None
        logging.warning(f"{mod_name} alarm_id not set, alarm_id is None")

    if task.alarm_id is not None:
        try:
            task.alarm_clear_time = mod_conf.get(CONF_TASK, CONF_ALARM_CLEAR_TIME)
        except configparser.NoOptionError:
            logging.warning(f"{mod_name} not set alarm_clear_time, use 15s as default")

    if CONF_ONSTART in mod_conf.options(CONF_TASK):
        is_onstart = (mod_conf.get(CONF_TASK, CONF_ONSTART) == 'yes')
        if task_type == PERIOD_CONF:
            is_onstart = (mod_conf.get(CONF_TASK, CONF_ONSTART) != 'no')
        logging.debug("the task ready to start")
        task.onstart = is_onstart

    if CONF_ENV_FILE in mod_conf.options(CONF_TASK):
        env_file_dir = mod_conf.get(CONF_TASK, CONF_ENV_FILE)
        task.env_file = env_file_dir

    if CONF_CONFLICT in mod_conf.options(CONF_TASK):
        conflict = mod_conf.get(CONF_TASK, CONF_CONFLICT)
        task.conflict = conflict

    return task


def load_tasks():
    """load tasks"""
    logging.debug("enter load_tasks")
    # mod files store in /etc/sysSentry/tasks/
    if not os.path.exists(SYSSENTRY_CONF_PATH):
        logging.error("%s not existed", SYSSENTRY_CONF_PATH)
        return "failed", ""
    if not os.path.exists(TASKS_STORAGE_PATH):
        logging.error("%s not existed", TASKS_STORAGE_PATH)
        return "failed", ""

    mod_files = os.listdir(TASKS_STORAGE_PATH)
    mod_files.sort()
    for mod_file in mod_files:
        logging.debug("find mod, path is %s", mod_file)
        if not mod_file.endswith(MOD_FILE_SUFFIX):
            continue
        mod_name = mod_file[:-MOD_SUFFIX_LEN]

        if not mod_name_verify(mod_name):
            logging.error("mod name invalid: %s", mod_name)
            continue

        try:
            mod_conf = configparser.ConfigParser()
            mod_conf.read(os.path.join(TASKS_STORAGE_PATH, mod_file))
        except configparser.Error:
            logging.error("configparser parse configure file")
            continue

        new_task = parse_mod_conf(mod_name, mod_conf)
        if not new_task:
            logging.error("mod %s load failed", mod_name)
            continue
        TasksMap.add_task(new_task, new_task.type, mod_name)
        set_task_status(mod_name, "LOADED")

    return "success", ""


def chk_reload_type(mod_name, mod_conf):
    """check reload type"""
    if CONF_TASK not in mod_conf:
        logging.error("common not in mod configure")
        return False

    if CONF_TYPE not in mod_conf[CONF_TASK]:
        logging.error("type not in mod configure")
        return False

    new_type = mod_conf[CONF_TASK][CONF_TYPE].upper()
    for task_type in TasksMap.tasks_dict:
        if mod_name in TasksMap.tasks_dict[task_type]:
            cur_task = TasksMap.tasks_dict[task_type][mod_name]
            if cur_task.type != new_type:
                logging.error("reload: type of mod %s is changed, cannot reload", mod_name)
                return False

    return True


def reload_mod_by_name(mod_name):
    """reload mod by name"""
    if not os.path.exists(SYSSENTRY_CONF_PATH):
        logging.error("%s not existed", SYSSENTRY_CONF_PATH)
        return "failed", "conf dir not exist"
    if not os.path.exists(TASKS_STORAGE_PATH):
        logging.error("%s not existed", TASKS_STORAGE_PATH)
        return "failed", "conf dir not exist"

    try:
        mod_conf = configparser.ConfigParser()
        mod_path = TASKS_STORAGE_PATH + "/" + mod_name + ".mod"
        mod_conf.read(mod_path)
    except configparser.Error:
        logging.error("config parse failed")
        return "failed", "config parse failed"

    if not chk_reload_type(mod_name, mod_conf):
        return "failed", "type of mod is different from old type, reload failed"

    new_task = parse_mod_conf(mod_name, mod_conf)
    if not new_task:
        return "failed", "parse mod conf failed"

    if not TasksMap.is_task_exist(mod_name):
        logging.debug("reload_single_mod cannot find %s", mod_name)
        TasksMap.add_task(new_task, new_task.type, mod_name)
        set_task_status(mod_name, "LOADED")
    else:
        task = TasksMap.get_task_by_name(mod_name)
        task.task_start = new_task.task_start
        task.task_stop = new_task.task_stop
        task.load_enabled = new_task.load_enabled
        task.heartbeat_interval = new_task.heartbeat_interval
        task.onstart = new_task.onstart
        task.env_file = new_task.env_file
        task.conflict = new_task.conflict
        if task.type == PERIOD_TYPE:
            task.interval = new_task.interval
        set_task_status(mod_name, "LOADED")

    return "success", ""


def reload_single_mod(mod_name):
    """reload single mod by name"""
    res = "success"
    ret = ""

    if not mod_name_verify(mod_name):
        return "failed", "mod name invalid"

    res, ret = reload_mod_by_name(mod_name)

    return res, ret

