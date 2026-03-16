#!/bin/bash
# Copyright (c), 2023-2024, Huawei Tech. Co., Ltd.

source "libs/expect.sh"
source "libs/lib.sh"
source "libs/common.sh"
set +e

tmp_log="tmp_log"

# 测试period巡检类型的各种任务状态

function pre_test() {
    common_pre_test "test_task" "pkill test_task" "period" 60 3600 "test_type_period"
}

function do_test() {
    #systemctl start sysSentry
    #expect_eq $? 0
    
    sentryctl status test_type_period 2>&1 | tee ${tmp_log} | cat 
    expect_true "grep -E '(status: WAITING | RUNNING)' ${tmp_log}"

    sentryctl start test_type_period
    expect_eq $? 0

    sentryctl status test_type_period 2>&1 | tee ${tmp_log} | cat 
    expect_true "grep -E '(status: RUNNING)' ${tmp_log}"

    sentryctl stop test_type_period
    expect_eq $? 0

    sleep 1

    sentryctl status test_type_period 2>&1 | tee ${tmp_log} | cat
    expect_true "grep -E '(status: FAILED)' ${tmp_log}"

    sentryctl start test_type_period
    expect_eq $? 0

    sleep 12

    # wating状态
    sentryctl status test_type_period 2>&1 | tee ${tmp_log} | cat
    expect_true "grep -E '(status: WAITING)' ${tmp_log}"

    sentryctl start test_type_period
    expect_eq $? 0

    if pgrep -x "test_task" >/dev/null; then
        pkill -x "test_task"
        sleep 2
        sentryctl status test_type_period | grep -w "status: WAITING"
        expect_eq $? 0

        sentryctl start test_type_period
        expect_eq $? 0

        sentryctl stop test_type_period
        expect_eq $? 0

        sentryctl status test_type_period | grep -w "status: FAILED"
        expect_eq $? 0
    fi

}

function post_test() {
	systemctl stop sysSentry.socket sysSentry.service
    systemctl stop xalarmd.socket xalarmd.service
    kill -9 `pgrep -w test_task`
   rm -rf ${tmp_log} test/sysSentry/test_task /usr/bin/test_task /etc/sysSentry/tasks/test_type_period.mod
}
set -x
run_testcase
