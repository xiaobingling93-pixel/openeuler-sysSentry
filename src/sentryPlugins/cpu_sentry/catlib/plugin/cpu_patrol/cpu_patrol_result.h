#ifndef CPU_PATROL_RESULT_H
#define CPU_PATROL_RESULT_H

#include <stdio.h>
#include <unistd.h>
#include <sched.h>
#include "cat_structs.h"

#define CPU_PATH_FORMAT "/sys/devices/system/cpu/cpu%d/online"
#define PATROL_RESULT_LEN 512
#define MAX_CPU_SYS_FILE_PATH_LEN 256
#define BMC_COMMAND 0x0001
#define MAX_LINE_LEN 256
#define PAIR_LEN 2

typedef enum {
    CPU_STATE_OFFLINE = '0',
    CPU_STATE_ONLINE = '1',
    CPU_STATE_UNKNOWN = '2'
} cpu_core_state;

#define FILE_NAME(x) ((strrchr(x, '/') == NULL) ? (x) : strrchr(x, '/') + 1)
#define CAT_LOG(level, ...)                                                            \
    do {                                                                               \
        printf("[%s] %s %d %s: ", level, FILE_NAME(__FILE__), __LINE__, __FUNCTION__); \
        printf(__VA_ARGS__);                                                           \
        printf("\n");                                                                  \
    } while (0)

#define CAT_LOG_I(...) CAT_LOG("INFO", __VA_ARGS__)
#define CAT_LOG_W(...) CAT_LOG("WARN", __VA_ARGS__)
#define CAT_LOG_E(...) CAT_LOG("ERROR", __VA_ARGS__)

static inline int get_cpu_count(void)
{
    long n = sysconf(_SC_NPROCESSORS_CONF);
    if (n <= 0) {
        CAT_LOG_W("Warning: Failed to get cpu count, using fallback (4096)\n");
        return 4096;
    }
    return (int)n;
}


#define MAX_CPU_CORES 4096

typedef struct {
    unsigned int order_list[MAX_CPU_CORES];
    unsigned short current_nums;
} core_list_st;

void handle_patrol_result(void);
// 返回巡检隔离的故障核列表
cat_return_t get_patrol_result(cpu_set_t *isolated_cpu_set);
void clear_patrol_result(void);

#endif


