"""Single-buffer host residuals for the small-VRAM block path.

The container transfers ownership: passing a GPU Tensor directly to Module
would leave it alive in Module's argument tuple throughout both sublayers.
Copies retain dtype and shape; normalization and residual kernels are unchanged.
"""
import time
import torch


class ResidualState:
    def __init__(self, tensor):
        if torch.is_grad_enabled() or tensor.requires_grad:
            raise RuntimeError('Residual offload requires inference without autograd')
        if not tensor.is_contiguous():
            raise ValueError('Residual offload requires the original contiguous packed layout')
        self.tensor = tensor
        self.shape, self.dtype, self.device = tuple(tensor.shape), tensor.dtype, tensor.device
        self.host = None
        self.stored = False
        self.closed = False
        self.copies = {'to_host': 0, 'to_device': 0}
        self.copy_wall_seconds = 0.

    def take(self):
        if self.closed or self.tensor is None:
            raise RuntimeError('Residual has no device value to consume')
        tensor, self.tensor = self.tensor, None
        return tensor

    def _check(self, tensor):
        if self.closed or tuple(tensor.shape) != self.shape or tensor.dtype != self.dtype or tensor.device != self.device or not tensor.is_contiguous():
            raise ValueError('Residual shape, dtype or device changed')

    def store(self, tensor):
        self._check(tensor)
        if self.tensor is not None:
            raise RuntimeError('Consume the device residual before staging it')
        tick = time.perf_counter()
        if self.host is None:
            # Pageable storage avoids consuming the platform's limited locked
            # pages in addition to attention readouts and the weight cache.
            self.host = torch.empty(self.shape, dtype=self.dtype, device='cpu')
        self.host.copy_(tensor, non_blocking=False)
        self.stored = True
        self.copies['to_host'] += 1
        self.copy_wall_seconds += time.perf_counter()-tick

    def restore(self):
        if self.closed or not self.stored:
            raise RuntimeError('No complete host residual is available')
        tick = time.perf_counter()
        # copy=True also makes CPU contract checks use independent storage.
        tensor = self.host.to(self.device, copy=True, non_blocking=False)
        self.copies['to_device'] += 1
        self.copy_wall_seconds += time.perf_counter()-tick
        return tensor

    def replace(self, tensor):
        self._check(tensor)
        if self.tensor is not None:
            raise RuntimeError('Cannot overwrite an unconsumed device residual')
        self.tensor = tensor

    def stats(self):
        return dict(host_buffer_bytes=self.host.numel()*self.host.element_size() if self.host is not None else 0,
                    pinned_host_bytes=0, copies=dict(self.copies), blocking_copy_wall_seconds=self.copy_wall_seconds,
                    timing_scope='Blocking copy calls can include waiting for prior compute; not pure PCIe transfer time.')

    def close(self):
        self.tensor = self.host = None
        self.stored = False
        self.closed = True


def residual_forward(pre, post):
    def forward(self, state, temb, adaln_indices, rotary_emb, attention_mask=None):
        if torch.is_grad_enabled():
            raise RuntimeError('Residual offload requires inference without autograd')
        if not isinstance(state, ResidualState):
            raise TypeError('Residual offload needs the owning packed-input container')
        hidden = state.take()
        shift_a, scale_a, gate_a, shift_f, scale_f, gate_f = self.adaln_proj(temb)
        normalized = pre(hidden, self.norm1.weight, self.norm1.eps, scale_a, shift_a, adaln_indices)
        state.store(hidden)
        del hidden
        branch = self.attn(normalized, rotary_emb, attention_mask)
        del normalized
        residual = state.restore()
        hidden = post(residual, gate_a, adaln_indices, branch)
        del residual, branch
        normalized = pre(hidden, self.norm2.weight, self.norm2.eps, scale_f, shift_f, adaln_indices)
        state.store(hidden)
        del hidden
        branch = self.ff(normalized)
        del normalized
        residual = state.restore()
        state.replace(post(residual, gate_f, adaln_indices, branch))
        del residual, branch
        return state
    return forward
