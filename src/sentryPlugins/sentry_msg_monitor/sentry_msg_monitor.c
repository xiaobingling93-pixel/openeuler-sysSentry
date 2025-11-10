/*
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * sysSentry is licensed under the Mulan PSL v2.
 * You can use this software according to the terms and conditions of the Mulan PSL v2.
 * You may obtain a copy of Mulan PSL v2 at:
 *     http://license.coscl.org.cn/MulanPSL2
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
 * PURPOSE.
 * See the Mulan PSL v2 for more details.

 * Description: sentry msg monitor
 * Author: Luckky
 * Create: 2025-02-18
 */

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <string.h>
#include <errno.h>
#include <pthread.h>
#include <time.h>
#include <json-c/json.h>
#include <libobmm.h>

#include "register_xalarm.h"
#include "log_utils.h"
#include "smh_common_type.h"
#include "ub_fault_lib.h"

#define TOOL_NAME "sentry_msg_monitor"
#define SMH_DEV_PATH "/dev/sentry_msg_helper"
#define PID_FILE_PATH "/var/run/"TOOL_NAME".pid"
#define ID_LIST_LENGTH 4  //reboot oom panic kernel_reboot
#define MSG_STR_MAX_LEN 1024
#define DEFAULT_LOG_LEVEL LOG_INFO
#define MAX_RETRY_NUM 3
#define RETRY_PERIOD 1
#define XALARM_GENERAL_MSG_ITEM_CNT 2 // msgid_res
#define XALARM_PANIC_MSG_ITEM_CNT 4 // msgid_{cna:cna,eid:eid}_res
#define PYHS_ADDR_HEX_STR_MAX_LEN 20

struct receiver_cleanup_data {
    struct alarm_msg *al_msg;
    struct alarm_register* register_info;
};

static int handle_file_lock(int fd, bool lock)
{
    int ret;
    struct flock fl;
    fl.l_type   = lock ? F_WRLCK : F_UNLCK;
    fl.l_whence = SEEK_SET;
    fl.l_start  = 0;
    fl.l_len    = 0;

    ret = fcntl(fd, F_SETLK, &fl);
    if (ret < 0) {
        logging_error("fcntl failed, error msg is %s\n", strerror(errno));
    } else {
        logging_debug("fcntl success, lock ret code is %d\n", ret);
    }
    return ret;
}

static int check_and_set_pid_file()
{
    int ret, fd;
    fd = open(PID_FILE_PATH, O_CREAT | O_RDWR, 0600);
    if (fd < 0) {
        logging_error("open file %s failed!\n", PID_FILE_PATH);
        return -1;
    }

    ret = handle_file_lock(fd, true);
    if (ret < 0) {
        logging_error("%s is already running\n", TOOL_NAME);
        close(fd);
        return ret;
    }

    return fd;
}

static int release_pid_file(int fd)
{
    int ret;
    ret = handle_file_lock(fd, false);
    if (ret < 0) {
        logging_error("release pid file %s lock failed, error msg is %s\n", PID_FILE_PATH, strerror(errno));
        return ret;
    }

    close(fd);
    ret = remove(PID_FILE_PATH);
    if (ret < 0) {
        logging_error("remove %s failed, error msg is %s\n", PID_FILE_PATH, strerror(errno));
    }
    return ret;
}

static int smh_dev_get_fd(void)
{
    int smh_dev_fd;
    smh_dev_fd = open(SMH_DEV_PATH, O_RDWR);
    if (smh_dev_fd < 0) {
        logging_error("Failed to open smh_dev_fd for %s.\n", SMH_DEV_PATH);
    }

    return smh_dev_fd;
}

static int convert_ubus_type_to_sentry_type(enum ras_err_type ubus_type)
{
    int sentry_type = -1;
    switch (ubus_type) {
        case UB_MEM_ATOMIC_DATA_ERR:
            sentry_type = SENTRY_MEM_ERR_ROUTE;
            break;
        case MAR_NOPORT_VLD_INT_ERR:
            sentry_type = SENTRY_MEM_FLUX_INT;
            break;
        case MAR_NEAR_AUTH_FAIL_ERR:
            sentry_type = SENTRY_MEM_ERR_OUTBOUND_TRANSLATION;
            break;
        case MAR_FAR_AUTH_FAIL_ERR:
        case UB_MEM_FLOW_READ_AUTH_POISON:
        case UB_MEM_FLOW_READ_AUTH_RESPERR:
            sentry_type = SENTRY_MEM_ERR_INBOUND_TRANSLATION;
            break;
        case MAR_TIMEOUT_ERR:
        case UB_MEM_TIMEOUT_POISON:
        case UB_MEM_TIMEOUT_RESPERR:
            sentry_type = SENTRY_MEM_ERR_TIMEOUT;
            break;
        case MAR_ILLEGAL_ACCESS_ERR:
            sentry_type = SENTRY_MEM_ERR_BUS;
            break;
        case REMOTE_READ_DATA_ERR_OR_WRITE_RESPONSE_ERR:
        case UB_MEM_READ_DATA_ERR:
        case UB_MEM_FLOW_POISON:
        case UB_MEM_READ_DATA_POISON:
        case UB_MEM_READ_DATA_RESPERR:
            sentry_type = SENTRY_MEM_ERR_UCE;
            break;
        case MAR_FLUX_INT_ERR:
        case MAR_WITHOUT_CXT_ERR:
            sentry_type = SENTRY_MEM_ERR_NO_REPORT;
            break;
        default:
            logging_warn("Unknown ubus type: %d\n", ubus_type);
            break;
    }
    return sentry_type;
}

static int convert_power_off_smh_smg_to_str(const struct sentry_msg_helper_msg* smh_msg, char* str)
{
    int res;
    res = snprintf(str, MSG_STR_MAX_LEN, "%lu", smh_msg->msgid);
    if ((size_t)res >= MSG_STR_MAX_LEN) {
        logging_warn("msg str size exceeds the max value\n");
        return -1;
    }
    return 0;
}

static int convert_oom_smh_smg_to_str(const struct sentry_msg_helper_msg* smh_msg, char* str)
{
    int res;
    size_t offset = 0;

    char *nid_str = (char *) calloc (MSG_STR_MAX_LEN, sizeof(char));
    if (!nid_str) {
        logging_error("Failed to allocate memory!");
        return -1;
    }
    for (int i = 0; i < OOM_EVENT_MAX_NUMA_NODES ; i++) {
        res = snprintf(nid_str + offset, MSG_STR_MAX_LEN - offset, "%d%s",
                       smh_msg->helper_msg_info.oom_info.nid[i],
                       (i < OOM_EVENT_MAX_NUMA_NODES - 1) ? "," : "");
        if ((size_t)res >= MSG_STR_MAX_LEN) {
            logging_warn("msg str size exceeds the max value\n");
            free(nid_str);
            nid_str = NULL;
            return -1;
        }
        offset += res;
    }
    res = snprintf(str, MSG_STR_MAX_LEN,
                   "%lu_{nr_nid:%d,nid:[%s],sync:%d,timeout:%d,reason:%d}",
                   smh_msg->msgid,
                   smh_msg->helper_msg_info.oom_info.nr_nid,
                   nid_str,
                   smh_msg->helper_msg_info.oom_info.sync,
                   smh_msg->helper_msg_info.oom_info.timeout,
                   smh_msg->helper_msg_info.oom_info.reason);
    free(nid_str);
    nid_str = NULL;
    if ((size_t)res >= MSG_STR_MAX_LEN) {
        logging_warn("msg str size exceeds the max value\n");
        return -1;
    }
    return 0;
}

static int convert_remote_smh_smg_to_str(const struct sentry_msg_helper_msg* smh_msg, char* str)
{
    int res = snprintf(str, MSG_STR_MAX_LEN, "%lu_{cna:%u,eid:%s}",
                       smh_msg->msgid,
                       smh_msg->helper_msg_info.remote_info.cna,
                       smh_msg->helper_msg_info.remote_info.eid);
    if ((size_t)res >= MSG_STR_MAX_LEN) {
        logging_warn("msg str size exceeds the max value\n");
        return -1;
    }
    return 0;
}

static int convert_ub_mem_err_smh_msg_to_str(struct sentry_msg_helper_msg* smh_msg, char* str)
{
    enum ras_err_type raw_err_type = smh_msg->helper_msg_info.ub_mem_info.raw_ubus_mem_err_type;
    int sentry_err_type = convert_ubus_type_to_sentry_type(raw_err_type);
    // return -1 indicates that only logs are recorded, and no alerts are sent to xalam.
    if (sentry_err_type == SENTRY_MEM_ERR_NO_REPORT) {
        logging_info("received kernel event raw_ubus_mem_err_type is %d\n", raw_err_type);
        return -1;
    }
    if (sentry_err_type == -1) {
        logging_error("raw_ubus_mem_err_type to sentry_ubus_mem_err_type failed, "
                      "raw_ubus_mem_err_type: %d, sentry_ubus_mem_err_type: %d\n",
                      raw_err_type, sentry_err_type);
        return -1;
    }
    uint64_t msgid = smh_msg->msgid;
    uint64_t pa = smh_msg->helper_msg_info.ub_mem_info.pa;

    mem_id id;
    unsigned long obmm_offset;
    int result = obmm_query_memid_by_pa(pa, &id, &obmm_offset);
    if (result < 0) {
        logging_error("query memid falied, result: %d, errno: %d (%s)\n", result, errno, strerror(errno));
        return -1;
    }

    if (smh_msg->helper_msg_info.ub_mem_info.mem_type == FD_MODE
        && smh_msg->helper_msg_info.ub_mem_info.fault_with_kill) {
        logging_info("ub mem event raw type is %d, sending SIGBUS signal to process\n", raw_err_type);
        find_and_send_sigbus_to_thread(id, obmm_offset);
    }

    char hex_str[PYHS_ADDR_HEX_STR_MAX_LEN];
    int ret = snprintf(hex_str, sizeof(hex_str), "0x%lx", (long)pa);
    if (ret < 0) {
        logging_error("convert pa to string failed\n");
        return -1;
    }
    struct json_object *root = json_object_new_object();
    json_object_object_add(root, "msgid", json_object_new_int64(msgid));
    json_object_object_add(root, "sentry_ubus_mem_err_type", json_object_new_int(sentry_err_type));
    json_object_object_add(root, "raw_ubus_mem_err_type", json_object_new_int(raw_err_type));
    json_object_object_add(root, "pa", json_object_new_string(hex_str));
    json_object_object_add(root, "memid", json_object_new_int64(id));

    const char* json_str = json_object_to_json_string(root);
    if (json_str == NULL) {
        logging_error("json_str return NULL\n");
        json_object_put(root);
        return -1;
    }

    strncpy(str, json_str, MSG_STR_MAX_LEN - 1);

    if (strlen(str) >= MSG_STR_MAX_LEN) {
        logging_error("msg str size exceeds the max value\n");
        json_object_put(root);
        return -1;
    }
    json_object_put(root);
    return 0;
}

static int convert_smh_msg_to_str(struct sentry_msg_helper_msg* smh_msg, char* str)
{
    int res;
    switch (smh_msg->type) {
        case SMH_MESSAGE_POWER_OFF:
            res = convert_power_off_smh_smg_to_str(smh_msg, str);
            break;
        case SMH_MESSAGE_OOM:
            res = convert_oom_smh_smg_to_str(smh_msg, str);
            break;
        case SMH_MESSAGE_PANIC:
        case SMH_MESSAGE_KERNEL_REBOOT:
            res = convert_remote_smh_smg_to_str(smh_msg, str);
            break;
        case SMH_MESSAGE_UB_MEM_ERR:
            res = convert_ub_mem_err_smh_msg_to_str(smh_msg, str);
            break;
        default:
            logging_warn("Unknown msg type: %d\n", smh_msg->type);
            return -1;
    }
    return res;
}

static int convert_str_to_smh_msg(struct alarm_msg *al_msg, struct sentry_msg_helper_msg* smh_msg)
{
    int n, ret = 0;
    unsigned short alarm_ack_type = al_msg->usAlarmId;
    switch (alarm_ack_type) {
        case ALARM_REBOOT_ACK_EVENT:
        case ALARM_OOM_ACK_EVENT:
            if (!(sscanf(al_msg->pucParas, "%lu_%lu%n",
                         &(smh_msg->msgid),
                         &(smh_msg->res),
                         &n) == XALARM_GENERAL_MSG_ITEM_CNT) || strlen(al_msg->pucParas) != n) {
                logging_warn("Invalid msg str format, str is %s\n", al_msg->pucParas);
                ret = -1;
            }
            break;
        case ALARM_PANIC_ACK_EVENT:
        case ALARM_KERNEL_REBOOT_ACK_EVENT:
            if (!(sscanf(al_msg->pucParas, "%lu_{cna:%u,eid:%39[^}]}_%lu%n",
                &(smh_msg->msgid),
                &(smh_msg->helper_msg_info.remote_info.cna),
                smh_msg->helper_msg_info.remote_info.eid,
                &(smh_msg->res),
                &n) == XALARM_PANIC_MSG_ITEM_CNT) || strlen(al_msg->pucParas) != n) {
                logging_warn("Invalid msg str format, str is %s\n", al_msg->pucParas);
                ret = -1;
            }
            break;
        default:
            ret = -1;
            logging_warn("Unknown ack event type: %d\n", alarm_ack_type);
    }
    return ret;
}

static unsigned short convert_msg_type_to_xalarm_type(enum sentry_msg_helper_msg_type msg_type)
{
    unsigned short xalarm_type = 0;
    switch (msg_type) {
        case SMH_MESSAGE_POWER_OFF:
            xalarm_type = ALARM_REBOOT_EVENT;
            break;
        case SMH_MESSAGE_OOM:
            xalarm_type = ALARM_OOM_EVENT;
            break;
        case SMH_MESSAGE_PANIC:
            xalarm_type = ALARM_PANIC_EVENT;
            break;
        case SMH_MESSAGE_KERNEL_REBOOT:
            xalarm_type = ALARM_KERNEL_REBOOT_EVENT;
            break;
        case SMH_MESSAGE_UB_MEM_ERR:
            xalarm_type = ALARM_UBUS_MEM_EVENT;
            break;
        default:
            logging_warn("Unknown msg type: %d\n", msg_type);
            break;
    }
    return xalarm_type;
}

static void sender_cleanup(void* arg)
{
    logging_debug("In sender thread cleanup\n");
    int fd = *(int *)arg;
    if (fd > 0) {
        close(fd);
    }
    logging_info("Sender thread cleanup over\n");
}

static void* sender_thread(void* arg)
{
    int ret, retry_num;
    int fd = smh_dev_get_fd();
    if (fd < 0) {
        goto close_recv;
    }
    pthread_cleanup_push(sender_cleanup, &fd);

    pthread_t partner_t;
    char *str = (char *) calloc (MSG_STR_MAX_LEN, sizeof(char));
    if (!str) {
        logging_error("Failed to allocate memory!");
        close(fd);
        goto close_recv;
    }

    while (1) {
        struct sentry_msg_helper_msg smh_msg;
        errno = 0;
        ret = read(fd, &smh_msg, sizeof(struct sentry_msg_helper_msg));
        if (ret != sizeof(struct sentry_msg_helper_msg)) {
            if (errno == ERESTART || errno == EFAULT) {
                logging_warn("Read dev failed, return code (%d): try to read the next one msg from kernel\n", errno);
                continue;
            } else if (errno == EAGAIN) {
                logging_warn("Read dev failed, return code (%d): kernel queue is full, try to read again\n", errno);
                continue;
            } else {
                logging_error("Read dev failed, return code %d\n", errno);
                goto sender_err;
            }
        }
        logging_info("Read dev success!\n");

        ret = convert_smh_msg_to_str(&smh_msg, str);
        if (ret < 0) {
            continue;
        }
        logging_info("convert_smh_msg_to_str success, msgid is %u\n", smh_msg.msgid);

        unsigned short alarm_type = convert_msg_type_to_xalarm_type(smh_msg.type);
        if (alarm_type == 0) {
            logging_warn("Send msg to xalarmd failed: Get unknown type msg, skip it\n");
            continue;
        }

        retry_num = 0;
        for (int i = 0; i < MAX_RETRY_NUM; i++) {
            ret = xalarm_report_event(alarm_type, str);
            if (ret == 0) {
                logging_info("Send msg success: alarm_type: %d\n", alarm_type);
                break;
            }
            if (ret == -EINVAL) {
                logging_warn("Send msg to xalarmd failed: (%d) Invalid input value, skip it\n", ret);
                break;
            } else if (ret == -ENOTCONN || ret == -ECOMM || ret == -ENODEV) {
                retry_num++;
                logging_warn("Send msg to xalarmd failed: (%d) Bad socket conn, start the %dth retry in %d seconds.\n",
                             ret, retry_num, RETRY_PERIOD);
                sleep(RETRY_PERIOD);
            } else if (ret < 0) {
                logging_warn("xalarm_report_event return %d\n", ret);
                break;
            }
        }
        if (ret == -ENOTCONN || ret == -ECOMM) {
            logging_warn("Send msg to xalarmd failed after %d retries: Bad socket conn, skip it.\n", retry_num);
        }
    }

sender_err:
    close(fd);
    free(str);
    str = NULL;
close_recv:
    partner_t = *(pthread_t*)arg;
    if (partner_t) {
        pthread_cancel(partner_t);
    }
    logging_error("Sender thread exited unexpectedly\n");
    pthread_cleanup_pop(0);
    return NULL;
}

static void receiver_cleanup(void* arg)
{
    logging_debug("In receiver thread cleanup\n");
    struct receiver_cleanup_data* rcd = (struct receiver_cleanup_data*) arg;
    if (rcd->al_msg) {
        free(rcd->al_msg);
    }
    if (rcd->register_info) {
        xalarm_unregister_event(rcd->register_info);
    }
    logging_info("Receiver thread cleanup over\n");
}

static void* receiver_thread(void* arg)
{
    int ret, fd, retry_num;
    struct alarm_msg *al_msg;
    struct sentry_msg_helper_msg smh_msg;
    pthread_t partner_t;
    struct alarm_register* register_info;

    fd = smh_dev_get_fd();
    if (fd < 0) {
        goto close_send;
    }

    al_msg = (struct alarm_msg*)malloc(sizeof(struct alarm_msg));
    if (!al_msg) {
        logging_error("malloc al_msg failed!\n");
        goto receiver_err;
    }

re_register:
    register_info = NULL;
    struct alarm_subscription_info id_filter = {
        .len = ID_LIST_LENGTH
    };
    id_filter.id_list[0] = ALARM_REBOOT_ACK_EVENT;
    id_filter.id_list[1] = ALARM_OOM_ACK_EVENT;
    id_filter.id_list[2] = ALARM_PANIC_ACK_EVENT;
    id_filter.id_list[3] = ALARM_KERNEL_REBOOT_ACK_EVENT;

    retry_num = 0;
    for (int i = 0; i < MAX_RETRY_NUM; i++) {
        ret = xalarm_register_event(&register_info, id_filter);
        if (ret == 0) {
            break;
        }
        if (ret == -ENOTCONN) {
            retry_num++;
            logging_warn("Failed to register xalarm, start the %dth retry in %d seconds.\n", retry_num, RETRY_PERIOD);
            sleep(RETRY_PERIOD);
        } else {
            logging_error("xalarm_register_event return %d\n", ret);
            goto receiver_err;
        }
    }
    if (ret == -ENOTCONN) {
        logging_error("Failed to register xalarm after %d retries: bad connection, "
                      "enter the error handling process\n", retry_num);
        goto receiver_err;
    }

    struct receiver_cleanup_data rcd = {
        .al_msg = al_msg,
        .register_info = register_info
    };
    pthread_cleanup_push(receiver_cleanup, &rcd);

    while (1) {
        ret = xalarm_get_event(al_msg, register_info);
        if (ret == -ENOTCONN || ret == -ECONNRESET || ret == -EBADF) {
            logging_warn("Failed to get msg: (%d) Xalarmd service exception, try to re-register\n", ret);
            xalarm_unregister_event(register_info);
            goto re_register;
        } else if (ret < 0) {
            logging_error("xalarm_get_event return %d\n", ret);
            goto un_register;
        } else {
            logging_info("Get msg: alarm_type: %d\n", al_msg->usAlarmId);
        }

        ret = convert_str_to_smh_msg(al_msg, &smh_msg);
        if (ret < 0) {
            logging_warn("Convert str failed: Bad format '%s', skip it\n", al_msg->pucParas);
            continue;
        }
        retry_num = 0;
        for (int i = 0; i < MAX_RETRY_NUM; i++) {
            errno = 0;
            ret = ioctl(fd, SMH_MSG_ACK, &smh_msg);
            if (ret == 0) {
                break;
            }
            if (errno == ERESTART || errno == ETIME || errno == ENOENT) {
                logging_warn("Ack to kernel failed: ioctl return %d, skip it\n", errno);
                break;
            } else if (errno == EFAULT) {
                retry_num++;
                logging_warn("Ack to kernel failed: (%d) Copy from user failed, start the %dth retry in %d seconds.\n",
                             errno, retry_num, RETRY_PERIOD);
                sleep(RETRY_PERIOD);
            } else if (ret < 0) {
                logging_error("Ack to kernel failed: ioctl return %d\n", errno);
                goto un_register;
            }
        }
        if (errno == EFAULT) {
            logging_warn("Ack to kernel failed after %d retries: Copy from user failed, skip it\n", retry_num);
        }
    }

un_register:
    xalarm_unregister_event(register_info);
receiver_err:
    free(al_msg);
    close(fd);
close_send:
    partner_t = *(pthread_t*)arg;
    if (partner_t) {
        pthread_cancel(partner_t);
    }
    logging_error("Receiver thread exited unexpectedly\n");
    pthread_cleanup_pop(0);
    return NULL;
}

int main()
{
    int ret, pid_fd;
    pthread_t sender, receiver;

    pid_fd = check_and_set_pid_file();
    if (pid_fd < 0) {
        return pid_fd;
    }

    ret = pthread_create(&sender, NULL, sender_thread, &receiver);
    if (ret) {
        logging_error("Failed to create sender thread");
        goto err_release;
    }

    ret = pthread_create(&receiver, NULL, receiver_thread, &sender);
    if (ret) {
        logging_error("Failed to create receiver thread");
        pthread_cancel(sender);
        pthread_join(sender, NULL);
        goto err_release;
    }

    logging_info("sentry_msg_monitor start!\n");

    pthread_join(sender, NULL);
    pthread_join(receiver, NULL);

err_release:
    release_pid_file(pid_fd);
    logging_info("sentry_msg_monitor end with ret %d!\n", ret);
    return ret;
}
