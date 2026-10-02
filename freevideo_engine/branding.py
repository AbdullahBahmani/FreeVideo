"""Shared native UI palette, type scale and bundled artwork.

One table defines every surface, hue, text size, radius and gap the native
views may use, so a new panel picks an existing step instead of inventing a
shade. No imaging dependency at runtime.
"""
import math
from pathlib import Path

# Surfaces, from the window backdrop up to a hovered control. A navy tint
# runs through every step; the content pane sits one step above the window.
BACKGROUND = '#111720'            # Window, sidebar and input wells.
CANVAS = '#161e29'                # Content pane of the launcher.
SURFACE = '#1a222e'
RAISED = '#212a37'
HOVER = '#2a3341'
BORDER = '#2a3443'
SHEEN = '#35404e'                 # Control outlines; one-pixel lift on a card's edge.

# Ink. MUTED carries secondary copy; DISABLED never states anything new.
TEXT = '#e7edf7'
MUTED = '#a5b3c6'
DISABLED = '#7f8ea3'

# One hue per meaning. A SUBTLE value is the backdrop for its own status only;
# it is not decoration for unrelated controls. DANGER matches the web theme's
# --fv-danger so a failure reads the same in both interfaces.
ACCENT = '#6db8fa'
ACCENT_HOVER = '#91cbff'
ACCENT_RAMP = '#82dcd3'          # Gradient destination for a progress fill.
ACCENT_DIM = '#406c93'           # A meter that is subordinate to another one.
ACCENT_SUBTLE = '#1d3248'
ACCENT_DISABLED = '#243a52'
ACCENT_DISABLED_TEXT = '#8ba0b6'
SUCCESS = '#76d9b3'
SUCCESS_SUBTLE = '#1f3636'
WARNING = '#e0b062'
DANGER = '#f09aa2'
DANGER_SUBTLE = '#30212a'

# Type: five steps, not one per widget. BODY stays at Segoe UI's native
# interface size. Raising it reflows every view, and the launcher must still
# fit its 680x540 minimum, where the real-Tk tests assert that the primary
# button stays inside the window; rerun those before changing BODY.
FAMILY = 'Segoe UI'
MICRO, BODY, STRONG, SECTION, HERO = 9, 10, 12, 15, 22
MONO = 'Consolas'                # Retained log output only.

# Three radii and one spacing unit. Gaps are multiples of STEP.
RADIUS_SM, RADIUS_MD, RADIUS_LG = 8, 12, 16
STEP = 4


def space(units):
    """Vertical and horizontal gaps come from the same four-pixel rhythm."""
    return STEP * units


def rgb(value):
    return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))


def _mix(under, over, alpha):
    return tuple(round(a + (b - a) * alpha) for a, b in zip(under, over))


def _area(x, y, rect, radius, inset, samples=4):
    """Antialiased share of one pixel covered by a rounded rectangle.

    Tk's boolean per-pixel transparency cannot smooth a corner, so shapes are
    baked over the surface they sit on and the coverage is supersampled here.
    The rectangle is explicit, so an image may carry a gap beside its shape.
    """
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1)/2., (y0 + y1)/2.
    half_w, half_h = (x1 - x0)/2. - inset, (y1 - y0)/2. - inset
    r = max(0., radius - inset)
    covered = 0
    for row in range(samples):
        py = abs(y + (row + .5)/samples - cy)
        for column in range(samples):
            px = abs(x + (column + .5)/samples - cx)
            if px > half_w or py > half_h:
                continue
            dx, dy = px - (half_w - r), py - (half_h - r)
            covered += 1 if dx <= 0 or dy <= 0 else dx*dx + dy*dy <= r*r
    return covered / float(samples*samples)


def _stroke(x, y, points, thickness, samples=4):
    """Antialiased coverage of a polyline, for the check inside an indicator."""
    half = thickness/2.
    covered = 0
    for row in range(samples):
        py = y + (row + .5)/samples
        for column in range(samples):
            px = x + (column + .5)/samples
            best = 1e9
            for (x0, y0), (x1, y1) in zip(points, points[1:]):
                dx, dy = x1-x0, y1-y0
                length = dx*dx + dy*dy
                t = 0. if not length else max(0., min(1., ((px-x0)*dx + (py-y0)*dy) / length))
                best = min(best, math.hypot(px - (x0 + t*dx), py - (y0 + t*dy)))
            covered += max(0., min(1., half + .5 - best))
    return covered / float(samples*samples)


def rounded_photo(master, width, height, radius, fill, backdrop, outline=None, check=None, rect=None):
    """A rounded rectangle, and optionally a check mark, baked over a backdrop."""
    import tkinter as tk
    under, face = rgb(backdrop), rgb(fill)
    edge = rgb(outline) if outline else face
    mark = rgb(check[0]) if check else None
    points = check[1] if check else ()
    rect = (0, 0, width, height) if rect is None else rect
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            colour = _mix(under, edge, _area(x, y, rect, radius, 0.))
            colour = _mix(colour, face, _area(x, y, rect, radius, 1.))
            if mark:
                colour = _mix(colour, mark, _stroke(x, y, points, 2.2))
            row.append('#%02x%02x%02x' % colour)
        rows.append('{' + ' '.join(row) + '}')
    image = tk.PhotoImage(master=master, width=width, height=height)
    image.put(' '.join(rows))
    return image


def _retain(master, images):
    """Tk discards an image whose Python object is collected."""
    kept = getattr(master, 'freevideo_images', None)
    if kept is None:
        kept = master.freevideo_images = []
    kept.extend(images)


def _image_element(style, master, element, faces, order, *, radius, backdrop, padding=0):
    """Replace a themed border with a 9-slice rounded image, one per state.

    ttk cannot round a corner. Substituting the outermost element of an
    existing layout keeps every ttk state, padding and label behaviour.
    `order` lists state specifications most specific first, as ttk matches
    them in order; the default face is drawn when none applies.
    """
    import tkinter as tk
    size = 2*radius + 6
    images = {name: rounded_photo(master, size, size, radius, fill, backdrop, outline)
              for name, (fill, outline) in faces.items()}
    _retain(master, images.values())
    # Each entry stays one (state..., image) tuple; ttk unpacks it that way.
    specs = [tuple(list(states) + [images[name]]) for states, name in order]
    try:
        style.element_create(element, 'image', images['normal'], *specs,
                             # border is the 9-slice split only. Left implicit,
                             # ttk also insets the children by it and every
                             # control grows; a tab needs its own padding back,
                             # because the element it replaces carried it.
                             border=radius, padding=padding, sticky='nsew')
    except tk.TclError:
        return False
    return True


BUTTON_STATES = ((('disabled',), 'disabled'), (('pressed',), 'pressed'),
                 (('active',), 'active'), (('focus',), 'focus'))


def _rounded_buttons(style, master):
    """Round every ttk button: on the window, on a card, and the accent one."""
    faces = lambda fill, hover, pressed, off, edge=BORDER: dict(
        normal=(fill, edge), active=(hover, edge), pressed=(pressed, ACCENT),
        disabled=(off, edge), focus=(fill, ACCENT))
    plans = (
        ('FreeVideo.button', 'TButton', BACKGROUND, faces(RAISED, HOVER, RAISED, SURFACE)),
        ('FreeVideoCard.button', 'Card.TButton', SURFACE, faces(RAISED, HOVER, RAISED, SURFACE)),
        ('FreeVideoPrimary.button', 'Primary.TButton', BACKGROUND,
         dict(normal=(ACCENT, ACCENT), active=(ACCENT_HOVER, ACCENT_HOVER), pressed=(ACCENT, ACCENT),
              disabled=(ACCENT_DISABLED, ACCENT_DISABLED), focus=(ACCENT, TEXT))),
        ('FreeVideoQuiet.button', 'Quiet.TButton', BACKGROUND,
         dict(normal=(BACKGROUND, BACKGROUND), active=(RAISED, RAISED), pressed=(RAISED, RAISED),
              disabled=(BACKGROUND, BACKGROUND), focus=(BACKGROUND, ACCENT))),
    )
    for element, target, backdrop, states in plans:
        if _image_element(style, master, element, states, BUTTON_STATES,
                          radius=RADIUS_SM, backdrop=backdrop):
            style.layout(target, [(element, {'sticky': 'nsew', 'children': [
                ('Button.focus', {'sticky': 'nsew', 'children': [
                    ('Button.padding', {'sticky': 'nsew', 'children': [
                        ('Button.label', {'sticky': 'nsew'})]})]})]})])


def _rounded_fields(style, master):
    """A text field is a rounded recess whose edge lights up on focus."""
    order = ((('disabled',), 'disabled'), (('focus',), 'focus'))
    plans = (('FreeVideo.field', 'TEntry', BACKGROUND, SURFACE),
             ('FreeVideoWell.field', 'Well.TEntry', SURFACE, BACKGROUND))
    for element, target, backdrop, fill in plans:
        faces = dict(normal=(fill, BORDER), focus=(fill, ACCENT), disabled=(backdrop, BORDER))
        if _image_element(style, master, element, faces, order,
                          radius=RADIUS_SM, backdrop=backdrop):
            style.layout(target, [(element, {'sticky': 'nsew', 'children': [
                ('Entry.padding', {'sticky': 'nsew', 'children': [
                    ('Entry.textarea', {'sticky': 'nsew'})]})]})])


def _rounded_combobox(style, master):
    """clam hangs the arrow outside the field, which reads as a second square
    box beside a rounded one. Round the field and move the arrow inside it."""
    element = 'FreeVideo.combofield'
    faces = dict(normal=(SURFACE, BORDER), focus=(SURFACE, ACCENT),
                 active=(SURFACE, HOVER), disabled=(BACKGROUND, BORDER))
    order = ((('disabled',), 'disabled'), (('focus',), 'focus'), (('hover',), 'active'))
    if _image_element(style, master, element, faces, order, radius=RADIUS_SM, backdrop=BACKGROUND):
        style.layout('TCombobox', [(element, {'sticky': 'nswe', 'children': [
            ('Combobox.downarrow', {'side': 'right', 'sticky': 'ns'}),
            ('Combobox.padding', {'sticky': 'nswe', 'children': [
                ('Combobox.textarea', {'sticky': 'nswe'})]})]})])


def _rounded_tabs(style, master):
    """Notebook tabs read as one segmented control rather than filing tabs."""
    element = 'FreeVideo.tab'
    faces = dict(normal=(BACKGROUND, BACKGROUND), selected=(SURFACE, BORDER),
                 active=(RAISED, RAISED), disabled=(BACKGROUND, BACKGROUND))
    order = ((('disabled',), 'disabled'), (('selected',), 'selected'), (('active',), 'active'))
    if _image_element(style, master, element, faces, order, radius=RADIUS_SM, backdrop=BACKGROUND,
                      padding=(space(5), space(2) + 1)):
        style.layout('TNotebook.Tab', [(element, {'sticky': 'nswe', 'children': [
            ('Notebook.padding', {'side': 'top', 'sticky': 'nswe', 'children': [
                ('Notebook.focus', {'side': 'top', 'sticky': 'nswe', 'children': [
                    ('Notebook.label', {'side': 'top', 'sticky': ''})]})]})]})])


def _rounded_checkbutton(style, master):
    """An accent box with a drawn check, instead of clam's flat square."""
    import tkinter as tk
    size, radius, gap = 17, 5, space(2)
    # An image element ignores its own padding here, so the gap before the
    # label is part of the picture: the strip is simply the window colour.
    box = (0, 0, size, size)
    tick = ((.26*size, .54*size), (.43*size, .72*size), (.76*size, .30*size))
    draw = lambda fill, edge, check=None: rounded_photo(
        master, size + gap, size, radius, fill, BACKGROUND, edge, check, rect=box)
    states = dict(off=draw(BACKGROUND, BORDER), hover=draw(BACKGROUND, ACCENT),
                  on=draw(ACCENT, ACCENT, (BACKGROUND, tick)),
                  off_disabled=draw(BACKGROUND, DISABLED),
                  on_disabled=draw(ACCENT_DISABLED, ACCENT_DISABLED, (ACCENT_DISABLED_TEXT, tick)))
    _retain(master, states.values())
    try:
        style.element_create('FreeVideo.checkindicator', 'image', states['off'],
                             ('disabled', 'selected', states['on_disabled']),
                             ('disabled', states['off_disabled']),
                             ('selected', states['on']),
                             ('active', states['hover']), sticky='')
    except tk.TclError:
        return
    for target in ('TCheckbutton', 'TRadiobutton'):
        style.layout(target, [(target.replace('T', '') + '.padding', {'sticky': 'nswe', 'children': [
            ('FreeVideo.checkindicator', {'side': 'left', 'sticky': ''}),
            (target.replace('T', '') + '.focus', {'side': 'left', 'sticky': 'w', 'children': [
                (target.replace('T', '') + '.label', {'sticky': 'nswe'})]})]})])


def theme(window):
    import tkinter as tk
    from tkinter import ttk
    window.configure(bg=BACKGROUND)
    window.freevideo_icon = tk.PhotoImage(master=window, file=str(Path(__file__).with_name('assets') / 'icon.png'))
    window.iconphoto(True, window.freevideo_icon)
    style = ttk.Style(window)
    style.theme_use('clam')
    style.configure('.', background=BACKGROUND, foreground=TEXT, font=(FAMILY, BODY),
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, focuscolor=ACCENT)
    style.configure('TFrame', background=BACKGROUND)
    style.configure('TLabel', background=BACKGROUND)
    style.configure('Title.TLabel', font=(FAMILY, HERO, 'bold'))
    style.configure('Section.TLabel', font=(FAMILY, SECTION, 'bold'))
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('Meta.TLabel', foreground=MUTED, font=(FAMILY, MICRO))
    style.configure('Danger.TLabel', foreground=DANGER)
    # Text placed on a card repeats the card's fill; clam draws no inheritance.
    style.configure('Card.TFrame', background=SURFACE)
    # A retained failure gets its own surface so it reads as the page's
    # subject rather than as loose text under the progress card.
    style.configure('Alert.Card.TFrame', background=DANGER_SUBTLE)
    style.configure('Card.TLabel', background=SURFACE)
    style.configure('Heading.Card.TLabel', background=SURFACE, font=(FAMILY, STRONG, 'bold'))
    style.configure('Hero.Card.TLabel', background=SURFACE, font=(FAMILY, HERO, 'bold'))
    style.configure('ProgressTitle.Card.TLabel', background=SURFACE, font=(FAMILY, SECTION, 'bold'))
    style.configure('Muted.Card.TLabel', background=SURFACE, foreground=MUTED, font=(FAMILY, BODY))
    style.configure('Meta.Card.TLabel', background=SURFACE, foreground=MUTED, font=(FAMILY, MICRO))
    style.configure('Accent.Card.TLabel', background=SURFACE, foreground=ACCENT, font=(FAMILY, BODY, 'bold'))
    style.configure('Stat.Card.TLabel', background=SURFACE, font=(FAMILY, SECTION, 'bold'))
    # Retained for the tabbed engine panel's progress cards.
    style.configure('Progress.TLabel', background=SURFACE, font=(FAMILY, BODY, 'bold'))
    style.configure('ProgressMeta.TLabel', background=SURFACE, foreground=MUTED, font=(FAMILY, MICRO))
    style.configure('TButton', padding=(space(4), space(2) + 1), background=RAISED, borderwidth=1, relief='flat')
    style.map('TButton', background=[('disabled', SURFACE), ('active', HOVER)],
              foreground=[('disabled', DISABLED), ('active', TEXT)])
    style.configure('Quiet.TButton', background=BACKGROUND, borderwidth=0, padding=(space(2), space(2)))
    style.map('Quiet.TButton', background=[('disabled', BACKGROUND), ('active', RAISED)],
              foreground=[('disabled', DISABLED), ('active', TEXT)])
    # A link carries no border or fill, so only its colour reacts.
    style.configure('Link.TButton', background=BACKGROUND, foreground=ACCENT, borderwidth=0,
                    padding=(0, space(1)), font=(FAMILY, BODY))
    style.map('Link.TButton', background=[('active', BACKGROUND), ('disabled', BACKGROUND)],
              foreground=[('active', ACCENT_HOVER), ('disabled', DISABLED)])
    style.configure('Primary.TButton', padding=(space(5), space(3)), foreground=BACKGROUND, background=ACCENT,
                    bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT)
    style.map('Primary.TButton', background=[('disabled', ACCENT_DISABLED), ('active', ACCENT_HOVER)],
              foreground=[('disabled', ACCENT_DISABLED_TEXT), ('active', BACKGROUND)])
    style.configure('TEntry', padding=space(2), fieldbackground=SURFACE, insertcolor=TEXT)
    style.map('TEntry', bordercolor=[('focus', ACCENT)], lightcolor=[('focus', ACCENT)], darkcolor=[('focus', ACCENT)])
    # An input that sits on a card reads as a recess, so it goes a step darker
    # than the card rather than matching it and losing its own edge.
    style.configure('Well.TEntry', padding=space(2), fieldbackground=BACKGROUND, insertcolor=TEXT)
    style.map('Well.TEntry', fieldbackground=[('disabled', SURFACE)], bordercolor=[('focus', ACCENT)],
              lightcolor=[('focus', ACCENT)], darkcolor=[('focus', ACCENT)])
    # clam gives the arrow its own bordered box. Blend it into the field so the
    # control reads as one rounded shape.
    style.configure('TCombobox', padding=space(2) - 2, fieldbackground=SURFACE, arrowcolor=MUTED,
                    background=SURFACE, bordercolor=SURFACE, lightcolor=SURFACE, darkcolor=SURFACE,
                    relief='flat', arrowsize=space(3) + 1)
    style.map('TCombobox', fieldbackground=[('readonly', SURFACE)], foreground=[('readonly', TEXT)],
              background=[('readonly', SURFACE), ('disabled', BACKGROUND), ('active', SURFACE)],
              bordercolor=[('readonly', SURFACE), ('disabled', BACKGROUND), ('active', SURFACE)],
              lightcolor=[('readonly', SURFACE), ('disabled', BACKGROUND), ('active', SURFACE)],
              darkcolor=[('readonly', SURFACE), ('disabled', BACKGROUND), ('active', SURFACE)],
              arrowcolor=[('disabled', DISABLED), ('active', ACCENT), ('!disabled', MUTED)])
    for name in ('TCheckbutton', 'TRadiobutton'):
        style.configure(name, background=BACKGROUND, indicatorbackground=RAISED, indicatorforeground=ACCENT)
        style.map(name, background=[('active', BACKGROUND)], foreground=[('disabled', DISABLED)],
                  indicatorbackground=[('selected', ACCENT), ('active', BORDER)])
    style.configure('TNotebook', borderwidth=0)
    style.configure('TNotebook.Tab', padding=(space(5) + 2, space(3)), background=BACKGROUND)
    style.map('TNotebook.Tab', background=[('selected', SURFACE)], foreground=[('selected', ACCENT)])
    for name in ('Horizontal.TProgressbar', 'FreeVideo.Horizontal.TProgressbar'):
        style.configure(name, background=ACCENT, troughcolor=RAISED, borderwidth=0,
                        lightcolor=ACCENT, darkcolor=ACCENT, thickness=6)
    style.configure('Vertical.TScrollbar', background=RAISED, troughcolor=BACKGROUND,
                    arrowcolor=MUTED, borderwidth=0)
    _rounded_buttons(style, window)
    _rounded_fields(style, window)
    _rounded_combobox(style, window)
    _rounded_tabs(style, window)
    _rounded_checkbutton(style, window)
    # A thumb without stepper arrows; the wizard scrolls with the wheel.
    style.layout('Wizard.Vertical.TScrollbar', [('Vertical.Scrollbar.trough', {'sticky': 'ns', 'children': [
        ('Vertical.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])
    style.configure('Wizard.Vertical.TScrollbar', width=space(2) - 1, background=RAISED, troughcolor=BACKGROUND,
                    borderwidth=0, relief='flat', lightcolor=RAISED, darkcolor=RAISED, bordercolor=BACKGROUND)
    style.map('Wizard.Vertical.TScrollbar', background=[('active', BORDER), ('!active', RAISED)])
    return style


def wordmark(parent, width=228):
    import tkinter as tk
    from tkinter import ttk
    # This PNG is a rasterization of web/assets/freevideo.svg. Tk reads PNG
    # directly, including in the standalone EXE; Pillow/Torch are not imported.
    original = tk.PhotoImage(master=parent, file=str(Path(__file__).with_name('assets') / 'wordmark.png'))
    ratio = max(1, round(original.width() / width))
    photo = original.subsample(ratio)
    label = ttk.Label(parent, image=photo, text='FreeVideo')
    label.image = photo  # Tk does not retain the Python image object.
    return label
