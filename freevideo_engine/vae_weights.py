"""Bounded preparation of H3 decoder Linear weights for FP16 autocast.

This is an explicit experiment, not a blanket VAE precision change. RMSNorm,
LayerNorm, residual scales, register tokens and post-quantization stay FP32.
Original checkpoint bytes and the encoder used for input images are untouched.
"""
from pathlib import Path


def load_parameters(model, paths, *, device_for_name):
    """Read one tensor at a time, with no retained full FP32 state dictionary.

    CPU tensors are copied even when their dtype is unchanged, so a tiny norm
    parameter cannot retain the mapping containing gigabytes of consumed weights.
    All shapes/keys are checked before reading payloads; changed files fail closed.
    """
    import torch
    from .tensor_io import open_tensors
    expected = dict(model.named_parameters())
    files, sources = {}, {}
    for path in sorted(Path(p) for p in paths):
        stamp = path.stat()
        files[path] = (stamp.st_size, stamp.st_mtime_ns, stamp.st_ctime_ns)
        with open_tensors(str(path), framework='pt') as handle:
            for name in handle.keys():
                if name.startswith(('encoder.', 'quant_conv.')):
                    continue
                if name not in expected or name in sources:
                    raise ValueError('Unexpected or duplicate VAE decoder weight: ' + name)
                metadata = handle.get_slice(name)
                if tuple(metadata.get_shape()) != tuple(expected[name].shape):
                    raise ValueError('VAE decoder weight shape mismatch: ' + name)
                if not (metadata.get_dtype().startswith('F') or metadata.get_dtype() == 'BF16'):
                    raise ValueError('VAE weight is not floating point: ' + name)
                sources[name] = path
    if set(sources) != set(expected):
        raise ValueError('Missing VAE decoder weights: ' + ', '.join(sorted(set(expected) - set(sources))))
    converted, loaded, streamed_count, streamed_bytes = 0, 0, 0, 0
    for path, stamp in files.items():
        names = [name for name, source in sources.items() if source == path]
        if not names:
            continue
        for name in names:
            parent, _, leaf = name.rpartition('.')
            owner = model.get_submodule(parent) if parent else model
            dtype = torch.float16 if isinstance(owner, torch.nn.Linear) else torch.float32
            device = torch.device(device_for_name(name))
            if device.type == 'meta':
                # Only metadata is needed until a streamed layer executes.
                # Reading the whole CPU remainder here defeats streaming even
                # if its storage is discarded by the later offloader.
                target = torch.empty(expected[name].shape, dtype=dtype, device='meta')
                owner._parameters[leaf] = torch.nn.Parameter(target, requires_grad=False)
                streamed_count += 1
                streamed_bytes += target.numel() * target.element_size()
                continue
            # A long-lived shard handle keeps consumed pages mapped even after
            # individual tensors are released. Close it after every upload.
            with open_tensors(str(path), framework='pt') as handle:
                source = handle.get_tensor(name)
                if not source.is_floating_point():
                    raise ValueError('VAE weight is not floating point: ' + name)
                # Match from_pretrained's FP32 parameter dtype before autocast,
                # including the rounding of a non-FP32 checkpoint tensor.
                target = source.to(dtype=torch.float32).to(device=device, dtype=dtype, copy=True)
                owner._parameters[leaf] = torch.nn.Parameter(target, requires_grad=False)
                converted += int(dtype == torch.float16)
                loaded += target.numel() * target.element_size()
                del source, target
        current = path.stat()
        if (current.st_size, current.st_mtime_ns, current.st_ctime_ns) != stamp:
            raise ValueError('VAE checkpoint changed during preparation: ' + str(path))
    return dict(linear_parameter_count=converted, prepared_parameter_bytes=loaded,
                streamed_parameter_count=streamed_count, streamed_parameter_bytes=streamed_bytes,
                source_policy='Original FP32 checkpoint, one tensor at a time',
                compute_policy='FP16 Linear weights; FP32 normalization, residual scales and other parameters')


def load_video_decoder(base, *, resident_blocks, weight_source=None):
    """Place the selected decoder prefix directly on CUDA without a CPU copy."""
    import torch
    from diffusers import AutoencoderKLMiniMaxH3
    directory = Path(base) / 'vae'
    config = AutoencoderKLMiniMaxH3.load_config(str(directory), local_files_only=True)
    with torch.device('meta'):
        model = AutoencoderKLMiniMaxH3.from_config(config)
    if type(resident_blocks) is not int or not 0 <= resident_blocks <= len(model.decoder.transformer_blocks):
        raise ValueError('Invalid VAE resident block count')
    if weight_source is not None and weight_source.prefixes != tuple(
            f'decoder.transformer_blocks.{index}.' for index in range(
                resident_blocks, len(model.decoder.transformer_blocks))):
        raise ValueError('Streamed VAE source does not match the offloaded layer order')
    model.encoder = None
    model.quant_conv = None
    # The pinned decoder has one non-persistent buffer, generated by its own
    # constructor rather than read from the checkpoint. Preserve its FP32 math.
    model.decoder.rope = type(model.decoder.rope)(
        int(model.config.decoder_attention_head_dim * model.config.decoder_rope_dim_ratio),
        theta=model.config.decoder_rope_theta)
    if any(value.is_meta for value in model.buffers()):
        raise ValueError('Unexpected unmaterialized VAE buffer')
    def placement(name):
        prefix = 'decoder.transformer_blocks.'
        if name.startswith(prefix) and int(name[len(prefix):].split('.', 1)[0]) >= resident_blocks:
            return 'meta' if weight_source is not None else 'cpu'
        return 'cuda'
    metrics = load_parameters(model, directory.glob('*.safetensors'), device_for_name=placement)
    if weight_source is not None:
        from .offload import initialize_streamed_layer
        for index, layer in enumerate(list(model.decoder.transformer_blocks)[resident_blocks:]):
            initialize_streamed_layer(layer, weight_source, index)
    model.eval().requires_grad_(False)
    return model, metrics
