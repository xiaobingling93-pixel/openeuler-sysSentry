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
import stat
import threading

from time import sleep
from .xalarm_api import alarm_bin2stu, alarm_stu2str
from .xalarm_transfer import (
    check_filter,
    transmit_alarm,
    wait_for_connection,
    cleanup_closed_connections,
    broadcast_sentry_down
)


ALARM_DIR = "/var/run/xalarm"
USER_RECV_SOCK = "/var/run/xalarm/alarm"
SOCK_FILE = "/var/run/xalarm/report"
ALARM_REPORT_LEN = 8216
ALARM_DIR_PERMISSION = 0o750
SOCKET_FILE_PERMISSON = 0o600
PERMISSION_MASK = 0o777
PERIOD_CHECK_TIME = 3
ALARM_LISTEN_QUEUE_LEN = 5
PERIOD_SCANN_TIME = 60
fd_to_socket_lock = threading.Lock()


def check_permission(path, permission):
    """check whether the permission of path is right
    """
    return (os.stat(path).st_mode & PERMISSION_MASK) == permission


def check_socket_file(path):
    if not os.path.exists(path):
        return False

    file_stat = os.stat(path)
    # path is not a socket file
    if not stat.S_ISSOCK(file_stat.st_mode):
        return False
    return True


def clear_sock_file(sock_file):
    """unlink unix socket if exist
    """
    if os.path.exists(sock_file):
        os.unlink(sock_file)


def clear_sock_conn(sock_fd, epoll_fd):
    if sock_fd is None:
        return
    if sock_fd.fileno() == -1:
        return
    if epoll_fd is not None:
        epoll_fd.unregister(sock_fd.fileno())
        epoll_fd.close()
    sock_fd.close()


def create_sock_conn(sock_file, sock_type):
    sock_fd, epoll_fd = (None, None)
    try:
        sock_fd = socket.socket(socket.AF_UNIX, sock_type)
        sock_fd.bind(sock_file)

        if sock_type == socket.SOCK_STREAM:
            sock_fd.listen(ALARM_LISTEN_QUEUE_LEN)
            sock_fd.setblocking(False)

        epoll_fd = select.epoll()
        epoll_fd.register(sock_fd.fileno(), select.EPOLLIN)
        os.chmod(sock_file, SOCKET_FILE_PERMISSON)
        logging.info("socket file %s has been created", sock_file)
        return sock_fd, epoll_fd
    except socket.error as e:
        logging.error("failed to bind %s socket, reason is %s", sock_file, str(e))
        clear_sock_conn(sock_fd, epoll_fd)

    return sock_fd, epoll_fd


def recover_sock_path_and_permission():
    # if directory not exists or permission denied, remake
    if not os.path.exists(ALARM_DIR):
        logging.info("xalarmd run dir not exists, create %s", ALARM_DIR)
        os.mkdir(ALARM_DIR)
    if not check_permission(ALARM_DIR, ALARM_DIR_PERMISSION):
        logging.info("xalarmd run dir %s permission set not properly, recover as default permission", ALARM_DIR)
        os.chmod(ALARM_DIR, ALARM_DIR_PERMISSION)
    if os.path.exists(SOCK_FILE) and not check_permission(SOCK_FILE, SOCKET_FILE_PERMISSON):
        logging.info("socket file %s permission %s set not properly, recover as default permission",
                    SOCK_FILE, oct(os.stat(SOCK_FILE).st_mode & PERMISSION_MASK))
        os.chmod(SOCK_FILE, SOCKET_FILE_PERMISSON)
    if os.path.exists(USER_RECV_SOCK) and not check_permission(USER_RECV_SOCK, SOCKET_FILE_PERMISSON):
        logging.info("socket file %s permission %s set not properly, recover as default permission",
                    USER_RECV_SOCK, oct(os.stat(USER_RECV_SOCK).st_mode & PERMISSION_MASK))
        os.chmod(USER_RECV_SOCK, SOCKET_FILE_PERMISSON)


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
            continue
        cleanup_closed_connections(alarm_sock, alarm_epoll, fd_to_socket, fd_to_socket_lock)


def monitor_sentry_service():
    """
    Monitor sysSentry service status via systemd D-Bus
    When sysSentry service becomes inactive or failed, broadcast alarm to all clients
    """
    global fd_to_socket
    global fd_to_socket_lock

    try:
        import dbus
        from gi.repository import GLib
        from dbus.mainloop.glib import DBusGMainLoop
    except ImportError as e:
        logging.error("Failed to import dbus or GLib: %s, systemd monitoring disabled", str(e))
        return

    try:
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
    except Exception as e:
        logging.error("Failed to monitor sysSentry service: %s", str(e))


def watch_socket_file_and_dir():
    global conn_thread
    global alarm_epoll
    global report_epoll
    global conn_thread_should_stop
    global report_sock
    global alarm_sock
    global fd_to_socket
    global fd_to_socket_lock
    while True:
        try:
            recover_sock_path_and_permission()
            if not check_socket_file(SOCK_FILE):
                logging.info("socket file %s not found or socket file been replaced, recovering ...", SOCK_FILE)
                clear_sock_conn(report_sock, report_epoll)
                clear_sock_file(SOCK_FILE)
                # if create socket socket, will retry to create because socket file was cleared in last step
                report_sock, report_epoll = create_sock_conn(SOCK_FILE, socket.SOCK_DGRAM)
            
            if not check_socket_file(USER_RECV_SOCK):
                logging.info("socket file %s not found or socket file been replaced, recovering ...", USER_RECV_SOCK)
                # set conn_thread_should_stop as True
                conn_thread_should_stop.set()
                # Ensure that conn_thread has been stopped before clean and release resources
                conn_thread.join()

                # Now only transmit_alarm will use this lock
                # Ensure fd_to_socket dict resource has been released
                with fd_to_socket_lock:
                    for stored_sock_fd, stored_sock in fd_to_socket.items():
                        if stored_sock is None:
                            continue
                        if alarm_sock is not None and (stored_sock.fileno() != alarm_sock.fileno()):
                            stored_sock.close()
                    clear_sock_conn(alarm_sock, alarm_epoll)
                    clear_sock_file(USER_RECV_SOCK)
                    
                    alarm_sock, alarm_epoll = create_sock_conn(USER_RECV_SOCK, socket.SOCK_STREAM)
                    fd_to_socket = {alarm_sock.fileno(): alarm_sock,}

                # set conn_thread_should_stop as False
                conn_thread_should_stop.clear()
                conn_thread = start_wait_for_conn_thread(
                    alarm_sock,
                    alarm_epoll,
                    fd_to_socket,
                    conn_thread_should_stop,
                    fd_to_socket_lock
                )
        except Exception as e:
            logging.error("Error watch socket file thread: %s", str(e))

        sleep(PERIOD_CHECK_TIME)


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

    clear_sock_file(SOCK_FILE)
    clear_sock_file(USER_RECV_SOCK)
    recover_sock_path_and_permission()
    global report_sock
    global alarm_sock
    global alarm_epoll
    global report_epoll
    global fd_to_socket
    global conn_thread_should_stop
    global conn_thread
    global fd_to_socket_lock
    report_sock, report_epoll = create_sock_conn(SOCK_FILE, socket.SOCK_DGRAM)
    alarm_sock, alarm_epoll = create_sock_conn(USER_RECV_SOCK, socket.SOCK_STREAM)
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

    watch_thread = threading.Thread(target=watch_socket_file_and_dir)
    watch_thread.daemon = True
    watch_thread.start()

    systemd_monitor_thread = threading.Thread(target=monitor_sentry_service)
    systemd_monitor_thread.daemon = True
    systemd_monitor_thread.start()

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
            
    conn_thread_should_stop.set()
    conn_thread.join()
    cleanup_thread.join()
    watch_thread.join()

    alarm_epoll.unregister(alarm_sock.fileno())
    alarm_epoll.close()
    alarm_sock.close()
    os.unlink(USER_RECV_SOCK)

    report_sock.close()




