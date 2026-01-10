#!/bin/bash
# Copyright (c), 2023-2024, Huawei Tech. Co., Ltd.

source "libs/expect.sh"
source "libs/lib.sh"
source "libs/wait.sh"
source "libs/shopt.sh"
set +e

#测试upgrade场景:更新生效的场景、错误的clientId、错误的alarm id

function pre_test() {
    rm -rf ./checklog test/xalarm/upgrade_demo test/xalarm/send_demo
    gcc test/xalarm/upgrade_demo.c -o test/xalarm/upgrade_demo -lxalarm
    gcc test/xalarm/send_demo.c -o test/xalarm/send_demo -lxalarm
    systemctl start xalarmd.socket xalarmd.service
}

function do_test() {
    ./test/xalarm/upgrade_demo 4 0 1001 1002 1003 1004 >> checklog 2>&1 &
    sleep 2
    ./test/xalarm/send_demo 1004 1 2 "cpu usage high warning"
    wait_cmd_ok "grep \"id:1004\" ./checklog" 1 3
    expect_eq $? 0 "check upgrade take effect"

    kill -9 $(pgrep -w upgrade_demo)
    rm -rf checklog

    ./test/xalarm/upgrade_demo 4 0 1001 1002 1003 4004 >> checklog 2>&1 &
    wait_cmd_ok "grep \"xalarm_Upgrade: invalid args\" ./checklog" 1 3
    expect_eq $? 0 "upgrade with invalid alarm id"

    rm -rf checklog

    ./test/xalarm/upgrade_demo 4 999 1001 1002 1003 1004 >> checklog 2>&1 &
    wait_cmd_ok "grep \"xalarm_Upgrade: invalid args\" ./checklog" 1 3
    expect_eq $? 0 "upgrade with invalid client id"
	
}

function post_test() {
    kill -9 $(pgrep -w upgrade_demo)
    sleep 1
    cat ./checklog
    rm -rf ./checklog test/xalarm/upgrade_demo test/xalarm/send_demo
    systemctl stop xalarmd.socket xalarmd.service
    sleep 1
}

run_testcase



