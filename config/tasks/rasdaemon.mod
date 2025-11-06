[common]
enabled=yes
task_start=/usr/sbin/rasdaemon -f
task_stop=kill $pid
type=oneshot
onstart=yes
env_file=/etc/sysconfig/rasdaemon
conflict=up
