# 定义编译器
CC = clang

ARCH := $(shell uname -m | sed 's/x86_64/x86/' | sed 's/aarch64/arm64/' | sed 's/ppc64le/powerpc/' | sed 's/mips.*/mips/')

# 定义内核态编译选项
KERNEL_CFLAGS = -O2 -g -target bpf -D__TARGET_ARCH_$(ARCH)

# 定义用户态编译选项
USER_CFLAGS = -g -fstack-protector-strong -D_FORTIFY_SOURCE=2 -O2 -Wl,-z,relro,-z,now -lbpf

# 定义目标文件
KERNEL_TARGET = ebpf_collector.bpf.o
USER_TARGET = ebpf_collector
SKELETON_HEADER = ebpf_collector.skel.h

# 默认目标
all: $(KERNEL_TARGET) $(SKELETON_HEADER) $(USER_TARGET)

# 编译内核态文件
$(KERNEL_TARGET): ebpf_collector.bpf.c
	$(CC) $(KERNEL_CFLAGS) -c $< -o $@

# 生成骨架文件
$(SKELETON_HEADER): $(KERNEL_TARGET)
	bpftool gen skeleton $< > $@
	rm -f $<

# 编译用户态文件
$(USER_TARGET): ebpf_collector.c $(SKELETON_HEADER)
	$(CC) $(USER_CFLAGS) $< -o $@

# 清理生成的文件
clean:
	rm -f $(KERNEL_TARGET) $(SKELETON_HEADER) $(USER_TARGET)

# 伪目标，避免与文件名冲突
.PHONY: all clean
