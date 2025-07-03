all: soc_ring_sentry

soc_ring_sentry:
	gcc *.c -Wall -o3 -I../../libsentry/c/log -L../../libsentry/c/log/build -I../../libs/libxalarm -L../../libs/build/libxalarm -lxalarm -lsentry_log -ljson-c -pthread -lnuma -o soc_ring_sentry

clean:
	rm -f soc_ring_sentry

.PHONY: all clean
