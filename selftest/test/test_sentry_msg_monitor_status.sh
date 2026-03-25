#!/bin/bash
# Copyright (c), 2023-2024, Huawei Tech. Co., Ltd.

source "libs/expect.sh"
source "libs/lib.sh"
source "libs/common.sh"
set +e

tmp_log="tmp_log"

function pre_test() {
    systemctl start sysSentry.socket sysSentry.service
    cp /etc/sysSentry/tasks/sentry_msg_monitor.mod /etc/sysSentry/tasks/sentry_msg_monitor.mod_bak
}

function do_test() {
    sentryctl status sentry_msg_monitor 2>&1 | tee ${tmp_log} | cat
    expect_true "grep -E '(status: WAITING | RUNNING)' ${tmp_log}"

    sed -i 's/^task_pre=.*/task_pre=modprobe sentry_reporter/' /etc/sysSentry/tasks/sentry_msg_monitor.mod

    sentryctl reload sentry_msg_monitor
    expect_eq $? 0

    sentryctl start sentry_msg_monitor

    sentryctl status sentry_msg_monitor 2>&1 | tee ${tmp_log} | cat
    expect_true "grep -E '(status: RUNNING)' ${tmp_log}"

    pid1=$(pidof sentry_msg_monitor)
    kill -9 $pid1

    sleep 1

    # exit abnormally, task status should be WAITING
    sentryctl status sentry_msg_monitor 2>&1 | tee ${tmp_log} | cat
    expect_true "grep -E '(status: WAITING)' ${tmp_log}"

    sentryctl start sentry_msg_monitor
    expect_eq $? 0

    sentryctl status sentry_msg_monitor 2>&1 | tee ${tmp_log} | cat
    expect_true "grep -E '(status: RUNNING)' ${tmp_log}"

    pid2=$(pidof sentry_msg_monitor)
    expect_ne $pid1 $pid2

    sentryctl stop sentry_msg_monitor
    expect_eq $? 0

    # exit abnormally, task status should be EXITED (see stop() function)
    sentryctl status sentry_msg_monitor 2>&1 | tee ${tmp_log} | cat
    expect_true "grep -E '(status: EXITED)' ${tmp_log}"
}

function post_test() {
    systemctl stop sysSentry.service sysSentry.socket
    systemctl stop xalarmd.service xalarmd.socket

    rm -rf /etc/sysSentry/tasks/sentry_msg_monitor.mod
    mv /etc/sysSentry/tasks/sentry_msg_monitor.mod_bak /etc/sysSentry/tasks/sentry_msg_monitor.mod
}
set -x
run_testcase
