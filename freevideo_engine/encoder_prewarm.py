"""Idle, interruptible encoder file-cache prefetch for interactive sessions.

The native encoder maps its checkpoint. Reading it while idle warms the same OS
pages without keeping another Torch process, private model copy or CUDA context.
The OS can reclaim all warmed pages. This is not GPU model residency.
"""
import os
from pathlib import Path
import threading
import time

from .hardware import cgroup_memory
from .monitoring import save
from .system import system_memory

GiB = 1 << 30
CHUNK = 8 * 1024 * 1024


def plan(size, available, *, ram_budget=None, complete=True):
    reserve = 2 * GiB
    limit = max(0, available - reserve)
    if ram_budget is not None:
        limit = min(limit, max(0, int(ram_budget)))
    return dict(enabled=bool(complete and size > 0 and size <= limit), bytes=size,
                memory_allowance_bytes=limit, system_reserve_bytes=reserve,
                scope='Reclaimable OS file cache; no private model copy or GPU allocation',
                reason=('Idle RAM covers the checkpoint plus system headroom' if complete and 0 < size <= limit
                        else 'Leave memory for active applications; encoder loads on demand'))


def available_memory():
    memory = system_memory()
    group = cgroup_memory()
    available = memory['available_bytes']
    if group.get('available_bytes') is not None:
        # Use actual remaining cgroup capacity, not host RAM or an assumption
        # that the kernel will reclaim other applications' pages in time.
        available = min(available, group['available_bytes'])
    return available, group.get('complete', True)


def prefetch(path, selected, cancelled, *, busy=None, notify=None, availability=available_memory):
    path = Path(path)
    result = dict(selected, state='skipped', done_bytes=0)
    started = time.monotonic()
    if not selected['enabled']:
        return result
    initial = path.stat()
    result['state'] = 'reading'
    buffer = bytearray(CHUNK)
    last = 0.
    with path.open('rb', buffering=0) as stream:
        while result['done_bytes'] < selected['bytes']:
            if cancelled.is_set() or busy and busy():
                result.update(state='cancelled', reason='A new request takes priority')
                break
            available, complete = availability()
            if not complete or available < selected['system_reserve_bytes'] + CHUNK:
                result.update(state='released', reason='Live RAM pressure; warmed pages remain reclaimable')
                break
            count = stream.readinto(buffer)
            if not count:
                raise ValueError('Encoder checkpoint changed during prefetch')
            result['done_bytes'] += count
            elapsed = time.monotonic() - started
            result.update(elapsed_seconds=elapsed, bytes_per_second=result['done_bytes'] / max(.001, elapsed))
            if notify and elapsed - last >= 1:
                notify(dict(result))
                last = elapsed
        else:
            current = path.stat()
            if (current.st_size, current.st_mtime_ns) != (initial.st_size, initial.st_mtime_ns):
                raise ValueError('Encoder checkpoint changed during prefetch')
            result.update(state='ready', reason='Checkpoint pages read; native loader can reuse them if still cached')
    result['elapsed_seconds'] = time.monotonic() - started
    return result


class IdlePrewarmer:
    def __init__(self):
        self.thread = None
        self.cancelled = threading.Event()
        self.guard = threading.Lock()
        self.report = None

    def stop(self):
        self.cancelled.set()
        thread = self.thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=1.)
        from .encoder_diagnostics import prewarm_receipt
        return prewarm_receipt(self.report, gpu=False)

    def schedule(self, path, report, *, ram_budget=None, busy=None, notify=None):
        with self.guard:
            self.stop()
            if self.thread and self.thread.is_alive():
                return False  # At most one bounded read, even on a stalled disk.
            self.cancelled = threading.Event()
            self.report = Path(report)
            cancel = self.cancelled
            def work():
                result = {'state': 'cancelled', 'reason': 'A new request takes priority'}
                try:
                    # Return the completed video to the user before doing work.
                    if cancel.wait(2.) or busy and busy():
                        return
                    available, complete = available_memory()
                    selected = plan(Path(path).stat().st_size, available, ram_budget=ram_budget, complete=complete)
                    if os.environ.get('FREEVIDEO_ENCODER_PREWARM', 'auto').lower() in ('0', 'off', 'false'):
                        selected.update(enabled=False, reason='Disabled by FREEVIDEO_ENCODER_PREWARM')
                    result = prefetch(path, selected, cancel, busy=busy, notify=notify)
                except Exception as error:
                    result = {'state': 'failed', 'reason': str(error)}
                finally:
                    try:
                        save(report, dict(result, checkpoint=str(path), completed_epoch=time.time()))
                        if notify:
                            notify(result)
                    except (OSError, RuntimeError):
                        pass  # Optional idle preparation cannot fail a saved video.
            self.thread = threading.Thread(target=work, name='FreeVideo encoder prefetch', daemon=True)
            self.thread.start()
            return True


IDLE = IdlePrewarmer()
