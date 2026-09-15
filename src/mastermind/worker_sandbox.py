"""Linux extraction boundary: Landlock filesystem allowlist and seccomp no-network.

The wrapper fails closed if the host cannot provide both boundaries. Restrictions
are inherited by descendants, so parser helpers cannot acquire service credentials.
"""
import ctypes
import ctypes.util
import errno
import os
import platform
import resource
import runpy
import sys
from pathlib import Path


class Ruleset(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64), ("handled_access_net", ctypes.c_uint64)]


class PortRule(ctypes.Structure):
    _fields_ = [("allowed_access", ctypes.c_uint64), ("port", ctypes.c_uint64)]


class PathRule(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


class Argument(ctypes.Structure):
    _fields_ = [("arg", ctypes.c_uint), ("op", ctypes.c_uint), ("a", ctypes.c_uint64), ("b", ctypes.c_uint64)]


def isolate(directory, *, proxy_port=None, browser=False):
    if sys.platform != "linux" or platform.machine() != "x86_64":
        raise RuntimeError("The qualified extraction sandbox requires Linux x86-64")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "no_new_privs failed")
    abi = libc.syscall(444, 0, 0, 1)
    if abi < (4 if proxy_port else 3):
        raise RuntimeError("The required Landlock ABI is unavailable")
    handled = (1 << 15)-1
    ruleset = Ruleset(handled, 3 if proxy_port else 0)
    descriptor = libc.syscall(444, ctypes.byref(ruleset), ctypes.sizeof(ruleset) if abi >= 4 else 8, 0)
    if descriptor < 0:
        raise OSError(ctypes.get_errno(), "Landlock ruleset failed")
    read_access = (1 << 0) | (1 << 2) | (1 << 3)
    try:
        if proxy_port:
            rule = PortRule(2, proxy_port)
            if libc.syscall(445, descriptor, 2, ctypes.byref(rule), 0) != 0:
                raise OSError(ctypes.get_errno(), "Landlock proxy-port rule failed")
        locations = {"/usr": read_access, "/lib": read_access, "/lib64": read_access,
                     "/bin": read_access, "/etc": read_access, "/app": read_access,
                     "/opt/mastermind/browser": read_access,
                     str(directory): handled, "/dev/null": (1 << 1) | (1 << 2),
                     "/dev/urandom": 1 << 2, "/dev/random": 1 << 2}
        if browser:
            # Chromium runs in one process; only its own proc subtree is visible.
            # The Worker/driver process memory, environment and descriptors remain hidden.
            locations["/proc/self"] = read_access
            for name in ("/proc/cpuinfo", "/proc/meminfo", "/proc/stat", "/proc/sys/fs/inotify/max_user_watches",
                         "/proc/sys/kernel/osrelease"):
                locations[name] = 1 << 2
        for name, access in locations.items():
            path = Path(name)
            if not path.exists():
                continue
            target = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = PathRule(access, target)
                if libc.syscall(445, descriptor, 1, ctypes.byref(rule), 0) != 0:
                    raise OSError(ctypes.get_errno(), "Landlock path rule failed")
            finally:
                os.close(target)
        if libc.syscall(446, descriptor, 0) != 0:
            raise OSError(ctypes.get_errno(), "Landlock restriction failed")
    finally:
        os.close(descriptor)
    library = ctypes.util.find_library("seccomp")
    if not library:
        raise RuntimeError("libseccomp is required")
    seccomp = ctypes.CDLL(library, use_errno=True)
    seccomp.seccomp_init.argtypes = [ctypes.c_uint32]
    seccomp.seccomp_init.restype = ctypes.c_void_p
    seccomp.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    seccomp.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint,
                                              ctypes.POINTER(Argument)]
    seccomp.seccomp_load.argtypes = [ctypes.c_void_p]
    seccomp.seccomp_release.argtypes = [ctypes.c_void_p]
    context = seccomp.seccomp_init(0x7FFF0000)  # allow, then deny network socket families
    if not context:
        raise RuntimeError("seccomp allocation failed")
    try:
        for name in (b"socket", b"socketpair"):
            # Git may open TCP only to the local broker's port. UDP is denied
            # independently, so DNS cannot bypass the parent broker's resolver.
            rule = Argument(1, 7, 15, 2) if proxy_port else Argument(0, 1, 1, 0)
            number = seccomp.seccomp_syscall_resolve_name(name)
            if seccomp.seccomp_rule_add_array(context, 0x00050000 | errno.EPERM, number, 1, ctypes.byref(rule)) != 0:
                raise RuntimeError("seccomp rule failed")
        for name in (b"io_uring_setup", b"io_uring_register", b"io_uring_enter", b"ptrace", b"process_vm_readv", b"process_vm_writev"):
            number = seccomp.seccomp_syscall_resolve_name(name)
            if number >= 0 and seccomp.seccomp_rule_add_array(context, 0x00050000 | errno.EPERM, number, 0, None) != 0:
                raise RuntimeError("seccomp io_uring rule failed")
        if seccomp.seccomp_load(context) != 0:
            raise RuntimeError("seccomp loading failed")
    finally:
        seccomp.seccomp_release(context)


def main():
    directory = Path(sys.argv[1]).resolve(strict=True)
    if not directory.is_dir() or directory.parent != Path("/work") or directory.is_symlink():
        raise RuntimeError("Sandbox job directory is invalid")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (1200, 1200))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8*1024**3, 8*1024**3))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_AS, (1536*1024**2, 1536*1024**2))
    # Under combined model/parser pressure, terminate the disposable parser first.
    Path("/proc/self/oom_score_adj").write_text("1000")
    os.chdir(directory)
    mode = sys.argv[2] if len(sys.argv) > 2 else "extract"
    proxy_port = int(sys.argv[3]) if mode == "git" and len(sys.argv) == 4 else None
    isolate(directory, proxy_port=proxy_port)
    if mode == "probe":
        import json
        import socket
        denied = []
        for name, action in (("network", lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM)),
                             ("service_identity", lambda: Path("/run/mastermind/worker_token").read_bytes()),
                             ("sibling_job", lambda: Path("/work/other/canary").read_bytes())):
            try:
                action()
            except PermissionError:
                denied.append(name)
        Path("probe.json").write_text(json.dumps({"denied": denied}))
    elif mode == "extract":
        sys.argv = ["extractors", str(directory / "extraction-plan.json"), str(directory / "extracted.json")]
        runpy.run_module("mastermind.extractors", run_name="__main__")
    elif mode == "git":
        sys.argv = ["worker_git", str(directory), str(proxy_port)]
        runpy.run_module("mastermind.worker_git", run_name="__main__")
    else:
        raise RuntimeError("Unsupported sandbox operation")


if __name__ == "__main__":
    try:
        main()
    except BaseException:  # noqa: BLE001 - scrub every untrusted parser/wrapper failure at the process boundary
        # Source paths, parser diagnostics and token values never enter container logs.
        print("Worker sandbox operation failed.", file=sys.stderr)
        raise SystemExit(70) from None
