/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.
 * Description: tc ring testcase program
 * Author: lizixian
 * Create: 2025-7-10
 */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <ctype.h>
#include <stdbool.h>
#include <errno.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/mman.h>
#include <unistd.h>
#include <sched.h>
#include <time.h>
#include <fcntl.h>
#include <pthread.h>
#include <numa.h>
#include <sys/reboot.h>
#include "register_xalarm.h"
#include "log_utils.h"
#include "soc_ring_sentry.h"
#include "tc_ring_one.h"

struct tc_ring_one_config {
    void**                 test_space_base;         // 存储每个numa节点测试空间的指针，需要根据当前系统numa节点数量动态申请存储空间
    size_t                 mem_size;              // 每个numa节点测试空间内存大小
    size_t                 block_size;              // 每个测试块的大小，固定为64kByte
    uint64_t               loop_cnt;              // 测试循环总数，0 -- 无限测试
    int64_t                delay_ms;                // 每次读完一个数据块后的休眠时间，≤ 0则不休眠，继续下一个数据块的扫描
    int64_t                rd_loop;                 // 每个扫描bit单次循环内的数据扫描次数，固定为0x80
    pthread_t*             tc_core_threads;         // 记录每个核的测试线程
    pthread_barrier_t      tc_barrier;              // 同步标志
    pthread_mutex_t*       tc_node_mutex;           // 每个numa节点数据更新的锁，单个numa节点测试空间的数据刷新，只能由一个本numa节点的测试核来刷新
    uint32_t*              node_update_flag;        // 测试空间数据刷新状态标志
    uint64_t               err_handle;              // 错误后处理
    bool*                  black_list;              // 测试黑名单
    int                    tc_core_total;           // 测试核总数
    int                    sys_core_total;          // 系统核总数
    int                    scan_bit;                // 扫描的bit
    int                    err_flag;                 // 错误计数
    int                    numa_node;               //系统numa总数
};

#define TC_RING_ONE_BLOCK_SIZE                      0x10000
#define TC_RING_ONE_RD_LOOP                         0x80
#define TC_RING_ONE_DATA_UNIT                       128
#define TC_RING_ONE_CACHELINE_SIZE                  64

#define TC_RING_ONE_PRAMA_ERR                       -1
#define TC_RING_ONE_FAIL                            -2
#define TC_RING_ONE_SUCCESS                         0

#define TC_ERROR_HANDLE_NONE                        0
#define TC_ERROR_HANDLE_PANIC                       1
#define TC_ERROR_HANDLE_SHUTDOWN                    2
#define TC_ERROR_HANDLE_REBOOT                      3

static const uint32_t tc_ring_one_pattern[32] = {
    0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF,
    0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF,
    0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF,
    0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF,
    0x00000000, 0x00000000, 0x00000000, 0x00000000,
    0x00000000, 0x00000000, 0x00000000, 0x00000000,
    0x00000000, 0x00000000, 0x00000000, 0x00000000,
    0x00000000, 0x00000000, 0x00000000, 0x00000000,
};

static const uint32_t g_tc_ring_one_special_bits[] = {394, 397, 405, 343, 394, 393, 392, 377};

static void* tc_ring_one_thread_entry(void* arg);

static int get_numa_node(void)
{
    return numa_max_node() + 1;
}

static int is_cpu_online(int core_id)
{
    char online_file[64];
     struct stat buffer;
    int online;
    FILE *fp;

    snprintf(online_file, sizeof(online_file), "/sys/devices/system/cpu/cpu%d/online", core_id);
    if ((core_id == 0) && (lstat(online_file, &buffer) != 0)) {
        return 1;
    }

    fp = fopen(online_file, "r");
    if (!fp) {
        logging_error("Failed to open %s\n", online_file);
        return 0;
    }

    fscanf(fp, "%d", &online);
    fclose(fp);

    return online;
}

static uintptr_t vaddr_to_phys(uintptr_t vaddr)
{
    int page_size = sysconf(_SC_PAGESIZE);
    char page_map_name[64];
    int pid = getpid();
    uintptr_t offset;
    uintptr_t pinfo;
    int fd;

    offset = vaddr / page_size * (sizeof(pinfo));
    sprintf(page_map_name, "/proc/%d/pagemap", pid);
    fd = open(page_map_name, O_RDONLY);
    if (fd < 0) {
        logging_error("Failed to open %s\n", page_map_name);
        return 0;
    }
    if (pread(fd, &pinfo, sizeof(pinfo), offset) != sizeof(pinfo)) {
        logging_error("Failed to read %s\n", page_map_name);
        close(fd);
        return 0;
    }

    close(fd);
    if((pinfo & (1ULL << 63)) == 0) {
        logging_error("pfn is not present\n");
        return 0;
    } else {
        return (pinfo & ((1ULL << 55) - 1)) * page_size + (vaddr & (page_size - 1));
    }
}

static int get_numa_node_of_core(int core_id)
{
    int numa_node = numa_node_of_cpu(core_id);;

    if (numa_node < 0) {
        logging_error("[CORE%d] numa_node_of_cpu failed, errno:%d\n", core_id, errno);
    }

    return numa_node;
}

/**
 * 从指定 NUMA 节点优先分配内存，若失败则尝试其他节点
 * @numa_node:          系统numa总数
 * @preferred_node:     优先分配的 NUMA 节点号
 * @size:               需要分配的内存大小（字节）
 * @return:             成功返回内存指针，失败返回 NULL
 */
static void *numa_alloc_fallback(int numa_node, int preferred_node, size_t size)
{
    struct bitmask *allowed_nodes;
    void *ptr = NULL;
    int node;

    // 1. 获取所有可用的 NUMA 节点
    allowed_nodes = numa_get_mems_allowed();
    if (!allowed_nodes) {
        logging_error("Failed to get allowed NUMA nodes\n");
        return NULL;
    }

    // 2. 优先从指定节点分配内存
    if (numa_bitmask_isbitset(allowed_nodes, preferred_node)) {
        ptr = numa_alloc_onnode(size, preferred_node);
        if (ptr != NULL) {
            logging_debug("Allocated %#x bytes on NUMA assigned node %d, addr: %p\n", size, preferred_node, ptr);
            return ptr;
        }
    }

    // 3. 遍历所有节点（跳过优先节点）
    for (node = 0; node < numa_node; node++) {
        if (node == preferred_node || !numa_bitmask_isbitset(allowed_nodes, node)) {
            continue;  // 跳过优先节点或不允许的节点
        }

        ptr = numa_alloc_onnode(size, node);
        if (ptr != NULL) {
            logging_debug("Allocated %#x bytes on NUMA other node %d, addr: %p\n", size, node, ptr);
            return ptr;
        }
    }

    // 4. 所有节点均失败，尝试跨节点分配
    ptr = numa_alloc_interleaved(size);
    if (ptr == NULL) {
        logging_error("Failed to allocate %#x bytes on any NUMA node\n", size);
    }

    return ptr;
}

static void tc_ring_one_space_init(void *base, size_t size)
{
    int i;

    for (i = 0; i < size; i += TC_RING_ONE_DATA_UNIT) {
        memcpy((char*)base + i, tc_ring_one_pattern, sizeof(tc_ring_one_pattern));
    }
}

static bool is_core_invalid(struct tc_ring_one_config *config, int core_id)
{
    return config->black_list[core_id] || !is_cpu_online(core_id);
}

static int tc_ring_one_ctrl_var_init(struct tc_ring_one_config *config)
{
    pthread_mutexattr_t attr;
    int valid_core_num = 0;
    int i;

    for (i = 0; i < config->sys_core_total; i++) {
        if (!is_core_invalid(config, i)) {
            valid_core_num++;
        }
    }

    if (pthread_mutexattr_init(&attr) != 0) {
        logging_error("Failed to initialize mutex attribute\n");
        return TC_RING_ONE_PRAMA_ERR;
    }

    pthread_mutexattr_settype(&attr, PTHREAD_MUTEX_ERRORCHECK);
    config->tc_node_mutex = (pthread_mutex_t *)calloc(config->numa_node, sizeof(pthread_mutex_t));
    if (config->tc_node_mutex == NULL) {
        logging_error("Failed to allocate memory for tc_mutex\n");
        goto mutex_alloc_fail;
    }

    for (i = 0; i < config->numa_node; i++) {
        if (pthread_mutex_init(&(config->tc_node_mutex[i]), &attr) != 0) {
            logging_error("Failed to initialize mutex %d\n", i);
            goto mutex_init_fail;
        }
    }

    config->tc_core_threads = (pthread_t *)calloc(config->sys_core_total, sizeof(pthread_t));
    if (config->tc_core_threads == NULL) {
        logging_error("Failed to allocate memory for tc_core_threads\n");
        goto mutex_init_fail;
    }

    pthread_mutexattr_destroy(&attr);
    pthread_barrier_init(&config->tc_barrier, NULL, valid_core_num);
    return TC_RING_ONE_SUCCESS;

mutex_init_fail:
    for (i = i - 1; i >= 0; i--) {
        pthread_mutex_destroy(&config->tc_node_mutex[i]);
    }

    free(config->tc_node_mutex);
    config->tc_node_mutex = NULL;

mutex_alloc_fail:
    pthread_mutexattr_destroy(&attr);
    return TC_RING_ONE_PRAMA_ERR;
}

static int tc_ring_one_init(struct tc_ring_one_config *config)
{
    int ret, i;
    void *ptr;

    if (numa_available() < 0) {
        logging_error("NUMA is not available on this system\n");
        return TC_RING_ONE_PRAMA_ERR;
    }

    // 为每个 NUMA 节点分配测试内存空间
    config->test_space_base = (void **)calloc(config->numa_node, sizeof(void *));
    if (config->test_space_base == NULL) {
        logging_error("Failed to allocate memory for test_space_base\n");
        return TC_RING_ONE_PRAMA_ERR;
    }

    for (i = 0; i < config->numa_node; i++) {
        ptr = numa_alloc_fallback(config->numa_node, i, config->mem_size);
        if (ptr == NULL) {
            ret = TC_RING_ONE_PRAMA_ERR;
            goto numa_alloc_fail;
        }

        tc_ring_one_space_init(ptr, config->mem_size);
        config->test_space_base[i] = ptr;
    }

    config->node_update_flag = (uint32_t *)calloc(config->numa_node, sizeof(uint32_t));
    if (config->node_update_flag == NULL) {
        logging_error("Failed to allocate memory for node_update_flag\n");
        ret = TC_RING_ONE_PRAMA_ERR;
        goto numa_alloc_fail;
    }

    for (i = 0; i < config->numa_node; i++) {
            config->node_update_flag[i] = 0;
    }

    ret = tc_ring_one_ctrl_var_init(config);
    if (ret != 0) {
        logging_error("tc_ring_one_ctrl_var_init fail ret:%d\n", ret);
        goto ctrl_var_init_fail;
    }

    return ret;

ctrl_var_init_fail:
    free(config->node_update_flag);
    config->node_update_flag = NULL;

numa_alloc_fail:
    for (i = i - 1; i >= 0; i--) {
        numa_free(config->test_space_base[i], config->mem_size);
    }

    free(config->test_space_base);
    config->test_space_base = NULL;
    return ret;
}

static void tc_ring_one_release(struct tc_ring_one_config *config)
{
    int node;

    for (int i = 0; i < config->numa_node; i++) {
        numa_free(config->test_space_base[i], config->mem_size);
    }

    free(config->test_space_base);
    config->test_space_base = NULL;
    free(config->node_update_flag);
    config->node_update_flag = NULL;
    pthread_barrier_destroy(&(config->tc_barrier));
    for (node = 0; node < config->numa_node; node++) {
        pthread_mutex_destroy(&config->tc_node_mutex[node]);
    }

    free(config->tc_node_mutex);
    config->tc_node_mutex = NULL;
}

// 将线程绑定到指定 CORE
static int bind_thread_to_core(pthread_t thread, int core_id)
{
    cpu_set_t cpuset;
    int ret = 0;

    CPU_ZERO(&cpuset);
    CPU_SET(core_id, &cpuset);

    ret = pthread_setaffinity_np(thread, sizeof(cpu_set_t), &cpuset);
    if (ret != 0) {
        logging_error("pthread_setaffinity_np failed\n");
        ret = TC_RING_ONE_PRAMA_ERR;
    }

    return ret;
}

static int tc_ring_one_exec(struct tc_ring_one_config *config)
{
    int ret;
    int i;

    ret = tc_ring_one_init(config);
    if (ret != 0) {
        logging_error("tc_ring_one_init fail ret:%d\n", ret);
        return ret;
    }

    for (i = 0; i < config->sys_core_total; i++) {
        if (is_core_invalid(config, i)) {
            // 跳过黑名单 & offline 的core
            continue;
        }

        ret = pthread_create(&config->tc_core_threads[i], NULL, tc_ring_one_thread_entry, (void *)config);
        if (ret != 0) {
            logging_error("Failed to create thread for core %d\n", i);
            goto pthread_create_fail;
        }

        ret = bind_thread_to_core(config->tc_core_threads[i], i);
        if (ret != 0) {
            logging_error("Failed to bind thread to core %d\n", i);
            goto pthread_bind_fail;
        }
    }

    // 等待所有线程完成
    for (i = 0; i < config->sys_core_total; i++) {
        if (is_core_invalid(config, i)) {
            // 跳过黑名单 & offline 的core
            continue;
        }

        pthread_join(config->tc_core_threads[i], NULL);
    }

    if (config->err_flag > 0) {
        ret = TC_RING_ONE_FAIL;
    } else {
        ret = TC_RING_ONE_SUCCESS;
    }

pthread_bind_fail:
    pthread_cancel(config->tc_core_threads[i]);
    pthread_join(config->tc_core_threads[i], NULL);

pthread_create_fail:
    for (i = i - 1; i >= 0; i--) {
        if (is_core_invalid(config, i)) {
            continue;
        }

        pthread_cancel(config->tc_core_threads[i]);
        pthread_join(config->tc_core_threads[i], NULL);
    }

    tc_ring_one_release(config);
    free(config->tc_core_threads);
    config->tc_core_threads = NULL;
    return ret;
}

void tc_ring_one_post_process(uint64_t err_handle, int result)
{
    if (result == TC_RING_ONE_SUCCESS) {
        logging_info("tc_ring_one test pass\n");
    } else if (result == TC_RING_ONE_FAIL) {
        switch (err_handle) {  // 根据错误处理策略进行相应的处理
            case TC_ERROR_HANDLE_NONE:
                logging_error("the system administrator must handle this error!!!\n");
                break;
            case TC_ERROR_HANDLE_SHUTDOWN:
                    logging_error("Execute 'shutdown'\n");
                if (reboot(RB_POWER_OFF) < 0) {
                    logging_error("ERROR: Failed to execute 'shutdown'\n");
                }
                break;
            case TC_ERROR_HANDLE_REBOOT:
                    logging_error("Execute 'reboot'\n");
                if (reboot(RB_AUTOBOOT) < 0) {
                    logging_error("ERROR: Failed to execute 'reboot'\n");
                }
                break;
            default: // panic
                abort();
                break;
        }
    } else {
        // 通过log打印
        logging_error("The system can not run the tc_ring_one:\n");
        logging_error("1. the system must support NUMA\n");
        logging_error("2. the memory in the system maybe too small\n");
        soc_ring_sentry_report(RESULT_LEVEL_SKIP, "The system can not run the tc_ring_one testcase");
    }
}

int tc_ring_one_main(uint64_t mem_size, uint64_t loop_cnt, uint64_t delay,
                               uint64_t err_handle, bool *blacklist, size_t core_num)
{
    struct tc_ring_one_config tc_config = { 0 };
    int ret;

    tc_config.mem_size = mem_size;
    tc_config.loop_cnt = loop_cnt;
    tc_config.delay_ms = delay;
    tc_config.err_handle = err_handle;
    tc_config.black_list = blacklist;
    tc_config.sys_core_total = core_num;
    tc_config.block_size = TC_RING_ONE_BLOCK_SIZE;
    tc_config.rd_loop = TC_RING_ONE_RD_LOOP;
    tc_config.numa_node = get_numa_node();

    ret = tc_ring_one_exec(&tc_config);
    tc_ring_one_post_process(err_handle, ret);

    return ret;
}

static void tc_ring_one_init_data_pattern(uintptr_t base, size_t size, int scan_bit)
{
    uint64_t dat_pattern = (1ULL << (scan_bit & 0x3F));
    size_t word_offset = (scan_bit >> 6) << 3;              // 待测试bit在cacheline中的word的偏移位置(一个word为64 bit)
    int i;

    for (i = 0; i < size; i += TC_RING_ONE_DATA_UNIT) {
        *((uint64_t *)(base + i + word_offset + TC_RING_ONE_CACHELINE_SIZE)) = dat_pattern;
    }
}

static void tc_ring_one_data_clear(uintptr_t base, size_t size, int scan_bit)
{
    size_t word_offset = (scan_bit >> 6) << 3;				// 待测试bit在cacheline中的word的偏移位置(一个word为64 bit)
    int i;

    for (i = 0; i < size; i += TC_RING_ONE_DATA_UNIT) {
        *((uint64_t *)(base + i + word_offset + TC_RING_ONE_CACHELINE_SIZE)) = 0;
    }
}

static void tc_ring_one_testspace_update(struct tc_ring_one_config *config, int scan_bit)
{
    int core_id = sched_getcpu();
    int numa_node = get_numa_node_of_core(core_id);

    pthread_barrier_wait(&config->tc_barrier);
    if (numa_node >= 0) {
        pthread_mutex_lock(&config->tc_node_mutex[numa_node]);
        if (config->node_update_flag[numa_node] == 0) {
            tc_ring_one_init_data_pattern((uintptr_t)config->test_space_base[numa_node], config->mem_size, scan_bit);
            config->node_update_flag[numa_node] = 1;
        }

        pthread_mutex_unlock(&config->tc_node_mutex[numa_node]);
    }

    pthread_barrier_wait(&config->tc_barrier);
}

static void tc_ring_one_testspace_recover(struct tc_ring_one_config *config, int scan_bit)
{
    uint32_t core_id = sched_getcpu();
    int numa_node = get_numa_node_of_core(core_id);

    pthread_barrier_wait(&config->tc_barrier);
    if (numa_node >= 0) {
        pthread_mutex_lock(&config->tc_node_mutex[numa_node]);
        if (config->node_update_flag[numa_node] == 1) {
            tc_ring_one_data_clear((uintptr_t)config->test_space_base[numa_node], config->mem_size, scan_bit);
            config->node_update_flag[numa_node] = 0;
        }
        pthread_mutex_unlock(&config->tc_node_mutex[numa_node]);
    }

    pthread_barrier_wait(&config->tc_barrier);
}

/**
 * tc_ring_one_scan_test_block - 针对测试空间的指定块空间进行读扫描, 确保在块空间的的指定bit位置不存在非预期的由1跳变成0的情况
 * @base_addr:		测试空间中指定测试块首地址(必须为128B对齐地址)
 * @scan_bit:	    待测试bit位置(0-511)
 * @block_size:	    待测试块空间大小
 * @loop_cnt:	    巡检次数
 *
 * 在调用本函数之前，要保证测试空间已经被待验证的数据Pattern初始化。
 * 待验证的数据Pattern:
 *     - base_addr + n * 64        各个数据bit为1
 *     - base_addr + (n + 1) * 64  待验证的数据bit为1, 其余数据bit为0
 *
 * 注意: 调用者要保证 base_addr + block_size 不能超过测试空间长度
 */
static bool tc_ring_one_scan_test_block(uintptr_t base_addr, int scan_bit, size_t block_size, uint64_t loop_cnt)
{
    uint64_t tgt_dat_pattern = (1ULL << (scan_bit & 0x3F));
    size_t word_offset = (scan_bit >> 6) << 3;			// 待测试bit在cacheline中的word的偏移位置(一个word为64 Byte)
    uint64_t tgt_dat_all_one = ~0x0ULL;
    char err_msg[1024];
    uint64_t rd_data[2];
    size_t i;

    for (i = 0; i < block_size; i += TC_RING_ONE_DATA_UNIT) {
        rd_data[0] = *((uint64_t *)(base_addr + i + word_offset));                              // base_addr + n * 64 + word_offset
        rd_data[1] = *((uint64_t *)(base_addr + i + TC_RING_ONE_CACHELINE_SIZE + word_offset)); // base_addr + (n + 1) * 64 + word_offset
        if((rd_data[0] != tgt_dat_all_one) || (rd_data[1] != tgt_dat_pattern)) {
            snprintf(err_msg, sizeof(err_msg), "[ERROR][CORE%d] test loop %lu vaddr = %#lx paddr = %#lx read_data = %#llx read_disturb = %#llx "
                "target_data = %#llx bit_index = %d offset = %#lx block_size = %#lx",
                sched_getcpu(), loop_cnt, (base_addr + i + word_offset), vaddr_to_phys(base_addr + i + word_offset), rd_data[1], rd_data[0],
                tgt_dat_pattern, scan_bit, word_offset, block_size);
            soc_ring_sentry_report(RESULT_LEVEL_MAJOR_ALM, err_msg);
            return false;
        }
    }

    return true;
}

static bool tc_ring_one_scan_bit(struct tc_ring_one_config *config, int scan_bit, uint64_t loop_cnt)
{
    int core_id = sched_getcpu();
    int numa_node = get_numa_node_of_core(core_id);;
    uint32_t i, j;

    // numa为无效值时直接返回，不再执行扫描测试
    if (numa_node < 0) {
        return true;
    }

    for (i = 0; i < config->rd_loop; i++) {
        for (j = 0; j < config->mem_size; j += config->block_size) {
            // 按测试块大小，扫描测试空间
            if (!tc_ring_one_scan_test_block((uintptr_t)((char *)(config->test_space_base[numa_node])) + j,
                                        scan_bit, config->block_size, loop_cnt)) {
                __atomic_add_fetch(&config->err_flag, 1, __ATOMIC_SEQ_CST);
                return false;
            }

            if (config->delay_ms > 0) {
                // 每扫描完一个测试块就休眠一段时间
                usleep(config->delay_ms * 1000);
            }
        }
    }

    return true;
}

static bool tc_ring_one_test_issue(struct tc_ring_one_config *config, int scan_bit, int loop_cnt)
{
    bool ret;

    tc_ring_one_testspace_update(config, scan_bit);
    ret = tc_ring_one_scan_bit(config, scan_bit, loop_cnt);
    tc_ring_one_testspace_recover(config, scan_bit);

    if (config->err_flag) {
        return false;
    }

    return ret;
}

static void* tc_ring_one_thread_entry(void *arg)
{
    struct tc_ring_one_config *config = arg;
    int scan_sequence_id = 0;
    int scan_special_id = 0;
    uint64_t loop_cnt = 0;
    uint64_t tc_flag = 1;

    while (tc_flag == 1 && config->err_flag == 0) {
        config->scan_bit = scan_sequence_id;
        pthread_barrier_wait(&config->tc_barrier);
        if (!tc_ring_one_test_issue(config, config->scan_bit, loop_cnt)) {
            break;
        }

        scan_sequence_id = (scan_sequence_id + 1) % (TC_RING_ONE_CACHELINE_SIZE * 8);
        scan_special_id = g_tc_ring_one_special_bits[random() % 8];
        config->scan_bit = scan_special_id;
        pthread_barrier_wait(&config->tc_barrier);
        if (!tc_ring_one_test_issue(config, config->scan_bit, loop_cnt)) {
            break;
        }

        loop_cnt++;
        if ((config->loop_cnt != 0) && (loop_cnt >= config->loop_cnt)) {
            tc_flag = 0;
        }
    }

    return config;
}

// end of tc_ring_one.c
