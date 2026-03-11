#!/bin/bash
# Copyright (c), 2023-2024, Huawei Tech. Co., Ltd.

source "libs/expect.sh"
source "libs/lib.sh"
source "libs/common.sh"
set +e

tmp_log="tmp_log"

# 异常的task_stop命令，在运行时是否报错

function pre_test() {
    common_pre_test "test_task" "aaa" "oneshot" 60 3600 "test_end_exception"
}

function do_test() {
    sentryctl status test_end_exception 2>&1 | tee ${tmp_log}
    expect_true "grep -E '(status: EXITED)' ${tmp_log}"

    sentryctl start test_end_exception
    expect_eq $? 0

    sentryctl status test_end_exception 2>&1 | tee ${tmp_log}
    expect_true "grep -E '(status: RUNNING)' ${tmp_log}"

    start_line=$(expr $(wc -l < /var/log/sysSentry/sysSentry.log) + 1)
    sentryctl stop test_end_exception
    expect_eq $? 0
    end_line=$(wc -l < /var/log/sysSentry/sysSentry.log)
    
    sed -n "${start_line}, ${end_line}p" /var/log/sysSentry/sysSentry.log > ${tmp_log}
    expect_true "grep -E '(stop Popen failed)' ${tmp_log}" || cat ${tmp_log}

    sentryctl status test_end_exception 2>&1 | tee ${tmp_log}
    expect_true "grep -E '(status: RUNNING)' ${tmp_log}"
}

function post_test() {
    systemctl stop sysSentry.socket sysSentry.service
    systemctl stop xalarmd.socket xalarmd.service
    kill -9 `pgrep -w test_task`

   rm -rf ${tmp_log} test/sysSentry/test_task 
   rm -rf /usr/bin/test_task /etc/sysSentry/tasks/test_end_exception.mod
}
set -x
run_testcase
