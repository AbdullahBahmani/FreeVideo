"""User paths; importing the CLI or planner never initializes CUDA."""
import os
from pathlib import Path
import sys
from .system import install_root


def data_root():
    return install_root()


def vdn_root():
    return Path(os.environ.get('FREEVIDEO_VDN_ROOT', data_root() / 'vendor' / 'vdn')).expanduser()


def model_root():
    return Path(os.environ.get('FREEVIDEO_MODEL_ROOT', data_root() / 'models')).expanduser()


def add_vdn():
    root = vdn_root().resolve()
    if not (root / 'src/models/hybrid_attention.py').is_file():
        raise RuntimeError('VDN dependency is missing. Run freevideo setup or set FREEVIDEO_VDN_ROOT.')
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    # Editable-install .pth files retain the original absolute checkout path.
    # Resolve the pinned sibling source explicitly when a workspace is mounted
    # or moved under a different prefix (for example a capacity container).
    diffusers = root / 'diffusers' / 'src'
    if not (diffusers / 'diffusers/__init__.py').is_file():
        raise RuntimeError('Patched Diffusers dependency is missing. Run freevideo setup --install-packages.')
    if str(diffusers) not in sys.path:
        sys.path.insert(0, str(diffusers))
    # Pinned VDN imports its CUDA/Triton FP8 and temporal-conv modules at
    # module import time. The MPS execution policy never selects those paths.
    if sys.platform == 'darwin':
        from .mps_compat import install
        install()
    from .fa4_guard import activate
    activate()
    return root


def base_path():
    return model_root() / 'h3-base'


def checkpoint_path():
    return model_root() / 'stage-dmd-step-250'


def comfy_root():
    value = os.environ.get('FREEVIDEO_COMFY_ROOT')
    return Path(value).expanduser() if value else data_root() / 'vendor' / 'ComfyUI'
