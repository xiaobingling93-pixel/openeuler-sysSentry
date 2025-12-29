#!/bin/bash

if [ "$(systemctl is-system-running)" = "stopping" ]; then
    echo "[sentry] Detected system shutdown/reboot, keeping the driver loaded."
else
    echo "[sentry] Manual stop, unloading driver"
    /sbin/rmmod sentry_remote_reporter
    /sbin/rmmod sentry_uvb_comm
    /sbin/rmmod sentry_urma_comm
    /sbin/rmmod sentry_reporter
    /sbin/rmmod sentry_msg_helper
    echo "[sentry] unload sentry kmod success"
fi