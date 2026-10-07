"""Doodle shapes for the flamingo video (Phase 5 fresh run 1)."""
SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920">'
PINK, DEEP, BEAK, LEG = "#f9a8c9", "#e8608f", "#fff4e0", "#e8608f"


def flamingo(gid="bird", cx=540, fy=1040, s=1.0, legs=1, face="calm", sleep=False, attrs='data-in="none"', flip=False) -> str:
    """A flamingo standing at foot (cx, fy). Height ≈ 970·s px (head top to foot). legs=1 tucks the second leg;
    face: calm | dead (X eyes) | happy; sleep=True rests the head on the back. flip mirrors it (facing left)."""
    k = -1 if flip else 1
    X = lambda dx: cx + k * dx * s          # noqa: E731
    Y = lambda dy: fy - dy * s              # noqa: E731
    o = f'<g id="{gid}" {attrs}>'
    # standing leg: hidden thigh under the body, visible shin to the ankle, then the foot
    o += (f'<path d="M{X(0)},{Y(440)} L{X(4)},{Y(240)} L{X(0)},{Y(8)}" fill="none" stroke="{LEG}" stroke-width="{13 * s}" '
          f'stroke-linecap="round"/>')
    o += f'<circle cx="{X(4)}" cy="{Y(240)}" r="{13 * s}" fill="{DEEP}"/>'
    o += f'<path d="M{X(-46)},{Y(0)} L{X(52)},{Y(0)}" fill="none" stroke="{LEG}" stroke-width="{12 * s}" stroke-linecap="round"/>'
    if legs == 2:
        o += (f'<path d="M{X(70)},{Y(440)} L{X(88)},{Y(240)} L{X(84)},{Y(8)}" fill="none" stroke="{LEG}" stroke-width="{13 * s}" '
              f'stroke-linecap="round"/><path d="M{X(40)},{Y(0)} L{X(132)},{Y(0)}" fill="none" stroke="{LEG}" stroke-width="{12 * s}" '
              f'stroke-linecap="round"/>')
    else:   # tucked leg: down to the ankle, folded back up under the belly
        o += (f'<path d="M{X(40)},{Y(450)} L{X(-20)},{Y(330)} L{X(-110)},{Y(420)}" fill="none" stroke="{LEG}" stroke-width="{13 * s}" '
              f'stroke-linecap="round" stroke-linejoin="round"/>')
    # body, tail, wing
    o += f'<ellipse cx="{X(10)}" cy="{Y(540)}" rx="{185 * s}" ry="{112 * s}" fill="{PINK}"/>'
    o += f'<path d="M{X(-160)},{Y(560)} L{X(-250)},{Y(600)} L{X(-170)},{Y(500)} Z" fill="{DEEP}"/>'
    o += f'<path d="M{X(-110)},{Y(560)} C{X(-40)},{Y(620)} {X(70)},{Y(610)} {X(120)},{Y(545)} C{X(40)},{Y(505)} {X(-50)},{Y(500)} {X(-110)},{Y(560)} Z" fill="{DEEP}"/>'
    if sleep:   # neck curls back, head on the back
        o += (f'<path d="M{X(150)},{Y(580)} C{X(230)},{Y(700)} {X(60)},{Y(760)} {X(-40)},{Y(680)}" fill="none" stroke="{PINK}" '
              f'stroke-width="{32 * s}" stroke-linecap="round"/>')
        hx, hy = X(-60), Y(660)
        o += f'<circle cx="{hx}" cy="{hy}" r="{56 * s}" fill="{PINK}"/>'
        o += f'<path d="M{hx - k * 22 * s},{hy - 4 * s} q{k * 10 * s},{8 * s} {k * 20 * s},0" fill="none" stroke="#222" stroke-width="{5 * s}"/>'
        o += (f'<path d="M{hx - k * 40 * s},{hy + 6 * s} L{hx - k * 120 * s},{hy + 30 * s} L{hx - k * 110 * s},{hy + 66 * s} Z" '
              f'fill="{BEAK}"/><path d="M{hx - k * 100 * s},{hy + 26 * s} L{hx - k * 120 * s},{hy + 30 * s} L{hx - k * 110 * s},{hy + 66 * s} Z" fill="#222"/>')
    else:       # S-shaped neck up to the head
        o += (f'<path d="M{X(150)},{Y(590)} C{X(260)},{Y(720)} {X(-60)},{Y(760)} {X(40)},{Y(900)}" fill="none" stroke="{PINK}" '
              f'stroke-width="{32 * s}" stroke-linecap="round"/>')
        hx, hy = X(50), Y(925)
        o += f'<circle cx="{hx}" cy="{hy}" r="{60 * s}" fill="{PINK}"/>'
        if face == "dead":   # X eye
            ex, ey = hx + k * 14 * s, hy - 10 * s
            o += (f'<path d="M{ex - 15 * s},{ey - 15 * s} L{ex + 15 * s},{ey + 15 * s} M{ex + 15 * s},{ey - 15 * s} L{ex - 15 * s},{ey + 15 * s}" '
                  f'fill="none" stroke="#222" stroke-width="{7 * s}"/>')
        elif face == "happy":
            o += f'<path d="M{hx + k * 2 * s},{hy - 10 * s} q{k * 12 * s},{-14 * s} {k * 24 * s},0" fill="none" stroke="#222" stroke-width="{7 * s}"/>'
        else:
            o += f'<circle cx="{hx + k * 14 * s}" cy="{hy - 10 * s}" r="{10 * s}" fill="#222"/>'
        o += (f'<path d="M{hx + k * 50 * s},{hy - 8 * s} L{hx + k * 150 * s},{hy + 26 * s} L{hx + k * 134 * s},{hy + 80 * s} Z" fill="{BEAK}"/>'
              f'<path d="M{hx + k * 122 * s},{hy + 20 * s} L{hx + k * 150 * s},{hy + 26 * s} L{hx + k * 134 * s},{hy + 80 * s} Z" fill="#222"/>')
    return o + "</g>"


def water(y=1040, x0=60, x1=1020, attrs='data-in="none"'):
    n = int((x1 - x0) / 96)
    return (f'<path d="M{x0},{y} ' + " ".join(f"q48,-22 96,0" if i == 0 else "t96,0" for i in range(n)) +
            f'" fill="none" stroke="#3b82c4" stroke-width="8" {attrs}/>')


def ground(y=1044, attrs='data-in="none"'):
    return f'<path d="M80,{y} C400,{y - 8} 700,{y + 6} 1000,{y - 3}" fill="none" stroke="#5b4636" stroke-width="7" {attrs}/>'


def text(t, y=215, size=104, x=540, attrs='data-in="none"', family="marker"):
    return f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" {attrs}>{t}</text>'


def sway(cx, y, at, w=150, attrs=""):
    """Small sway marks either side of a point (left and right arcs)."""
    return (f'<g data-in="pop" data-at="{at}" {attrs}><path d="M{cx - w},{y - 40} q-30,40 0,80" fill="none" stroke="#3b82c4" stroke-width="8"/>'
            f'<path d="M{cx + w},{y - 40} q30,40 0,80" fill="none" stroke="#3b82c4" stroke-width="8"/></g>')
