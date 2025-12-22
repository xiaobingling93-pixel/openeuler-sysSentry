# 常见问题与解决方法

## **问题1：如何使用内核无锁采集方案进行数据采集？**

内核无锁采集和ebpf采集无法同时使用，且内核无锁采集优先级高于ebpf采集，openEuler-20.03-LTS-SP4版本操作系统上运行sentryCollector服务时默认使用ebpf采集，如需要启动内核无锁采集，需通过以下方法重编内核：

step1. 下载kernel-source包并解压

```shell
[root@openEuler ~]# yumdownloader kernel-source-4.19.90-2409.3.0.0294.oe2003sp4
# 请跟据机器架构替换[$ARCH]为x86_64或aarch64
[root@openEuler ~]# rpm2cpio kernel-source-4.19.90-2409.3.0.0294.oe2003sp4.[$ARCH].rpm |cpio -div
[root@openEuler ~]# cd usr/src/linux-4.19.90-2409.3.0.0294.oe2003sp4.[$ARCH]/
```

step2. 配置&构建

```shell
[root@openEuler ~]# yum install -y openssl-devel bc rsync gcc gcc-c++ flex bison m4 ncurses-devel elfutils-libelf-devel

# 搜索BLK_IO_HIERARCHY_STATS，对应的config全部打开后保存退出
[root@openEuler ~]# make menuconfig

修改Makefile中的EXTRAVERSION = .blk_io (这里修改会体现在最终构建出来的内核版本号上)

# 编译
[root@openEuler ~]# make -j 200 && make modules_install && make install
```

step3. 使用新内核重启

```shell
[root@openEuler ~]# grubby --info ALL 				# 查看新编的内核对应的index
[root@openEuler ~]# grubby --set-default-index N 	# N对应新编内核的index
[root@openEuler ~]# reboot
```

step4. 重新启动sysSentry相关服务

```shell
[root@openEuler ~]# systemctl restart xalarmd
[root@openEuler ~]# systemctl restart sysSentry
[root@openEuler ~]# systemctl restart sentryCollector
```

可以查看环境上是否存在以下目录，请自行替换[disk]为有效磁盘名

```shell
[root@openEuler ~]# ll /sys/kernel/debug/block/[disk]/blk_io_hierarchy/
```

如目录存在，则此时sentryCollector服务运行的为内核无锁采集

## **问题2：如何区分系统上的盘是什么类型？**

在环境中通过`lsblk -d`命令可以查看到当前环境上的所有磁盘类型及其rotate情况：
1. nvme_ssd盘：磁盘名以nvme开头且rotate为0
2. sata_ssd盘：磁盘名以sd开头且rotate为1
3. sata_hdd盘：磁盘名以sd开头且rotate为0

## **问题3：平均阈值插件/AI阈值插件运行时会对系统上的哪些数据进行分析？**
平均阈值插件/AI阈值插件会通过sentryCollector服务获取系统上指定磁盘各阶段的latency和iodump数据并进行数据分析：
- latency：io时延数据，统计周期内io完成的时间信息；
- iodump：io超时未完成数量，如果某个io超过1秒未完成，即为iodump数量加一。
  
sentryCollector采集共有ebpf采集和内核无锁采集两种方式，默认会使用ebpf采集，两种采集的区别及内核无锁采集的使用方法请参考《[二次开发指南](./developer_guide.md)》文档

## **问题4：已经执行了`sentryctl start avg_block_io/ai_block_io`命令，为什么查看状态依然是EXITED？**
可能存在以下原因：

1. sentryCollector服务未启动，可通过`systemctl status sentryCollector`查看服务是否为运行状态；
2. 配置文件字段异常，可以查看/var/log/sysSentry/avg_block_io.log（或ai_block_io.log）日志文件是否存在报错信息，并根据报错内容修改/etc/sysSentry/plugins/avg_block_io.ini（或ai_block_io.ini）文件。值得注意的是，当period_time配置与sentryCollector采集服务配置不匹配时，avg_block_io报错信息为`"Cannot get valid disk"`而非period_time异常。