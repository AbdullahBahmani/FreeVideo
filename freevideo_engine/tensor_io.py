"""Bounded CPU tensor reads for model preparation, without persistent file maps."""


def open_tensors(path, *, framework='pt'):
    from safetensors import safe_open
    # The default Torch mmap is copy-on-write. On Windows its commit charge is
    # the whole shard, and a tiny returned tensor can keep that mapping alive.
    # pread owns only the requested tensor's bytes, including BF16/FP8 tensors.
    # Do not silently fall back to mmap on an older manually installed runtime.
    try:
        return safe_open(path, framework=framework, device='cpu', backend='pread')
    except TypeError as error:
        raise RuntimeError('Bounded model preparation requires safetensors >= 0.8.0. '
                           'Rerun setup to update the managed environment.') from error
