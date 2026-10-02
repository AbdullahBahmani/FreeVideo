"""Retain overall stages and concurrent transfer progress independently of logs."""
import math
import time

from .terminal_ui import duration


def number(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value >= 0)


class ProgressState:
    def __init__(self):
        self.phase = {}
        self.tasks = {}
        self.last = {}
        self.model_groups = []

    def update(self, event, now=None):
        now = time.monotonic() if now is None else now
        event = dict(event)
        if event.get('kind') == 'models':
            self.model_groups = event.get('groups', [])
            return
        if event.get('kind') == 'phase':
            self.phase = event
            return
        key = str(event.get('key', 'current'))
        if event.get('kind') == 'task':
            self.tasks.pop(key, None)
        previous = self.tasks.get(key, {})
        state = event.get('state', 'running')
        self.tasks[key] = dict(previous, **event, observed_at=now)
        self.tasks[key]['state'] = state
        self.last = self.tasks[key]
        # Completed events need not grow with the number of downloaded files.
        for name in list(self.tasks):
            if len(self.tasks) <= 32:
                break
            if self.tasks[name].get('state') != 'running':
                self.tasks.pop(name)

    def snapshot(self, now=None):
        now = time.monotonic() if now is None else now
        active = [self._view(row, now) for row in self.tasks.values() if row.get('state') == 'running']
        # Keep a download visible while a parallel compiler reports a heartbeat.
        active.sort(key=lambda row: (number(row.get('total')) and row['total'] > 0,
                                     row.get('unit') == 'bytes'), reverse=True)
        current = active[0] if active else self._view(self.last, now)
        return dict(phase_progress=dict(self.phase), active_tasks=active, progress=current, model_groups=self.model_groups)

    @staticmethod
    def _view(row, now):
        value = dict(row)
        age = max(0., now - value.pop('observed_at', now))
        total, done = value.get('total'), value.get('done')
        valid = number(total) and total > 0 and number(done) and done <= total
        value['fraction'] = done / total if valid else None
        remaining = value.get('remaining_seconds')
        if not valid or age > 10 or not number(remaining):
            value['remaining_seconds'] = None
        value['age_seconds'] = age
        return value


def progress_text(event, zh=False):
    """A truthful count/ETA for the current file or operation, never stage averages."""
    t = lambda en, cn: cn if zh else en
    total, done = event.get('total'), event.get('done')
    valid = number(total) and total > 0 and number(done) and done <= total
    parts = []
    if valid:
        parts.append('%.0f%%' % (100 * done / total))
        if event.get('unit') == 'bytes':
            unit, size = ('GiB', 2**30) if total >= 2**30 else ('MiB', 2**20)
            parts.append('%.1f / %.1f %s' % (done / size, total / size, unit))
        else:
            parts.append('%d / %d' % (done, total))
    elif event.get('state') == 'complete':
        parts.append(t('Complete', '已完成'))
    else:
        parts.append(t('Measuring progress…', '正在获取进度…'))
    remaining = event.get('remaining_seconds')
    if valid and number(remaining) and remaining > 0:
        parts.append(t('File ETA ~', '本文件预计剩余约 ') if event.get('unit') == 'bytes' else t('ETA ~', '预计剩余约 '))
        parts[-1] += duration(math.ceil(remaining))
    return ' · '.join(parts)
