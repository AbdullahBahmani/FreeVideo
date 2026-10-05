"""Import-time compatibility shims for VDN on Apple Silicon.

Pinned VDN imports two Triton-only modules at module import time even when their
optimized functions are disabled.  The MPS policy uses eager PyTorch paths, so
provide only the symbols those modules import.  Any accidental attempt to execute
a CUDA/Triton-only function fails loudly.
"""
from __future__ import annotations

import sys
import types

import torch
from torch import nn


def _unsupported(name):
    def fail(*args, **kwargs):
        raise RuntimeError(f"{name} is a CUDA/Triton-only VDN path and is disabled on Apple Silicon MPS")
    return fail


def install():
    if "src.models.ops.fp8_linear" not in sys.modules:
        fp8 = types.ModuleType("src.models.ops.fp8_linear")
        class Fp8Linear(nn.Module):
            pass
        fp8.Fp8Linear = Fp8Linear
        fp8.FP8_DTYPE = torch.float8_e4m3fn
        fp8.MIN_WIDTH = 4096
        fp8.SKIP_END_BLOCKS = 4
        fp8.per_tensor_gemm = lambda: False
        fp8.quantize_activation = _unsupported("VDN FP8 activation quantization")
        fp8.swiglu_quantize_activation = _unsupported("VDN FP8 SwiGLU quantization")
        fp8.convert_linear_to_fp8 = _unsupported("VDN FP8 conversion")
        fp8.revert_fp8 = lambda handle: 0
        sys.modules[fp8.__name__] = fp8

    if "src.models.ops.temporal_conv" not in sys.modules:
        temporal = types.ModuleType("src.models.ops.temporal_conv")
        temporal.temporal_conv_activate = _unsupported("VDN Triton temporal convolution")
        sys.modules[temporal.__name__] = temporal
