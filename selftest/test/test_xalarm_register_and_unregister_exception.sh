#!/bin/bash
# Copyright (c), 2023-2024, Huawei Tech. Co., Ltd.

source "libs/expect.sh"
source "libs/lib.sh"
source "libs/wait.sh"
source "libs/shopt.sh"
set +e

#测试unregister的场景，其他用户解注册已有clientId和没出现的clientId，重复注册

function pre_test() {
    rm -rf ./checklog test/xalarm/unreg_demo test/xalarm/send_demo test/xalarm/reg_demo
    gcc test/xalarm/reg_demo.c -o test/xalarm/reg_demo -lxalarm
    gcc test/xalarm/unreg_demo.c -o test/xalarm/unreg_demo -lxalarm
    systemctl start xalarmd.socket xalarmd.service
}

function do_test() {
    ./test/xalarm/reg_demo 2 >> checklog 2>&1 &
    wait_cmd_ok "grep \"xalarm_Register: alarm has registered\" ./checklog" 1 3
    expect_eq $? 0 "register twice"
	
    ./test/xalarm/reg_demo >> checklog 2>&1 &
    ./test/xalarm/unreg_demo 0 >> checklog 2>&1 &
    wait_cmd_ok "grep \"unregister xalarm, client id is 0.xalarm_UnRegister: alarm has not registered\" ./checklog" 1 3
    expect_eq $? 0 "unregister available client id of xalarm"

    ./test/xalarm/unreg_demo 100 >> checklog 2>&1 &
    wait_cmd_ok "grep \"unregister xalarm, client id is 100.xalarm_UnRegister: alarm has not registered\" ./checklog" 1 3
    expect_eq $? 0 "unregister unavailable client id of xalarm"
	
}

function post_test() {
    systemctl stop xalarmd.socket xalarmd.service
    sleep 1
    cat ./checklog
    rm -rf ./checklog test/xalarm/unreg_demo test/xalarm/reg_demo
    systemctl stop xalarmd.socket xalarmd.service
    sleep 1
}

run_testcase



