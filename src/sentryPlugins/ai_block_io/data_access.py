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

import json
import logging

from sentryCollector.collect_plugin import (
    Result_Messages,
    get_io_data,
    get_iodump_data,
    is_iocollect_valid,
    get_disk_type
)


from .io_data import IOStageData, IOData, IOStageDumpData, IODumpData

COLLECT_STAGES = [
    "throtl",
    "wbt",
    "gettag",
    "plug",
    "bfq",
    "hctx",
    "requeue",
    "rq_driver",
    "bio",
    "iocost",
    "deadline",
]


def check_collect_valid(period):
    data_raw = is_iocollect_valid(period)
    if data_raw["ret"] == 0:
        try:
            data = json.loads(data_raw["message"])
        except Exception as e:
            logging.warning(f"get valid devices failed, occur exception: {e}")
            return None
        if not data:
            logging.warning(f"get valid devices failed, return {data_raw}")
            return None
        return [k for k in data.keys()]
    else:
        logging.warning(f"get valid devices failed, return {data_raw}")
        return None


def check_detect_frequency_is_valid(period):
    data_raw = is_iocollect_valid(period)
    if data_raw["ret"] == 0:
        try:
            data = json.loads(data_raw["message"])
        except Exception as e:
            return None
        if not data:
            return None
        return [k for k in data.keys()]
    else:
        return None


def check_disk_is_available(period_time, disk):
    data_raw = is_iocollect_valid(period_time, disk)
    if data_raw["ret"] == 0:
        try:
            data = json.loads(data_raw["message"])
        except Exception as e:
            return False
        if not data:
            return False
        return True
    else:
        return False


def _get_raw_data(period, disk_list):
    return get_io_data(
        period,
        disk_list,
        COLLECT_STAGES,
        ["read", "write", "flush", "discard"],
    )


def _get_io_stage_data(data):
    io_stage_data = IOStageData()
    for data_type in ("read", "write", "flush", "discard"):
        if data_type in data:
            getattr(io_stage_data, data_type).latency = data[data_type][0]
            getattr(io_stage_data, data_type).io_dump = data[data_type][1]
            getattr(io_stage_data, data_type).io_length = data[data_type][2]
            getattr(io_stage_data, data_type).iops = data[data_type][3]
    return io_stage_data


def get_io_data_from_collect_plug(period, disk_list):
    data_raw = _get_raw_data(period, disk_list)
    if data_raw["ret"] == 0:
        ret = {}
        try:
            data = json.loads(data_raw["message"])
        except json.decoder.JSONDecodeError as e:
            logging.warning(f"get io data failed, {e}")
            return None

        for disk in data:
            disk_data = data[disk]
            disk_ret = IOData()
            for k, v in disk_data.items():
                try:
                    getattr(disk_ret, k)
                    setattr(disk_ret, k, _get_io_stage_data(v))
                except AttributeError:
                    logging.debug(f"no attr {k}")
                    continue
            ret[disk] = disk_ret
        return ret
    logging.warning(f'get io data failed with message: {data_raw["message"]}')
    return None


def _get_raw_iodump_data(period, disk_list):
    return get_iodump_data(
        period,
        disk_list,
        COLLECT_STAGES,
        ["read", "write", "flush", "discard"],
    )


def _get_iodump_stage_data(data):
    io_stage_data = IOStageDumpData()
    for data_type in ("read", "write", "flush", "discard"):
        if data_type in data:
            getattr(io_stage_data, data_type).iodump_data = data[data_type]
    return io_stage_data


def get_iodump_data_from_collect_plug(period, disk_list):
    data_raw = _get_raw_iodump_data(period, disk_list)
    if data_raw["ret"] == 0:
        ret = {}
        try:
            data = json.loads(data_raw["message"])
        except json.decoder.JSONDecodeError as e:
            logging.warning(f"get iodump data failed, {e}")
            return None

        for disk in data:
            disk_data = data[disk]
            disk_ret = IODumpData()
            for k, v in disk_data.items():
                try:
                    getattr(disk_ret, k)
                    setattr(disk_ret, k, _get_iodump_stage_data(v))
                except AttributeError:
                    logging.debug(f"no attr {k}")
                    continue
            ret[disk] = disk_ret
        return ret
    logging.warning(f'get iodump data failed with message: {data_raw["message"]}')
    return None