#!/bin/bash
# Copyright (c), 2023-2024, Huawei Tech. Co., Ltd.

source "libs/expect.sh"
source "libs/lib.sh"
source "libs/wait.sh"
source "libs/shopt.sh"
set +e

#测试读取配置文件异常的场景

function pre_test() {
    cp /etc/sysSentry/xalarm.conf /etc/sysSentry/xalarm.conf.bak
    rm -f ./tmp_log
    systemctl stop xalarmd.socket xalarmd.service
    sleep 1
}

function do_test() {

    # 异常的alarm id
    start_line=$(expr $(wc -l < /var/log/sysSentry/xalarm.log) + 1)
    echo -e "[filter]\nid_mask = 999,9999,aaa,test-and-run,7869-2431" > /etc/sysSentry/xalarm.conf
    systemctl start xalarmd.socket xalarmd.service
    end_line=$(wc -l < /var/log/sysSentry/xalarm.log)
    sed -n "${start_line}, ${end_line}p" /var/log/sysSentry/xalarm.log >> ./tmp_log
    wait_cmd_ok "grep \"invalid alarm id 999, ignored\" ./tmp_log" 1 3
    expect_eq $? 0 "xalarm config: alarm id less than 1001"
    
    wait_cmd_ok "grep \"invalid alarm id 9999, ignored\" ./tmp_log" 1 3
    expect_eq $? 0 "xalarm config: alarm id more than 9999"
    
    wait_cmd_ok "grep \"invalid alarm id aaa, ignored\" ./tmp_log" 1 3
    expect_eq $? 0 "xalarm config: alarm id is not number"
    
    wait_cmd_ok "grep \"invalid alarm id test-and-run, ignored\" ./tmp_log" 1 3
    expect_eq $? 0 "xalarm config: alarm id is not number interval"
    
    wait_cmd_ok "grep \"invalid alarm id 7869-2431, ignored\" ./tmp_log" 1 3
    expect_eq $? 0 "xalarm config: alarm id is not a valid number interval"
    
    rm -f /etc/sysSentry/xalarm.conf
    start_line=$(expr $(wc -l < /var/log/sysSentry/xalarm.log) + 1)
    echo -e "[no_filter]\nid_mask = 123" > /etc/sysSentry/xalarm.conf
    systemctl stop xalarmd.socket xalarmd.service
    sleep 1
    systemctl start xalarmd.socket xalarmd.service
    end_line=$(wc -l < /var/log/sysSentry/xalarm.log)
    sed -n "${start_line}, ${end_line}p" /var/log/sysSentry/xalarm.log >> ./tmp_log
    wait_cmd_ok "grep \"no filter conf\" ./tmp_log" 1 3
    expect_eq $? 0 "no filter conf"
    
    rm -f /etc/sysSentry/xalarm.conf
    start_line=$(expr $(wc -l < /var/log/sysSentry/xalarm.log) + 1)
    echo -e "[filter]\nid_mask_number = 123" > /etc/sysSentry/xalarm.conf
    systemctl stop xalarmd.socket xalarmd.service
    sleep 1
    systemctl start xalarmd.socket xalarmd.service
    end_line=$(wc -l < /var/log/sysSentry/xalarm.log)
    sed -n "${start_line}, ${end_line}p" /var/log/sysSentry/xalarm.log >> ./tmp_log
    wait_cmd_ok "grep \"no id_mask conf\" ./tmp_log" 1 3
    expect_eq $? 0 "no id_mask conf"

}

function post_test() {
    cat ./tmp_log
    rm -f /etc/sysSentry/xalarm.conf ./tmp_log
    cp /etc/sysSentry/xalarm.conf.bak /etc/sysSentry/xalarm.conf
    systemctl stop xalarmd.socket xalarmd.service
    sleep 1
}

run_testcase

