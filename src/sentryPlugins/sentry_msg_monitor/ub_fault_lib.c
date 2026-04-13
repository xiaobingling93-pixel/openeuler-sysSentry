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

 * Description: ub fault lib
 * Author: sxt1001
 * Create: 2025-11-10
*/

#include <stdlib.h>
#include <fcntl.h>
#include <signal.h>
#include <unistd.h>
#include <dirent.h>
#include <stdbool.h>
#include <ctype.h>
#include <string.h>

#include "log_utils.h"
#include "ub_fault_lib.h"

#define COMMAND_STR_MAX_LEN 512
#define OBMM_SHMDEV_NAME_MAX_LEN 256
#define COMMAND_OUTPUT_LINE_MAX_LEN 1024
#define ID_CAPACITY 10
#define PERM_STRING_LEN 8

static int find_processes_by_device(const char *obmm_shmdev_name, pid_t **pids)
{
    char command[COMMAND_STR_MAX_LEN];
    FILE *fp;
    char line[COMMAND_OUTPUT_LINE_MAX_LEN];
    int capacity = ID_CAPACITY;
    int found = 0;

    if (!obmm_shmdev_name) {
        logging_error("obmm_shmdev_name is empty\n");
        return -1;
    }

    snprintf(command, sizeof(command), "/usr/bin/lsof \"%s\" | awk 'NR > 1 {print $2}'", obmm_shmdev_name);

    *pids = malloc(capacity * sizeof(pid_t));
    if (!*pids) {
        logging_error("malloc failed for pids\n");
        return -1;
    }

    fp = popen(command, "r");
    if (!fp) {
        logging_error("popen failed\n");
        free(*pids);
        *pids = NULL;
        return -1;
    }

    while (fgets(line, sizeof(line), fp)) {
        pid_t pid = atoi(line);
        if (pid <= 0) {
            logging_warn("invalid pid line : [%s]\n", line);
            break;
        }

        int duplicate = 0;
        for (int i = 0; i < found; i++) {
            if ((*pids)[i] == pid) {
                duplicate = 1;
                break;
            }
        }

        if (!duplicate) {
            if (found >= capacity) {
                capacity *= 2;
                if (capacity > SIZE_MAX / sizeof(pid_t)) {
                    logging_error("capacity is too long");
                    break;
                }
                pid_t *new_pids = realloc(*pids, capacity * sizeof(pid_t));
                if (!new_pids) {
                    logging_error("realloc failed\n");
                    break;
                }
                *pids = new_pids;
            }
            (*pids)[found++] = pid;
        }
    }

    if (found == 0) {
        logging_info("No program that opens %s is found.\n", obmm_shmdev_name);
    }
    pclose(fp);
    return found;
}

static bool is_accessing_faulty_address(const char *obmm_shmdev_name, const char *tid_maps_str, unsigned long obmm_offset, unsigned long *virt_addr)
{
    FILE *tid_maps_fp;
    char line[COMMAND_OUTPUT_LINE_MAX_LEN];
    int found = 0;

    if (!obmm_shmdev_name || !tid_maps_str) {
        logging_error("Invalid parameter\n");
        return false;
    }

    tid_maps_fp = fopen(tid_maps_str, "r");
    if (!tid_maps_fp) {
        logging_error("fopen %s failed\n", tid_maps_str);
        return false;
    }

    while (fgets(line, sizeof(line), tid_maps_fp)) {
        unsigned long start, end;
        char perms[PERM_STRING_LEN];
        unsigned long offset;
        char other_maps_line[COMMAND_OUTPUT_LINE_MAX_LEN];

        if (!strstr(line, obmm_shmdev_name)) {
            continue;
        }

        // parse maps line
        if (sscanf(line, "%lx-%lx %7s %lx %1023s",
                   &start, &end, perms, &offset, other_maps_line) < 5) {
            logging_error("parse [%s] failed.\n", line);
            continue;
        }

        // check offset
        logging_debug("start to check offset for [%s]\n", line);
        if (obmm_offset <= ((end - start) + offset) && obmm_offset >= offset) {
            *virt_addr = start - offset + obmm_offset;
            found = 1;
        }

        if (found) {
            break;
        }
    }
    fclose(tid_maps_fp);

    return found ? true : false;
}

static bool is_positive_integer(const char *str) {
    if (!str || *str == '\0')
        return false;

    while (*str) {
        if (!isdigit((unsigned char)*str)) {
            return false;
        }
        str++;
    }
    return true;
}

static int check_process_mapping(const char *obmm_shmdev_name, pid_t pid, unsigned long obmm_offset,
                                 unsigned long *virt_addr, pid_t **tids, int *tid_count)
{
    char p_task_path[MAX_PATH];
    struct dirent *entry;
    int capacity = ID_CAPACITY;
    int found = 0;

    *tids = malloc(capacity * sizeof(pid_t));
    if (!*tids) {
        logging_error("malloc failed for tids\n");
        return -1;
    }

    // We need to send a SIGBUS signal to the thread, check /proc/$pid/task/$tid/maps
    snprintf(p_task_path, sizeof(p_task_path), "/proc/%d/task/", pid);

    DIR *dir = opendir(p_task_path);
    if (!dir) {
        logging_error("opendir %s failed\n", p_task_path);
        return -1;
    }

    while ((entry = readdir(dir)) != NULL) {
        if (entry->d_type == DT_DIR && is_positive_integer(entry->d_name)) {
            char tid_maps_path[MAX_PATH];
            pid_t tid = atoi(entry->d_name);
            logging_debug("start to check /proc/%d/task/%d/maps\n", pid, tid);
            snprintf(tid_maps_path, sizeof(tid_maps_path), "/proc/%d/task/%d/maps", pid, tid);
            if (is_accessing_faulty_address(obmm_shmdev_name, tid_maps_path, obmm_offset, virt_addr)) {
                if (found >= capacity) {
                    capacity *= 2;
                    if (capacity > SIZE_MAX / sizeof(pid_t)) {
                        logging_error("capacity is too loncapacity is too long");
                        break;
                    }
                    pid_t *new_tids = realloc(*tids, capacity * sizeof(pid_t));
                    if (!new_tids) {
                        logging_error("realloc new_tids failed\n");
                        break;
                    }
                    *tids = new_tids;
                }
                (*tids)[found++] = tid;
            }
        }
    }
    *tid_count = found;
    closedir(dir);
    return found ? 0 : -1;
}

static int send_sigbus_to_thread(pid_t tid, unsigned long virt_addr)
{
    union sigval value;
    int ret;

    value.sival_ptr = (void *)virt_addr;

    ret = sigqueue(tid, SIGBUS, value);
    if (ret) {
        logging_error("sigqueue failed\n");
    }
    return ret;
}

int find_and_send_sigbus_to_thread(mem_id memid, unsigned long obmm_offset)
{
    pid_t *pids = NULL;
    int pid_count = 0;
    char obmm_shmdev_name[OBMM_SHMDEV_NAME_MAX_LEN];

    snprintf(obmm_shmdev_name, sizeof(obmm_shmdev_name), "/dev/obmm_shmdev%lu", memid);

    pid_count = find_processes_by_device(obmm_shmdev_name, &pids);
    if (pid_count <= 0) {
        logging_info("No pid is found, unable to send SIGBUS signal\n");
        if (pids) {
            free(pids);
        }
        return 0;
    }

    bool is_found_tid_to_kill = false;
    for (int pid_idx = 0; pid_idx < pid_count; pid_idx++) {
        unsigned long virt_addr;
        pid_t *tids = NULL;
        int tid_count = 0;
        if (check_process_mapping(obmm_shmdev_name, pids[pid_idx], obmm_offset, &virt_addr, &tids, &tid_count) == 0) {
            for (int tid_idx = 0; tid_idx < tid_count; tid_idx++) {
                logging_info("Sending SIGBUS to thread %d for process %d\n", tids[tid_idx], pids[pid_idx]);
                is_found_tid_to_kill = true;
                send_sigbus_to_thread(tids[tid_idx], virt_addr);
            }
        }
        if (tids) {
            free(tids);
        }
    }
    if (!is_found_tid_to_kill) {
        logging_info("No tid is found, unable to send SIGBUS signal\n");
    }
    if (pids) {
        free(pids);
    }
    return 0;
}
