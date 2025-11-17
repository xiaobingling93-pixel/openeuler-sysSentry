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

class AbnormalWindowBase:
    def __init__(self, window_size=10, window_threshold=7):
        self.window_size = window_size
        self.window_threshold = window_threshold
        self.abnormal_window = [False] * window_size
        self.window_data = [-1] * window_size

    def append_new_data(self, ab_res):
        self.window_data.pop(0)
        self.window_data.append(ab_res)

    def append_new_period(self, ab_res, avg_val=0):
        self.abnormal_window.pop(0)
        if self.is_abnormal_period(ab_res, avg_val):
            self.abnormal_window.append(True)
        else:
            self.abnormal_window.append(False)

    def is_abnormal_window(self):
        return sum(self.abnormal_window) >= self.window_threshold

    def window_data_to_string(self):
        return ",".join(str(x) for x in self.window_data)


class IoWindow(AbnormalWindowBase):
    def __init__(self, window_size=10, window_threshold=7, abnormal_multiple=5, abnormal_multiple_lim=30, abnormal_time=40):
        super().__init__(window_size, window_threshold)
        self.abnormal_multiple = abnormal_multiple
        self.abnormal_multiple_lim = abnormal_multiple_lim
        self.abnormal_time = abnormal_time

    def is_abnormal_period(self, value, avg_val):
        return (value > avg_val * self.abnormal_multiple and value > self.abnormal_multiple_lim) or \
               (value > self.abnormal_time)


class IoDumpWindow(AbnormalWindowBase):
    def __init__(self, window_size=10, window_threshold=7, abnormal_time=40):
        super().__init__(window_size, window_threshold)
        self.abnormal_time = abnormal_time

    def is_abnormal_period(self, value, avg_val=0):
        return value > self.abnormal_time


class IopsWindow(AbnormalWindowBase):
    def is_abnormal_period(self, value, avg_val=10):
        return False


class IoArrayDataWindow:
    def __init__(self, window_size=10):
        self.window_size = window_size
        self.window_data = [[] for _ in range(window_size)]

    def append_new_data(self, msg):
        self.window_data.pop(0)
        self.window_data.append(msg)

    def window_data_to_string(self):
        return str(self.window_data)