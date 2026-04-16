#!/bin/bash
# Copyright (C), 2026, Huawei Tech. Co., Ltd.
# Description: test bmc_ras_sentry plugin alarm info on virtual machine
# 
# Create: 2026-04-16

source "libs/lib.sh"
source "libs/expect.sh"
source "libs/wait.sh"

function pre_test() {
    systemctl restart sysSentry.service
}

function do_test() {

    expect_task_status_eq "bmc_ras_sentry" "RUNNING"

    # ipmitool is not applicable on virtual machine
    output=$(ipmitool 2>&1)
    if echo $output | grep -q "Could not open device at /dev/ipmi"; then
        alarm_info=$(sentryctl get_alarm bmc_ras_sentry)
        expect_str_eq "$alarm_info" "[]"

        alarm_info=$(sentryctl get_alarm bmc_ras_sentry -s 1 -d)
        expect_str_eq "$alarm_info" "[]"

    fi
}

function post_test() {
    systemctl stop xalarmd.service
    systemctl stop sysSentry.service
}

run_testcase
