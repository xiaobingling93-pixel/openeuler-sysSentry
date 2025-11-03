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
Read and save collector.conf value.
"""
import configparser
import logging
import os
import re


COLLECT_CONF_PATH = "/etc/sysSentry/collector.conf"

CONF_COMMON = 'common'
CONF_MODULES = 'modules'

# io
CONF_IO = 'io'
CONF_IO_PERIOD_TIME = 'period_time'
CONF_IO_MAX_SAVE = 'max_save'
CONF_IO_DISK = 'disk'
CONF_IO_PERIOD_TIME_DEFAULT = 1
CONF_IO_MAX_SAVE_DEFAULT = 10
CONF_IO_DISK_DEFAULT = "default"
CONF_IO_NVME_SSD = "nvme_ssd_threshold"
CONF_IO_SATA_SSD = "sata_ssd_threshold"
CONF_IO_SATA_HDD = "sata_hdd_threshold"
CONF_IO_THRESHOLD_DEFAULT = 1000

# log
CONF_LOG = 'log'
CONF_LOG_LEVEL = 'level'
LogLevel = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL
}


def get_log_level(filename=COLLECT_CONF_PATH):
    if not os.path.exists(filename):
        return logging.INFO

    try:
        config = configparser.ConfigParser()
        config.read(filename)
        if not config.has_option(CONF_LOG, CONF_LOG_LEVEL):
            return logging.INFO
        log_level = config.get(CONF_LOG, CONF_LOG_LEVEL)
        if log_level.lower() in LogLevel:
            return LogLevel.get(log_level.lower())
        return logging.INFO
    except configparser.Error:
        return logging.INFO


class CollectConfig:
    def __init__(self, filename=COLLECT_CONF_PATH):
        
        self.filename = filename
        self.modules = []
        self.module_count = 0
        self.load_config()

    def load_config(self):
        if not os.path.exists(self.filename):
            logging.error("%s is not exists", self.filename)
            return

        try:
            self.config = configparser.ConfigParser()
            self.config.read(self.filename)
        except configparser.Error:
            logging.error("collect configure file read failed")
            return
        
        try:
            common_config = self.config[CONF_COMMON]
            modules_str = common_config[CONF_MODULES].lower()
            # remove space
            modules_list = set(modules_str.replace(" ", "").split(','))
        except KeyError as e:
            logging.error("read config data failed, %s", e)
            return

        pattern = r'^[a-zA-Z0-9-_]+$'
        for module_name in modules_list:
            if not re.match(pattern, module_name):
                logging.warning("module_name: %s is invalid", module_name)
                continue
            if not self.config.has_section(module_name):
                logging.warning("module_name: %s config is incorrect", module_name)
                continue
            self.modules.append(module_name)

    def load_module_config(self, module_name):
        module_name = module_name.strip().lower()
        if module_name in self.modules and self.config.has_section(module_name):
            return {key.lower(): value for key, value in self.config[module_name].items()}
        else:
            raise ValueError(f"Module '{module_name}' not found in configuration")

    def get_io_config(self):
        result_io_config = {}
        io_map_value = self.load_module_config(CONF_IO)
        # period_time
        period_time = io_map_value.get(CONF_IO_PERIOD_TIME)
        if period_time and period_time.isdigit() and int(period_time) >= 1 and int(period_time) <= 300:
            result_io_config[CONF_IO_PERIOD_TIME] = int(period_time)
        else:
            logging.warning("module_name = %s section, field = %s is incorrect, use default %d", 
                CONF_IO, CONF_IO_PERIOD_TIME, CONF_IO_PERIOD_TIME_DEFAULT)
            result_io_config[CONF_IO_PERIOD_TIME] = CONF_IO_PERIOD_TIME_DEFAULT
        # max_save
        max_save = io_map_value.get(CONF_IO_MAX_SAVE)
        if max_save and max_save.isdigit() and int(max_save) >= 1 and int(max_save) <= 300:
            result_io_config[CONF_IO_MAX_SAVE] = int(max_save)
        else:
            logging.warning("module_name = %s section, field = %s is incorrect, use default %d", 
                CONF_IO, CONF_IO_MAX_SAVE, CONF_IO_MAX_SAVE_DEFAULT)
            result_io_config[CONF_IO_MAX_SAVE] = CONF_IO_MAX_SAVE_DEFAULT
        # disk
        disk = io_map_value.get(CONF_IO_DISK)
        if disk:
            disk_str = disk.lower().replace(" ", "")
            pattern = r'^[a-zA-Z0-9-_,]+$'
            if not re.match(pattern, disk_str):
                logging.warning("module_name = %s section, field = %s is incorrect, use default %s", 
                CONF_IO, CONF_IO_DISK, CONF_IO_DISK_DEFAULT)
                disk_str = CONF_IO_DISK_DEFAULT
            disk_str = ",".join(set(disk_str.split(',')))
            result_io_config[CONF_IO_DISK] = disk_str
        else:
            logging.warning("module_name = %s section, field = %s is incorrect, use default %s", 
                CONF_IO, CONF_IO_DISK, CONF_IO_DISK_DEFAULT)
            result_io_config[CONF_IO_DISK] = CONF_IO_DISK_DEFAULT
        logging.debug("config get_io_config: %s", result_io_config)
        return result_io_config

    def get_io_threshold(self):
        result_io_threshold = {}
        io_map_value = self.load_module_config(CONF_IO)
        # nvme ssd threshold
        nvme_ssd_threshold = io_map_value.get(CONF_IO_NVME_SSD)
        if nvme_ssd_threshold and nvme_ssd_threshold.isdigit() and int(nvme_ssd_threshold) >= 1:
            result_io_threshold[CONF_IO_NVME_SSD] = int(nvme_ssd_threshold)
        else:
            logging.warning("module_name = %s section, field = %s is incorrect, use default %d", 
                CONF_IO, CONF_IO_NVME_SSD, CONF_IO_THRESHOLD_DEFAULT)
            result_io_threshold[CONF_IO_NVME_SSD] = CONF_IO_THRESHOLD_DEFAULT
        # sata ssd threshold
        sata_ssd_threshold = io_map_value.get(CONF_IO_SATA_SSD)
        if sata_ssd_threshold and sata_ssd_threshold.isdigit() and int(sata_ssd_threshold) >= 1:
            result_io_threshold[CONF_IO_SATA_SSD] = int(sata_ssd_threshold)
        else:
            logging.warning("module_name = %s section, field = %s is incorrect, use default %d", 
                CONF_IO, CONF_IO_SATA_SSD, CONF_IO_THRESHOLD_DEFAULT)
            result_io_threshold[CONF_IO_SATA_SSD] = CONF_IO_THRESHOLD_DEFAULT
        # sata hdd threshold
        sata_hdd_threshold = io_map_value.get(CONF_IO_SATA_HDD)
        if sata_hdd_threshold and sata_hdd_threshold.isdigit() and int(sata_hdd_threshold) >= 1:
            result_io_threshold[CONF_IO_SATA_HDD] = int(sata_hdd_threshold)
        else:
            logging.warning("module_name = %s section, field = %s is incorrect, use default %d", 
                CONF_IO, CONF_IO_SATA_HDD, CONF_IO_THRESHOLD_DEFAULT)
            result_io_threshold[CONF_IO_SATA_HDD] = CONF_IO_THRESHOLD_DEFAULT
        logging.debug("config get_io_threshold: %s", result_io_threshold)
        return result_io_threshold

    def get_common_config(self):
        return {key.lower(): value for key, value in self.config['common'].items()}
