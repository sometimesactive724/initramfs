#!/usr/bin/env python3
import os
from os.path import join
from shutil import copyfile

def syscall_header():
    yield '''
struct sys_dirent {
\tlong inode;
\tlong offset;
\tshort size;
\tchar type;
\tchar name[];
};
long syscall(int number, int *error, ...);

// PATH_MAX with null terminator
#define SYS_PATH_MAX_WITH_NUL 256
'''
    with open('/usr/include/asm/unistd_64.h') as f:
        for l in f:
            if l.startswith('#define __NR_'):
                yield '#define SYS' + l[12:].upper()

def write_all(fd, data):
    written = 0
    while written < len(data):
        written += os.write(fd, data[written:])

def extract_modules(output, modules):
    o = os.open(output, os.O_WRONLY|os.O_TRUNC|os.O_CREAT, 0o666)
    for module, path in modules.items():
        f = os.open(path, os.O_RDONLY)
        write_all(o, b'static const char ' + module.encode('ascii') + b'[]={')

        length = 0

        while d := os.read(f, 16384):
            length += len(d)
            data = b','.join(str(i).encode('ascii') for i in list(d)) + b','
            write_all(o, data)
        os.close(f)
        write_all(o, b'};')

    write_all(o, b'static const struct module{size_t size;const char*data;}modules[]={')
    for module in modules:
        m = module.encode('ascii')
        write_all(o, b'{sizeof '+m+b','+m+b'},')
    write_all(o, b'};')
    os.close(o)

class SpawnError(Exception):
    def __init__(self, *, code = None, signum = None):
        assert (code is None) ^ (signum is None)
        if code is not None:
            super().__init__(f'Process returned {code}')
            self.code = code
        if signum is not None:
            super().__init__(f'Process was killed by signal {signum}')
            self.signum = signum

def spawn(*arguments, file=None, environ=None, pass_fds = None):
    return os.posix_spawnp(
        arguments[0] if file is None else file,
        arguments,
        os.environb if environ is None else environ,
        file_actions = None if pass_fds is None else tuple((os.POSIX_SPAWN_DUP2, k, v) for k, v in pass_fds)
    )
def wait(pid):
    if (e := os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1])) != 0:
        raise SpawnError(signum = -e) if e < 0 else SpawnError(code = e)

def generate(working_directory, module_directory, source_directory, out):
    syscall = os.open(join(source_directory, 'syscall.h'), os.O_WRONLY|os.O_TRUNC|os.O_CREAT, 0o666)
    for i in syscall_header():
        write_all(syscall, i.encode('ascii'))
    os.close(syscall)
    nasm = spawn('nasm', '-felf64', join(source_directory, 'syscall.s'), '-o', join(working_directory, 'syscall.o'))
    copyfile('/boot/intel-ucode.img', out)

    modules = [
        'crypto.xor',
        'lib.raid6.raid6_pq',
        'arch.x86.crypto.crc32c-intel',
        'lib.libcrc32c',
        'crypto.xxhash_generic',
        'fs.btrfs.btrfs'
    ]
    modules = [(m, name := f'module{i}', join(working_directory, name + '.ko')) for i, m in enumerate(modules)]
    for i in [spawn('zstd', '-fdo', v, join(module_directory, m.replace('.', '/')) + '.ko.zst')  for m, k, v in modules]:
        wait(i)
    extract_modules(join(source_directory, 'modules.h'), {k: v for _, k, v in modules})

    wait(nasm)
    wait(spawn('gcc', join(source_directory, 'initramfs.c'), join(working_directory, 'syscall.o'), '-nostdlib', '-s', '-no-pie', '-static', '-fno-stack-protector', '-Ofast', '-w', '-o', join(working_directory, 'init')))
    pipe = os.pipe()
    output = os.open(out, os.O_WRONLY|os.O_APPEND)
    cpio = spawn('env', '-C', working_directory, 'cpio', '-o0H', 'newc', pass_fds = ((pipe[0], 0),(output, 1)))
    os.close(pipe[0])
    write_all(pipe[1], b'init')
    os.close(pipe[1])
    os.close(output)
    wait(cpio)

if __name__ == '__main__':
    from sys import argv
    os.makedirs(argv[3], exist_ok=True)
    generate(argv[3], argv[2], argv[1], join(argv[3], 'initramfs'))
