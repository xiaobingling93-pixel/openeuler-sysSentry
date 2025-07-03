[common]
enabled=yes
task_start=/usr/bin/soc_ring_sentry
task_stop=pkill -f soc_ring_sentry
type=oneshot
onstart=yes
env_file=/etc/sysconfig/soc_ring_sentry.env