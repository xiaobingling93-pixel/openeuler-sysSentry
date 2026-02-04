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
collect plugin
"""
import json
import socket
import logging
import re
import os

from syssentry.utils import MAX_MSG_LEN

COLLECT_SOCKET_PATH = "/var/run/sysSentry/collector.sock"

# data length param
CLT_MSG_HEAD_LEN = 9    #3+2+4
CLT_MSG_PRO_LEN = 2
CLT_MSG_MAGIC_LEN = 3
CLT_MSG_LEN_LEN = 4

CLT_MAGIC = "CLT"
RES_MAGIC = "RES"

# disk limit
LIMIT_DISK_CHAR_LEN = 32
LIMIT_DISK_LIST_LEN = 10

# stage limit
LIMIT_STAGE_CHAR_LEN = 20
LIMIT_STAGE_LIST_LEN = 15

#iotype limit
LIMIT_IOTYPE_CHAR_LEN = 7
LIMIT_IOTYPE_LIST_LEN = 4

#period limit
LIMIT_PERIOD_MIN_LEN = 1
LIMIT_PERIOD_MAX_LEN = 300

# max_save
LIMIT_MAX_SAVE_LEN = 300

# interface protocol
class ClientProtocol():
    IS_IOCOLLECT_VALID = 0
    GET_IO_DATA = 1
    GET_IODUMP_DATA = 2
    GET_DISK_DATA = 3
    PRO_END = 4

class ResultMessage():
    RESULT_SUCCEED = 0
    RESULT_UNKNOWN = 1 # unknown error
    RESULT_NOT_PARAM = 2 # the parameter does not exist or the type does not match.
    RESULT_INVALID_LENGTH = 3 # invalid parameter length.
    RESULT_EXCEED_LIMIT = 4 # the parameter length exceeds the limit.
    RESULT_PARSE_FAILED = 5 # parse failed
    RESULT_INVALID_CHAR = 6 # invalid char
    RESULT_DISK_NOEXIST = 7 # disk is not exist
    RESULT_DISK_TYPE_MISMATCH= 8 # disk type mismatch

Result_Messages = {
    ResultMessage.RESULT_SUCCEED: "Succeed",
    ResultMessage.RESULT_UNKNOWN: "Unknown error",
    ResultMessage.RESULT_NOT_PARAM: "The parameter does not exist or the type does not match",
    ResultMessage.RESULT_INVALID_LENGTH: "Invalid parameter length",
    ResultMessage.RESULT_EXCEED_LIMIT: "The parameter length exceeds the limit",
    ResultMessage.RESULT_PARSE_FAILED: "Parse failed",
    ResultMessage.RESULT_INVALID_CHAR: "Invalid char",
    ResultMessage.RESULT_DISK_NOEXIST: "Disk is not exist",
    ResultMessage.RESULT_DISK_TYPE_MISMATCH: "Disk type mismatch"
}

class DiskType():
    TYPE_NVME_SSD = 0
    TYPE_SATA_SSD = 1
    TYPE_SATA_HDD = 2

Disk_Type = {
    DiskType.TYPE_NVME_SSD: "nvme_ssd",
    DiskType.TYPE_SATA_SSD: "sata_ssd",
    DiskType.TYPE_SATA_HDD: "sata_hdd"
}

def client_send_and_recv(request_data, data_str_len, protocol):
    """client socket send and recv message"""
    try:
        client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    except socket.error:
        logging.debug("collect_plugin: client create socket error")
        return None

    try:
        client_socket.connect(COLLECT_SOCKET_PATH)
    except OSError:
        client_socket.close()
        logging.debug("collect_plugin: client connect error")
        return None

    req_data_len = len(request_data)
    request_msg = CLT_MAGIC + str(protocol).zfill(CLT_MSG_PRO_LEN) + str(req_data_len).zfill(CLT_MSG_LEN_LEN) + request_data

    try:
        client_socket.send(request_msg.encode())
        res_data = client_socket.recv(len(RES_MAGIC) + CLT_MSG_PRO_LEN + data_str_len)
        res_data = res_data.decode()
    except (OSError, UnicodeError):
        client_socket.close()
        logging.debug("collect_plugin: client communicate error")
        return None

    res_magic = res_data[:CLT_MSG_MAGIC_LEN]
    if res_magic != "RES":
        client_socket.close()
        logging.debug("res msg format error")
        return None

    protocol_str = res_data[CLT_MSG_MAGIC_LEN:CLT_MSG_MAGIC_LEN+CLT_MSG_PRO_LEN]
    try:
        protocol_id = int(protocol_str)
    except ValueError:
        client_socket.close()
        logging.debug("recv msg protocol id is invalid %s", protocol_str)
        return None

    if protocol_id >= ClientProtocol.PRO_END:
        client_socket.close()
        logging.debug("protocol id is invalid")
        return None

    try:
        res_data_len = int(res_data[CLT_MSG_MAGIC_LEN+CLT_MSG_PRO_LEN:])
        if res_data_len < 0 or res_data_len > MAX_MSG_LEN:
            client_socket.close()
            logging.error("socket recv data is illegal:%d", res_data_len)
            return None
        res_msg_data = client_socket.recv(res_data_len)
        res_msg_data = res_msg_data.decode()
        return res_msg_data
    except (OSError, ValueError, UnicodeError):
        logging.debug("collect_plugin: client recv res msg error")
    finally:
        client_socket.close()

    return None

def validate_parameters(param, len_limit, char_limit):
    ret = ResultMessage.RESULT_SUCCEED
    if not param:
        logging.error("param is invalid, param = %s", param)
        ret = ResultMessage.RESULT_NOT_PARAM
        return [False, ret]

    if not isinstance(param, list):
        logging.error("%s is not list type.", param)
        ret = ResultMessage.RESULT_NOT_PARAM
        return [False, ret]

    if len(param) <= 0:
        logging.error("%s length is 0.", param)
        ret =  ResultMessage.RESULT_INVALID_LENGTH
        return [False, ret]

    pattern = r'^[a-zA-Z0-9_-]+$'
    for info in param:
        if not re.match(pattern, info):
            logging.error("%s is invalid char", info)
            ret =  ResultMessage.RESULT_INVALID_CHAR
            return [False, ret]

    # length of len_limit is exceeded, keep len_limit
    if len(param) > len_limit:
        logging.error("%s length more than %d, keep the first %d", param, len_limit, len_limit)
        param[:] = param[0:len_limit]

    # only keep elements under the char_limit length
    param[:] = [elem for elem in param if len(elem) <= char_limit]

    return [True, ret]

def is_iocollect_valid(period, disk_list=None, stage=None):
    result = inter_is_iocollect_valid(period, disk_list, stage)
    error_code = result['ret']
    if error_code != ResultMessage.RESULT_SUCCEED:
        result['message'] = Result_Messages[error_code]
    return result

def inter_is_iocollect_valid(period, disk_list=None, stage=None):
    result = {}
    result['ret'] = ResultMessage.RESULT_UNKNOWN
    result['message'] = ""

    if not period or not isinstance(period, int):
        result['ret'] = ResultMessage.RESULT_NOT_PARAM
        return result
    if period < LIMIT_PERIOD_MIN_LEN or period > LIMIT_PERIOD_MAX_LEN * LIMIT_MAX_SAVE_LEN:
        result['ret'] = ResultMessage.RESULT_INVALID_LENGTH
        return result

    if not disk_list:
        disk_list = []
    else:
        res = validate_parameters(disk_list, LIMIT_DISK_LIST_LEN, LIMIT_DISK_CHAR_LEN)
        if not res[0]:
            result['ret'] = res[1]
            return result

    if not stage:
        stage = []
    else:
        res = validate_parameters(stage, LIMIT_STAGE_LIST_LEN, LIMIT_STAGE_CHAR_LEN)
        if not res[0]:
            result['ret'] = res[1]
            return result

    req_msg_struct = {
            'disk_list': json.dumps(disk_list),
            'period': period,
            'stage': json.dumps(stage)
        }
    request_message = json.dumps(req_msg_struct)
    result_message = client_send_and_recv(request_message, CLT_MSG_LEN_LEN, ClientProtocol.IS_IOCOLLECT_VALID)
    if not result_message:
        logging.error("collect_plugin: client_send_and_recv failed")
        return result
        
    try:
        json.loads(result_message)
    except json.JSONDecodeError:
        logging.error("is_iocollect_valid: json decode error")
        result['ret'] = ResultMessage.RESULT_PARSE_FAILED
        return result

    result['ret'] = ResultMessage.RESULT_SUCCEED
    result['message'] = result_message
    return result


def inter_get_io_common(period, disk_list, stage, iotype, protocol):
    result = {}
    result['ret'] = ResultMessage.RESULT_UNKNOWN
    result['message'] = ""

    if not isinstance(period, int):
        result['ret'] = ResultMessage.RESULT_NOT_PARAM
        return result
    if period < LIMIT_PERIOD_MIN_LEN or period > LIMIT_PERIOD_MAX_LEN * LIMIT_MAX_SAVE_LEN:
        result['ret'] = ResultMessage.RESULT_INVALID_LENGTH
        return result

    res = validate_parameters(disk_list, LIMIT_DISK_LIST_LEN, LIMIT_DISK_CHAR_LEN)
    if not res[0]:
        result['ret'] = res[1]
        return result

    res = validate_parameters(stage, LIMIT_STAGE_LIST_LEN, LIMIT_STAGE_CHAR_LEN)
    if not res[0]:
        result['ret'] = res[1]
        return result

    res = validate_parameters(iotype, LIMIT_IOTYPE_LIST_LEN, LIMIT_IOTYPE_CHAR_LEN)
    if not res[0]:
        result['ret'] = res[1]
        return result

    req_msg_struct = {
        'disk_list': json.dumps(disk_list),
        'period': period,
        'stage': json.dumps(stage),
        'iotype': json.dumps(iotype)
    }

    request_message = json.dumps(req_msg_struct)
    result_message = client_send_and_recv(request_message, CLT_MSG_LEN_LEN, protocol)
    if not result_message:
        logging.error("collect_plugin: client_send_and_recv failed")
        return result
    try:
        json.loads(result_message)
    except json.JSONDecodeError:
        logging.error("get_io_common: json decode error")
        result['ret'] = ResultMessage.RESULT_PARSE_FAILED
        return result

    result['ret'] = ResultMessage.RESULT_SUCCEED
    result['message'] = result_message
    return result


def get_io_data(period, disk_list, stage, iotype):
    result = inter_get_io_common(period, disk_list, stage, iotype, ClientProtocol.GET_IO_DATA)
    error_code = result['ret']
    if error_code != ResultMessage.RESULT_SUCCEED:
        result['message'] = Result_Messages[error_code]
    return result


def get_iodump_data(period, disk_list, stage, iotype):
    result = inter_get_io_common(period, disk_list, stage, iotype, ClientProtocol.GET_IODUMP_DATA)
    error_code = result['ret']
    if error_code != ResultMessage.RESULT_SUCCEED:
        result['message'] = Result_Messages[error_code]
    return result


def get_disk_data(period, disk_list, stage, iotype):
    result = inter_get_io_common(period, disk_list, stage, iotype, ClientProtocol.GET_DISK_DATA)
    error_code = result['ret']
    if error_code != ResultMessage.RESULT_SUCCEED:
        result['message'] = Result_Messages[error_code]
    return result


def get_disk_type(disk):
    result = {}
    result['ret'] = ResultMessage.RESULT_UNKNOWN
    result['message'] = ""
    if not disk:
        logging.error("param is invalid")
        result['ret'] = ResultMessage.RESULT_NOT_PARAM
        return result
    if len(disk) <= 0 or len(disk) > LIMIT_DISK_CHAR_LEN:
        logging.error("invalid disk length")
        result['ret'] = ResultMessage.RESULT_INVALID_LENGTH
        return result
    pattern = r'^[a-zA-Z0-9_-]+$'
    if not re.match(pattern, disk):
        logging.error("%s is invalid char", disk)
        result['ret'] =  ResultMessage.RESULT_INVALID_CHAR
        return result

    base_path = '/sys/block'
    all_disk = []
    for disk_name in os.listdir(base_path):
        all_disk.append(disk_name)

    if disk not in all_disk:
        logging.error("disk %s is not exist", disk)
        result['ret'] = ResultMessage.RESULT_DISK_NOEXIST
        return result
    
    if disk[0:4] == "nvme":
        result['message'] = str(DiskType.TYPE_NVME_SSD)
    elif disk[0:2] == "sd":
        disk_file = '/sys/block/{}/queue/rotational'.format(disk)
        try:
            with open(disk_file, 'r') as file:
                num = int(file.read())
                if num == 0:
                    result['message'] = str(DiskType.TYPE_SATA_SSD)
                elif num == 1:
                    result['message'] = str(DiskType.TYPE_SATA_HDD)
                else:
                    logging.error("disk %s is not support, num = %d", disk, num)
                    result['ret'] = ResultMessage.RESULT_DISK_TYPE_MISMATCH
                    return result
        except FileNotFoundError:
            logging.error("The disk_file [%s] does not exist", disk_file)
            result['ret'] = ResultMessage.RESULT_DISK_NOEXIST
            return result
        except Exception as e:
            logging.error("open disk_file %s happen an error: %s", disk_file, e)
            return result
    else:
        logging.error("disk %s is not support", disk)
        result['ret'] = ResultMessage.RESULT_DISK_TYPE_MISMATCH
        return result

    result['ret'] = ResultMessage.RESULT_SUCCEED
    return result
