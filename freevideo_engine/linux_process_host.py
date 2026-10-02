"""Own an install step's descendants, including SDKs that create new sessions.

The supervisor adopts orphaned grandchildren and runs cleanup if the controller
dies. It needs no root privileges, cgroup delegation, or third-party packages.
"""
import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def children():
    return [int(pid) for pid in Path('/proc/self/task/%d/children' % os.getpid()).read_text().split()]


def cleanup():
    deadline = time.monotonic() + 1.5
    hard_deadline = deadline + 3
    terminated = set()
    while True:
        try:
            while os.waitpid(-1, os.WNOHANG)[0]:
                pass
        except ChildProcessError:
            return
        pending = children()
        if not pending:
            return
        for pid in pending:
            try:
                if time.monotonic() >= deadline:
                    os.kill(pid, signal.SIGKILL)
                elif pid not in terminated:
                    os.kill(pid, signal.SIGTERM)
                    terminated.add(pid)
            except ProcessLookupError:
                pass
        if time.monotonic() > hard_deadline:
            raise RuntimeError('Install descendants did not exit after SIGKILL; retain the lock and inspect blocked disk I/O')
        time.sleep(.05)


def main():
    parent, inherited, *command = sys.argv[1:]
    stopping = []
    for name in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(name, lambda *_: stopping.append(True))
    libc = ctypes.CDLL(None, use_errno=True)
    for option, value in ((36, 1),):  # SUBREAPER
        if libc.prctl(option, value, 0, 0, 0):
            raise OSError(ctypes.get_errno(), 'Linux install process supervision is unavailable')
    if os.getppid() != int(parent) or stopping:
        return 130  # Close the race where the controller died during startup.
    try:
        child = subprocess.Popen(command, pass_fds=tuple(int(fd) for fd in inherited.split(',') if fd))
        # PDEATHSIG follows the creating *thread*, which may return as soon as
        # ComfyUI is ready. Follow the parent process instead; reparenting on
        # its exit cannot be confused with a later reuse of the original PID.
        while child.poll() is None and not stopping:
            if os.getppid() != int(parent):
                stopping.append(True)
                break
            try:
                child.wait(timeout=.1)
            except subprocess.TimeoutExpired:
                pass
        return 130 if stopping else child.returncode if child.returncode >= 0 else 128-child.returncode
    finally:
        cleanup()


if __name__ == '__main__':
    raise SystemExit(main())
