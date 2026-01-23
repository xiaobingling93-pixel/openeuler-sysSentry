import logging
import socket
from enum import Enum

from .utils import execute_command

HEX_CHAR_LEN = 2
SOCKET_RECEIVE_LEN = 128
BMC_DATA_HEAD = "REP"
BMC_REPORT_TYPE_BIT = 0
HBMC_REPAIR_TYPE_BIT = 1
HBMC_REPAIR_RESULT_BIT = 2
HBMC_ISOLATION_TYPE_BIT = 3
HBMC_SEND_HEAD_LEN = 4 # "ipmtool", "raw", "0x30", "0x92"
HBMC_SEND_ROW_BIT = 26 + HBMC_SEND_HEAD_LEN
HBMC_SEND_COL_BIT = 30 + HBMC_SEND_HEAD_LEN
HBMC_REPAIR_TYPE_OFFSET = 7

HBMC_SEND_SUCCESS_CODE = "db 07 00"


class ReportType(Enum):
    HBMC_REPAIR_BMC = 0x00


class HBMCRepairType(Enum):
    CE_ACLS = 7
    PS_UCE_ACLS = 8
    CE_SPPR = 9
    PS_UCE_SPPR = 10


class HBMCRepairResultType(Enum):
    ISOLATE_FAILED_OVER_THRESHOLD = 0b10000001
    ISOLATE_FAILED_OTHER_REASON   = 0b10000010
    REPAIR_FAILED_NO_RESOURCE     = 0b10010100
    REPAIR_FAILED_INVALID_PARAM   = 0b10011000
    REPAIR_FAILED_OTHER_REASON	  = 0b10011100
    ONLINE_PAGE_FAILED            = 0b10100000
    ISOLATE_REPAIR_ONLINE_SUCCESS = 0b00000000


class HBMCIsolationType(Enum):
    ROW_FAULT = 1
    SINGLE_ADDR_FAULT = 6


def find_value_is_in_enum(value: int, enum: Enum):
    for item in enum:
        if value == item.value:
            return True
    return False


def convert_hex_char_to_int(data, bit):
    if len(data) < (bit+1)*HEX_CHAR_LEN:
        logging.error(f"Data {data} len is too short, current convert bit is {bit}")
    char = data[bit*HEX_CHAR_LEN:(bit+1)*HEX_CHAR_LEN]
    try:
        value = int(char, 16)
    except ValueError:
        logging.error(f"Cannot convert char [{char}] to int")
        raise ValueError
    return value


def reverse_byte(data):
    return data[3], data[2], data[1], data[0]


def parse_hbmc_report(data: str):
    logging.debug(f"bmc receive raw data is {data}")
    repair_type = convert_hex_char_to_int(data, HBMC_REPAIR_TYPE_BIT)
    repair_type += HBMC_REPAIR_TYPE_OFFSET
    if not find_value_is_in_enum(repair_type, HBMCRepairType):
        logging.warning(f"HBMC msg repair type ({repair_type}) is unknown")
        raise ValueError

    repair_result = convert_hex_char_to_int(data, HBMC_REPAIR_RESULT_BIT)
    if not find_value_is_in_enum(repair_result, HBMCRepairResultType):
        logging.warning(f"HBMC msg repair result ({repair_result}) is unknown")
        raise ValueError

    isolation_type = convert_hex_char_to_int(data, HBMC_ISOLATION_TYPE_BIT)
    if not find_value_is_in_enum(isolation_type, HBMCIsolationType):
        logging.warning(f"HBMC msg isolation type ({isolation_type}) is unknown")
        raise ValueError

    cmd_list = [
        "ipmitool",
        "raw",
        "0x30", # Netfn
        "0x92", # cmd
        "0xdb",
        "0x07",
        "0x00",
        "0x65", # sub command
        "0x01", # SystemId
        "0x00", # LocalSystemId
        "{:#04X}".format(repair_type),
        "{:#04X}".format(repair_result),
        "{:#04X}".format(isolation_type),
    ]
    # send the remain data directly
    data = data[(HBMC_ISOLATION_TYPE_BIT + 1) * HEX_CHAR_LEN:]
    other_info_str = []
    for i in range(len(data) // 2):
        other_info_str.append("{:#04X}".format(convert_hex_char_to_int(data, i)))
    cmd_list.extend(other_info_str)

    cmd_list[HBMC_SEND_ROW_BIT:HBMC_SEND_ROW_BIT + 4] = reverse_byte(cmd_list[HBMC_SEND_ROW_BIT:HBMC_SEND_ROW_BIT + 4])
    cmd_list[HBMC_SEND_COL_BIT:HBMC_SEND_COL_BIT + 4] = reverse_byte(cmd_list[HBMC_SEND_COL_BIT:HBMC_SEND_COL_BIT + 4])

    logging.info(f"Send bmc alarm command is {cmd_list}")

    ret = execute_command(cmd_list)
    if HBMC_SEND_SUCCESS_CODE not in ret:
        logging.warning(f"Send bmc alarm failed, error code is {ret}")
        raise ValueError
    logging.debug("Send bmc alarm success")


PARSE_REPORT_MSG_FUNC_DICT = {
    ReportType.HBMC_REPAIR_BMC.value: parse_hbmc_report,
}


def bmc_recv(server_socket: socket.socket):
    logging.debug("Get hbm socket connection request")
    try:
        client_socket, _ = server_socket.accept()
        logging.debug("cpu alarm fd listen ok")

        data = client_socket.recv(SOCKET_RECEIVE_LEN)
        data = data.decode()

        data_head = data[0:len(BMC_DATA_HEAD)]
        if data_head != BMC_DATA_HEAD:
            logging.warning(f"The head of the msg is incorrect, head is {data_head}")
            raise ValueError

        # remove the data head
        data = data[len(BMC_DATA_HEAD):]
        logging.info(f"Remove head data is {data}")

        report_type = convert_hex_char_to_int(data, BMC_REPORT_TYPE_BIT)
        if report_type not in PARSE_REPORT_MSG_FUNC_DICT.keys():
            logging.warning(f"The type of the msg ({report_type}) is unknown")
            raise ValueError

        PARSE_REPORT_MSG_FUNC_DICT[report_type](data)

    except socket.error:
        logging.error("socket error")
        return
    except (ValueError, OSError, TypeError, IndexError, NotImplementedError):
        logging.error("server recv bmc msg failed!")
        client_socket.close()
        return
