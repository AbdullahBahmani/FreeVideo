"""Transient progress snapshots for reopened ComfyUI tabs; no request inputs."""
from copy import deepcopy
import threading
import time
import uuid


class ProgressState:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.stream_id = uuid.uuid4().hex
        self.sequence = 0
        self.rows = {}
        self.lock = threading.Lock()

    def publish(self, node, message):
        # Only presentation fields. In particular, do not retain the prompt,
        # workflow, paths, device identity or full resource forecast here.
        keys = ('label', 'detail', 'phase', 'stage', 'timing_phase', 'done', 'total',
                'unit', 'block', 'blocks', 'elapsed_seconds', 'step_elapsed_seconds',
                'estimated_step_seconds', 'remaining_seconds', 'display_fraction',
                'estimated', 'uniform_remaining_steps', 'overall', 'retry', 'warning', 'kernel_cache_note',
                'new_request', 'reset', 'result')
        value = deepcopy({key: message[key] for key in keys if key in message})
        node = str(node)
        with self.lock:
            now = self.clock()
            old = self.rows.get(node)
            if old and value.get('warning'):
                # A memory warning must not replace the current sampling step.
                value = dict(old['message'], warning=value['warning'])
                measured = old['measured']
            else:
                measured = now
                if old and not value.get('new_request') and old['message'].get('retry'):
                    value.setdefault('retry', old['message']['retry'])
            self.sequence += 1
            value.update(node=node, stream_id=self.stream_id, sequence=self.sequence)
            self.rows[node] = {'message': value, 'measured': measured}
            while len(self.rows) > 32:
                oldest = min(self.rows, key=lambda key: self.rows[key]['message']['sequence'])
                del self.rows[oldest]
            return dict(value, age_seconds=max(0., now - measured))

    def snapshot(self):
        with self.lock:
            now = self.clock()
            return [dict(deepcopy(row['message']), age_seconds=max(0., now-row['measured']))
                    for row in self.rows.values()]


STATE = ProgressState()


def publish(server, node, message):
    value = STATE.publish(node, message)
    if server is not None:
        # Progress belongs to the running node, not to the tab that queued it.
        server.send_sync('freevideo_progress', value)
    return value


def cancel_request(queue, prompt_id, node_id, interrupt):
    """Remove or interrupt exactly this FreeVideo request under the queue lock."""
    with queue.mutex:
        running, pending = queue.get_current_queue()
        def matches(row):
            return (row[1] == prompt_id
                    and row[2].get(str(node_id), {}).get('class_type') == 'FreeVideoGenerate')
        if any(matches(row) for row in pending):
            queue.delete_queue_item(matches)
            return 'cancelled'
        if any(matches(row) for row in running):
            # Hold the same lock used by task_done/get: the next request cannot
            # start between checking the ID and setting Comfy's interrupt flag.
            interrupt()
            return 'cancelling'
        return 'finished'


def register():
    from aiohttp import web
    from server import PromptServer
    server = PromptServer.instance
    if server is None or getattr(server, '_freevideo_progress', False):
        return
    server._freevideo_progress = True

    @server.routes.get('/freevideo/progress')
    async def progress(request):
        return web.json_response({'progress': STATE.snapshot()},
                                 headers={'Cache-Control': 'no-store'})

    @server.routes.post('/freevideo/cancel')
    async def cancel(request):
        value = await request.json()
        prompt_id, node_id = value.get('prompt_id'), value.get('node_id')
        if not isinstance(prompt_id, str) or not prompt_id or not isinstance(node_id, str):
            return web.json_response({'error': 'A request and node ID are required'}, status=400)
        import nodes
        return web.json_response({'status': cancel_request(server.prompt_queue, prompt_id,
            node_id, nodes.interrupt_processing)})
