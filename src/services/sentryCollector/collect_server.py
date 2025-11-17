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
listen module
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
import threading
import time

from .collect_io import IO_GLOBAL_DATA, IO_CONFIG_DATA, IO_DUMP_DATA, DISK_DATA
from .collect_config import CollectConfig

SENTRY_RUN_DIR = "/var/run/sysSentry"
COLLECT_SOCKET_PATH = "/var/run/sysSentry/collector.sock"

# socket param
CLT_LISTEN_QUEUE_LEN = 5
SERVER_EPOLL_TIMEOUT = 0.3

# data length param
CLT_MSG_HEAD_LEN = 9    #3+2+4
CLT_MSG_PRO_LEN = 2
CLT_MSG_MAGIC_LEN = 3
CLT_MSG_LEN_LEN = 4

# data flag param
CLT_MAGIC = "CLT"
RES_MAGIC = "RES"

# interface protocol
class ServerProtocol():
    IS_IOCOLLECT_VALID = 0
    GET_IO_DATA = 1
    GET_IODUMP_DATA = 2
    GET_DISK_DATA = 3
    PRO_END = 4

class CollectServer():

    def __init__(self):

        self.io_global_data = {}

        self.stop_event = threading.Event()

    @staticmethod
    def get_io_common(data_struct, data_source):
        result_rev = {}

        if len(IO_CONFIG_DATA) == 0:
            logging.error("the collect thread is not started, the data is invalid.")
            return json.dumps(result_rev)
        period_time = IO_CONFIG_DATA[0]
        max_save = IO_CONFIG_DATA[1]

        period = int(data_struct['period'])
        disk_list = json.loads(data_struct['disk_list'])
        stage_list = json.loads(data_struct['stage'])
        iotype_list = json.loads(data_struct['iotype'])

        if (period < period_time) or (period > period_time * max_save) or (period % period_time):
            logging.error("get_io_common: period time is invalid, user period: %d, config period_time: %d",
                           period, period_time)
            return json.dumps(result_rev)

        collect_index = period // period_time - 1
        logging.debug("user period: %d, config period_time: %d,  collect_index: %d", period, period_time, collect_index)

        for disk_name, stage_info in data_source.items():
            if disk_name not in disk_list:
                continue
            result_rev[disk_name] = {}
            for stage_name, iotype_info in stage_info.items():
                if len(stage_list) > 0 and stage_name not in stage_list:
                    continue
                result_rev[disk_name][stage_name] = {}
                for iotype_name, iotype_data in iotype_info.items():
                    if iotype_name not in iotype_list:
                        continue
                    if len(iotype_data) - 1 < collect_index:
                        continue
                    result_rev[disk_name][stage_name][iotype_name] = iotype_data[collect_index]

        return json.dumps(result_rev)

    def is_iocollect_valid(self, data_struct):

        result_rev = {}
        self.io_global_data = IO_GLOBAL_DATA

        if len(IO_CONFIG_DATA) == 0:
            logging.error("the collect thread is not started, the data is invalid.")
            return json.dumps(result_rev)

        period_time = IO_CONFIG_DATA[0]
        max_save = IO_CONFIG_DATA[1]

        disk_list = json.loads(data_struct['disk_list'])
        period = int(data_struct['period'])
        stage_list = json.loads(data_struct['stage'])

        if (period < period_time) or (period > period_time * max_save) or (period % period_time):
            logging.error("is_iocollect_valid: period time is invalid, user period: %d, config period_time: %d", period, period_time)
            return json.dumps(result_rev)

        for disk_name, stage_info in self.io_global_data.items():
            if len(disk_list) > 0 and disk_name not in disk_list:
                continue
            result_rev[disk_name] = []
            if len(stage_list) == 0:
                result_rev[disk_name] = list(stage_info.keys())
                continue
            for stage_name, stage_data in stage_info.items():
                if stage_name in stage_list:
                    result_rev[disk_name].append(stage_name)

        return json.dumps(result_rev)

    def get_io_data(self, data_struct):
        return self.get_io_common(data_struct, IO_GLOBAL_DATA)

    def get_iodump_data(self, data_struct):
        return self.get_io_common(data_struct, IO_DUMP_DATA)

    def get_disk_data(self, data_struct):
        return self.get_io_common(data_struct, DISK_DATA)

    def msg_data_process(self, msg_data, protocal_id):
        """message data process"""
        logging.debug("msg_data %s", msg_data)
        protocol_name = msg_data[0]
        try:
            data_struct = json.loads(msg_data)
        except json.JSONDecodeError:
            logging.error("msg data process: json decode error")
            return "Request message decode failed"

        if protocal_id == ServerProtocol.IS_IOCOLLECT_VALID:
            res_msg = self.is_iocollect_valid(data_struct)
        elif protocal_id == ServerProtocol.GET_IO_DATA:
            res_msg = self.get_io_data(data_struct)
        elif protocal_id == ServerProtocol.GET_IODUMP_DATA:
            res_msg = self.get_iodump_data(data_struct)
        elif protocal_id == ServerProtocol.GET_DISK_DATA:
            res_msg = self.get_disk_data(data_struct)

        return res_msg

    def msg_head_process(self, msg_head):
        """message head process"""
        ctl_magic = msg_head[:CLT_MSG_MAGIC_LEN]
        if ctl_magic != CLT_MAGIC:
            logging.error("recv msg head magic invalid")
            return None

        protocol_str = msg_head[CLT_MSG_MAGIC_LEN:CLT_MSG_MAGIC_LEN+CLT_MSG_PRO_LEN]
        try:
            protocol_id = int(protocol_str)
        except ValueError:
            logging.error("recv msg protocol id is invalid")
            return None

        data_len_str = msg_head[CLT_MSG_MAGIC_LEN+CLT_MSG_PRO_LEN:CLT_MSG_HEAD_LEN]
        try:
            data_len = int(data_len_str)
        except ValueError:
            logging.error("recv msg data len is invalid %s", data_len_str)
            return None

        return [protocol_id, data_len]

    def server_recv(self, server_socket: socket.socket):
        """server receive"""
        try:
            client_socket, _ = server_socket.accept()
            logging.debug("server_fd listen ok")
        except socket.error:
            logging.error("server accept failed, %s", socket.error)
            return

        try:
            msg_head = client_socket.recv(CLT_MSG_HEAD_LEN)
            logging.debug("recv msg head: %s", msg_head.decode())
            head_info = self.msg_head_process(msg_head.decode())
        except (OSError, UnicodeError):
            client_socket.close()
            logging.error("server recv HEAD failed")
            return

        protocol_id = head_info[0]
        data_len = head_info[1]
        logging.debug("msg protocol id: %d, data length: %d", protocol_id, data_len)
        if protocol_id >= ServerProtocol.PRO_END:
            client_socket.close()
            logging.error("protocol id is invalid")
            return

        if data_len < 0:
            client_socket.close()
            logging.error("msg head parse failed")
            return

        try:
            msg_data = client_socket.recv(data_len)
            msg_data_decode = msg_data.decode()
            logging.debug("msg data %s", msg_data_decode)
        except (OSError, UnicodeError):
            client_socket.close()
            logging.error("server recv MSG failed")
            return

        res_data = self.msg_data_process(msg_data_decode, protocol_id)
        logging.debug("res data %s", res_data)

        # server send
        res_head = RES_MAGIC
        res_head += str(protocol_id).zfill(CLT_MSG_PRO_LEN)
        res_data_len = str(len(res_data)).zfill(CLT_MSG_LEN_LEN)
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

    def server_fd_create(self):
        """create server fd"""
        if not os.path.exists(SENTRY_RUN_DIR):
            logging.error("%s not exist, failed", SENTRY_RUN_DIR)
            return None

        try:
            server_fd = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server_fd.setblocking(False)
            if os.path.exists(COLLECT_SOCKET_PATH):
                os.remove(COLLECT_SOCKET_PATH)

            server_fd.bind(COLLECT_SOCKET_PATH)
            os.chmod(COLLECT_SOCKET_PATH, 0o600)
            server_fd.listen(CLT_LISTEN_QUEUE_LEN)
            logging.debug("%s bind and listen", COLLECT_SOCKET_PATH)
        except socket.error:
            logging.error("server fd create failed")
            server_fd = None
        return server_fd

    def server_loop(self):
        """main loop"""
        logging.info("collect listen thread start")
        server_fd = self.server_fd_create()
        if not server_fd:
            return

        epoll_fd = select.epoll()
        epoll_fd.register(server_fd.fileno(), select.EPOLLIN)

        logging.debug("start server_loop loop")
        while True:
            if self.stop_event.is_set():
                logging.debug("collect listen thread exit")
                server_fd = None
                return
            try:
                events_list = epoll_fd.poll(SERVER_EPOLL_TIMEOUT)
                for event_fd, _ in events_list:
                    if event_fd == server_fd.fileno():
                        self.server_recv(server_fd)
                    else:
                        continue
            except Exception:
                logging.error('collect listen exception : %s', traceback.format_exc())

    def stop_thread(self):
        self.stop_event.set() 
