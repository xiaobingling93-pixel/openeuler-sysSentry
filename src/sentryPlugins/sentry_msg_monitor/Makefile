# Copyright (c) 2025 Huawei Technologies Co., Ltd.
# sysSentry is licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#      http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
# PURPOSE.
# See the Mulan PSL v2 for more details.

# Description: build file for sentry_msg_monitor
# Author: Luckky
# Create: 2025-02-18

ARCH := $(shell uname -m)

ifneq ($(ARCH), aarch64)
UNSUPPORTED_TARGETS := all install clean distclean uninstall
$(UNSUPPORTED_TARGETS):
	@echo "sentry_msg_monitor only supports aarch64 architecture (current: $(ARCH))"
	@exit 0
.DEFAULT_GOAL := all
else
all: sentry_msg_monitor

sentry_msg_monitor:
	gcc sentry_msg_monitor.c ub_fault_lib.c bmc_log_lib.c -fstack-protector-strong -Wall -D_FORTIFY_SOURCE=2 -O2 -g -Wl,-z,relro -Wl,-z,now -fPIE -pie -I../../libsentry/c/log -L../../libsentry/c/log/build -I../../libs/libxalarm -L../../libs/build/libxalarm -lobmm -lxalarm -lsentry_log -ljson-c -pthread -o sentry_msg_monitor

clean:
	rm -f sentry_msg_monitor
endif

.PHONY: all clean
