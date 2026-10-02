"""User-facing model download destinations, from the installation manifests."""
import json
from pathlib import Path
from urllib.parse import quote, urlsplit


def links():
    root = Path(__file__).parent
    spec = json.loads((root / 'dependencies.json').read_text(encoding='utf-8'))['models']
    edge = json.loads((root / 'prepared_models.json').read_text(encoding='utf-8'))
    return {
        'video': [('Hugging Face', 'https://huggingface.co/' + edge['repo']),
                  ('ModelScope', 'https://modelscope.ai/models/' + spec['edge_modelscope']['repo'])],
        'encoder': [('Hugging Face', 'https://huggingface.co/' + spec['encoder_repo'] + '/blob/' +
                     spec['encoder_revision'] + '/' + quote(spec['encoder_file'], safe='/'))],
        'decoder': [('Hugging Face · Video', 'https://huggingface.co/' + spec['vdn_repo'] + '/tree/' +
                     spec['vdn_revision'] + '/h3-base/vae'),
                    ('Hugging Face · Audio', 'https://huggingface.co/' + spec['vdn_repo'] + '/tree/' +
                     spec['vdn_revision'] + '/h3-base/audio_vae'),
                    ('ModelScope', 'https://modelscope.ai/models/' + spec['vdn_modelscope']['repo'])],
    }


def cloud_models():
    """Only publisher-approved or release-verified shares become download links."""
    path = Path(__file__).with_name('model_shares.json')
    if not path.exists():
        return []
    value = json.loads(path.read_text(encoding='utf-8'))
    result = []
    for row in value.get('models', []):
        url = urlsplit(row.get('url', ''))
        if ((row.get('publisher_approved') is True or row.get('verified') is True)
                and url.scheme == 'https' and url.hostname == 'pan.quark.cn'
                and url.path.startswith('/s/') and not url.username and not url.password):
            result.append(row)
    return result


def show_component(app, component):
    import webbrowser
    from . import branding as b
    from .launcher_copy import display
    titles = {'video': ('Video model', '视频模型'), 'encoder': ('Text encoder', '文本编码器'),
              'decoder': ('Video & audio decoders', '视频与音频解码器')}
    instructions = {
        'video': ('Choose your GPU variant on the model page and keep its folder structure.',
                  '按模型页说明选择显卡版本，保留下载的目录结构。'),
        'encoder': ('Download the text encoder to your model folder.',
                    '下载文本编码器，放入模型目录。'),
        'decoder': ('Download the vae and audio_vae folders.',
                    '下载 vae 和 audio_vae 文件夹。'),
    }
    dialog = app.tk.Toplevel(app.window)
    dialog.title('FreeVideo · ' + app.t(*titles[component])); dialog.transient(app.window)
    dialog.configure(bg=b.BACKGROUND)
    body = app.ttk.Frame(dialog, padding=24); body.pack(fill='both', expand=True)
    app.ttk.Label(body, text=app.t(*titles[component]), style='Heading.TLabel').pack(anchor='w')
    app.ttk.Label(body, text=app.t(*instructions[component]), wraplength=490).pack(fill='x', pady=12)
    for title, url in links()[component]:
        app.ttk.Button(body, text=display(title, app.zh) + ' ↗', command=lambda u=url: webbrowser.open(u)).pack(fill='x', pady=4)
    for row in cloud_models():
        app.ttk.Button(body, text=app.t('Quark model pack · ', '夸克模型包 · ') + row['label'] + ' ↗',
                       command=lambda u=row['url']: webbrowser.open(u)).pack(fill='x', pady=4)
    app.ttk.Label(body, text=app.t('After downloading, extract ZIP files and choose the model folder below. Subfolders are scanned automatically.',
        '下载完成后先解压 ZIP，再选择模型所在文件夹；会自动扫描子文件夹。'), wraplength=490).pack(fill='x', pady=12)
    def choose():
        dialog.destroy()
        app.model_method.set('reuse')
        app.add_model_folder()
    app.ttk.Button(body, text=app.t('Downloaded · choose folder…', '已下载，选择文件夹…'), command=choose).pack(fill='x')
