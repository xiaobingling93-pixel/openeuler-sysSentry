# 平均阈值慢盘检测插件

用户可通过平均阈值慢盘检测插件进行慢盘故障检测，当巡检插件检测到系统存在慢盘时，会将结果上报给xalarmd服务，用户可通过注册告警或get_alarm命令的方式查看告警结果（注册告警和get_alarm命令可参考《[安装和使用](./installation_and_usage.md)》。

## 使用限制

1. 平均阈值慢盘检测插件可检出以下四种情况的慢盘：
   - 压力大导致的慢盘，上报告警日志中含有关键字"IO press"；
   - 盘故障导致的慢盘，上报告警日志中含有关键字"driver slow"；
   - IO栈异常导致的慢盘，上报告警日志中含有关键字"kernel slow"；
   - 未知故障导致的慢盘，上报告警日志中含有关键字"unknown".
2. 平均阈值慢盘检测插件运行时占用系统性能（cpu利用率、内存使用率、io吞吐等）不超过整个运行环境的5%。
3. 平均阈值慢盘检测插件的检出率为80%+，准确率为80%+。
4. 仅支持openEuler-20.03-LTS-SP4版本，并使用4.19.90内核。
5. 仅支持对nvme-ssd、sata-ssd、sata-hdd盘进行慢盘检测，区分盘的方法请参考[常见问题与解决方法 - Q2](./question_and_answer.md#问题2：如何区分系统上的盘是什么类型？)。
6. 启动平均阈值巡检前，请确认sysSentry、xalarmd、sentryCollector服务均处于运行状态。

## 安装插件

### 前置条件

已安装sysSentry巡检插件，sentryCollector采集服务已配置io相关采集项（请参考《[安装和使用](./installation_and_usage.md)》进行配置）。

### 安装软件包

```shell
[root@openEuler ~]# yum install -y avg_block_io pysentry_notify pysentry_collect
```

### 将avg_block_io加入框架管理

```shell
[root@openEuler ~]# sentryctl reload avg_block_io
```

## 配置文件说明

avg_block_io插件配置文件路径为/etc/sysSentry/plugins/avg_block_io.ini，对该文件修改会在下一次启动巡检任务时生效。

| 配置段               | 配置项           | 配置项说明                                                   | 默认值     | 必选项 |
| -------------------- | ---------------- | ------------------------------------------------------------ | ---------- | ------ |
| [log]                | level            | 记录日志的等级，可配置范围是debug/info/warning/error/critical，未配置或值异常时使用默认参数 | info       | Y      |
| [common]             | disk             | 磁盘名称，由逗号分隔，default表示当前环境上所有盘，配置异常时仅保留正确字段 | default    | Y      |
| [common]             | stage            | 监控阶段，由逗号分隔，目前已支持throtl/wbt/gettag/plug/deadline/hctx/requeue/rq_driver/bio九个阶段，根据盘种类不同提供的stage可能有不同，配置default表示盘支持的所有阶段，未配置时使用默认配置，配置异常时报错退出；注：用户自行配置时，必须包含bio阶段 | default    | Y      |
| [common]             | iotype           | io类别，由逗号分隔，共支持两种场景：read、write，未配置时使用默认配置，配置异常时报错退出 | read,write | Y      |
| [common]             | period_time      | 插件的巡检周期，整形类型，单位为秒，数值应为sentryCollector采集周期的整数倍，且倍数不超过sentryCollector的max_save（请参考sentryCollector配置文件） | 1          | Y      |
| [algorithm]          | win_size         | 平均阈值算法窗口长度，整形类型，该字段值越大，算法统计结果越稳定。范围为win_threshold~300，未配置时使用默认配置，配置异常时报错退出 | 30         | Y      |
| [algorithm]          | win_threshold    | 平均阈值算法超阈值数量，整形类型，该字段值越小，算法上报异常速度越快，误报越高。范围为1~win_size，未配置时使用默认配置，配置异常时报错退出 | 6          | Y      |
| [latency_\<DISK_TYPE>]  | read_avg_lim     | 读时延平均值上限，单位us，代表窗口中读IO平均时延限制，数值越大，算法漏报率越高，未配置时使用默认配置，配置异常时报错退出 | -          | Y      |
| [latency_\<DISK_TYPE>]  | write_avg_lim    | 写时延平均值上限，单位us，代表窗口中写IO平均时延限制，数值越大，算法漏报率越高，未配置时使用默认配置，配置异常时报错退出 | -          | Y      |
| [latency_\<DISK_TYPE>]  | read_avg_time    | 读时延倍数，整形类型，代表读时延数据超过read_avg_lim数据多少倍时，记为异常数据，数值越大，算法漏报率越高，未配置时使用默认配置，配置异常时报错退出 | -          | Y      |
| [latency_\<DISK_TYPE>]  | write_avg_time   | 写时延倍数，整形类型，代表写时延数据超过write_avg_lim数据多少倍时，记为异常数据，数值越大，算法漏报率越高，未配置时使用默认配置，配置异常时报错退出 | -          | Y      |
| [latency_\<DISK_TYPE>]  | read_tot_lim     | 读时延绝对上限，单位us，读时延超过此数据即为异常数据，数值越大，算法漏报率越高，未配置时使用默认配置，配置异常时报错退出 | -          | Y      |
| [latency_\<DISK_TYPE>]  | write_tot_lim    | 写时延绝对上限，单位us，写时延超过此数据即为异常数据，数值越大，算法漏报率越高，未配置时使用默认配置，配置异常时报错退出 | -          | Y      |
| [iodump]             | read_iodump_lim  | 读iodump绝对上限，整形类型，读iodump数量超过此数据即为异常数据，数值越大，算法漏报率越高，未配置时使用默认配置，配置异常时报错退出 | 0          | Y      |
| [iodump]             | write_iodump_lim | 写iodump绝对上限，整形类型，写iodump数量超过此数据即为异常数据，数值越大，算法漏报率越高，未配置时使用默认配置，配置异常时报错退出 | 0          | Y      |
| [\<stage>_\<DISK_TYPE>] | read_avg_lim     | 指定stage阶段的读时延平均值上限，单位us，代表窗口中读IO平均时延限制，数值越大，算法漏报率越高，未配置时使用默认配置，配置异常时报错退出 | -          | N      |
| [\<stage>_\<DISK_TYPE>] | read_tot_lim     | 指定stage阶段的读时延绝对上限，单位us，读时延超过此数据即为异常数据，数值越大，算法漏报率越高，未配置时使用默认配置，配置异常时报错退出 | -          | N      |

>![](figures/icon-note.gif)**说明：** 
>1. latency_\<DISK_TYPE>、iodump、\<stage>_\<DISK_TYPE>配置段的所有参数调整均会影响算法的准确性，且优劣并存：若数值越大，算法漏报率越高，则数值越小，算法误报率越高。需要根据经验进行取舍。
>2. \<DISK_TYPE>为磁盘类型，目前仅支持三类：sata_ssd、nvme_ssd、sata_hdd。
>3. \<stage>\_\<DISK_TYPE>中的stage可以为common.stage参数支持的任意阶段，该部分为可选配置，如果配置后，在进行到对应阶段的故障检测时将使用该部分的参数，而不是latency_\<DISK_TYPE>或iodump中的参数。

## 使用平均阈值慢盘检测插件

1. 启动巡检

   ```shell
   [root@openEuler ~]# sentryctl start avg_block_io
   ```

2. 查看巡检插件状态

   ```shell
   [root@openEuler ~]# sentryctl status avg_block_io
   ```

   状态为RUNNING即为运行中，状态为EXITED为退出

3. 查看告警信息

   ```shell
   [root@openEuler ~]# sentryctl get_alarm avg_block_io -s 1 -d
   ```

   示例：
   ```shell
    [
        {
            "alarm_id": 1002,
            "alarm_type": "ALARM_TYPE_OCCUR",
            "alarm_level": "MINOR_ALM",
            "timestamp": "2024-10-23 11:56:51",
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
    ]
    ```
   输出结果中各字段介绍： 

   | 字段 | 描述 |
   | --- | --- |
   | alarm_id | 用户上报告警的id，平均阈值慢盘检测插件的告警id固定为1002 |
   | alarm_type | 告警的类型，平均阈值慢盘检测插件的告警类型为ALARM_TYPE_OCCUR，代表告警产生 |
   | alarm_level | 告警的等级，平均阈值慢盘检测插件的告警等级为MINOR_ALM，代表系统存在异常，并且已经尝试自动隔离等方式修复 |
   | timestamp | 告警上报的时间 |
   | alarm_info | 告警内容详细信息，由平均阈值慢盘检测插件的自定义内容，不同的巡检插件上报的内容不一致 |

   alarm_info中各字段解释如下：
   | alarm_info中字段 | 描述 |
   | --- | --- |
   | alarm_source | 告警插件名称，平均阈值慢盘检测插件的固定值为avg_block_io |
   | driver_name | 告警磁盘名称，如sda |
   | io_type | 告警io类型，可能存在两种告警：<br>1. read：读io慢盘故障告警<br>2. write：写io慢盘故障告警 |
   | reason | 告警原因，平均阈值慢盘检测插件可能存在以下四种不同告警原因：<br>1. IO press，压力大导致的慢盘告警；<br>2. driver slow，盘故障导致的慢盘告警；<br>3. kernel slow，IO栈异常导致的慢盘告警；<br>4. unknown，未知故障导致的慢盘告警； |
   | block_stack | 慢io出现异常的阶段，可能出现的阶段为bio/throtl/wbt/bfq/rq_driver/gettag/plug/deadline/hctx/requeue共九个阶段的组合，九个阶段的详细介绍可参考[《二次开发指南》 - 插件事件告警上报](./developer_guide.md#插件事件告警上报) |
   | details | 告警日志内记录的信息，仅在get_alarm执行包含"-d/--detailed"选项时展示，内容为上报异常磁盘的latency（io时延数据）和iodump（io超时未完成数量）的信息 |

4. 停止巡检

   ```shell
   sentryctl stop avg_block_io
   ```

5. 查看巡检结果信息
   在巡检运行结束后可通过以下命令查看巡检结果：

   ```shell
   sentryctl get_result avg_block_io
   ```

   回显信息格式为json格式，内容格式如下：

   ```ini
   {
       "result": "PASS",
       "start_time": "YYYY-mm-DD HH:MM:SS",
       "end_time": "YYYY-mm-DD HH:MM:SS",
       "error_msg" : "",
       "details":{}  # 平均阈值算法中detail信息为空
   }
   ```
   其中"result"和"error_msg"对应关系如下：

   | result | 对应error_msg信息 | 含义 |
   | ------ | --------------- | -------- |
   | PASS         | ""                                                           | 巡检任务正常运行结束，无异常 |
   | SKIP         | "not supported.maybe some rpm package not be installed."     | 因缺少依赖、环境不支持等原因跳过/未执行巡检任务 |
   | FAIL         | "FAILED. config may be incorrect or the command may be invalid/killed!" | 因执行命令错误等原因，巡检任务执行失败 |
   | MINOR_ALM    | "the command output shows that the status is 'INFO' or 'GENERAL_WARN'." | 巡检任务结束，存在系统存在异常，并且已经尝试自动隔离等方式完成修复 |
   | MAJOR_ALM    | "the command output shows that the status is 'WARN' or 'IMPORTANT_WARN'." | 巡检任务结束，系统存在异常，需要通过重启等方式修复 |
   | CRITICAL_ALM | "the command output shows that the status is 'FAIL' or 'EMERGENCY_WARN'." | 巡检任务结束，致命告警，系统或硬件存在无法修复问题，建议更换 |
