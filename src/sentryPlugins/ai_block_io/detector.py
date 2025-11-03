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
from datetime import datetime

from .io_data import MetricName
from .threshold import Threshold
from .sliding_window import SlidingWindow, DataWindow
from .utils import get_metric_value_from_io_data_dict_by_metric_name, get_metric_value_from_iodump_data_dict


class Detector:

    def __init__(self, metric_name: MetricName, threshold: Threshold, sliding_window: SlidingWindow):
        self._metric_name = metric_name
        self._threshold = threshold
        # for when threshold update, it can print latest threshold with metric name
        self._threshold.set_metric_name(self._metric_name)
        self._slidingWindow = sliding_window
        self._threshold.attach_observer(self._slidingWindow)
        self._count = None

    @property
    def metric_name(self):
        return self._metric_name

    def get_sliding_window_data(self):
        return self._slidingWindow.get_data()

    def is_slow_io_event(self, io_data_dict_with_disk_name: dict):
        if self._count is None:
            self._count = datetime.now()
        else:
            now_time = datetime.now()
            time_diff = (now_time - self._count).total_seconds()
            if time_diff >= 60:
                logging.info(f"({self._metric_name}) 's latest ai threshold is: {self._threshold.get_threshold()}.")
                self._count = None

        logging.debug(f'enter Detector: {self}')
        metric_value = get_metric_value_from_io_data_dict_by_metric_name(io_data_dict_with_disk_name, self._metric_name)
        if metric_value is None:
            logging.debug('not found metric value, so return None.')
            return (False, False), None, None, None, None
        logging.debug(f'input metric value: {str(metric_value)}')
        self._threshold.push_latest_data_to_queue(metric_value)
        detection_result = self._slidingWindow.is_slow_io_event(metric_value)
        # 检测到慢周期，由Detector负责打印info级别日志
        if detection_result[0][1]:
            ai_threshold = "None" if detection_result[2] is None else round(detection_result[2], 3)
            logging.info(f'[abnormal_period]: disk: {self._metric_name.disk_name}, '
                         f'stage: {self._metric_name.stage_name}, '
                         f'iotype: {self._metric_name.io_access_type_name}, '
                         f'type: {self._metric_name.metric_name}, '
                         f'ai_threshold: {ai_threshold}, '
                         f'curr_val: {metric_value}')
        else:
            logging.debug(f'Detection result: {str(detection_result)}')
        logging.debug(f'exit Detector: {self}')
        return detection_result

    def __repr__(self):
        return (f'disk_name: {self._metric_name.disk_name}, stage_name: {self._metric_name.stage_name},'
                f' io_type_name: {self._metric_name.io_access_type_name},'
                f' metric_name: {self._metric_name.metric_name}, threshold_type: {self._threshold},'
                f' sliding_window_type: {self._slidingWindow}')


class DataDetector:

    def __init__(self, metric_name: MetricName, data_window: DataWindow):
        self._metric_name = metric_name
        self._data_window = data_window

    def __repr__(self):
        return (f'disk_name: {self._metric_name.disk_name}, stage_name: {self._metric_name.stage_name},'
                f' io_type_name: {self._metric_name.io_access_type_name},'
                f' metric_name: {self._metric_name.metric_name}')

    @property
    def metric_name(self):
        return self._metric_name

    def get_data_window_data(self):
        return self._data_window.get_data()

    def push_data(self, iodump_data_dict_with_disk_name: dict):
        logging.debug(f'enter Detector: {self}')
        metric_value = get_metric_value_from_iodump_data_dict(iodump_data_dict_with_disk_name, self._metric_name)
        if metric_value is None:
            logging.debug('not found metric value, so return None.')
            return False
        logging.debug(f'input metric value: {str(metric_value)}')
        self._data_window.push(metric_value)
        return True


def set_to_str(parameter: set):
    ret = ""
    parameter = list(parameter)
    length = len(parameter)
    for i in range(length):
        if i == 0:
            ret += parameter[i]
        else:
            ret += "," + parameter[i]
    return ret


class DiskDetector:

    def __init__(self, disk_name: str):
        self._disk_name = disk_name
        self._detector_list = []
        self._data_detector_list = []

    def __repr__(self):
        msg = f'disk: {self._disk_name}, '
        for detector in self._detector_list:
            msg += f'\n detector: [{detector}]'
        for data_detector in self._data_detector_list:
            msg += f'\n data_detector: [{data_detector}]'
        return msg

    def add_detector(self, detector: Detector):
        self._detector_list.append(detector)

    def add_data_detector(self, data_detector: DataDetector):
        self._data_detector_list.append(data_detector)

    def get_detector_list_window(self):
        latency_wins = {"read": {}, "write": {}}
        iodump_wins = {"read": {}, "write": {}}
        iops_wins = {"read": {}, "write": {}}
        for detector in self._detector_list:
            if detector.metric_name.metric_name == 'latency':
                latency_wins[detector.metric_name.io_access_type_name][detector.metric_name.stage_name] = detector.get_sliding_window_data()
            elif detector.metric_name.metric_name == 'io_dump':
                iodump_wins[detector.metric_name.io_access_type_name][detector.metric_name.stage_name] = detector.get_sliding_window_data()
            elif detector.metric_name.metric_name == 'iops':
                iops_wins[detector.metric_name.io_access_type_name][detector.metric_name.stage_name] =\
                      detector.get_sliding_window_data()
        return latency_wins, iodump_wins, iops_wins

    def get_data_detector_list_window(self):
        iodump_data_wins = {"read": {}, "write": {}}
        for data_detector in self._data_detector_list:
            if data_detector.metric_name.metric_name == 'iodump_data':
                iodump_data_wins[data_detector.metric_name.io_access_type_name][data_detector.metric_name.stage_name] =\
                      data_detector.get_data_window_data()
        return iodump_data_wins

    def is_slow_io_event(self, io_data_dict_with_disk_name: dict):
        diagnosis_info = {"bio": [], "rq_driver": [], "kernel_stack": []}
        for detector in self._detector_list:
            # result返回内容：(是否检测到慢IO，是否检测到慢周期)、窗口、ai阈值、绝对阈值
            # 示例： (False, False), self._io_data_queue, self._ai_threshold, self._abs_threshold
            result = detector.is_slow_io_event(io_data_dict_with_disk_name)
            if result[0][0]:
                if detector.metric_name.stage_name == "bio":
                    diagnosis_info["bio"].append(detector.metric_name)
                elif detector.metric_name.stage_name == "rq_driver":
                    diagnosis_info["rq_driver"].append(detector.metric_name)
                else:
                    diagnosis_info["kernel_stack"].append(detector.metric_name)

        if len(diagnosis_info["bio"]) == 0:
            return False, None, None, None, None, None, None

        driver_name = self._disk_name
        reason = "unknown"
        block_stack = set()
        io_type = set()
        alarm_type = set()

        for key, value in diagnosis_info.items():
            for metric_name in value:
                block_stack.add(metric_name.stage_name)
                io_type.add(metric_name.io_access_type_name)
                alarm_type.add(metric_name.metric_name)

        latency_wins, iodump_wins, iops_wins = self.get_detector_list_window()
        details = {"latency": latency_wins, "iodump": iodump_wins, "iops": iops_wins}

        io_press = {"throtl", "wbt", "iocost", "bfq"}
        driver_slow = {"rq_driver"}
        kernel_slow = {"gettag", "plug", "deadline", "hctx", "requeue"}

        if not io_press.isdisjoint(block_stack):
            reason = "io_press"
        elif not driver_slow.isdisjoint(block_stack):
            reason = "driver_slow"
        elif not kernel_slow.isdisjoint(block_stack):
            reason = "kernel_slow"

        return True, driver_name, reason, set_to_str(block_stack), set_to_str(io_type), set_to_str(alarm_type), details

    def push_data_to_data_detectors(self, iodump_data_dict_with_disk_name: dict):
        for data_detector in self._data_detector_list:
            data_detector.push_data(iodump_data_dict_with_disk_name)
