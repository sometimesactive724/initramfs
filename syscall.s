global syscall
syscall:
mov [rsp - 8], rsi
mov eax, edi
mov rdi, rdx
mov rsi, rcx
mov rdx, r8
mov r10, r9
mov r8, [rsp + 8]
mov r9, [rsp + 16]
syscall
cmp rax, -4095
jae .error
ret
.error:
neg eax
mov rdx, [rsp - 8]
mov [rdx], eax
mov rax, -1
ret
