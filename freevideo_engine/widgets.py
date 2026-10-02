"""Drawn Tk primitives shared by the native launcher and the engine panel.

ttk cannot round a canvas-free surface or draw a gradient meter, so these are
painted directly. Every size, radius and hue comes from `branding`.
"""
import tkinter as tk
from tkinter import ttk

from . import branding as b


def _rgb(value):
    return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))


def _rounded(x0, y0, x1, y1, radius):
    """Corner points for a smoothed polygon; Tk splines the rest."""
    return (x0+radius, y0, x1-radius, y0, x1, y0, x1, y0+radius, x1, y1-radius, x1, y1,
            x1-radius, y1, x0+radius, y1, x0, y1, x0, y1-radius, x0, y0+radius, x0, y0)


class Card(tk.Canvas):
    """A rounded surface. Only the outline carries status; fills stay SURFACE
    so the ttk children on the card never need a second background."""

    def __init__(self, parent, *, padding=None, radius=None, fill=b.SURFACE,
                 body_style='Card.TFrame', **kwargs):
        super().__init__(parent, background=b.BACKGROUND, highlightthickness=0, width=1, **kwargs)
        self.padding = b.space(5) if padding is None else padding
        self.radius = b.RADIUS_LG if radius is None else radius
        self.outline = b.BORDER
        self.body = ttk.Frame(self, style=body_style)
        self.surface = self.create_polygon(0, 0, 1, 1, fill=fill, outline=self.outline, smooth=True)
        # A one-pixel lift just inside the flat top edge. It must not paint
        # over the outline: on a tinted card that would replace the status
        # colour with grey for the whole top border.
        self.sheen = self.create_line(0, 0, 1, 0, fill=b.SHEEN, width=1)
        self.inner = self.create_window(self.padding, self.padding, window=self.body, anchor='nw')
        self.bind('<Configure>', self.resize)
        self.body.bind('<Configure>', self.resize)

    def tint(self, outline):
        if outline != self.outline:
            self.outline = outline
            self.itemconfigure(self.surface, outline=outline)
            # A status colour is its own highlight; grey on top would mute it.
            self.itemconfigure(self.sheen, state='normal' if outline == b.BORDER else 'hidden')

    def resize(self, _=None):
        w = self.winfo_width()
        self.itemconfigure(self.inner, width=max(1, w - 2*self.padding))
        h = self.body.winfo_reqheight() + 2*self.padding
        if int(float(self.cget('height'))) != h:
            self.configure(height=h)
        h = max(h, self.winfo_height())
        r = self.radius
        self.coords(self.surface, *_rounded(1, 1, w-1, h-1, r))
        self.coords(self.sheen, r, 2, w-r, 2)
        self.itemconfigure(self.surface, outline=self.outline)
        self.itemconfigure(self.sheen, state='normal' if self.outline == b.BORDER else 'hidden')


class Radio(tk.Canvas):
    """A drawn selection dot. ttk's own indicator cannot sit on a card canvas,
    and a text glyph does not match the drawn check in the consent box."""

    def __init__(self, parent, size=None):
        self.size = b.space(4) if size is None else size
        super().__init__(parent, width=self.size, height=self.size,
                         background=b.SURFACE, highlightthickness=0)
        self.select(False)

    def select(self, selected, disabled=False):
        self.delete('all')
        radius, centre = self.size/2 - 1, self.size/2
        hue = b.DISABLED if disabled else b.ACCENT if selected else b.MUTED
        self.create_oval(centre-radius, centre-radius, centre+radius, centre+radius,
                         outline=hue, width=1.4,
                         fill=b.ACCENT_SUBTLE if selected and not disabled else b.SURFACE)
        if selected:
            inner = radius/2.4
            self.create_oval(centre-inner, centre-inner, centre+inner, centre+inner,
                             fill=hue, outline='')


class Stat(Card):
    """A figure above its label. A row of tiles reads faster than a stack of
    sentences, and the number is what the reader came for."""

    def __init__(self, parent, label, value):
        super().__init__(parent, padding=b.space(3), radius=b.RADIUS_MD)
        self.value = ttk.Label(self.body, text=value, style='Stat.Card.TLabel', justify='left')
        self.value.pack(anchor='w', fill='x')
        self.caption = ttk.Label(self.body, text=label, style='Meta.Card.TLabel', justify='left')
        self.caption.pack(anchor='w', fill='x', pady=(b.space(1), 0))
        # A figure never clips: a narrow column wraps it instead.
        self.body.bind('<Configure>', self.wrap, add='+')

    def wrap(self, event):
        for label in (self.value, self.caption):
            label.configure(wraplength=max(60, event.width))

    def show(self, label, value):
        self.caption.configure(text=label)
        self.value.configure(text=value)


class StepRail(tk.Canvas):
    """Wizard stages as pips on a hairline. A reached stage is a check, the
    current one a filled dot; the rail replaces three full-width blocks."""

    def __init__(self, parent, app, stages):
        super().__init__(parent, background=b.BACKGROUND, highlightthickness=0,
                         height=b.space(6), width=1)
        import tkinter.font as fonts
        self.app, self.stages, self.step = app, stages, 0
        self.typeface = fonts.Font(family=b.FAMILY, size=b.MICRO)
        self.strong = fonts.Font(family=b.FAMILY, size=b.MICRO, weight='bold')
        self.bind('<Configure>', lambda _: self.draw())

    def show(self, step):
        self.step = step
        self.draw()

    def draw(self):
        self.delete('all')
        width = self.winfo_width()
        if width <= 1:
            return
        y, radius, gap, link = self.winfo_height()/2, b.space(2), b.space(2), b.space(9)
        labels = [self.app.t(*stage) for stage in self.stages]
        # Measure every stage with the bold face, so the centred group keeps
        # one position instead of sliding as the current step advances.
        spans = [self.strong.measure(text) for text in labels]
        total = sum(2*radius + gap + span for span in spans) + (len(labels)-1)*(gap + link + gap)
        x = max(1., (width - total)/2.)
        for index, text in enumerate(labels):
            reached, current = index < self.step, index == self.step
            hue = b.SUCCESS if reached else b.ACCENT if current else b.BORDER
            centre = x + radius
            self.create_oval(centre-radius, y-radius, centre+radius, y+radius, outline=hue, width=1,
                             fill=b.SUCCESS_SUBTLE if reached else
                             b.ACCENT_SUBTLE if current else b.BACKGROUND)
            if reached:
                self.create_line(centre-3.5, y, centre-1, y+2.5, centre+3.5, y-3.5, fill=b.SUCCESS,
                                 width=2, capstyle='round', joinstyle='round')
            elif current:
                self.create_oval(centre-2, y-2, centre+2, y+2, fill=b.ACCENT, outline='')
            self.create_text(centre + radius + gap, y, anchor='w', text=text,
                             fill=b.SUCCESS if reached else b.ACCENT if current else b.MUTED,
                             font=self.strong if current else self.typeface)
            x += 2*radius + gap + spans[index]
            if index + 1 < len(labels):
                self.create_line(x + gap, y, x + gap + link, y,
                                 fill=b.ACCENT if reached else b.BORDER, width=1)
                x += gap + link + gap


class PillButton(tk.Canvas):
    """The page's primary action. ttk cannot round a button corner, so this
    draws one and keeps the ttk.Button surface the launcher already calls:
    invoke, state, configure(text=, width=) and the pack geometry."""

    def __init__(self, parent, command=None):
        super().__init__(parent, background=b.BACKGROUND, highlightthickness=0, width=1, height=1)
        import tkinter.font as fonts
        self.command, self.label, self.chars = command, '', 0
        self.disabled = self.hovered = self.pressed = self.focused = False
        self.typeface = fonts.Font(family=b.FAMILY, size=b.BODY, weight='bold')
        self.surface = self.create_polygon(0, 0, 1, 1, smooth=True, fill=b.ACCENT, outline=b.ACCENT)
        self.caption = self.create_text(0, 0, text='', fill=b.BACKGROUND, font=self.typeface)
        super().configure(cursor='hand2', takefocus=1)
        # Repacking can drop this button under a stationary pointer, which
        # sends Enter without a matching Leave. Every crossing and every move
        # therefore re-reads where the pointer actually is.
        self.bind('<Configure>', lambda _: self.hover())
        self.bind('<Enter>', lambda _: self.hover())
        self.bind('<Leave>', lambda _: self.hover())
        self.bind('<Button-1>', lambda _: self.mark('pressed', True))
        self.bind('<ButtonRelease-1>', self.released)
        self.bind('<FocusIn>', lambda _: self.mark('focused', True))
        self.bind('<FocusOut>', lambda _: self.mark('focused', False))
        for key in ('<Return>', '<space>'):
            self.bind(key, self.activated)
        self.measure()

    def configure(self, cnf=None, **kwargs):
        resize = False
        if 'text' in kwargs:
            self.label, resize = kwargs.pop('text'), True
        if 'width' in kwargs:
            self.chars, resize = kwargs.pop('width'), True
        result = super().configure(cnf, **kwargs) if (cnf or kwargs) else None
        if resize:
            self.measure()
        return result
    config = configure

    def cget(self, key):
        return self.label if key == 'text' else self.chars if key == 'width' else super().cget(key)

    def measure(self):
        text = self.typeface.measure(self.label)
        requested = self.typeface.measure('0') * self.chars if self.chars else text
        super().configure(width=max(text, requested) + 2*b.space(6),
                          height=self.typeface.metrics('linespace') + 2*b.space(3))
        self.draw()

    def mark(self, name, value):
        setattr(self, name, value)
        self.draw()

    def hover(self, _=None):
        x, y = self.winfo_pointerxy()
        self.hovered = (self.winfo_rootx() <= x < self.winfo_rootx() + self.winfo_width()
                        and self.winfo_rooty() <= y < self.winfo_rooty() + self.winfo_height())
        self.draw()

    def released(self, _=None):
        was_pressed, self.pressed = self.pressed, False
        self.draw()
        if was_pressed and self.hovered:
            self.invoke()

    def activated(self, _=None):
        self.invoke()
        return 'break'

    def invoke(self):
        if not self.disabled and self.command is not None:
            return self.command()

    def state(self, states=None):
        for name in states or ():
            if name in ('disabled', '!disabled'):
                self.disabled = not name.startswith('!')
        if states:
            self.draw()
        return ('disabled',) if self.disabled else ()

    def instate(self, states, *_):
        return all((name == 'disabled') == self.disabled for name in states)

    def draw(self):
        w = self.winfo_width() if self.winfo_width() > 1 else self.winfo_reqwidth()
        h = self.winfo_height() if self.winfo_height() > 1 else self.winfo_reqheight()
        fill = (b.ACCENT_DISABLED if self.disabled else
                b.ACCENT if self.pressed else
                b.ACCENT_HOVER if self.hovered else b.ACCENT)
        self.coords(self.surface, *_rounded(1, 1, w-1, h-1, b.RADIUS_MD))
        self.itemconfigure(self.surface, fill=fill,
                           outline=b.TEXT if self.focused and not self.disabled else fill)
        self.coords(self.caption, w/2, h/2)
        self.itemconfigure(self.caption, text=self.label,
                           fill=b.ACCENT_DISABLED_TEXT if self.disabled else b.BACKGROUND)


class Progress(tk.Canvas):
    """A rounded meter. Determinate work ramps accent to teal and finishes in
    SUCCESS; unmeasured work sweeps, instead of showing an empty track."""

    def __init__(self, parent, *, background=b.SURFACE, height=None, subdued=False):
        self.values = dict(maximum=1, value=0, mode='determinate', tint=None)
        self.offset, self.timer, self.subdued = 0., None, subdued
        super().__init__(parent, background=background,
                         height=b.space(2) + 2 if height is None else height, width=1, highlightthickness=0)
        self.bind('<Configure>', self.draw)
        self.bind('<Destroy>', lambda _: self.stop())

    def configure(self, cnf=None, **kwargs):
        for name in ('maximum', 'value', 'mode', 'tint'):
            if name in kwargs:
                self.values[name] = kwargs.pop(name)
        result = super().configure(cnf, **kwargs) if (kwargs or cnf) else None
        if self.values['mode'] != 'indeterminate':
            self.stop()
        self.draw()
        return result

    def __getitem__(self, key):
        return self.values[key] if key in self.values else super().__getitem__(key)

    def start(self, interval=40):
        self.values['mode'] = 'indeterminate'
        if self.timer is None:
            self.timer = self.after(interval, self.advance, interval)

    def advance(self, interval):
        self.timer = None
        if not self.winfo_exists():
            return
        self.offset = (self.offset + .018) % 1
        self.draw()
        self.timer = self.after(interval, self.advance, interval)

    def stop(self):
        if self.timer is not None:
            try:
                self.after_cancel(self.timer)
            except tk.TclError:
                pass
            self.timer = None
        self.offset = 0.

    def ramp(self, start, end, y, thickness, target, flat=False):
        length = max(0., end - start)
        if length <= 0:
            return
        destination = _rgb(target)
        origin = destination if flat else _rgb(b.ACCENT)
        parts = max(1, min(32, int(length/8)))
        for index in range(parts):
            mix = index / max(1, parts-1)
            color = '#%02x%02x%02x' % tuple(round(a+(z-a)*mix) for a, z in zip(origin, destination))
            self.create_line(start+length*index/parts, y, start+length*(index+1)/parts, y,
                             fill=color, width=thickness, capstyle='round')

    def draw(self, _=None):
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        if w <= h:
            return
        radius = h/2
        self.create_line(radius, radius, w-radius, radius, fill=b.RAISED, width=h, capstyle='round')
        track = w - h
        if self.values['mode'] == 'indeterminate':
            span = track * .32
            start = radius - span + (track + span) * self.offset
            self.ramp(max(radius, start), min(w-radius, start+span), radius, h, self.values['tint'] or b.ACCENT_RAMP)
            return
        maximum = self.values['maximum']
        ratio = max(0, min(1, self.values['value']/maximum)) if maximum else 0
        if not ratio:
            return
        if self.subdued:
            self.ramp(radius, radius + track*ratio, radius, h, b.ACCENT_DIM, flat=True)
            return
        # A finished or flagged meter is one solid colour; only work in
        # progress ramps, so the two states never look like the same bar.
        target = self.values['tint'] or (b.SUCCESS if ratio >= 1 else b.ACCENT_RAMP)
        self.ramp(radius, radius + track*ratio, radius, h, target,
                  flat=ratio >= 1 or self.values['tint'] is not None)
