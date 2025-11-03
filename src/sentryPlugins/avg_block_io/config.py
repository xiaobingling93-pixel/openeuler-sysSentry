import configparser
import logging
import os

from .module_conn import report_alarm_fail
from sentryCollector.collect_plugin import Disk_Type


CONF_LOG = 'log'
CONF_LOG_LEVEL = 'level'
LogLevel = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL
}

CONF_COMMON = 'common'
CONF_COMMON_DISK = 'disk'
CONF_COMMON_STAGE = 'stage'
CONF_COMMON_IOTYPE = 'iotype'
CONF_COMMON_PER_TIME = 'period_time'

CONF_ALGO = 'algorithm'
CONF_ALGO_SIZE = 'win_size'
CONF_ALGO_THRE_LATENCY = 'win_threshold_latency'
CONF_ALGO_THRE_IODUMP = 'win_threshold_iodump'

CONF_LATENCY = 'latency_{}'
CONF_IODUMP = 'iodump'


DEFAULT_PARAM = {
    CONF_LOG: {
        CONF_LOG_LEVEL: 'info'
    }, CONF_COMMON: {
        CONF_COMMON_DISK: 'default',
        CONF_COMMON_STAGE: 'default',
        CONF_COMMON_IOTYPE: 'read,write',
        CONF_COMMON_PER_TIME: 1
    }, CONF_ALGO: {
        CONF_ALGO_SIZE: 30,
        CONF_ALGO_THRE_LATENCY: 6,
        CONF_ALGO_THRE_IODUMP: 3
    }, 'latency_nvme_ssd': {
        'read_avg_lim': 10000,
        'write_avg_lim': 10000,
        'read_avg_time': 3,
        'write_avg_time': 3,
        'read_tot_lim': 50000,
        'write_tot_lim': 50000,
    }, 'latency_sata_ssd' : {
        'read_avg_lim': 10000,
        'write_avg_lim': 10000,
        'read_avg_time': 3,
        'write_avg_time': 3,
        'read_tot_lim': 50000,
        'write_tot_lim': 50000,
    }, 'latency_sata_hdd' : {
        'read_avg_lim': 15000,
        'write_avg_lim': 15000,
        'read_avg_time': 3,
        'write_avg_time': 3,
        'read_tot_lim': 50000,
        'write_tot_lim': 50000
    }, CONF_IODUMP: {
        'read_iodump_lim': 0,
        'write_iodump_lim': 0
    }
}


def get_section_value(section_name, config):
    common_param = {}
    config_sec = config[section_name]
    for config_key in DEFAULT_PARAM[section_name]:
        if config_key in config_sec:
            if not config_sec[config_key].isdecimal():
                report_alarm_fail(f"Invalid {section_name}.{config_key} config.")
            common_param[config_key] = int(config_sec[config_key])
        else:
            common_param[config_key] = DEFAULT_PARAM[section_name][config_key]
            logging.warning(f"Unset {section_name}.{config_key} in config file, use {common_param[config_key]} as default")
    return common_param

            
def read_config_log(filename):
    """read config file, get [log] section value"""
    default_log_level = DEFAULT_PARAM[CONF_LOG][CONF_LOG_LEVEL]
    if not os.path.exists(filename):
        return LogLevel.get(default_log_level)

    config = configparser.ConfigParser()
    config.read(filename)

    log_level = config.get(CONF_LOG, CONF_LOG_LEVEL, fallback=default_log_level)
    if log_level.lower() in LogLevel:
        return LogLevel.get(log_level.lower())
    return LogLevel.get(default_log_level)


def read_config_common(config):
    """read config file, get [common] section value"""    
    if not config.has_section(CONF_COMMON):
        report_alarm_fail(f"Cannot find {CONF_COMMON} section in config file")

    try:
        disk_name = config.get(CONF_COMMON, CONF_COMMON_DISK).lower()
        disk = [] if disk_name == "default" else disk_name.split(",")
    except configparser.NoOptionError:
        disk = []
        logging.warning(f"Unset {CONF_COMMON}.{CONF_COMMON_DISK}, set to default")

    try:
        stage_name = config.get(CONF_COMMON, CONF_COMMON_STAGE).lower()
        stage = [] if stage_name == "default" else stage_name.split(",")
    except configparser.NoOptionError:
        stage = []
        logging.warning(f"Unset {CONF_COMMON}.{CONF_COMMON_STAGE}, set to default")

    if len(disk) > 10:
        logging.warning(f"Too many {CONF_COMMON}.disks, record only max 10 disks")
        disk = disk[:10]

    try:
        iotype_name = config.get(CONF_COMMON, CONF_COMMON_IOTYPE).lower().split(",")
        iotype_list = [rw.lower() for rw in iotype_name if rw.lower() in ['read', 'write']]
        err_iotype = [rw.lower() for rw in iotype_name if rw.lower() not in ['read', 'write']]

        if err_iotype:
            report_alarm_fail(f"Invalid {CONF_COMMON}.{CONF_COMMON_IOTYPE} config")

    except configparser.NoOptionError:
        iotype_list = DEFAULT_PARAM[CONF_COMMON][CONF_COMMON_IOTYPE]
        logging.warning(f"Unset {CONF_COMMON}.{CONF_COMMON_IOTYPE}, use {iotupe_list} as default")
    
    try:
        period_time = int(config.get(CONF_COMMON, CONF_COMMON_PER_TIME))
        if not (1 <= period_time <= 300):
            raise ValueError("Invalid period_time")
    except ValueError:
        report_alarm_fail(f"Invalid {CONF_COMMON}.{CONF_COMMON_PER_TIME}")
    except configparser.NoOptionError:
        period_time = DEFAULT_PARAM[CONF_COMMON][CONF_COMMON_PER_TIME]
        logging.warning(f"Unset {CONF_COMMON}.{CONF_COMMON_PER_TIME}, use {period_time} as default")

    return period_time, disk, stage, iotype_list


def read_config_algorithm(config):
    """read config file, get [algorithm] section value"""
    if not config.has_section(CONF_ALGO):
        report_alarm_fail(f"Cannot find {CONF_ALGO} section in config file")

    try:
        win_size = int(config.get(CONF_ALGO, CONF_ALGO_SIZE))
        if not (1 <= win_size <= 300):
            raise ValueError(f"Invalid {CONF_ALGO}.{CONF_ALGO_SIZE}")
    except ValueError:
        report_alarm_fail(f"Invalid {CONF_ALGO}.{CONF_ALGO_SIZE} config")
    except configparser.NoOptionError:
        win_size = DEFAULT_PARAM[CONF_ALGO][CONF_ALGO_SIZE]
        logging.warning(f"Unset {CONF_ALGO}.{CONF_ALGO_SIZE}, use {win_size} as default")
    
    try:
        win_threshold_latency = int(config.get(CONF_ALGO, CONF_ALGO_THRE_LATENCY))
        if win_threshold_latency < 1 or win_threshold_latency > 300 or win_threshold_latency > win_size:
            raise ValueError(f"Invalid {CONF_ALGO}.{CONF_ALGO_THRE_LATENCY}")
    except ValueError:
        report_alarm_fail(f"Invalid {CONF_ALGO}.{CONF_ALGO_THRE_LATENCY} config")
    except configparser.NoOptionError:
        win_threshold_latency = DEFAULT_PARAM[CONF_ALGO]['win_threshold_latency']
        logging.warning(f"Unset {CONF_ALGO}.{CONF_ALGO_THRE_LATENCY}, use {win_threshold_latency} as default")

    try:
        win_threshold_iodump = int(config.get(CONF_ALGO, CONF_ALGO_THRE_IODUMP))
        if win_threshold_iodump < 1 or win_threshold_iodump > 300 or win_threshold_iodump > win_size:
            raise ValueError(f"Invalid {CONF_ALGO}.{CONF_ALGO_THRE_IODUMP}")
    except ValueError:
        report_alarm_fail(f"Invalid {CONF_ALGO}.{CONF_ALGO_THRE_IODUMP} config")
    except configparser.NoOptionError:
        win_threshold_iodump = DEFAULT_PARAM[CONF_ALGO][CONF_ALGO_THRE_IODUMP]
        logging.warning(f"Unset {CONF_ALGO}.{CONF_ALGO_THRE_IODUMP}, use {win_threshold_iodump} as default")

    return win_size, win_threshold_latency, win_threshold_iodump


def read_config_latency(config):
    """read config file, get [latency_xxx] section value"""
    common_param = {}
    for type_name in Disk_Type:
        section_name = CONF_LATENCY.format(Disk_Type[type_name])
        if not config.has_section(section_name):
            report_alarm_fail(f"Cannot find {section_name} section in config file")

        common_param[Disk_Type[type_name]] = get_section_value(section_name, config)
    return common_param


def read_config_iodump(config):
    """read config file, get [iodump] section value"""
    if not config.has_section(CONF_IODUMP):
        report_alarm_fail(f"Cannot find {CONF_IODUMP} section in config file")

    return get_section_value(CONF_IODUMP, config) 


def read_config_stage(config, stage, iotype_list, curr_disk_type):
    """read config file, get [STAGE_NAME_diskType] section value"""
    res = {}
    section_name = f"{stage}_{curr_disk_type}"
    if not config.has_section(section_name):
        return res

    for key in config[section_name]:
        if config[stage][key].isdecimal():
            res[key] = int(config[stage][key])

    return res
