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
Description: xalarm server
Author:
Create: 2023-11-02
"""

import socket
import os
import logging
import select
import threading
from time import sleep

import dbus
from gi.repository import GLib
from dbus.mainloop.glib import DBusGMainLoop

from .xalarm_api import alarm_bin2stu, alarm_stu2str
from .xalarm_transfer import (
    check_filter,
    transmit_alarm,
    wait_for_connection,
    cleanup_closed_connections,
    broadcast_sentry_down
)


ALARM_REPORT_LEN = 8216
PERIOD_CHECK_TIME = 3
ALARM_LISTEN_QUEUE_LEN = 5
PERIOD_SCANN_TIME = 1
fd_to_socket_lock = threading.Lock()


def get_systemd_sockets():
    """
    Get sockets from systemd socket activation
    Returns (alarm_sock, socket_epoll) and (report_sock, report_epoll)
    """
    try:
        listen_fds = int(os.environ.get('LISTEN_FDS', '0'))
        # we have at least 2 sockets
        if listen_fds < 2:
            logging.error("fd verify failed, systemd socket activation maybe not available or invalid")
            logging.error("Please ensure xalarmd.socket is enabled and started")
            logging.error("Run: systemctl enable xalarmd.socket && systemctl start xalarmd.socket")
            return None, None

        # File descriptors start from 3 (SD_LISTEN_FDS_START)
        # Need to verify socket types to ensure correct mapping
        # Expected: alarm socket (STREAM), report socket (DGRAM)
        systemd_alarm_sock = None
        systemd_report_sock = None

        # Check all passed file descriptors
        for fd_offset in range(listen_fds):
            fd = 3 + fd_offset
            try:
                # Get socket type to determine which socket this is
                # Use numeric constants for better compatibility, SOL_SOCKET = 1, SO_TYPE = 3
                test_sock = socket.fromfd(fd, socket.AF_UNIX, socket.SOCK_STREAM)
                sock_type_val = test_sock.getsockopt(1, 3)
                test_sock.close()

                if sock_type_val == socket.SOCK_STREAM:
                    # STREAM socket -> alarm socket
                    if systemd_alarm_sock is not None:
                        logging.error("Multiple STREAM sockets found, expected only one")
                        return None, None
                    systemd_alarm_sock = socket.fromfd(fd, socket.AF_UNIX, socket.SOCK_STREAM)
                    logging.info("Found STREAM socket at FD %d (alarm socket)", fd)
                elif sock_type_val == socket.SOCK_DGRAM:
                    # DGRAM socket -> report socket
                    if systemd_report_sock is not None:
                        logging.error("Multiple DGRAM sockets found, expected only one")
                        return None, None
                    systemd_report_sock = socket.fromfd(fd, socket.AF_UNIX, socket.SOCK_DGRAM)
                    logging.info("Found DGRAM socket at FD %d (report socket)", fd)
                else:
                    logging.error("Unknown socket type %d at FD %d", sock_type_val, fd)
                    return None, None
            except Exception as e:
                logging.error("Failed to check socket type at FD %d: %s", fd, str(e))
                return None, None

        # Verify we found both required sockets
        if systemd_alarm_sock is None:
            logging.error("STREAM socket (alarm) not found")
            return None, None
        if systemd_report_sock is None:
            logging.error("DGRAM socket (report) not found")
            return None, None

        # Create epoll for alarm socket
        systemd_alarm_epoll = select.epoll()
        systemd_alarm_epoll.register(systemd_alarm_sock.fileno(), select.EPOLLIN)

        # Create epoll for report socket
        systemd_report_epoll = select.epoll()
        systemd_report_epoll.register(systemd_report_sock.fileno(), select.EPOLLIN)

        logging.info("Successfully obtained sockets from systemd socket activation")
        logging.info("Alarm socket (STREAM): FD %d, Report socket (DGRAM): FD %d",
                     systemd_alarm_sock.fileno(), systemd_report_sock.fileno())
        return (systemd_alarm_sock, systemd_alarm_epoll), (systemd_report_sock, systemd_report_epoll)

    except Exception as e:
        logging.error("Failed to get systemd sockets: %s", str(e))
        logging.error("Please ensure xalarmd.socket is enabled and started")
        logging.error("Run: systemctl enable xalarmd.socket && systemctl start xalarmd.socket")
        return None, None


def period_task_to_cleanup_connections():
    global alarm_sock
    global alarm_epoll
    global fd_to_socket
    global conn_thread_should_stop
    global fd_to_socket_lock
    logging.info("cleanup thread is running")

    while True:
        sleep(PERIOD_SCANN_TIME)
        # if conn thread stopped, cleanup thread should not cleanup anymore
        if conn_thread_should_stop.is_set():
            break
        cleanup_closed_connections(alarm_sock, alarm_epoll, fd_to_socket, fd_to_socket_lock)


def monitor_sentry_service():
    """
    Monitor sysSentry service status via systemd D-Bus
    When sysSentry service becomes inactive or failed, broadcast alarm to all clients
    """
    global fd_to_socket
    global fd_to_socket_lock

    DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    systemd = bus.get_object('org.freedesktop.systemd1',
                            '/org/freedesktop/systemd1/unit/sysSentry_2eservice')

    def on_properties_changed(interface, changed, invalidated):
        if 'ActiveState' in changed:
            state = changed['ActiveState']
            logging.info("sysSentry service state changed to: %s", state)
            if state in ['inactive', 'failed']:
                logging.warning("sysSentry service is down, broadcasting alarm to all clients")
                broadcast_sentry_down(alarm_sock, fd_to_socket, fd_to_socket_lock)

    systemd.connect_to_signal(dbus_interface='org.freedesktop.DBus.Properties',
                              signal_name='PropertiesChanged',
                              handler_function=on_properties_changed)

    logging.info("sysSentry service monitoring started")
    loop = GLib.MainLoop()
    loop.run()


def start_wait_for_conn_thread(alarm_sock_, alarm_epoll_,
        fd_to_socket_, conn_thread_should_stop_, fd_to_socket_lock_):
    conn_thread = threading.Thread(
        target=wait_for_connection,
        args=(
            alarm_sock_,
            alarm_epoll_,
            fd_to_socket_,
            conn_thread_should_stop_,
            fd_to_socket_lock_)
        )
    conn_thread.daemon = True
    conn_thread.start()
    return conn_thread


def server_loop(alarm_config):
    """alarm daemon process loop
    """
    logging.info("server loop waiting for messages")

    # Get sockets from systemd socket activation
    systemd_sockets = get_systemd_sockets()
    if systemd_sockets[0] is None:
        logging.error("Failed to get systemd sockets, exiting")
        return

    global report_sock
    global alarm_sock
    global alarm_epoll
    global report_epoll
    global fd_to_socket
    global conn_thread_should_stop
    global conn_thread
    global fd_to_socket_lock

    (alarm_sock, alarm_epoll), (report_sock, report_epoll) = systemd_sockets
    fd_to_socket = {alarm_sock.fileno(): alarm_sock,}

    conn_thread_should_stop = threading.Event()
    conn_thread = start_wait_for_conn_thread(
        alarm_sock,
        alarm_epoll,
        fd_to_socket,
        conn_thread_should_stop,
        fd_to_socket_lock
    )

    cleanup_thread = threading.Thread(target=period_task_to_cleanup_connections)
    cleanup_thread.daemon = True
    cleanup_thread.start()

    systemd_monitor_thread = threading.Thread(target=monitor_sentry_service)
    systemd_monitor_thread.daemon = True
    systemd_monitor_thread.start()

    try:
        while True:
            try:
                # set timeout as 1 seconds to avoid main process blocked by recvfrom
                # which will cause socket cannot be rebuild
                events = report_epoll.poll(1.0)
                data = None
                for fileno, event in events:
                    if fileno == report_sock.fileno():
                        data, _ = report_sock.recvfrom(ALARM_REPORT_LEN)

                if not data:
                    continue
                if len(data) != ALARM_REPORT_LEN:
                    logging.debug("server receive report msg length wrong %d",
                                    len(data))
                    continue
                alarm_info = alarm_bin2stu(data)
                alarm_str = alarm_stu2str(alarm_info)
                logging.info("server recieve report msg, %s", alarm_str)
                if not check_filter(alarm_info, alarm_config):
                    continue
                transmit_alarm(
                    alarm_sock,
                    alarm_epoll,
                    fd_to_socket,
                    data,
                    alarm_str,
                    fd_to_socket_lock
                )
            except Exception as e:
                logging.error(f"Error server:{e}")
    finally:
        conn_thread_should_stop.set()
        conn_thread.join()
        cleanup_thread.join()
        systemd_monitor_thread.join()

        alarm_epoll.unregister(alarm_sock.fileno())
        alarm_epoll.close()
        alarm_sock.close()

        report_epoll.close()
        report_sock.close()




