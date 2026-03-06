[common]
enabled=yes
task_start=/usr/bin/bmc_ras_sentry
task_stop=kill $pid
type=oneshot
alarm_id=1015
alarm_clear_time=5
