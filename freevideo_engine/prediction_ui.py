"""Expose forecast ranges and retain pre-request prediction errors, torch-free."""
import json
import math
import os

from .terminal_ui import TerminalUI, duration


def estimate_text(value, *, memory=False):
    if not isinstance(value, dict) or value.get('estimate') is None:
        return 'unknown'
    low, high, point = value.get('lower'), value.get('upper'), value.get('estimate')
    if (any(type(n) not in (int, float) or not math.isfinite(n) or n < 0 for n in (low, high, point))
            or not low <= point <= high):
        return 'unknown'
    return ('%.1f–%.1f GiB' % (low / 2**30, high / 2**30)) if memory else duration(low) + '–' + duration(high)


def summary(forecast, *, zh=False):
    if not isinstance(forecast, dict) or forecast.get('status') != 'estimated':
        return ('暂无匹配的完整运行历史；完成后自动学习。' if zh else
                'No matching complete history yet; this request will teach the estimator.')
    stages, resources = forecast.get('stages') or {}, forecast.get('resources') or {}
    if not isinstance(stages, dict) or not isinstance(resources, dict):
        return summary({}, zh=zh)
    total = estimate_text(stages.get('work_seconds'))
    sample = estimate_text(stages.get('sample_seconds'))
    decode = estimate_text(stages.get('decode_save_seconds'))
    vram = estimate_text(resources.get('whole_gpu_peak_bytes'), memory=True)
    ram = estimate_text(resources.get('ram_peak_bytes'), memory=True)
    preview = forecast.get('tuning_preview') or {}
    pending_input = isinstance(preview, dict) and preview.get('input_tokens_known') is False
    scope = (' · 不含文字编码' if zh else ' · excludes text encoding')
    if pending_input:
        scope += ('；提示词编码后配置可能调整' if zh else '; the profile may change after prompt encoding')
    if zh:
        return ('预计引擎 %s · 采样 %s · 解码保存 %s · 显存 %s · RAM %s · %s 条历史，可信度 %s%s' %
                (total, sample, decode, vram, ram, forecast.get('evidence_count', 0),
                 {'weak': '较低', 'moderate': '中等', 'strong': '较高'}.get(forecast.get('confidence'), '未知'),
                 '（外推）' if forecast.get('extrapolation') else '')) + scope
    return ('Engine %s · sampling %s · decode/save %s · VRAM %s · RAM %s · %s histories, %s confidence%s' %
            (total, sample, decode, vram, ram, forecast.get('evidence_count', 0), forecast.get('confidence', 'unknown'),
             ' (extrapolated)' if forecast.get('extrapolation') else '')) + scope


def show(forecast, *, stage='video'):
    if os.environ.get('FREEVIDEO_UI_EVENTS') == '1':
        print(json.dumps({'event': 'freevideo_ui', 'kind': 'prediction', 'key': 'request-prediction',
              'label': 'History forecast', 'detail': summary(forecast), 'forecast': forecast,
              'stage': stage}), flush=True)
    else:
        stages = forecast.get('stages') or {}
        TerminalUI('FreeVideo', plain=True).panel('Request forecast', [
            ('Estimate', summary(forecast)),
            ('Model load', estimate_text(stages.get('load_seconds'))),
            ('Sampling', estimate_text(stages.get('sample_seconds'))),
            ('Decode / save', estimate_text(stages.get('decode_save_seconds'))),
            ('Scope', 'Video-engine time; text encoding is separate. Ranges are estimates, not capacity guarantees.')])


def errors(forecast, observation):
    result = {'scope': 'Forecast saved before this request; actual request excluded from its own prediction.',
              'stages': {}, 'resources': {}}
    forecast = forecast if isinstance(forecast, dict) else {}
    observation = observation if isinstance(observation, dict) else {}
    for group, actuals in (('stages', observation.get('stage_seconds') or {}), ('resources', observation)):
        values = forecast.get(group) or {}
        if not isinstance(values, dict) or not isinstance(actuals, dict):
            continue
        for key, predicted in values.items():
            actual = actuals.get(key)
            if not isinstance(predicted, dict):
                continue
            expected, low, high = (predicted.get(n) for n in ('estimate', 'lower', 'upper'))
            if (any(type(n) not in (int, float) or not math.isfinite(n) or n < 0 for n in (actual, expected, low, high))
                    or not low <= expected <= high):
                continue
            result[group][key] = dict(predicted=expected, actual=actual, error=actual-expected,
                relative_error=(actual-expected)/expected if expected > 0 else None,
                within_interval=low <= actual <= high)
    return result
