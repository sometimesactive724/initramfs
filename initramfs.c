#include<stdnoreturn.h>
#include<stdint.h>
#include<fcntl.h>
#include<sys/mount.h>
#include<stddef.h>
#include<linux/mman.h>
#include<dirent.h>
#include<fcntl.h>
#include"syscall.h"
#include"modules.h"
static size_t strlen(const char *s) {
        const char *c;
        for(c = s; *c; c++);
        return c - s;
}
static void print(const char *s) {
        int e;
        syscall(SYS_WRITE, &e, 1, s, strlen(s));
}
static void printi(uint64_t i) {
        char n[20];
        char *p = n + 20;
        do *--p = i % 10 + '0';
        while(i/=10);
        int e;
        syscall(SYS_WRITE, &e, 1, p, 20 - (p - n));
}
static noreturn void panic(char *msg, int e) {
	print(msg);
	print(", errno: ");
	printi(e);
	print("\n");
	syscall(SYS_EXIT, &e, 1);
}
static void removedircontents(int parentfd, char* name) {
	int e;
	int dirfd = syscall(SYS_OPENAT, &e, parentfd, name, O_RDONLY|O_NONBLOCK|O_CLOEXEC|O_DIRECTORY);
	if(dirfd == -1)
		panic("could not open directory", e);
	char buf[4096];
	long l;
	while(l = syscall(SYS_GETDENTS64, &e, dirfd, buf, sizeof buf)) {
		if(l == -1)
			panic("error listing directory", e);
		for(struct sys_dirent *d = (struct sys_dirent*)buf; (char*)d - (char*)buf < l; d=(struct sys_dirent*)((char*)d+d->size)) {
			if(d->name[0] == '.' && (d->name[1] == 0 || (d->name[1] == '.' && d->name[2] == 0)))
				continue;
			if(d->type == DT_DIR) {
				removedircontents(dirfd, d->name);
				if(syscall(SYS_UNLINKAT, &e, dirfd, d->name, AT_REMOVEDIR) == -1)
					panic("could not remove directory", e);
			}
			else if(syscall(SYS_UNLINKAT, &e, dirfd, d->name, 0) == -1)
				panic("could not remove file", e);
		}
       }
	if(syscall(SYS_CLOSE, &e, dirfd) == -1)
		panic("error closing file descriptor", e);
}
void _start() {
	int e;
	for(const struct module *module = modules; (char*)module - (char*)modules < sizeof modules; module++)
		if(syscall(SYS_INIT_MODULE, &e, module->data, module->size, ""))
			panic("error adding module", e);
        if(syscall(SYS_MOUNT, &e, "devtmpfs", "/dev", "devtmpfs", 0, NULL) == -1)
		panic("error mounting devtmpfs to /dev", e);

        if(syscall(SYS_MOUNT, &e, "/dev/nvme0n1p7", "/root", "btrfs", MS_LAZYTIME|MS_RELATIME, NULL) == -1)
		panic("error mounting root", e);

	if(syscall(SYS_MOUNT, &e, "/dev", "/root/dev", NULL, MS_MOVE, NULL) == -1)
		panic("error moving mount", e);

	if(syscall(SYS_CHDIR, &e, "/root") == -1)
		panic("error changing directory", e);

	if(syscall(SYS_MOUNT, &e, ".", "/", NULL, MS_MOVE, NULL) == -1)
		panic("error switching root", e);

	removedircontents(-1, "/");

	if(syscall(SYS_CHROOT, &e, ".") == -1)
		panic("error changing root to new root", e);

	if(syscall(SYS_EXECVE, &e, "/usr/lib/systemd/systemd", (char*[]){"systemd", NULL}, NULL) == -1)
		panic("error executing init", e);
}
