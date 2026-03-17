#define _GNU_SOURCE
#include <unistd.h>
#include <stdio.h>
#include <string.h>
#include <fcntl.h>
#include <stdlib.h>
#include <errno.h>
#include <stdbool.h>
#include <xalarm/register_xalarm.h>

#include "cat_structs.h"
#include "cpu_patrol_result.h"

core_list_st g_isolated_core_list = { 0 };

/*
 * 功能说明：把核id插入到数组里面，递增排序
 */
static cat_return_t insert_core_to_list(core_list_st *core_list, int coreid)
{
    if (coreid == 0) {
        CAT_LOG_W("Core %d is a special core and cannot be isolated", coreid);
        return CAT_OK;
    }
    if (coreid < 0) {
        CAT_LOG_W("Inner error, coreid is a negative number");
        return CAT_ERR;
    }

    if (core_list->current_nums >= MAX_CPU_CORES) {
        CAT_LOG_W("current cpu nums exceeds the maximum capacity (%d)", MAX_CPU_CORES);
        return CAT_OK;
    }

    bool if_insert = false;
    for (unsigned short i = 0; i < core_list->current_nums; i++) {
        if (core_list->order_list[i] < (unsigned int)coreid) {
            continue;
        } else if (core_list->order_list[i] == (unsigned int)coreid) {
            // 已存在，无需重复插入
            if_insert = true;
            break;
        }
        for (unsigned short j = core_list->current_nums - 1; j >= i; j--) {
            core_list->order_list[j + 1] = core_list->order_list[j];
            if (j == 0) {
                break;
            }
        }
        core_list->order_list[i] = coreid;
        core_list->current_nums++;
        if_insert = true;
        break;
    }

    // 在数组末尾插入
    if (!if_insert) {
        core_list->order_list[core_list->current_nums] = coreid;
        core_list->current_nums++;
    }

    return CAT_OK;
}

/*
 * 功能说明：巡检结果“1-3,7,9,12-15”,解析时先按逗号切割，再按短横线切割
 */
static cat_return_t parse_patrol_result(char *buf, core_list_st *fault_list)
{
    const int number_base = 10; // 字符串转十进制
    char coma_split[] = ",";
    char line_split[] = "-";
    while (true) {
        char *split = strtok_r(buf, coma_split, &buf);
        if (split == NULL) {
            break;
        }
        char *sub_save_ptr = NULL;
        char *subSplit = strtok_r(split, line_split, &sub_save_ptr);
        int coreid_before = (int) strtol(subSplit, NULL, number_base);
        int coreid_after = strcmp(sub_save_ptr, "") == 0 ? -1 : (int) strtol(sub_save_ptr, NULL, 10);
        if (coreid_after < 0) {
            insert_core_to_list(fault_list, coreid_before);
        } else {
            for (int i = coreid_before; i <= coreid_after; i++) {
                insert_core_to_list(fault_list, i);
            }
        }
    }
    return CAT_OK;
}

static cat_return_t get_result(char *buf, int buf_len)
{
    int fd = open("/sys/devices/system/cpu/cpuinspect/result", O_RDONLY);
    if (fd < 0) {
        CAT_LOG_E("Open cpu_utility file fail, %s", strerror(errno));
        return CAT_ERR;
    }

    int count = read(fd, buf, buf_len);
    if (count <= 0) {
        CAT_LOG_E("Read error, count %d", count);
        close(fd);
        return CAT_ERR;
    }
    buf[count - 1] = '\0'; // read返回包涵换行符‘\n’，把‘\n'换成结束符
    close(fd);

    return CAT_OK;
}

static int open_cpu_sys_file(unsigned int cpu, int oflag)
{
    char path[MAX_CPU_SYS_FILE_PATH_LEN] = {0};
    int ret = snprintf(path, sizeof(path), CPU_PATH_FORMAT, cpu);
    if (ret <= 0) {
        CAT_LOG_E("Get cpu sys file path fail, %d", ret);
        return -1;
    }

    int fd = open(path, oflag);
    if (fd < 0) {
        CAT_LOG_E("Open cpu sys file fail, %s", strerror(errno));
        return -1;
    }

    return fd;
}

// 获取指定cpu的状态信息(主要是是否在线或离线)
static char get_cpu_core_status(unsigned int cpu)
{
    // 打开online文件
    int fd = open_cpu_sys_file(cpu, O_RDONLY);
    if (fd == -1) {
        return CPU_STATE_UNKNOWN;
    }
    char buf = CPU_STATE_UNKNOWN;
    if (read(fd, &buf, sizeof(buf)) <= 0) {
        CAT_LOG_E("Read cpu state fail");
        close(fd);
        return CPU_STATE_UNKNOWN;
    }
    close(fd);

    return buf;
}

static cat_return_t do_cpu_core_offline(unsigned int cpu)
{
    int fd = open_cpu_sys_file(cpu, O_RDWR);
    if (fd == -1) {
        return CAT_ERR;
    }

    char buf[2] = "";
    buf[0] = CPU_STATE_OFFLINE;
    buf[1] = '\0';

    ssize_t rc = write(fd, buf, strlen(buf));
    close(fd);
    if (rc < 0) {
        CAT_LOG_E("CPU%d offline failed, errno:%d", cpu, errno);
        return CAT_ERR;
    }
    /* 检测是否下线成功 */
    if (get_cpu_core_status(cpu) == CPU_STATE_OFFLINE) {
        return CAT_OK;
    }

    return CAT_ERR;
}

/*
 * 解析字符串(\d, \d)为一个pair
*/
void parse_string(char* str, int* arr, int size) {
    char* token;
    int i = 0;
    
    token = strtok(str, ",");
    while (token != NULL && i < size) {
        arr[i] = atoi(token);
        i++;
        token = strtok(NULL, ",");
    }
}

/*
 * 根据core_id获取socket_id
*/
int get_socket_id(int core_id) {
    FILE *file;
    char line[MAX_LINE_LEN];
    int id_pair[PAIR_LEN];
    int socket_id;

    file = popen("lscpu -p=cpu,socket | grep '[0-9]\\+,[0-9]\\+'", "r");
    if (file == NULL) {
        perror("Error opening file");
        return -1;
    }

    while (fgets(line, MAX_LINE_LEN, file) != NULL) {
        parse_string(line, id_pair, 2);
        if (id_pair[0] == core_id) {
            return id_pair[1];
        }
    }

    fclose(file);
    return -1;
}

/*
 * 功能说明：隔离巡检故障核，并把成功隔离的故障核添加到隔离列表
 */

void isolate_cpu_core(core_list_st *isolated_core_list, const core_list_st *fault_list)
{
    int ret, core_id, socket_id;
    unsigned int total_core = sysconf(_SC_NPROCESSORS_CONF);
    if (total_core == -1) {
        CAT_LOG_E("Get total cpu cores failed.");
        return;
    }
    for (unsigned short i = 0; i < fault_list->current_nums; i++) {
        core_id = fault_list->order_list[i];
        socket_id = get_socket_id(core_id);
        // 0核不隔离
        if ((core_id >= total_core) || (core_id == 0)) {
            CAT_LOG_E("Isolate cpu core failed, invalid core id(%u)", core_id);
            continue;
        }
        if (get_cpu_core_status(core_id) != CPU_STATE_ONLINE) {
            continue;
        }
        if (socket_id == -1) {
            CAT_LOG_E("Get socket id failed, core id is (%u)", core_id);
        } else {
            int ret = cpu_alarm_Report(UCE, CPU, BMC, BMC_COMMAND, ASSERTION, socket_id, core_id);
            if (ret != 0) {
                CAT_LOG_E("Failed to report to xlarm");
            }
        }
        if (do_cpu_core_offline(core_id) == CAT_OK) {
            (void)insert_core_to_list(isolated_core_list, core_id);
            CAT_LOG_I("<ISOLATE-CORE>:%d", core_id);
        }
    }
}

/*
 * 功能说明：把列表1,2,3,10,22,23,24转换成"1-3,10,22,24"形式字符串
 */
static cat_return_t get_core_list_str(const core_list_st *core_list, char *out_str, unsigned short out_str_len)
{
    if (core_list->current_nums == 0) {
        *out_str = '\0';
        return CAT_OK;
    }

    char buf[PATROL_RESULT_LEN] = {0};
    char tmp_buf[PATROL_RESULT_LEN] = {0};
    unsigned int begin_cpuid = core_list->order_list[0];
    unsigned int end_cpuid = begin_cpuid;

    for (unsigned short i = 1; i < core_list->current_nums; i++) {
        if (core_list->order_list[i] == (end_cpuid + 1)) {
            end_cpuid++;
            continue;
        }

        if (begin_cpuid == end_cpuid) {
            (void)snprintf(tmp_buf, sizeof(tmp_buf), "%u", begin_cpuid);
        } else {
            (void)snprintf(tmp_buf, sizeof(tmp_buf), "%u-%u", begin_cpuid, end_cpuid);
        }
        (void)strncat(buf, tmp_buf, sizeof(buf) - strlen(buf) - 1);
        (void)strncat(buf, ",", sizeof(buf) - strlen(buf) - 1);

        end_cpuid = core_list->order_list[i];
        begin_cpuid = end_cpuid;
    }
    if (begin_cpuid == end_cpuid) {
        (void)snprintf(tmp_buf, sizeof(tmp_buf), "%u", begin_cpuid);
    } else {
        (void)snprintf(tmp_buf, sizeof(tmp_buf), "%u-%u", begin_cpuid, end_cpuid);
    }
    (void)strncat(buf, tmp_buf, sizeof(buf) - strlen(buf) - 1);

    int ret = snprintf(out_str, out_str_len, "%s", buf);
    if (ret < 0 || ret >= out_str_len) {
        CAT_LOG_E("snprintf failed");
        return CAT_ERR;
    }
    return CAT_OK;
}

static cat_return_t get_core_list(const core_list_st *core_list, cpu_set_t *cpu_set)
{
    if (core_list->current_nums == 0) {
        return CAT_OK;
    }

    for (unsigned short i = 0; i < core_list->current_nums; i++) {
        CPU_SET(core_list->order_list[i], cpu_set);
    }

    return CAT_OK;
}

void handle_patrol_result(void)
{
    char buf[PATROL_RESULT_LEN] = {0};
    if (get_result(buf, PATROL_RESULT_LEN) != CAT_OK) {
        return;
    }

    if (buf[0] == '\0') {
        return;
    }

    int max_cpu_number = get_cpu_count();
    if (max_cpu_number > MAX_CPU_CORES) {
        CAT_LOG_W("the cpu num in the current environment exceeds the num supported by the catcli");
    }

    // 记录巡检过程中发现的故障核
    CAT_LOG_W("Found fault cores:[%s]", buf);

    // 获取巡检故障核
    core_list_st fault_list = { 0 };
    if (parse_patrol_result(buf, &fault_list) != CAT_OK) {
        return;
    }

    // 隔离巡检故障核，并把成功隔离的故障核添加到隔离列表
    isolate_cpu_core(&g_isolated_core_list, &fault_list);
}

/*
 * 功能说明：返回巡检隔离的故障核列表
 */
cat_return_t get_patrol_result(cpu_set_t *isolated_cpu_set)
{
    return get_core_list(&g_isolated_core_list, isolated_cpu_set);
}

void clear_patrol_result(void)
{
    (void)memset(&g_isolated_core_list, 0, sizeof(g_isolated_core_list));
}

