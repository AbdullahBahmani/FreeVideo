"""Bounded, copyable request failures for interactive callers. No GPU imports."""
import json
from pathlib import Path
import re

from .diagnostics import Redactor


def launcher_failure(value, *, zh=False):
    """Short guidance for known failures; callers retain the full error separately."""
    if not value:
        return dict(title='', detail='', action='', kind='')
    text = str(value)[-65536:]
    rules = (
        (r'Installation RAM monitoring failed|Cannot read process-tree memory', 'memory-monitor',
         ('Memory usage could not be read', '暂时无法读取进程内存'),
         ('Download progress is saved. Check and continue to retry; copy the details if it happens again.',
          '下载进度已保留。点击“检查并继续”重试；若再次出现，请复制详情反馈。')),
        (r'No space left on device|WinError 112|disk (?:is )?full', 'disk',
         ('Not enough disk space', '磁盘空间不足'),
         ('Free up space on the installation drive, then continue.', '清理安装盘空间后，点击继续。')),
        (r'Model download paused|unexpected-transfer-size|ConnectionError|ConnectTimeout|ReadTimeout|HTTP probe failed|Could not resolve host|SSL certificate|Every download source failed|All Git sources failed|All package sources failed|Python download failed on every route', 'download',
         ('Download interrupted', '下载中断了'),
         ('Check your network or change the source or connection mode in Settings → Downloads, then retry.', '检查网络，或在“设置 → 下载”中切换下载源、连接模式后重试。')),
        (r'PermissionError|Access is denied|Permission denied|WinError 5\b', 'permission',
         ('This folder is not writable', '无法写入这个目录'),
         ('Choose an installation folder you can write to, then retry.', '选择有写入权限的安装目录后重试。')),
        (r'ModuleNotFoundError|No module named|DLL load failed', 'dependencies',
         ('The environment needs repair', '运行环境需要修复'),
         ('Return to Installation and check the same folder to restore missing dependencies.', '返回安装设置，检查当前安装目录，补齐运行依赖。')),
        (r'CUDA (?:error: )?out of memory|torch\.OutOfMemoryError|Insufficient currently available memory|crossed its RAM budget|paging file is too small|WinError 1455', 'memory',
         ('Memory is unavailable for this step', '这一步可用内存不足'),
         ('Close other memory-heavy applications and retry. Copy the details if it continues.', '关闭占用内存较多的程序后重试；仍失败时可复制详情反馈。')),
    )
    for pattern, kind, title, action in rules:
        if re.search(pattern, text, re.I):
            return dict(title=title[zh], detail='', action=action[zh], kind=kind)
    # Validation messages are already actionable. Show the cause, not a stack
    # trace or a guessed hardware diagnosis, and leave long details expandable.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    detail = next((line for line in reversed(lines) if not line.startswith(('File ', 'Traceback', '^'))), '')
    detail = re.sub(r'^(?:ValueError|RuntimeError|OSError):\s*', '', detail)
    return dict(title='暂时未能完成' if zh else 'Couldn’t complete this step',
                detail=detail[:400], action='', kind='unknown')


def _read(path, limit, *, tail=False):
    try:
        with path.open('rb') as stream:
            if tail:
                stream.seek(0, 2)
                start = max(0, stream.tell() - limit)
                stream.seek(start)
                value = stream.read(limit).decode('utf-8', errors='replace')
                return value.partition('\n')[2] if start and '\n' in value else value
            raw = stream.read(limit + 1)
            return raw.decode('utf-8', errors='replace') if len(raw) <= limit else ''
    except OSError:
        return ''


def generation_failure(run, exit_code=None):
    """Surface the cause, including a child traceback, even without a report."""
    run = Path(run)
    redactor = Redactor()
    prompt = _read(run / 'prompt.txt', 128*1024).strip()
    if prompt:
        redactor.prompts.add(prompt)
    lines = ['FreeVideo generation failed' + (' (exit %s)' % exit_code if exit_code is not None else '')]
    raw = _read(run / 'video.request.json', 512*1024)
    try:
        report = json.loads(raw)
    except (ValueError, TypeError):
        report = {}
    if not isinstance(report, dict):
        report = {}
    redactor.structured(report)  # Collect prompt values without showing the request.
    error = report.get('error_message') or report.get('error')
    if isinstance(error, str):
        lines.append(error[:8192])
    planning = report.get('resource_planning')
    encoding_failure = report.get('encoding_failure')
    phase = encoding_failure.get('phase') if isinstance(encoding_failure, dict) else None
    phase = phase or report.get('phase')
    if phase:
        lines.append('Stage: ' + str(phase))
    if isinstance(planning, list) and planning and isinstance(planning[-1], dict):
        last = planning[-1]
        if not phase:
            lines.append('Stage: ' + str(last.get('stage', 'unknown')))
        state = last.get('idle_cache') or {}
        accounting = state.get('ram_accounting', {}) if isinstance(state, dict) else {}
        if not isinstance(accounting, dict):
            accounting = {}
        for key, label in (('raw_available_bytes', 'System reported available RAM'),
                           ('credited_available_bytes', 'Available RAM including reclaimable idle cache')):
            value = accounting.get(key)
            if type(value) is int and value >= 0:
                lines.append('%s: %.2f GiB' % (label, value / 2**30))
        memory = state.get('memory') if isinstance(state, dict) else None
        if isinstance(memory, dict):
            for key, label in (('system_physical_available_bytes', 'Windows free physical RAM'),
                               ('system_commit_available_bytes', 'Windows commit headroom'),
                               ('reclaimable_mapped_bytes', 'Worker reclaimable mappings'),
                               ('guard_bytes', 'Worker private working RAM')):
                value = memory.get(key)
                if type(value) is int and value >= 0:
                    lines.append('%s: %.2f GiB' % (label, value / 2**30))
        recovery = next((r.get('recovery') for r in reversed(planning) if isinstance(r, dict) and r.get('recovery')), None)
        if recovery:
            lines.append('Idle cache release: ' + str(recovery.get('reason', recovery) if isinstance(recovery, dict) else recovery))
    # Child logs carry the actual CUDA/encoder error when the parent only knows
    # an exit code. Read bounded tails; do not read model data or entire logs.
    for name in ('generate.log', 'video.engine.log', 'video.encoding.log'):
        value = _read(run / name, 8192, tail=True)
        if not value:
            continue
        rows = [line for line in value.splitlines() if line.strip() and not line.lstrip().startswith('{"event":')]
        trace = '\n'.join(rows[-45:])
        if trace:
            lines.extend(['\n' + name + ':', trace])
    if len(lines) == 1:
        lines.append('The worker ended without a readable error report.')
    lines.append('\nRetained outputs: ' + str(run))
    value = redactor.text('\n'.join(lines))
    value = re.sub(r'\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))', '', value)
    return re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', value)


def startup_failure(message, log):
    detail = _read(Path(log), 8192, tail=True).strip()
    return Redactor().text(message + ('\n\n' + detail if detail else '\nNo readable process output was produced.') + '\n\nLog: ' + str(log))
