[common]
enabled=yes
task_start=/usr/bin/sentry_msg_monitor
task_stop=kill $pid
type=period
interval=10
onstart=yes
env_file=/etc/sysconfig/sentry_msg_monitor.env
conflict=up
