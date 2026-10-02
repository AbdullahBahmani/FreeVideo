"""Short, isolated consumer-GPU compatibility checks for doctor --probe."""
import json
import math
import sys
import platform
import traceback
import torch
from .locking import runtime_lock


@torch.no_grad()
def main():
    backend = sys.argv[1]
    torch.set_num_threads(4)
    torch.manual_seed(171)
    with runtime_lock():
        if backend == 'linear':
            from .paths import add_vdn
            add_vdn()
            from src.models.ops.fp8_linear import quantize_activation, per_tensor_gemm
            from .fp8_gemm import scaled_mm
            from .kernel_capabilities import fp8_implementation
            # Wide output and a tail tile exercise the bounded compatibility
            # epilogue on the user's real GPU without loading any model.
            x = torch.randn(701, 512, device='cuda', dtype=torch.bfloat16)
            weight = torch.randn(12288, 512, device='cuda', dtype=torch.bfloat16)
            shapes = {'activation': list(x.shape), 'weight': list(weight.shape), 'output_dtype': str(x.dtype)}
            if torch.cuda.get_device_capability() < (8, 9):
                from .weight_only import linear
                scale = weight.float().abs().amax().reshape(1, 1) / 448.
                fp8 = (weight.float() / scale).to(torch.float8_e4m3fn)
                value = linear(x, fp8, scale)
                policy = 'bf16-weight-only'
            else:
                scale = (weight.float().abs().amax() if per_tensor_gemm() else weight.float().abs().amax(1)).reshape(1, -1) / 448.
                fp8 = (weight.float() / scale.reshape(-1, 1)).to(torch.float8_e4m3fn)
                xq, xs = quantize_activation(x)
                implementation = fp8_implementation(platform.system(), 'per_tensor' if per_tensor_gemm() else 'rowwise')
                value = scaled_mm(xq, fp8.t(), xs, scale, out_dtype=x.dtype, implementation=implementation)
                policy = 'native-fp8-per-tensor' if per_tensor_gemm() else 'native-fp8-rowwise'
                policy += '/' + implementation
            # Small dequantized reference only; no model weights are loaded.
            reference_x = x.float() if torch.cuda.get_device_capability() < (8, 9) else xq.float() * xs
            reference = reference_x @ (fp8.float() * scale.reshape(-1, 1)).t()
            tolerance = .01
        else:
            if backend == 'torch-flash' and not torch.backends.cuda.is_flash_attention_available():
                raise RuntimeError('This PyTorch wheel was built without CUDA Flash Attention. '
                                   'Automatic selection can use cuDNN or Sage2 if their probes pass.')
            from .attention import WindowAttention
            from src.models.sequence_layout import SequenceLayout
            from src.models.softmax_attention.window import window_bounds, window_softmax_reference
            layout = SequenceLayout(seq_len=487, video_start=3, num_frames=15, tokens_per_frame=32)
            q, k, v = [torch.randn(487, 4, 128, device='cuda', dtype=torch.bfloat16) for _ in range(3)]
            shapes = {'qkv': list(q.shape), 'dtype': str(q.dtype), 'stride': list(q.stride())}
            attention = WindowAttention(backend, window_batch=2)
            value = attention(q, k, v, layout, window_bounds(15, radius=2, chunk=3), 128 ** -.5, 'both')
            policy = dict(attention.backend_calls)
            reference = window_softmax_reference(q, k, v, layout, window_bounds(15, radius=2, chunk=3), 128 ** -.5, 'both')
            tolerance = .06 if backend == 'sage2' else .006
        torch.cuda.synchronize()
        if not bool(torch.isfinite(value).all()):
            raise RuntimeError('Kernel returned non-finite values')
        relative = ((value.float() - reference.float()).square().mean() /
                    reference.float().square().mean().clamp_min(1e-20)).sqrt().item()
        if not math.isfinite(relative) or relative > tolerance:
            raise RuntimeError(f'Kernel relative RMSE {relative:.6f} exceeded {tolerance}')
        print(json.dumps({'backend': backend, 'status': 'complete', 'policy': policy,
                          'gpu': torch.cuda.get_device_name(), 'capability': torch.cuda.get_device_capability(),
                          'scope': 'Small-shape execution only', 'finite': True,
                          'relative_rmse': relative, 'relative_rmse_limit': tolerance,
                          'shapes': shapes,
                          'torch_flash_compiled': torch.backends.cuda.is_flash_attention_available(),
                          'torch': str(torch.__version__), 'cuda': torch.version.cuda,
                          'system': platform.system()}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        traceback.print_exc()
        print(json.dumps({'backend': sys.argv[1], 'status': 'error', 'error': str(error),
                          'torch_flash_compiled': torch.backends.cuda.is_flash_attention_available(),
                          'torch': str(torch.__version__), 'cuda': torch.version.cuda,
                          'system': platform.system()}), flush=True)
        sys.exit(1)
