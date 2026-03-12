# bmc ras告警上报插件

用户可通过bmc ras告警上报插件获取bmc上各种ras告警信息，当插件检测到bmc ras告警时，会将结果上报给xalarmd服务。检测模式为定时轮询，每次轮询会上报当前产生的告警，不上报历史告警。用户可通过注册告警或get_alarm命令的方式查看告警结果（注册告警和get_alarm命令可参考《[安装和使用](https://docs.openeuler.openatom.cn/zh/docs/20.03_LTS_SP4/docs/sysSentry/%E5%AE%89%E8%A3%85%E5%92%8C%E4%BD%BF%E7%94%A8.html)》）。

## 硬件规格要求

- 仅支持鲲鹏服务器
- bmc版本要求5.13.00.0及以上

## 安装插件

### 前置条件

已安装sysSentry巡检插件，sentryCollector采集服务已配置io相关采集项（请参考《[安装和使用](./installation_and_usage.md)》进行配置）。
硬盘raid场景下需要安装raid工具（目前仅支持raid工具hiraidadm《[hiraidadm工具使用指南](https://support.huawei.com/enterprise/zh/doc/EDOC1100048779/d802bccf)》，raid工具storcli64《[storcli64工具使用指南](https://support.huawei.com/enterprise/zh/doc/EDOC1100048779/596d0e24)》）。

### 安装软件包

```shell
yum install -y ras_bmc_sentry ipmitool libxalarm
```

## bmc ras告警上报插件参数配置

bmc ras告警上报插件参数配置保存在/etc/sysSentry/plugins/bmc_ras_sentry.ini

- 配置项说明

| 配置项        | 配置项说明                                                        | 默认值    | 必选项 |
| ------------- | ----------------------------------------------------------------- | --------- | ------ |
| log_level     | 日志级别，可配置范围为debug/info/warning/error/critical           | info      | y      |
| patrol_second | 采样周期，单位为秒，可配置范围为[60，3600]                        | 60        | y      |
| bmc_events    | 查询事件配置，每个事件以四位数字标识，前两位标识主体类型，后两位标识告警事件，00表示所有当前类型告警事件，0000表示所有类型所有事件，各个事件间以逗号隔开（具体事件ID参考BMC告警事件字典）| 0000      | y   |

- 配置示例

```ini
log_level=info

patrol_second=60

bmc_events=0101,0102
```

### BMC告警事件字典

- BMC 主体类型字典

| id       | 类型说明 |
| -------- | -------- |
| 01       | 硬盘     |
| 02       | raid卡   |
| 03       | 内存     |
| 04       | cpu      |

- BMC 硬盘事件字典

| id       | bmc告警id  | 事件说明                              |
| -------- | ---------- | ------------------------------------- |
| 01       | 0x02000009 | 硬盘预故障                            |
| 02       | 0x2B000003 | SAS PHY 误码增长过快                  |
| 03       | 0x02000013 | 硬盘 MCE/AER 错误                     |
| 04       | 0x02000015 | 硬盘温度过高一般告警                  |
| 05       | 0x02000019 | 硬盘温度过高严重告警                  |
| 06       | 0x02000027 | 硬盘状态异常                          |
| 07       | 0x0200002D | 硬盘丢失                              |
| 08       | 0x02000039 | 硬盘 I/O 性能下降                     |
| 09       | 0x0200003B | 硬盘有效冗余块比例较低                |
| 10       | 0x0200003D | 硬盘链路降速率                        |
| 11       | 0x02000041 | 硬盘预估剩余寿命过低                  |
| 12       | 0x0200001D | 硬盘剩余寿命过低告警                  |

## 使用bmc ras告警上报插件

1. 启动巡检

   ```shell
   sentryctl start bmc_ras_sentry
   ```

2. 查看巡检插件状态

   ```shell
   sentryclt status bmc_ras_sentry
   ```

   状态为RUNNING即为运行中，状态为EXITED为退出

3. 查看告警信息

   ```shell
   sentryctl get_alarm bmc_ras_sentry -s 1 -d
   ```

   sentryctl get_alarm 命令用法参考《[安装和使用](https://docs.openeuler.openatom.cn/zh/docs/20.03_LTS_SP4/docs/sysSentry/%E5%AE%89%E8%A3%85%E5%92%8C%E4%BD%BF%E7%94%A8.html)》

   示例：

   ```shell
    [
        {
            "alarm_id": 1015,
            "alarm_type": "ALARM_TYPE_OCCUR",
            "alarm_level": "MINOR_ALM",
            "timestamp": "2026-03-05 09:55:31",
            "alarm_info": {
                "alarm_source": "bcm_ras_sentry",
                "id": "0101",
                "bmc_id": "0x02000009",
                "level": 1,
                "time": "2026-03-02 11:25:44",
                "disk_info": {
                    "physical_disk": "034QVV10P8100491",
                    "logical_disk": "sda",
                }
            }
        }
    ]
   ```

   输出结果各字段介绍：

   | 字段 | 描述 |
   | --- | --- |
   | alarm_id | 用户上报告警的id，bmc ras告警上报插件的固定值为1015 |
   | alarm_type | 告警上报类型，bmc ras告警上报插件告警类型为ALARM_TYPE_OCCUR，代表告警产生|
   | alarm_level | 告警等级，bmc ras告警上报插件告警等级为MINOR_ALM，表示系统存在异常 |
   | timestamp | 告警上报的时间 |
   | alarm_info | 告警详细内容，由bmc ras告警上报插件自定义 |

   alarm_info各字段介绍：

   | 字段 | 描述 |
   | --- | --- |
   | alarm_source | 告警插件名称，bmc ras告警上报插件的固定值为bmc_ras_sentry |
   | id | bmc ras告警上报插件内部定义的告警事件id，（具体事件ID参考BMC告警事件字典） |
   | bmc_id | bmc上定义的告警id |
   | level | 告警等级，1-轻微，2-正常，3-严重，4-紧急 |
   | time | 告警产生的时间 |
   | disk_info | 硬盘内容，硬盘类型告警特有字段 |

   disk info各字段介绍：

   | 字段 | 描述 |
   | --- | --- |
   | physical_disk | 物理盘SN号，标识唯一物理盘 |
   | logical_disk | 逻辑盘符，表示os上显示的硬盘盘符，如sda |

4. 停止巡检

   ```shell
   sentryclt stop bmc_ras_sentry
   ```

5. 查看巡检结果

   在停止巡检后可查看巡检结果信息：

   ```shell
   sentryctl get_result bmc_ras_sentry
   ```
