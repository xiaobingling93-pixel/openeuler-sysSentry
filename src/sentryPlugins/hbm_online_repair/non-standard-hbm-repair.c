/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2023-2025. All rights reserved.
 * Description: hbm online repair core functions
 * Author: luckky
 * Create: 2024-10-30
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdbool.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <linux/fs.h>
#include <sys/stat.h>
#include <sys/ioctl.h>

#include "logger.h"
#include "non-standard-hbm-repair.h"

extern int page_isolation_threshold;
size_t flash_total_size = 0;
struct hisi_common_error_section {
    uint32_t   val_bits;
    uint8_t    version;
    uint8_t    soc_id;
    uint8_t    socket_id;
    uint8_t    totem_id;
    uint8_t    nimbus_id;
    uint8_t    subsystem_id;
    uint8_t    module_id;
    uint8_t    submodule_id;
    uint8_t    core_id;
    uint8_t    port_id;
    uint16_t   err_type;
    struct {
        uint8_t  function;
        uint8_t  device;
        uint16_t segment;
        uint8_t  bus;
        uint8_t  reserved[3];
    }          pcie_info;
    uint8_t    err_severity;
    uint8_t    reserved[3];
    uint32_t   reg_array_size;
    uint32_t   reg_array[];
};

struct fault_addr_info {
    uint32_t fields[FAULT_FIELD_NUM];
};

typedef struct {
    const char* name;
    uint32_t len;
} fault_field_meta;

static const fault_field_meta field_meta[FAULT_FIELD_NUM] = {
    {"processor_id", FAULT_ADDR_PROCESSOR_ID_LEN},
    {"die_id", FAULT_ADDR_DIE_ID_LEN},
    {"stack_id", FAULT_ADDR_STACK_ID_LEN},
    {"sid", FAULT_ADDR_SID_LEN},
    {"channel_id", FAULT_ADDR_CHANNEL_ID_LEN},
    {"bankgroup_id", FAULT_ADDR_BANKGROUP_ID_LEN},
    {"bank_id", FAULT_ADDR_BANK_ID_LEN},
    {"row_id", FAULT_ADDR_ROW_ID_LEN},
    {"column_id", FAULT_ADDR_COLUMN_ID_LEN},
    {"error_type", FAULT_ADDR_ERROR_TYPE_LEN},
    {"repair_type", FAULT_ADDR_REPAIR_TYPE_LEN},
    {"reserved", FAULT_ADDR_RESERVED_LEN},
    {"crc8", FAULT_ADDR_CRC8_LEN},
};

typedef struct {
    const char    *VariableName;
    const char    *VendorGuid;
    uint32_t      DataSize;
    uint8_t       *Data;
    uint32_t      Attributes;
} efi_variable_t;

char* flash_names[FLASH_ENTRY_NUM] = {
    "repair0000",
    "repair0001",
    "repair0100",
    "repair0101",
    "repair0200",
    "repair0201",
    "repair0300",
    "repair0301",
};
char *flash_guids[FLASH_ENTRY_NUM] = {
    "CD2FF4D9-D937-4e1d-B810-A1A568C37C01",
    "DD92CC91-43E6-4c69-A42A-B08F72FCB157",
    "4A8E0D1E-4CFA-47b2-9359-DA3A0006878B",
    "733F9979-4ED4-478d-BD6A-E4D0F0390FDB",
    "9BFBBA1F-5A93-4d36-AD47-D3C2D714D914",
    "A0920D6F-78B8-4c09-9F61-7CEC845F116C",
    "0049CE5E-8C18-414c-BDC1-A87E60CEEFD7",
    "6AED17B4-50C7-4a40-A5A7-48AF55DD8EAC"
};

static int get_guid_index(uint32_t socket_id, uint32_t error_type)
{
    if (2 * socket_id + error_type >= FLASH_ENTRY_NUM)
        return -1;
    return 2 * socket_id + error_type;
}

static void parse_fault_addr_info(struct fault_addr_info* info_struct, unsigned long long fault_addr)
{
    for (int i = 0; i < FAULT_FIELD_NUM - 1; i++) {
        const fault_field_meta* meta = &field_meta[i];
        info_struct->fields[i] = (uint32_t)(fault_addr & FAULT_ADDR_FIELD_MASK(meta->len));
        fault_addr >>= meta->len;
    }
    info_struct->fields[FAULT_FIELD_NUM - 1] = (uint32_t)fault_addr;
}

static void log_fault_addr_info(enum log_level level, const struct fault_addr_info* info_struct)
{
    for (int i = 0; i < FAULT_FIELD_NUM; i++)
        log(level, "info_struct.%s is %u\n", field_meta[i].name, info_struct->fields[i]);
}

static bool is_variable_existing(char *name, char *guid)
{
    char filename[PATH_MAX];
    snprintf(filename, PATH_MAX - 1, "%s/%s-%s", EFIVARFS_PATH, name, guid);

    return access(filename, F_OK | R_OK) == 0;
}

static size_t get_var_size(char *name, char *guid) {
    char filename[PATH_MAX];
    int fd;
    struct stat stat;

    snprintf(filename, PATH_MAX - 1, "%s/%s-%s", EFIVARFS_PATH, name, guid);

    // open var file
    fd = open(filename, O_RDONLY);
    if (fd < 0) {
        log(LOG_WARNING, "open %s failed\n", filename);
        goto err;
    }
    // read stat
    if (fstat(fd, &stat) != 0) {
        log(LOG_WARNING, "fstat %s failed\n", filename);
        goto err;
    }
    close(fd);
    return stat.st_size;
err:
    if (fd >= 0)
        close(fd);
    return (size_t)-1;
}

void get_flash_total_size() {
    for (int i = 0; i < FLASH_ENTRY_NUM; i++) {
        if (is_variable_existing(flash_names[i], flash_guids[i])) {
            flash_total_size += get_var_size(flash_names[i], flash_guids[i]);
        }
    }
    // check total entry size
    log(LOG_DEBUG, "current fault info total size: %luKB, flash max threshold: %uKB\n",
           flash_total_size / KB_SIZE, MAX_VAR_SIZE / KB_SIZE);
    if (flash_total_size > MAX_VAR_SIZE) {
        log(LOG_WARNING, "fault info storage %zu reach threshold, cannot save new record\n", flash_total_size);
    }
}

static int read_variable_attribute(char *name, char *guid, uint32_t *attribute) {
    char filename[PATH_MAX];
    int fd;
    size_t readsize;

    snprintf(filename, PATH_MAX - 1, "%s/%s-%s", EFIVARFS_PATH, name, guid);

    // open var file
    fd = open(filename, O_RDONLY);
    if (fd < 0) {
        log(LOG_ERROR, "open %s failed\n", filename);
        return -1;
    }

    // read attributes from first 4 bytes
    readsize = read(fd, attribute, sizeof(uint32_t));
    if (readsize != sizeof(uint32_t)) {
        log(LOG_ERROR, "read attribute of %s failed\n", filename);
        return -1;
    }

    close(fd);
    return 0;
}

static int efivarfs_set_mutable(char *name, char *guid, bool mutable)
{
	unsigned long orig_attrs, new_attrs;
    char filename[PATH_MAX];
    int fd;

    snprintf(filename, PATH_MAX - 1, "%s/%s-%s", EFIVARFS_PATH, name, guid);

    fd = open(filename, O_RDONLY);
    if (fd < 0) {
        log(LOG_ERROR, "open %s failed\n", filename);
        goto err;
    }

	if (ioctl(fd, FS_IOC_GETFLAGS, &orig_attrs) == -1) {
		log(LOG_ERROR, "ioctl FS_IOC_GETFLAGS failed\n");
		goto err;
	}

    if (mutable)
	    new_attrs = orig_attrs & ~(unsigned long)FS_IMMUTABLE_FL;
    else
        new_attrs = orig_attrs | FS_IMMUTABLE_FL;

    if (new_attrs == orig_attrs) {
        close(fd);
        return 0;
    }

	if (ioctl(fd, FS_IOC_SETFLAGS, &new_attrs) == -1) {
		log(LOG_ERROR, "ioctl FS_IOC_SETFLAGS failed\n");
		goto err;
	}
    close(fd);
	return 0;
err:
    if (fd >= 0)
        close(fd);
    return -1;
}

static int write_variable(char *name, char *guid, void *value, unsigned long size, uint32_t attribute, bool is_existing) {
    int fd = -1, mode;
    size_t writesize;
    void *buffer;
    unsigned long total;
    char filename[PATH_MAX];

    snprintf(filename, PATH_MAX - 1, "%s/%s-%s", EFIVARFS_PATH, name, guid);

    // prepare attributes(size 4 bytes) and data
    total = size + sizeof(uint32_t);
    buffer = malloc(total);
    if (buffer == NULL) {
        log(LOG_ERROR, "malloc data for %s failed\n", filename);
        goto err;
    }
    memcpy(buffer, &attribute, sizeof(uint32_t));
    memcpy(buffer + sizeof(uint32_t), value, size);

    // change attr
    if (is_existing && efivarfs_set_mutable(name, guid, 1) != 0) {
        log(LOG_ERROR, "set mutable for %s failed\n", filename);
        goto err;
    }

    mode = O_WRONLY;
    mode |= is_existing ? O_APPEND : O_CREAT;

    // open var file
    fd = open(filename, mode, S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH);
    if (fd < 0) {
        log(LOG_ERROR, "open %s failed\n", filename);
        goto err;
    }

    // write to var file
    writesize = write(fd, buffer, total);
    if (writesize != total) {
        log(LOG_ERROR, "write %s failed\n", filename);
        goto err;
    }

    close(fd);
    free(buffer);
    if (is_existing && efivarfs_set_mutable(name, guid, 0) != 0) {
        log(LOG_ERROR, "set immutable for %s failed\n", filename);
    }
    return 0;
err:
    if (fd >= 0)
        close(fd);
    if (buffer)
        free(buffer);
    if (is_existing && efivarfs_set_mutable(name, guid, 0) != 0) {
        log(LOG_ERROR, "set immutable for %s failed\n", filename);
    }
    return -1;
}

static int write_fault_info_to_flash(const struct hisi_common_error_section *err) {
    int ret, guid_index;
    uint32_t reg_size;
    uint64_t fault_addr;
    bool is_existing;
    uint32_t attribute = -1;

    // check flash usage threshold
    if (flash_total_size + sizeof(uint64_t) > MAX_VAR_SIZE) {
        log(LOG_WARNING, "fault info storage reach threshold, cannot save new record into flash\n");
        return -1;
    }

    // parse physical addr
    reg_size = err->reg_array_size / sizeof(uint32_t);
    fault_addr = err->reg_array[reg_size - 1];
    fault_addr <<= TYPE_UINT32_WIDTH;
    fault_addr += err->reg_array[reg_size - 2];

    // get guid
    struct fault_addr_info info_struct;
    parse_fault_addr_info(&info_struct, fault_addr);
    guid_index = get_guid_index(info_struct.fields[PROCESSOR_ID], info_struct.fields[ERROR_TYPE]);
    if (guid_index < 0) {
        log(LOG_ERROR, "invalid fault info\n");
        return -1;
    }

    // judge if the efivar is existing to set the attribute
    is_existing = is_variable_existing(flash_names[guid_index], flash_guids[guid_index]);
    attribute = EFI_VARIABLE_NON_VOLATILE |
                EFI_VARIABLE_BOOTSERVICE_ACCESS |
                EFI_VARIABLE_RUNTIME_ACCESS;
    if (is_existing) {
        ret = read_variable_attribute(flash_names[guid_index], flash_guids[guid_index], &attribute);
        if (ret < 0) {
            log(LOG_ERROR, "read variable %s-%s attribute failed, stop writing\n", flash_names[guid_index], flash_guids[guid_index]);
            return -1;
        }
        attribute |= EFI_VARIABLE_APPEND_WRITE;
    }

    // record physical addr in flash
    ret = write_variable(flash_names[guid_index], flash_guids[guid_index], &fault_addr, sizeof(uint64_t), attribute, is_existing);
    if (ret < 0) {
        log(LOG_ERROR, "write to %s-%s failed\n", flash_names[guid_index], flash_guids[guid_index]);
        return -1;
    }
    flash_total_size += sizeof(uint64_t);
    log(LOG_INFO, "write hbm fault info to flash %s-%s success\n", flash_names[guid_index], flash_guids[guid_index]);
    return 0;
}

static int write_file(char *path, const char *name, unsigned long long value)
{
    char fname[MAX_PATH];
    char buf[20];
    int ret;
    int fd;

    snprintf(fname, MAX_PATH, "%s/%s", path, name);

    fd = open(fname, O_WRONLY);
    if (fd < 0) {
        log(LOG_WARNING, "HBM: Cannot to open '%s': %s\n",
                    fname, strerror(errno));
        return -errno;
    }

    snprintf(buf, sizeof(buf), "0x%llx\n", value);
    ret = write(fd, buf, strlen(buf));
    if (ret <= 0)
        log(LOG_WARNING, "HBM: Failed to set %s (0x%llx): %s\n",
                    fname, value, strerror(errno));

    close(fd);
    if (ret == 0) {
        ret = -EINVAL;
    } else if (ret < 0) {
        ret = -errno;
    }
    return ret;
}

static int get_hardware_corrupted_size()
{
    FILE *fp;
    char line[256];
    int hardware_corrupted_size = -1;
    char *key = "HardwareCorrupted:";

    fp = fopen("/proc/meminfo", "r");
    if (fp == NULL) {
        log(LOG_ERROR, "Failed to open /proc/meminfo\n");
        return -1;
    }

    while (fgets(line, sizeof(line), fp) != NULL) {
        char *pos;
        if ((pos = strstr(line, key)) != NULL) {
            sscanf(pos, "HardwareCorrupted: %5d kB\n", &hardware_corrupted_size);
            break;
        }
    }

    fclose(fp);
    return hardware_corrupted_size;
}

static uint8_t get_repair_failed_result_code(int ret)
{
    if (ret == -ENOSPC) {
        return REPAIR_FAILED_NO_RESOURCE;
    } else if (ret == -EIO) {
        return REPAIR_FAILED_OTHER_REASON;
    } else if (ret == -ENXIO || ret == -EINVAL) {
        return REPAIR_FAILED_INVALID_PARAM;
    }
    return REPAIR_FAILED_OTHER_REASON;
}

static int notice_BMC(const struct hisi_common_error_section *err, uint8_t repair_result_code)
{
    int sockfd;
    struct sockaddr_un addr;
    char bmc_msg[sizeof(BMC_REPORT_FORMAT)] = {0};
    uint8_t repair_type_code, isolation_type_code;
    uint32_t repair_type;
    unsigned long long fault_addr;

    sockfd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (sockfd < 0) {
        log(LOG_ERROR, "Failed to create BMC notice socket\n");
        return -1;
    }

    memset(&addr, 0, sizeof(struct sockaddr_un));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, BMC_SOCKET_PATH, sizeof(addr.sun_path) - 1);
    if (connect(sockfd, (struct sockaddr *)&addr, sizeof(struct sockaddr_un)) < 0) {
        log(LOG_ERROR, "Failed to connect BMC notice socket\n");
        close(sockfd);
        return -1;
    }

    /* assemble bmc specific msg */
    repair_type_code = 0;
    isolation_type_code = 0;
    repair_type = err->reg_array[HBM_REPAIR_REQ_TYPE];
    if (repair_type & HBM_CE_ACLS) {
        repair_type_code = 0;
        isolation_type_code = SINGLE_ADDR_FAULT;
    } else if (repair_type & HBM_PSUE_ACLS) {
        repair_type_code = 1;
        isolation_type_code = SINGLE_ADDR_FAULT;
    } else if (repair_type & HBM_CE_SPPR) {
        repair_type_code = 2;
        isolation_type_code = ROW_FAULT;
    } else if (repair_type & HBM_PSUE_SPPR) {
        repair_type_code = 3;
        isolation_type_code = ROW_FAULT;
    }
    
    const uint32_t reg_size = err->reg_array_size / sizeof(uint32_t);

    fault_addr = err->reg_array[reg_size - 1];
    fault_addr <<= TYPE_UINT32_WIDTH;
    fault_addr += err->reg_array[reg_size - 2];

    log(LOG_DEBUG, "Get the fault addr is %llu\n", fault_addr);

    struct fault_addr_info info_struct;
    parse_fault_addr_info(&info_struct, fault_addr);

    log_fault_addr_info(LOG_DEBUG, &info_struct);

    snprintf(bmc_msg, sizeof(BMC_REPORT_FORMAT), BMC_REPORT_FORMAT,
        repair_type_code,
        repair_result_code,
        isolation_type_code,
        info_struct.fields[PROCESSOR_ID],
        info_struct.fields[DIE_ID],
        info_struct.fields[STACK_ID],
        info_struct.fields[SID],
        info_struct.fields[CHANNEL_ID],
        info_struct.fields[BANKGROUP_ID],
        info_struct.fields[BANK_ID],
        info_struct.fields[ROW_ID],
        info_struct.fields[COLUMN_ID]
    );

    log(LOG_DEBUG, "Send msg to sysSentry, bmc msg is %s\n", bmc_msg);

    if (write(sockfd, bmc_msg, strlen(bmc_msg)) <= 0) {
        log(LOG_ERROR, "Failed to send data to BMC notice socket\n");
        close(sockfd);
        return -1;
    }

    close(sockfd);
    return 0;
}

static int hbmc_hbm_page_isolate(const struct hisi_common_error_section *err)
{
    unsigned long long paddr;
    int ret;
    bool is_acls = err->reg_array[HBM_REPAIR_REQ_TYPE] & (HBM_CE_ACLS | HBM_PSUE_ACLS);
    int required_isolate_size = (is_acls ? HBM_ACLS_ADDR_NUM : HBM_SPPR_ADDR_NUM) * DEFAULT_PAGE_SIZE_KB;
    int hardware_corrupted_size = get_hardware_corrupted_size();
    if (hardware_corrupted_size < 0) {
        log(LOG_ERROR, "Page isolate failed: Get hardware_corrupted_size failed");
        notice_BMC(err, ISOLATE_FAILED_OTHER_REASON);
        return -1;
    }
    if ((required_isolate_size + hardware_corrupted_size) > page_isolation_threshold) {
        log(LOG_INFO, "Page isolate failed: the isolation resource is not enough\n");
        notice_BMC(err, ISOLATE_FAILED_OVER_THRESHOLD);
        return -1;
    }
    if (is_acls) {
        /* ACLS */
        paddr = err->reg_array[HBM_ADDH];
        paddr <<= TYPE_UINT32_WIDTH;
        paddr += err->reg_array[HBM_ADDL];

        ret = write_file("/sys/kernel/page_eject", "offline_page", paddr);
        if (ret < 0) {
            notice_BMC(err, ISOLATE_FAILED_OTHER_REASON);
            log(LOG_WARNING, "HBM: ACLS offline failed, address is 0x%llx \n", paddr);
            return ret;
        }
    } else {
        /* SPPR */
        bool all_success = true;
        uint32_t i;
        for (i = 0; i < HBM_SPPR_ADDR_NUM; i++) {
            paddr = err->reg_array[2 * i + HBM_ADDH];
            paddr <<= TYPE_UINT32_WIDTH;
            paddr += err->reg_array[2 * i + HBM_ADDL];
            ret = write_file("/sys/kernel/page_eject", "offline_page", paddr);
            if (ret < 0) {
                all_success = false;
                log(LOG_WARNING, "HBM: SPPR offline failed, address is 0x%llx \n", paddr);
                continue;
            }
        }
        if (!all_success) {
            notice_BMC(err, ISOLATE_FAILED_OTHER_REASON);
            ret = -1;
        }
    }
    return ret < 0 ? ret : 0;
}

static uint8_t hbmc_hbm_after_repair(bool is_acls, const int repair_ret, const unsigned long long paddr)
{
    int ret;
    if (repair_ret < 0) {
        log(LOG_WARNING, "HBM %s: Keep page (0x%llx) offline\n", is_acls ? "ACLS" : "SPPR", paddr);
        /* not much we can do about errors here */
        (void)write_file("/sys/kernel/page_eject", "remove_page", paddr);
        return get_repair_failed_result_code(repair_ret);
    }

    ret = write_file("/sys/kernel/page_eject", "online_page", paddr);
    if (ret < 0) {
        log(LOG_WARNING, "HBM %s: Page (0x%llx) online failed\n",is_acls ? "ACLS" : "SPPR", paddr);
        return ONLINE_PAGE_FAILED;
    } else {
        log(LOG_INFO, "HBM %s: Page (0x%llx) repair and online success\n",is_acls ? "ACLS" : "SPPR", paddr);
        return ISOLATE_REPAIR_ONLINE_SUCCESS;
    }
}

static int hbmc_hbm_repair(const struct hisi_common_error_section *err, char *path)
{
    unsigned long long paddr;
    int ret;
    uint8_t repair_result_code;
    bool is_acls;

    /* Both ACLS and SPPR only repair the first address */
    paddr = err->reg_array[HBM_ADDH];
    paddr <<= TYPE_UINT32_WIDTH;
    paddr += err->reg_array[HBM_ADDL];

    is_acls = err->reg_array[HBM_REPAIR_REQ_TYPE] & HBM_CE_ACLS ||
        err->reg_array[HBM_REPAIR_REQ_TYPE] & HBM_PSUE_ACLS;

    ret = write_file(path, is_acls ? "acls_query" : "sppr_query", paddr);

    if (ret < 0) {
        if (ret != -ENXIO) {
            notice_BMC(err, get_repair_failed_result_code(ret));
            log(LOG_WARNING, "HBM: Address 0x%llx is not supported to %s repair\n", paddr, is_acls ? "ACLS" : "SPPR");
        }
        return ret;
    }

    ret = write_file(path, is_acls ? "acls_repair" : "sppr_repair", paddr);

    if (is_acls) {
        /* ACLS */
        repair_result_code = hbmc_hbm_after_repair(is_acls, ret, paddr);
        notice_BMC(err, repair_result_code);
        return ret;
    } else {
        /* SPPR */
        bool all_online_success = true;
        uint32_t i;
        for (i = 0; i < HBM_SPPR_ADDR_NUM; i++) {
            paddr = err->reg_array[2 * i + HBM_ADDH];
            paddr <<= TYPE_UINT32_WIDTH;
            paddr += err->reg_array[2 * i + HBM_ADDL];

            repair_result_code = hbmc_hbm_after_repair(is_acls, ret, paddr);
            if (repair_result_code != ISOLATE_REPAIR_ONLINE_SUCCESS) {
                all_online_success = false;
            }
        }
        if (ret < 0) {
            notice_BMC(err, get_repair_failed_result_code(ret));
            return ret;
        } else if (all_online_success) {
            notice_BMC(err, ISOLATE_REPAIR_ONLINE_SUCCESS);
            return 0;
        } else {
            notice_BMC(err, ONLINE_PAGE_FAILED);
            return ret;
        }
    }
    /* The final return code is not necessary */
    return ret < 0 ? ret : 0;
}

static int hbmc_get_memory_type(char *path)
{
    int type = HBM_UNKNOWN;
    char fname[MAX_PATH];
    char buf[128];
    FILE *file;

    size_t suffix_len = sizeof("/memory_type") - 1;
    int limit = MAX_PATH - suffix_len - 1;
    snprintf(fname, MAX_PATH, "%.*s/%s", limit, path, "memory_type");

    file = fopen(fname, "r");
    if (!file) {
        log(LOG_WARNING, "HBM: Cannot to open '%s': %s\n",
                    fname, strerror(errno));
        return -errno;
    }

    if (!fgets(buf, sizeof(buf), file)) {
        log(LOG_WARNING, "HBM: Failed to read %s\n", fname);
        goto err;
    }

    /* Remove the last '\n' */
    buf[strlen(buf) - 1] = 0;

    if (strcmp(buf, "HBM") == 0)
        type = HBM_HBM_MEMORY;
    else if (strcmp(buf, "DDR") == 0)
        type = HBM_DDR_MEMORY;

err:
    fclose(file);
    return type;
}

static void hbm_repair_handler(const struct hisi_common_error_section *err)
{
    log(LOG_DEBUG, "Received ACLS/SPPR flat mode repair request, try to repair\n");
    char *sys_dev_path = "/sys/devices/platform";
    char path[MAX_PATH];
    struct dirent *dent;
    DIR *dir;
    int ret;
    bool find_device = false, find_hbm_mem = false, addr_in_hbm_device = false;

    ret = hbmc_hbm_page_isolate(err);
    if (ret < 0) {
        return;
    }

    dir = opendir(sys_dev_path);
    if (!dir) {
        log(LOG_WARNING, "Can't read '%s': %s\n",
                    sys_dev_path, strerror(errno));
        notice_BMC(err, REPAIR_FAILED_OTHER_REASON);
        return;
    }

    while ((dent = readdir(dir))) {
        if (!strstr(dent->d_name, HBM_MEM_RAS_NAME))
            continue;
        find_device = true;

        snprintf(path, MAX_PATH, "%s/%s", sys_dev_path, dent->d_name);

        if (hbmc_get_memory_type(path) == HBM_HBM_MEMORY) {
            find_hbm_mem = true;
            ret = hbmc_hbm_repair(err, path);
            if (ret != -ENXIO) {
                addr_in_hbm_device = true;
                break;
            }
        }
    }

    if (!find_device) {
        log(LOG_ERROR, "Repair driver is not loaded, skip error, error_type is %u\n",
                err->reg_array[HBM_REPAIR_REQ_TYPE] & HBM_ERROR_MASK);
        notice_BMC(err, REPAIR_FAILED_OTHER_REASON);
    } else if (!find_hbm_mem) {
        log(LOG_ERROR, "No HBM device memory type found, skip error, error_type is %u\n",
                err->reg_array[HBM_REPAIR_REQ_TYPE] & HBM_ERROR_MASK);
        notice_BMC(err, REPAIR_FAILED_OTHER_REASON);
    } else if (!addr_in_hbm_device) {
        log(LOG_ERROR, "Err addr is not in device, skip error, error_type is %u\n",
                err->reg_array[HBM_REPAIR_REQ_TYPE] & HBM_ERROR_MASK);
        notice_BMC(err, REPAIR_FAILED_INVALID_PARAM);
    }

    closedir(dir);
}

static bool hbm_repair_validate(const struct hisi_common_error_section *err)
{
    if (!((err->val_bits & BIT(COMMON_VALID_MODULE_ID)) &&
          (err->val_bits & BIT(COMMON_VALID_SUBMODULE_ID)) &&
          (err->val_bits & BIT(COMMON_VALID_REG_ARRAY_SIZE))
        )) {
        log(LOG_DEBUG, "Err val_bits validate failed, val_bits is %u\n", err->val_bits);
        return false;
    }
    log(LOG_DEBUG, "err->module_id: %u\n", err->module_id);
    log(LOG_DEBUG, "err->submodule_id: %u\n", err->submodule_id);
    log(LOG_DEBUG, "err->val_bits: 0x%x\n", err->val_bits);
    log(LOG_DEBUG, "err->reg_array_size: %u\n", err->reg_array_size);

    if (err->module_id != HBMC_MODULE_ID ||
        err->submodule_id != HBMC_SUBMOD_HBM_REPAIR) {
        log(LOG_DEBUG, "err module_id or sub_module id doesn't not match\n");
        return false;
    }

    uint32_t hbm_repair_reg_type = err->reg_array[HBM_REPAIR_REQ_TYPE] & HBM_ERROR_MASK;
    bool is_acls_valid = (hbm_repair_reg_type & (HBM_CE_ACLS | HBM_PSUE_ACLS)) &&
        (err->reg_array_size == HBM_ACLS_ARRAY_SIZE);
    bool is_sppr_valid = (hbm_repair_reg_type & (HBM_CE_SPPR | HBM_PSUE_SPPR)) &&
        (err->reg_array_size == HBM_SPPR_ARRAY_SIZE);
    bool is_cache_mode = (hbm_repair_reg_type & HBM_CACHE_MODE) && 
        (err->reg_array_size == HBM_CACHE_ARRAY_SIZE);

    if (!(is_acls_valid || is_sppr_valid || is_cache_mode)) {
        log(LOG_WARNING, "err type (%u) is unknown or address array length (%u) is invalid\n",
                    hbm_repair_reg_type, err->reg_array_size);
        return false;
    }

    log(LOG_INFO, "Received ACLS/SPPR repair request\n");
    return true;
}

static bool hbm_flat_mode_validate(const struct hisi_common_error_section *err)
{
    uint32_t hbm_repair_reg_type = err->reg_array[HBM_REPAIR_REQ_TYPE] & HBM_ERROR_MASK;
    return !(hbm_repair_reg_type & HBM_CACHE_MODE);
}

int decode_hisi_common_section(struct ras_non_standard_event *event)
{
    const struct hisi_common_error_section *err = (struct hisi_common_error_section *)event->error;

    if (hbm_repair_validate(err)) {
        write_fault_info_to_flash(err);
        if (hbm_flat_mode_validate(err)) {
            hbm_repair_handler(err);
        }
    }

    return 0;
}
