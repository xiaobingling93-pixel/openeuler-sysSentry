# Copyright (c) Huawei Technologies Co., Ltd. 2023-2025. All rights reserved.
# Description: cmake file for log_utils
cmake_minimum_required(VERSION 3.22)
project(sentry_log)
add_library(sentry_log SHARED log_utils.c)
set_target_properties(sentry_log PROPERTIES LINK_FLAGS "-Wl,-z,relro -Wl,-z,now -Wl,-z,noexecstack -Wtrampolines")
set_target_properties(sentry_log PROPERTIES CMAKE_C_FLAGS "-shared -fPIC -fstack-protector-strong -D_FORTIFY_SOURCE=2 -O2 -Wall -Werror -g")
