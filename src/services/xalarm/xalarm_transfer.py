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
Description: xalarm transfer
Author:
Create: 2023-11-02
"""

import socket
import logging
import threading
import errno
from time import sleep

MIN_ID_NUMBER = 1001
MAX_ID_NUMBER = 1128
MAX_CONNECTION_NUM = 100 
TEST_CONNECT_BUFFER_SIZE = 32
MAX_RETRY_TIMES = 3


def check_filter(alarm_info, alarm_filter):
    """check id_mask for alarm messages forwarding
    """
    if not alarm_filter:
        return True
    if alarm_info.alarm_id < MIN_ID_NUMBER or alarm_info.alarm_id > MAX_ID_NUMBER:
        return False
    index = alarm_info.alarm_id - MIN_ID_NUMBER
    if not alarm_filter.id_mask[index]:
        return False
    return True


def cleanup_closed_connections(server_sock, epoll, fd_to_socket, fd_to_socket_lock):
    """
    clean invalid client socket connections saved in 'fd_to_socket'
    :param server_sock: server socket instance of alarm
    :param epoll: epoll instance, used to unregister invalid client connections
    :param fd_to_socket: dict instance, used to hold client connections and server connections
    """
    to_remove = []
    with fd_to_socket_lock:
        for fileno, connection in fd_to_socket.items():
            if connection is server_sock:
                continue
            try:
                # test whether connection still alive, use MSG_DONTWAIT to avoid blocking thread
                # use MSG_PEEK to avoid consuming buffer data
                data = connection.recv(TEST_CONNECT_BUFFER_SIZE, socket.MSG_DONTWAIT | socket.MSG_PEEK)
                if not data:
                    to_remove.append(fileno)
            except BlockingIOError:
                pass
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                to_remove.append(fileno)
        
        for fileno in to_remove:
            fd_to_socket[fileno].close()
            del fd_to_socket[fileno]
            logging.info(f"cleaned up connection {fileno} for client lost connection.")


def wait_for_connection(server_sock, epoll, fd_to_socket, conn_thread_should_stop, fd_to_socket_lock):
    """
    thread function for catch and save client connection
    :param server_sock: server socket instance of alarm
    :param epoll: epoll instance, used to unregister invalid client connections
    :param fd_to_socket: dict instance, used to hold client connections and server connections
    :param conn_thread_should_stop: bool instance
    """
    logging.info("wait for connection thread is running")
    while not conn_thread_should_stop.is_set():
        try:
            events = epoll.poll(1)

            for fileno, event in events:
                if fileno == server_sock.fileno():
                    connection, client_address = server_sock.accept()
                    # if reach max connection, cleanup closed connections
                    if len(fd_to_socket) - 1 >= MAX_CONNECTION_NUM:
                        cleanup_closed_connections(server_sock, epoll, fd_to_socket, fd_to_socket_lock)
                    # if connections still reach max num, close this connection automatically
                    if len(fd_to_socket) - 1 >= MAX_CONNECTION_NUM:
                        logging.info(f"connection reach max num of {MAX_CONNECTION_NUM}, closed current connection!")
                        connection.close()
                        continue
                    with fd_to_socket_lock:
                        fd_to_socket[connection.fileno()] = connection
                    logging.info("connection fd %d registered event.", connection.fileno())
        except socket.error as e: 
            logging.debug(f"socket error, reason is {e}")
        except (KeyError, OSError, ValueError) as e:
            logging.debug(f"wait for connection failed {e}")


def broadcast_sentry_down(server_socket, fd_to_socket, fd_to_socket_lock):
    """
    broadcast sysSentry down alarm to all clients
    :param server_socket: xalarmd service socket
    :param fd_to_socket: dict instance, used to hold client connections and server connections
    :param fd_to_socket_lock: lock instance for fd_to_socket
    """
    from .xalarm_api import Xalarm, alarm_stu2bin

    to_remove = []

    alarm_info = Xalarm(1128, 1, 1, 0, 0, "sysSentry service is down")
    bin_data = alarm_stu2bin(alarm_info)

    with fd_to_socket_lock:
        for fileno, connection in fd_to_socket.items():
            try:
                if connection is server_socket:
                    continue
                connection.sendall(bin_data)
                logging.info("Broadcast sysSentry down msg success, fd is %d", fileno)
            except (BrokenPipeError, ConnectionResetError):
                to_remove.append(fileno)
            except Exception as e:
                logging.info("Broadcast sysSentry down msg failed, fd is %d, reason is: %s",
                    fileno, str(e))

        for fileno in to_remove:
            fd_to_socket[fileno].close()
            del fd_to_socket[fileno]
            logging.info(f"cleaned up connection {fileno} for client lost connection.")


def transmit_alarm(server_sock, epoll, fd_to_socket, bin_data, alarm_str, fd_to_socket_lock):
    """
    this function is to broadcast alarm data to client, if fail to send data, remove connections held by fd_to_socket
    :param server_sock: server socket instance of alarm
    :param epoll: epoll instance, used to unregister invalid client connections
    :param fd_to_socket: dict instance, used to hold client connections and server connections
    :param bin_data: binary instance, alarm info data in C-style struct format defined in xalarm_api.py
    """
    to_remove = []
    to_retry = []

    with fd_to_socket_lock:
        for fileno, connection in fd_to_socket.items():
            if connection is not server_sock:
                try:
                    connection.sendall(bin_data)
                    logging.info("Broadcast msg success, fd is %d, alarm msg is %s",
                            fileno, alarm_str)
                except (BrokenPipeError, ConnectionResetError):
                    to_remove.append(fileno)
                except socket.error as e:
                    if e.errno == errno.EAGAIN:
                        to_retry.append(connection)
                    else:
                        logging.info("Sending msg failed, fd is %d, alarm msg is %s, reason is: %s",
                            fileno, alarm_str, str(e))
                except Exception as e:
                    logging.info("Sending msg failed, fd is %d, alarm msg is %s, reason is: %s",
                            fileno, alarm_str, str(e))
        
        for connection in to_retry:
            for i in range(MAX_RETRY_TIMES):
                try:
                    connection.sendall(bin_data)
                    break
                except Exception as e:
                    sleep(0.1)
                    logging.info("Sending msg failed for %d times, fd is %d, alarm msg is %s, reason is: %s",
                        i, connection.fileno(), alarm_str, str(e))

        for fileno in to_remove:
            fd_to_socket[fileno].close()
            del fd_to_socket[fileno]
            logging.info(f"cleaned up connection {fileno} for client lost connection.")


