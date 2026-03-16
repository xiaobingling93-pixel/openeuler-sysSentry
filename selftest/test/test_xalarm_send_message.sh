#!/bin/bash
# Copyright (c), 2023-2024, Huawei Tech. Co., Ltd.

source "libs/expect.sh"
source "libs/lib.sh"
source "libs/wait.sh"
source "libs/shopt.sh"
set +e

#测试发送消息的场景，参数合法性校验以及关闭xalarmd之后的场景

function pre_test() {
    rm -rf ./checklog ./tmp_log test/xalarm/send_demo test/xalarm/reg_demo
    gcc test/xalarm/send_demo.c -o test/xalarm/send_demo -lxalarm
    gcc test/xalarm/reg_demo.c -o test/xalarm/reg_demo -lxalarm
    systemctl stop xalarmd.socket xalarmd.service
    sleep 1
    systemctl start xalarmd.socket xalarmd.service
}

function do_test() {
    ./test/xalarm/reg_demo >> checklog 2>&1 &
    wait_cmd_ok "grep \"register success\" ./checklog" 1 3
    expect_eq $? 0 "xalarm register success"

    # 发送用户注册的alarm id消息
    ./test/xalarm/send_demo 1001 1 2 "cpu usage high warning - 1" >> checklog 2>&1 &
    wait_cmd_ok "grep \"id:1001\" ./checklog" 1 3
    expect_eq $? 0 "alarm id check"

    wait_cmd_ok "grep \"level:1\" ./checklog" 1 3
    expect_eq $? 0 "alarm level check"

    wait_cmd_ok "grep \"type:2\" ./checklog" 1 3
    expect_eq $? 0 "alarm type check"

    wait_cmd_ok "grep \"cpu usage high warning - 1\" ./checklog" 1 3
    expect_eq $? 0 "alarm message check"
	
    # 发送用户未注册的alarm id消息
    start_line=$(wc -l < ./checklog)
    ./test/xalarm/send_demo 1007 1 2 "cpu usage high warning - 2" >> checklog 2>&1 &
    end_line=$(wc -l < ./checklog)
    expect_eq $end_line $start_line "send unregistered alarm id to xalarm"

    # 验证不合法参数
    start_line=$(expr $(wc -l < ./checklog) + 1)
    ./test/xalarm/send_demo 9000 2 1 "cpu usage high - 3" >> checklog 2>&1 &
    end_line=$(wc -l < ./checklog)
    sed -n "${start_line}, ${end_line}p" ./checklog > ./tmp_log
    wait_cmd_ok "grep \"xalarm_Report: alarm info invalid\" ./tmp_log" 1 3
    expect_eq $? 0 "alarm id check"
 
    start_line=$(expr $(wc -l < ./checklog) + 1)
    ./test/xalarm/send_demo 1002 7 -1 "cpu usage high - 4" >> checklog 2>&1 &
    end_line=$(wc -l < ./checklog)
    sed -n "${start_line}, ${end_line}p" ./checklog > ./tmp_log
    wait_cmd_ok "grep \"xalarm_Report: alarm info invalid\" ./tmp_log" 1 3
    expect_eq $? 0 "alarm type check"
 
    start_line=$(expr $(wc -l < ./checklog) + 1)
    ./test/xalarm/send_demo 1002 2 -1 "cpu usage high - 5" >> checklog 2>&1 &
    end_line=$(wc -l < ./checklog)
    sed -n "${start_line}, ${end_line}p" ./checklog > ./tmp_log
    wait_cmd_ok "grep \"xalarm_Report: alarm info invalid\" ./tmp_log" 1 3
    expect_eq $? 0 "alarm level check"

    # 验证解注册
    sleep 10
    ./test/xalarm/send_demo 1001 1 2 "cpu usage high warning - 6" >> checklog 2>&1 &
    wait_cmd_ok "grep \"unregister xalarm success\" ./checklog" 1 3
    expect_eq $? 0 "check unregister xalarm"

    # 停止xalarmd服务后发消息
    systemctl stop xalarmd.socket xalarmd.service
    sleep 3

    ./test/xalarm/send_demo 1001 1 2 "cpu usage high warning - 7" >> checklog 2>&1 &
    wait_cmd_ok "grep \"xalarm_Report: sendto failed errno\" ./checklog" 1 3
    expect_eq $? 0 "xalarm send message while stop xalarmd service"
}

function post_test() {
    systemctl stop xalarmd.socket xalarmd.service
    sleep 1
    cat ./checklog
    rm -rf ./checklog ./tmp_log test/xalarm/send_demo test/xalarm/reg_demo
    systemctl stop xalarmd.socket xalarmd.service
    sleep 1
}

run_testcase



