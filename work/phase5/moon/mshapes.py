"""Doodle shapes for the Moon-illusion video (Phase 5 fresh run 2)."""
SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920">'
MOON, CRATER, NIGHT = "#fff3b0", "#e9d77a", "#1d2b53"


def moon(gid, cx, cy, r, attrs='data-in="none"', outline=True, face=None):
    o = f'<g id="{gid}" {attrs}><circle cx="{cx}" cy="{cy}" r="{r}" fill="{MOON}"' + ("" if outline else ' data-outline="none"') + "/>"
    for dx, dy, rr in ((-0.35, -0.25, 0.16), (0.3, 0.1, 0.12), (-0.05, 0.38, 0.1), (0.38, -0.38, 0.07)):
        o += f'<circle cx="{cx + dx * r}" cy="{cy + dy * r}" r="{rr * r}" fill="{CRATER}" data-outline="none"/>'
    if face == "smug":
        o += (f'<path d="M{cx - 0.3 * r},{cy - 0.05 * r} q{0.1 * r},{-0.08 * r} {0.2 * r},0 M{cx + 0.1 * r},{cy - 0.05 * r} '
              f'q{0.1 * r},{-0.08 * r} {0.2 * r},0 M{cx - 0.25 * r},{cy + 0.25 * r} q{0.25 * r},{0.15 * r} {0.5 * r},0" fill="none" stroke="#1d1b1a" stroke-width="{max(5, 0.03 * r)}"/>')
    return o + "</g>"


def skyline(y=1040, attrs='data-in="none"', gid="town", fill="#2c3e66"):
    """Rooftops and a tree along the horizon (filled, no outline — reads on paper and on night backgrounds)."""
    o = f'<g id="{gid}" {attrs}>'
    for x, w, h in ((80, 140, 170), (232, 112, 240), (356, 160, 140), (528, 106, 210), (646, 180, 160), (838, 160, 230)):
        o += f'<rect x="{x}" y="{y - h}" width="{w}" height="{h}" fill="{fill}" data-outline="none"/>'
        o += f'<path d="M{x - 10},{y - h} L{x + w / 2},{y - h - 60} L{x + w + 10},{y - h} Z" fill="{fill}" data-outline="none"/>'
    o += f'<rect x="76" y="{y}" width="928" height="16" fill="{fill}" data-outline="none"/>'
    return o + "</g>"


def text(t, y=215, size=104, x=540, attrs='data-in="none"', family="marker", fill=None):
    return f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}"' + (f' fill="{fill}"' if fill else "") + f" {attrs}>{t}</text>"


def stars(pts, at="0.2", fill="#fff3b0"):
    return "".join(f'<g data-lib="sparkle" data-fill="{fill}" transform="translate({x} {y}) scale({s})" data-in="pop" data-at="{at}"/>'
                   for x, y, s in pts)


def camera(cx, cy, s=1.0, attrs='data-in="pop" data-at="0.2"', gid="cam"):
    return (f'<g id="{gid}" {attrs}><rect x="{cx - 150 * s}" y="{cy - 95 * s}" width="{300 * s}" height="{190 * s}" rx="{26 * s}" fill="#5b6475"/>'
            f'<rect x="{cx - 60 * s}" y="{cy - 125 * s}" width="{120 * s}" height="{40 * s}" rx="{10 * s}" fill="#5b6475"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{66 * s}" fill="#222b3a"/><circle cx="{cx}" cy="{cy}" r="{38 * s}" fill="#7ab3ef"/>'
            f'<circle cx="{cx + 100 * s}" cy="{cy - 60 * s}" r="{12 * s}" fill="#ffd23f"/></g>')


def hand_nail(cx, cy, s=1.0, attrs='data-in="slide-up" data-at="0.3"', gid="hand"):
    """An outstretched index finger pointing up, fingernail at (cx, cy)."""
    return (f'<g id="{gid}" {attrs}><rect x="{cx - 46 * s}" y="{cy - 40 * s}" width="{92 * s}" height="{560 * s}" rx="{44 * s}" fill="#f6c9a8"/>'
            f'<rect x="{cx - 30 * s}" y="{cy - 26 * s}" width="{60 * s}" height="{70 * s}" rx="{22 * s}" fill="#ffe8de"/>'
            f'<path d="M{cx - 40 * s},{cy + 120 * s} q{40 * s},{-12 * s} {80 * s},0 M{cx - 40 * s},{cy + 210 * s} q{40 * s},{-12 * s} {80 * s},0" '
            f'fill="none" stroke="#b97a5a" stroke-width="{5 * s}"/></g>')


def tube(x0, y0, x1, y1, w=120, attrs='data-in="slide-left" data-at="0.3"', gid="tube"):
    import math
    ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
    L = math.hypot(x1 - x0, y1 - y0)
    return (f'<g id="{gid}" {attrs}><g transform="translate({x0} {y0}) rotate({ang:.1f})">'
            f'<rect x="0" y="{-w / 2}" width="{L}" height="{w}" fill="#f2e6c9"/>'
            f'<ellipse cx="{L}" cy="0" rx="{w * 0.18}" ry="{w / 2}" fill="#d9c79f"/>'
            f'<path d="M{L * 0.3},{-w / 2} l{L * 0.12},{w}" fill="none" stroke="#c9b586" stroke-width="5"/>'
            f'<path d="M{L * 0.6},{-w / 2} l{L * 0.12},{w}" fill="none" stroke="#c9b586" stroke-width="5"/></g></g>')
