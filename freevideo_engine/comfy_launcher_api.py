"""Read-only launcher handshake and the bundled default workflow."""
import json
from pathlib import Path


def register():
    from aiohttp import web
    import folder_paths
    from server import PromptServer
    from .comfy_bridge import source_root, installation_root
    server = PromptServer.instance
    if server is None or getattr(server, '_freevideo_launcher', None):
        return
    # Capture the loaded source now. Replacing files does not make an old live
    # server eligible for opening a new-version workflow without restarting.
    source = source_root().resolve()
    root = Path(folder_paths.__file__).resolve().parent
    info = dict(protocol=1, source=str(source), engine_root=str(installation_root(source)),
                comfy_root=str(root), data_root=str(Path(folder_paths.base_path).resolve()))
    from .comfy_console import install
    try:
        info['console_log'] = str(install(info['engine_root']))
    except (OSError, ValueError) as error:
        info['console_error'] = 'Could not capture ComfyUI output: ' + str(error)
    server._freevideo_launcher = info

    @server.routes.get('/freevideo/launcher')
    async def launcher(request):
        return web.json_response(info)

    @server.routes.get('/freevideo/launcher/workflow')
    async def workflow(request):
        value = json.loads((source / 'example_workflows' / 'FreeVideo-All-in-One.json').read_text(encoding='utf-8'))
        return web.json_response(value)
