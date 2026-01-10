import os
import time
import socket
import logging
from struct import error as StructParseError

from xalarm.xalarm_api import alarm_stu2bin, Xalarm

MAX_NUM_OF_ALARM_ID = 128
MIN_ALARM_ID = 1001
MAX_ALARM_ID = (MIN_ALARM_ID + MAX_NUM_OF_ALARM_ID - 1)

MINOR_ALM = 1
MAJOR_ALM = 2
CRITICAL_ALM = 3

ALARM_TYPE_OCCUR = 1
ALARM_TYPE_RECOVER = 2

MAX_PUC_PARAS_LEN = 8192

DIR_XALARM = "/var/run/xalarm"
PATH_REPORT_ALARM = "/var/run/xalarm/report"


def check_params(alarm_id, alarm_level, alarm_type, puc_paras) -> bool:
    if not os.path.exists(DIR_XALARM):
        logging.error(f"check_params: {DIR_XALARM} not exist, failed")
        return False
    
    if not os.path.exists(PATH_REPORT_ALARM):
        logging.error(f"check_params: {PATH_REPORT_ALARM} not exist, failed")
        return False

    if (alarm_id < MIN_ALARM_ID or alarm_id > MAX_ALARM_ID or
        alarm_level < MINOR_ALM or alarm_level > CRITICAL_ALM or
        alarm_type < ALARM_TYPE_OCCUR or alarm_type > ALARM_TYPE_RECOVER):
        logging.error("check_params: alarm info invalid")
        return False
    
    if len(puc_paras) >= MAX_PUC_PARAS_LEN:
        logging.error(f"check_params: alarm msg should be less than {MAX_PUC_PARAS_LEN}")
        return False

    return True

def xalarm_report(alarm_id, alarm_level, alarm_type, puc_paras) -> bool:
    if not check_params(alarm_id, alarm_level, alarm_type, puc_paras):
        return False

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)

        current_time = time.time()
        current_time_seconds = int(current_time)
        current_microseconds = int((current_time - current_time_seconds) * 1_000_000)
        alarm_info = Xalarm(alarm_id, alarm_type, alarm_level,
                        current_time_seconds, current_microseconds, puc_paras)

        sock.sendto(alarm_stu2bin(alarm_info), PATH_REPORT_ALARM)
    except (FileNotFoundError, StructParseError, socket.error, OSError, UnicodeError) as e:
        logging.error(f"error occurs when sending msg.")
        return False
    finally:
        sock.close()
    
    return True


