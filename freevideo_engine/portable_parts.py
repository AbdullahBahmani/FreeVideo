"""Join independently distributed model and runtime manifests before startup."""
import hashlib
import json
from pathlib import Path

from .monitoring import save
from .portable import inside


def assemble_manifest(root):
    """No imports of models, GPU queries, downloads, or changes to existing installs."""
    root = Path(root).resolve()
    runtime = json.loads(inside(root, 'runtime.json').read_text(encoding='utf-8'))
    if runtime.get('schema_version') != 1:
        raise ValueError('Unsupported FreeVideo runtime package')
    marker = inside(root, 'models/model-pack.json')
    if not marker.is_file():
        raise ValueError('尚未放入模型包。请将对应显卡的纯模型包解压到同一位置，'
                         '让 models、python、ComfyUI 位于同一个 FreeVideo-Windows 文件夹内。')
    raw = marker.read_bytes()
    model = json.loads(raw)
    variant = model.get('variant')
    digest = hashlib.sha256(raw).hexdigest()
    if (model.get('schema_version') != 1 or variant not in ('rowwise', 'per_tensor')
            or runtime.get('model_packs', {}).get(variant) != digest):
        raise ValueError('模型包与运行环境包不匹配。请使用同一批发布的配套包。')
    rows = runtime['files'] + model['files'] + [dict(path='models/model-pack.json',
                                                   bytes=len(raw), sha256=digest)]
    seen = set()
    for row in rows:
        inside(root, row['path'])
        if (row['path'].casefold() in seen or type(row['bytes']) is not int or row['bytes'] < 0
                or len(row['sha256']) != 64
                or any(c not in '0123456789abcdef' for c in row['sha256'])):
            raise ValueError('Invalid component inventory')
        seen.add(row['path'].casefold())
    if any(not r['path'].startswith('models/') for r in model['files']):
        raise ValueError('Model package contains non-model paths')
    if any(r['path'].startswith('models/') for r in runtime['files']):
        raise ValueError('Runtime package contains model paths')
    value = dict(runtime['configuration'], variant=variant, files=rows,
                 cache='models/edge/' + ('rowwise/cache' if variant == 'rowwise' else 'cache'),
                 component_model_sha256=digest)
    for key in ('python', 'source', 'comfy', 'vdn', 'model_root', 'encoder_root', 'cache'):
        inside(root, value[key])
    destination = inside(root, 'portable.json')
    if destination.exists():
        if json.loads(destination.read_text(encoding='utf-8')) != value:
            raise ValueError('此文件夹已有另一版本的整合包。请在新文件夹中解压配套包，现有文件已保留。')
    else:
        save(destination, value)
    return value
