/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2023-2024. All rights reserved.
 * Description: inspection message alarm program
 * Author: Lan Sheng
 * Create: 2023-10-23
 */

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <signal.h>
#include <unistd.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/un.h>
#include <json-c/json.h>
#include <regex.h>
#include <ctype.h>

#include <stddef.h>

#include "register_xalarm.h"

#define DIR_XALARM "/var/run/xalarm"
#define PATH_REG_ALARM "/var/run/xalarm/alarm"
#define PATH_REPORT_ALARM "/var/run/xalarm/report"
#define ALARM_DIR_PERMISSION 0755
#define ALARM_SOCKET_PERMISSION 0666
#define TIME_UNIT_MILLISECONDS 1000

#define MAX_PARAS_LEN 8191
#define MIN_ALARM_ID 1001
#define MAX_ALARM_ID (MIN_ALARM_ID + MAX_NUM_OF_ALARM_ID - 1)

#define ALARM_ENABLED 1
#define RECV_DELAY_MSEC 100
#define TASK_NAME_MAX_LEN 256

struct alarm_register_info {
    char alarm_enable_bitmap[MAX_NUM_OF_ALARM_ID];
    int register_fd;
    pthread_t register_tid;
    bool is_registered;
    alarm_callback_func callback;
    int thread_should_stop;
};

const char *g_result_level_string[] = {
    "PASS",
    "FAIL",
    "SKIP",
    "MINOR_ALM",
    "MAJOR_ALM",
    "CRITICAL_ALM",
};

struct alarm_register_info g_register_info = {{0}, -1, ULONG_MAX, false, NULL, 1};

static bool id_is_registered(unsigned short alarm_id)
{
    if (alarm_id < MIN_ALARM_ID || alarm_id > MAX_ALARM_ID) {
        return false;
    }

    return g_register_info.alarm_enable_bitmap[alarm_id - MIN_ALARM_ID] == ALARM_ENABLED;
}

static void put_alarm_info(struct alarm_info *info)
{
    if ((g_register_info.callback != NULL) && (info != NULL) && (id_is_registered(info->usAlarmId))) {
        g_register_info.callback(info);
    }
}

static int create_unix_socket(const char *path)
{
    struct sockaddr_un alarm_addr;
    int fd = -1;
    int ret = 0;
    int flags;

    if (path == NULL || path[0] == '\0') {
        printf("create_unix_socket path is null");
        return -1;
    }

    fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) {
        printf("socket failed:%s\n", strerror(errno));
        return -1;
    }
    flags = fcntl(fd, F_GETFL, 0);
    ret = fcntl(fd, F_SETFL, flags | O_NONBLOCK);
    if (ret == -1) {
        printf("%s: fcntl setfl failed\n", __func__);
        goto release_socket;
    }

    if (access(DIR_XALARM, F_OK) == -1) {
        if (mkdir(DIR_XALARM, ALARM_DIR_PERMISSION) == -1) {
            printf("mkdir %s failed\n", DIR_XALARM);
            goto release_socket;
        }
    }

    if (memset(&alarm_addr, 0, sizeof(alarm_addr)) == NULL) {
        printf("create_unix_socket:  memset alarm_addr failed, ret: %d\n", ret);
        goto release_socket;
    }
    alarm_addr.sun_family = AF_UNIX;
    strncpy(alarm_addr.sun_path, path, sizeof(alarm_addr.sun_path) - 1);

    if (connect(fd, (struct sockaddr*)&alarm_addr, sizeof(alarm_addr)) == -1) {
        printf("create_unix_socket:  connect alarm_addr failed, ret: %d\n", ret);
        goto release_socket;
    }

    return fd;

release_socket:
    (void)close(fd);

    return -1;
}

static void *alarm_recv(void *arg)
{
    int recvlen = 0;
    struct alarm_info info;
    int ret = 0;
    
    /* prctl does not return false if arg2 is right when arg1 is PR_SET_NAME */
    ret = prctl(PR_SET_NAME, "register-recv");
    if (ret != 0) {
        printf("alarm_recv: prctl set thread name failed\n");
        return NULL;
    }
    while (!g_register_info.thread_should_stop) {
        recvlen = recv(g_register_info.register_fd, &info, sizeof(struct alarm_info), 0);
        if (recvlen == (int)sizeof(struct alarm_info)) {
            put_alarm_info(&info);
        } else if (recvlen < 0) {
            if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) {
                usleep(RECV_DELAY_MSEC * TIME_UNIT_MILLISECONDS);
                continue;
            }
            printf("recv error len:%d errno:%d\n", recvlen, errno);
        } else if (recvlen == 0) {
            printf("connection closed by xalarmd, maybe connections reach max num or service stopped.\n");
            g_register_info.thread_should_stop = 1;
            break;
        }
    }
    return NULL;
}

static pthread_t create_thread(void)
{
    int ret;
    pthread_t t_id = ULONG_MAX;

    ret = pthread_create(&t_id, NULL, alarm_recv, NULL);
    if (ret < 0) {
        printf("create_thread: pthread_create error ret:%d\n", ret);
        t_id = ULONG_MAX;
    }
    return t_id;
}

static void set_alarm_id(struct alarm_subscription_info id_filter)
{
    int i;

    memset(g_register_info.alarm_enable_bitmap, 0, MAX_NUM_OF_ALARM_ID * sizeof(char));
    for (i = 0; i < id_filter.len; i++) {
        g_register_info.alarm_enable_bitmap[id_filter.id_list[i] - MIN_ALARM_ID] = ALARM_ENABLED;
    }
}

static bool alarm_subscription_verify(struct alarm_subscription_info id_filter)
{
    int i;

    if (id_filter.len > MAX_NUM_OF_ALARM_ID) {
        return false;
    }

    for (i = 0; i < id_filter.len; i++) {
        if (id_filter.id_list[i] < MIN_ALARM_ID || id_filter.id_list[i] > MAX_ALARM_ID) {
            return false;
        }
    }
    return true;
}

bool xalarm_Upgrade(struct alarm_subscription_info id_filter, int client_id)
{
    if (!g_register_info.is_registered) {
        printf("%s: alarm has not registered, cannot upgrade\n", __func__);
        return false;
    }

    if (!alarm_subscription_verify(id_filter) || client_id != 0) {
        printf("%s: invalid args\n", __func__);
        return false;
    }
    if (g_register_info.thread_should_stop) {
        printf("%s: upgrade failed, alarm thread has stopped\n", __func__);
        return false;
    }
    set_alarm_id(id_filter);

    return true;
}

int xalarm_Register(alarm_callback_func callback, struct alarm_subscription_info id_filter)
{
    if (g_register_info.is_registered || (g_register_info.register_fd != -1) ||
        (g_register_info.register_tid != ULONG_MAX)) {
        printf("%s: alarm has registered\n", __func__);
        return -1;
    }

    if (!alarm_subscription_verify(id_filter) || callback == NULL) {
        printf("%s: param is invalid\n", __func__);
        return -1;
    }

    g_register_info.register_fd = create_unix_socket(PATH_REG_ALARM);
    if (g_register_info.register_fd == -1) {
        printf("%s: create_unix_socket failed\n", __func__);
        return -1;
    }

    g_register_info.thread_should_stop = 0;
    g_register_info.register_tid = create_thread();
    if (g_register_info.register_tid == ULONG_MAX) {
        printf("%s: create_thread failed\n", __func__);
        (void)close(g_register_info.register_fd);
        g_register_info.register_fd = -1;
        g_register_info.thread_should_stop = 1;
        return -1;
    }

    set_alarm_id(id_filter);
    g_register_info.callback = callback;
    g_register_info.is_registered = true;
    return 0;
}

void xalarm_UnRegister(int client_id)
{
    if (!g_register_info.is_registered) {
        printf("%s: alarm has not registered\n", __func__);
        return;
    }

    if (client_id != 0) {
        printf("%s: invalid client\n", __func__);
        return;
    }

    if (g_register_info.register_tid != ULONG_MAX) {
        g_register_info.thread_should_stop = 1;
        pthread_join(g_register_info.register_tid, NULL);
        g_register_info.register_tid = ULONG_MAX;
    }

    if (g_register_info.register_fd != -1) {
        (void)close(g_register_info.register_fd);
        g_register_info.register_fd = -1;
    }

    memset(g_register_info.alarm_enable_bitmap, 0, MAX_NUM_OF_ALARM_ID * sizeof(char));
    g_register_info.callback = NULL;
    g_register_info.is_registered = false;
}

/* return 0 if invalid id\level\type */
unsigned short xalarm_getid(const struct alarm_info *palarm)
{
    return palarm == NULL ? 0 : palarm->usAlarmId;
}

unsigned char xalarm_getlevel(const struct alarm_info *palarm)
{
    return palarm == NULL ? 0 : palarm->ucAlarmLevel;
}

unsigned char xalarm_gettype(const struct alarm_info *palarm)
{
    return palarm == NULL ? 0 : palarm->ucAlarmType;
}

long long xalarm_gettime(const struct alarm_info *palarm)
{
    return palarm == NULL ? 0 : ((long long)(palarm->AlarmTime.tv_sec) * TIME_UNIT_MILLISECONDS +
            (long long)(palarm->AlarmTime.tv_usec) / TIME_UNIT_MILLISECONDS);
}

char *xalarm_getdesc(const struct alarm_info *palarm)
{
    return palarm == NULL ? NULL : (char *)palarm->pucParas;
}

static int init_report_addr(struct sockaddr_un *alarm_addr, char *report_path)
{
    if (alarm_addr == NULL) {
        fprintf(stderr, "%s: alarm_addr is null\n", __func__);
        return -1;
    }

    if (memset(alarm_addr, 0, sizeof(struct sockaddr_un)) == NULL) {
        fprintf(stderr, "%s: memset  alarm_addr failed\n", __func__);
        return -1;
    }
    alarm_addr->sun_family = AF_UNIX;
    strncpy(alarm_addr->sun_path, report_path, sizeof(alarm_addr->sun_path) - 1);

    return 0;
}

int xalarm_Report(unsigned short usAlarmId, unsigned char ucAlarmLevel,
    unsigned char ucAlarmType, char *pucParas)
{
    int ret = 0, fd;
    struct alarm_info info;
    struct sockaddr_un alarm_addr;

    if ((usAlarmId < MIN_ALARM_ID || usAlarmId > MAX_ALARM_ID) ||
        (ucAlarmLevel < MINOR_ALM || ucAlarmLevel > CRITICAL_ALM) ||
        (ucAlarmType < ALARM_TYPE_OCCUR || ucAlarmType > ALARM_TYPE_RECOVER)) {
        fprintf(stderr, "%s: alarm info invalid\n", __func__);
        return -1;
    }

    if (pucParas == NULL || (int)strlen(pucParas) > MAX_PARAS_LEN) {
        fprintf(stderr, "%s: alarm info invalid\n", __func__);
        return -1;
    }

    if (memset(&info, 0, sizeof(struct alarm_info)) == NULL) {
        fprintf(stderr, "%s: memset info failed\n", __func__);
        return -1;
    }
    info.usAlarmId = usAlarmId;
    info.ucAlarmLevel = ucAlarmLevel;
    info.ucAlarmType = ucAlarmType;
    gettimeofday(&info.AlarmTime, NULL);
    if (pucParas != NULL) {
        strncpy((char *)info.pucParas, (char *)pucParas, MAX_PARAS_LEN - 1);
    }

    fd = socket(AF_UNIX, SOCK_DGRAM, 0);
    if (fd < 0) {
        fprintf(stderr, "%s socket create error: %s\n", __func__, strerror(errno));
        return -ENODEV;
    }

    ret = init_report_addr(&alarm_addr, PATH_REPORT_ALARM);
    if (ret == -1) {
        close(fd);
        return -1;
    }

    while (true) {
        ret = sendto(fd, &info, sizeof(struct alarm_info), 0, (struct sockaddr *)&alarm_addr,
            sizeof(alarm_addr.sun_family) + strlen(alarm_addr.sun_path));
        if (ret < 0) {
            if (errno == EINTR) {
                /* interrupted by signal, ignore */
                continue;
            } else {
                fprintf(stderr, "%s: sendto failed errno: %d\n", __func__, errno);
            }
        } else if (ret == 0) {
            fprintf(stderr, "%s: sendto failed, ret is 0\n", __func__);
        } else {
            if (ret != (int)sizeof(struct alarm_info)) {
                fprintf(stderr, "%s sendto failed, ret:%d, len:%u\n", __func__, ret, sizeof(struct alarm_info));
            }
        }
        break;
    }
    close(fd);

    return (ret > 0) ? 0 : -1;
}


bool is_valid_report_module(unsigned short module) {
    switch ((int) module) {
        case CPU:
            return true;
        default:
            return false;
    }
}

bool is_valid_report_type(unsigned short type) {
    switch ((int) type) {
        case CE:
        case UCE:
            return true;
        default:
            return false;
    }
}

bool is_valid_report_trans_to(unsigned short trans_to) {
    switch ((int) trans_to) {
        case BMC:
            return true;
        default:
            return false;
    }
}

bool check_params(unsigned short type, unsigned short module, unsigned short trans_to, int report_info_len) {
    bool is_valid_type = is_valid_report_type(type);
    bool is_valid_module = is_valid_report_module(module);
    bool is_valid_trans_to = is_valid_report_trans_to(trans_to);
    bool is_valid_report_info_len = (report_info_len >= 0 && report_info_len <= 999) ? true : false;

    return is_valid_type && is_valid_module && is_valid_trans_to && is_valid_report_info_len;
}

int cpu_alarm_Report(unsigned short type, unsigned short module, unsigned short trans_to, unsigned short command,
                     unsigned short event_type, int socket_id, int core_id)
{
    int ret, fd;
    bool is_valid;
    int report_info_len;
    char report_info[MAX_CHAR_LEN];
    char alarm_msg[MAX_CHAR_LEN];
    struct sockaddr_un alarm_addr;

    fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) {
        fprintf(stderr, "%s socket create error: %s\n", __func__, strerror(errno));
        return -1;
    }

    ret = init_report_addr(&alarm_addr, PATH_REPORT_CPU_ALARM);
    if (ret == -1) {
        close(fd);
        return -1;
    }

    sprintf(report_info, "%u %u %d %d", command, event_type, socket_id, core_id);

    report_info_len = strlen(report_info);
    is_valid = check_params(type, module, trans_to, report_info_len);
    if (!is_valid) {
        fprintf(stderr, "%s: cpu_alarm: invalid params\n", __func__);
        close(fd);
        return -1;
    }

    sprintf(alarm_msg, "REP%1u%1u%02u%03d%s", type, module, trans_to, report_info_len, report_info);

    while (true) {
        ret = connect(fd, (struct sockaddr *)&alarm_addr, offsetof(struct sockaddr_un, sun_path) + strlen(alarm_addr.sun_path));

        if (ret < 0) {
            if (errno == EINTR) {
                /* interrupted by signal, ignore */
                continue;
            } else {
                fprintf(stderr, "%s: connect failed errno: %d\n", __func__, errno);
            }
        }
        
        ret = write(fd, alarm_msg, strlen(alarm_msg));
        if (ret < 0) {
            if (errno == EINTR) {
                /* interrupted by signal, ignore */
                continue;
            } else {
                fprintf(stderr, "%s: write failed errno: %d\n", __func__, errno);
            }
        } else if (ret == 0) {
            fprintf(stderr, "%s: write failed, ret is 0\n", __func__);
        } else {
            if (ret != strlen(alarm_msg)) {
                fprintf(stderr, "%s write failed, ret:%d, len:%d\n", __func__, ret, strlen(alarm_msg));
            }
        }
        break;
    }
    close(fd);

    return (ret > 0) ? 0 : -1;
}


/**
 * @brief send data to socket
 *
 * @param socket_path unix socket file path
 * @param message string data to send, must end in '\0'
 * @return int success or not, 0 means success, -1 means failure
 */
int send_data_to_socket(const char *socket_path, const char *message)
{
    int sockfd;
    int ret;
    struct sockaddr_un addr;

    // initialize socket
    sockfd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (sockfd == -1) {
        fprintf(stderr, "failed to create socket\n");
        return RETURN_CODE_FAIL;
    }

    // set socket address
    if (memset(&addr, 0, sizeof(struct sockaddr_un)) == NULL) {
        fprintf(stderr, "%s: memset info failed.\n", __func__);
        close(sockfd);
        return RETURN_CODE_FAIL;
    }

    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, socket_path, sizeof(addr.sun_path) - 1);
    // connect socket
    if (connect(sockfd, (struct sockaddr *)&addr, sizeof(struct sockaddr_un)) == -1) {
        fprintf(stderr, "failed to connect socket %s\n", socket_path);
        close(sockfd);
        return RETURN_CODE_FAIL;
    }

    // write data
    if (write(sockfd, message, strlen(message)) == -1) {
        fprintf(stderr, "failed to send data to socket %s\n", socket_path);
        close(sockfd);
        return RETURN_CODE_FAIL;
    }

    close(sockfd);
    return RETURN_CODE_SUCCESS;
}


static bool is_valid_task_name(const char *task_name)
{
    if (task_name == NULL) {
        fprintf(stderr, "task_name is null\n");
        return false;
    }

    if (!isalpha(task_name[0])) {
        fprintf(stderr, "task_name does not start with an English letter\n");
        return false;
    }

    if (strlen(task_name) > TASK_NAME_MAX_LEN) {
        fprintf(stderr, "task_name is too long\n");
        return false;
    }

    int ret;

    const char *pattern_task_name = "^[a-zA-Z][a-zA-Z0-9_]*$";
    regex_t regex_task_name;

    ret = regcomp(&regex_task_name, pattern_task_name, REG_EXTENDED);
    if (ret) {
        fprintf(stderr, "Could not compile regex\n");
        return false;
    }

    ret = regexec(&regex_task_name, task_name, 0, NULL, 0);
    if (ret) {
        fprintf(stderr, "'task_name' (%s) contains illegal characters\n", task_name);
        regfree(&regex_task_name);
        return false;
    }

    regfree(&regex_task_name);
    return true;
}


/**
 * @brief send result to sysSentry
 *
 * @param task_name task name, eg. "memory_sentry"
 * @param result_level result level, eg. RESULT_LEVEL_PASS
 * @param report_data result details info, Character string converted from the JSON format.
 * @return int success or not, 0 means success, -1 means failure
 */
int report_result(const char *task_name, enum RESULT_LEVEL result_level, const char *report_data)
{
    int ret = RETURN_CODE_FAIL;
    if (result_level < 0 || result_level >= RESULT_LEVEL_NUM) {
        fprintf(stderr, "result_level (%d) is invalid, it must be in [0-5]\n", result_level);
        return ret;
    }

    if (!is_valid_task_name(task_name)) {
        return ret;
    }

    json_object *send_data = json_object_new_object();
    json_object *result_data = json_object_new_object();
    json_object_object_add(result_data, "result", json_object_new_string(g_result_level_string[result_level]));
    // The null pointer does not need to be determined. json_object_new_string () can receive null pointers.
    json_object_object_add(result_data, "details", json_object_new_string(report_data));
    json_object_object_add(send_data, "result_data", result_data);
    json_object_object_add(send_data, "task_name", json_object_new_string(task_name));

    const char *result_json_string = json_object_to_json_string(send_data);
    if (result_json_string == NULL) {
        fprintf(stderr, "%s: json_object_to_json_string return NULL", __func__);
        goto free_json;
    }

    int send_data_len = strlen(result_json_string);
    if (send_data_len > RESULT_INFO_MAX_LEN) {
        fprintf(stderr, "%s: failed to send result message (%s) to sysSentry! send data is too long (%d) > (%d)\n",
                __func__, result_json_string, send_data_len, RESULT_INFO_MAX_LEN);
        goto free_json;
    }

    char *message = (char *)calloc(RESULT_INFO_HEAD_LEN + RESULT_INFO_MAX_LEN, sizeof(char));
    if (!message) {
        fprintf(stderr, "Failed to allocate memory!");
        goto free_json;
    }

    sprintf(message, "%s%04d%s", RESULT_INFO_HEAD_MAGIC, send_data_len, result_json_string);

    if (send_data_to_socket(RESULT_REPORT_SOCKET, message)) {
        fprintf(stderr, "%s: failed to send result message (%s) to sysSentry!\n", __func__, message);
        goto free_msg;
    }

    ret = RETURN_CODE_SUCCESS;
free_msg:
    free(message);
    message = NULL;
free_json:
    json_object_put(send_data);
    return ret;
}

int xalarm_register_event(struct alarm_register **register_info, struct alarm_subscription_info id_filter)
{
    int i;
    // check whether id_filter is valid
    if (register_info == NULL || !alarm_subscription_verify(id_filter)) {
        return -EINVAL;
    }

    *register_info = (struct alarm_register *)malloc(sizeof(struct alarm_register));
    // failed to malloc memory for register_info struct
    if (*register_info == NULL) {
        return -ENOMEM;
    }

    // transform id_filter(eg:[1001, 1002]) into bitmap(eg:[true, true, false, ..., false])
    memset((*register_info)->alarm_enable_bitmap, 0, MAX_NUM_OF_ALARM_ID * sizeof(char));
    for (i = 0; i < id_filter.len; i++) {
        (*register_info)->alarm_enable_bitmap[id_filter.id_list[i] - MIN_ALARM_ID] = ALARM_ENABLED;
    }

    // establish connection between xalarmd and this program
    (*register_info)->register_fd = create_unix_socket(PATH_REG_ALARM);
    if ((*register_info)->register_fd == -1) {
        free(*register_info);
        return -ENOTCONN;
    }

    return 0;
}

void xalarm_unregister_event(struct alarm_register *register_info)  
{
    if (register_info == NULL) {
        return;
    }
    // close client fd socket connection resource
    if (register_info->register_fd != -1) {
        (void)close(register_info->register_fd);
        register_info->register_fd = -1;
    }

    free(register_info);
}

int xalarm_get_event(struct alarm_msg* msg, struct alarm_register *register_info)
{
    struct alarm_info info;
    
    if (msg == NULL || register_info == NULL) {
        return -EINVAL;
    }

    while (true) {
        int recvlen = recv(register_info->register_fd, &info, sizeof(struct alarm_info), 0);

        // recvlen < 0 means that we meet with error when recv.
        if (recvlen < 0) {
            // when recv EINTR or EAGAIN or EWOULDBLOCK signal, we should try again.
            // EINTR means recv func interrupted by signal
            // EAGIAN and EWOULDBLOCK means recv has been blocked(in nonblock mode)
            if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) {
                usleep(RECV_DELAY_MSEC * TIME_UNIT_MILLISECONDS);
                continue;
            } else {
                // otherwise means we meet up with some unrecoverable error
                // ECONNRESET means server closed the connection for some error
                // EBADF means this filr descriptor is invalid
                // ENOMEM means out of memory
                // EFAULT means invalid buffer address
                close(register_info->register_fd);
                return -errno;
            }
        }
        // recvlen == 0 means the connection has been properly closed, 
        // and the remote end has no more data to send.
        if (recvlen == 0) {
            close(register_info->register_fd);
            return -ENOTCONN;
        }
        // if recvlen == sizeof(alarm_info), that means we recieved data correctlly
        // why use alarm_info rather than alarm_msg? alarm_info is used for old
        // api, it's a communication protocol between xalarmd service and libxalarm.
        // to be compatible with old api and reduce modification to xalarmd, use
        // alarm_info for communication and return alarm_msg(alarm_msg is subset of
        // alarm_info).
        if (recvlen == (int)sizeof(struct alarm_info)) {
            // filter alarm id, alarm id reciecved which is not registered by this program
            // will be ignored and continue to wait for next msg
            if (info.usAlarmId < MIN_ALARM_ID || info.usAlarmId > MAX_ALARM_ID || 
                    register_info->alarm_enable_bitmap[info.usAlarmId - MIN_ALARM_ID] != ALARM_ENABLED) {
                continue;
            }
            msg->usAlarmId = info.usAlarmId;
            msg->AlarmTime = info.AlarmTime;
            strncpy((char *)msg->pucParas, (char *)info.pucParas, MAX_PARAS_LEN - 1);
            // no need to close fd because get_event() can be reused after recv one msg
            return 0;
        }
        // if recvlen > 0 but not equal to sizeof alarm_info, loop to wait for msg
    }
}

int xalarm_report_event(unsigned short usAlarmId, char *pucParas)
{
    int ret, fd;
    struct alarm_info info;
    struct sockaddr_un alarm_addr;

    if (usAlarmId < MIN_ALARM_ID || usAlarmId > MAX_ALARM_ID) {
        return -EINVAL;
    }

    if (pucParas == NULL || (int)strlen(pucParas) > MAX_PARAS_LEN) {
        return -EINVAL;
    }

    memset(&info, 0, sizeof(struct alarm_info));
    info.usAlarmId = usAlarmId;
    info.ucAlarmLevel = MINOR_ALM;
    info.ucAlarmType = ALARM_TYPE_OCCUR;
    gettimeofday(&info.AlarmTime, NULL);
    strncpy((char *)info.pucParas, (char *)pucParas, MAX_PARAS_LEN - 1);


    fd = socket(AF_UNIX, SOCK_DGRAM, 0);
    if (fd < 0) {
        fprintf(stderr, "%s socket create error: %s\n", __func__, strerror(errno));
        return -ENODEV;
    }

    ret = init_report_addr(&alarm_addr, PATH_REPORT_ALARM);
    if (ret == -1) {
        close(fd);
        return -ENOTCONN;
    }

    while (true) {
        ret = sendto(fd, &info, sizeof(struct alarm_info), 0, (struct sockaddr *)&alarm_addr,
            sizeof(alarm_addr.sun_family) + strlen(alarm_addr.sun_path));
        // if errno == EINTR means sendto has been interrupted by system, should retry
        if (ret < 0 && errno == EINTR) {
            continue;
        }
        break;
    }

    close(fd);

    if (ret != (int)sizeof(struct alarm_info)) {
        return -ECOMM;
    }
    return (ret > 0) ? 0 : -errno;
}


