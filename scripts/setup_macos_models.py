#!/usr/bin/env python3
"""Download the pinned compact model bundle and common H3 assets for macOS MPS."""
from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--workers", type=int, default=1, choices=(1, 2))
    args = parser.parse_args()

    if platform.system() != "Darwin" or platform.machine().lower() not in ("arm64", "aarch64"):
        raise SystemExit("Apple Silicon macOS is required.")

    import torch
    if not torch.backends.mps.is_available():
        raise SystemExit("PyTorch MPS is unavailable; run scripts/check_macos.py first.")

    root = args.root.expanduser().resolve()
    model_dir = root / "models"
    encoder_dir = model_dir / "encoder"

    from freevideo_engine import prepared_model
    from freevideo_engine.provision import models, prepare

    # (0, 0) intentionally selects the rowwise compact FP8 variant.  The MPS
    # backend does not execute FP8 kernels; it uses these bytes only as compact
    # storage and expands each projection for BF16/FP16 compute.
    prepared = prepared_model.select((0, 0), root)
    if prepared is None:
        raise SystemExit("No rowwise prepared model is pinned by this FreeVideo revision.")

    plan = {
        "root": str(root),
        "model_dir": str(model_dir),
        "encoder_dir": str(encoder_dir),
        "prepared_model": prepared,
        "reuse_cache": None,
        "verification": "auto",
        "network": {},
        "model_transfer": {"file_workers": args.workers},
        "disk_mode": "standard",
        "local_models": None,
        "inventory": {
            "hardware": {
                "capability": [0, 0],
                "system": "Darwin",
            }
        },
    }

    models(plan)
    receipt = root / ".freevideo" / "macos-prepared.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    prepare(plan, receipt)

    result = {
        "success": True,
        "cache": prepared["cache"],
        "base": str(model_dir / "h3-base"),
        "checkpoint": str(model_dir / "stage-dmd-step-250"),
        "encoder_models": str(encoder_dir),
        "receipt": str(receipt),
    }
    (root / ".freevideo" / "macos-paths.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
