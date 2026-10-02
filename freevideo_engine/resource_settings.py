"""Persistent ComfyUI resource preferences, read once for each new request."""
import json
import math
from pathlib import Path

from .monitoring import save


def validate(value):
    if value is None:
        return None  # Leave the automatic policy in charge, including tight fits.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < .2:
        raise ValueError('Reserved VRAM must be automatic or a finite number of at least 0.2 GiB')
    return float(value)


def read(root):
    path = Path(root) / 'resource-settings.json'
    if not path.exists():
        return {'gpu_reserve_gib': None}
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('Invalid resource settings')
    return {'gpu_reserve_gib': validate(value.get('gpu_reserve_gib'))}


def write(root, value):
    result = {'gpu_reserve_gib': validate(value)}
    save(Path(root) / 'resource-settings.json', result)
    return result
