"""Cross-platform accelerator helpers.

CUDA remains the production backend.  Apple Silicon uses PyTorch MPS in the
experimental macOS port.  Keep platform-specific calls in this module so the
inference code does not need to pretend that MPS is CUDA.
"""
from __future__ import annotations

from contextlib import nullcontext
import platform

import torch


def kind() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def device() -> torch.device:
    selected = kind()
    if selected == "cpu":
        raise RuntimeError(
            "FreeVideo requires an accelerator. NVIDIA CUDA and Apple Silicon MPS are supported."
        )
    return torch.device(selected)


def is_cuda(value=None) -> bool:
    return (torch.device(value).type if value is not None else kind()) == "cuda"


def is_mps(value=None) -> bool:
    return (torch.device(value).type if value is not None else kind()) == "mps"


def synchronize(value=None) -> None:
    selected = torch.device(value).type if value is not None else kind()
    if selected == "cuda":
        torch.cuda.synchronize(value)
    elif selected == "mps":
        torch.mps.synchronize()


def empty_cache() -> None:
    selected = kind()
    if selected == "cuda":
        torch.cuda.empty_cache()
    elif selected == "mps":
        torch.mps.empty_cache()


def memory_allocated() -> int:
    if kind() == "cuda":
        return int(torch.cuda.memory_allocated())
    if kind() == "mps":
        return int(torch.mps.current_allocated_memory())
    return 0


def memory_reserved() -> int:
    if kind() == "cuda":
        return int(torch.cuda.memory_reserved())
    if kind() == "mps":
        # MPS reports driver allocations instead of a CUDA-style caching pool.
        return int(torch.mps.driver_allocated_memory())
    return 0


def max_memory_allocated() -> int:
    if kind() == "cuda":
        return int(torch.cuda.max_memory_allocated())
    return memory_allocated()


def max_memory_reserved() -> int:
    if kind() == "cuda":
        return int(torch.cuda.max_memory_reserved())
    return memory_reserved()


def reset_peak_memory_stats() -> None:
    if kind() == "cuda":
        torch.cuda.reset_peak_memory_stats()


def mem_get_info() -> tuple[int, int]:
    if kind() == "cuda":
        free, total = torch.cuda.mem_get_info()
        return int(free), int(total)
    if kind() == "mps":
        from .system import system_memory
        memory = system_memory()
        recommended = getattr(torch.mps, "recommended_max_memory", None)
        total = int(recommended()) if recommended is not None else int(memory["total_bytes"] * 0.7)
        used = int(torch.mps.driver_allocated_memory())
        # MPS and CPU share physical memory.  Never report more GPU headroom
        # than the OS says is currently available.
        free = min(max(0, total - used), int(memory["available_bytes"]))
        return free, total
    return 0, 0


def device_name() -> str:
    if kind() == "cuda":
        return torch.cuda.get_device_name()
    if kind() == "mps":
        try:
            import subprocess
            return subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
            ).strip() or "Apple Silicon"
        except (OSError, subprocess.SubprocessError):
            return platform.processor() or "Apple Silicon"
    return platform.processor() or "CPU"


def autocast(dtype=torch.float16, *, enabled=True):
    selected = kind()
    if not enabled:
        return nullcontext()
    if selected == "cuda":
        return torch.autocast(device_type="cuda", dtype=dtype)
    if selected == "mps":
        # MPS autocast support changes across PyTorch releases.  FP16 is the
        # conservative path; if a wheel rejects it, execute in the tensor dtype.
        try:
            return torch.autocast(device_type="mps", dtype=dtype)
        except (RuntimeError, TypeError):
            return nullcontext()
    return nullcontext()
