[common]
enabled=yes
task_pre=modprobe sentry_reporter;modprobe sentry_remote_reporter
task_post=bash /etc/sysSentry/task_scripts/sentry_msg_monitor.sh
task_start=/usr/bin/sentry_msg_monitor
task_stop=kill $pid
type=period
interval=10
onstart=yes
env_file=/etc/sysconfig/sentry_msg_monitor.env
conflict=up
