# coding: utf-8
# Copyright (c) 2025 Huawei Technologies Co., Ltd.
# sysSentry is licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#     http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
# PURPOSE.
# See the Mulan PSL v2 for more details.

"""
Get disk latency distribution data.
"""
import struct
import logging
from typing import List, Optional, Dict, Any
from .collect_plugin import get_disk_type
from syssentry.utils import execute_command


class CollectDisk:
    """
    硬盘时延分布数据采集,目前仅支持华为V6和V7代nvme盘,且接口协议版本应为1,带内查询接口如下:
    nvme get-log -i  0xC2 -l 784 /dev/[nvme_disk]
    正常调用时，响应格式为：
    Device:nvme0n1 log-id:xxx namespace-id:xxx
          0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
    0000 01 00 00 00 00 00 00 00 72 00 00 00 18 00 00 00
    0010 53 3e 00 00 b7 c9 00 00 fc 0c 01 00 42 f9 02 00
    0020 b6 fe 03 00 95 04 04 00 14 05 04 00 38 f2 03 00
    ...
    0300 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
    响应部分各字段含义如下:
    Byte    类型       描述
    03:00   version   major version
    07:04   version   minor version
    135:08  读时延分布 时延为0-1ms的读命令个数,每32us一个档位,共32个档位,共128bytes,每个档位统计占用4byte
    259:136 读时延分布 时延为1-32ms的读命令个数,每1ms一个档位,共31个档位,共124bytes,每个档位统计占用4byte
    379:260 读时延分布 时延为32ms-1s的读命令个数,每32ms一个档位,共30个档位,共120bytes,每个档位统计占用4byte
    383:380 读时延分布 时延为1-2s的读命令个数,只有一个档位,统计个数占用4byte
    387:384 读时延分布 时延为2-3s的读命令个数,只有一个档位,统计个数占用4byte
    391:388 读时延分布 时延为3-4s的读命令个数,只有一个档位,统计个数占用4byte
    395:392 读时延分布 时延为大于4s的读命令个数,只有一个档位,统计个数占用4byte
    523:296 写时延分布 时延为0-1ms的写命令个数,每32us一个档位,共32个档位,共128bytes,每个档位统计占用4byte
    647:523 写时延分布 时延为1-32ms的写命令个数,每1ms一个档位,共31个档位,共124bytes,每个档位统计占用4byte
    767:648 写时延分布 时延为32ms-1s的写命令个数,每32ms一个档位,共30个档位,共120bytes,每个档位统计占用4byte
    771:768 写时延分布 时延为1-2s的写命令个数,只有一个档位,统计个数占用4byte
    775:772 写时延分布 时延为2-3s的写命令个数,只有一个档位,统计个数占用4byte
    779:776 写时延分布 时延为3-4s的写命令个数,只有一个档位,统计个数占用4byte
    783:780 写时延分布 时延为大于4s的写命令个数,只有一个档位,统计个数占用4byte
    最终返回的数据会合并一下,一共12个数据,分别为0-1ms,1-10ms,10-100ms,100-1s,1-3s,大于3s这6个档位的读写时延
    """

    def __init__(self, disk_name: str):
        self.disk_name = disk_name
        self.is_support = False
        self._check_support()

    def get_support_flag(self) -> bool:
        return self.is_support

    def collect_data(self) -> List[int]:
        if not self.is_support:
            logging.error(f"Disk {self.disk_name} is not supported for latency collection.")
            return []

        try:
            cmd = ["nvme", "get-log", "-i", "0xC2", "-l", "784", f"/dev/{self.disk_name}"]
            output = execute_command(cmd)
            if not output:
                logging.error(f"Failed to get NVMe log for disk {self.disk_name}.")
                return []

            result = self._parse_nvme_output(output)
            return result
        except Exception as e:
            logging.error(f"Error collecting latency data for disk {self.disk_name}: {e}")
        return []

    def _check_support(self):
        try:
            disk_type_result = get_disk_type(self.disk_name)
            if disk_type_result["ret"] != 0 or disk_type_result["message"] != '0':
                logging.warning(f"Disk {self.disk_name} type is not supported.")
                return

            if not self._check_disk_model():
                logging.warning(f"Disk {self.disk_name} model is not supported.")
                return

            if not self._check_nvme_version():
                logging.warning(f"Disk {self.disk_name} NVMe version is not supported.")
                return

            self.is_support = True
            logging.info(f"Disk {self.disk_name} is supported for latency collection.")
        except Exception as e:
            logging.error(f"Error checking disk {self.disk_name} support: {e}")

    def _check_disk_model(self) -> bool:
        cmd = ["lsblk", "-o", "name,model"]
        try:
            output = execute_command(cmd)
            if not output:
                logging.error(f"Failed to get disk model.")
                return False

            for line in output.splitlines():
                if self.disk_name in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        model = parts[-1]
                        if model.startswith("HWE6") or model.startswith("HWE7"):
                            return True
        except Exception as e:
            logging.error(f"Error checking disk model for {self.disk_name}: {e}")
        return False

    def _check_nvme_version(self) -> bool:
        try:
            cmd = ["nvme", "get-log", "-i", "0xC2", "-l", "784", f"/dev/{self.disk_name}"]
            output = execute_command(cmd)
            if not output:
                logging.error(f"Failed to get NVMe log for disk {self.disk_name}.")
                return False

            lines = output.splitlines()
            line = lines[2]
            parts = line.split()
            hex_data = []
            if len(parts) < 17:
                return False
            for hex_byte in parts[1:9]:
                hex_data.append(hex_byte)

            data = bytes.fromhex(''.join(hex_data))
            if len(data) < 8:
                return False

            major_version = struct.unpack('<I', data[0:4])[0]
            minor_version = struct.unpack('<I', data[4:8])[0]
            if major_version != 1 or minor_version != 0:
                logging.warning(f"Disk {self.disk_name} NVMe log version is {major_version}.{minor_version}, expected 1.0.")
                return False
            return True
        except Exception as e:
            logging.error(f"Error checking NVMe version for {self.disk_name}: {e}")
        return False

    def _parse_nvme_output(self, output: str) -> List[int]:
        lines = output.splitlines()
        hex_data = []

        for line in lines[2:]:
            parts = line.split()
            for hex_byte in parts[1:17]:
                hex_data.append(hex_byte)

        data = bytes.fromhex(''.join(hex_data))
        if len(data) < 784:
            logging.error(f"NVMe log data for disk {self.disk_name} is incomplete.")
            return []

        result = [0] * 12  # 6 read + 6 write latency buckets
        for i in range(32):
            offset = 8 + i * 4
            count = struct.unpack('<I', data[offset:offset+4])[0]
            result[0] += count
        for i in range(9):
            offset = 136 + i * 4
            count = struct.unpack('<I', data[offset:offset+4])[0]
            result[1] += count
        for i in range(9, 31):
            offset = 136 + i * 4
            count = struct.unpack('<I', data[offset:offset+4])[0]
            result[2] += count
        for i in range(3):
            offset = 260 + i * 4
            count = struct.unpack('<I', data[offset:offset+4])[0]
            result[2] += count
        for i in range(3, 30):
            offset = 260 + i * 4
            count = struct.unpack('<I', data[offset:offset+4])[0]
            result[3] += count
        result[4] += struct.unpack('<I', data[380:384])[0]
        result[4] += struct.unpack('<I', data[384:388])[0]
        result[5] += struct.unpack('<I', data[388:392])[0]
        result[5] += struct.unpack('<I', data[392:396])[0]

        for i in range(32):
            offset = 396 + i * 4
            count = struct.unpack('<I', data[offset:offset+4])[0]
            result[6] += count
        for i in range(9):
            offset = 524 + i * 4
            count = struct.unpack('<I', data[offset:offset+4])[0]
            result[7] += count
        for i in range(9, 31):
            offset = 524 + i * 4
            count = struct.unpack('<I', data[offset:offset+4])[0]
            result[8] += count
        for i in range(3):
            offset = 648 + i * 4
            count = struct.unpack('<I', data[offset:offset+4])[0]
            result[8] += count
        for i in range(3, 30):
            offset = 648 + i * 4
            count = struct.unpack('<I', data[offset:offset+4])[0]
            result[9] += count
        result[10] += struct.unpack('<I', data[768:772])[0]
        result[10] += struct.unpack('<I', data[772:776])[0]
        result[11] += struct.unpack('<I', data[776:780])[0]
        result[11] += struct.unpack('<I', data[780:784])[0]
        return result