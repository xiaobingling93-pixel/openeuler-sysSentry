# 灵衢可靠性插件

该插件支持带外下电、OOM、panic、带内下电和UB内存故障事件消息接收和上报，依赖xalarmd服务。整体流程为：内核通知链阻塞事件进程并发送消息，消息经过内核设备、用户态插件、xalarmd的转发发送至对应的处理程序，程序处理完毕后将消息反向传播至内核，内核根据返回消息的时间和结果来判断下一步处理操作。

## 硬件规格要求

- 仅支持aarch64架构。
- 仅支持满足灵衢总线协议的服务器。
- 使用UVB通信时，需要依赖BIOS支持相应功能，否则UVB通信功能无法使用。

## 使用限制

- 当前仅支持单进程订阅和处理。
- 完整功能依赖内核6.6及以上版本，并且需要包含下面驱动，否则插件无法使用。
  - sentry_reporter
  - sentry_remote_reporter

- 带外下电特性仅针对BMC界面下电场景。
- 事件发送等待期间，禁止卸载sentry_remote_reporter或者sentry_reporter驱动。
- 当事件发生后，针对远端未回复的情况，阻塞通知链实际超时时间可能会超过用户设置的时间，该现象由内核计时器不准引起，为正常现象。
- 本节点的CNA和eid信息、集群其他节点信息需要管控面进行设置，如果未设置相关信息，则系统panic或者带内下电的时候，不会触发劫持操作。
- 当URMA建链成功后，如果链路出现异常，支持重新建链。
- UB通信链路的畅通依赖配置正确。
- 心跳回复之前，panic/带内下电消息无法发送；若心跳检测的两次周期之间，链路断开，则无法自动重新建链，panic/带内下电消息无法发送。
- 如果需要开启panic事件劫持功能，kernel命令行参数需要添加`crash_kexec_post_notifiers`。
- 如果需要开启OOM事件劫持功能，kernel命令行参数需要添加`numa_remote`。
- UB故障事件仅上报给注册了1013事件类型的服务，该类型故障不支持重发。
- UB故障事件上报的详细信息中仅包含借用内存物理地址、memid信息，内存借用关系依赖通过系统中内存借用管理服务查询获取。
- UB故障事件上报不支持故障风暴抑制能力，当前BIOS已有对故障事件的抑制功能，sysSentry不再做进一步抑制处理。
- 业务使用Device方式进行内存借用/共享使用时，当内存发生UCE故障，内核不支持对故障页进行隔离，依赖业务订阅对应的故障事件后，对内存进行解映射后，隔离故障页再进行重新映射。
- 插件会向使用发生UCE故障地址的业务线程发送SIGBUS信号，业务线程需要针对SIGBUS信号做自定义截获处理流程，否则业务线程会按照信号默认行为被杀死。

## 关键规格

- 集群内最大支持16个节点。
- 基于URMA通信时，节点eid仅支持配置IPV6格式。
- 针对带外下电/oom/UB内存故障/panic/带内下电流程的劫持功能默认处于关闭状态，需要由管控面执行命令打开相应功能才能生效。
- 针对panic/带内下电流程的劫持操作，系统发送事件消息并阻塞一段时间后继续原流程，相关日志记录在dmesg中（内核日志持久化由kbox服务提供），最终不会阻塞panic/带内下电流程。
- 由于panic/带内下电流程会被劫持，因此系统的panic/带内下电的重启时间比原有时间增加，具体时间为设置好的超时时间，默认为35秒。当节点在超时时间内收到回复消息，则会提前结束阻塞继续原流程。
- 使用UVB通信时，当CNA无效时将超时失败，因BIOS超时时间为1s，1s后BIOS才能进行下一个CNA转发。
- sysSentry支持对UBUS驱动上报的内存故障事件进行处理和转发，转发的事件类型为sysSentry自定义故障类型。
- sysSentry支持对于异步访问远端内存失败场景下，根据用户配置选择是否对进程进行复位，若需要复位，NUMA场景下则根据物理地址查询对应的进程pid，FD场景下需要依赖obmm组件提供接口查询进程pid,成功获取进程pid后，发送SIGBUS信号触发进程复位。

## 安装插件

### 前置条件

已安装sysSentry框架和xalarmd服务。

### 安装软件包

```shell
yum install -y sentry_msg_monitor
```

### 将sentry_msg_monitor加入框架管理

```shell
sentryctl reload sentry_msg_monitor
```

## 使用灵衢可靠性插件

### 事件使能和配置

#### 带外下电事件配置

带外下电事件默认是未开启的，开启或者关闭方法如下：

```shell
sentryctl set sentry_reporter --power_off=on/off
```

#### OOM事件配置

OOM事件默认是未开启的，开启或者关闭方法如下：

```shell
sentryctl set sentry_reporter --oom=on/off
```

#### UB内存故障上报事件配置

UB内存故障上报事件默认是未开启的，开启或者关闭方法如下：

```shell
sentryctl set sentry_reporter --ub_mem_fault=on/off
```

用户可以配置发生UB内存故障时是否需要向使用故障内存的线程发送SIGBUS信号，默认是开启的。开启或者关闭方法如下：

```shell
sentryctl set sentry_reporter --ub_mem_fault_with_kill=on/off
```

#### panic事件上报功能配置

panic事件是跨节点的，需要通过URMA或者UVB发送msg到主节点，因此，下面步骤2和步骤3至少需要配置一个。

**步骤1** 设置eid和cna信息，以及根据需要设置超时时间。

```shell
sentryctl set sentry_remote_reporter --eid=eid --cna=cna --panic=on --panic_timeout_ms=xxx
```

panic事件配置参数说明：

| 参数 | 取值范围 | 说明|
| --- | --- | --- |
|--cna | 0~16777215| 配置节点的CNA信息，CNA具有唯一性，不同的节点不要配置相同的CNA |
| --eid | IPV6地址 | 配置节点的eid信息，eid为128位数，按照16进制表示，每16位（4字节）通过英文“;”分割，长度固定为39。节点eid可以配置单个eid或者2个eid，通过";"分割 |
| --panic | "on"或者"off" | 控制开启/关闭panic劫持事件功能，panic事件劫持功能默认处于关闭状态。 |
| --panic_timeout_ms | 0~3600000 |配置通知链阻塞时间，单位:毫秒，默认值:35000 |

**步骤2（可选）** 初始化URMA通信组件参数

```shell
sentryctl set sentry_urma_comm --server_eid="eid11,eid21,...,eidn1;eid12,eid22,...,eidn2" --client_jetty_id=xxx
```

URMA通信组件初始化参数说明：

| 参数 | 取值范围| 说明|
| --- | ---| --- |
|--server_eid |IPV6地址 |配置当前节点所需链接的其他节点的eid信息，最多支持 2 DIE 32个节点建链。配置建链eid的时候，第一个eid是本端eid，后面为需要联通的对端eid，eid之间使用英文","分割。配置多个DIE的链接方式时，中间使用英文";"分割。<br>  --server_eid中本端eid的设置顺序需要和前面--eid设置的顺序相同，否则会建链失败 |
|--client_jetty_id |3~1023 | 配置当前节点的jetty id信息，需要设置未被占用的值|

**步骤3（可选）**  初始化UVB通信组件参数

```shell
sentryctl set sentry_uvb_comm --server_cna="cna1；cna2;...;cnan"
```

UVB通信组件初始化参数说明：

| 参数 | 取值范围| 说明|
| --- | ---| --- |
|--server_cna |0~16777215(0xFFFFFF)| 配置当前节点所需要链接的对端节点的CNA信息，每个CNA之间使用英文";"分割。<br>  - 多个节点的CNA信息通过英文";"分割<br>  - 建议不要设置重复的CNA。|

#### 带内下电事件上报功能配置

kernel reboot事件是跨节点的，需要通过URMA或者UVB发送msg到主节点，因此，下面步骤2和步骤3至少需要配置一个。

**步骤1** 设置eid和cna信息，以及根据需要设置超时时间。

```shell
sentryctl set sentry_remote_reporter --eid=eid --cna=cna --kernel_reboot=on --kernel_reboot_timeout_ms=xxx
```

带内reboot事件配置参数说明：

| 参数 | 取值 | 说明|
| --- | --- | --- |
|--cna | 0~16777215 | 配置节点的CNA信息，CNA具有唯一性，不同的节点不要配置相同的CNA |
| --eid | IPV6地址 | 配置节点的eid信息，eid为128位数，按照16进制表示，每16位（4字节）通过英文“;”分割，长度固定为39。节点eid可以配置单个eid或者2个eid，通过";"分割 |
| --kernel_reboot | "on"或者"off" | 控制开启/关闭带内reboot事件劫持功能，带内下电事件劫持功能默认处于关闭状态 |
| --kernel_reboot_timeout_ms | 0~3600000 |配置通知链阻塞时间，单位：毫秒，默认值:35000 |

**步骤2（可选）** 初始化URMA通信组件参数

```shell
sentryctl set sentry_urma_comm --server_eid="eid11,eid21,...,eidn1;eid12,eid22,...,eidn2" --client_jetty_id=xxx
```

URMA通信组件初始化参数说明：

| 参数 | 取值| 说明|
| --- | ---| --- |
|--server_eid |IPV6地址 |配置当前节点所需链接的其他节点的eid信息，最多支持 2 DIE 32个节点建链。配置建链eid的时候，第一个eid是本端eid，后面为需要联通的对端eid，eid之间使用英文","分割。配置多个DIE的链接方式时，中间使用英文";"分割。<br>  --server_eid中本端eid的设置顺序需要和前面--eid设置的顺序相同，否则会建链失败 |
|--client_jetty_id |3~1023 | 配置当前节点的jetty id信息，需要设置未被占用的值|

**步骤3（可选）**  初始化UVB通信组件参数

```shell
sentryctl set sentry_uvb_comm --server_cna="cna1；cna2;...;cnan"
```

UVB通信组件初始化参数说明：

| 参数 | 取值范围| 说明|
| --- | ---| --- |
|--server_cna |0~16777215(0xFFFFFF)| 配置当前节点所需要链接的对端节点的CNA信息，每个CNA之间使用英文";"分割。<br>  - 多个节点的CNA信息通过英文";"分割<br>  - 建议不要设置重复的CNA。|

### 故障事件上报和回复消息格式

#### 故障事件对应的告警id

| 故障事件 | 故障事件id |
| --- | --- |
| 带外下电事件上报 |1003 （ALARM_REBOOT_EVENT ） |
| 带外下电事件回复 |1004 （ALARM_REBOOT_ACK_EVENT） |
| OOM事件上报|1005（ALARM_OOM_EVENT）|
| OOM事件回复|1006（ALARM_OOM_ACK_EVENT）|
| Panic事件上报|1007（ALARM_PANIC_EVENT） |
| Panic事件回复|1008（ALARM_PANIC_ACK_EVENT） |
| 带内reboot事件上报|1009（ALARM_KERNEL_REBOOT_EVENT）|
| 带内reboot事件回复|1010（ALARM_KERNEL_REBOOT_ACK_EVENT） |
| UB内存故障事件|1013 （ALARM_UBUS_MEM_EVENT） |

#### 故障事件上报的消息格式

| 故障事件 | 故障事件消息格式 | 描述|
| --- | --- | ---|
|带外下电事件 | msgid|msgid:uint64_t类型，表示消息对应的id |
|OOM事件 | msgid_{nr_nid:nr_nid,nid:[nid[0],nid[1],...,nid[7]],sync:sync,timeout:timeout,reason:reason} |msgid:uint64_t类型，表示消息对应的id<br>  nr_nid:int类型，表示nid的数组长度<br>  nid[n]:int类型，表示nid数组脏每一项具体指<br>  sync:int类型，表示是否需要回复消息，1表示需要回复，0表示不需要回复。<br>  reason:int类型，产生oom的原因的原因号，具体内容查看linux/mm.h中reclaim_reason enum类型定义。 |
| Panic事件| msgid_{cna:cna,eid:eid}|msgid:uint64_t类型，表示消息对应的id<br>  cna:故障节点的CNA信息<br>  eid:故障节点的eid信息 |
| 带内reboot事件 | msgid_{cna:cna,eid:eid}  | msgid:uint64_t类型，表示消息对应的id<br>  cna:故障节点的CNA信息<br>  eid:故障节点的eid信息 |
| UB内存故障事件| json格式| 见下面"UB内存故障事件对应的消息字段说明"，示例：{"msgid":123,"sentry_ubus_mem_err_type":0,"ras_ubus_mem_err_type":1,"pa":"0x12345678","memid":1} |

UB内存故障事件对应的消息字段说明：

| 参数名称 | 类型 | 取值说明|
| --- | --- | ---|
|msgid|整型|表示内核驱动上报故障对应的消息id|
|sentry_ubus_mem_err_type|整型|sentry上报的内存故障类型|
|ras_ubus_mem_err_type|整型|UBUS上报的详细故障原因|
|pa|字符串|访问失败的物理地址，0x开头表示16进制64位整数|
|memid|整型|该物理地址对应OBMM中的memid|

#### 故障事件回复消息格式

| 故障事件类型      | 故障事件回复消息格式 | 描述 |
| ----------------- | -------------------- | ---- |
| 带外下电事件      | msgid_res |msgid:uint64_t类型，表示消息对应的id<br>  res:unsigned long类型，表示消息处理结果      |
| OOM事件                  |msgid_res |msgid:uint64_t类型，表示消息对应的id<br>  res:unsigned long类型，表示消息处理结果      |
| panic事件         |msgid_{cna:cna,eid:eid}_res                      |msgid:uint64_t类型，表示消息对应的id<br>  cna:对应节点的CNA信息<br>  eid:对应节点的eid信息<br>  res:unsigned long类型，表示消息处理结果     |
| kernel reboot事件 |msgid_{cna:cna,eid:eid}_res                      |msgid:uint64_t类型，表示消息对应的id<br>  cna:对应节点的CNA信息<br>  eid:对应节点的eid信息<br>  res:unsigned long类型，表示消息处理结果     |

### xalarmd接口

消息接收处理程序依赖xalarmd服务，需要使用到的接口详见 《[二次开发指南](./developer_guide.md)》
