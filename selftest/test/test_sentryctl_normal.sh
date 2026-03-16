#!/bin/bash
# Copyright (c), 2023-2024, Huawei Tech. Co., Ltd.

source "libs/expect.sh"
source "libs/lib.sh"
source "libs/common.sh"
set +e

tmp_log="tmp_log"

# 正常流程执行

function pre_test() {
    common_pre_test "test_task" "pkill test_task" "oneshot" 60 3600 "test_normal"
}

function do_test() {
    sentryctl status test_normal 2>&1 | tee ${tmp_log}
    expect_true "grep -E '(status: EXITED)' ${tmp_log}"

    sentryctl list 2>&1 | tee ${tmp_log}
    expect_true "grep -E '(['test_normal', 'EXITED'])' ${tmp_log}"

    sentryctl start test_normal
    expect_eq $? 0

    sentryctl start test_normal 2>&1 | tee ${tmp_log}
    expect_true "grep -E '(task is running, please wait)' ${tmp_log}"

    sentryctl stop test_normal
    expect_eq $? 0

    look_pid "test_task"
    if [ $? -eq 0 ]
    then
        sentryctl status test_normal 2>&1 | tee ${tmp_log}
        expect_true "grep -E '(status: FAILED)' ${tmp_log}"
    fi
}

function post_test() {
    systemctl stop sysSentry.socket sysSentry.service
    systemctl stop xalarmd.socket xalarmd.service
    kill -9 `pgrep -w test_task`
    rm -rf ${tmp_log}
    rm -rf test/sysSentry/test_task /usr/bin/test_task /etc/sysSentry/tasks/test_normal.mod
}
set -x
run_testcase
