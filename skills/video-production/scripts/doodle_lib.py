"""doodle_lib — reusable hand-drawn components for the doodle engine.

A scene SVG uses them with `<g data-lib="NAME" ... transform="translate(x y) scale(s)"/>`. The engine expands the
element into the snippet returned here (local coordinates; the group's transform places it). Everything is drawn
in ink by default; `data-fill` / `data-color` add marker colour. Components keep the channel's look consistent —
the stick figure ("dude") is the recurring mascot.

Component catalogue (attributes in brackets):
  dude      stick-figure mascot, feet at (0,0), ~380 px tall   [data-pose, data-face, data-acc, data-color, data-fill]
  bubble    speech bubble centred at (0,0)                     [data-text, data-w, data-h, data-tail, data-size]
  thought   thought cloud centred at (0,0)                     [data-text, data-w, data-h, data-size]
  arrow     curved arrow in parent coordinates                 [data-from "x,y", data-to "x,y", data-bend]
  burst     spiky impact star                                  [data-r, data-n, data-fill]
  bulb, brain, robot, clock, heart, question, exclaim, check, cross, sparkle, sweat, lines, coin, phone,
  spiral, feather, knob, zz, star, cloud, sun, bomb, trophy, magnifier
"""
from __future__ import annotations

import math
from xml.sax.saxutils import escape

POSES = ["stand", "wave", "arms-up", "point", "point-left", "shrug", "think", "hips", "facepalm", "run",
         "tickle-self", "reach", "sit", "fall"]
FACES = ["happy", "sad", "shock", "meh", "smug", "angry", "laugh", "think", "ko", "nervous", "wink", "love"]
ACCESSORIES = ["glasses", "tie", "tuft", "cap", "coat"]

HEAD = (0, -292)
R_HEAD = 62
SHOULDER = (0, -200)
HIP = (0, -95)

# arm = shoulder -> elbow -> hand ; leg = hip -> knee -> foot   (left, right)
ARMS = {
    "stand": [(-34, -150, -46, -100), (34, -150, 46, -100)],
    "wave": [(-34, -150, -46, -100), (58, -232, 92, -300)],
    "arms-up": [(-55, -248, -78, -318), (55, -248, 78, -318)],
    "point": [(-34, -150, -46, -100), (70, -208, 140, -214)],
    "point-left": [(-70, -208, -140, -214), (34, -150, 46, -100)],
    "shrug": [(-52, -168, -92, -214), (52, -168, 92, -214)],
    "think": [(-30, -160, 22, -150), (44, -150, 24, -246)],
    "hips": [(-58, -150, -16, -106), (58, -150, 16, -106)],
    "facepalm": [(-34, -150, -46, -100), (46, -186, 8, -282)],
    "run": [(-46, -176, -24, -128), (46, -214, 84, -178)],
    "tickle-self": [(-50, -168, -6, -130), (50, -168, 6, -142)],
    "reach": [(52, -196, 118, -190), (62, -206, 132, -206)],
    "sit": [(-34, -150, -40, -100), (34, -150, 40, -100)],
    "fall": [(-60, -230, -100, -270), (60, -230, 100, -268)],
}
LEGS = {
    "stand": [(-20, -48, -40, 0), (20, -48, 40, 0)],
    "run": [(-38, -58, -82, -36), (30, -48, 26, 0)],
    "sit": [(-50, -95, -56, 0), (50, -95, 56, 0)],
    "fall": [(-30, -40, -70, -10), (40, -60, 80, -40)],
}


def _pl(points: list[tuple[float, float]]) -> str:
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points)


def _face(face: str, hx: float, hy: float, ink: str) -> list[str]:
    e = []
    dot = lambda x, y, r=6.5: f'<circle cx="{hx + x}" cy="{hy + y}" r="{r}" fill="{ink}" stroke="none"/>'  # noqa: E731
    if face in ("happy", "smug", "nervous", "wink", "meh", "sad", "angry", "think"):
        if face == "smug":
            e += [f'<path d="M{hx - 30},{hy - 8} L{hx - 12},{hy - 8}"/>', f'<path d="M{hx + 12},{hy - 8} L{hx + 30},{hy - 8}"/>']
        elif face == "wink":
            e += [dot(-20, -8), f'<path d="M{hx + 10},{hy - 6} Q{hx + 20},{hy - 16} {hx + 30},{hy - 6}"/>']
        elif face == "think":
            e += [dot(-12, -16), dot(26, -16)]
        else:
            e += [dot(-20, -8), dot(20, -8)]
    if face == "happy":
        e.append(f'<path d="M{hx - 24},{hy + 16} Q{hx},{hy + 42} {hx + 24},{hy + 16}"/>')
    elif face == "wink":
        e.append(f'<path d="M{hx - 22},{hy + 18} Q{hx + 2},{hy + 38} {hx + 24},{hy + 14}"/>')
    elif face == "sad":
        e += [f'<path d="M{hx - 22},{hy + 34} Q{hx},{hy + 14} {hx + 22},{hy + 34}"/>',
              f'<path d="M{hx - 32},{hy - 22} L{hx - 12},{hy - 28}"/>', f'<path d="M{hx + 12},{hy - 28} L{hx + 32},{hy - 22}"/>']
    elif face == "shock":
        e += [f'<circle cx="{hx - 20}" cy="{hy - 10}" r="12" fill="#ffffff"/>', dot(-20, -10, 5),
              f'<circle cx="{hx + 20}" cy="{hy - 10}" r="12" fill="#ffffff"/>', dot(20, -10, 5),
              f'<ellipse cx="{hx}" cy="{hy + 28}" rx="11" ry="15" fill="{ink}"/>']
    elif face == "meh":
        e.append(f'<path d="M{hx - 18},{hy + 26} L{hx + 18},{hy + 26}"/>')
    elif face == "smug":
        e.append(f'<path d="M{hx - 16},{hy + 26} Q{hx + 8},{hy + 34} {hx + 26},{hy + 14}"/>')
    elif face == "angry":
        e += [f'<path d="M{hx - 34},{hy - 30} L{hx - 10},{hy - 18}"/>', f'<path d="M{hx + 10},{hy - 18} L{hx + 34},{hy - 30}"/>',
              f'<path d="M{hx - 20},{hy + 32} Q{hx},{hy + 20} {hx + 20},{hy + 32}"/>']
    elif face == "laugh":
        e += [f'<path d="M{hx - 30},{hy - 6} Q{hx - 20},{hy - 20} {hx - 10},{hy - 6}"/>',
              f'<path d="M{hx + 10},{hy - 6} Q{hx + 20},{hy - 20} {hx + 30},{hy - 6}"/>',
              f'<path d="M{hx - 26},{hy + 10} L{hx + 26},{hy + 10} Q{hx + 24},{hy + 44} {hx},{hy + 44} Q{hx - 24},{hy + 44} {hx - 26},{hy + 10} Z" fill="{ink}"/>']
    elif face == "think":
        e.append(f'<path d="M{hx - 6},{hy + 28} L{hx + 20},{hy + 24}"/>')
    elif face == "ko":
        for cx in (-20, 20):
            e += [f'<path d="M{hx + cx - 9},{hy - 17} L{hx + cx + 9},{hy + 1}"/>', f'<path d="M{hx + cx + 9},{hy - 17} L{hx + cx - 9},{hy + 1}"/>']
        e.append(f'<path d="M{hx - 20},{hy + 28} Q{hx - 10},{hy + 20} {hx},{hy + 28} Q{hx + 10},{hy + 36} {hx + 20},{hy + 28}"/>')
    elif face == "nervous":
        e += [f'<path d="M{hx - 22},{hy + 26} L{hx - 11},{hy + 20} L{hx},{hy + 26} L{hx + 11},{hy + 20} L{hx + 22},{hy + 26}"/>',
              f'<path d="M{hx + 52},{hy - 40} Q{hx + 64},{hy - 18} {hx + 54},{hy - 10} Q{hx + 42},{hy - 16} {hx + 52},{hy - 40} Z" fill="#7cc6f2"/>']
    elif face == "love":
        for cx in (-20, 20):
            x, y = hx + cx, hy - 10
            e.append(f'<path d="M{x},{y + 9} C{x - 16},{y - 2} {x - 9},{y - 15} {x},{y - 6} C{x + 9},{y - 15} {x + 16},{y - 2} {x},{y + 9} Z" fill="#e8452c" stroke="none"/>')
        e.append(f'<path d="M{hx - 22},{hy + 18} Q{hx},{hy + 40} {hx + 22},{hy + 18}"/>')
    return e


def dude(a: dict) -> str:
    pose = a.get("data-pose", "stand")
    face = a.get("data-face", "happy")
    ink = a.get("data-color", "#1d1b1a")
    acc = [x.strip() for x in a.get("data-acc", "").split(",") if x.strip()]
    arms = ARMS.get(pose, ARMS["stand"])
    legs = LEGS.get(pose, LEGS["stand"])
    hx, hy = HEAD
    tilt = {"think": -6, "shrug": 4, "facepalm": 8, "fall": -25, "run": 8}.get(pose, 0)
    parts = []
    body_top, hip = (0, hy + R_HEAD), HIP
    if pose == "sit":
        hip = (0, -95)
    if "coat" in acc:  # lab coat: a trapezoid behind the body
        parts.append(f'<path d="M-30,-220 L30,-220 L58,-60 L-58,-60 Z" fill="{a.get("data-fill", "#ffffff")}"/>')
    elif a.get("data-fill"):  # a simple t-shirt blob in marker colour
        parts.append(f'<path d="M-26,-222 L26,-222 L32,-120 L-32,-120 Z" fill="{a["data-fill"]}" stroke="none"/>')
    parts.append(f'<path d="{_pl([body_top, hip])}"/>')
    for ex, ey, hx2, hy2 in arms:
        parts.append(f'<path d="{_pl([SHOULDER, (ex, ey), (hx2, hy2)])}"/>')
    for kx, ky, fx, fy in legs:
        parts.append(f'<path d="{_pl([hip, (kx, ky), (fx, fy)])}"/>')
        parts.append(f'<path d="M{fx},{fy} L{fx + (14 if fx >= 0 else -14)},{fy}"/>')
    if "tie" in acc:
        parts.append('<path d="M0,-226 L-10,-206 L0,-150 L10,-206 Z" fill="#e8452c"/>')
    head = [f'<circle cx="{hx}" cy="{hy}" r="{R_HEAD}" fill="#ffffff"/>']
    head += _face(face, hx, hy, ink)
    if "glasses" in acc:
        head += [f'<circle cx="{hx - 21}" cy="{hy - 8}" r="17" fill="none"/>', f'<circle cx="{hx + 21}" cy="{hy - 8}" r="17" fill="none"/>',
                 f'<path d="M{hx - 4},{hy - 10} L{hx + 4},{hy - 10}"/>']
    if "tuft" in acc:
        head.append(f'<path d="M{hx - 8},{hy - 60} Q{hx - 4},{hy - 92} {hx + 14},{hy - 86} M{hx + 2},{hy - 61} Q{hx + 14},{hy - 84} {hx + 30},{hy - 74}"/>')
    if "cap" in acc:
        head.append(f'<path d="M{hx - 60},{hy - 18} Q{hx - 56},{hy - 74} {hx},{hy - 76} Q{hx + 56},{hy - 74} {hx + 60},{hy - 18} Z '
                    f'M{hx + 40},{hy - 22} L{hx + 104},{hy - 18}" fill="{a.get("data-fill", "#3b82c4")}"/>')
    return (f'<g stroke="{ink}">' + "".join(parts) +
            f'<g transform="rotate({tilt} {hx} {hy + 40})">' + "".join(head) + "</g></g>")


def _text_el(text: str, x: float, y: float, size: float, extra: str = "") -> str:
    return (f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="middle" dominant-baseline="middle" '
            f'font-family="hand"{extra}>{escape(text)}</text>')


def bubble(a: dict) -> str:
    w, h = float(a.get("data-w", 420)), float(a.get("data-h", 200))
    tail = a.get("data-tail", "down-left")
    x0, y0, x1, y1 = -w / 2, -h / 2, w / 2, h / 2
    r = min(46, h / 3)
    tx = {"down-left": -w * 0.22, "down-right": w * 0.22, "down": 0}.get(tail, -w * 0.22)
    tip = {"down-left": (-w * 0.38, y1 + 90), "down-right": (w * 0.38, y1 + 90), "down": (0, y1 + 95)}.get(tail, (-w * 0.38, y1 + 90))
    d = (f"M{x0 + r},{y0} L{x1 - r},{y0} Q{x1},{y0} {x1},{y0 + r} L{x1},{y1 - r} Q{x1},{y1} {x1 - r},{y1} "
         f"L{tx + 34},{y1} L{tip[0]},{tip[1]} L{tx - 10},{y1} L{x0 + r},{y1} Q{x0},{y1} {x0},{y1 - r} "
         f"L{x0},{y0 + r} Q{x0},{y0} {x0 + r},{y0} Z")
    out = f'<path d="{d}" fill="{a.get("data-fill", "#ffffff")}"/>'
    if a.get("data-text"):
        out += _text_el(a["data-text"], 0, 4, float(a.get("data-size", 64)))
    return out


def thought(a: dict) -> str:
    w, h = float(a.get("data-w", 440)), float(a.get("data-h", 240))
    n = 9
    pts = []
    for k in range(n):
        t0, t1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
        p0 = (w / 2 * math.cos(t0), h / 2 * math.sin(t0))
        p1 = (w / 2 * math.cos(t1), h / 2 * math.sin(t1))
        tm = (t0 + t1) / 2
        c = (w / 2 * 1.28 * math.cos(tm), h / 2 * 1.32 * math.sin(tm))
        pts.append((p0, c, p1))
    d = f"M{pts[0][0][0]:.1f},{pts[0][0][1]:.1f} " + " ".join(f"Q{c[0]:.1f},{c[1]:.1f} {p1[0]:.1f},{p1[1]:.1f}" for _, c, p1 in pts) + " Z"
    out = f'<path d="{d}" fill="{a.get("data-fill", "#ffffff")}"/>'
    out += f'<circle cx="{-w * 0.30}" cy="{h * 0.70}" r="22" fill="#ffffff"/><circle cx="{-w * 0.40}" cy="{h * 0.92}" r="13" fill="#ffffff"/>'
    if a.get("data-text"):
        out += _text_el(a["data-text"], 0, 4, float(a.get("data-size", 60)))
    return out


def arrow(a: dict) -> str:
    x0, y0 = (float(v) for v in a.get("data-from", "0,0").split(","))
    x1, y1 = (float(v) for v in a.get("data-to", "200,0").split(","))
    bend = float(a.get("data-bend", 0.25))
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = x1 - x0, y1 - y0
    cx, cy = mx - dy * bend, my + dx * bend
    ang = math.atan2(y1 - cy, x1 - cx)
    L = 38
    h1 = (x1 - L * math.cos(ang - 0.5), y1 - L * math.sin(ang - 0.5))
    h2 = (x1 - L * math.cos(ang + 0.5), y1 - L * math.sin(ang + 0.5))
    return (f'<path d="M{x0},{y0} Q{cx:.1f},{cy:.1f} {x1},{y1}" fill="none"/>'
            f'<path d="M{h1[0]:.1f},{h1[1]:.1f} L{x1},{y1} L{h2[0]:.1f},{h2[1]:.1f}" fill="none"/>')


def burst(a: dict) -> str:
    r, n = float(a.get("data-r", 150)), int(a.get("data-n", 12))
    pts = []
    for k in range(2 * n):
        rr = r if k % 2 == 0 else r * 0.58
        t = math.pi * k / n - math.pi / 2
        pts.append((rr * math.cos(t), rr * math.sin(t)))
    return f'<path d="{_pl(pts)} Z" fill="{a.get("data-fill", "#ffd23f")}"/>'


def star(a: dict) -> str:
    r = float(a.get("data-r", 80))
    pts = [((r if k % 2 == 0 else r * 0.45) * math.cos(math.pi * k / 5 - math.pi / 2),
            (r if k % 2 == 0 else r * 0.45) * math.sin(math.pi * k / 5 - math.pi / 2)) for k in range(10)]
    return f'<path d="{_pl(pts)} Z" fill="{a.get("data-fill", "#ffd23f")}"/>'


def _simple(svg: str):
    return lambda a: svg.replace("{fill}", a.get("data-fill", "#ffd23f"))


SIMPLE = {
    "bulb": _simple('<path d="M-60,10 C-110,-60 -70,-150 0,-150 C70,-150 110,-60 60,10 C45,30 40,45 40,60 L-40,60 C-40,45 -45,30 -60,10 Z" fill="{fill}"/>'
                    '<path d="M-36,78 L36,78 M-30,96 L30,96 M-18,114 L18,114"/><path d="M-18,30 L-10,-30 L0,-10 L10,-30 L18,30" fill="none"/>'
                    '<path d="M-150,-90 L-118,-80 M150,-90 L118,-80 M0,-205 L0,-172 M-110,-180 L-88,-150 M110,-180 L88,-150" fill="none"/>'),
    "robot": _simple('<path d="M0,-170 L0,-210" fill="none"/><circle cx="0" cy="-222" r="14" fill="#e8452c"/>'
                     '<rect x="-90" y="-170" width="180" height="140" rx="22" fill="{fill}"/>'
                     '<circle cx="-38" cy="-104" r="20" fill="#ffffff"/><circle cx="38" cy="-104" r="20" fill="#ffffff"/>'
                     '<circle cx="-38" cy="-104" r="7" fill="#1d1b1a"/><circle cx="38" cy="-104" r="7" fill="#1d1b1a"/>'
                     '<path d="M-36,-58 L-18,-50 L0,-58 L18,-50 L36,-58" fill="none"/>'
                     '<rect x="-70" y="-20" width="140" height="150" rx="16" fill="{fill}"/>'
                     '<path d="M-70,10 L-130,60 L-150,20 M70,10 L130,60 L150,20 M-40,130 L-40,190 L-64,190 M40,130 L40,190 L64,190" fill="none"/>'
                     '<circle cx="0" cy="44" r="18" fill="#ffd23f"/>'),
    "clock": _simple('<circle cx="0" cy="0" r="130" fill="#ffffff"/><path d="M0,0 L0,-84 M0,0 L60,26" fill="none"/>'
                     '<path d="M0,-130 L0,-108 M130,0 L108,0 M0,130 L0,108 M-130,0 L-108,0" fill="none"/><circle cx="0" cy="0" r="9" fill="#1d1b1a"/>'),
    "heart": _simple('<path d="M0,90 C-120,10 -130,-80 -60,-96 C-24,-104 -6,-80 0,-60 C6,-80 24,-104 60,-96 C130,-80 120,10 0,90 Z" fill="{fill}"/>'),
    "question": _simple('<path d="M-50,-70 C-50,-130 50,-140 56,-80 C60,-36 0,-30 0,20 L0,40" fill="none" stroke-width="18"/>'
                        '<circle cx="0" cy="92" r="13" fill="#1d1b1a"/>'),
    "exclaim": _simple('<path d="M0,-120 L0,40" fill="none" stroke-width="20"/><circle cx="0" cy="92" r="14" fill="#1d1b1a"/>'),
    "check": _simple('<path d="M-70,0 L-20,60 L80,-70" fill="none" stroke="#2f9e44" stroke-width="22"/>'),
    "cross": _simple('<path d="M-60,-60 L60,60 M60,-60 L-60,60" fill="none" stroke="#e03131" stroke-width="22"/>'),
    "sparkle": _simple('<path d="M0,-60 Q8,-8 60,0 Q8,8 0,60 Q-8,8 -60,0 Q-8,-8 0,-60 Z" fill="{fill}"/>'),
    "sweat": _simple('<path d="M0,-40 Q22,0 14,20 Q0,36 -14,20 Q-22,0 0,-40 Z" fill="#7cc6f2"/>'),
    "lines": _simple('<path d="M-60,-40 L40,-40 M-90,0 L30,0 M-60,40 L40,40" fill="none"/>'),
    "coin": _simple('<circle cx="0" cy="0" r="70" fill="{fill}"/><circle cx="0" cy="0" r="48" fill="none"/>'
                    '<path d="M0,-30 L0,30" fill="none"/>'),
    "phone": _simple('<rect x="-70" y="-130" width="140" height="260" rx="24" fill="#ffffff"/>'
                     '<rect x="-50" y="-100" width="100" height="180" rx="8" fill="{fill}"/><path d="M-14,108 L14,108" fill="none"/>'),
    "spiral": _simple('<path d="M0,0 C10,-10 20,0 14,12 C4,30 -24,24 -26,0 C-28,-34 12,-46 34,-22 C58,6 40,54 0,56 '
                      'C-44,58 -70,22 -64,-14" fill="none"/>'),
    "feather": _simple('<path d="M-30,170 C-10,80 20,-40 70,-190" fill="none"/>'
                       '<path d="M-14,96 C-70,60 -60,-80 70,-190 C76,-120 66,-40 40,10 L22,0 L30,30 C14,70 4,90 -14,96 Z" fill="{fill}"/>'
                       '<path d="M-6,60 L-44,40 M4,20 L-38,-6 M16,-20 L-24,-56 M30,-64 L-6,-108 M44,-110 L18,-150 '
                       'M2,46 L36,28 M14,4 L50,-20 M28,-44 L60,-74" fill="none" stroke-width="4"/>'),
    "knob": _simple('<circle cx="0" cy="0" r="110" fill="{fill}"/><path d="M0,0 L-62,62" fill="none" stroke-width="12"/>'
                    '<path d="M-150,0 L-130,0 M-106,-106 L-92,-92 M0,-150 L0,-130 M106,-106 L92,-92 M150,0 L130,0" fill="none"/>'),
    "zz": lambda a: _text_el("z", -20, 20, 70) + _text_el("Z", 30, -40, 100),
    "cloud": _simple('<path d="M-120,40 C-170,40 -170,-30 -110,-34 C-110,-90 -30,-100 -10,-60 C20,-110 110,-90 100,-30 '
                     'C160,-30 160,40 110,40 Z" fill="{fill}"/>'),
    "sun": _simple('<circle cx="0" cy="0" r="70" fill="{fill}"/><path d="M0,-100 L0,-140 M0,100 L0,140 M100,0 L140,0 M-100,0 L-140,0 '
                   'M72,-72 L100,-100 M-72,72 L-100,100 M72,72 L100,100 M-72,-72 L-100,-100" fill="none"/>'),
    "bomb": _simple('<circle cx="0" cy="20" r="96" fill="#3a3a3a"/><rect x="-24" y="-96" width="48" height="30" fill="#3a3a3a"/>'
                    '<path d="M0,-96 C10,-140 50,-140 60,-170" fill="none"/><path d="M60,-170 L48,-190 M60,-170 L82,-182 M60,-170 L76,-150" '
                    'fill="none" stroke="#e8452c"/>'),
    "trophy": _simple('<path d="M-70,-110 L70,-110 L60,-20 C50,20 -50,20 -60,-20 Z" fill="{fill}"/>'
                      '<path d="M-70,-90 C-130,-90 -120,-20 -64,-20 M70,-90 C130,-90 120,-20 64,-20" fill="none"/>'
                      '<path d="M0,20 L0,70 M-50,90 L50,90 L40,70 L-40,70 Z" fill="{fill}"/>'),
    "magnifier": _simple('<circle cx="-20" cy="-20" r="80" fill="#dff1fb"/><path d="M38,38 L120,120" fill="none" stroke-width="22"/>'),
}

def brain(a: dict) -> str:
    """Brain blob; folds stay in the upper half so an optional face (data-face) reads cleanly."""
    out = ('<path d="M-120,10 C-150,-40 -120,-100 -70,-104 C-60,-140 -10,-150 10,-122 C40,-150 100,-130 104,-90 '
           'C150,-80 160,-20 128,10 C150,50 110,96 70,84 C50,112 -10,112 -26,86 C-70,108 -126,80 -120,10 Z" '
           f'fill="{a.get("data-fill", "#f783ac")}"/>'
           '<path d="M-70,-62 C-44,-74 -40,-34 -12,-44 M20,-84 C30,-56 58,-64 70,-36 M0,-112 C-6,-92 6,-72 0,-56 '
           'M-112,-22 C-92,-44 -72,-22 -58,-42 M64,-56 C84,-34 102,-54 116,-30" fill="none"/>')
    if a.get("data-face"):
        out += '<g transform="translate(0 18) scale(1.35)">' + "".join(_face(a["data-face"], 0, 0, a.get("data-color", "#1d1b1a"))) + "</g>"
    return out


COMPONENTS = {"dude": dude, "brain": brain, "bubble": bubble, "thought": thought, "arrow": arrow, "burst": burst, "star": star, **SIMPLE}


def expand(name: str, attrs: dict) -> str:
    """Return the inner SVG markup for component `name` (raises KeyError for unknown names)."""
    return COMPONENTS[name](attrs)
