"""Prepare a final cold-model RAM test without dropping the system page cache.

Only immutable model files in the selected FP8 cache, VAEs and shared encoder
are advised away. fincore or libc mincore verifies the result because
POSIX_FADV_DONTNEED is advisory. No file contents, global drop_caches setting or
unrelated caches change.
See https://man7.org/linux/man-pages/man2/posix_fadvise.2.html and mincore(2).
"""
import argparse
import ctypes
import json
import mmap
import os
from pathlib import Path
import shutil
import subprocess
import time

from freevideo_engine.locking import runtime_lock
from freevideo_engine.paths import base_path


def residency(paths):
    if shutil.which('fincore') is None:
        return mincore_residency(paths)
    result = subprocess.run(['fincore', '--json', '--bytes', '--output', 'RES,SIZE,FILE',
                             *map(str, paths)], check=True, text=True, capture_output=True)
    return json.loads(result.stdout)['fincore']


def mincore_residency(paths):
    """Query Linux page residency without touching pages or requiring util-linux."""
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int,
                          ctypes.c_int, ctypes.c_longlong]
    libc.mmap.restype = ctypes.c_void_p
    libc.mincore.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_ubyte)]
    libc.mincore.restype = ctypes.c_int
    libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    libc.munmap.restype = ctypes.c_int
    rows = []
    for path in paths:
        size = path.stat().st_size
        resident = 0
        if size:
            with path.open('rb', buffering=0) as file:
                address = libc.mmap(None, size, mmap.PROT_READ, mmap.MAP_SHARED, file.fileno(), 0)
                if address == ctypes.c_void_p(-1).value:
                    error = ctypes.get_errno()
                    raise OSError(error, os.strerror(error), str(path))
                try:
                    pages = (ctypes.c_ubyte * ((size + mmap.PAGESIZE - 1) // mmap.PAGESIZE))()
                    if libc.mincore(address, size, pages):
                        error = ctypes.get_errno()
                        raise OSError(error, os.strerror(error), str(path))
                    resident = sum(value & 1 for value in pages) * mmap.PAGESIZE
                finally:
                    if libc.munmap(address, size):
                        error = ctypes.get_errno()
                        raise OSError(error, os.strerror(error), str(path))
        rows.append({'res': resident, 'size': size, 'file': str(path)})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--model-files', nargs='+', type=Path, help='Explicit immutable model set for another pipeline')
    parser.add_argument('--base', type=Path, default=base_path())
    parser.add_argument('--encoder', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if args.model_files:
        if args.cache:
            parser.error('Select a prepared FP8 cache or explicit model files')
        paths = args.model_files
    else:
        if args.cache is None:
            parser.error('--cache or --model-files is required')
        paths = list(args.cache.rglob('*.safetensors'))
        paths += list((args.base / 'vae').glob('*.safetensors'))
        paths += list((args.base / 'audio_vae').glob('*.safetensors'))
        if args.encoder:
            paths.append(args.encoder)
    paths = sorted({p.resolve() for p in paths})
    if not paths or any(not p.is_file() or p.suffix != '.safetensors' for p in paths):
        raise ValueError('Every selected file must exist in the immutable model store')
    if any(p.stat().st_uid != os.geteuid() for p in paths) and os.geteuid() != 0:
        raise PermissionError('Accurate mincore residency requires ownership of the model files')
    before_stat = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in paths}
    started = time.perf_counter()
    with runtime_lock():
        clients = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader'], text=True).strip()
        if clients:
            raise RuntimeError('Wait for all model workers to exit before evicting their file pages')
        before = residency(paths)
        for path in paths:
            with path.open('rb', buffering=0) as file:
                os.fsync(file.fileno())
                os.posix_fadvise(file.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
        after = residency(paths)
    if any((p.stat().st_size, p.stat().st_mtime_ns) != before_stat[str(p)] for p in paths):
        raise RuntimeError('A model file changed during cache preparation')
    result = {'scope': __doc__, 'file_count': len(paths), 'before': before, 'after': after,
              'residency_verifier': 'fincore' if shutil.which('fincore') else 'libc mincore',
              'resident_before_bytes': sum(int(row['res']) for row in before),
              'resident_after_bytes': sum(int(row['res']) for row in after),
              'file_bytes': sum(int(row['size']) for row in after),
              'seconds': time.perf_counter() - started,
              'file_content_written': False, 'global_drop_caches_used': False}
    # Partial final pages may remain. Report them rather than claiming zero.
    result['cold_model_pages_verified'] = result['resident_after_bytes'] <= 16 * 1024 * 1024
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('before', 'after', 'scope')}))
    if not result['cold_model_pages_verified']:
        raise RuntimeError('Too many model pages remain resident for the planned cold-model test')


if __name__ == '__main__':
    main()
