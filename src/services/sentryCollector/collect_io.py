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
collect module
"""
import os
import time
import logging
import threading
import subprocess
import re
from typing import Union

from .collect_config import CollectConfig
from .collect_config import CONF_IO_NVME_SSD, CONF_IO_SATA_SSD, CONF_IO_SATA_HDD, CONF_IO_THRESHOLD_DEFAULT
from .collect_plugin import get_disk_type, DiskType

Io_Category = ["read", "write", "flush", "discard"]
IO_GLOBAL_DATA = {}
IO_CONFIG_DATA = []
IO_DUMP_DATA = {}
EBPF_GLOBAL_DATA = []
EBPF_PROCESS = None
EBPF_STAGE_LIST = ["wbt", "rq_driver", "bio", "gettag"]
EBPF_SUPPORT_VERSION = ["6.6.0"]

#iodump data limit
IO_DUMP_DATA_LIMIT = 10

class IoStatus():
    TOTAL = 0
    FINISH = 1
    LATENCY = 2

class CollectIo():

    def __init__(self, module_config):

        io_config = module_config.get_io_config()

        self.period_time = io_config['period_time']
        self.max_save = io_config['max_save']
        disk_str = io_config['disk']

        self.disk_map_stage = {}
        self.window_value = {}

        self.ebpf_base_path = 'ebpf_collector'

        self.loop_all = False
        self.io_threshold_config = module_config.get_io_threshold()

        if disk_str == "default":
            self.loop_all = True
        else:
            self.disk_list = disk_str.strip().split(',')

        self.stop_event = threading.Event()
        self.iodump_pattern = re.compile(
            r'(?P<task_name>[^-]+)-(?P<pid>\d+)\s+'
            r'\w+\s+'
            r'stage\s+(?P<stage>\w+)\s+'
            r'(?P<ptr>[0-9a-fA-F]{16})\s+'
            r'.*started\s+(?P<start_time_ns>\d+)\s+ns\s+ago'
        )

        IO_CONFIG_DATA.append(self.period_time)
        IO_CONFIG_DATA.append(self.max_save)

    def update_io_threshold(self, disk_name, stage_list):
        disk_type_result = get_disk_type(disk_name)
        if disk_type_result["ret"] == 0 and disk_type_result["message"] in ('0', '1', '2'):
            disk_type = int(disk_type_result["message"])
            if disk_type == DiskType.TYPE_NVME_SSD:
                config_threshold = str(self.io_threshold_config[CONF_IO_NVME_SSD])
            elif disk_type == DiskType.TYPE_SATA_SSD:
                config_threshold = str(self.io_threshold_config[CONF_IO_SATA_SSD])
            elif disk_type == DiskType.TYPE_SATA_HDD:
                config_threshold = str(self.io_threshold_config[CONF_IO_SATA_HDD])
            else:
                return

            for stage in stage_list:
                io_threshold_file = '/sys/kernel/debug/block/{}/blk_io_hierarchy/{}/threshold'.format(disk_name, stage)
                try:
                    with open(io_threshold_file, 'r') as file:
                        current_threshold = file.read().strip()
                except FileNotFoundError:
                    logging.error("The file %s does not exist.", io_threshold_file)
                    continue
                except Exception as e:
                    logging.error("An error occurred while reading: %s", e)
                    continue

                if current_threshold != config_threshold:
                    try:
                        with open(io_threshold_file, 'w') as file:
                            file.write(config_threshold)
                        logging.info("update %s io_dump_threshold from %s to %s",
                                      io_threshold_file, current_threshold, config_threshold)
                    except Exception as e:
                        logging.error("An error occurred while writing: %s", e)

    def get_blk_io_hierarchy(self, disk_name, stage_list):
        stats_file = '/sys/kernel/debug/block/{}/blk_io_hierarchy/stats'.format(disk_name)
        try:
            with open(stats_file, 'r') as file:
                lines = file.read()
        except FileNotFoundError:
            logging.error("The file %s does not exist", stats_file)
            return -1
        except Exception as e:
            logging.error("An error occurred: %s", e)
            return -1

        curr_value = lines.strip().split('\n')

        for stage_val in curr_value:
            stage = stage_val.split(' ')[0]
            if (len(self.window_value[disk_name][stage])) >= 2:
                self.window_value[disk_name][stage].pop(0)

            curr_stage_value = stage_val.split(' ')[1:-1]
            self.window_value[disk_name][stage].append(curr_stage_value)
        return 0

    def append_period_lat(self, disk_name, stage_list):
        for stage in stage_list:
            if len(self.window_value[disk_name][stage]) < 2:
                return
            curr_stage_value = self.window_value[disk_name][stage][-1]
            last_stage_value = self.window_value[disk_name][stage][-2]

            for index in range(len(Io_Category)):
                # read=0, write=1, flush=2, discard=3
                if (len(IO_GLOBAL_DATA[disk_name][stage][Io_Category[index]])) >= self.max_save:
                    IO_GLOBAL_DATA[disk_name][stage][Io_Category[index]].pop()
                if (len(IO_DUMP_DATA[disk_name][stage][Io_Category[index]])) >= self.max_save:
                    IO_DUMP_DATA[disk_name][stage][Io_Category[index]].pop()

                curr_lat = self.get_latency_value(curr_stage_value, last_stage_value, index)
                curr_iops = self.get_iops(curr_stage_value, last_stage_value, index)
                curr_io_length = self.get_io_length(curr_stage_value, last_stage_value, index)
                curr_io_dump = self.get_io_dump(disk_name, stage, index)

                IO_GLOBAL_DATA[disk_name][stage][Io_Category[index]].insert(0, [curr_lat, curr_io_dump, curr_io_length, curr_iops])
                if curr_io_dump == 0:
                    IO_DUMP_DATA[disk_name][stage][Io_Category[index]].insert(0, [])

    def get_iops(self, curr_stage_value, last_stage_value, category):
        try:
            finish = int(curr_stage_value[category * 3 + IoStatus.FINISH]) - int(last_stage_value[category * 3 + IoStatus.FINISH])
        except ValueError as e:
            logging.error("get_iops convert to int failed, %s", e)
            return 0
        value = finish / self.period_time
        if value.is_integer():
            return int(value)
        else:
            return round(value, 1)

    def get_latency_value(self, curr_stage_value, last_stage_value, category):
        try:
            finish = int(curr_stage_value[category * 3 + IoStatus.FINISH]) - int(last_stage_value[category * 3 + IoStatus.FINISH])
            lat_time = (int(curr_stage_value[category * 3 + IoStatus.LATENCY]) - int(last_stage_value[category * 3 + IoStatus.LATENCY]))
        except ValueError as e:
            logging.error("get_latency_value convert to int failed, %s", e)
            return 0
        if finish <= 0 or lat_time <= 0:
            return 0
        value = lat_time / finish / 1000
        if value.is_integer():
            return int(value)
        else:
            return round(value, 1)

    def get_io_length(self, curr_stage_value, last_stage_value, category):
        try:
            lat_time = (int(curr_stage_value[category * 3 + IoStatus.LATENCY]) - int(last_stage_value[category * 3 + IoStatus.LATENCY]))
        except ValueError as e:
            logging.error("get_io_length convert to int failed, %s", e)
            return 0
        if lat_time <= 0:
            return 0
        # ns convert us
        lat_time = lat_time / 1000
        # s convert us
        period_time = self.period_time * 1000 * 1000
        value = lat_time / period_time
        if value.is_integer():
            return int(value)
        else:
            return round(value, 1)

    def get_io_dump(self, disk_name, stage, category):
        io_dump_file = '/sys/kernel/debug/block/{}/blk_io_hierarchy/{}/io_dump'.format(disk_name, stage)
        count = 0
        io_dump_msg = []
        pattern = self.iodump_pattern

        try:
            with open(io_dump_file, 'r') as file:
                for line in file:
                    if line.count('.op=' + Io_Category[category].upper()) > 0:
                        match = pattern.match(line)
                        if match:
                            if count < IO_DUMP_DATA_LIMIT:
                                parsed = match.groupdict()
                                values = [
                                    parsed["task_name"],
                                    parsed["pid"],
                                    parsed["stage"],
                                    parsed["ptr"],
                                    str(int(parsed["start_time_ns"]) // 1000000)
                                ]
                                value_str = ",".join(values)
                                io_dump_msg.append(value_str)
                        else:
                            logging.info(f"io_dump parse err, info : {line.strip()}")
                        count += 1
                if count > 0:
                    IO_DUMP_DATA[disk_name][stage][Io_Category[category]].insert(0, io_dump_msg)
                    logging.info(f"io_dump info : {disk_name}, {stage}, {Io_Category[category]}, {count}")
        except FileNotFoundError:
            logging.error("The file %s does not exist.", io_dump_file)
            return count
        except Exception as e:
            logging.error("An error occurred1: %s", e)
            return count
        return count

    def extract_first_column(self, file_path):
        column_names = [] 
        try:
            with open(file_path, 'r') as file:
                for line in file:
                    parts = line.strip().split()
                    if parts:
                        column_names.append(parts[0])
        except FileNotFoundError:
            logging.error("The file %s does not exist.", file_path)
        except Exception as e:
            logging.error("An error occurred2: %s", e)
        return column_names

    def is_kernel_avaliable(self):
        base_path = '/sys/kernel/debug/block'
        all_disk = []
        for disk_name in os.listdir(base_path):
            disk_path = os.path.join(base_path, disk_name)
            blk_io_hierarchy_path = os.path.join(disk_path, 'blk_io_hierarchy')

            if not os.path.exists(blk_io_hierarchy_path):
                logging.warning("no blk_io_hierarchy directory found in %s, skipping.", disk_name)
                continue

            for file_name in os.listdir(blk_io_hierarchy_path):
                file_path = os.path.join(blk_io_hierarchy_path, file_name)
                if file_name == 'stats':
                    all_disk.append(disk_name)
        
        if len(all_disk) == 0:
            logging.debug("no blk_io_hierarchy disk, it is not lock-free collection")
            return False

        if self.loop_all:
            self.disk_list = all_disk

        for disk_name in self.disk_list:
            if not self.loop_all and disk_name not in all_disk:
                logging.warning("the %s disk not exist!", disk_name)
                continue
            stats_file = '/sys/kernel/debug/block/{}/blk_io_hierarchy/stats'.format(disk_name)
            stage_list = self.extract_first_column(stats_file)
            self.disk_map_stage[disk_name] = stage_list
            self.window_value[disk_name] = {}
            IO_GLOBAL_DATA[disk_name] = {}
            IO_DUMP_DATA[disk_name] = {}

        return len(IO_GLOBAL_DATA) != 0
    
    def is_ebpf_avaliable(self):
        with open('/proc/version', 'r') as f:
            kernel_version = f.read().split()[2]
            major_version = kernel_version.split('-')[0]
        
        base_path = '/sys/kernel/debug/block'
        for disk_name in os.listdir(base_path):
            if not self.loop_all and disk_name not in self.disk_list:
                continue
            self.disk_map_stage[disk_name] = EBPF_STAGE_LIST
            self.window_value[disk_name] = {}
            IO_GLOBAL_DATA[disk_name] = {}
            IO_DUMP_DATA[disk_name] = {}
        
        for disk_name, stage_list in self.disk_map_stage.items():
            for stage in stage_list:
                self.window_value[disk_name][stage] = {}
                IO_GLOBAL_DATA[disk_name][stage] = {}
                IO_DUMP_DATA[disk_name][stage] = {}
                for category in Io_Category:
                    IO_GLOBAL_DATA[disk_name][stage][category] = []
                    IO_DUMP_DATA[disk_name][stage][category] = []
                    self.window_value[disk_name][stage][category] = [[0,0,0], [0,0,0]]

        return major_version in EBPF_SUPPORT_VERSION and os.path.exists('/usr/bin/ebpf_collector') and len(IO_GLOBAL_DATA) != 0 
    
    def get_ebpf_raw_data(
        self
    ) -> None:
        global EBPF_PROCESS
        global EBPF_GLOBAL_DATA

        while True:
            if self.stop_event.is_set():
                logging.debug("collect io thread exit")
                return
            line = EBPF_PROCESS.stdout.readline()
            if not line:
                logging.info("no ebpf data found, wait for collect")
                break
            EBPF_GLOBAL_DATA.append(line.strip())
            time.sleep(0.1)
    
    def update_ebpf_collector_data(
        self,
    ) -> None:
        global EBPF_GLOBAL_DATA

        while True:
            if self.stop_event.is_set():
                logging.debug("collect io thread exit")
                return
            if EBPF_GLOBAL_DATA:
                for data in EBPF_GLOBAL_DATA:
                    data_list = data.split()
                    if len(data_list) != 6:
                        continue
                    stage, finish_count, latency, io_dump, io_type ,disk_name = data_list
                    if stage not in EBPF_STAGE_LIST:
                        continue
                    if disk_name not in self.window_value:
                        continue
                    io_type = self.get_ebpf_io_type(io_type)
                    if not io_type:
                        continue                  
                    if (len(self.window_value[disk_name][stage][io_type])) >= 2:
                        self.window_value[disk_name][stage][io_type].pop()
                    self.window_value[disk_name][stage][io_type].append([int(finish_count), int(latency), int(io_dump)])
                EBPF_GLOBAL_DATA.clear()
            time.sleep(0.1)
    
    def get_ebpf_io_type(
        self,
        io_type: str
    ) -> str:
        io_type_mapping = {
            "R": "read",
            "W": "write",
            "F": "flush",
            "D": "discard"
        }
        io_type = io_type_mapping.get(io_type, None)
        return io_type
    
    def append_ebpf_period_data(
        self, 
    ) -> None:
        global IO_GLOBAL_DATA
        while True:
            if self.stop_event.is_set():
                logging.debug("collect io thread exit")
                return
            start_time = time.time()
            for disk_name, stage_list in self.disk_map_stage.items():
                for stage in stage_list:
                    for io_type in Io_Category:
                        if len(self.window_value[disk_name][stage][io_type]) < 2:
                            return
                        if (len(IO_GLOBAL_DATA[disk_name][stage][io_type])) >= self.max_save:
                            IO_GLOBAL_DATA[disk_name][stage][io_type].pop()
                        if (len(IO_DUMP_DATA[disk_name][stage][io_type])) >= self.max_save:
                            IO_DUMP_DATA[disk_name][stage][io_type].pop()
                        curr_finish_count, curr_latency, curr_io_dump_count = self.window_value[disk_name][stage][io_type][-1]
                        prev_finish_count, prev_latency, prev_io_dump_count = self.window_value[disk_name][stage][io_type][-2]
                        self.window_value[disk_name][stage][io_type].pop(0)
                        self.window_value[disk_name][stage][io_type].insert(1, self.window_value[disk_name][stage][io_type][0])
                        curr_lat = self.get_ebpf_latency_value(curr_latency=curr_latency, prev_latency=prev_latency, curr_finish_count=curr_finish_count, prev_finish_count=prev_finish_count)
                        curr_iops = self.get_ebpf_iops(curr_finish_count=curr_finish_count, prev_finish_count=prev_finish_count)
                        curr_io_length = self.get_ebpf_io_length(curr_latency=curr_latency, prev_latency=prev_latency)
                        curr_io_dump = self.get_ebpf_io_dump(curr_io_dump_count=curr_io_dump_count, prev_io_dump_count=prev_io_dump_count)
                        if curr_io_dump > 0:
                            logging.info(f"ebpf io_dump info : {disk_name}, {stage}, {io_type}, {curr_io_dump}")
                        IO_GLOBAL_DATA[disk_name][stage][io_type].insert(0, [curr_lat, curr_io_dump, curr_io_length, curr_iops])
                        IO_DUMP_DATA[disk_name][stage][io_type].insert(0, [])

            elapsed_time = time.time() - start_time
            sleep_time = self.period_time - elapsed_time
            if sleep_time < 0:
                continue
            while sleep_time > 1:
                if self.stop_event.is_set():
                    logging.debug("collect io thread exit")
                    return
                time.sleep(1)
                sleep_time -= 1
            time.sleep(sleep_time)
            
    def get_ebpf_latency_value(
        self,
        curr_latency: int,
        prev_latency: int,
        curr_finish_count: int,
        prev_finish_count: int
    ) -> Union[int, float]:
        finish = curr_finish_count - prev_finish_count
        lat_time = curr_latency - prev_latency
        if finish <= 0 or lat_time <= 0:
            return 0
        value = lat_time / finish / 1000
        if value.is_integer():
            return int(value)
        else:
            return round(value, 1)
    
    def get_ebpf_iops(
        self,
        curr_finish_count: int,
        prev_finish_count: int
    ) -> Union[int, float]:
        finish = curr_finish_count - prev_finish_count
        if finish <= 0:
            return 0
        value = finish / self.period_time
        if value.is_integer():
            return int(value)
        else:
            return round(value, 1)
    
    def get_ebpf_io_length(
        self,
        curr_latency: int,
        prev_latency: int,
    ) -> Union[int, float]:
        lat_time = curr_latency - prev_latency
        if lat_time <= 0:
            return 0
        # ns convert us
        lat_time = lat_time / 1000
        # s convert us
        period_time = self.period_time * 1000 * 1000
        value = lat_time / period_time
        if value.is_integer():
            return int(value)
        else:
            return round(value, 1)
    
    def get_ebpf_io_dump(
        self,
        curr_io_dump_count: int,
        prev_io_dump_count: int
    ) -> Union[int, float]:
        io_dump_count = curr_io_dump_count
        if io_dump_count <= 0:
            return 0
        value = io_dump_count
        return int(value)                         
    
    def start_ebpf_subprocess(
        self
    ) -> None:
        global EBPF_PROCESS
        EBPF_PROCESS = subprocess.Popen(self.ebpf_base_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    def stop_ebpf_subprocess(
        self
    ) -> None:
        global EBPF_PROCESS
        if not EBPF_PROCESS:
            logging.debug("No eBPF process to stop")
            return
        try:
            EBPF_PROCESS.terminate()
            EBPF_PROCESS.wait(timeout=3)
        except subprocess.TimeoutExpired:
            logging.debug("eBPF process did not exit within timeout. Forcing kill.")
            EBPF_PROCESS.kill()
            EBPF_PROCESS.wait()
        logging.info("ebpf collector thread exit")

    def main_loop(self):
        global IO_GLOBAL_DATA
        global IO_DUMP_DATA
        logging.info("collect io thread start")
        
        if self.is_kernel_avaliable() and len(self.disk_map_stage) != 0:
            for disk_name, stage_list in self.disk_map_stage.items():
                for stage in stage_list:
                    self.window_value[disk_name][stage] = []
                    IO_GLOBAL_DATA[disk_name][stage] = {}
                    IO_DUMP_DATA[disk_name][stage] = {}
                    for category in Io_Category:
                        IO_GLOBAL_DATA[disk_name][stage][category] = []
                        IO_DUMP_DATA[disk_name][stage][category] = []
                    self.update_io_threshold(disk_name, stage_list)

            while True:
                start_time = time.time()

                if self.stop_event.is_set():
                    logging.debug("collect io thread exit")
                    return

                for disk_name, stage_list in self.disk_map_stage.items():
                    if self.get_blk_io_hierarchy(disk_name, stage_list) < 0:
                        continue
                    self.append_period_lat(disk_name, stage_list)

                elapsed_time = time.time() - start_time
                sleep_time = self.period_time - elapsed_time
                if sleep_time < 0:
                    continue
                while sleep_time > 1:
                    if self.stop_event.is_set():
                        logging.debug("collect io thread exit")
                        return
                    time.sleep(1)
                    sleep_time -= 1
                time.sleep(sleep_time)
        elif self.is_ebpf_avaliable():
            logging.info("ebpf collector thread start")
            self.start_ebpf_subprocess()
            
            thread_get_data = threading.Thread(target=self.get_ebpf_raw_data)
            thread_update_data = threading.Thread(target=self.update_ebpf_collector_data)
            thread_append_data = threading.Thread(target=self.append_ebpf_period_data)
            
            thread_get_data.start()
            thread_update_data.start()
            thread_append_data.start()
            
            thread_get_data.join()
            thread_update_data.join()
            thread_append_data.join()

            self.stop_ebpf_subprocess()
        else:
            logging.warning("fail to start ebpf collector thread. collect io thread exits")
            return

    # set stop event, notify thread exit
    def stop_thread(self):
        self.stop_event.set()
