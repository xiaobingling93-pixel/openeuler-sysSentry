#!/bin/bash
# Copyright (c), 2023-2024, Huawei Tech. Co., Ltd.

source "libs/expect.sh"
source "libs/lib.sh"
source "libs/common.sh"
set +e

tmp_log="tmp_log"

# 测试子任务名有效性测试用例
result1="this is a1122+#modname"

function pre_test() {
    common_pre_test "test_task" "pkill test_task" "oneshot" 60 3600 "$result1"
}

function do_test() {

    sentryctl list 2>&1 | tee ${tmp_log}
    expect_false "grep -E '($result1)' ${tmp_log}"

    result2="this_is_a1122_modname"
    common_pre_test "test_task" "pkill test_task" "oneshot" 60 3600 "$result2"

    sentryctl list 2>&1 | tee ${tmp_log} | cat 
    expect_true "grep -E '($result2)' ${tmp_log}"

}

function post_test() {
    systemctl stop sysSentry.socket sysSentry.service
    systemctl stop xalarmd.socket xalarmd.service
    kill -9 `pgrep -w test_task`
    rm -rf ${tmp_log}
    rm -rf test/sysSentry/test_task /usr/bin/test_task
    rm -rf /etc/sysSentry/tasks/this*.mod
}
set -x
run_testcase
