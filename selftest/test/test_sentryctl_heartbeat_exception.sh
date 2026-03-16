#!/bin/bash
# Copyright (c), 2023-2024, Huawei Tech. Co., Ltd.

source "libs/expect.sh"
source "libs/lib.sh"
source "libs/common.sh"
set +e

tmp_log="tmp_log"
start_line=0

# 测试异常的心跳间隔的巡检任务

function pre_test() {
    start_line=$(expr $(wc -l < /var/log/sysSentry/sysSentry.log) + 1)
    common_pre_test "test_task" "pkill test_task" "oneshot" 60 -1 "test_heartbeat_exception"
}

function do_test() {
    #systemctl start sysSentry
    #expect_eq $? 0

    end_line=$(wc -l < /var/log/sysSentry/sysSentry.log)
    sed -n "${start_line}, ${end_line}p" /var/log/sysSentry/sysSentry.log > ${tmp_log}
    expect_true "grep -E '(heartbeat interval -1 is invalid)' ${tmp_log}" || cat ${tmp_log}
    
    sentryctl status test_heartbeat_exception 2>&1 | tee ${tmp_log} | cat
    expect_true "grep -E '(status: EXITED)' ${tmp_log}"

    sleep 1

    sentryctl start test_heartbeat_exception
    expect_eq $? 0

    sentryctl status test_heartbeat_exception 2>&1 | tee ${tmp_log} | cat
    expect_true "grep -E '(status: RUNNING)' ${tmp_log}"

    sleep 12

    sentryctl status test_heartbeat_exception 2>&1 | tee ${tmp_log} | cat
    expect_true "grep -E '(status: EXITED)' ${tmp_log}"

}

function post_test() {
	systemctl stop sysSentry.socket sysSentry.service
    systemctl stop xalarmd.socket xalarmd.service
    kill -9 `pgrep -w test_task`
   rm -rf ${tmp_log} test/sysSentry/test_task 
   rm -rf /usr/bin/test_task /etc/sysSentry/tasks/test_heartbeat_exception.mod
}
set -x
run_testcase
