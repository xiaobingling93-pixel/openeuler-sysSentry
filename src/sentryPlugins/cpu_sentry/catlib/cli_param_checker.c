#include <sys/socket.h>
#include <sys/un.h>
#include <regex.h>
#include <stdbool.h>
#include <string.h>
#include <limits.h>
#include <unistd.h>
#include "cli_common.h"
#include "cat_structs.h"
#include "cli_param_checker.h"
#define CPU_USAGE_PERCENTAGE_MAX 100
#define CPULIST_REGEX "^([0-9]+(-[0-9]+)*,?)+$"

void checkset_cpu_usage_percentage(char *getopt_optarg, catcli_request_body *p_request_body, struct option_errs *errs)
{
    long cpu_utility = strtol(getopt_optarg, NULL, DECIMAL);
    if (cpu_utility <= 0 || cpu_utility > CPU_USAGE_PERCENTAGE_MAX || strchr(getopt_optarg, '.') != NULL) {
        strncpy(errs->patrol_module_err,
            "\"cpu_utility \" must be an integer greater in the range (0,100],correct \"-u, --cpu_utility\"\n", MAX_ERR_LEN);
    	p_request_body->cpu_utility = 0;
    } else {
    	p_request_body->cpu_utility = (int)cpu_utility;
    }
}

void checkset_cpulist(char *getopt_optarg, catcli_request_body *p_request_body, struct option_errs *errs)
{
    regex_t reg = { 0 };
    regcomp(&reg, CPULIST_REGEX, REG_EXTENDED); // 编译正则模式串
    const size_t nmatch = 1;                    // 定义匹配结果最大允许数
    regmatch_t pmatch[1];                       // 定义匹配结果在待匹配串中的下标范围
    char getopt_optarg_copy[strlen(getopt_optarg) + 1];
    strcpy(getopt_optarg_copy,getopt_optarg);
    int status = regexec(&reg, getopt_optarg_copy, nmatch, pmatch, 0);
    regfree(&reg); // 释放正则表达式
    if (status != 0) {
        strncpy(errs->cpulist_err,
            "\"cpulist\" is invalid format,the correct format should be like '0-3,7',correct \"-l, --cpulist\"\n",
            MAX_ERR_LEN);
    } else {
        long total_core = sysconf(_SC_NPROCESSORS_CONF);
        char *savePtr = NULL;
        savePtr = getopt_optarg_copy;
        while (true) {
            char *split = strtok_r(savePtr, ",", &savePtr);
            if (split == NULL) {
                break;
            }
            char *subSavePtr = NULL;
            char *subSplit = strtok_r(split, "-", &subSavePtr);
            long coreid_before = strtol(subSplit, NULL, DECIMAL);
            long coreid_after = -1;
            if (subSavePtr) {
                coreid_after = strcmp(subSavePtr, "") == 0 ? -1 : strtol(subSavePtr, NULL, DECIMAL);
            }
            if (coreid_before > total_core || coreid_after > total_core) {
                strncpy(errs->cpulist_err,
                    "The specified \"cpulist\" contain cpu core id which has exceeded the max cpu core id,correct "
                    "\"-l, --cpulist\"\n",
                    MAX_ERR_LEN);
                return;
            }
            if (coreid_after >= 0 && coreid_before > coreid_after) {
                strncpy(errs->cpulist_err,
                    "\"cpulist\" must not contain descending cpuid segment such as \"8-2\",correct \"-l, --cpulist\"\n",
                    MAX_ERR_LEN);
                return;
            }
        }
        p_request_body->module_params = getopt_optarg;
    }
}

void checkset_patrol_time(char *getopt_optarg, catcli_request_body *p_request_body, struct option_errs *errs)
{
    long second = strtol(getopt_optarg, NULL, DECIMAL);
    if (second <= 0 || second > INT_MAX || strchr(getopt_optarg, '.') != NULL) {
        strncpy(errs->patrol_time_err,
            "\"patrol_second\" must be a number in the range of (0,INT_MAX] ,correct \"-t, --patrol_second\"\n",
            MAX_ERR_LEN);
    } else {
    	p_request_body->patrol_second = (int)second;
    }
}

void checkset_patrol_type(char *getopt_optarg, catcli_request_body *p_request_body, struct option_errs *errs)
{
    if (strcmp(getopt_optarg, "0x0001") == 0 || strcasecmp(getopt_optarg, "CPU") == 0) {
        p_request_body->patrol_module = CAT_PATROL_CPU;
    } else if (strcmp(getopt_optarg, "0x0002") == 0 || strcasecmp(getopt_optarg, "MEM") == 0) {
        p_request_body->patrol_module = CAT_PATROL_MEM;
    } else if (strcmp(getopt_optarg, "0x0004") == 0 || strcasecmp(getopt_optarg, "HBM") == 0) {
        p_request_body->patrol_module = CAT_PATROL_HBM;
    } else if (strcmp(getopt_optarg, "0x0008") == 0 || strcasecmp(getopt_optarg, "NPU") == 0) {
        p_request_body->patrol_module = CAT_PATROL_NPU;
    } else {
        p_request_body->patrol_module = CAT_PATROL_UNKNOWN;
        strncpy(errs->patrol_module_err, "unknown patrol module,correct \"-m, --patrol_module\"\n", MAX_ERR_LEN);
    }
}


int checkParamsDependency(catcli_request_body *p_request_body, option_errs *p_option_errs)
{
    bool has_err = false;
    if (p_request_body->patrol_module == CAT_PATROL_UNKNOWN) {
        PRINT_RED("<ERROR>:%s", p_option_errs->patrol_module_err);
        has_err = true;
    }
    if (p_request_body->cpu_utility <= 0) {
        PRINT_RED("<ERROR>:%s", p_option_errs->cpu_usage_percentage_err);
        has_err = true;
    }
    if (p_request_body->patrol_second <= 0) {
        PRINT_RED("<ERROR>:%s", p_option_errs->patrol_time_err);
        has_err = true;
    }
    if (p_request_body->module_params == NULL && p_request_body->patrol_module == CAT_PATROL_CPU) {
        PRINT_RED("<ERROR>:%s", p_option_errs->cpulist_err);
        has_err = true;
    }
    if (has_err) {
        print_opts_help();
        return CAT_INVALID_PARAMETER;
    }
    return CAT_OK;
}

