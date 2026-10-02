const reduceMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

export function closeDialog(dialog) {
    if (!dialog.open || dialog.dataset.closing === 'true') return;
    if (reduceMotion() || !dialog.animate) { dialog.close(); return; }
    dialog.dataset.closing = 'true';
    dialog.animate([{opacity: 1, transform: 'translateY(0) scale(1)'},
        {opacity: 0, transform: 'translateY(6px) scale(.99)'}],
    {duration: 170, easing: 'ease-in', fill: 'forwards'}).finished.then(() => dialog.close(), () => {});
}

// Keep native details/summary semantics, including keyboard clicks, while
// animating their measured height in both directions and on rapid toggles.
export function animateDetails(details) {
    const summary = details.querySelector('summary');
    let animation = null, expanded = details.open;
    const click = event => {
        if (reduceMotion() || !details.animate) return;
        event.preventDefault();
        const start = details.getBoundingClientRect().height;
        expanded = animation ? !expanded : !details.open;
        animation?.cancel();
        details.open = expanded;
        const end = details.getBoundingClientRect().height;
        details.open = true; details.dataset.expanded = String(expanded);
        details.style.overflow = 'hidden';
        const current = details.animate([{height: `${start}px`}, {height: `${end}px`}],
            {duration: 240, easing: 'cubic-bezier(.2,.7,.2,1)', fill: 'both'});
        animation = current;
        current.finished.then(() => {
            if (animation !== current) return;
            details.open = expanded; current.cancel(); animation = null;
            details.style.overflow = ''; delete details.dataset.expanded;
        }, () => {});
    };
    summary.addEventListener('click', click);
    return () => { summary.removeEventListener('click', click); animation?.cancel(); };
}
