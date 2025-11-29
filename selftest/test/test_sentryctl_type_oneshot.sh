#!/bin/bash
# Copyright (c), 2023-2024, Huawei Tech. Co., Ltd.

source "libs/expect.sh"
source "libs/lib.sh"
source "libs/common.sh"
set +e

tmp_log="tmp_log"

# 测试oneshot巡检类型的各种任务状态

function pre_test() {
    common_pre_test "test_task" "pkill test_task" "oneshot" 60 36000 "test_type_oneshot"
}

function do_test() {
    #systemctl start sysSentry
    #expect_eq $? 0
    
    sentryctl status test_type_oneshot 2>&1 | tee ${tmp_log} | cat 
    expect_true "grep -E '(status: EXITED)' ${tmp_log}"

    sentryctl start test_type_oneshot
    expect_eq $? 0

    sentryctl status test_type_oneshot 2>&1 | tee ${tmp_log} | cat 
    expect_true "grep -E '(status: RUNNING)' ${tmp_log}"

    sentryctl stop test_type_oneshot
    expect_eq $? 0

    sleep 1

    sentryctl status test_type_oneshot 2>&1 | tee ${tmp_log} | cat
    expect_true "grep -E '(status: FAILED)' ${tmp_log}"

    sentryctl start test_type_oneshot
    expect_eq $? 0

    if pgrep -x "test_task" >/dev/null; then
        pkill -x "test_task"
        sleep 1
        sentryctl status test_type_oneshot 2>&1 | tee ${tmp_log} | cat 
        expect_true "grep -E '(status: FAILED)' ${tmp_log}"

        sentryctl start test_type_oneshot
        expect_eq $? 0

        sleep 1

        sentryctl status test_type_oneshot 2>&1 | tee ${tmp_log} | cat 
        expect_true "grep -E '(status: RUNNING)' ${tmp_log}"
    fi

    sleep 12

    sentryctl status test_type_oneshot 2>&1 | tee ${tmp_log} | cat
    expect_true "grep -E '(status: EXITED)' ${tmp_log}"

}

function post_test() {
	while [[ -n "`ps aux|grep -w syssentry|grep -v grep`" ]]; do
		kill -9 `pgrep -w syssentry`
		kill -9 `pgrep -w test_task`
		sleep 1
	done
   rm -rf ${tmp_log} test/sysSentry/test_task /usr/bin/test_task /etc/sysSentry/tasks/test_type_oneshot.mod
}
set -x
run_testcase
