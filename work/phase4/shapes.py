"""Doodle shapes for the knuckle video (joint cross-section, fist)."""
SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920">'
SKIN, BONE, FLUID = "#f6c9a8", "#f3e6c8", "#cfe8ff"


def joint(gid="joint", cx=540, top=380, bottom=1050, s=1.0, attrs='data-in="none"'):
    w = 130 * s; gap = (bottom - top) * 0.09; mid = (top + bottom) / 2
    return (f'<g id="{gid}" {attrs}><ellipse cx="{cx}" cy="{mid}" rx="{230 * s}" ry="{150 * s}" fill="{FLUID}"/>'
            f'<path d="M{cx - w},{top} L{cx + w},{top} L{cx + w},{mid - gap - 60 * s} Q{cx + w},{mid - gap} {cx},{mid - gap} '
            f'Q{cx - w},{mid - gap} {cx - w},{mid - gap - 60 * s} Z" fill="{BONE}"/>'
            f'<path d="M{cx - w},{bottom} L{cx + w},{bottom} L{cx + w},{mid + gap + 60 * s} Q{cx + w},{mid + gap} {cx},{mid + gap} '
            f'Q{cx - w},{mid + gap} {cx - w},{mid + gap + 60 * s} Z" fill="{BONE}"/></g>')


def bubble(cx=540, cy=715, r=48, at="0.2", attrs=""):
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="white" stroke="p2" stroke-width="7" data-in="pop" data-at="{at}" {attrs}/>')


def fist(gid="fist", cx=540, base=1050, s=1.0, attrs='data-in="none"'):
    pw, fw = 170 * s, 85 * s
    out = f'<g id="{gid}" {attrs}><rect x="{cx - pw}" y="{base - 420 * s}" width="{2 * pw}" height="{420 * s}" rx="{60 * s}" fill="{SKIN}"/>'
    for k in range(4):
        x = cx - pw + k * fw
        out += f'<rect x="{x}" y="{base - 700 * s}" width="{fw}" height="{330 * s}" rx="{40 * s}" fill="{SKIN}"/>'
        out += f'<path d="M{x + 18 * s},{base - 560 * s} q{fw / 4 - 9 * s},-10 {fw / 2 - 18 * s},0" fill="none" stroke="#b97a5a" stroke-width="5"/>'
    out += (f'<rect x="{cx - pw - 70 * s}" y="{base - 380 * s}" width="{110 * s}" height="{230 * s}" rx="{50 * s}" fill="{SKIN}" '
            f'transform="rotate(-25 {cx - pw} {base - 260 * s})"/></g>')
    return out


def pop(cx, cy, at, s=1.0):
    return f'<g data-lib="burst" data-r="{int(55 * s)}" data-n="8" data-fill="p0" transform="translate({cx} {cy})" data-in="pop" data-at="{at}"/>'


def text(t, y=215, size=104, attrs='data-in="none"'):
    return f'<text x="540" y="{y}" font-family="marker" font-size="{size}" {attrs}>{t}</text>'
