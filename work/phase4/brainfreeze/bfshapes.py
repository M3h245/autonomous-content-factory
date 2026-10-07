"""Doodle shapes for the brain-freeze video (glass of ice water, cone, head, ice cube)."""
SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920">'
WATER, GLASS, CONE, SCOOP, SKIN = "#cfe8ff", "#ffffff", "#e8b06a", "#f7c6d9", "#f6c9a8"


def glass(gid="glass", cx=540, base=1300, h=760, w=420, straw=True, attrs='data-in="none"', straw_h=220):
    top = base - h
    o = (f'<g id="{gid}" {attrs}><path d="M{cx - w / 2},{top} L{cx + w / 2},{top} L{cx + w / 2 - 50},{base} L{cx - w / 2 + 50},{base} Z" fill="{GLASS}"/>'
         f'<path d="M{cx - w / 2 + 14},{top + 120} L{cx + w / 2 - 14},{top + 120} L{cx + w / 2 - 54},{base - 14} L{cx - w / 2 + 54},{base - 14} Z" fill="{WATER}" stroke="none"/>')
    for dx, dy in ((-90, 210), (40, 250), (-20, 380)):
        o += f'<rect x="{cx + dx - 55}" y="{top + dy - 55}" width="110" height="110" rx="18" fill="#ffffff" transform="rotate({dx / 6} {cx + dx} {top + dy})"/>'
    if straw:
        o += f'<path d="M{cx + 60},{base - 60} L{cx + 140},{top - straw_h} L{cx + 250},{top - straw_h - 40}" fill="none" stroke="#e8452c" stroke-width="26"/>'
    return o + "</g>"


def cone(gid="cone", cx=540, base=1350, s=1.0, attrs='data-in="none"'):
    w, h = 300 * s, 520 * s
    top = base - h
    o = f'<g id="{gid}" {attrs}><path d="M{cx - w / 2},{top} L{cx + w / 2},{top} L{cx},{base} Z" fill="{CONE}"/>'
    o += f'<path d="M{cx - w / 4},{top + 40 * s} L{cx + w / 8},{top + 260 * s} M{cx + w / 4},{top + 40 * s} L{cx - w / 8},{top + 260 * s}" fill="none"/>'
    o += f'<circle cx="{cx - 70 * s}" cy="{top - 60 * s}" r="{120 * s}" fill="{SCOOP}"/><circle cx="{cx + 80 * s}" cy="{top - 70 * s}" r="{115 * s}" fill="#fff3c4"/>'
    o += f'<circle cx="{cx}" cy="{top - 190 * s}" r="{120 * s}" fill="#c9a27e"/>'
    return o + "</g>"


def head(gid="head", cx=540, cy=900, r=330, face="shock", attrs='data-in="none"'):
    o = f'<g id="{gid}" {attrs}><circle cx="{cx}" cy="{cy}" r="{r}" fill="{SKIN}"/>'
    ex, ey = r * 0.33, r * 0.05
    if face == "shock":
        o += (f'<circle cx="{cx - ex}" cy="{cy + ey}" r="{r * 0.09}" fill="#ffffff"/><circle cx="{cx + ex}" cy="{cy + ey}" r="{r * 0.09}" fill="#ffffff"/>'
              f'<circle cx="{cx - ex}" cy="{cy + ey}" r="{r * 0.035}" fill="#1d1b1a"/><circle cx="{cx + ex}" cy="{cy + ey}" r="{r * 0.035}" fill="#1d1b1a"/>'
              f'<ellipse cx="{cx}" cy="{cy + r * 0.45}" rx="{r * 0.16}" ry="{r * 0.2}" fill="#7a2e2e"/>')
    else:   # wince
        o += (f'<path d="M{cx - ex - 40},{cy + ey - 20} L{cx - ex + 40},{cy + ey} L{cx - ex - 40},{cy + ey + 20}" fill="none" stroke-width="10"/>'
              f'<path d="M{cx + ex + 40},{cy + ey - 20} L{cx + ex - 40},{cy + ey} L{cx + ex + 40},{cy + ey + 20}" fill="none" stroke-width="10"/>'
              f'<path d="M{cx - r * 0.25},{cy + r * 0.48} q{r * 0.12},-{r * 0.1} {r * 0.25},0 q{r * 0.12},{r * 0.1} {r * 0.25},0" fill="none" stroke-width="10"/>')
    return o + "</g>"


def pain(cx, cy, at="0.2", s=1.0, extra=""):
    """zig-zag pain lines (forehead)"""
    return (f'<path d="M{cx - 120 * s},{cy} l{40 * s},-{40 * s} l{40 * s},{40 * s} l{40 * s},-{40 * s} l{40 * s},{40 * s} l{40 * s},-{40 * s} l{40 * s},{40 * s}" '
            f'fill="none" stroke="#3b82c4" stroke-width="14" data-in="draw" data-at="{at}" {extra}/>')


def cube(gid, cx, cy, s=1.0, attrs='data-in="none"'):
    return (f'<g id="{gid}" {attrs}><rect x="{cx - 110 * s}" y="{cy - 110 * s}" width="{220 * s}" height="{220 * s}" rx="{30 * s}" fill="#e7f5ff"/>'
            f'<path d="M{cx - 60 * s},{cy - 70 * s} L{cx - 10 * s},{cy - 70 * s}" fill="none" stroke="#ffffff" stroke-width="12"/></g>')


def text(t, y=215, size=104, x=540, attrs='data-in="none"', fill=None):
    f = f' fill="{fill}"' if fill else ""
    return f'<text x="{x}" y="{y}" font-family="marker" font-size="{size}"{f} {attrs}>{t}</text>'
