[common]
enabled=yes
task_start=/usr/bin/python3 /usr/bin/ai_block_io
task_stop=pkill -f /usr/bin/ai_block_io
type=oneshot
alarm_id=1002
alarm_clear_time=5
