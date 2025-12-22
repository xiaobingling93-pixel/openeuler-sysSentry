# 二次开发指南

sysSentry作为一款巡检任务管理框架，除了管理已提供的插件外，也支持对用户开发的插件进行管理，想要开发一款新的插件并通过sysSentry框架进行管理，需要实现以下能力：
1. 编写插件管理配置文件
2. 完成插件功能开发

本文档将详细介绍如何使用sysSentry提供的对外接口开发新的插件。

## 插件管理配置文件

用户编写的新插件可以通过sysSentry进行管理，为了达到此目的，需要用户为新插件增加对应的配置文件，该文件应放置在`/etc/sysSentry/tasks/`目录下，文件名为`[插件名].mod`，假设插件名为test，配置文件参考：

```shell
[root@openEuler ~]# cat /etc/sysSentry/tasks/test.mod
[common]
enabled=yes							# 必选，是否加载插件
task_start=/usr/bin/test			# 必选，插件启动命令
task_stop=pkill -f /usr/bin/test	# 必选，插件停止命令
type=oneshot						# 必选，插件任务类型
alarm_id=1100						# 可选，新增alarm_id信息
alarm_clear_time=5					# 可选，新增告警清理时间
```


## 插件功能开发

### 插件使用限制

用户开发的新插件需满足如下要求：
1. 插件开发语言无限制，但建议用户优选python或c语言开发，目前sysSentry仅提供python和c语言的二次开发接口；
2. 所有插件必须为可执行文件；
3. 所有插件必须包含停止命令，执行该命令可准确的停止插件任务而不影响系统上其他程序的运行；

### 获取采集数据（可选）

如果用户希望通过sentryCollector采集服务获取系统数据，请参考[对接sentryCollector采集服务](#对接sentrycollector采集服务)章节。

### 插件事件告警上报

用户可通过告警上报接口将插件的告警信息上报到xalarmd服务，并通过get_alarm接口查看告警内容：

```shell
[root@openEuler ~]# sentryctl get_alarm <插件名>
```

sysSentry提供python与c两种语言的对外接口。

#### 告警上报使用限制
1. 告警上报仅支持告警id的范围为1001-1128共128种，其中1001固定为内存巡检占用，1002为慢IO告警占用。
2. 告警上报最大支持8191个字符。

#### python实现插件告警上报

需要安装pysentry_notify软件包：

```shell
[root@openEuler ~]# yum install -y pysentry_notify
```

**接口** 告警信息上报

| 接口   | xalarm_report(alarm_id, alarm_level, alarm_type, puc_paras)  |
| ------ | ------------------------------------------------------------ |
| 描述   | 巡检插件可以通过该接口上报告警信息到xalarmd服务              |
| 参数   | alarm_id -- 告警id，整数类型<br>alarm_level -- 告警级别，枚举类型，取值为：MINOR_ALM（一般告警）、MAJOR_ALM（严重告警）和CRITICAL_ALM（致命告警）<br/>alarm_type -- 告警类别，枚举类型，取值为：ALARM_TYPE_OCCUR（告警产生）和ALARM_TYPE_RECOVER（故障恢复）<br/>punc_params -- 告警描述信息，字符串类型 |
| 限制   | 1. 告警id限制取值范围为1001-1128。目前1001（内存巡检）、1002（慢IO检测）已被占用，不建议使用<br/>2. 告警描述信息，最大长度为8191，在慢IO巡检中以json格式通信，具体json中各字段可以参考下面：慢IO上报json格式说明。 |
| 返回值 | 若上报告警成功，则返回值为Ture，否则返回值为False。          |

慢IO上报json格式说明：

| 参数名称 | 类型         | 取值说明                                                 |
| ------------ | ---------------- | ------------------------------------------------------------ |
| device_name  | 字符串           | 发生慢IO事件的故障盘设备名，例如"/dev/sda"                   |
| reason       | 字符串           | 慢IO事件的故障原因，取值如下范围 disk_slow：可能由于盘侧响应码导致的慢IO；kernel_stack：可能由于内核栈导致的慢IO；high_press：可能由于业务压力大导致的慢IO |
| block_stack  | 字符串列表       | 存在异常的IO调用栈列表，例如["bio","rq_driver"]，取值范围如下：bio、 throtl、 wbt、 gettag、plug、deadline、 hctx、requeue、rq_driver |
| io_type      | 字符串           | 出现慢IO的io类型，取值范围如下：read：读io出现慢io场景；write：写io出现慢io场景 |
| alarm_source | 字符串           | 告警来源插件，取值范围如下：avg_block_io：平均阈值检测插件告警；ai_block_io：ai阈值检测插件告警 |
| alarm_type   | 字符串           | 出现慢IO告警的类型，取值范围如下：latency：时延数据超过阈值产生慢io告警；iodump：超时未完成的IO数量超过阈值产生慢IO告警 |
| details      | JSON格式数据列表 | 详细的IO时延数据清单 |

示例：

```python
from xalarm.sentry_notify import (
    xalarm_report,
    MAJOR_ALM,
    ALARM_TYPE_OCCUR
)

ALARM_ID = 1002
ALARM_MSG = """
{
"alarm_info": {
            "alarm_source": "avg_block_io",
            "driver_name": "sda",
            "io_type": "write",
            "reason": "IO press",
            "block_stack": "bio,wbt",
            "alarm_type": "latency",
            "details": {
                "latency": "gettag: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0], rq_driver: [0,0,0,0,0,437.9,0,0,0,0,517,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0], bio: [0,0,0,0,0,521.1,0,0,0,0,557.8,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0], wbt: [0,0,0,0,0,0,8.5,0,0,0,0,12.0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]",
                "iodump": "gettag: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0], rq_driver: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0], bio: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0], wbt: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]"
            }
}
}
"""

if __name__ == "__main__":
    ret = xalarm_report(ALARM_ID, MAJOR_ALM, ALARM_TYPE_OCCUR, ALARM_MSG)
    if ret == -1:
        print("send failed.")
```

#### c语言实现插件告警上报

需要安装libxalarm软件包：

```shell
[root@openEuler ~]# yum install -y libxalarm
```

开发环境还需要安装libxalarm-devel包（构建依赖，非运行依赖）：

```shell
[root@openEuler ~]# yum install -y libxalam-devel
```

**接口** 告警信息上报

| 接口   | int xalarm_Report(unsigned short usAlarmId, unsigned char ucAlarmLevel, unsigned char ucAlarmType, char *pucParas); |
| ------ | ------------------------------------------------------------ |
| 描述   | sysSentry告警上报接口，用于向xalarmd上报需要转发的告警     |
| 参数   | usAlarmId -- 告警id<br/>usAlarmLevel -- 告警级别，枚举类型，取值为：MINOR_ALM（一般告警）、MAJOR_ALM（严重告警）或CRITICAL_ALM（致命告警）<br/>ucAlarmType -- 告警类别，取值范围为ALARM_TYPE_OCCUR（告警产生）或ALARM_TYPE_RECOVER（故障恢复）<br/>pucParas -- 告警描述信息，长度上限为8191个字符 |
| 限制   | 1. 告警id限制取值范围为1001-1128。目前1001（内存巡检）、1002（慢IO检测）已被占用，不建议使用<br/>2. 告警描述信息最大长度为8191 |
| 返回值 | 返回0表示成功，失败返回-1 |

示例：

```shell
[root@openEuler ~]# cat send_alarm.c
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <xalarm/register_xalarm.h>

#define ALARMID 1002

int main(int argc, char **argv)
{
    int alarmId = ALARMID;
    int level = MAJOR_ALM;
    int type = ALARM_TYPE_OCCUR;
    unsigned char *msg = "{\""
                            "alarm_info\": {"
                                "\"alarm_source\": \"avg_block_io\","
                                "\"driver_name\": \"sda\","
                                "\"io_type\": \"write\","
                                "\"reason\": \"IO press\","
                                "\"block_stack\": \"bio,wbt\","
                                "\"alarm_type\": \"latency\","
                                "\"details\": {"
                                    "\"latency\": \"gettag: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0], rq_driver: [0,0,0,0,0,437.9,0,0,0,0,517,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0], bio: [0,0,0,0,0,521.1,0,0,0,0,557.8,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0], wbt: [0,0,0,0,0,0,8.5,0,0,0,0,12.0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]\","
                                    "\"iodump\": \"gettag: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0], rq_driver: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0], bio: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0], wbt: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]\""
                                    "}"
                                "}"
                            "}\0";

    int ret = xalarm_Report(alarmId, level, type, msg);
    
    if (ret == -1) {
        printf("send failed.\n");
    }

    return 0;
}
[root@openEuler ~]# gcc send_alarm.c -o send_alarm -lxalarm
```

### 日志记录

sysSentry框架运行过程中产生的日志保存在在`/var/log/sysSentry/sysSentry.log`中，可通过查看该日志获取框架运行详情。

#### 插件日志记录位置和格式

开发巡检插件时，推荐插件运行过程中产生的日志保存在`/var/log/sysSentry/`目录下，文件名命名为`[插件名].log`；日志文件名称推荐和插件名称一致。

日志记录相关信息时，推荐日志格式为：`<时间戳> - <日志级别> - [<文件名:行号>] - <日志消息>`
其中时间戳格式为：YYYY-MM-DD HH:MM:SS,FF , 时间戳示例为：`2006-01-02 15:04:05.99`

日志级别可选项为：debug/info/warning/error/critical。
选项的含义如下：
- debug：最低级别，用于记录详细的技术信息，帮助开发调试。
- info：记录程序的正常运行信息，如启动和关闭状态。
- warning：记录可能引起问题的情况，但不影响程序运行。
- error：记录严重问题，导致功能失败或程序中断。
- critical：最高级别，记录非常严重的问题，可能导致程序完全停止运行。

推荐程序正常运行时，日志级别设为info。

#### 插件日志轮转配置
sysSentry框架及插件的日志会基于logrotate机制进行自动轮转。日志轮转是一种系统管理技术，用于管理日志文件的大小和数量，以防止日志文件占用过多的磁盘空间。

系统每次触发logrotate时会对sysSentry框架及插件的日志文件大小进行判断，如果日志文件超过4096k，则进行logrotate，一个插件/服务的日志最多轮转两次，轮转日志会被压缩。

##### 插件日志轮转配置示例
日志轮转配置可参考`/etc/logrotate.d/sysSentry`文件进行配置。
当前`/etc/logrotate.d/sysSentry`的配置内容如下：
```shell
/var/log/sysSentry/*.log{
    compress
    missingok
    notifempty
    copytruncate
    rotate 2
    size +4096k
    hourly
}
```
其中各项配置项含义为：
- `/var/log/sysSentry/*.log`表明对哪些日志文件进行转储，*为通配符，表示所有`/var/log/sysSentry/`目录下以.log结尾的日志文件。
- compress表明默认将日志文件进行压缩，节省内存空间。也可配置为nocompress，表明不压缩日志文件。推荐此项默认配置为compress。
- missingok表明如果日志缺失，logrotate不会报错，也不会停止处理其他日志文件。推荐此配置项默认配置。
- notifempty表明如果日志文件为空，则不进行转储。推荐此配置项默认配置。
- copytruncate表明在日志转储时，先将当前的日志文件复制一份，然后将日志文件清空，再将复制的文件进行压缩。这通常用于正在被系统进程使用的日志文件，确保进程可以继续写入新的日志。推荐此配置项默认配置。
- rotate 2表明在轮转操作后保留2个旧的日志文件。一旦旧的文件数量超过2个，logrotate会自动删除旧的日志文件为新的日志文件腾出空间。可根据需求自行定义所需日志数量大小。
- size +4096k表明当日志文件大小超过4096k时，将自动触发日志转储操作。可根据需求自行定义所需日志文件大小。
- hourly表明日志轮转的频率是每小时。可配置项有hourly/daily/weekly/monthly等。示例中表明logrotate每小时轮转日志文件。推荐此项默认配置为hourly。

##### 更改插件日志轮转配置
对新增插件：
1. 可更改`/etc/logrotate.d/sysSentry`已有的配置项内容（注：此举会更改所有`/var/log/sysSentry/`目录下以.log结尾的日志文件配置）.
2. 若想对`/var/log/sysSentry/`目录下不同的日志文件设置不同配置，可在`/etc/logrotate.d/sysSentry`对每一个日志文件进行单独配置，如下所示：
    ```shell
    /var/log/sysSentry/`[日志名一]`.log{
        # 所需配置项等
    }
    /var/log/sysSentry/`[日志名二]`.log{
        # 所需配置项等
    }
    ```
请不要对同一日志，设置不同配置。如下例所示：
```shell
# A BAD EXAMPLE
/var/log/sysSentry/*.log{
    compress
}
/var/log/sysSentry/example.log{
    nocompress
}
```
在该示例中，*为通配符，表示所有`/var/log/sysSentry/`目录下以.log结尾的日志文件，已经包含了example.log，设置为轮转日志需要压缩；但配置文件中又单独设置example.log不需要压缩。该做法可能会造成预期之外的行为。

如果手动修改了/etc/logrotate.d/sysSentry文件，可通过logrotate -f /etc/logrotate.d/sysSentry手动触发日志轮转。
logrotate的其他使用方法请参考<https://linux.die.net/man/8/logrotate>
### 结果上报

用户可通过sysSentry提供的接口将插件巡检结果上报给sysSentry服务，并通过get_result命令查看结果：

```shell
[root@openEuler ~]# sentryctl get_result <插件名>
```

提供python与c两种语言的对外接口。

#### 结果上报使用限制

1. 结果上报接口应在巡检插件运行结束前被调用。
2. 巡检插件的一个生命中期内仅应上报一次巡检结果。
3. 巡检插件运行成功或失败均应该上报巡检结果。

#### python巡检结果上报接口

**结构体** ResultLevel

```python
class ResultLevel(Enum):
    """result level for report_result"""
    PASS = 0    # 巡检任务正常运行结束，无异常
    FAIL = 1    # 因缺少依赖、环境不支持等原因跳过/未执行巡检任务
    SKIP = 2    # 因执行命令错误等原因，巡检任务执行失败
    MINOR_ALM = 3   # 巡检任务结束，存在系统存在异常，并且已经尝试自动隔离等方式完成修复
    MAJOR_ALM = 4   # 巡检任务结束，系统存在异常，需要通过重启等方式修复
    CRITICAL_ALM = 5    # 巡检任务结束，致命告警，系统或硬件存在无法修复问题，建议更换
```

**接口** 结果上报

| 接口   | int report_result(task_name: str, result_level : ResultLevel, report_data : str) -> int |
| ------ | ------------------------------------------------------------ |
| 描述   | 用于模块工具向sysSentry上报巡检结果                          |
| 参数   | task_name -- 巡检任务名称<br>result_level -- 巡检结果异常等级，可选参数请参考ResultLevel结构体<br>report_data -- 巡检结果详细信息，应为json格式转换而成的字符串 |
| 返回值 | 正常：0，异常：非0 |

示例：

```python
[root@openEuler ~]# python3
Python 3.7.9 (default, Dec 11 2023, 19:40:40) 
[GCC 7.3.0] on linux
Type "help", "copyright", "credits" or "license" for more information.
>>> import json
>>> from syssentry.result import ResultLevel, report_result
>>> report_result("test", ResultLevel.PASS, json.dumps({}))
0
```

#### c巡检结果上报接口

需要安装libxlaram软件包：

```shell
[root@openEuler ~]# yum install -y libxlaram
```
开发环境还需要安装libxalarm-devel包（构建依赖，非运行依赖）：
```shell
[root@openEuler ~]# yum install -y libxalam-devel
```

**结构体** RESULT_LEVEL <a id="resultlevel_c"></a>


```c
enum RESULT_LEVEL {
    RESULT_LEVEL_PASS = 0,  // 巡检任务正常运行结束，无异常
    RESULT_LEVEL_FAIL = 1,  // 因缺少依赖、环境不支持等原因跳过/未执行巡检任务
    RESULT_LEVEL_SKIP = 2,  // 因执行命令错误等原因，巡检任务执行失败
    RESULT_LEVEL_MINOR_ALM = 3, // 巡检任务结束，存在系统存在异常，并且已经尝试自动隔离等方式完成修复
    RESULT_LEVEL_MAJOR_ALM = 4, // 巡检任务结束，系统存在异常，需要通过重启等方式修复
    RESULT_LEVEL_CRITICAL_ALM = 5,  // 巡检任务结束，致命告警，系统或硬件存在无法修复问题，建议更换
};
```

接口：结果上报

| 接口   | int report_result(const char *task_name, enum RESULT_LEVEL result_level, const char *report_data); |
| ------ | ------------------------------------------------------------ |
| 描述   | 用于模块工具向sysSentry上报巡检结果                          |
| 参数   | task_name：巡检任务名称<br>result_level：巡检结果异常等级，可选参数请参考ResultLevel结构体<br>report_data：巡检结果详细信息，应为json格式转换而成的字符串 |
| 返回值 | 正常：0，异常：非0 |

示例：

```shell
[root@openEuler ~]# cat report_res.c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <xalarm/register_xalarm.h>

int main(int argc, char *argv[]) {
    enum RESULT_LEVEL result_lv = 0;
    result_lv = RESULT_LEVEL_PASS;
    details = "{\"a\": 1, \"b\": 2}";
    int res = report_result(task_name, result_lv, details);
    if (res == -1) {
        printf("failed send result to sysSentry\n");
    }

    return 0;
}
[root@openEuler ~]# gcc report_res.c -o report_res -lxalarm
```

## 对接sentryCollector采集服务

sysSentry软件中包含用来做数据采集的服务：sentryCollector，用户可通过sentryCollector服务定期采集系统数据。

### 采集使用限制

1. 当前仅支持对系统io数据进行采集，并提供ebpf采集和内核无锁采集两种方案；
2. 仅支持对nvme ssd（nvme固态硬盘）、sata ssd（sata固态硬盘）、sata hdd（sata机械硬盘）三种磁盘的数据进行采集；
3. sentryCollector的io数据采集默认使用ebpf采集，如需使用内核无锁采集，请参考[常见问题解决方法 - Q1](./question_and_answer.md#问题1：如何使用内核无锁采集方案进行数据采集？)进行部署。

### io数据采集

sentryCollector支持按周期采集指定磁盘的数据，并提供两种采集方式：

- 内核无锁采集 -- 由内核进行数据采集，并将采集结果上报给用户态读取，需要重编内核实现。
- ebpf采集 -- 通过使用ebpf向内核打点的方式进行采集，无需重编内核。

#### 内核无锁采集和ebpf采集的差异

内存无锁采集和ebpf采集在以下几个方面存在区别：
1. 支持采集的阶段不同
将一个io从发生到结束分成多个不同的阶段，以下是两种采集方式支持的阶段类型：

| 阶段         | bio    | rq_driver | throtl   | wbt    | gettag | plug     | deadline | bpf      | requeue  | hctx     |
| ------------ | ------ | --------- | -------- | ------ | ------ | -------- | -------- | -------- | -------- | -------- |
| 内核无锁采集 | 支持 | 支持    | 支持   | 支持 | 支持 | 支持   | 支持   | 支持   | 支持   | 支持   |
| ebpf采集     | 支持 | 支持    | 不支持 | 支持 | 支持 | 不支持 | 不支持 | 不支持 | 不支持 | 不支持 |

2. 支持采集的IO类型不同

| IO类型  | 内核无锁采集 | ebpf采集 | 数据含义   |
| ------- | ------------ | -------- | ---------- |
| read    | 支持       | 支持   | 读IO       |
| write   | 支持       | 支持   | 写IO       |
| flush   | 支持       | 不支持 | flush IO   |
| discard | 支持       | 不支持 | discard IO |

除以上两个差异之外，内核无锁采集和ebpf采集方案可采的数据类型、支持系统等数据均相同：
1. 两种采集方案均支持4.19内核，x86_64和aarch64架构。
2. 两种采集方案均支持采集nvme ssd（nvme固态硬盘）、sata ssd（sata固态硬盘）和sata hdd（sata机械硬盘）三种盘的数据。
3. 两种采集方案均支持对latency、iodump、iolength、iops数据的采集：
    - latency -- 指定周期内的时延数据；
    - iodump -- 指定周期内超时未完成的io数量，如io运行超过1秒未完成即为超时；
    - iolength -- io队列长度
    - iops -- 每秒内完成的io数量

#### 对外接口

当前仅提供python语言的接口，需要用户安装pysentry_collect软件包：

```shell
[root@openEuler ~]# yum install -y pysentry_collect

```

**接口一** 查看磁盘类型

| 接口   | get_disk_type(disk)                                          |
| ------ | ------------------------------------------------------------ |
| 描述   | 从采集模块中查询磁盘类型                                     |
| 参数   | disk – 磁盘名，例：sda，必选参数                             |
| 限制   | 磁盘名不超过32个字符                                         |
| 返回值 | 返回值格式为：{"ret": value1, "message":value2}<br>value1取值为0或者其他正整数，0表示成功，其他非零表示失败;<br>message是个字符串，表示表示磁盘类型，字符串类型，如果ret为非零，则message为空字符串，当前支持的message对应磁盘类型如下：<br/>"message": "0"  -- nvme_ssd<br/>"message": "1"  -- sata_ssd<br/>"message": "2"  -- sata_hdd<br/>返回值示例：<br>\- 磁盘类型不支持：{"ret": 8, "message": ""} # ret结果非0<br/>- 函数执行成功：{"ret": 0, "message": "1"}  # 磁盘为sata ssd类型 |

示例：

```shell
[root@openEuler ~]# python3
Python 3.7.9 (default, Dec 11 2023, 19:40:40) 
[GCC 7.3.0] on linux
Type "help", "copyright", "credits" or "license" for more information.
>>> from sentryCollector.collect_plugin import get_disk_type, Disk_Type
>>> res = get_disk_type("sda")
>>> res
{'ret': 0, 'message': '1'}
>>> curr_disk_type = int(res['message'])
>>> curr_disk_type
1
>>> Disk_Type[curr_disk_type]
'sata_ssd'
```

**接口二** 查询采集是否合法

| 接口   | is_iocollect_valid(period, disk_list=None, stage=None)       |
| ------ | ------------------------------------------------------------ |
| 描述   | 确认是否在采集范围内，确认周期是否合法                       |
| 参数   | period – 用户采集周期，整形，单位秒，必选参数<br>disk_list – 磁盘列表，默认为None，代表关注所有磁盘，可选参数。可传入自定义列表，例：["sda", "sdb", "sdv"]<br/>stage – 采集阶段，默认为None，代表关注所有采集阶段，可选参数。可传入自定义阶段列表，例：["wbt", "bio"] |
| 限制   | 1. 采集周期取值在1到300之间<br/>2. 磁盘列表磁盘个数不超过10个，如果超过10个，默认取前10个，磁盘列表种的磁盘名不超过32个字符<br/>3. 采集阶段个数不超过15个，阶段名字符不超过20个字符 |
| 返回值 | 返回值格式为：{"ret": value1, "message":value2}<br/>value1取值为0或者其他正整数，0表示成功，其他非零表示失败<br/>message是个字符串，表示有效的磁盘和该磁盘对应的stage，字符串类型，如果字符串为空说明全都不支持，格式如下：<br/>{"disk_name1": ["stage1", "stage2"], "disk_name2": ["stage1", "stage2"], ...}  <br/>返回值示例：<br/>- 验证失败：{"ret": 1, "message": {}} # ret结果非0<br/>- 验证成功，所有盘均不支持采集：{"ret": 0, "message": {}}<br/>- 部分盘不支持（message中返回支持的盘和对应的阶段）：{"ret": 0, "message": {"sda": ["bio", "gettag"], "sdb": ["bio", "gettag"]}} |

示例：

```shell
[root@openEuler ~]# python3
Python 3.7.9 (default, Dec 11 2023, 19:40:40) 
[GCC 7.3.0] on linux
Type "help", "copyright", "credits" or "license" for more information.
>>> from sentryCollector.collect_plugin import is_iocollect_valid
>>> is_iocollect_valid(1, ["sda"])
{'ret': 0, 'message': '{"sda": ["throtl", "wbt", "gettag", "plug", "deadline", "hctx", "requeue", "rq_driver", "bio"]}'}
```

**接口三** 查询指定数据

| 接口   | get_io_data(period, disk_list, stage, iotype)                |
| ------ | ------------------------------------------------------------ |
| 功能   | 确认是否在采集范围内，确认周期是否合法                       |
| 参数   | period – 用户采集周期，整形，单位秒，必选参数<br>disk_list -- 磁盘列表，必选参数，例：["sda", "sdb", "sdv"]<br/>stage – 读取的阶段，必选参数，例：["bio", "gettag", "wbt"]。<br/>iotype – IO类型，列表中对应要获取的IO数据类型，仅支持read/write/flush/discard，必选参数，例：["read", "write"] |
| 限制   | 1. 采集周期取值在1到300之间，并且为period_time值的整数倍，且倍数不超过max_save（两个数值请参考/etc/sysSentry/sentryCollector.conf）<br/>2. 磁盘列表磁盘个数不超过10个，如果超过10个，默认取前10个，磁盘列表种的磁盘名不超过32个字符<br>3. 采集阶段个数不超过15个，阶段名字符不超过20个字符<br>4. IO类型个数不超过4个，字符长度不超过7个(最长的长度是discard) |
| 返回值 | 返回值格式为：{"ret": value1, "message":value2}<br/>value1取值为0或者其他正整数，0表示成功，其他非零表示失败<br/>message是个字符串，表示采集模块处理过的当前周期数据，字符串类型，格式如下:<br/>"{"disk_name1": {"stage1": {"read": [latency, iodump, iolength, iops],"write": [write_latency, write_iodump, iolength, iops]},"stage2": {…}},…}"  <br/>返回值示例：<br/>- 获取数据失败：{"ret": 1, "message": {}} # ret结果非0<br/>- 获取数据成功：{"ret": 0, "message": "{"sda": {"bio": {"read": [0.1, 0, 100, 19], "write": [0.5, 3, 100, 12]}, "wbt": {}}, "sdb"…}"}  <br/>   其中[0.5, 3, 100, 12]对应[时延ns，iodumps数量，io队列长度，iops] |

示例：

```shell
[root@openEuler ~]# python3
Python 3.7.9 (default, Dec 11 2023, 19:40:40) 
[GCC 7.3.0] on linux
Type "help", "copyright", "credits" or "license" for more information.
>>> from sentryCollector.collect_plugin import get_io_data
>>> get_io_data(1, ["sda"], ["bio"], ["read"])
{'ret': 0, 'message': '{"sda": {"bio": {"read": [0, 0, 0, 0]}}}'}
```