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
import logging
from .extra_logger import extra_slow_log

AVG_VALUE = 0
AVG_COUNT = 1


def get_nested_value(data, keys):
    """get data from nested dict"""
    for key in keys:
        if key in data:
            data = data[key]
        else:
            return None
    return data


def set_nested_value(data, keys, value):
    """set data to nested dict"""
    for key in keys[:-1]:
        if key in data:
            data = data[key]
        else:
            return False
    data[keys[-1]] = value
    return True


def get_win_data(disk_name, rw, io_data):
    """get latency and iodump win data"""
    latency = ''
    iodump = ''
    iops = ''
    iodump_data = ''
    disk_data = ''
    for stage_name in io_data[disk_name]:
        if 'latency' in io_data[disk_name][stage_name][rw]:
            latency_list = io_data[disk_name][stage_name][rw]['latency'].window_data_to_string()
            latency += f'{stage_name}: [{latency_list}], '
        if 'iodump' in io_data[disk_name][stage_name][rw]:
            iodump_list = io_data[disk_name][stage_name][rw]['iodump'].window_data_to_string()
            iodump += f'{stage_name}: [{iodump_list}], '
        if 'iops' in io_data[disk_name][stage_name][rw]:
            iops_list = io_data[disk_name][stage_name][rw]['iops'].window_data_to_string()
            iops += f'{stage_name}: [{iops_list}], '
        if 'iodump_data' in io_data[disk_name][stage_name][rw]:
            iodump_data_list = io_data[disk_name][stage_name][rw]['iodump_data'].window_data_to_string()
            iodump_data += f'"{stage_name}": {iodump_data_list}, '
        if 'disk_data' in io_data[disk_name][stage_name][rw]:
            disk_data_list = io_data[disk_name][stage_name][rw]['disk_data'].window_data_to_string()
            disk_data += f'"{stage_name}": {disk_data_list}, '
    if iodump_data:
        iodump_data = '{' + iodump_data[:-2] + '}'
    if disk_name:
        disk_data = '{' + disk_data[:-2] + '}'
    return {"latency": latency[:-2], "iodump": iodump[:-2], "iops": iops[:-2], \
            "iodump_data": iodump_data, "disk_data": disk_data}


def is_abnormal(io_key, io_data):
    """check if latency and iodump win abnormal"""
    abnormal_list = ''
    for key in ['latency', 'iodump']:
        all_keys = get_nested_value(io_data, io_key)
        if all_keys and key in all_keys:
            win = get_nested_value(io_data, io_key + (key,))
            if win and win.is_abnormal_window():
                abnormal_list += key + ', '
    if not abnormal_list:
        return False, abnormal_list
    return True, abnormal_list[:-2]


def update_io_avg(old_avg, period_value, win_size):
    """update average of latency window"""
    if old_avg[AVG_COUNT] < win_size:
        new_avg_count = old_avg[AVG_COUNT] + 1
        new_avg_value = (old_avg[AVG_VALUE] * old_avg[AVG_COUNT] + period_value[0]) / new_avg_count
    else:
        new_avg_count = old_avg[AVG_COUNT]
        new_avg_value = (old_avg[AVG_VALUE] * (old_avg[AVG_COUNT] - 1) + period_value[0]) / new_avg_count
    return [new_avg_value, new_avg_count]


def update_io_period(old_avg, period_value, io_data, io_key):
    """update period of latency and iodump window"""
    all_wins = get_nested_value(io_data, io_key)
    if all_wins and "latency" in all_wins:
        io_data[io_key[0]][io_key[1]][io_key[2]]["latency"].append_new_period(period_value[0], old_avg[AVG_VALUE])
    if all_wins and "iodump" in all_wins:
        io_data[io_key[0]][io_key[1]][io_key[2]]["iodump"].append_new_period(period_value[1])


def update_io_data(period_value, io_data, io_key):
    """update data of latency and iodump window"""
    all_wins = get_nested_value(io_data, io_key)
    if all_wins and "latency" in all_wins:
        io_data[io_key[0]][io_key[1]][io_key[2]]["latency"].append_new_data(period_value[0])
    if all_wins and "iodump" in all_wins:
        io_data[io_key[0]][io_key[1]][io_key[2]]["iodump"].append_new_data(period_value[1])
    if all_wins and "iops" in all_wins:
        io_data[io_key[0]][io_key[1]][io_key[2]]["iops"].append_new_data(period_value[3])


def log_abnormal_period(old_avg, period_value, io_data, io_key):
    """record log of abnormal period"""
    all_wins = get_nested_value(io_data, io_key)
    if all_wins and "latency" in all_wins:
        if all_wins["latency"].is_abnormal_period(period_value[0], old_avg[AVG_VALUE]):
            logging.info(f"[abnormal_period] disk: {io_key[0]}, stage: {io_key[1]}, iotype: {io_key[2]}, "
                            f"type: latency, avg: {round(old_avg[AVG_VALUE], 3)}, curr_val: {period_value[0]}")
    if all_wins and "iodump" in all_wins:
        if all_wins["iodump"].is_abnormal_period(period_value[1]):
            logging.info(f"[abnormal_period] disk: {io_key[0]}, stage: {io_key[1]}, iotype: {io_key[2]}, "
                            f"type: iodump, curr_val: {period_value[1]}")


def log_slow_win(msg, reason):
    """record log of slow win"""
    logging.warning(f"[SLOW IO] disk: {msg['driver_name']}, stage: {msg['block_stack']}, "
                    f"iotype: {msg['io_type']}, type: {msg['alarm_type']}, reason: {reason}")
    logging.info(f"latency: {msg['details']['latency']}")
    logging.info(f"iodump: {msg['details']['iodump']}")
    logging.info(f"iops: {msg['details']['iops']}")
    extra_slow_log(msg)


def update_avg_and_check_abnormal(data, io_key, win_size, io_avg_value, io_data):
    """update avg and check abonrmal, return true if win_size full"""
    period_value = get_nested_value(data, io_key)
    old_avg = get_nested_value(io_avg_value, io_key)

    # 更新avg数据
    update_io_data(period_value, io_data, io_key)
    if old_avg[AVG_COUNT] < win_size:
        set_nested_value(io_avg_value, io_key, update_io_avg(old_avg, period_value, win_size))
        return False

    # 打印异常周期数据
    log_abnormal_period(old_avg, period_value, io_data, io_key)

    # 更新win数据 -- 判断异常周期
    update_io_period(old_avg, period_value, io_data, io_key)
    all_wins = get_nested_value(io_data, io_key)
    if not all_wins or 'latency' not in all_wins:
        return True
    period = get_nested_value(io_data, io_key + ("latency",))
    if period and period.is_abnormal_period(period_value[0], old_avg[AVG_VALUE]):
        return True
    set_nested_value(io_avg_value, io_key, update_io_avg(old_avg, period_value, win_size))
    return True


def update_avg_array_data(array_data, is_success, io_key, io_data, data_type):
    """update array data to io_data"""
    all_wins = get_nested_value(io_data, io_key)
    if all_wins and data_type in all_wins:
        if not is_success:
            io_data[io_key[0]][io_key[1]][io_key[2]][data_type].append_new_data([])
        else:
            period_value = get_nested_value(array_data, io_key)
            io_data[io_key[0]][io_key[1]][io_key[2]][data_type].append_new_data(period_value)

