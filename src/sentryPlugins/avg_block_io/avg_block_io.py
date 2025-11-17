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
import signal
import configparser
import time

from .config import read_config_log, read_config_common, read_config_algorithm, read_config_latency, read_config_iodump, read_config_stage
from .stage_window import IoWindow, IoDumpWindow, IopsWindow, IoArrayDataWindow
from .module_conn import avg_is_iocollect_valid, avg_get_io_data, avg_get_iodump_data, avg_get_disk_data, \
    report_alarm_fail, process_report_data, sig_handler, get_disk_type_by_name, check_disk_list_validation
from .utils import update_avg_and_check_abnormal, update_avg_array_data
from .extra_logger import init_extra_logger

CONFIG_FILE = "/etc/sysSentry/plugins/avg_block_io.ini"
AVG_EXTRA_LOG_PATH = "/var/log/sysSentry/avg_block_io_extra.log"


def init_io_win(io_dic, config, common_param):
    """initialize windows of latency, iodump, and dict of avg_value"""
    iotype_list = io_dic["iotype_list"]
    io_data = {}
    io_avg_value = {}
    for disk_name in io_dic["disk_list"]:
        io_data[disk_name] = {}
        io_avg_value[disk_name] = {}
        curr_disk_type = get_disk_type_by_name(disk_name)
        for stage_name in io_dic["stage_list"]:
            io_data[disk_name][stage_name] = {}
            io_avg_value[disk_name][stage_name] = {}
            # 解析stage配置
            curr_stage_param = read_config_stage(config, stage_name, iotype_list, curr_disk_type)
            for rw in iotype_list:
                io_data[disk_name][stage_name][rw] = {}
                io_avg_value[disk_name][stage_name][rw] = [0, 0]

                # 对每个rw创建latency和iodump窗口
                avg_lim_key = "{}_avg_lim".format(rw)
                avg_time_key = "{}_avg_time".format(rw)
                tot_lim_key = "{}_tot_lim".format(rw)
                iodump_lim_key = "{}_iodump_lim".format(rw)

                # 获取值，优先从 curr_stage_param 获取，如果不存在，则从 common_param 获取
                avg_lim_value = curr_stage_param.get(avg_lim_key, common_param.get(curr_disk_type, {}).get(avg_lim_key))
                avg_time_value = curr_stage_param.get(avg_time_key, common_param.get(curr_disk_type, {}).get(avg_time_key))
                tot_lim_value = curr_stage_param.get(tot_lim_key, common_param.get(curr_disk_type, {}).get(tot_lim_key))
                iodump_lim_value = curr_stage_param.get(iodump_lim_key, common_param.get("iodump", {}).get(iodump_lim_key))

                if avg_lim_value and avg_time_value and tot_lim_value:
                    io_data[disk_name][stage_name][rw]["latency"] = \
                        IoWindow(window_size=io_dic["win_size"], window_threshold=io_dic["win_threshold_latency"], \
                                 abnormal_multiple=avg_time_value, abnormal_multiple_lim=avg_lim_value, \
                                    abnormal_time=tot_lim_value)
                    logging.debug("Successfully create {}-{}-{}-latency window".format(disk_name, stage_name, rw))

                if iodump_lim_value is not None:
                    io_data[disk_name][stage_name][rw]["iodump"] =\
                          IoDumpWindow(window_size=io_dic["win_size"], window_threshold=io_dic["win_threshold_iodump"],\
                                        abnormal_time=iodump_lim_value)
                    logging.debug("Successfully create {}-{}-{}-iodump window".format(disk_name, stage_name, rw))

                io_data[disk_name][stage_name][rw]["iops"] = IopsWindow(window_size=io_dic["win_size"])
                logging.debug("Successfully create {}-{}-{}-iops window".format(disk_name, stage_name, rw))

                io_data[disk_name][stage_name][rw]["iodump_data"] = IoArrayDataWindow(window_size=io_dic["win_size"])
                logging.debug("Successfully create {}-{}-{}-iodump_data window".format(disk_name, stage_name, rw))

                io_data[disk_name][stage_name][rw]["disk_data"] = IoArrayDataWindow(window_size=io_dic["win_size"])
                logging.debug("Successfully create {}-{}-{}-disk_data window".format(disk_name, stage_name, rw))
    return io_data, io_avg_value


def get_valid_disk_stage_list(io_dic, config_disk, config_stage):
    """get disk_list and stage_list by sentryCollector"""
    json_data = avg_is_iocollect_valid(io_dic, config_disk, config_stage)

    all_disk_set = json_data.keys()
    all_stage_set = set()
    for disk_stage_list in json_data.values():
        all_stage_set.update(disk_stage_list)

    disk_list = [key for key in all_disk_set if key in config_disk]
    not_in_disk_list = [key for key in config_disk if key not in all_disk_set]

    if not config_disk and not not_in_disk_list:
        disk_list = [key for key in all_disk_set]

    if not disk_list:
        report_alarm_fail("Cannot get valid disk name")

    disk_list = check_disk_list_validation(disk_list)

    disk_list = disk_list[:10] if len(disk_list) > 10 else disk_list

    if not config_disk:
        logging.info(f"Default common.disk using disk={disk_list}")
    elif sorted(disk_list) != sorted(config_disk):
        logging.warning(f"Set common.disk to {disk_list}")

    stage_list = [key for key in all_stage_set if key in config_stage]
    not_in_stage_list = [key for key in config_stage if key not in all_stage_set]

    if not_in_stage_list:
        report_alarm_fail(f"Invalid common.stage_list config, cannot set {not_in_stage_list}")

    if not config_stage:
        stage_list = [key for key in all_stage_set]

    if not stage_list:
        report_alarm_fail("Cannot get valid stage name.")

    if not config_stage:
        logging.info(f"Default common.stage using stage={stage_list}")

    return disk_list, stage_list


def main_loop(io_dic, io_data, io_avg_value):
    """main loop of avg_block_io"""
    period_time = io_dic["period_time"]
    disk_list = io_dic["disk_list"]
    stage_list = io_dic["stage_list"]
    iotype_list = io_dic["iotype_list"]
    win_size = io_dic["win_size"]
    # 开始循环
    while True:
        # 等待x秒
        time.sleep(period_time)

        # 采集模块对接，获取周期数据
        is_success, curr_period_data = avg_get_io_data(io_dic)
        if not is_success:
            logging.error(f"{curr_period_data['msg']}")
            continue

        # 获取iodump的详细信息
        is_success_iodump, iodump_data = avg_get_iodump_data(io_dic)

        # 获取磁盘的时延数据
        is_success_disk, disk_data = avg_get_disk_data(io_dic)

        # 处理周期数据
        reach_size = False
        for disk_name in disk_list:
            for stage_name in stage_list:
                for rw in iotype_list:
                    if disk_name in curr_period_data and stage_name in curr_period_data[disk_name] and rw in curr_period_data[disk_name][stage_name]:
                        io_key = (disk_name, stage_name, rw)
                        reach_size = update_avg_and_check_abnormal(curr_period_data, io_key, win_size, io_avg_value, io_data)
                        update_avg_array_data(iodump_data, is_success_iodump, io_key, io_data, "iodump_data")
                        update_avg_array_data(disk_data, is_success_disk, io_key, io_data, "disk_data")

        # win_size不满时不进行告警判断
        if not reach_size:
            continue

        # 判断异常窗口、异常场景
        for disk_name in disk_list:
            for rw in iotype_list:
                process_report_data(disk_name, rw, io_data)


def main():
    """main func"""
    # 注册停止信号-2/-15
    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    log_level = read_config_log(CONFIG_FILE)
    log_format = "%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
    logging.basicConfig(level=log_level, format=log_format)
    init_extra_logger(AVG_EXTRA_LOG_PATH, log_level, log_format)

    # 初始化配置读取
    config = configparser.ConfigParser(comment_prefixes=('#', ';'))
    try:
        config.read(CONFIG_FILE)
    except configparser.Error:
        report_alarm_fail("Failed to read config file")

    io_dic = {}

    # 读取配置文件 -- common段
    io_dic["period_time"], disk, stage, io_dic["iotype_list"] = read_config_common(config)

    # 采集模块对接，is_iocollect_valid()
    io_dic["disk_list"], io_dic["stage_list"] = get_valid_disk_stage_list(io_dic, disk, stage)

    logging.debug(f"disk={io_dic['disk_list']}, stage={io_dic['stage_list']}")

    if "bio" not in io_dic["stage_list"]:
        report_alarm_fail("Cannot run avg_block_io without bio stage")

    # 初始化窗口 -- config读取，对应is_iocollect_valid返回的结果
    # step1. 解析公共配置 --- algorithm
    io_dic["win_size"], io_dic["win_threshold_latency"], io_dic["win_threshold_iodump"] = read_config_algorithm(config)

    # step2. 解析公共配置 --- latency_xxx
    common_param = read_config_latency(config)

    # step3. 解析公共配置 --- iodump
    common_param['iodump'] = read_config_iodump(config)

    # step4. 循环创建窗口
    io_data, io_avg_value = init_io_win(io_dic, config, common_param)

    main_loop(io_dic, io_data, io_avg_value)
