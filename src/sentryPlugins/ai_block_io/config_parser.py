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

import os
import configparser
import logging

from .alarm_report import Report
from .threshold import ThresholdType
from .utils import get_threshold_type_enum, get_sliding_window_type_enum, get_log_level
from .data_access import check_detect_frequency_is_valid
from .extra_logger import init_extra_logger


LOG_FORMAT = "%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
AI_EXTRA_LOG_PATH = "/var/log/sysSentry/ai_block_io_extra.log"

ALL_STAGE_LIST = [
    "throtl",
    "wbt",
    "gettag",
    "plug",
    "deadline",
    "hctx",
    "requeue",
    "rq_driver",
    "bio",
]
EBPF_STAGE_LIST = [
    "wbt",
    "rq_driver",
    "bio",
    "gettag"
]
ALL_IOTPYE_LIST = ["read", "write"]
DISK_TYPE_MAP = {
    0: "nvme_ssd",
    1: "sata_ssd",
    2: "sata_hdd",
}


def init_log_format(log_level: str):
    logging.basicConfig(level=get_log_level(log_level.lower()), format=LOG_FORMAT)
    if log_level.lower() not in ("info", "warning", "error", "debug"):
        logging.warning(
            "the log_level: %s you set is invalid, use default value: info.", log_level
        )
    init_extra_logger(AI_EXTRA_LOG_PATH, get_log_level(log_level.lower()), LOG_FORMAT)


class ConfigParser:
    DEFAULT_CONF = {
        "log": {"level": "info"},
        "common": {
            "period_time": 1,
            "disk": None,
            "stage": "throtl,wbt,gettag,plug,deadline,hctx,requeue,rq_driver,bio",
            "iotype": "read,write",
        },
        "algorithm": {
            "train_data_duration": 24.0,
            "train_update_duration": 2.0,
            "algorithm_type": get_threshold_type_enum("boxplot"),
            "boxplot_parameter": 1.5,
            "n_sigma_parameter": 3.0,
            "win_type": get_sliding_window_type_enum("not_continuous"),
            "win_size": 30,
            "win_threshold_latency": 6,
            "win_threshold_iodump": 3,
        },
        "latency_sata_ssd": {
            "read_avg_lim": 10000,
            "write_avg_lim": 10000,
            "read_tot_lim": 50000,
            "write_tot_lim": 50000
        },
        "latency_nvme_ssd": {
            "read_avg_lim": 10000,
            "write_avg_lim": 10000,
            "read_tot_lim": 50000,
            "write_tot_lim": 50000
        },
        "latency_sata_hdd": {
            "read_avg_lim": 15000,
            "write_avg_lim": 15000,
            "read_tot_lim": 50000,
            "write_tot_lim": 50000
        },
        "iodump": {
            "read_iodump_lim": 0,
            "write_iodump_lim": 0
        }
    }

    def __init__(self, config_file_name):
        self._conf = ConfigParser.DEFAULT_CONF
        self._config_file_name = config_file_name

    def _get_config_value(
        self,
        config_items: dict,
        key: str,
        value_type,
        default_value=None,
        gt=None,
        ge=None,
        lt=None,
        le=None,
        section=None
    ):
        if section is not None:
            print_key = section + "." + key
        else:
            print_key = key
        value = config_items.get(key)
        if value is None:
            logging.warning(
                "config of %s not found, the default value %s will be used.",
                print_key,
                default_value,
            )
            value = default_value
        if not value:
            logging.critical(
                "the value of %s is empty, ai_block_io plug will exit.", print_key
            )
            Report.report_pass(
                f"the value of {print_key} is empty, ai_block_io plug will exit."
            )
            exit(1)
        try:
            value = value_type(value)
        except ValueError:
            logging.critical(
                "the value of %s is not a valid %s, ai_block_io plug will exit.",
                print_key,
                value_type,
            )
            Report.report_pass(
                f"the value of {print_key} is not a valid {value_type}, ai_block_io plug will exit."
            )
            exit(1)
        if gt is not None and value <= gt:
            logging.critical(
                "the value of %s is not greater than %s, ai_block_io plug will exit.",
                print_key,
                gt,
            )
            Report.report_pass(
                f"the value of {print_key} is not greater than {gt}, ai_block_io plug will exit."
            )
            exit(1)
        if ge is not None and value < ge:
            logging.critical(
                "the value of %s is not greater than or equal to %s, ai_block_io plug will exit.",
                print_key,
                ge,
            )
            Report.report_pass(
                f"the value of {print_key} is not greater than or equal to {ge}, ai_block_io plug will exit."
            )
            exit(1)
        if lt is not None and value >= lt:
            logging.critical(
                "the value of %s is not less than %s, ai_block_io plug will exit.",
                print_key,
                lt,
            )
            Report.report_pass(
                f"the value of {print_key} is not less than {lt}, ai_block_io plug will exit."
            )
            exit(1)
        if le is not None and value > le:
            logging.critical(
                "the value of %s is not less than or equal to %s, ai_block_io plug will exit.",
                print_key,
                le,
            )
            Report.report_pass(
                f"the value of {print_key} is not less than or equal to {le}, ai_block_io plug will exit."
            )
            exit(1)

        return value

    def _read_period_time(self, items_common: dict):
        self._conf["common"]["period_time"] = self._get_config_value(
            items_common,
            "period_time",
            int,
            self.DEFAULT_CONF["common"]["period_time"],
            gt=0
        )
        frequency = self._conf["common"]["period_time"]
        ret = check_detect_frequency_is_valid(frequency)
        if ret is None:
            log = f"period_time: {frequency} is invalid, "\
                  f"Check whether the value range is too large or is not an "\
                  f"integer multiple of period_time.. exiting..."
            Report.report_pass(log)
            logging.critical(log)
            exit(1)

    def _read_disks_to_detect(self, items_common: dict):
        disks_to_detection = items_common.get("disk")
        if disks_to_detection is None:
            logging.warning("config of disk not found, the default value will be used.")
            self._conf["common"]["disk"] = None
            return
        disks_to_detection = disks_to_detection.strip()
        disks_to_detection = disks_to_detection.lower()
        if not disks_to_detection:
            logging.critical("the value of disk is empty, ai_block_io plug will exit.")
            Report.report_pass(
                "the value of disk is empty, ai_block_io plug will exit."
            )
            exit(1)
        disk_list = disks_to_detection.split(",")
        disk_list = [disk.strip() for disk in disk_list]
        if len(disk_list) == 1 and disk_list[0] == "default":
            self._conf["common"]["disk"] = None
            return
        if len(disk_list) > 10:
            ten_disk_list = disk_list[0:10]
            other_disk_list = disk_list[10:]
            logging.warning(f"disk only support maximum is 10, disks: {ten_disk_list} will be retained, other: {other_disk_list} will be ignored.")
        else:
            ten_disk_list = disk_list
        set_ten_disk_list = set(ten_disk_list)
        if len(ten_disk_list) > len(set_ten_disk_list):
            tmp = ten_disk_list
            ten_disk_list = list(set_ten_disk_list)
            logging.warning(f"disk exist duplicate, it will be deduplicate, before: {tmp}, after: {ten_disk_list}")
        self._conf["common"]["disk"] = ten_disk_list

    def _read_train_data_duration(self, items_algorithm: dict):
        self._conf["algorithm"]["train_data_duration"] = self._get_config_value(
            items_algorithm,
            "train_data_duration",
            float,
            self.DEFAULT_CONF["algorithm"]["train_data_duration"],
            gt=0,
            le=720,
        )

    def _read_train_update_duration(self, items_algorithm: dict):
        default_train_update_duration = self.DEFAULT_CONF["algorithm"][
            "train_update_duration"
        ]
        if default_train_update_duration > self._conf["algorithm"]["train_data_duration"]:
            default_train_update_duration = (
                self._conf["algorithm"]["train_data_duration"] / 2
            )
        self._conf["algorithm"]["train_update_duration"] = self._get_config_value(
            items_algorithm,
            "train_update_duration",
            float,
            default_train_update_duration,
            gt=0,
            le=self._conf["algorithm"]["train_data_duration"],
        )

    def _read_algorithm_type_and_parameter(self, items_algorithm: dict):
        algorithm_type = items_algorithm.get("algorithm_type")
        if algorithm_type is None:
            default_algorithm_type = self._conf["algorithm"]["algorithm_type"]
            logging.warning(f"algorithm_type not found, it will be set default: {default_algorithm_type}")
        else:
            self._conf["algorithm"]["algorithm_type"] = get_threshold_type_enum(algorithm_type)

        if self._conf["algorithm"]["algorithm_type"] is None:
            logging.critical(
                "the algorithm_type: %s you set is invalid. ai_block_io plug will exit.",
                algorithm_type,
            )
            Report.report_pass(
                f"the algorithm_type: {algorithm_type} you set is invalid. ai_block_io plug will exit."
            )
            exit(1)

        elif self._conf["algorithm"]["algorithm_type"] == ThresholdType.NSigmaThreshold:
            self._conf["algorithm"]["n_sigma_parameter"] = self._get_config_value(
                items_algorithm,
                "n_sigma_parameter",
                float,
                self.DEFAULT_CONF["algorithm"]["n_sigma_parameter"],
                gt=0,
                le=10,
            )
        elif (
            self._conf["algorithm"]["algorithm_type"] == ThresholdType.BoxplotThreshold
        ):
            self._conf["algorithm"]["boxplot_parameter"] = self._get_config_value(
                items_algorithm,
                "boxplot_parameter",
                float,
                self.DEFAULT_CONF["algorithm"]["boxplot_parameter"],
                gt=0,
                le=10,
            )

    def _read_stage(self, items_algorithm: dict):
        stage_str = items_algorithm.get("stage")
        if stage_str is None:
            stage_str = self.DEFAULT_CONF["common"]["stage"]
            logging.warning(f"stage not found, it will be set default: {stage_str}")
        else:
            stage_str = stage_str.strip()

        stage_str = stage_str.lower()
        stage_list = stage_str.split(",")
        stage_list = [stage.strip() for stage in stage_list]
        if len(stage_list) == 1 and stage_list[0] == "":
            logging.critical("stage value not allow is empty, exiting...")
            exit(1)

        # check if kernel or ebpf is supported (code is from collector)
        valid_stage_list = ALL_STAGE_LIST
        base_path = '/sys/kernel/debug/block'
        all_disk = []
        for disk_name in os.listdir(base_path):
            disk_path = os.path.join(base_path, disk_name)
            blk_io_hierarchy_path = os.path.join(disk_path, 'blk_io_hierarchy')

            if not os.path.exists(blk_io_hierarchy_path):
                logging.warning("no blk_io_hierarchy directory found in %s, skipping.", disk_name)
                continue

            for file_name in os.listdir(blk_io_hierarchy_path):
                if file_name == 'stats':
                    all_disk.append(disk_name)
        
        if len(all_disk) == 0:
            logging.debug("no blk_io_hierarchy disk, it is not lock-free collection")
            valid_stage_list = EBPF_STAGE_LIST

        if len(stage_list) == 1 and stage_list[0] == "default":
            logging.warning(
                "stage will enable default value: %s",
                self.DEFAULT_CONF["common"]["stage"],
            )
            self._conf["common"]["stage"] = valid_stage_list
            return

        for stage in stage_list:
            if stage not in valid_stage_list:
                logging.critical(
                    "stage: %s is not valid stage, ai_block_io will exit...", stage
                )
                exit(1)
        dup_stage_list = set(stage_list)
        if "bio" not in dup_stage_list:
            logging.critical("stage must contains bio stage, exiting...")
            exit(1)
        self._conf["common"]["stage"] = dup_stage_list

    def _read_iotype(self, items_algorithm: dict):
        iotype_str = items_algorithm.get("iotype")
        if iotype_str is None:
            iotype_str = self.DEFAULT_CONF["common"]["iotype"]
            logging.warning(f"iotype not found, it will be set default: {iotype_str}")
        else:
            iotype_str = iotype_str.strip()

        iotype_str = iotype_str.lower()
        iotype_list = iotype_str.split(",")
        iotype_list = [iotype.strip() for iotype in iotype_list]
        if len(iotype_list) == 1 and iotype_list[0] == "":
            logging.critical("iotype value not allow is empty, exiting...")
            exit(1)
        if len(iotype_list) == 1 and iotype_list[0] == "default":
            logging.warning(
                "iotype will enable default value: %s",
                self.DEFAULT_CONF["common"]["iotype"],
            )
            self._conf["common"]["iotype"] = ALL_IOTPYE_LIST
            return
        for iotype in iotype_list:
            if iotype not in ALL_IOTPYE_LIST:
                logging.critical(
                    "iotype: %s is not valid iotype, ai_block_io will exit...", iotype
                )
                exit(1)
        dup_iotype_list = set(iotype_list)
        self._conf["common"]["iotype"] = dup_iotype_list

    def _read_sliding_window_type(self, items_sliding_window: dict):
        sliding_window_type = items_sliding_window.get("win_type")

        if sliding_window_type is None:
            default_sliding_window_type = self._conf["algorithm"]["win_type"]
            logging.warning(f"win_type not found, it will be set default: {default_sliding_window_type}")
            return

        sliding_window_type = sliding_window_type.strip()
        if sliding_window_type is not None:
            self._conf["algorithm"]["win_type"] = (
                get_sliding_window_type_enum(sliding_window_type)
            )
        if self._conf["algorithm"]["win_type"] is None:
            logging.critical(
                "the win_type: %s you set is invalid. ai_block_io plug will exit.",
                sliding_window_type,
            )
            Report.report_pass(
                f"the win_type: {sliding_window_type} you set is invalid. ai_block_io plug will exit."
            )
            exit(1)

    def _read_window_size(self, items_sliding_window: dict):
        self._conf["algorithm"]["win_size"] = self._get_config_value(
            items_sliding_window,
            "win_size",
            int,
            self.DEFAULT_CONF["algorithm"]["win_size"],
            gt=0,
            le=300,
        )

    def _read_window_minimum_threshold(self, items_sliding_window: dict):
        default_window_minimum_threshold = self.DEFAULT_CONF["algorithm"]["win_threshold_latency"]
        self._conf["algorithm"]["win_threshold_latency"] = (
            self._get_config_value(
                items_sliding_window,
                "win_threshold_latency",
                int,
                default_window_minimum_threshold,
                gt=0,
                le=self._conf["algorithm"]["win_size"],
            )
        )

    def read_config_from_file(self):
        if not os.path.exists(self._config_file_name):
            init_log_format(self._conf["log"]["level"])
            logging.critical(
                "config file %s not found, ai_block_io plug will exit.",
                self._config_file_name,
            )
            Report.report_pass(
                f"config file {self._config_file_name} not found, ai_block_io plug will exit."
            )
            exit(1)

        con = configparser.ConfigParser()
        try:
            con.read(self._config_file_name, encoding="utf-8")
        except configparser.Error as e:
            init_log_format(self._conf["log"]["level"])
            logging.critical(
                "config file read error: %s, ai_block_io plug will exit.", e
            )
            Report.report_pass(
                f"config file read error: {e}, ai_block_io plug will exit."
            )
            exit(1)

        if con.has_section("log"):
            items_log = dict(con.items("log"))
            # 情况一：没有log，则使用默认值
            # 情况二：有log，值为空或异常，使用默认值
            # 情况三：有log，值正常，则使用该值
            self._conf["log"]["level"] = items_log.get(
                "level", self.DEFAULT_CONF["log"]["level"]
            )
            init_log_format(self._conf["log"]["level"])
        else:
            init_log_format(self._conf["log"]["level"])
            logging.warning(
                "log section parameter not found, it will be set to default value."
            )

        if con.has_section("common"):
            items_common = dict(con.items("common"))

            self._read_period_time(items_common)
            self._read_disks_to_detect(items_common)
            self._read_stage(items_common)
            self._read_iotype(items_common)
        else:
            Report.report_pass("not found common section. exiting...")
            logging.critical("not found common section. exiting...")
            exit(1)

        if con.has_section("algorithm"):
            items_algorithm = dict(con.items("algorithm"))
            self._read_train_data_duration(items_algorithm)
            self._read_train_update_duration(items_algorithm)
            self._read_algorithm_type_and_parameter(items_algorithm)
            self._read_sliding_window_type(items_algorithm)
            self._read_window_size(items_algorithm)
            self._read_window_minimum_threshold(items_algorithm)
            self._read_window_threshold_iodump(items_algorithm)

        if con.has_section("latency_sata_ssd"):
            items_latency_sata_ssd = dict(con.items("latency_sata_ssd"))
            self._conf["latency_sata_ssd"]["read_tot_lim"] = self._get_config_value(
                items_latency_sata_ssd,
                "read_tot_lim",
                int,
                self.DEFAULT_CONF["latency_sata_ssd"]["read_tot_lim"],
                gt=0,
                section="latency_sata_ssd"
            )
            self._conf["latency_sata_ssd"]["write_tot_lim"] = self._get_config_value(
                items_latency_sata_ssd,
                "write_tot_lim",
                int,
                self.DEFAULT_CONF["latency_sata_ssd"]["write_tot_lim"],
                gt=0,
                section="latency_sata_ssd"
            )
            self._conf["latency_sata_ssd"]["read_avg_lim"] = self._get_config_value(
                items_latency_sata_ssd,
                "read_avg_lim",
                int,
                self.DEFAULT_CONF["latency_sata_ssd"]["read_avg_lim"],
                gt=0,
                section="latency_sata_ssd"
            )
            self._conf["latency_sata_ssd"]["write_avg_lim"] = self._get_config_value(
                items_latency_sata_ssd,
                "write_avg_lim",
                int,
                self.DEFAULT_CONF["latency_sata_ssd"]["write_avg_lim"],
                gt=0,
                section="latency_sata_ssd"
            )
            if self._conf["latency_sata_ssd"]["read_avg_lim"] >= self._conf["latency_sata_ssd"]["read_tot_lim"]:
                Report.report_pass("latency_sata_ssd.read_avg_lim must < latency_sata_ssd.read_tot_lim . exiting...")
                logging.critical("latency_sata_ssd.read_avg_lim must < latency_sata_ssd.read_tot_lim . exiting...")
                exit(1)
            if self._conf["latency_sata_ssd"]["write_avg_lim"] >= self._conf["latency_sata_ssd"]["write_tot_lim"]:
                Report.report_pass("latency_sata_ssd.write_avg_lim must < latency_sata_ssd.write_tot_lim . exiting...")
                logging.critical("latency_sata_ssd.read_avg_lim must < latency_sata_ssd.read_tot_lim . exiting...")
                exit(1)
        else:
            Report.report_pass("not found latency_sata_ssd section. exiting...")
            logging.critical("not found latency_sata_ssd section. exiting...")
            exit(1)

        if con.has_section("latency_nvme_ssd"):
            items_latency_nvme_ssd = dict(con.items("latency_nvme_ssd"))
            self._conf["latency_nvme_ssd"]["read_tot_lim"] = self._get_config_value(
                items_latency_nvme_ssd,
                "read_tot_lim",
                int,
                self.DEFAULT_CONF["latency_nvme_ssd"]["read_tot_lim"],
                gt=0,
                section="latency_nvme_ssd"
            )
            self._conf["latency_nvme_ssd"]["write_tot_lim"] = self._get_config_value(
                items_latency_nvme_ssd,
                "write_tot_lim",
                int,
                self.DEFAULT_CONF["latency_nvme_ssd"]["write_tot_lim"],
                gt=0,
                section="latency_nvme_ssd"
            )
            self._conf["latency_nvme_ssd"]["read_avg_lim"] = self._get_config_value(
                items_latency_nvme_ssd,
                "read_avg_lim",
                int,
                self.DEFAULT_CONF["latency_nvme_ssd"]["read_avg_lim"],
                gt=0,
                section="latency_nvme_ssd"
            )
            self._conf["latency_nvme_ssd"]["write_avg_lim"] = self._get_config_value(
                items_latency_nvme_ssd,
                "write_avg_lim",
                int,
                self.DEFAULT_CONF["latency_nvme_ssd"]["write_avg_lim"],
                gt=0,
                section="latency_nvme_ssd"
            )
            if self._conf["latency_nvme_ssd"]["read_avg_lim"] >= self._conf["latency_nvme_ssd"]["read_tot_lim"]:
                Report.report_pass("latency_nvme_ssd.read_avg_lim must < latency_nvme_ssd.read_tot_lim . exiting...")
                logging.critical("latency_nvme_ssd.read_avg_lim must < latency_nvme_ssd.read_tot_lim . exiting...")
                exit(1)
            if self._conf["latency_nvme_ssd"]["write_avg_lim"] >= self._conf["latency_nvme_ssd"]["write_tot_lim"]:
                Report.report_pass("latency_nvme_ssd.write_avg_lim must < latency_nvme_ssd.write_tot_lim . exiting...")
                logging.critical("latency_nvme_ssd.write_avg_lim must < latency_nvme_ssd.write_tot_lim . exiting...")
                exit(1)
        else:
            Report.report_pass("not found latency_nvme_ssd section. exiting...")
            logging.critical("not found latency_nvme_ssd section. exiting...")
            exit(1)

        if con.has_section("latency_sata_hdd"):
            items_latency_sata_hdd = dict(con.items("latency_sata_hdd"))
            self._conf["latency_sata_hdd"]["read_tot_lim"] = self._get_config_value(
                items_latency_sata_hdd,
                "read_tot_lim",
                int,
                self.DEFAULT_CONF["latency_sata_hdd"]["read_tot_lim"],
                gt=0,
                section="latency_sata_hdd"
            )
            self._conf["latency_sata_hdd"]["write_tot_lim"] = self._get_config_value(
                items_latency_sata_hdd,
                "write_tot_lim",
                int,
                self.DEFAULT_CONF["latency_sata_hdd"]["write_tot_lim"],
                gt=0,
                section="latency_sata_hdd"
            )
            self._conf["latency_sata_hdd"]["read_avg_lim"] = self._get_config_value(
                items_latency_sata_hdd,
                "read_avg_lim",
                int,
                self.DEFAULT_CONF["latency_sata_hdd"]["read_avg_lim"],
                gt=0,
                section="latency_sata_hdd"
            )
            self._conf["latency_sata_hdd"]["write_avg_lim"] = self._get_config_value(
                items_latency_sata_hdd,
                "write_avg_lim",
                int,
                self.DEFAULT_CONF["latency_sata_hdd"]["write_avg_lim"],
                gt=0,
                section="latency_sata_hdd"
            )
            if self._conf["latency_sata_hdd"]["read_avg_lim"] >= self._conf["latency_sata_hdd"]["read_tot_lim"]:
                Report.report_pass("latency_sata_hdd.read_avg_lim must < latency_sata_hdd.read_tot_lim . exiting...")
                logging.critical("latency_sata_hdd.read_avg_lim must < latency_sata_hdd.read_tot_lim . exiting...")
                exit(1)
            if self._conf["latency_sata_hdd"]["write_avg_lim"] >= self._conf["latency_sata_hdd"]["write_tot_lim"]:
                Report.report_pass("latency_sata_hdd.write_avg_lim must < latency_sata_hdd.write_tot_lim . exiting...")
                logging.critical("latency_sata_hdd.write_avg_lim must < latency_sata_hdd.write_tot_lim . exiting...")
                exit(1)
        else:
            Report.report_pass("not found latency_sata_hdd section. exiting...")
            logging.critical("not found latency_sata_hdd section. exiting...")
            exit(1)

        if con.has_section("iodump"):
            items_iodump = dict(con.items("iodump"))
            self._conf["iodump"]["read_iodump_lim"] = self._get_config_value(
                items_iodump,
                "read_iodump_lim",
                int,
                self.DEFAULT_CONF["iodump"]["read_iodump_lim"],
                ge=0
            )
            self._conf["iodump"]["write_iodump_lim"] = self._get_config_value(
                items_iodump,
                "write_iodump_lim",
                int,
                self.DEFAULT_CONF["iodump"]["write_iodump_lim"],
                ge=0
            )
        else:
            Report.report_pass("not found iodump section. exiting...")
            logging.critical("not found iodump section. exiting...")
            exit(1)

        self.__print_all_config_value()

    def __repr__(self) -> str:
        return str(self._conf)

    def __str__(self) -> str:
        return str(self._conf)

    def __print_all_config_value(self):
        logging.info("all config is follow:\n %s", self)

    def get_tot_lim(self, disk_type, io_type):
        if io_type == "read":
            return self._conf.get(
                f"latency_{DISK_TYPE_MAP.get(disk_type, '')}", {}
            ).get("read_tot_lim", None)
        elif io_type == "write":
            return self._conf.get(
                f"latency_{DISK_TYPE_MAP.get(disk_type, '')}", {}
            ).get("write_tot_lim", None)
        else:
            return None

    def get_avg_lim(self, disk_type, io_type):
        if io_type == "read":
            return self._conf.get(
                f"latency_{DISK_TYPE_MAP.get(disk_type, '')}", {}
            ).get("read_avg_lim", None)
        elif io_type == "write":
            return self._conf.get(
                f"latency_{DISK_TYPE_MAP.get(disk_type, '')}", {}
            ).get("write_avg_lim", None)
        else:
            return None

    def get_train_data_duration_and_train_update_duration(self):
        return (
            self._conf["algorithm"]["train_data_duration"],
            self._conf["algorithm"]["train_update_duration"],
        )

    def get_window_size_and_window_minimum_threshold(self):
        return (
            self._conf["algorithm"]["win_size"],
            self._conf["algorithm"]["win_threshold_latency"],
            self._conf["algorithm"]["win_threshold_iodump"],
        )

    @property
    def period_time(self):
        return self._conf["common"]["period_time"]

    @property
    def algorithm_type(self):
        return self._conf["algorithm"]["algorithm_type"]

    @property
    def sliding_window_type(self):
        return self._conf["algorithm"]["win_type"]

    @property
    def train_data_duration(self):
        return self._conf["algorithm"]["train_data_duration"]

    @property
    def train_update_duration(self):
        return self._conf["algorithm"]["train_update_duration"]

    @property
    def window_size(self):
        return self._conf["algorithm"]["win_size"]

    @property
    def window_minimum_threshold(self):
        return self._conf["algorithm"]["win_threshold_latency"]

    @property
    def absolute_threshold(self):
        return self._conf["common"]["absolute_threshold"]

    @property
    def log_level(self):
        return self._conf["log"]["level"]

    @property
    def disks_to_detection(self):
        return self._conf["common"]["disk"]

    @property
    def stage(self):
        return self._conf["common"]["stage"]

    @property
    def iotype(self):
        return self._conf["common"]["iotype"]

    @property
    def boxplot_parameter(self):
        return self._conf["algorithm"]["boxplot_parameter"]

    @property
    def n_sigma_parameter(self):
        return self._conf["algorithm"]["n_sigma_parameter"]

    @property
    def read_iodump_lim(self):
        return self._conf["iodump"]["read_iodump_lim"]

    @property
    def write_iodump_lim(self):
        return self._conf["iodump"]["write_iodump_lim"]

    def _read_window_threshold_iodump(self, items_sliding_window: dict):
        default_window_threshold_iodump = self.DEFAULT_CONF["algorithm"]["win_threshold_iodump"]
        self._conf["algorithm"]["win_threshold_iodump"] = (
            self._get_config_value(
                items_sliding_window,
                "win_threshold_iodump",
                int,
                default_window_threshold_iodump,
                gt=0,
                le=self._conf["algorithm"]["win_size"],
            )
        )