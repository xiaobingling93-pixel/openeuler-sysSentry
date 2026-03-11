#!/bin/bash
# Copyright (c), 2023-2024, Huawei Tech. Co., Ltd.

source "libs/expect.sh"
source "libs/lib.sh"
source "libs/common.sh"
set +e

tmp_log="tmp_log"
start_line=0

# 测试异常的巡检类型的任务

function pre_test() {
    start_line=$(expr $(wc -l < /var/log/sysSentry/sysSentry.log) + 1)
    common_pre_test "test_task" "pkill test_task" "aaa" 60 3600 "test_type_exception"
}

function do_test() {
    end_line=$(wc -l < /var/log/sysSentry/sysSentry.log)
    sed -n "${start_line}, ${end_line}p" /var/log/sysSentry/sysSentry.log > ${tmp_log}
    expect_true "grep -E '(test_type_exception load failed)' ${tmp_log}" || cat ${tmp_log}
    
    sentryctl status test_type_exception 2>&1 | tee ${tmp_log}
    expect_true "grep -E '(status: cannot find task by name)' ${tmp_log}"

    sentryctl start test_type_exception 2>&1 | tee ${tmp_log}
    expect_true "grep -E '(task not exist)' ${tmp_log}"

    sentryctl stop test_type_exception 2>&1 | tee ${tmp_log}
    expect_true "grep -E '(task not exist)' ${tmp_log}"

}

function post_test() {
    systemctl stop sysSentry.socket sysSentry.service
    systemctl stop xalarmd.socket xalarmd.service
    kill -9 `pgrep -w test_task`

   rm -rf ${tmp_log} test/sysSentry/test_task /usr/bin/test_task /etc/sysSentry/tasks/test_type_exception.mod
}
set -x
run_testcase
