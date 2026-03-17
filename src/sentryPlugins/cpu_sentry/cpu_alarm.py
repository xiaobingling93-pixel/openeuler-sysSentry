import re
import math
import logging
import socket
from enum import Enum

from syssentry.utils import execute_command, MAX_MSG_LEN

MAX_CORE_ID = 1024
MAX_SOCKET_ID = 255
CPU_ALARM_PARAM_LEN = 4
DEFAULT_CORE_ID_ARRAY_CAPACITY = 32
BIT_8 = 8
BIN_PREFIX_LEN = 2
BINARY = 2
MIN_DATA_LEN = 0
MAX_DATA_LEN = 999

PARAM_REP_LEN = 3
PARAM_TYPE_LEN = 1
PARAM_MODULE_LEN = 1
PARAM_TRANS_TO_LEN = 2
PARAM_DATA_LEN = 3


class Type(Enum):
    CE = 0x00
    UCE = 0x01


class Module(Enum):
    CPU = 0x00


class TransTo(Enum):
    BMC = 0x01


class EventType(Enum):
    ASSERTION = 0x00
    DEASSERTION = 0x01


def is_valid_enum_value(enum_type, value):
    for enum in enum_type:
        if enum.value == value:
            return True
    return False


def check_input_param(cpu_alarm_info):
    command, event_type, socket_id, core_id = cpu_alarm_info
    if not is_valid_enum_value(EventType, event_type):
        raise ValueError("invalid param `event_type`")
    if not (0 <= socket_id <= MAX_SOCKET_ID):
        raise ValueError("invalid param `socket_id`")
    if not (0 <= core_id <= MAX_CORE_ID):
        raise ValueError("invalid param `core_id`")


def parser_cpu_alarm_info(req_data):
    if not req_data:
        raise ValueError("recv empty data")

    cpu_alarm_info = list(map(int, req_data.split()))

    if len(cpu_alarm_info) != CPU_ALARM_PARAM_LEN:
        logging.debug(
            "expected {} params in fixed params, got {}".format(
                CPU_ALARM_PARAM_LEN, len(cpu_alarm_info)
            )
        )
        raise ValueError

    check_input_param(cpu_alarm_info)

    return cpu_alarm_info


def get_cpu_num():
    cmd_list = ["/usr/bin/lscpu"]
    ret = execute_command(cmd_list)
    if not ret:
        return -1
    matches = list(re.finditer(r"^\s*(CPU|CPU\(s\)):\s*\d+$", ret, re.MULTILINE))
    if not matches:
        logging.error("No CPU information found in lscpu output")
        return -1
    cpu_num_str = matches[0].group(0).split()[-1]
    try:
        return int(cpu_num_str)
    except ValueError:
        logging.error("Failed to parse CPU number: %s", cpu_num_str)
        return -1


def get_cpu_interval():
    cmd_list = ["/usr/sbin/dmidecode", "-t", "processor"]
    ret = execute_command(cmd_list)
    if not ret:
        logging.error("dmidecode cmd failed")
        return [], -1

    core_count_pattern = r"Core Count:\s*\d+"
    matches_core_count = [
        item.group(0) for item in re.finditer(core_count_pattern, ret)
    ]

    thread_count_pattern = r"Thread Count:\s*\d+"
    matches_thread_count = [
        item.group(0) for item in re.finditer(thread_count_pattern, ret)
    ]

    if len(matches_core_count) != len(matches_thread_count):
        logging.error("mismatched core count nums with thread count nums")
        raise ValueError("Unexpected core count nums with thread count nums")

    group_num = 0
    for core_count_str, thread_count_str in zip(
        matches_core_count, matches_thread_count
    ):
        core_count = int(core_count_str.split()[-1])
        thread_count = int(thread_count_str.split()[-1])
        if core_count == 0 or thread_count < core_count:
            logging.error("thread count is less than core count or core count is 0")
            raise ValueError("Unexpected value of thread count and core count")
        group_num += thread_count // core_count

    cpu_num = get_cpu_num()
    if (cpu_num < 0):
        logging.error("invalid cpu num")
        return [], -1

    core_siblings_list = []
    if group_num == 0:
        logging.error("unexpected value of group num with `0`")
        raise ValueError("Unexpected value of group num")
    cpu_num_per_group = cpu_num // group_num

    if cpu_num_per_group <= 0:
        logging.error("got invalid cpu num per group")
        raise ValueError("Unexpected value of cpu num per group")

    for i in range(0, cpu_num, cpu_num_per_group):
        core_siblings_list.append((i, i + cpu_num_per_group - 1))
    return core_siblings_list, cpu_num_per_group


def get_core_id(core_id_logical, core_siblings_list):
    for tup in core_siblings_list:
        begin, end = tup
        if begin <= core_id_logical <= end:
            return core_id_logical - begin
    return -1


def upload_bmc(_type, module, command, event_type, socket_id, core_id_logical):
    try:
        if _type != Type.UCE.value:
            logging.error("invalid param `type` for upload bmc")
            return
        if module != Module.CPU.value:
            logging.error("invalid param `module` for upload bmc")
            return

        core_siblings_list, cpu_num_per_group = get_cpu_interval()
        if (len(core_siblings_list) == 0):
            logging.error("get empty cpu list")
            return

        core_id = get_core_id(core_id_logical, core_siblings_list)
        if core_id < 0:
            logging.error("cannot map `logical_core_id` to `core_siblings`")
            return

        core_id_array_capacity = DEFAULT_CORE_ID_ARRAY_CAPACITY
        if cpu_num_per_group > DEFAULT_CORE_ID_ARRAY_CAPACITY:
            core_id_array_capacity = math.ceil(cpu_num_per_group / 8) * 8

        core_id_bin_str = bin(1 << core_id)[BIN_PREFIX_LEN:].zfill(
            core_id_array_capacity
        )
        core_id_array = []

        for i in range(0, core_id_array_capacity, BIT_8):
            core_id_array.append(int(core_id_bin_str[i : i + BIT_8], BINARY))

        core_id_array.reverse()
        core_id_cmd = ["{:#04X}".format(_id) for _id in core_id_array]

        cmd_list = [
            "/usr/bin/ipmitool",
            "raw",
            "0x30",
            "0x92",
            "0xdb",
            "0x07",
            "0x00",
            "0x05",
            "0x01",
            "{:#04X}".format(event_type),
            "0x0f",
            "{:#04X}".format(socket_id),
        ]
        cmd_list.extend(core_id_cmd)
        execute_command(cmd_list)
    except (ValueError, TypeError):
        logging.error("failed to resolve bmc params")


def check_fixed_param(data, expect):
    if not data:
        raise ValueError("recv empty param")
    data = data.decode()
    if isinstance(expect, tuple):
        if not expect[0] <= int(data) <= expect[1]:
            raise ValueError("expected number range param is not in specified range")
        return int(data)
    elif type(expect) == type(Enum):
        if not is_valid_enum_value(expect, int(data)):
            raise ValueError("expected enum value param is not valid")
        return int(data)
    elif isinstance(expect, int):
        if int(data) != expect:
            raise ValueError("expected number param is not valid")
        return int(data)
    elif isinstance(expect, str):
        if data != expect:
            raise ValueError("expected str param is not valid")
        return data
    raise NotImplementedError("unexpected param type")


def cpu_alarm_recv(server_socket: socket.socket):
    try:
        client_socket, _ = server_socket.accept()
        logging.debug("cpu alarm fd listen ok")

        data = client_socket.recv(PARAM_REP_LEN)
        check_fixed_param(data, "REP")

        data = client_socket.recv(PARAM_TYPE_LEN)
        _type = check_fixed_param(data, Type)

        data = client_socket.recv(PARAM_MODULE_LEN)
        module = check_fixed_param(data, Module)

        data = client_socket.recv(PARAM_TRANS_TO_LEN)
        trans_to = check_fixed_param(data, TransTo)

        data = client_socket.recv(PARAM_DATA_LEN)
        data_len = check_fixed_param(data, (MIN_DATA_LEN, MAX_DATA_LEN))

        if data_len < 0 or data_len > MAX_MSG_LEN:
            client_socket.close()
            logging.error("socket recv data is illegal:%d", data_len)
            return
        data = client_socket.recv(data_len)

        command, event_type, socket_id, core_id = parser_cpu_alarm_info(data)
    except socket.error:
        logging.error("socket error")
        return
    except (ValueError, OSError, UnicodeError, TypeError, NotImplementedError):
        logging.error("server recv cpu alarm msg failed!")
        client_socket.close()
        return

    upload_bmc(_type, module, command, event_type, socket_id, core_id)


