# coding: utf-8
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# sysSentry is licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#     http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
# PURPOSE.
# See the Mulan PSL v2 for more details.
"""
Description: xalarm events management - manage event switches based on client subscriptions
Author:
Create: 2026-04-20
"""

import logging
import threading
import json
import time
from collections import defaultdict

from syssentry.sentry_proc import (
    set_sentry_reporter_proc,
    set_remote_reporter_proc,
)

from .xalarm_api import (
    MIN_ALARM_ID,
    MAX_ALARM_ID,
)

event_state_lock = threading.Lock()
fd_to_events = defaultdict(set)
enabled_events = set()

ENABLE_EVENT_INPUT = "on"
DISABLE_EVENT_INPUT = "off"

ALARM_REBOOT_EVENT = 1003
ALARM_OOM_EVENT = 1005
ALARM_PANIC_EVENT = 1007
ALARM_KERNEL_REBOOT_EVENT = 1009
ALARM_UBUS_MEM_EVENT = 1013
SENTRY_REPORTER_MODULE_EVENT_ID_LIST = [ALARM_REBOOT_EVENT, ALARM_OOM_EVENT, ALARM_UBUS_MEM_EVENT]
SENTRY_REMOTE_REPORTER_MODULE_EVENT_ID_LIST = [ALARM_PANIC_EVENT, ALARM_KERNEL_REBOOT_EVENT]

EVENT_PROC_NAME_DICT = {
    ALARM_REBOOT_EVENT : "power_off",
    ALARM_OOM_EVENT : "oom",
    ALARM_PANIC_EVENT : "panic",
    ALARM_KERNEL_REBOOT_EVENT : "kernel_reboot",
    ALARM_UBUS_MEM_EVENT : "ub_mem_fault"
}


def set_sentry_reporter_module_switch(event_id: int, param: str):
    """set sentry proc value"""
    if param not in [ENABLE_EVENT_INPUT, DISABLE_EVENT_INPUT] or not (
        event_id in SENTRY_REPORTER_MODULE_EVENT_ID_LIST or
        event_id in SENTRY_REMOTE_REPORTER_MODULE_EVENT_ID_LIST
    ):
        logging.error(f"invalid param: {param}")
    if event_id in SENTRY_REPORTER_MODULE_EVENT_ID_LIST:
        set_sentry_reporter_proc(EVENT_PROC_NAME_DICT[event_id], param)
    else:
        set_remote_reporter_proc(EVENT_PROC_NAME_DICT[event_id], param)


def open_event(event_id: int) -> bool:
    """
    Open event switch for specific event ID.
    Called when first client subscribes to this event.

    Args:
        event_id: Event ID in range [1001, 1128]

    Returns:
        bool: True if successful
    """
    try:
        set_sentry_reporter_module_switch(event_id, ENABLE_EVENT_INPUT)
        logging.info("Event %d enabled - client subscribed", event_id)
        return True
    except Exception as e:
        logging.error("Failed to enable event %d: %s", event_id, str(e))
        return False


def disable_event(event_id: int) -> bool:
    """
    Close event switch for specific event ID.
    Called when no clients subscribe to this event anymore.

    Args:
        event_id: Event ID

    Returns:
        bool: True if successful
    """
    try:
        set_sentry_reporter_module_switch(event_id, DISABLE_EVENT_INPUT)
        logging.info("Event %d disabled - no clients subscribed", event_id)
        return True
    except Exception as e:
        logging.error("Failed to disable event %d: %s", event_id, str(e))
        return False


def parse_event_message(data: bytes) -> tuple:
    """
    Parse client event message to get action and event IDs.

    Args:
        data: JSON format event message

    Returns:
        tuple: (action, event_ids), action is None if parse failed
    """
    try:
        msg_str = data.decode('utf-8').strip()
        if not msg_str:
            logging.warning("Empty event message")
            return (None, [])

        msg = json.loads(msg_str)

        action = msg.get("action")
        if action not in ["register_events", "unregister_events"]:
            logging.warning("Invalid action in event message: %s", action)
            return (None, [])

        event_ids = msg.get("event_ids", [])
        if not isinstance(event_ids, list):
            logging.warning("event_ids is not a list")
            return (None, [])

        valid_ids = []
        for eid in event_ids:
            if isinstance(eid, int) and MIN_ALARM_ID <= eid <= MAX_ALARM_ID:
                valid_ids.append(eid)
            else:
                logging.warning("Invalid event ID: %s", eid)

        return (action, valid_ids)
    except json.JSONDecodeError as e:
        logging.error("Failed to parse event message: %s", str(e))
        return (None, [])
    except Exception as e:
        logging.error("Error parsing event message: %s", str(e))
        return (None, [])


def handle_client_event(client_fd: int, data: bytes) -> None:
    """
    Handle client event message (registration or unregistration).

    Args:
        client_fd: Client socket file descriptor
        data: JSON format event message
    """
    action, event_ids = parse_event_message(data)
    if not action or not event_ids:
        logging.warning("no event id, registration msg is %s", data)
        return

    if action == "register_events":
        logging.info("start register event")
        register_client_events(client_fd, event_ids)
    elif action == "unregister_events":
        logging.info("start unregister event")
        unregister_client_events(client_fd, event_ids)


def register_client_events(client_fd: int, event_ids: list) -> None:
    """
    Register client's event subscriptions and enable events if needed.

    Args:
        client_fd: Client socket file descriptor
        event_ids: Event ID list client subscribes to
    """
    with event_state_lock:
        fd_to_events[client_fd] = set(event_ids)

        for event_id in event_ids:
            if event_id not in enabled_events:
                if open_event(event_id):
                    enabled_events.add(event_id)

        logging.info("Client fd %d registered events: %s", client_fd, event_ids)


def unregister_client_events(client_fd: int, event_ids: list) -> None:
    """
    Unregister client's event subscriptions and disable events if no other clients need them.

    Args:
        client_fd: Client socket file descriptor
        event_ids: Event ID list client wants to unsubscribe
    """
    with event_state_lock:
        if client_fd not in fd_to_events:
            return

        for event_id in event_ids:
            if event_id in fd_to_events[client_fd]:
                fd_to_events[client_fd].discard(event_id)

                still_needed = False
                for _, other_events in fd_to_events.items():
                    if event_id in other_events:
                        still_needed = True
                        break

                if not still_needed and event_id in enabled_events:
                    disable_event(event_id)
                    enabled_events.discard(event_id)

        logging.info("Client fd %d unregistered events: %s", client_fd, event_ids)
