# coding: utf-8
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# sysSentry is licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#     http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
# PURPOSE.
# See the Mulan PSL v2 for more details.

"""
kernel sentry proc file write function
"""

import logging

MAX_DIE_NUM = 2
MAX_UVB_CNA_STR_LEN = 22
MAX_NODES = 32
MIN_CLIENT_JETTY_ID = 3
MAX_CLIENT_JETTY_ID = 1023
MAX_URMA_EID_LENGTH = 39


def write_proc_file(proc_dir, proc_name, proc_value):
    """
    Don't use 'shell=True' for subprocess.run/subprocess.Popen, it's not safe. However, if 'shell=true'
    is not set, it is difficult to modify the proc file for subprocess.run/subprocess.Popen.
    """
    exit_code = 0
    try:
        with open("/proc/%s/%s" % (proc_dir, proc_name), mode="w") as f:
            f.write(str(proc_value) + "\n")
    except PermissionError as e:
        exit_code = -e.errno
        logging.error(f"sentryctl: error: set {proc_dir} failed for {proc_name}, the user does not have the permission")
    except FileNotFoundError as e:
        exit_code = -e.errno
        logging.error(f"sentryctl: error: set {proc_dir} failed for {proc_name}, the proc file does not exist!")
    except Exception as e:
        exit_code = getattr(e, 'errno', -1)
        exit_code = -exit_code if exit_code > 0 else -1
        logging.error(f"sentryctl: error: set {proc_dir} failed for {proc_name}")
    return exit_code


def set_sentry_reporter_proc(proc_name, proc_value):
    return write_proc_file("sentry_reporter", proc_name, proc_value)


def set_remote_reporter_proc(proc_name, proc_value):
    return write_proc_file("sentry_remote_reporter", proc_name, proc_value)


def set_urma_heartbeat(proc_value):
    return write_proc_file("sentry_urma_comm", "heartbeat", proc_value)


def set_uvb_proc(server_cna_str):
    if len(server_cna_str.strip()) == 0:
        logging.error("Invalid args for server_cna")
        return -1
    server_cna_list = server_cna_str.strip().split(";")
    if len(server_cna_list) > MAX_NODES:
        logging.error("Exceeded the maximum number (%d) of nodes supported." % MAX_NODES)
        return -1
    for cna in server_cna_list:
        if len(cna.strip()) == 0:
            logging.error("Find invalid cna (%s) for server_cna" % cna)
            return -1
        if len(cna.strip()) > MAX_UVB_CNA_STR_LEN:
            logging.error("Invalid cna (%s) for server_cna" % cna)
            return -1
    server_cna_string = ";".join(server_cna_list)
    return write_proc_file("sentry_uvb_comm", "server_cna", server_cna_string)


def set_urma_proc(server_eid, client_jetty_id):
    if len(server_eid.strip()) == 0:
        logging.error("Invalid args for server_eid, server_eid is empty string")
        return -1
    if client_jetty_id < MIN_CLIENT_JETTY_ID or client_jetty_id > MAX_CLIENT_JETTY_ID:
        logging.error("Invalid args for client_jetty_id")
        return -1

    server_eid_list = server_eid.strip().split(";")
    if len(server_eid_list) > MAX_DIE_NUM:
        logging.error("Invalid args for server_eid, server_eid contains an extra semicolon.")
        return -1
    for server_eid_i in server_eid_list:
        if len(server_eid_i) == 0:
            logging.error("Invalid args for server_eid, server_eid is empty string")
            return -1
        server_eid_list_i = server_eid_i.split(",")
        for eid_i in server_eid_list_i:
            if len(eid_i.strip()) != MAX_URMA_EID_LENGTH:
                logging.error(
                        "Invalid args for server_eid, the length of the eid (%s) does not equal %s.",
                        eid_i,
                        MAX_URMA_EID_LENGTH
                )
                return -1
    write_urma_info = " ".join((server_eid, str(client_jetty_id)))
    return write_proc_file("sentry_urma_comm", "client_info", write_urma_info)


def set_oom_rate_limit_policy(policy_json):
    """
    Set OOM rate limit policy via proc file
    policy_json: JSON string format like '{"RR_KSWAPD": 5, "RR_DIRECT_RECLAIM": 3, "RR_HUGEPAGE_RECLAIM": 2}'
    Returns: 0 on success, negative error code on failure
    """
    return write_proc_file("sentry_reporter", "oom_rate_limit", policy_json)
