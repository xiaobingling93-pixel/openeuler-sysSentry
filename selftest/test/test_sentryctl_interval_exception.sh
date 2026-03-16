#!/bin/bash
# Copyright (c), 2023-2024, Huawei Tech. Co., Ltd.

source "libs/expect.sh"
source "libs/lib.sh"
source "libs/common.sh"
set +e

tmp_log="tmp_log"
start_line=0

# 测试异常的时间间隔的巡检任务

function pre_test() {
    start_line=$(expr $(wc -l < /var/log/sysSentry/sysSentry.log) + 1)
    common_pre_test "test_task" "pkill test_task" "period" -1 3600 "test_interval_exception"
}

function do_test() {
    #systemctl start sysSentry
    #expect_eq $? 0

    end_line=$(wc -l < /var/log/sysSentry/sysSentry.log)
    sed -n "${start_line}, ${end_line}p" /var/log/sysSentry/sysSentry.log > ${tmp_log}
    expect_true "grep -E '(period delay is invalid)' ${tmp_log}" || cat ${tmp_log}

    sleep 1
    
    sentryctl status test_interval_exception 2>&1 | tee ${tmp_log} | cat
    expect_true "grep -E '(status: RUNNING)' ${tmp_log}"

    sleep 3

    sentryctl status test_interval_exception 2>&1 | tee ${tmp_log} | cat
    expect_true "grep -E '(status: RUNNING)' ${tmp_log}"

    sentryctl stop test_interval_exception
    expect_eq $? 0

    sleep 1

    sentryctl status test_interval_exception 2>&1 | tee ${tmp_log} | cat
    expect_true "grep -E '(status: FAILED)' ${tmp_log}"

}

function post_test() {
	systemctl stop sysSentry.socket sysSentry.service
    systemctl stop xalarmd.socket xalarmd.service
    kill -9 `pgrep -w test_task`
   rm -rf ${tmp_log} test/sysSentry/test_task 
   rm -rf /usr/bin/test_task /etc/sysSentry/tasks/test_interval_exception.mod
}
set -x
run_testcase
