"""FP8 storage with BF16/FP16 compute.

CUDA uses the original Triton W8A16 kernel.  The experimental Apple Silicon
route keeps compact FP8 weights on CPU/unified memory, dequantizes one linear
weight at a time and executes the GEMM on MPS.  This favors correctness and
bounded persistent memory over speed.
"""
import torch
import torch.nn.functional as F

_CUDA_TRITON = torch.cuda.is_available()

if _CUDA_TRITON:
    import triton
    import triton.language as tl

    from .triton_compat import activate
    activate()

    @triton.jit
    def _decode_e4m3(bits):
        bits = bits.to(tl.uint32)
        exponent = (bits >> 3) & 15
        mantissa = bits & 7
        normal = ((exponent + 120) << 23) | (mantissa << 20)
        value = tl.where(exponent == 0, mantissa.to(tl.float32) * (1. / 512.),
                         normal.to(tl.float32, bitcast=True))
        value = tl.where((bits & 128) != 0, -value, value)
        return tl.where((bits & 127) == 127, float('nan'), value)


    @triton.autotune(configs=[
        triton.Config({'BM': 32, 'BN': 64, 'BK': 32}, num_warps=4, num_stages=3),
        triton.Config({'BM': 64, 'BN': 64, 'BK': 32}, num_warps=4, num_stages=3),
        triton.Config({'BM': 32, 'BN': 128, 'BK': 32}, num_warps=4, num_stages=3),
    ], key=['M', 'N', 'K'])
    @triton.jit
    def _matmul(A, W, S, O, M: tl.constexpr, N: tl.constexpr, K: tl.constexpr,
                SA: tl.constexpr, SW: tl.constexpr, COLUMNWISE: tl.constexpr,
                BM: tl.constexpr, BN: tl.constexpr, BK: tl.constexpr):
        blocks_m, blocks_n = triton.cdiv(M, BM), triton.cdiv(N, BN)
        group = tl.program_id(0) // (8 * blocks_n)
        first_m = group * 8
        group_m = tl.minimum(blocks_m - first_m, 8)
        within = tl.program_id(0) % (8 * blocks_n)
        rows = (first_m + within % group_m) * BM + tl.arange(0, BM)
        cols = (within // group_m) * BN + tl.arange(0, BN)
        inner = tl.arange(0, BK)
        scale = tl.load(S + cols, cols < N, other=1.) if COLUMNWISE else tl.load(S)
        acc = tl.zeros((BM, BN), tl.float32)
        for begin in range(triton.cdiv(K, BK)):
            kk = begin * BK + inner
            a = tl.load(A + rows[:, None] * SA + kk[None, :],
                        (rows[:, None] < M) & (kk[None, :] < K), other=0.)
            bits = tl.load(W + cols[None, :] * SW + kk[:, None],
                           (cols[None, :] < N) & (kk[:, None] < K), other=0)
            weight = _decode_e4m3(bits) * scale
            acc += tl.dot(a, weight.to(a.dtype))
        tl.store(O + rows[:, None] * N + cols[None, :], acc,
                 (rows[:, None] < M) & (cols[None, :] < N))


def _portable_linear(value, weight_fp8, weight_scale, bias=None):
    """Dequantize one weight on CPU, then run the projection on the active device."""
    # CPU supports float8 -> float32 conversion even when the target MPS device
    # does not support float8 storage.  Do not retain this expanded copy.
    weight = weight_fp8.detach().cpu().float()
    scale = weight_scale.detach().cpu().float()
    if scale.numel() == 1:
        weight.mul_(scale.reshape(()))
    else:
        if scale.numel() != weight.shape[0]:
            raise ValueError('Expected scalar or per-output-channel weight scales')
        weight.mul_(scale.reshape(-1, 1))
    weight = weight.to(device=value.device, dtype=value.dtype)
    target_bias = None if bias is None else bias.to(device=value.device, dtype=value.dtype)
    return F.linear(value, weight, target_bias)


def linear(value, weight_fp8, weight_scale, bias=None):
    rows = value.reshape(-1, value.shape[-1]).contiguous()
    if rows.dtype not in (torch.bfloat16, torch.float16):
        raise ValueError('W8A16 expects BF16 or FP16 activations')
    if weight_fp8.dtype != torch.float8_e4m3fn or not weight_fp8.is_contiguous():
        raise ValueError('Expected contiguous E4M3 weights')
    if weight_scale.numel() not in (1, weight_fp8.shape[0]):
        raise ValueError('Expected scalar or per-output-channel weight scales')
    m, k = rows.shape
    n, weight_k = weight_fp8.shape
    if k != weight_k:
        raise ValueError('Projection input width differs from the weight')

    if rows.device.type != 'cuda' or not _CUDA_TRITON:
        result = _portable_linear(rows, weight_fp8, weight_scale, bias)
        return result.reshape(*value.shape[:-1], n)

    output = torch.empty((m, n), device=rows.device, dtype=rows.dtype)
    _matmul[lambda meta: (triton.cdiv(m, meta['BM']) * triton.cdiv(n, meta['BN']),)](
        rows, weight_fp8.view(torch.uint8), weight_scale.contiguous(), output,
        m, n, k, rows.stride(0), weight_fp8.stride(0), weight_scale.numel() != 1)
    if bias is not None:
        output.add_(bias)
    return output.reshape(*value.shape[:-1], n)


class WeightOnlyLinear(torch.nn.Module):
    @property
    def bias(self):
        return self.original.bias

    def _apply(self, fn, recurse=True):
        """On MPS keep compact float8 storage on CPU while moving small state."""
        from .device import kind
        if kind() != 'mps':
            return super()._apply(fn, recurse=recurse)
        preserved = {}
        for name in ('weight_fp8', 'weight_scale'):
            if name in self._buffers:
                preserved[name] = self._buffers.pop(name)
        try:
            return super()._apply(fn, recurse=recurse)
        finally:
            self._buffers.update(preserved)

    def project(self, value, channels):
        if self.weight_scale.numel() == 1:
            scales = self.weight_scale
        else:
            scales = self.weight_scale.reshape(-1)[channels].contiguous()
        return linear(value, self.weight_fp8[channels], scales,
                      None if self.bias is None else self.bias[channels])

    def forward(self, value):
        return linear(value, self.weight_fp8, self.weight_scale, self.bias)
