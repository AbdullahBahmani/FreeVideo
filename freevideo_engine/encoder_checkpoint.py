"""Read-only native encoder weights without Windows whole-file COW commit."""
import json
import math
import mmap
import os
import struct
import sys
import warnings
import weakref


def read_only_state_dict(path, dtypes):
    """Only for immutable inference weights; tensors retain their mapping.

    safetensors' Torch mmap path briefly owns two whole-file copy-on-write
    mappings. Windows charges commit for both before any tensor is accessed.
    A read-only map needs no private backing for untouched checkpoint pages.
    In-place weight edits must operate on a clone, as with Comfy's native
    read-only model loader. No quantization or dtype conversion happens here.
    """
    import torch

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('Duplicate safetensors header key')
            value[key] = item
        return value

    with open(path, 'rb') as stream:
        size = os.fstat(stream.fileno()).st_size
        prefix = stream.read(8)
        if len(prefix) != 8:
            raise ValueError('Incomplete safetensors header')
        header_size = struct.unpack('<Q', prefix)[0]
        if not 2 <= header_size <= min(100_000_000, size - 8):
            raise ValueError('Invalid safetensors header size')
        header = json.loads(stream.read(header_size), object_pairs_hook=unique)
        if not isinstance(header, dict):
            raise ValueError('Invalid safetensors header')
        metadata = header.pop('__metadata__', {})
        if not isinstance(metadata, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                                 for k, v in metadata.items()):
            raise ValueError('Invalid safetensors metadata')
        base = 8 + header_size
        specs = []
        for name, info in header.items():
            if not isinstance(info, dict):
                raise ValueError('Invalid safetensors tensor specification')
            dtype_name = info.get('dtype')
            dtype = dtypes.get(dtype_name) if isinstance(dtype_name, str) else None
            shape, offsets = info.get('shape'), info.get('data_offsets')
            if dtype is None or not isinstance(shape, list) or any(type(n) is not int or n < 0 for n in shape):
                raise ValueError('Invalid or unsupported safetensors tensor dtype/shape')
            if not isinstance(offsets, list) or len(offsets) != 2 or any(type(n) is not int for n in offsets):
                raise ValueError('Invalid safetensors tensor offsets')
            begin, end = offsets
            count = math.prod(shape)
            if not 0 <= begin <= end <= size - base or count * dtype.itemsize != end - begin:
                raise ValueError('Safetensors tensor shape/offsets do not match its bytes')
            specs.append((begin, end, name, dtype, shape, count))
        # Include empty tensors, reject overlaps, holes and trailing data before
        # exposing any tensor to the native model constructor.
        cursor = 0
        for begin, end, *_ in sorted(specs):
            if begin != cursor:
                raise ValueError('Non-contiguous or overlapping safetensors data')
            cursor = end
        if cursor != size - base or sys.byteorder != 'little':
            raise ValueError('Invalid safetensors data length or unsupported byte order')
        mapping = mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ)
    state = {}
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', message='The given buffer is not writable')
            for begin, end, name, dtype, shape, count in specs:
                state[name] = (torch.frombuffer(mapping, dtype=dtype, count=count, offset=base+begin).reshape(shape)
                               if count else torch.empty(shape, dtype=dtype))
    except BaseException:
        state.clear()
        mapping.close()
        raise
    # frombuffer retains the buffer owner, including across Parameter/views.
    if not state or not any(spec[-1] for spec in specs):
        mapping.close()
        return state, metadata
    # Hand back the mapping so a caller that has finished with the weights can
    # advise its pages away. fadvise cannot: it only drops pages no process
    # maps, and these are mapped for as long as a tensor points into them --
    # advising a consumed 14.61 GiB checkpoint moved the resident total by
    # 0.00 GiB at three GPU budgets. madvise on the mapping itself does drop
    # them, and a read-only immutable file refaults correctly.
    MAPPINGS.setdefault(os.path.realpath(path), []).append(weakref.ref(mapping))
    begin, _, name, _, _, _ = next(spec for spec in specs if spec[-1])
    address = state[name].data_ptr() - (base + begin)
    READ_ONLY_RANGES.append((weakref.ref(mapping), address, address + len(mapping)))
    return state, metadata


# Read-only checkpoint mappings by path, so their pages can be released after
# their weights have been transferred. Weak references only: the tensors own
# the mapping and the last of them must still be what closes it. A strong
# reference here kept every checkpoint mapped for the life of the process.
MAPPINGS = {}
READ_ONLY_RANGES = []


def owns_readonly_tensor(tensor):
    """Recognize mapped weights after native Parameter, view or quantized wraps.

    Pointer ranges, not Python tensor attributes, survive those wrappers. The
    weak mmap owner prevents recycled addresses being mistaken for old weights.
    """
    if getattr(getattr(tensor, 'device', None), 'type', None) != 'cpu':
        return False
    try:
        start, size = tensor.data_ptr(), tensor.nbytes
    except (AttributeError, RuntimeError, TypeError):
        return False
    if type(start) is not int or type(size) is not int or size <= 0:
        return False
    found = False
    for item in list(READ_ONLY_RANGES):
        reference, begin, end = item
        mapping = reference()
        if mapping is None or mapping.closed:
            READ_ONLY_RANGES.remove(item)
        elif begin <= start and start + size <= end:
            found = True
    return found


def release_mapped_pages(paths):
    """Advise away the pages of checkpoints already transferred elsewhere.

    Read-only immutable weights, so a dropped page refaults from the file. The
    mapping stays open because tensors still point into it; only the resident
    pages go. Returns what it advised, or None when mapping advice is unavailable
    (including Windows) or there are no live mappings to advise.
    """
    if not hasattr(mmap.mmap, 'madvise') or not hasattr(mmap, 'MADV_DONTNEED'):
        return None
    advised, errors = 0, []
    for item in paths or ():
        live = MAPPINGS.get(os.path.realpath(item), [])
        for reference in list(live):
            mapping = reference()
            if mapping is None:
                live.remove(reference)      # its tensors are gone; so is it
                continue
            try:
                mapping.madvise(mmap.MADV_DONTNEED)
                advised += len(mapping)
            except ValueError:
                # Closed, so its pages are already gone with it. A weak
                # reference stays alive while something else still holds the
                # closed object, so drop the entry rather than report it.
                live.remove(reference)
            except OSError as error:
                errors.append('%s: %s' % (os.path.basename(item), error))
    return dict(advised_bytes=advised, errors=errors) if advised or errors else None


def load_clip(ckpt_paths, embedding_directory=None, clip_type=None, model_options=None,
              disable_dynamic=False, progress=None):
    """Keep the native CLIP construction and quantization, replace only file IO."""
    import comfy.sd
    import comfy.utils
    options = {} if model_options is None else model_options
    # Every platform now. The read-only map was written for Windows, where
    # safetensors' Torch path briefly owns two whole-file copy-on-write
    # mappings and commit is charged for both. It earns its place on Linux for
    # a different reason: it is the only path that keeps a handle on the
    # mapping, and without one the checkpoint's consumed pages cannot be
    # released after the weights reach the device. Those pages are the whole
    # host footprint -- 5.87 of 7.82 GiB resident at a 6.45 GiB GPU budget --
    # and a hard cgroup or commit limit does not wait for reclaim: a 10 GiB
    # limit killed this encoder at 9.84 GiB with no disk read recorded. The
    # native construction and quantization are unchanged either way; only the
    # file IO differs.
    states = []
    for path in ckpt_paths:
        if progress:
            progress('encoder_checkpoint_map')
        state, metadata = read_only_state_dict(path, comfy.utils._TYPES)
        if options.get('custom_operations') is None:
            state, metadata = comfy.utils.convert_old_quants(state, model_prefix='', metadata=metadata)
        states.append(state)
    if progress:
        progress('encoder_construct')
    clip = comfy.sd.load_text_encoder_state_dicts(states, embedding_directory=embedding_directory,
        clip_type=clip_type, model_options=options, disable_dynamic=disable_dynamic)
    # Native patcher recreation must use the same reader, not return to COW.
    clip.patcher.cached_patcher_init = (load_clip_model_patcher,
        (ckpt_paths, embedding_directory, clip_type, options, disable_dynamic))
    return clip


def load_clip_model_patcher(*args, **kwargs):
    return load_clip(*args, **kwargs).patcher
