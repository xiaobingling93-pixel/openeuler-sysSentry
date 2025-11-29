[common]
enabled=yes
task_pre=modprobe sentry_reporter;modprobe sentry_remote_reporter
task_post=rmmod sentry_remote_reporter;rmmod sentry_uvb_comm;rmmod sentry_urma_comm;rmmod sentry_reporter;rmmod sentry_msg_helper
task_start=/usr/bin/sentry_msg_monitor
task_stop=kill $pid
type=period
interval=10
onstart=yes
env_file=/etc/sysconfig/sentry_msg_monitor.env
conflict=up
