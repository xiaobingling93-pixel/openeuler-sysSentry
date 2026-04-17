#!/bin/bash
# Copyright (C), 2026, Huawei Tech. Co., Ltd.
# Description: test bmc_ras_sentry plugin invalid param
# 
# Create: 2026-04-16

source "libs/lib.sh"
source "libs/expect.sh"
source "libs/wait.sh"

function pre_test() {
    cp /etc/sysSentry/plugins/bmc_ras_sentry.ini /etc/sysSentry/plugins/bmc_ras_sentry.ini_bak

    systemctl restart sysSentry.service
}

function do_test() {

    expect_task_status_eq "bmc_ras_sentry" "RUNNING"

    sentryctl stop bmc_ras_sentry
    expect_task_status_eq "bmc_ras_sentry" "EXITED"

    # check log_level config 
    invalid_log_level_list=("err" "ERR" "ERROR" "1" "debugino" "#$%" "")
    for arg in "${invalid_log_level_list[@]}"; do
        echo > /var/log/sysSentry/bmc_ras_sentry.log

        sed -i "s/^log_level.*/log_level=${arg}/g" /etc/sysSentry/plugins/bmc_ras_sentry.ini

        sentryctl start bmc_ras_sentry
        sleep 1
        expect_task_status_eq "bmc_ras_sentry" "RUNNING"

        sentryctl stop bmc_ras_sentry
        expect_task_status_eq "bmc_ras_sentry" "EXITED"

        wait_cmd_ok "grep \"Invalid log_level value\" /var/log/sysSentry/bmc_ras_sentry.log" 1 3
        wait_cmd_ok "grep \"Parse config failed, use default configuration.\" /var/log/sysSentry/bmc_ras_sentry.log" 1 3
    done

    # check patrol_second config
    invalid_patrol_second_list=("59" "36001" "0" "-1" "7200" "#$%" "")
    for arg in "${invalid_patrol_second_list[@]}"; do
        echo > /var/log/sysSentry/bmc_ras_sentry.log

        sed -i "s/^patrol_second.*/patrol_second=${arg}/g" /etc/sysSentry/plugins/bmc_ras_sentry.ini

        sentryctl start bmc_ras_sentry
        sleep 1
        expect_task_status_eq "bmc_ras_sentry" "RUNNING"

        sentryctl stop bmc_ras_sentry
        expect_task_status_eq "bmc_ras_sentry" "EXITED"

        wait_cmd_ok "grep \"Invalid patrol_second value\" /var/log/sysSentry/bmc_ras_sentry.log" 1 3
        wait_cmd_ok "grep \"Parse config failed, use default configuration.\" /var/log/sysSentry/bmc_ras_sentry.log" 1 3
    done

    # check bmc_events config -- input type error
    invalid_bmc_events_list=("59" "36001" "0" "00000" "010101" "#$%" " " "0x0x" "abcd")
    for arg in "${invalid_bmc_events_list[@]}"; do
        echo > /var/log/sysSentry/bmc_ras_sentry.log

        sed -i "s/^bmc_events.*/bmc_events=${arg}/g" /etc/sysSentry/plugins/bmc_ras_sentry.ini

        sentryctl start bmc_ras_sentry
        sleep 1
        expect_task_status_eq "bmc_ras_sentry" "RUNNING"

        sentryctl stop bmc_ras_sentry
        expect_task_status_eq "bmc_ras_sentry" "EXITED"

        wait_cmd_ok "grep \"Invalid bmc_events value\" /var/log/sysSentry/bmc_ras_sentry.log" 1 3
        wait_cmd_ok "grep \"Parse config failed, use default configuration.\" /var/log/sysSentry/bmc_ras_sentry.log" 1 3
    done

    # check bmc_events config -- input event type id error
    # 01 -> hard drive, its event id is 00-12 and 00 -> all event type for this entity type
    invalid_bmc_events_list=("0113" "01-1" "0121")
    for arg in "${invalid_bmc_events_list[@]}"; do
        echo > /var/log/sysSentry/bmc_ras_sentry.log

        sed -i "s/^bmc_events.*/bmc_events=${arg}/g" /etc/sysSentry/plugins/bmc_ras_sentry.ini

        sentryctl start bmc_ras_sentry
        sleep 1
        expect_task_status_eq "bmc_ras_sentry" "RUNNING"

        sentryctl stop bmc_ras_sentry
        expect_task_status_eq "bmc_ras_sentry" "EXITED"

        wait_cmd_ok "grep \"BMC Event Id not find, Event id:\" /var/log/sysSentry/bmc_ras_sentry.log" 1 3
        wait_cmd_ok "grep \"Parse config failed, use default configuration.\" /var/log/sysSentry/bmc_ras_sentry.log" 1 3
    done

    # check bmc_events config -- input event type id error
    # 02 -> raid card, its event id is 00-02 and 00 -> all event type for this entity type
    invalid_bmc_events_list=("02-1" "0203" "0204" "02020")
    for arg in "${invalid_bmc_events_list[@]}"; do
        echo > /var/log/sysSentry/bmc_ras_sentry.log

        sed -i "s/^bmc_events.*/bmc_events=${arg}/g" /etc/sysSentry/plugins/bmc_ras_sentry.ini

        sentryctl start bmc_ras_sentry
        sleep 1
        expect_task_status_eq "bmc_ras_sentry" "RUNNING"

        sentryctl stop bmc_ras_sentry
        expect_task_status_eq "bmc_ras_sentry" "EXITED"

        wait_cmd_ok "grep \"BMC Event Id not find, Event id:\" /var/log/sysSentry/bmc_ras_sentry.log" 1 3
        wait_cmd_ok "grep \"Parse config failed, use default configuration.\" /var/log/sysSentry/bmc_ras_sentry.log" 1 3
    done

    # check bmc_events config -- input event type id error
    # 03 -> memory, its event id is 00-04 and 00 -> all event type for this entity type
    invalid_bmc_events_list=("03-1" "0305" "03050" "030402")
    for arg in "${invalid_bmc_events_list[@]}"; do
        echo > /var/log/sysSentry/bmc_ras_sentry.log

        sed -i "s/^bmc_events.*/bmc_events=${arg}/g" /etc/sysSentry/plugins/bmc_ras_sentry.ini

        sentryctl start bmc_ras_sentry
        sleep 1
        expect_task_status_eq "bmc_ras_sentry" "RUNNING"

        sentryctl stop bmc_ras_sentry
        expect_task_status_eq "bmc_ras_sentry" "EXITED"

        wait_cmd_ok "grep \"BMC Event Id not find, Event id:\" /var/log/sysSentry/bmc_ras_sentry.log" 1 3
        wait_cmd_ok "grep \"Parse config failed, use default configuration.\" /var/log/sysSentry/bmc_ras_sentry.log" 1 3
    done

    # check bmc_events config -- input event type id error
    # 04 -> cpu, its event id is 00-01 and 00 -> all event type for this entity type
    invalid_bmc_events_list=("0402" "04010" "04000")
    for arg in "${invalid_bmc_events_list[@]}"; do
        echo > /var/log/sysSentry/bmc_ras_sentry.log

        sed -i "s/^bmc_events.*/bmc_events=${arg}/g" /etc/sysSentry/plugins/bmc_ras_sentry.ini

        sentryctl start bmc_ras_sentry
        sleep 1
        expect_task_status_eq "bmc_ras_sentry" "RUNNING"

        sentryctl stop bmc_ras_sentry
        expect_task_status_eq "bmc_ras_sentry" "EXITED"

        wait_cmd_ok "grep \"BMC Event Id not find, Event id:\" /var/log/sysSentry/bmc_ras_sentry.log" 1 3
        wait_cmd_ok "grep \"Parse config failed, use default configuration.\" /var/log/sysSentry/bmc_ras_sentry.log" 1 3
    done
}

function post_test() {
    systemctl stop xalarmd.service
    systemctl stop sysSentry.service

    mv /etc/sysSentry/plugins/bmc_ras_sentry.ini_bak /etc/sysSentry/plugins/bmc_ras_sentry.ini
}

run_testcase
