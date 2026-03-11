#!/bin/bash
# Copyright (c), 2023-2024, Huawei Tech. Co., Ltd.

source "libs/expect.sh"
source "libs/lib.sh"
source "libs/common.sh"
set +e

tmp_log="tmp_log"

# 异常的task_start命令，在运行时是否报错

function pre_test() {
    common_pre_test "aaaa" "pkill test_task" "oneshot" 60 3600 "test_start_exception"
}

function do_test() {
    sentryctl status test_start_exception 2>&1 | tee ${tmp_log} | cat
    expect_true "grep -E '(status: EXITED)' ${tmp_log}"

    sleep 1

    sentryctl start test_start_exception 2>&1 | tee ${tmp_log} | cat
    expect_true "grep -E '(start command is invalid, popen failed)' ${tmp_log}"

    sentryctl status test_start_exception 2>&1 | tee ${tmp_log} | cat
    expect_true "grep -E '(status: FAILED)' ${tmp_log}"
}

function post_test() {
    systemctl stop sysSentry.socket sysSentry.service
    systemctl stop xalarmd.socket xalarmd.service
    kill -9 `pgrep -w test_task`
   rm -rf ${tmp_log} test/sysSentry/test_task 
   rm -rf /usr/bin/test_task /etc/sysSentry/tasks/test_start_exception.mod
}
set -x
run_testcase
