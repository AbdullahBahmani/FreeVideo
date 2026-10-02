"""Consume complete local placements and the existing same-shape FF recovery.

The core policy remains the cold-start candidate. This helper considers at most
three existing candidates and never turns a forecast into numerical validation
or a capacity certificate. It does not allocate memory or import Torch.
"""
import copy
from collections import deque
import math

from .hardware import GiB


NEUTRAL_KEYS = frozenset(('resident_blocks', 'pin_host_gb', 'prefetch', 'stream_weights'))
HISTORY_LIMIT = 256
MINIMUM_GAIN = .02


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _tokens(canvas):
    if not isinstance(canvas, dict):
        return None
    width, height, frames = [canvas.get(name) for name in ('width', 'height', 'frames')]
    if any(type(value) is not int or value <= 0 for value in (width, height, frames)):
        return None
    if width % 32 or height % 32 or frames < 5 or (frames - 5) % 17:
        return None
    return ((frames - 5) // 17 * 5 + 2) * (width // 32) * (height // 32)


def _arithmetic(options):
    return dict({key: value for key, value in options.items() if key != 'engine'},
                engine={key: value for key, value in options['engine'].items() if key not in NEUTRAL_KEYS})


def _patch(options):
    engine = options['engine']
    resident, pin, prefetch = [engine.get(key) for key in ('resident_blocks', 'pin_host_gb', 'prefetch')]
    streamed = engine.get('stream_weights', False)
    if (type(resident) is not int or not 0 <= resident <= 50 or not _number(pin)
            or type(prefetch) is not bool or type(streamed) is not bool):
        return None
    return dict(resident_blocks=resident, pin_host_gb=pin, prefetch=prefetch, stream_weights=streamed)


def _same_request_recompute(current, observed, canvas, measured, text_tokens, observation):
    """Reuse only the already shipped FF recovery on a complete matching input shape.

    Success at a different chunk/backend/decoder is not numerical validation.
    Do not extrapolate a recompute recovery to unknown text or reference shapes.
    """
    engine = current['engine']
    if (engine.get('fp8_ff_recompute', False) is not False
            or observed['engine'].get('fp8_ff_recompute') is not True
            or engine.get('inference_kernels') is not True
            or engine.get('linear_compute', 'native-fp8') != 'native-fp8'
            or type(engine.get('ff_chunk')) is not int or engine['ff_chunk'] <= 0):
        return False
    if (type(text_tokens) is not int or text_tokens <= 0
            or observation.get('text_tokens') != text_tokens
            or any(canvas.get(key, 0) != measured.get(key, 0) for key in
                   ('width', 'height', 'frames', 'fps', 'reference_video_tokens', 'reference_audio_tokens'))):
        return False
    expected = copy.deepcopy(_arithmetic(current))
    expected['engine']['fp8_ff_recompute'] = True
    return _arithmetic(observed) == expected


def _resource(forecast, name, statistic):
    value = forecast.get('resources', {}).get(name, {}).get(statistic)
    return value if _number(value) and value > 0 else None


def _seconds(forecast):
    stages = forecast.get('stages', {})
    sample = stages.get('sample_seconds', {}).get('estimate')
    if not _number(sample) or sample <= 0:
        return None
    return sample


def _work_seconds(forecast, canvas):
    value = forecast.get('stages', {}).get('work_seconds', {})
    numbers = [value.get(key) for key in ('lower', 'estimate', 'upper')]
    if (not all(_number(number) for number in numbers) or not 0 <= numbers[0] <= numbers[1] <= numbers[2]
            or numbers[1] <= 0):
        return None
    context = forecast.get('geometry', {})
    if not isinstance(context, dict) or any(context.get(key) != canvas[key] for key in ('width', 'height', 'frames')):
        return None
    return numbers[1]


def _work_context(forecast):
    context = forecast.get('execution_context')
    if not isinstance(context, dict):
        return None, False
    known = ('cold', 'warm', 'partial')
    matched = forecast.get('stages', {}).get('work_seconds', {}).get('cache_context_matched') is True
    if matched and context.get('adaln_cache_state') in known:
        return context['adaln_cache_state'], True
    counts = context.get('observed_cache_regimes', {})
    states = ([state for state, count in counts.items() if _number(count) and count > 0]
              if isinstance(counts, dict) else [])
    if len(states) == 1 and states[0] in known:
        return states[0], False
    return None, False


def _work_threads(forecast):
    context = forecast.get('execution_context')
    values = context.get('observed_host_threads') if isinstance(context, dict) else None
    if values is None or values == [] or values == [None]:
        return 'unknown', None
    if isinstance(values, list) and len(values) == 1 and isinstance(values[0], dict) and values[0]:
        return 'measured', values[0]
    return 'mixed', None


def select(base, canvas, hardware, history_rows, identity, *, reject=None, text_tokens=None,
           execution_context=None):
    """Return ``(profile, decision)`` from at most three complete local candidates.

    ``reject(profile)`` supplies an optional caller resource constraint.
    Live memory remains part of placement selection. Only a local complete
    observation supplies a candidate. The existing FF-recompute recovery may
    be reused for an identical input shape; it is labeled separately from
    neutral placement. No new head/window/chunk size or backend is applied.
    """
    from .prediction import predict, profile_options
    rows = list(deque(history_rows if history_rows is not None else (), maxlen=HISTORY_LIMIT))
    current = profile_options(base)
    arithmetic = _arithmetic(current)
    target_tokens = _tokens(canvas)
    if not target_tokens:
        raise ValueError('Prediction policy needs the original aligned H3 geometry')
    candidates = [{'profile': copy.deepcopy(base), 'origin': 'current-policy', 'source_attempt': None}]
    eligible = []
    seen = set()
    from .two_pass import same_strategy, steps as sampling_steps
    total_steps = sampling_steps(canvas.get('sampling_plan'))
    for row in reversed(rows):
        if (not isinstance(row, dict) or row.get('identity') != identity
                or row.get('outcome', row.get('state')) != 'success'
                or row.get('purpose') not in ('generation', 'validation', 'full_request')):
            continue
        observation = row.get('observation')
        if (not isinstance(observation, dict) or observation.get('full_request') is not True
                or observation.get('validated') is not True or type(observation.get('completed_steps')) is not int
                or observation['completed_steps'] != total_steps
                or observation.get('media_verified') is not True or observation.get('metrics_complete') is not True):
            continue
        times = observation.get('step_seconds')
        if not isinstance(times, list) or len(times) != total_steps or any(not _number(value) or value <= 0 for value in times):
            continue
        measured_canvas = observation.get('geometry', row.get('geometry', {}))
        if not same_strategy(measured_canvas, canvas):
            continue
        count = _tokens(measured_canvas)
        if not count or observation.get('completed_frames') != measured_canvas.get('frames'):
            continue
        original_canvas = row.get('geometry', {})
        if (not isinstance(original_canvas, dict) or any(original_canvas.get(key) != measured_canvas.get(key)
                for key in ('width', 'height', 'frames'))):
            continue
        try:
            options = profile_options(row.get('config', {}))
            patch = _patch(options)
            if patch is None:
                continue
            recovery = _same_request_recompute(current, options, canvas, original_canvas, text_tokens, observation)
            if _arithmetic(options) != arithmetic and not recovery:
                continue
            if recovery:
                patch['fp8_ff_recompute'] = True
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        marker = tuple(sorted(patch.items()))
        if marker in seen:
            continue
        stages = observation.get('stage_seconds')
        if not isinstance(stages, dict):
            continue
        sample = stages.get('sample_seconds')
        peak = observation.get('peak_reserved_bytes')
        if not _number(sample) or sample <= 0 or not _number(peak) or peak <= 0:
            continue
        seen.add(marker)
        selected = copy.deepcopy(base)
        selected['engine'].update(patch)
        if isinstance(selected.get('policy'), dict):
            selected['policy']['engine'] = copy.deepcopy(selected['engine'])
        # Distance chooses relevant historical candidates, not a memory/speed
        # model. The independent forecaster evaluates their requested geometry.
        distance = (abs(math.log(count / target_tokens)) +
                    abs(math.log(measured_canvas['width'] / canvas['width'])) +
                    abs(math.log(measured_canvas['height'] / canvas['height'])))
        work = stages.get('work_seconds')
        eligible.append(dict(profile=selected, origin='complete-local-ff-recovery' if recovery else 'complete-local-placement', source_attempt=row.get('id'),
                             distance=distance, sample_rate=sample / count,
                             work_rate=work / count if _number(work) and work > 0 else None, peak=peak))
    fastest_sample = sorted(eligible, key=lambda item: (item['distance'], item['sample_rate']))
    fastest_work = sorted((item for item in eligible if item['work_rate'] is not None),
                          key=lambda item: (item['distance'], item['work_rate']))
    lightest = sorted(eligible, key=lambda item: (item['distance'], item['peak']))
    # Useful placement beats occupancy: never synthesize additional residency
    # from free bytes alone. Both increases and decreases may win if measured.
    for item in fastest_work[:1] + fastest_sample[:1] + lightest[:1] + fastest_work[1:] + fastest_sample[1:]:
        if any(profile_options(item['profile']) == profile_options(existing['profile']) for existing in candidates):
            continue
        candidates.append(item)
        if len(candidates) == 3:
            break
    observed = hardware.to_dict() if hasattr(hardware, 'to_dict') else hardware
    policy = base.get('policy', {})
    desktop = observed.get('system') == 'Windows'
    gpu_reserve = policy.get('gpu_system_reserve_bytes', (1 if desktop else .5) * GiB)
    ram_reserve = policy.get('ram_system_reserve_bytes', (2 if desktop else 1) * GiB)
    gpu_limit = max(0, min(base['gpu_budget_gb'] * 1e9, observed['vram_free'] - gpu_reserve))
    if current.get('benchmark_allocator_limit_bytes') is not None:
        gpu_limit = min(gpu_limit, current['benchmark_allocator_limit_bytes'])
    ram_limit = max(0, min(base['inference_ram_budget_gb'] * 1e9, observed['ram_available'] - ram_reserve))
    # Live memory below the budget the plan was built against is the one case
    # where an unmeasured placement is genuinely suspect: the arithmetic behind
    # it no longer holds. A byte of slack absorbs the GB float round trip.
    live_shortfall = (gpu_limit + 1 < base['gpu_budget_gb'] * 1e9
                      or ram_limit + 1 < base['inference_ram_budget_gb'] * 1e9)
    evaluated = []
    for candidate in candidates:
        profile = candidate['profile']
        blocked = reject(profile) if reject is not None else None
        forecast = predict(rows, identity, profile, canvas, text_tokens=text_tokens, execution_context=execution_context)
        gpu_point = _resource(forecast, 'peak_reserved_bytes', 'estimate')
        ram_point = _resource(forecast, 'ram_peak_bytes', 'estimate')
        gpu_upper = _resource(forecast, 'peak_reserved_bytes', 'upper')
        ram_upper = _resource(forecast, 'ram_peak_bytes', 'upper')
        fits = (not blocked and forecast.get('status') == 'estimated' and gpu_point is not None
                and ram_point is not None and gpu_point <= gpu_limit and ram_point <= ram_limit)
        interval_fits = (fits and gpu_upper is not None and ram_upper is not None
                         and gpu_upper <= gpu_limit and ram_upper <= ram_limit)
        # "No local measurement" is not "will not fit". The forecaster reports
        # 'unknown' when this machine has no evidence for a placement, so a
        # placement it has never run can never be shown to fit. Only a caller
        # blocker, a forecast built on evidence, or live memory below what the
        # plan was budgeted against is evidence against a candidate.
        unmeasured = not blocked and forecast.get('status') != 'estimated'
        over_live_budget = bool(blocked) or (not fits and not unmeasured) or (unmeasured and live_shortfall)
        cache_state, cache_matched = _work_context(forecast)
        thread_state, threads = _work_threads(forecast)
        evaluated.append(dict(profile=profile, origin=candidate['origin'], source_attempt=candidate['source_attempt'],
            prediction=forecast, sampling_seconds=_seconds(forecast), work_seconds=_work_seconds(forecast, canvas),
            work_cache_state=cache_state, work_cache_context_matched=cache_matched,
            work_host_thread_state=thread_state, work_host_threads=threads,
            point_within_live_budget=bool(fits),
            interval_within_live_budget=bool(interval_fits),
            forecast_unmeasured=bool(unmeasured),
            forecast_over_live_budget=bool(over_live_budget),
            resource_estimate=dict(gpu_bytes=gpu_point, ram_bytes=ram_point),
            resource_upper=dict(gpu_bytes=gpu_upper, ram_bytes=ram_upper),
            rejected_reason=str(blocked) if blocked else None,
            reason='Neutral placement admission uses the point estimate; interval crossings remain uncertainty, not extra reserved memory'))
    baseline = evaluated[0]
    feasible = [item for item in evaluated if item['point_within_live_budget']]
    chosen = baseline
    reason = 'Keep current policy: no supported faster compatible placement forecast fits current memory'
    work_options = [item for item in feasible if item['work_seconds'] is not None and baseline['work_cache_state'] is not None
                    and item['work_cache_state'] == baseline['work_cache_state']
                    and baseline['work_host_thread_state'] != 'mixed'
                    and item['work_host_thread_state'] == baseline['work_host_thread_state']
                    and item['work_host_threads'] == baseline['work_host_threads']]
    sample_options = [item for item in feasible if item['sampling_seconds'] is not None]
    has_work_comparison = bool(work_options) and (len(evaluated) == 1 or any(item is not baseline for item in work_options))
    objective = 'work_seconds' if baseline['work_seconds'] is not None and has_work_comparison else 'sample_seconds'
    ranking = work_options if objective == 'work_seconds' else sample_options
    key = 'work_seconds' if objective == 'work_seconds' else 'sampling_seconds'
    objective_reason = ('Full video-engine load, sampling and decode time; valid forecast intervals, assuming the same observed %s cache regime.' % baseline['work_cache_state']
        if objective == 'work_seconds' else 'Sampling-only fallback: a matching full-work forecast is unavailable; no full-request gain is claimed.')
    if objective == 'work_seconds':
        objective_reason += (' Host thread settings match the measured history.' if baseline['work_host_thread_state'] == 'measured'
                             else ' Host thread settings were not recorded; this remains an unverified performance assumption.')
    if ranking:
        fastest = min(ranking, key=lambda item: item[key])
        if baseline['forecast_over_live_budget']:
            # Memory recovery is a different objective from paying sampling
            # time for a hoped-for load saving. A fitting placement may be
            # slower than the predicted-over-budget baseline; report that trade.
            chosen = fastest
            reason = 'Use a completed local neutral placement whose resource estimate fits the current request and live memory; this is not a claimed speedup over an over-budget or unmeasured baseline'
        elif baseline['forecast_unmeasured']:
            # Ranking needs both sides measured. Swapping in history here would
            # freeze whichever placement this machine completed first: the new
            # plan stays unmeasured, so it loses this comparison every time,
            # and a grown budget keeps spending a smaller budget's placement.
            # The same-shape FF recovery is the exception: it is a memory
            # recovery this machine already needed for this exact request, and
            # reusing it avoids rediscovering it through an OOM.
            recovery = next((item for item in ranking if item['origin'] == 'complete-local-ff-recovery'), None)
            if recovery is not None:
                chosen = recovery
            else:
                reason = ('Keep current policy: its placement has no local measurement to forecast, '
                          'and live memory still covers the budget it was planned against')
        elif baseline[key] is None:
            chosen = fastest
            reason = 'Use a completed local neutral placement whose resource estimate fits the current request and live memory; this is not a claimed speedup over an over-budget or unmeasured baseline'
        elif fastest[key] < baseline[key] * (1 - MINIMUM_GAIN):
            chosen = fastest
            reason = 'Use the faster predicted local placement; %s improvement exceeds the 2%% switch threshold' % objective
        else:
            reason = 'Keep current placement: %s improvement is below 2%%; occupying more memory is not a benefit' % objective
    result = copy.deepcopy(chosen['profile'])
    reused_recompute = chosen['origin'] == 'complete-local-ff-recovery'
    if reused_recompute:
        reason = ('Reuse the completed local FF-recompute recovery for the same request shape and text length; '
                  'its measured resource forecast fits live budgets. Avoid rediscovering this recovery through OOM; '
                  'this is the existing same-shape recovery path, not a new numerical-equivalence certificate.')
    decision = dict(changed=profile_options(result) != profile_options(base), reason=reason,
                    source_attempt=chosen['source_attempt'], prediction=chosen['prediction'],
                    candidates=evaluated, history_rows_considered=len(rows),
                    objective=objective, objective_reason=objective_reason,
                    limits=dict(gpu_bytes=gpu_limit, ram_bytes=ram_limit),
                    upper_bound_crosses_budget=(None if any(value is None for value in chosen['resource_upper'].values())
                        else chosen['resource_upper']['gpu_bytes'] > gpu_limit or chosen['resource_upper']['ram_bytes'] > ram_limit),
                    recovery='Resource guards and fresh-worker placement recovery remain required; an interval is not a guarantee.',
                    numerical_class='same-shape-ff-recompute' if reused_recompute else 'placement-only', capacity_certified=False,
                    scope=('Existing same-shape FF recovery and original request. Historical predictions remain bounded by live resources.'
                           if reused_recompute else 'Same arithmetic and original request. Historical predictions remain bounded by live resources.'))
    return result, decision
