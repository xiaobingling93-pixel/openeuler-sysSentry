# AI阈值慢盘检测插件

用户可通过AI阈值慢盘检测插件进行慢盘故障检测，当巡检插件检测到系统存在慢盘时，会将结果上报给xalarmd服务，用户可通过注册告警或get_alarm命令的方式查看告警结果（注册告警和get_alarm命令可参考《[安装和使用](./installation_and_usage.md)》。

## 使用限制

1. AI阈值慢盘检测插件可检出以下四种情况的慢盘：
   - 压力大导致的慢盘，上报告警日志中含有关键字"io_press"；
   - 盘故障导致的慢盘，上报告警日志中含有关键字"driver_slow"；
   - IO栈异常导致的慢盘，上报告警日志中含有关键字"kernel_slow"；
   - 未知故障导致的慢盘，上报告警日志中含有关键字"unknown"。
2. AI阈值慢盘检测插件运行时占用系统性能（cpu利用率、内存使用率、io吞吐等）不超过整个运行环境的5%。
3. 仅支持openEuler-20.03-LTS-SP4版本，并使用4.19.90内核。
4. 支持对nvme-ssd、sata-ssd、sata-hdd盘进行慢盘检测。
5. 仅支持对nvme-ssd、sata-ssd、sata-hdd盘进行慢盘检测，区分盘的方法请参考[常见问题与解决方法 - Q2](./question_and_answer.md#问题2：如何区分系统上的盘是什么类型？)。
6. 启动平均阈值巡检前，请确认sysSentry、xalarmd、sentryCollector服务均处于运行状态。


## 安装插件

### 前置条件

已安装sysSentry巡检插件，sentryCollector采集服务已配置io相关采集项（请参考《[安装和使用](./installation_and_usage.md)》进行配置）

### 安装软件包

```shell
yum install -y ai_block_io pysentry_notify pysentry_collect python3-numpy
```

### 将ai_block_io加入框架管理

```shell
[root@openEuler ~]# sentryctl reload ai_block_io
```

## 配置文件说明

ai_block_io插件配置文件路径：/etc/sysSentry/plugins/ai_block_io.ini，配置文件修改会在下一次启动巡检任务时生效。

| 配置段              | 配置项                | 配置项说明                                                   | 默认值         | 必选项 |
| ------------------- | --------------------- | ------------------------------------------------------------ | -------------- | ------ |
| [log]               | level                 | 记录日志的等级，可配置范围是debug/info/warning/error/critical，未配置或值异常时使用默认参数 | info           | Y      |
| [common]            | disk                  | 磁盘名称，由逗号分隔，default表示当前环境上所有盘，配置异常时仅保留正确字段 | default        | Y      |
| [common]            | stage                 | 监控阶段，由逗号分隔，目前已支持throtl/wbt/gettag/plug/deadline/hctx/requeue/rq_driver/bio九个阶段，根据盘种类不同提供的stage可能有不同，配置default表示盘支持的所有阶段，未配置时使用默认配置，配置异常时报错退出；注：用户自行配置时，必须包含bio阶段 | default        | Y      |
| [common]            | iotype                | io类别，由逗号分隔，共支持两种场景：read、write，未配置时使用默认配置，配置异常时报错退出 | read,write     | Y      |
| [common]            | period_time           | 插件的巡检周期，整形类型，单位为秒，数值应为sentryCollector采集周期的整数倍，且倍数不超过sentryCollector的max_save（请参考sentryCollector配置文件） | 1              | Y      |
| [algorithm]         | train_data_duration   | AI阈值算法训练数据采集时长，单位h, 浮点类型，该字段值越大，算法统计结果越稳定。范围为0~720，未配置时使用默认配置，配置异常时报错退出 | 24             | Y      |
| [algorithm]         | train_update_duration | AI阈值算法阈值更新时长，浮点类型，单位h, 该字段值越小，阈值更新越快，误报越高。范围为0~train_data_duration，未配置时使用默认配置，配置异常时报错退出 | 2              | Y      |
| [algorithm]         | algorithm_type        | AI阈值算法类型，字符串类型，该字段取值可选项为：boxplot/n_sigma，未配置时使用默认配置，配置异常时报错退出 | boxplot        | Y      |
| [algorithm]         | boxplot_parameter     | boxplot算法的参数，浮点类型，该字段值越大，对异常的敏感程度就越低。范围为0~10，未配置时使用默认配置，配置异常时报错退出 | 1.5            | N      |
| [algorithm]         | n_sigma_parameter     | n_sigma算法的参数，浮点类型，该字段值越大，对异常的敏感程度就越低。范围为0~10，未配置时使用默认配置，配置异常时报错退出 | 3.0            | N      |
| [algorithm]         | win_type              | AI阈值算法检测窗口类型，适用于不同的检测目的，字符串类型，该字段取值可选项为：not_continuous/continuous/median。未配置时使用默认配置，配置异常时报错退出 | not_continuous | Y      |
| [algorithm]         | win_size              | AI阈值算法检测窗口长度，慢IO检测时只判断窗口内的数据是否为异常，整数类型，范围为0~300。未配置时使用默认配置，配置异常时报错退出 | 30             | Y      |
| [algorithm]         | win_threshold         | AI阈值算法超阈值数量，整形类型，该字段值越小，算法上报异常速度越快，误报越高。范围为1~win_size，未配置时使用默认配置，配置异常时报错退出 | 6              | Y      |
| [latency_DISK_TYPE] | read_avg_lim          | 读时延平均值上限，单位us，代表窗口中读IO平均时延限制，数值越大，算法漏报率越高，未配置时使用默认配置，配置异常时报错退出 | 见下方注释3              | Y      |
| [latency_DISK_TYPE] | write_avg_lim         | 写时延平均值上限，单位us，代表窗口中写IO平均时延限制，数值越大，算法漏报率越高，未配置时使用默认配置，配置异常时报错退出 | 见下方注释3              | Y      |
| [latency_DISK_TYPE] | read_tot_lim          | 读时延绝对上限，单位us，读时延超过此数据即为异常数据，数值越大，算法漏报率越高，未配置时使用默认配置，配置异常时报错退出 | 见下方注释3              | Y      |
| [latency_DISK_TYPE] | write_tot_lim         | 写时延绝对上限，单位us，写时延超过此数据即为异常数据，数值越大，算法漏报率越高，未配置时使用默认配置，配置异常时报错退出 | 见下方注释3              | Y      |
| [iodump]            | read_iodump_lim       | 读iodump绝对上限，整形类型，读iodump数量超过此数据即为异常数据，数值越大，算法漏报率越高，未配置时使用默认配置，配置异常时报错退出 | 0              | Y      |
| [iodump]            | write_iodump_lim      | 写iodump绝对上限，整形类型，写iodump数量超过此数据即为异常数据，数值越大，算法漏报率越高，未配置时使用默认配置，配置异常时报错退出 | 0              | Y      |

>![](figures/icon-note.gif)**说明：** 
>1. latency_[DISK_TYPE]、iodump配置段的所有参数调整均会影响算法的准确性，且优劣并存：若数值越大，算法漏报率越高，则数值越小，算法误报率越高。需要根据经验进行取舍。
>2. [DISK_TYPE]为磁盘类型，目前仅支持三类：sata_ssd、nvme_ssd、sata_hdd。
>3. 目前不同磁盘read_avg_lim/write_avg_lim/read_tot_lim/write_tot_lim默认配置不同，详情如下：
>    - sata_ssd盘默认read_avg_lim为10000us, write_avg_lim为10000us, read_tot_lim为50000us， write_tot_lim为50000us；
>    - nvme_ssd盘默认read_avg_lim为300us, write_avg_lim为300us, read_tot_lim为500us， write_tot_lim为500us；
>    - sata_hdd盘默认read_avg_lim为15000us, write_avg_lim为15000us, read_tot_lim为50000us， write_tot_lim为50000us。
>4. win_type选择检测类型时，各选项分别代表以下含义：
>    - not_continuous：检测窗口内异常点不要求连续；
>    - continuous：检测窗口内异常点要求连续；
>    - median：检测窗口内所有数据点的中位数是否超过阈值。
>5. 当选择算法类型是boxplot，boxplot_parameter是必需的；当选择算法类型是n_sigma，n_sigma_parameter是必需的。

### 使用AI阈值慢盘检测插件

1. 启动巡检

   ```shell
   sentryctl start ai_block_io
   ```

2. 查看巡检插件状态

   ```shell
   sentryctl status ai_block_io
   ```

   状态为RUNNING即为运行中，状态为EXITED为退出

3. 查看告警信息

   ```shell
   sentryctl get_alarm ai_block_io -s 1 -d
   ```

   示例：

   ```shell
    [
        {
            "alarm_id": 1002,
            "alarm_type": "ALARM_TYPE_RECOVER",
            "alarm_level": "MINOR_ALARM",
            "timestamp": "2024-10-28 09:53:41",
            "alarm_info": {
                "alarm_source": "ai_block_io",
                "driver_name": "sda",
                "io_type": "write",
                "reason": "driver_slow",
                "block_stack": "bio,rq_driver",
                "alarm_type": "latency",
                "details": {
                    "latency": "{'read': {'bio': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 'rq_driver': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]}, 'write': {'bio': [17.8, 17.9, 18.0, 69.5, 79.2, 79.6, 80.4, 79.9, 81.2, 79.9, 76.2, 81.3, 78.7, 81.0, 81.0, 77.8, 79.1, 78.4, 82.1, 79.2, 80.1, 77.6, 79.5, 81.7, 78.4, 80.6, 77.5, 81.9, 81.1, 78.3], 'rq_driver': [15.1, 15.2, 15.3, 23.7, 28.8, 25.6, 27.0, 24.5, 28.2, 28.0, 26.0, 28.1, 27.3, 28.2, 28.7, 26.4, 26.8, 26.0, 28.1, 26.4, 27.5, 24.8, 27.7, 27.0, 25.7, 29.2, 25.6, 28.8, 27.9, 26.5]}}",
                    "iodump": "{'read': {'bio': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 'rq_driver': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]}, 'write': {'bio': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 'rq_driver': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]}}",
                }
            }
        }
    ]
   ```
   
   输出结果中各字段介绍： 

   | 字段 | 描述 |
   | --- | --- |
   | alarm_id | 用户上报告警的id，AI阈值慢盘检测插件的告警id固定为1002 |
   | alarm_type | 告警的类型，AI阈值慢盘检测插件的告警类型为ALARM_TYPE_OCCUR，代表告警产生 |
   | alarm_level | 告警的等级，AI阈值慢盘检测插件的告警等级为MINOR_ALM，代表系统存在异常，并且已经尝试自动隔离等方式修复 |
   | timestamp | 告警上报的时间 |
   | alarm_info | 告警内容详细信息，由AI阈值慢盘检测插件的自定义内容，不同的巡检插件上报的内容不一致 |

   alarm_info中各字段解释如下：
   
   | alarm_info中字段 | 描述 |
   | --- | --- |
   | alarm_source | 告警插件名称，AI阈值慢盘检测插件的固定值为ai_block_io |
   | driver_name | 告警磁盘名称，如sda |
   | io_type | 告警io类型，可能存在两种告警：<br>1. read：读io慢盘故障告警<br>2. write：写io慢盘故障告警 |
   | reason | 告警原因，AI阈值慢盘检测插件可能存在以下四种不同告警原因：<br>1. io_press，压力大导致的慢盘告警；<br>2. driver_slow，盘故障导致的慢盘告警；<br>3. kernel_slow，IO栈异常导致的慢盘告警；<br>4. unknown，未知故障导致的慢盘告警； |
   | block_stack | 慢io出现异常的阶段，可能出现的阶段为bio/throtl/wbt/bfq/rq_driver/gettag/plug/deadline/hctx/requeue共九个阶段的组合，九个阶段的详细介绍可参考[《二次开发指南》 - 插件事件告警上报](./developer_guide.md#插件事件告警上报) |
   | details | 告警日志内记录的信息，仅在get_alarm执行包含"-d/--detailed"选项时展示，内容为上报异常磁盘的latency（io时延数据）和iodump（io超时未完成数量）的信息 |

4. 停止巡检

   ```shell
   sentryctl stop ai_block_io
   ```

5. 查看巡检结果信息
   
   在巡检停止后可查看巡检结果信息：

   ```shell
   sentryctl get_result ai_block_io
   ```
   