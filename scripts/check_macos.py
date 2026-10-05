#!/usr/bin/env python3
"""Small Apple Silicon/MPS smoke test; downloads no models."""
from __future__ import annotations

import json
import platform
import sys


def main():
    if platform.system() != "Darwin" or platform.machine().lower() not in ("arm64", "aarch64"):
        raise SystemExit("This check is for Apple Silicon macOS (arm64).")

    import torch
    if not torch.backends.mps.is_built():
        raise SystemExit("This PyTorch wheel was not built with MPS support.")
    if not torch.backends.mps.is_available():
        raise SystemExit("MPS is unavailable. Update macOS/PyTorch and run natively, not under Rosetta.")

    from freevideo_engine.device import device_name, mem_get_info, synchronize
    from freevideo_engine.attention import WindowAttention

    dev = torch.device("mps")
    a = torch.randn((256, 256), device=dev, dtype=torch.float16)
    b = torch.randn((256, 256), device=dev, dtype=torch.float16)
    c = a @ b
    synchronize(dev)
    if not bool(torch.isfinite(c).all()):
        raise SystemExit("MPS matrix multiplication produced non-finite values.")

    # Exercise the exact generic SDPA path used by the experimental backend.
    attn = WindowAttention("torch-sdpa")
    q = torch.randn((128, 4, 64), device=dev, dtype=torch.float16)
    out = attn.dense(q, q, q, 64 ** -0.5)
    synchronize(dev)
    if out.shape != q.shape or not bool(torch.isfinite(out).all()):
        raise SystemExit("MPS scaled-dot-product attention smoke test failed.")

    free, total = mem_get_info()
    print(json.dumps({
        "success": True,
        "backend": "mps",
        "device": device_name(),
        "torch": str(torch.__version__),
        "macos": platform.mac_ver()[0],
        "recommended_device_memory_gib": round(total / 2**30, 2),
        "currently_available_gib": round(free / 2**30, 2),
    }, indent=2))


if __name__ == "__main__":
    main()
