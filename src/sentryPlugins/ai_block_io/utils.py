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
from dataclasses import asdict


from .threshold import ThresholdType
from .sliding_window import SlidingWindowType
from .io_data import MetricName, IOData


def get_threshold_type_enum(algorithm_type: str):
    if algorithm_type.lower() == "boxplot":
        return ThresholdType.BoxplotThreshold
    if algorithm_type.lower() == "n_sigma":
        return ThresholdType.NSigmaThreshold
    return None


def get_sliding_window_type_enum(sliding_window_type: str):
    if sliding_window_type.lower() == "not_continuous":
        return SlidingWindowType.NotContinuousSlidingWindow
    if sliding_window_type.lower() == "continuous":
        return SlidingWindowType.ContinuousSlidingWindow
    if sliding_window_type.lower() == "median":
        return SlidingWindowType.MedianSlidingWindow
    return None


def get_metric_value_from_io_data_dict_by_metric_name(
    io_data_dict: dict, metric_name: MetricName
):
    try:
        io_data: IOData = io_data_dict[metric_name.disk_name]
        io_stage_data = asdict(io_data)[metric_name.stage_name]
        base_data = io_stage_data[metric_name.io_access_type_name]
        metric_value = base_data[metric_name.metric_name]
        return metric_value
    except KeyError:
        return None


def get_metric_value_from_gen_data_dict(io_gen_data_dict: dict, metric_name: MetricName):
    try:
        io_gen_data = io_gen_data_dict[metric_name.disk_name]
        io_gen_stage_data = asdict(io_gen_data)[metric_name.stage_name]
        base_data = io_gen_stage_data[metric_name.io_access_type_name]
        metric_value = base_data[metric_name.metric_name]
        return metric_value
    except KeyError:
        return None


def get_data_queue_size_and_update_size(
    training_data_duration: float,
    train_update_duration: float,
    slow_io_detect_frequency: int,
):
    data_queue_size = int(training_data_duration * 60 * 60 / slow_io_detect_frequency)
    update_size = int(train_update_duration * 60 * 60 / slow_io_detect_frequency)
    return data_queue_size, update_size


def get_log_level(log_level: str):
    if log_level.lower() == "debug":
        return logging.DEBUG
    elif log_level.lower() == "info":
        return logging.INFO
    elif log_level.lower() == "warning":
        return logging.WARNING
    elif log_level.lower() == "error":
        return logging.ERROR
    elif log_level.lower() == "critical":
        return logging.CRITICAL
    return logging.INFO
