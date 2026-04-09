[common]
enabled=yes
task_start=/usr/bin/bmc_ras_sentry
task_stop=kill $pid
type=period
alarm_id=1015
alarm_clear_time=90
