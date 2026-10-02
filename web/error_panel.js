// Shared by the Studio and graph view. Text only; never render exception HTML.
export function errorText(detail) {
    const cause = detail?.exception_message || detail?.message || 'FreeVideo generation failed.';
    const trace = Array.isArray(detail?.traceback) ? detail.traceback.join('') : '';
    return String(cause + (trace ? '\n\n' + trace : '')).slice(0, 65536);
}

// Match explicit failure signatures, not a guessed GPU/RAM capacity. Keep the
// original error separately so an explanation never replaces diagnostic data.
export function failureAdvice(value, t) {
    const text = String(value).slice(0, 65536);
    const row = (kind, title, summary, action) => ({kind, title: t(...title), summary: t(...summary), action: t(...action)});
    if (/commit headroom exhausted|paging file is too small|WinError 1455/i.test(text))
        return row('commit', ['Windows memory allocation limit reached', 'Windows 内存提交额度不足'],
            ['Windows cannot back another memory allocation, even if physical RAM is still available.', 'Windows 已没有足够的提交额度；这与物理 RAM 是否还有空闲是两回事。'],
            ['Close memory-heavy applications and retry. In Windows virtual memory settings, use a system-managed paging file on a drive with free space.', '关闭占用内存较多的程序后重试。在 Windows 虚拟内存设置中，使用系统管理的分页文件，并确保所在磁盘有空闲空间。']);
    if (/CUDA out of memory|torch\.OutOfMemoryError|cudaErrorMemoryAllocation/i.test(text))
        return row('vram', ['GPU memory allocation failed', '显存分配失败'],
            ['The GPU could not allocate the memory needed at this stage.', '这一阶段的显存申请没有成功。'],
            ['Close other GPU workloads and retry so FreeVideo can replan using the newly available memory. Your resolution, duration and steps are kept.', '关闭其他占用显卡的任务后重试，FreeVideo 会根据新的可用显存重新规划，保留你的分辨率、时长和步数。']);
    if (/RAM guard:|crossed its RAM budget|Insufficient currently available memory/i.test(text))
        return row('ram', ['Available memory or an explicit RAM limit reached', '可用内存或手动 RAM 限额不足'],
            ['Automatic RAM estimates can be exceeded while memory is available. This stop indicates system pressure or an explicitly enforced limit.', '自动模式允许在系统仍有余量时超出预估 RAM；停止意味着系统内存压力，或触及了手动设置的硬限制。'],
            ['Close memory-heavy applications and retry. If you set a RAM limit for testing, remove or raise it for normal generation. Copy the details below if it still fails.', '关闭占用内存较多的程序后重试。如果设置过测试用 RAM 限制，正常生成时可取消或调高。仍失败时可复制下方详情。']);
    if (/No space left on device|WinError 112|disk (?:is )?full/i.test(text))
        return row('disk', ['Disk space is insufficient', '磁盘空间不足'],
            ['FreeVideo could not write a required file.', 'FreeVideo 无法写入所需文件。'],
            ['Free space on the installation/output drive and retry. Keep model downloads and retained outputs if you want to resume or inspect them.', '清理安装目录或输出目录所在磁盘的空间后重试；保留模型下载和输出文件，便于续传或排查。']);
    if (/Model download paused|unexpected-transfer-size|ConnectionError|ConnectTimeout|ReadTimeout/i.test(text))
        return row('download', ['Download needs attention', '下载未完成'],
            ['A transfer failed or its received data did not match the expected file.', '传输中断，或收到的数据与预期文件不一致。'],
            ['Check your connection or select another download source in Settings, then retry. Existing download fragments are retained.', '检查网络，或在设置中切换下载源后重试。已有下载片段会保留。']);
    if (/ModuleNotFoundError|No module named|DLL load failed/i.test(text))
        return row('dependencies', ['A runtime dependency could not load', '运行依赖无法加载'],
            ['The runtime may be incomplete or an incompatible environment may have been selected.', '运行环境可能不完整，或使用了不兼容的环境。'],
            ['Open the FreeVideo launcher and rerun installation for the same folder to check dependencies. If it persists, copy the details below.', '打开 FreeVideo 启动器，对同一安装目录重新执行安装以检查依赖。仍失败时可复制下方详情。']);
    return row('unknown', ['Generation stopped', '生成已停止'],
        ['This request did not complete. The exact error is retained below.', '这次请求未完成，具体错误已保留在下方。'],
        ['Copy the error details when reporting the issue; they include the failed stage when available.', '反馈问题时请复制错误详情，其中会保留已记录的失败阶段。']);
}

let activeDialog = null;
function showFailureDialog(value, t) {
    // Both graph and Studio receive execution_error. Show one modal for that
    // event, above the Studio modal if it is open, with keyboard dismissal.
    if (activeDialog?.open && activeDialog.freevideoError === value) return;
    activeDialog?.close();
    const dialog = document.createElement('dialog'); dialog.className = 'fv-failure-dialog';
    dialog.freevideoError = value;
    dialog.setAttribute('aria-label', t('FreeVideo error', 'FreeVideo 错误'));
    const panel = createErrorPanel(t); panel.show(value, false);
    const close = document.createElement('button'); close.type = 'button';
    close.textContent = t('Got it', '知道了'); close.autofocus = true;
    close.onclick = () => dialog.close();
    dialog.append(panel.element, close);
    dialog.onclose = () => { if (activeDialog === dialog) activeDialog = null; dialog.remove(); };
    document.body.append(dialog);
    if (typeof dialog.showModal !== 'function') { dialog.remove(); return; }
    activeDialog = dialog; dialog.showModal();
}

export function createErrorPanel(t) {
    if (!document.getElementById('freevideo-error-style')) {
        const style = document.createElement('style'); style.id = 'freevideo-error-style';
        style.textContent = `.fv-failure{border:1px solid var(--fv-danger,#dc7c7c);border-radius:var(--fv-r-md,12px);padding:12px 14px;margin:10px 0;text-align:left;min-width:0}
.fv-failure[hidden]{display:none}.fv-failure-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:8px}
.fv-failure textarea{box-sizing:border-box;width:100%;height:180px;min-height:100px;resize:vertical;border:1px solid var(--fv-border,#45454a);border-radius:var(--fv-r-sm,8px);background:var(--fv-bg,#202126);color:var(--fv-ink,#eee);font:12px/1.5 monospace;padding:9px;white-space:pre-wrap}
.fv-failure button,.fv-failure-dialog>button{min-height:var(--fv-h-sm,32px);border:1px solid var(--fv-border,#45454a);border-radius:var(--fv-r-sm,8px);background:var(--fv-raised,#303138);color:var(--fv-ink,#eee);padding:5px 12px;font:inherit;font-weight:var(--fv-medium,500);cursor:pointer}
.fv-failure p{font-size:14px;line-height:1.6;margin:8px 0}.fv-failure summary{cursor:pointer;margin-top:12px}
.fv-failure-dialog{box-sizing:border-box;width:min(560px,94vw);max-height:88vh;overflow:auto;padding:22px 24px;border:1px solid var(--fv-border,#45454a);border-radius:var(--fv-r-lg,16px);background:var(--fv-bg,#202126);color:var(--fv-ink,#eee);box-shadow:0 24px 80px #0008}
.fv-failure-dialog::backdrop{background:#070a0db8;backdrop-filter:blur(6px)}.fv-failure-dialog>.fv-failure{border:0;margin:0 0 16px;padding:0}.fv-failure-dialog>button{display:block;margin-left:auto;background:var(--fv-accent,#6db8fa);border-color:var(--fv-accent,#6db8fa);color:var(--fv-bg,#111720);font-weight:var(--fv-semibold,600)}`;
        document.head.append(style);
    }
    const element = document.createElement('section'); element.className = 'fv-failure'; element.hidden = true;
    const head = document.createElement('div'); head.className = 'fv-failure-head';
    const title = document.createElement('strong'); title.textContent = t('Generation failed', '生成失败');
    const copy = document.createElement('button'); copy.type = 'button'; copy.textContent = t('Copy error', '复制错误');
    const explanation = document.createElement('p'), action = document.createElement('p');
    const disclosure = document.createElement('details'), summary = document.createElement('summary');
    summary.textContent = t('Technical details', '技术详情');
    const details = document.createElement('textarea'); details.readOnly = true;
    details.setAttribute('aria-label', t('Error details', '错误详情')); details.spellcheck = false;
    copy.onclick = async () => {
        let copied = false;
        try { await navigator.clipboard.writeText(details.value); copied = true; } catch {
            // Remote ComfyUI commonly uses plain HTTP, where Clipboard API is
            // unavailable. Keep selectable text even if the browser denies copy.
            disclosure.open = true; details.focus(); details.select();
            try { copied = document.execCommand('copy'); } catch { /* manual Ctrl+C */ }
        }
        copy.textContent = copied ? t('Copied', '已复制') : t('Press Ctrl+C', '请按 Ctrl+C');
    };
    disclosure.append(summary, details);
    head.append(title, copy); element.append(head, explanation, action, disclosure);
    return {element, show(value, popup = true) {
        value = String(value).slice(0, 65536);
        const advice = failureAdvice(value, t);
        title.textContent = advice.title; explanation.textContent = advice.summary; action.textContent = advice.action;
        details.value = value; disclosure.open = false; element.hidden = false;
        copy.textContent = t('Copy error', '复制错误');
        if (popup) showFailureDialog(value, t);
    }, clear() { details.value = ''; element.hidden = true; }};
}
