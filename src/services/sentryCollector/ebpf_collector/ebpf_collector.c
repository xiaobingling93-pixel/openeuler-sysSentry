/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2024. All rights reserved.
 * Description: ebpf collector program
 * Author: Zhang Nan
 * Create: 2024-09-27
 */
#include <argp.h> 
#include <signal.h>
#include <stdio.h> 
#include <unistd.h> 
#include <time.h> 
#include <stdlib.h> 
#include <string.h> 
#include <stdarg.h>
#include <dirent.h>
#include <bpf/bpf.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/sysinfo.h> 
#include "ebpf_collector.h"
#include "ebpf_collector.skel.h"

#define BLK_MAP    (bpf_map__fd(skel->maps.blk_map))
#define BLK_RES    (bpf_map__fd(skel->maps.blk_res)) 
#define BIO_MAP    (bpf_map__fd(skel->maps.bio_map))
#define BIO_RES    (bpf_map__fd(skel->maps.bio_res))
#define WBT_MAP    (bpf_map__fd(skel->maps.wbt_map))
#define WBT_RES    (bpf_map__fd(skel->maps.wbt_res))
#define TAG_MAP    (bpf_map__fd(skel->maps.tag_map))
#define TAG_RES    (bpf_map__fd(skel->maps.tag_res))
#define BLK_RES_2    (bpf_map__fd(skel->maps.blk_res_2))
#define BIO_RES_2    (bpf_map__fd(skel->maps.bio_res_2))
#define WBT_RES_2    (bpf_map__fd(skel->maps.wbt_res_2))
#define TAG_RES_2    (bpf_map__fd(skel->maps.tag_res_2))

#define MAX_LINE_LENGTH 1024
#define MAX_SECTION_NAME_LENGTH 256
#define CONFIG_FILE "/etc/sysSentry/collector.conf"

typedef struct {
    int major;
    int minor;
} DeviceInfo;

typedef enum {
    LOG_LEVEL_NONE,
    LOG_LEVEL_DEBUG,
    LOG_LEVEL_INFO,
    LOG_LEVEL_WARNING,
    LOG_LEVEL_ERROR
} LogLevel;

LogLevel currentLogLevel = LOG_LEVEL_INFO;

static volatile bool exiting;

const char argp_program_doc[] = 
"Show block device I/O pattern.\n"
"\n"
"USAGE: ebpf_collector [--help]\n"
"\n"
"EXAMPLES:\n"
"    ebpf_collector              # show block I/O pattern\n";

static const struct argp_option opts[] = {
    { NULL, 'h', NULL, OPTION_HIDDEN, "Show the full help" }, 
    {},
};

static error_t parse_arg(int key, char *arg, struct argp_state *state) {
    static int pos_args; 

    switch (key) { 
    case 'h': 
        argp_state_help(state, stderr, ARGP_HELP_STD_HELP); 
        break;
    default: 
        return ARGP_ERR_UNKNOWN; 
    }
    return 0; 
}

void logMessage(LogLevel level, const char *format, ...){
    if (level >= currentLogLevel) {
        va_list args;
        va_start(args, format);
        vprintf(format, args);
        va_end(args);
    }
}

static void sig_handler(int sig)
{
    exiting = true; 
}

char* extract_device_name(const char *path) {
    const char *dev_dir = "/dev/";
    char *name = strrchr(path, '/') + 1; 
    if (strncmp(dev_dir, path, strlen(dev_dir)) == 0) {
        return strdup(name); 
    }
    return NULL; 
}

char* find_device_name(dev_t dev) {
    DIR *dir;
    struct dirent *entry;
    struct stat sb;
    char *device_name = NULL;
    char path[1024];

    dir = opendir("/dev");
    if (dir == NULL) {
        perror("Failed to open /dev");
        return NULL;
    }

    while ((entry = readdir(dir)) != NULL) {
        snprintf(path, sizeof(path), "/dev/%s", entry->d_name);

        if (entry->d_type == DT_DIR || entry->d_type == DT_LNK) {
            continue;
        }

        if (stat(path, &sb) == -1) {
            continue; 
        }

        if (major(sb.st_rdev) == major(dev) && minor(sb.st_rdev) == minor(dev)) {
            device_name = extract_device_name(path); 
            break;
        }
    }

    closedir(dir);
    return device_name;
}

static void update_io_dump(int fd, int *io_dump, int map_size, char *stage) {
    struct time_range_io_count time_count;
    u32 io_dump_key = 0;
    struct sysinfo info; 
    sysinfo(&info);
    int count_time = 150;
    u32 curr_time = info.uptime;
    while (count_time >= 0) {
        io_dump_key = curr_time - count_time;
        int err = bpf_map_lookup_elem(fd, &io_dump_key, &time_count);
        if (err < 0) {
            count_time -= 1; 
            continue; 
        }
        if ((curr_time - io_dump_key) >= 2) {
            int isempty = 1;
            for (int key = 0; key < map_size; key++) {
                if (time_count.count[key] > IO_DUMP_DIFF) {
                    io_dump[key] += time_count.count[key];
                    isempty = 0;
                }
            }
            if (isempty || (curr_time - io_dump_key) > IO_DUMP_THRESHOLD) {
                bpf_map_delete_elem(fd, &io_dump_key);
            } 
        }
        count_time -= 1;
    }
}

static int print_map_res(int fd, char *stage, int map_size, int *io_dump)
{
    struct stage_data counter; 
    int key = 0;

    logMessage(LOG_LEVEL_DEBUG, "print_map_res map_size: %d\n", map_size);
    for (key = 0; key < map_size; key++) {
        int err = bpf_map_lookup_elem(fd, &key, &counter); 
        if (err < 0) { 
            logMessage(LOG_LEVEL_ERROR, "failed to lookup %s map_res: %d\n", stage, err);
            return -1; 
        }
        
        size_t length = strlen(counter.io_type);
        char io_type;
        if (length > 0) {
            logMessage(LOG_LEVEL_DEBUG, "io_type have value.\n");
            io_type = counter.io_type[0];
        } else {
            logMessage(LOG_LEVEL_DEBUG, "io_type not value.\n");
            io_type = '\0';
        }
        int major = counter.major;
        int first_minor = counter.first_minor;
        dev_t dev = makedev(major, first_minor);    
        char *device_name = find_device_name(dev);
        logMessage(LOG_LEVEL_DEBUG, "device_name: %s, stage: %s, io_type: %c\n", device_name, stage, io_type);
        if (device_name && io_type) {
            printf("%-7s %10llu %10llu %d %c %s\n",
                stage, 
                counter.finish_count, 
                counter.duration,
                io_dump[key],
                io_type,
                device_name
            );
            fflush(stdout);
        }
    }

    return 0; 
}

int init_map(int fd, const char *map_name, int device_count, DeviceInfo *devices) {
    struct stage_data init_data = {0};

    memset(init_data.io_type, 0, sizeof(init_data.io_type));

    for (int i = 0; i < device_count; i++) {
        init_data.major = devices[i].major;
        init_data.first_minor = devices[i].minor;
        if (bpf_map_update_elem(fd, &i, &init_data, BPF_ANY) != 0) {
            logMessage(LOG_LEVEL_ERROR, "Failed to initialize map %s at index %d\n", map_name, i);
            return 1;
        }
    }

    return 0;
}

char *read_config_value(const char *file, const char *section, const char *key) {
    FILE *fp = fopen(file, "r");
    if (fp == NULL) {
        logMessage(LOG_LEVEL_ERROR, "Failed to open config file.\n");
        return NULL;
    }

    char line[MAX_LINE_LENGTH];
    char current_section[MAX_SECTION_NAME_LENGTH] = {0};
    char *value = NULL;

    while (fgets(line, sizeof(line), fp) != NULL) {
        size_t newline_char_idx = strcspn(line, "\n");
        if (newline_char_idx == MAX_LINE_LENGTH) {
            line[MAX_LINE_LENGTH - 1] = '\0';
        } else {
            line[newline_char_idx] = '\0';
        }

        if (line[0] == '\0' || line[0] == ';' || line[0] == '#') {
            continue;
        }

        if (line[0] == '[') {
            sscanf(line, "[%255[^]]", current_section);
            continue;
        }

        if (strcmp(current_section, section) == 0) {
            char *delimiter = "=";
            char *token = strtok(line, delimiter);
            if (token != NULL) {
                if (strcmp(token, key) == 0) {
                    token = strtok(NULL, delimiter);
                    if (token != NULL) {
                        value = strdup(token);
                        break;
                    }
                }
            }
        }
    }

    fclose(fp);
    return value;
}

void setLogLevel(const char *levelStr) {
    if (strcmp(levelStr, "info") == 0) {
        currentLogLevel = LOG_LEVEL_INFO;
    }
    else if (strcmp(levelStr, "warning") == 0) {
        currentLogLevel = LOG_LEVEL_WARNING;
    }
    else if (strcmp(levelStr, "error") == 0) {
        currentLogLevel = LOG_LEVEL_ERROR;
    }
    else if (strcmp(levelStr, "debug") == 0) {
        currentLogLevel = LOG_LEVEL_DEBUG;
    }
    else if (strcmp(levelStr, "none") == 0) {
        currentLogLevel = LOG_LEVEL_NONE;
    }
    else {
        logMessage(LOG_LEVEL_ERROR, "unknown log level: %s\n", levelStr);
    }
}

int check_for_device(const char *device_name) {
    char path[256];
    snprintf(path, sizeof(path), "/sys/block/%s", device_name);

    DIR *dir = opendir(path);
    if (dir == NULL) {
        return 0; 
    }

    struct dirent *entry;
    while ((entry = readdir(dir)) != NULL) {
        struct stat statbuf;
        if (stat(path, &statbuf) == 0) {
            if (S_ISDIR(statbuf.st_mode)) {
                closedir(dir);
                return 1;
            }
        }
    }
    closedir(dir);
    return 0;
}

// 处理事件的回调函数
static int handle_event(void *ctx, void *data, size_t data_sz) {
    struct event *e = (struct event *)data;
    logMessage(LOG_LEVEL_ERROR, "kernelspace error happen, stage: %d, period: %d, error: %d\n", e->stage, e->period, e->err);
    return 0;
}

int main(int argc, char **argv) {
    struct partitions *partitions = NULL; 
    const struct partition *partition; 
    static const struct argp argp = { 
        .options = opts, 
        .parser = parse_arg, 
        .doc = argp_program_doc, 
    };
    int err; 
    char filename[256];
    DIR *dir;
    struct dirent *entry;
    char path[1024];
    int major, minor;
    DeviceInfo devices[MAP_SIZE];
    int device_count = 0;
    struct rlimit r = {RLIM_INFINITY, RLIM_INFINITY}; 
    setrlimit(RLIMIT_MEMLOCK, &r); 

    char *level = read_config_value(CONFIG_FILE, "log", "level");
    if (level != NULL) {
        if (level[strlen(level) - 1] == '\r') {
            size_t len = strlen(level);
            level[len - 1] = '\0'; 
        }
        setLogLevel(level);
        free(level);
    } else {
        logMessage(LOG_LEVEL_INFO, "the log level is incorrectly configured. the default log level is info.\n");
    }
    logMessage(LOG_LEVEL_DEBUG, "finish config parse.\n");

    err = argp_parse(&argp, argc, argv, 0, NULL, NULL); 
    if (err) {
        logMessage(LOG_LEVEL_ERROR, "argp parse failed.\n");
        return err; 
    }

    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);

    dir = opendir("/dev");
    if (dir == NULL) {
        logMessage(LOG_LEVEL_ERROR, "Failed to open /dev directory.\n");
        return EXIT_FAILURE;
    }

    while ((entry = readdir(dir)) != NULL) {
        if (entry->d_type != DT_BLK) {
            continue;
        }
        snprintf(path, sizeof(path), "/dev/%s", entry->d_name);
        struct stat statbuf;
        if (lstat(path, &statbuf) != 0 && !S_ISBLK(statbuf.st_mode)) {
            continue;
        }
        if (!strncmp(entry->d_name, "dm-", 3) || !strncmp(entry->d_name, "loop", 4) ||
            !strncmp(entry->d_name, "md", 2)) {
            continue;
        }
        if (!check_for_device(entry->d_name)) {
            continue;
        }

        devices[device_count].major = major(statbuf.st_rdev);
        devices[device_count].minor = minor(statbuf.st_rdev);
        device_count++;
        if (device_count >= MAP_SIZE) {
            logMessage(LOG_LEVEL_DEBUG, " device_count moren than MAP_SIZE.\n");
            break;
        }
    }

    closedir(dir);

    struct ebpf_collector_bpf *skel = ebpf_collector_bpf__open();
    if (!skel) {
        logMessage(LOG_LEVEL_ERROR, "Failed to open and load BPF skeleton\n");
        return 1;
    }

    // 加载 BPF 程序到内核中
    err = ebpf_collector_bpf__load(skel);
    if (err) {
        logMessage(LOG_LEVEL_ERROR, "Failed to load BPF skeleton: %d\n", err);  
        ebpf_collector_bpf__destroy(skel);
        return 1;
    }

    // 附加 BPF 程序到 kprobe
    err = ebpf_collector_bpf__attach(skel);
    if (err) {
        logMessage(LOG_LEVEL_ERROR, "Failed to attach BPF skeleton: %d\n", err);  
        ebpf_collector_bpf__destroy(skel);
        return 1;
    }

    // 初始化环形缓冲区读取器
    struct ring_buffer *rb = NULL;
    rb = ring_buffer__new(bpf_map__fd(skel->maps.ringbuf), handle_event, NULL, NULL);
    if (!rb) {
        return 1;
    }


    if (init_map(BLK_RES, "blk_res_map", device_count, devices)) {
        logMessage(LOG_LEVEL_ERROR, "blk_res_map failed.\n");
        ebpf_collector_bpf__destroy(skel);
        return 1;
    }

    if (init_map(BIO_RES, "blo_res_map", device_count, devices) != 0) {
        logMessage(LOG_LEVEL_ERROR, "blo_res_map failed.\n");
        ebpf_collector_bpf__destroy(skel);
        return 1;
    }
    if (init_map(WBT_RES, "wbt_res_map", device_count, devices) != 0) {
        logMessage(LOG_LEVEL_ERROR, "wbt_res_map failed.\n");
        ebpf_collector_bpf__destroy(skel);
        return 1;
    }
    if (init_map(TAG_RES, "tag_res_map", device_count, devices) != 0) {
        logMessage(LOG_LEVEL_ERROR, "tag_res_map failed.\n");
        ebpf_collector_bpf__destroy(skel);
        return 1;
    }

    for (;;) { 
       
        sleep(1); 

        err = ring_buffer__poll(rb, 100);

        int io_dump_blk[MAP_SIZE] = {0}; 
        update_io_dump(BLK_RES_2, io_dump_blk, device_count,"rq_driver"); 
        err = print_map_res(BLK_RES, "rq_driver", device_count, io_dump_blk); 
        if (err) {
            logMessage(LOG_LEVEL_ERROR, "print_map_res rq_driver error.\n");
            break; 
        }

        int io_dump_bio[MAP_SIZE] = {0}; 
        update_io_dump(BIO_RES_2, io_dump_bio, device_count,"bio");
        err = print_map_res(BIO_RES, "bio", device_count, io_dump_bio); 
        if (err) {
            logMessage(LOG_LEVEL_ERROR, "print_map_res bio error.\n");
            break; 
        }

        int io_dump_tag[MAP_SIZE] = {0}; 
        update_io_dump(TAG_RES_2, io_dump_tag, device_count,"gettag");        
        err = print_map_res(TAG_RES, "gettag", device_count, io_dump_tag); 
        if (err) {
            logMessage(LOG_LEVEL_ERROR, "print_map_res gettag error.\n");
            break; 
        }

        int io_dump_wbt[MAP_SIZE] = {0}; 
        update_io_dump(WBT_RES_2, io_dump_wbt, device_count,"wbt");        
        err = print_map_res(WBT_RES, "wbt", device_count, io_dump_wbt); 
        if (err) {
            logMessage(LOG_LEVEL_ERROR, "print_map_res wbt error.\n");
            break; 
        }

        if (exiting) {
            logMessage(LOG_LEVEL_DEBUG, "exit program.\n");
            break; 
        }
    }

    ring_buffer__free(rb);
    ebpf_collector_bpf__destroy(skel);
    return -err;
}
