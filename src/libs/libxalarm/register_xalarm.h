/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2023-2024. All rights reserved.
 * Description: inspection message alarm program
 * Author: Lan Sheng
 * Create: 2023-10-23
 */

#ifndef __REGISTER_XALARM_H
#define __REGISTER_XALARM_H

#include <sys/time.h>
#include <stdbool.h>
 
#define ALARM_INFO_MAX_PARAS_LEN 8192
#define MAX_STRERROR_SIZE 1024
#define MAX_ALARM_TYEPS 1024
#define MIN_ALARM_ID 1001
#define BYTE_TO_BITS 8

#define MEMORY_ALARM_ID 1001

#define ALARM_REBOOT_EVENT 1003
#define ALARM_REBOOT_ACK_EVENT 1004
#define ALARM_OOM_EVENT 1005
#define ALARM_OOM_ACK_EVENT 1006
#define ALARM_PANIC_EVENT 1007
#define ALARM_PANIC_ACK_EVENT 1008
#define ALARM_KERNEL_REBOOT_EVENT 1009
#define ALARM_KERNEL_REBOOT_ACK_EVENT 1010

#define MINOR_ALM 1
#define MAJOR_ALM 2
#define CRITICAL_ALM 3

#define ALARM_TYPE_OCCUR 1
#define ALARM_TYPE_RECOVER 2

#define MAX_NUM_OF_ALARM_ID 128

#define PATH_REPORT_CPU_ALARM "/var/run/sysSentry/report.sock"
#define MAX_CHAR_LEN 128

/*
 * usAlarmId：unsigned short，告警id，某一类故障一个id，id定义避免重复。
 * ucAlarmLevel: 告警级别，从FATAL到DEBUG
 * ucAlarmType：unsigned char，告警类别，表示告警产生或告警恢复（对用户呈现需要用户操作的故障恢复）
 * AlarmTime：struct timeval，告警生成时间戳
 * pucParas：unsigned char*，告警描述信息
 */
/* socket 通信格式 */
struct alarm_info {
    unsigned short usAlarmId;
    unsigned char ucAlarmLevel;
    unsigned char ucAlarmType;
    struct timeval AlarmTime;
    char pucParas[ALARM_INFO_MAX_PARAS_LEN];
};

enum report_module {
    CPU = 0x00
};
enum report_type {
    CE = 0x00,
    UCE = 0x01
};
enum report_trans_to {
    BMC = 0x01
};

enum report_event_type {
    ASSERTION = 0x00,
    DEASSERTION = 0x01
};

int cpu_alarm_Report(unsigned short type, unsigned short module, unsigned short trans_to, unsigned short command,
                     unsigned short event_type, int socket_id, int core_id);
 
/*
 * hook回调函数处理
 * Notes        : 下述函数不支持多线程,不是信号安全函数
 */
typedef void (*alarm_callback_func)(struct alarm_info *palarm);

struct alarm_subscription_info {
    int id_list[MAX_NUM_OF_ALARM_ID];
    unsigned int len;
};

struct alarm_msg {
    unsigned short usAlarmId;
    struct timeval AlarmTime;
    char pucParas[ALARM_INFO_MAX_PARAS_LEN];
};
 
struct alarm_register {
    int register_fd;
    char alarm_enable_bitmap[MAX_NUM_OF_ALARM_ID];
};
 
int xalarm_report_event(unsigned short usAlarmId, char *pucParas);
int xalarm_register_event(struct alarm_register** register_info, struct alarm_subscription_info id_filter);
int xalarm_get_event(struct alarm_msg* msg, struct alarm_register *register_info);
void xalarm_unregister_event(struct alarm_register *register_info);

int xalarm_Register(alarm_callback_func callback, struct alarm_subscription_info id_filter);
void xalarm_UnRegister(int client_id);
bool xalarm_Upgrade(struct alarm_subscription_info id_filter, int client_id);
 
unsigned short xalarm_getid(const struct alarm_info *palarm);
unsigned char xalarm_gettype(const struct alarm_info *palarm);
unsigned char xalarm_getlevel(const struct alarm_info *palarm);
long long xalarm_gettime(const struct alarm_info *palarm);
char *xalarm_getdesc(const struct alarm_info *palarm);

int xalarm_Report(unsigned short usAlarmId,
        unsigned char ucAlarmLevel,
        unsigned char ucAlarmType,
        char *pucParas);

#define RESULT_REPORT_SOCKET "/var/run/sysSentry/result.sock"
#define RESULT_LEVEL_NUM 6

enum RESULT_LEVEL {
    RESULT_LEVEL_PASS = 0,
    RESULT_LEVEL_FAIL = 1,
    RESULT_LEVEL_SKIP = 2,
    RESULT_LEVEL_MINOR_ALM = 3,
    RESULT_LEVEL_MAJOR_ALM = 4,
    RESULT_LEVEL_CRITICAL_ALM = 5,
};

#define RESULT_INFO_HEAD_LEN 10
#define RESULT_INFO_HEAD_MAGIC "RESULT"
#define RESULT_INFO_MAX_LEN 4096
#define RESULT_INFO_LOG_MGS_MAX_LEN 255

#define RETURN_CODE_FAIL (-1)
#define RETURN_CODE_SUCCESS 0

extern int report_result(const char *task_name,
                         enum RESULT_LEVEL result_level,
                         const char *report_data);

extern int send_data_to_socket(const char *socket_path, const char *message);

#endif
