import os
import sys
import socket
import threading
import time
import inspect
from struct import error as StructParseError

from xalarm.xalarm_api import Xalarm, alarm_bin2stu


ALARM_REPORT_LEN = 8216
MAX_NUM_OF_ALARM_ID=128
MIN_ALARM_ID = 1001
MAX_ALARM_ID = (MIN_ALARM_ID + MAX_NUM_OF_ALARM_ID - 1)
DIR_XALARM = "/var/run/xalarm"
PATH_REG_ALARM = "/var/run/xalarm/alarm"
PATH_REPORT_ALARM = "/var/run/xalarm/report"
ALARM_DIR_PERMISSION = 0o0750
ALARM_REG_SOCK_PERMISSION = 0o0700
ALARM_SOCKET_PERMISSION = 0o0700
TIME_UNIT_MILLISECONDS = 1000
ALARM_REGISTER_INFO = None


class AlarmRegister:
    def __init__(self, id_filter: list, callback: callable):
        self.id_filter = id_filter
        self.callback = callback
        self.socket = self.create_unix_socket()
        self.is_registered = True
        self.thread = threading.Thread(target=self.alarm_recv)
        self.thread_should_stop = False

    def check_params(self) -> bool:
        if (len(self.id_filter) != MAX_NUM_OF_ALARM_ID):
            sys.stderr.write("check_params: invalid param id_filter\n")
            return False
        
        sig = inspect.signature(self.callback)
        if len(sig.parameters) != 1:
            sys.stderr.write("check_params: invalid param callback\n")
            return False
        
        if self.socket is None:
            sys.stderr.write("check_params: socket create failed\n")
            return False
        return True
    
    def set_id_filter(self, id_filter: list) -> bool:
        if (len(id_filter) > MAX_NUM_OF_ALARM_ID):
            sys.stderr.write("set_id_filter: invalid param id_filter\n")
            return False
        self.id_filter = id_filter

    def id_is_registered(self, alarm_id) -> bool:
        if alarm_id < MIN_ALARM_ID or alarm_id > MAX_ALARM_ID:
            return False
        return self.id_filter[alarm_id - MIN_ALARM_ID]
    
    def put_alarm_info(self, alarm_info: Xalarm) -> None:
        if not self.callback or not alarm_info:
            return
        if not self.id_is_registered(alarm_info.alarm_id):
            return
        self.callback(alarm_info)

    def create_unix_socket(self) -> socket.socket:
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.setblocking(False)

            if not os.access(DIR_XALARM, os.F_OK):
                os.makedirs(DIR_XALARM)
                os.chmod(DIR_XALARM, ALARM_DIR_PERMISSION)

            sock.connect(PATH_REG_ALARM)
            return sock
        except (IOError, OSError, FileNotFoundError) as e:
            sock.close()
            sys.stderr.write(f"create_unix_socket: create socket error:{e}\n")
            return None
    
    def alarm_recv(self):
        while not self.thread_should_stop:
            try:
                data = self.socket.recv(ALARM_REPORT_LEN)
                if not data:
                    sys.stderr.write("connection closed by xalarmd, maybe connections reach max num or service stopped.\n")
                    self.thread_should_stop = True
                    break
                if len(data) != ALARM_REPORT_LEN:
                    sys.stderr.write(f"server receive report msg length wrong {len(data)}\n")
                    continue

                alarm_info = alarm_bin2stu(data)
                self.put_alarm_info(alarm_info)
            except (BlockingIOError) as e:
                time.sleep(0.1)
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                sys.stderr.write("Connection closed by the server.\n")
                self.thread_should_stop = True
            except (ValueError, StructParseError, InterruptedError) as e:
                sys.stderr.write(f"{e}\n")
            except Exception as e:
                sys.stderr.write(f"{e}\n")
                self.thread_should_stop = True

    def start_thread(self) -> None:
        self.thread.daemon = True
        self.thread.start()
    
    def stop_thread(self) -> None:
        self.thread_should_stop = True
        self.thread.join()


def xalarm_register(callback: callable, id_filter: list) -> int:
    global ALARM_REGISTER_INFO

    if ALARM_REGISTER_INFO is not None:
        sys.stderr.write("xalarm_register: alarm has registered\n")
        return -1

    ALARM_REGISTER_INFO = AlarmRegister(id_filter, callback)
    if not ALARM_REGISTER_INFO.check_params():
        return -1

    ALARM_REGISTER_INFO.start_thread()

    return 0


def xalarm_unregister(clientId: int) -> None:
    global ALARM_REGISTER_INFO
    if clientId < 0:
        sys.stderr.write("xalarm_unregister: invalid client\n")
        return
    
    if ALARM_REGISTER_INFO is None:
        sys.stderr.write("xalarm_unregister: alarm has not registered\n")
        return
    
    ALARM_REGISTER_INFO.stop_thread()
    ALARM_REGISTER_INFO = None


def xalarm_upgrade(clientId: int, id_filter: list) -> bool:
    global ALARM_REGISTER_INFO
    if clientId < 0:
        sys.stderr.write("xalarm_upgrade: invalid client\n")
        return False
    if ALARM_REGISTER_INFO is None:
        sys.stderr.write("xalarm_upgrade: alarm has not registered\n")
        return False
    if ALARM_REGISTER_INFO.thread_should_stop:
        sys.stderr.write("xalarm_upgrade: upgrade failed, alarm thread has stopped\n")
        return False
    ALARM_REGISTER_INFO.id_filter = id_filter
    return True


def xalarm_getid(alarm_info: Xalarm) -> int:
    if not alarm_info:
        return 0
    return alarm_info.alarm_id


def xalarm_getlevel(alarm_info: Xalarm) -> int:
    if not alarm_info:
        return 0
    return alarm_info.alarm_level


def xalarm_gettype(alarm_info: Xalarm) -> int:
    if not alarm_info:
        return 0
    return alarm_info.alarm_type


def xalarm_gettime(alarm_info: Xalarm) -> int:
    if not alarm_info:
        return 0
    return alarm_info.timetamp.tv_sec * TIME_UNIT_MILLISECONDS + alarm_info.timetamp.tv_usec / TIME_UNIT_MILLISECONDS

def xalarm_getdesc(alarm_info: Xalarm) -> str:
    if not alarm_info:
        return None
    try:
        desc_str = alarm_info.msg1.rstrip(b'\x00').decode('utf-8')
    except UnicodeError:
        desc_str = None
    return desc_str

