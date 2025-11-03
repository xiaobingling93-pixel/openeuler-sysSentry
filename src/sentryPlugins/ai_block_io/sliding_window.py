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

from enum import Enum, unique
from typing import Any
import numpy as np


@unique
class SlidingWindowType(Enum):
    NotContinuousSlidingWindow = 0
    ContinuousSlidingWindow = 1
    MedianSlidingWindow = 2


class SlidingWindow:
    def __init__(self, queue_length: int, threshold: int, abs_threshold: int = None, avg_lim: int = None):
        self._queue_length = queue_length
        self._queue_threshold = threshold
        self._ai_threshold = None
        self._abs_threshold = abs_threshold
        self._avg_lim = avg_lim
        self._io_data_queue = []
        self._io_data_queue_abnormal_tag = []

    def is_abnormal(self, data):
        if self._avg_lim is not None and data < self._avg_lim:
            return False
        if self._ai_threshold is not None and data > self._ai_threshold:
            return True
        if self._abs_threshold is not None and data > self._abs_threshold:
            return True
        return False

    def push(self, data: float):
        if len(self._io_data_queue) == self._queue_length:
            self._io_data_queue.pop(0)
            self._io_data_queue_abnormal_tag.pop(0)
        self._io_data_queue.append(data)
        tag = self.is_abnormal(data)
        self._io_data_queue_abnormal_tag.append(tag)
        return tag

    def update(self, threshold):
        if self._ai_threshold == threshold:
            return
        self._ai_threshold = threshold
        self._io_data_queue_abnormal_tag.clear()
        for data in self._io_data_queue:
            self._io_data_queue_abnormal_tag.append(self.is_abnormal(data))

    def is_slow_io_event(self, data):
        return False, None, None, None

    def get_data(self):
        return self._io_data_queue

    def __repr__(self):
        return "[SlidingWindow]"


class NotContinuousSlidingWindow(SlidingWindow):
    def is_slow_io_event(self, data):
        is_abnormal_period = super().push(data)
        is_slow_io_event = False
        if len(self._io_data_queue) < self._queue_length or (self._ai_threshold is None and self._abs_threshold is None):
            is_slow_io_event = False
        if self._io_data_queue_abnormal_tag.count(True) >= self._queue_threshold:
            is_slow_io_event = True
        return (is_slow_io_event, is_abnormal_period), self._io_data_queue, self._ai_threshold, self._abs_threshold, self._avg_lim

    def __repr__(self):
        return f"[NotContinuousSlidingWindow, window size: {self._queue_length}, threshold: {self._queue_threshold}]"


class ContinuousSlidingWindow(SlidingWindow):
    def is_slow_io_event(self, data):
        is_abnormal_period = super().push(data)
        is_slow_io_event = False
        if len(self._io_data_queue) < self._queue_length or (self._ai_threshold is None and self._abs_threshold is None):
            is_slow_io_event = False
        consecutive_count = 0
        for tag in self._io_data_queue_abnormal_tag:
            if tag:
                consecutive_count += 1
                if consecutive_count >= self._queue_threshold:
                    is_slow_io_event = True
                    break
            else:
                consecutive_count = 0
        return (is_slow_io_event, is_abnormal_period), self._io_data_queue, self._ai_threshold, self._abs_threshold, self._avg_lim

    def __repr__(self):
        return f"[ContinuousSlidingWindow, window size: {self._queue_length}, threshold: {self._queue_threshold}]"


class MedianSlidingWindow(SlidingWindow):
    def is_slow_io_event(self, data):
        is_abnormal_period = super().push(data)
        is_slow_io_event = False
        if len(self._io_data_queue) < self._queue_length or (self._ai_threshold is None and self._abs_threshold is None):
            is_slow_io_event = False
        median = np.median(self._io_data_queue)
        if (self._ai_threshold is not None and median > self._ai_threshold) or (self._abs_threshold is not None and median > self._abs_threshold):
            is_slow_io_event = True
        return (is_slow_io_event, is_abnormal_period), self._io_data_queue, self._ai_threshold, self._abs_threshold, self._avg_lim

    def __repr__(self):
        return f"[MedianSlidingWindow, window size: {self._queue_length}]"


class SlidingWindowFactory:
    def get_sliding_window(
        self, sliding_window_type: SlidingWindowType, *args, **kwargs
    ):
        if sliding_window_type == SlidingWindowType.NotContinuousSlidingWindow:
            return NotContinuousSlidingWindow(*args, **kwargs)
        elif sliding_window_type == SlidingWindowType.ContinuousSlidingWindow:
            return ContinuousSlidingWindow(*args, **kwargs)
        elif sliding_window_type == SlidingWindowType.MedianSlidingWindow:
            return MedianSlidingWindow(*args, **kwargs)
        else:
            return NotContinuousSlidingWindow(*args, **kwargs)


class DataWindow:
    def __init__(self, window_size: int):
        self._window_size = window_size
        self._data_queue = []

    def __repr__(self):
        return f"[SingleDataWindow, window size: {self._window_size}]"

    def push(self, data: Any):
        if len(self._data_queue) == self._window_size:
            self._data_queue.pop(0)
        self._data_queue.append(data)

    def get_data(self):
        return self._data_queue