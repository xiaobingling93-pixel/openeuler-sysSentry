#!/bin/bash
# Copyright (c), 2023-2024, Huawei Tech. Co., Ltd.

source "libs/expect.sh"
source "libs/lib.sh"
source "libs/common.sh"
set +e

tmp_log="tmp_log"

# 测试子任务名过长的测试用例

function pre_test() {
    gcc test/sysSentry/test_task.c -o test/sysSentry/test_task
    cp test/sysSentry/test_task /usr/bin

    systemctl start xalarmd.socket xalarmd.service
    systemctl start sysSentry.socket sysSentry.service
    sleep 1
}

function do_test() {
    # length:256
    str="a"
    result1=""
    for i in {1..256}; do
        result1+="$str"
    done

    sentryctl status $result1 2>&1 | tee ${tmp_log} | cat 
    expect_true "grep -E '(status: cannot find task by name)' ${tmp_log}"


    result2=""
    for i in {1..251}; do
      result2+="$str"
    done
    add_test_config "test_task" "pkill test_task" "oneshot" 60 3600 "$result2"
    expect_eq $? 0

    sentryctl reload $result2
    expect_eq $? 0
    
    sentryctl status $result2 2>&1 | tee ${tmp_log}
    expect_true "grep -E '(status: EXITED)' ${tmp_log}"

}

function post_test() {
    systemctl stop sysSentry.socket sysSentry.service
    systemctl stop xalarmd.socket xalarmd.service
    kill -9 `pgrep -w test_task`

    cat /etc/sysSentry/tasks/"$result2.mod"
    rm -rf ${tmp_log} test_task /usr/bin/test_task /etc/sysSentry/tasks/"$result2.mod"
}
set -x
run_testcase
