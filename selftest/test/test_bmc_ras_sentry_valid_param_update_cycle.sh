#!/bin/bash
# Copyright (C), 2026, Huawei Tech. Co., Ltd.
# Description: test bmc_ras_sentry plugin valid param update cycle
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

    # check log_level config 
    valid_log_level_list=("error" "info" "debug" "warning" "critica"l)
    for arg in "${valid_log_level_list[@]}"; do
        echo > /var/log/sysSentry/bmc_ras_sentry.log

        sed -i "s/^log_level.*/log_level=${arg}/g" /etc/sysSentry/plugins/bmc_ras_sentry.ini

        expect_task_status_eq "bmc_ras_sentry" "RUNNING"

        # sleep BMCPLU_CONFIG_CHECK_CYCLE
        sleep 10

        upper_log_level_str=$(echo "$arg" | tr '[:lower:]' '[:upper:]')
        wait_cmd_ok "grep \"Log level update to $upper_log_level_str\" /var/log/sysSentry/bmc_ras_sentry.log" 1 3
    done

    # check patrol_second config
    valid_patrol_second_list=("66" "35999" "100")
    for arg in "${valid_patrol_second_list[@]}"; do
        echo > /var/log/sysSentry/bmc_ras_sentry.log

        sed -i "s/^patrol_second.*/patrol_second=${arg}/g" /etc/sysSentry/plugins/bmc_ras_sentry.ini

        expect_task_status_eq "bmc_ras_sentry" "RUNNING"

        # sleep BMCPLU_CONFIG_CHECK_CYCLE
        sleep 10
        wait_cmd_ok "grep \"Patrol interval update to $arg\" /var/log/sysSentry/bmc_ras_sentry.log" 1 3
    done

    # check bmc_events config -- input type error
    valid_bmc_events_list=("0101" "0201" "0301" "0401")
    for arg in "${valid_bmc_events_list[@]}"; do
        echo > /var/log/sysSentry/bmc_ras_sentry.log

        sed -i "s/^bmc_events.*/bmc_events=${arg}/g" /etc/sysSentry/plugins/bmc_ras_sentry.ini

        expect_task_status_eq "bmc_ras_sentry" "RUNNING"

        # sleep BMCPLU_CONFIG_CHECK_CYCLE
        sleep 10
        wait_cmd_ok "grep \"BMC Events update to $arg\" /var/log/sysSentry/bmc_ras_sentry.log" 1 3
    done
}

function post_test() {
    systemctl stop xalarmd.service
    systemctl stop sysSentry.service

    mv /etc/sysSentry/plugins/bmc_ras_sentry.ini_bak /etc/sysSentry/plugins/bmc_ras_sentry.ini
}

run_testcase
