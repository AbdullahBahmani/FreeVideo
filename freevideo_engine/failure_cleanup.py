"""Release failed inference frames after their diagnostic evidence is saved."""


def release_exception_frames(error):
    pending, seen, frames = [error], set(), set()
    cleared = 0
    while pending:
        current = pending.pop()
        if not isinstance(current, BaseException) or id(current) in seen:
            continue
        seen.add(id(current))
        pending.extend((current.__cause__, current.__context__))
        children = getattr(current, 'exceptions', ())
        if isinstance(children, (tuple, list)):
            pending.extend(children)
        tb = current.__traceback__
        current.__traceback__ = current.__cause__ = current.__context__ = None
        while tb is not None:
            frame = tb.tb_frame
            if id(frame) not in frames:
                frames.add(id(frame))
                try:
                    frame.clear()
                except RuntimeError:
                    pass  # The caller can still be executing; never clear it.
                else:
                    # Diagnostics inspect f_locals for tensor shapes. On
                    # CPython 3.9/3.12 that dictionary can itself retain tensors
                    # after frame.clear(), until explicitly emptied.
                    frame.f_locals.clear()
                    cleared += 1
            tb = tb.tb_next
    return cleared
