#!/bin/bash
# Copyright (c), 2023-2024, Huawei Tech. Co., Ltd.

source "libs/expect.sh"
source "libs/lib.sh"
source "libs/wait.sh"
source "libs/shopt.sh"
set +e

#验证启动多次xalarmd的场景

function pre_test() {
    rm -f ./tmp_log
    systemctl stop xalarmd.socket xalarmd.service
    sleep 1
}

function do_test() {
    # 验证多次启动的场景
    start_line=$(expr $(wc -l < /var/log/sysSentry/xalarm.log) + 1)
    systemctl start xalarmd.socket
    systemctl start xalarmd.service
    /usr/bin/xalarmd
    end_line=$(wc -l < /var/log/sysSentry/xalarm.log)

    process_num=$(ps -ef | grep xalarmd | grep -v grep | grep -v defunct | wc -l)
    echo "xalarm process num is $process_num" >> ./tmp_log
    expect_eq $process_num 1 "check xalarmd can launch multiple times"

    sed -n "${start_line}, ${end_line}p" /var/log/sysSentry/xalarm.log >> ./tmp_log
    wait_cmd_ok "grep \"get pid file lock failed\" ./tmp_log" 1 3
    expect_eq $? 0 "check xalarmd get pid file lock fail log"

    cat ./tmp_log
}

function post_test() {
    rm -f ./tmp_log
    systemctl stop xalarmd.socket xalarmd.service
    sleep 1
}

run_testcase



