#!/bin/bash
# Copyright (c), 2023-2024, Huawei Tech. Co., Ltd.

function common_pre_test() {

    kill -9 `ps aux|grep syssentry|grep -v grep|awk '{print $2}'`
    kill -9 `ps aux|grep test_task|grep -v grep|awk '{print $2}'`

    task_start="$1"
    task_stop="$2"
    type="$3"
    interval="$4"
    heartbeat_interval="$5"
    test_task_name="$6"

    add_test_config "$task_start" "$task_stop" "$type" $interval $heartbeat_interval $test_task_name

    gcc test/sysSentry/test_task.c -o test/sysSentry/test_task
    cp test/sysSentry/test_task /usr/bin

    systemctl start xalarmd.socket xalarmd.service
    systemctl start sysSentry.socket sysSentry.service
    sleep 1
}

function update_test_config() {
    task_start="$1"
    task_stop="$2"
    type="$3"
    interval="$4"
    heartbeat_interval="$5"
    config_file="config/sysSentry/$6.mod"

    if [ -f "$config_file" ]; then
        if [ -n "$task_start" ]; then
            sed -i "s/^task_start=.*/task_start=$task_start/" "$config_file"
        fi
        if [ -n "$task_stop" ]; then
            sed -i "s/^task_stop=.*/task_stop=$task_stop/" "$config_file"
        fi
        if [ -n "$type" ]; then
            sed -i "s/^type=.*/type=$type/" "$config_file"
        fi
        if [ -n "$interval" ]; then
            sed -i "s/^interval=.*/interval=$interval/" "$config_file"
        fi
        if [ -n "$heartbeat_interval" ]; then
            sed -i "s/^heartbeat_interval=.*/heartbeat_interval=$heartbeat_interval/" "$config_file"
        fi
        echo "$config_file file has been updated."
        return 0
    else
        log_error "at update_test_config, $config_file file not found."
    fi
    return 1
}

function add_test_config() {
    task_start="$1"
    task_stop="$2"
    type="$3"
    interval="$4"
    heartbeat_interval="$5"
    config_file="/etc/sysSentry/tasks/$6.mod"

    if [[ -z "$task_start" || -z "$task_stop" || -z "$type" ]]; then
        log_error "at add_test_config, task_start, task_stop and type can't be empty str"
        return 1
    fi

    if [ -f $config_file ];then
        rm -rf $config_file
    fi

    touch "$config_file"

    if [ -f "$config_file" ]; then
      echo "[common]" > "$config_file"
      echo "enabled=yes" >> "$config_file"
      echo "task_start=$task_start">> "$config_file"
      echo "task_stop=$task_stop">> "$config_file"
      echo "type=$type">> "$config_file"
      if [ -n "$interval" ]; then
          echo "interval=$interval">> "$config_file"
      fi
      if [ -n "heartbeat_interval" ];then
          echo "heartbeat_interval=$heartbeat_interval">> "$config_file"
      fi
      echo "$config_file file has been added."
      return 0
    else
      log_error "$config_file file not added."
    fi
    return 1
}

function look_pid() {
    task_task="$1"
    pid=$(ps -ef | grep '$task_task' | grep -v grep | awk '{print $2}')
    if [ -z "$pid"]
    then
        echo "$task_task is not existed"
        return 0
    else
        echo "$task_task is existed"
        return 1
    fi
}
