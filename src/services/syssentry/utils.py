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

"""
some common function
"""
import logging
import subprocess
import shlex
from datetime import datetime, timezone, timedelta


def is_valid_cmd(cmd):
    """check cmd"""
    if not isinstance(cmd, str):
        logging.error("cmd must be a string")
        raise ValueError
    if not cmd.strip():
        logging.error("cmd cannot be empty")
        raise ValueError
    return True if cmd.isalnum() else False


def run_cmd(cmd):
    """run cmd use subprocess.run"""
    if not is_valid_cmd(cmd):
        raise ValueError("cmd is illegal")
    result = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return result


def run_popen(cmd):
    """run cmd use subprocess.Popen"""
    if not is_valid_cmd(cmd):
        raise ValueError("cmd is illegal")
    pipe = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return pipe


def is_exists_cmd(cmd: str) -> bool:
    """Checking Whether a Command Exists in the Environment"""
    try:
        res = run_cmd(f"which {cmd}")
    except ValueError:
        return False
    if res.returncode:
        return False
    return True


def get_process_pid(process_name):
    """get the PID of a specified program."""
    process_pid = -1
    if "/" in process_name:
        process_name = process_name.split("/")[-1]
    try:
        res = run_cmd('pgrep -x {}'.format(process_name))
    except ValueError:
        return -1
    if res.returncode == 0:
        process_pid = res.stdout.decode().strip()
        try:
            process_pid = int(process_pid)
        except ValueError:
            process_pid = 0
    return process_pid


def get_current_time_string():
    """get time"""
    current_utc_time = datetime.now(timezone.utc)
    utc8_timezone = timezone(timedelta(hours=8))
    return current_utc_time.astimezone(utc8_timezone).strftime("%Y-%m-%d %H:%M:%S")


def execute_command(cmd_list):
    try:
        if not is_valid_cmd("".join(cmd_list)):
            raise ValueError("cmd is illegal")
        process = subprocess.run(
            cmd_list,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        )
        returncode = process.returncode
        if returncode != 0:
            logging.error("execute command with illegal returncode")
            return None
        return process.stdout
    except (OSError, ValueError):
        logging.error("failed to execute command")
        return None
