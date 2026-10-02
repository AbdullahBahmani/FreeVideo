"""Windows job launch gate; never interpret a command through a shell."""
import os
import signal
import subprocess
import sys


def main():
    from .win32 import kernel32
    from .processes import HANDLE_ENV
    lib = kernel32()
    gate = int(sys.argv[1])
    try:
        if lib.WaitForSingleObject(gate, 30000) != 0:
            raise RuntimeError('Worker was not assigned to its Windows Job Object in time')
    finally:
        lib.CloseHandle(gate)
    # The child handles cancellation and writes its reports. The host remains
    # alive while it exits; the owning controller enforces the grace timeout.
    signal.signal(signal.SIGBREAK, lambda *_: None)
    info = subprocess.STARTUPINFO()
    handle = os.environ.get(HANDLE_ENV)
    if handle:
        info.lpAttributeList = {'handle_list': [int(handle)]}
    # A GUI-launched gate may have redirected handles but no visible console.
    # Forward its streams explicitly so Popen sets STARTF_USESTDHANDLES rather
    # than depending on console/implicit handle inheritance for log capture.
    child = subprocess.Popen(sys.argv[2:], startupinfo=info, close_fds=True,
        stdin=sys.stdin if sys.stdin is not None else subprocess.DEVNULL,
        stdout=sys.stdout if sys.stdout is not None else subprocess.DEVNULL,
        stderr=sys.stderr if sys.stderr is not None else subprocess.DEVNULL)
    return child.wait()


if __name__ == '__main__':
    raise SystemExit(main())
