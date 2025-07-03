# soc_ring_sentry

#### 介绍
soc_ring_sentry是一款依赖sysSentry并用于SOC STL巡检的插件，该插件的使用方法是：

usage: soc_ring_sentry [OPTIONS]

Options:
  -h,            Show this help message and exit.
  -g,            Get the SOC Ring sentry case.

用户可以通过 `/etc/sysconfig/soc_ring_sentry.env` 修改环境变量以配置不同参数
该文件中各个环境变量含义为：
`LOG_LEVEL`
日志登记配置，默认配置为info级别。也可以配置为debug, warning, 或者error.

`SOC_RING_SENTRY_INTENSITY_DELAY`
巡检间隔时长配置，单位ms，默认配置为600ms。用户可自定义其他所需间隔时长。

`SOC_RING_SENTRY_MEM_SIZE`
巡检空间大小配置，单位KB，默认配置为4096KB。也可配置为其他64KB的倍数。

`SOC_RING_SENTRY_LOOP_CNT`
巡检次数配置，默认配置为0，即持续巡检。若配置为其他值则为巡检次数。

`SOC_RING_SENTRY_FAULT_HANDLING`
后处理标识配置，默认配置为1，即主动触发panic。
设置为0则表示检测到错误不做任何处理。
设置为2则表示检测到错误主动关机。
设置为3则表示检测到错误主动重启。

`SOC_RING_SENTRY_BLACKLIST`
巡检黑名单配置，默认配置为空。用户可将不运行巡检的CPU核号写入该环境变量，例如`SOC_RING_SENTRY_BLACKLIST=0,2,4,6-10`

