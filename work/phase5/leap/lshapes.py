"""Doodle shapes for the leap-year video (Phase 5 fresh run 3): calendar pages, an orbit, a quarter-day clock."""
SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920">'


def calendar(gid, x, y, w, h, month="FEB", year="", hl=None, attrs='data-in="none"', head="#e8452c", cols=7, rows=5):
    """A wall-calendar page: coloured header with month (+year), a grid of day squares; hl = (col, row) highlighted."""
    o = (f'<g id="{gid}" {attrs}><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="22" fill="white"/>'
         f'<rect x="{x}" y="{y}" width="{w}" height="{h * 0.22}" rx="22" fill="{head}"/>')
    gx, gy, gw, gh = x + w * 0.07, y + h * 0.3, w * 0.86, h * 0.62
    cw, ch = gw / cols, gh / rows
    for r in range(rows):
        for c in range(cols):
            fill = "#ffd23f" if hl == (c, r) else "#f1ece2"
            o += f'<rect x="{gx + c * cw + 5}" y="{gy + r * ch + 5}" width="{cw - 10}" height="{ch - 10}" rx="8" fill="{fill}" data-outline="none"/>'
    o += "</g>"
    if not (month or year):
        return o
    o += (f'<text x="{x + w / 2}" y="{y + h * 0.16}" font-family="marker" font-size="{int(h * 0.12)}" fill="white" '
          f'{attrs}>{month}{(" " + year) if year else ""}</text>')
    return o


def cell(x, y, w, h, c, r, cols=7, rows=5):
    """Centre of grid cell (c, r) of a calendar drawn with calendar(x, y, w, h)."""
    gx, gy, gw, gh = x + w * 0.07, y + h * 0.3, w * 0.86, h * 0.62
    return gx + (c + 0.5) * gw / cols, gy + (r + 0.5) * gh / rows


def text(t, y=215, size=104, x=540, attrs='data-in="none"', family="marker", fill=None):
    return f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}"' + (f' fill="{fill}"' if fill else "") + f" {attrs}>{t}</text>"


def orbit(cx, cy, rx, ry, attrs='data-in="none"', gid="orbit"):
    return (f'<g id="{gid}" {attrs}><ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="none" stroke="#3b82c4" stroke-width="8"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{ry * 0.45}" fill="#ffd23f"/></g>')


def earth(cx, cy, r, attrs='data-in="pop" data-at="0.2"', gid="earth"):
    return (f'<g id="{gid}" {attrs}><circle cx="{cx}" cy="{cy}" r="{r}" fill="#3b82c4"/>'
            f'<path d="M{cx - r * 0.5},{cy - r * 0.2} q{r * 0.3},{-r * 0.5} {r * 0.7},{-r * 0.1} q{-r * 0.1},{r * 0.4} {-r * 0.7},{r * 0.5} Z" fill="#2f9e44" data-outline="none"/></g>')


def quarter_clock(cx, cy, r, attrs='data-in="pop" data-at="0.2"', gid="clock"):
    return (f'<g id="{gid}" {attrs}><circle cx="{cx}" cy="{cy}" r="{r}" fill="white"/>'
            f'<path d="M{cx},{cy} L{cx},{cy - r} A{r},{r} 0 0 1 {cx + r},{cy} Z" fill="#ffd23f"/>'
            f'<path d="M{cx},{cy} L{cx},{cy - r * 0.8} M{cx},{cy} L{cx + r * 0.55},{cy}" fill="none" stroke="#1d1b1a" stroke-width="9"/></g>')
