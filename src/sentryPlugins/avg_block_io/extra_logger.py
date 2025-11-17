# coding: utf-8
# Copyright (c) 2025 Huawei Technologies Co., Ltd.
# sysSentry is licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#     http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
# PURPOSE.
# See the Mulan PSL v2 for more details.
import logging
import os
import re
import ast

extra_logger = None


# Define stage groups
STAGE_GROUPS = {
    'B->Q': ['throtl', 'wbt', 'iocost'],
    'Q->G': ['gettag'],
    'G->I': ['plug'],
    'I->D': ['deadline', 'bfq', 'hctx', 'requeue'],
    'D->C': ['rq_driver']
}

PATTERN = re.compile(r'(\w+):\s*\[([0-9.,]+)\]')


def init_extra_logger(log_path, log_level, log_format):
    global extra_logger
    try:
        if not os.path.exists(log_path):
            fd = os.open(log_path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)
        logger_name = f"extra_logger_{log_path}"
        logger = logging.getLogger(logger_name)
        logger.propagate = False
        logger.setLevel(log_level)

        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(log_level)

        formatter = logging.Formatter(log_format)
        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        extra_logger = logger
    except Exception as e:
        logging.error(f"Failed to create extra logger for {log_path}: {e}")
        extra_logger = logging.getLogger()  # Fallback to default logger


def extra_slow_log(msg):
    if "latency" in str(msg.get('alarm_type', '')):
        extra_latency_log(msg)
    if "iodump" in str(msg.get('alarm_type', '')):
        extra_iodump_log(msg)


def extra_latency_log(msg):
    # Parse the iops string from msg
    iops_avg = 0
    iops_str = msg['details']['iops']
    iops_matches = re.findall(PATTERN, iops_str)
    iops_data = {}
    for match in iops_matches:
        key = match[0]
        values = list(map(float, match[1].split(',')))
        iops_data[key] = values
    if 'rq_driver' in iops_data and iops_data['rq_driver']:
        iops_avg = sum(iops_data['rq_driver']) / len(iops_data['rq_driver'])

    extra_logger.warning(f"[SLOW IO] alarm_type: latency, disk: {msg['driver_name']}, "
                         f"iotype: {msg['io_type']}, iops: {int(iops_avg)}")

    # Parse the latency string from msg
    latency_str = msg['details']['latency']
    latency_matches = re.findall(PATTERN, latency_str)
    latency_data = {}
    for match in latency_matches:
        key = match[0]
        values = list(map(float, match[1].split(',')))
        latency_data[key] = values

    # Calculate statistics for each group
    group_stats = {}
    for group_name, stages in STAGE_GROUPS.items():
        all_values = []
        for stage in stages:
            if stage in latency_data:
                all_values.extend(latency_data[stage])
        if all_values:
            min_val = min(all_values)
            max_val = max(all_values)
            avg_val = sum(all_values) / len(all_values)
        else:
            min_val = 0
            max_val = 0
            avg_val = 0
        # Convert to ms
        min_val_ms = min_val / 1000.0
        max_val_ms = max_val / 1000.0
        avg_val_ms = avg_val / 1000.0
        group_stats[group_name] = {
            'min': min_val_ms,
            'max': max_val_ms,
            'avg': avg_val_ms
        }

    # Calculate total latency (B->C)
    total_avg = 0
    total_min = 0
    total_max = 0
    for group_name in STAGE_GROUPS:
        total_avg += group_stats[group_name]['avg']
        total_min += group_stats[group_name]['min']
        total_max += group_stats[group_name]['max']
    group_stats['B->C'] = {
        'min': total_min,
        'max': total_max,
        'avg': total_avg
    }

    # Calculate PCT for each group (except B->C)
    for group_name in STAGE_GROUPS:
        if total_avg > 0:
            pct = (group_stats[group_name]['avg'] / total_avg) * 100
        else:
            pct = 0
        group_stats[group_name]['pct'] = pct
    group_stats['B->C']['pct'] = 100.0

    # Output table
    stage_order = ['B->Q', 'Q->G', 'G->I', 'I->D', 'D->C', 'B->C']
    stage_width = 7
    num_width = 12
    pct_width = 8

    extra_logger.warning(
        f"{'Stage':<{stage_width}} "
        f"{'Min(ms)':>{num_width}} "
        f"{'Max(ms)':>{num_width}} "
        f"{'Avg(ms)':>{num_width}} "
        f"{'PCT':>{pct_width}}"
    )

    for stage in stage_order:
        try:
            s = group_stats[stage]
            min_str = f"{s['min']:>.3f}"
            max_str = f"{s['max']:>.3f}"
            avg_str = f"{s['avg']:>.3f}"
            pct_str = f"{s['pct']:.2f}%"

            extra_logger.warning(
                f"{stage:<{stage_width}} "
                f"{min_str:>{num_width}} "
                f"{max_str:>{num_width}} "
                f"{avg_str:>{num_width}} "
                f"{pct_str:>{pct_width}}"
            )
        except KeyError:
            return

    extra_disk_log(msg)


def extra_iodump_log(msg):
    extra_logger.warning(f"[SLOW IO] iodump, disk:{msg['driver_name']}, iotype:{msg['io_type']}")
    iodump_str = msg['details']['iodump_data']

    try:
        iodump_data = ast.literal_eval(iodump_str)
        bio_data = iodump_data['bio']
    except Exception as e:
        extra_logger.error(f"Failed to parse iodump data: {e}")
        return

    stack_to_stage = {}
    for stage, stacks in STAGE_GROUPS.items():
        for stack in stacks:
            stack_to_stage[stack] = stage

    last_bio_record = {}
    for window in bio_data:
        for entry in window:
            parts = entry.split(',')
            task_name, pid, io_stack, bio_ptr, start_ago = parts
            if io_stack in stack_to_stage:
                stage = stack_to_stage[io_stack]
                last_bio_record[bio_ptr] = (task_name, pid, io_stack, stage, bio_ptr, start_ago)

    header = f"{'TASK_NAME':<18} {'PID':>8} {'IO_STACK':<12} {'STAGE':<8} {'BIO_PTR':<20} {'START_AGO(ms)':>10}"
    extra_logger.warning(header)

    for bio_ptr in last_bio_record:
        task_name, pid, io_stack, stage, bio_ptr, start_ago = last_bio_record[bio_ptr]
        line = f"{task_name:<18} {pid:>8} {io_stack:<12} {stage:<8} {bio_ptr:<20} {start_ago:>10}"
        extra_logger.warning(line)


def extra_disk_log(msg):
    disk_str = msg['details']['disk_data']
    try:
        disk_data = ast.literal_eval(disk_str)
        rq_driver_data = disk_data['rq_driver']
    except Exception as e:
        extra_logger.error(f"Failed to parse disk data: {e}")
        return

    if not rq_driver_data[0]:
        return

    extra_logger.warning(f"disk latency:")
    header = f"{'0-1ms':>12} {'1-10ms':>12} {'10-100ms':>15} {'100ms-1s':>15} {'1-3s':>12} {'>3s':>12}"
    extra_logger.warning(header)

    total_data = [0] * 6
    for period_data in rq_driver_data:
        for i in range(6):
            total_data[i] += period_data[i]
    num_periods = len(rq_driver_data)
    avg_data = [total // num_periods for total in total_data]
    extra_logger.warning(
        f"{avg_data[0]:>12} {avg_data[1]:>12} {avg_data[2]:>15}"
        f"{avg_data[3]:>15} {avg_data[4]:>12} {avg_data[5]:>12}"
    )