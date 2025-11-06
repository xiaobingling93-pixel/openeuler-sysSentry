[common]
enabled=yes
task_start=/usr/bin/hbm_online_repair
task_stop=kill $pid
type=period
interval=10
onstart=yes
env_file=/etc/sysconfig/hbm_online_repair.env
conflict=up
