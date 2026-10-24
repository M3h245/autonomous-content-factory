"""doodle_parts — carefully drawn anatomy and object parts for the doodle engine (v3.3.1).

Why: scenes drawn ad hoc per video sometimes looked like a two-year-old's drawing (a foot as an "L" block, a plane
that read as an arrow through an ear). These parts are drawn once, reviewed once at full size, and reused, so every
video starts from the same quality floor. Use them like any doodle_lib component:

    <g data-lib="leg" transform="translate(540 620) scale(1.0)" data-in="none"/>

Every part is centred on (0,0) in its own coordinates; the size column is the drawn box at scale 1. Colour options:
`data-fill` (main fill), `data-skin` (skin tone for body parts). Strokes default to the engine's ink.

  part           size (w x h)   notes
  leg            720 x 690      side view of a lower leg and bare foot, toes to the right
  ear            390 x 780      outer ear (helix, antihelix, concha, tragus, lobe), opening faces left
  head           625 x 815      head and neck in profile, facing right; ear at about (-90, -40)
  hand           300 x 470      open hand, palm facing the viewer, fingers up
  eye            300 x 160      almond eye with iris, pupil and highlight
  plane          520 x 300      airliner side view, nose to the right
  thermometer    90 x 520       glass tube, red bulb; data-level 0..1 sets the red column
  metal_block    330 x 250      grey block with shine streaks (3/4 view)
  wood_block     330 x 250      brown block with grain lines (3/4 view)
  ice_cube       260 x 240      pale blue cube with highlight
  mug            300 x 280      mug with handle and steam
  pan            560 x 140      frying pan side view, handle to the right
  flame          160 x 260      candle-style flame, yellow core
  weight         400 x 400      cast-iron weight with handle
  hose           620 x 340      garden hose; data-state="kinked" (default) or "straight"
  molecule       260 x 220      three-atom cluster with bonds
  spoon          140 x 560      kitchen spoon, bowl up; data-fill="#aab4bf" metal (default) or a wood colour
  bowl           420 x 200      bowl of water; data-fill sets the water (blue cold, red warm, purple middle)
  bench          620 x 300      park bench (slats + legs); data-fill wood (default) or "#9aa5b1" metal
  slide          560 x 460      playground slide with ladder, metal chute
  heat_sink      460 x 300      chip with aluminium fins on top
  jacket         420 x 440      puffy winter jacket (air-filled baffles)
  cup            200 x 300      takeaway foam cup with lid
  water          700 x 200      water surface with waves (pool / lake); data-fill colour
  rug            560 x 120      woven rug next to a tile strip, seen from the side
  skin_layers    700 x 360      skin cross-section: surface, layers, nerve endings (blue cold, red warm)
  piggy_bank     360 x 280      piggy bank with a coin slot
  finger         460 x 190      pointing hand (fist, extended index finger, thumb, sleeve cuff), pointing right
  puddle         300 x 90       flat melt-water puddle
  speaker        300 x 300      loudspeaker cone with sound waves (for "louder" / volume)
  fan            300 x 300      desk/PC fan: frame, three blades, hub
  railing        620 x 480      stair handrail over steps; data-fill metal (default) or a wood colour
"""
from __future__ import annotations

SKIN = "#f6c9a8"
SKIN2 = "#eebd98"
LINE = "#d99f78"


def _skin(a: dict) -> str:
    return a.get("data-skin", SKIN)


def leg(a: dict) -> str:
    s = _skin(a)
    return (f'<g transform="translate(-619 -622)">'
            f'<path d="M290,280 C280,420 260,540 290,660 C305,720 300,780 290,830 C280,900 310,960 390,960 L840,965 '
            f'C920,968 975,945 978,905 C980,865 945,845 890,838 C780,822 660,790 580,735 C530,700 495,650 490,590 '
            f'C485,500 480,390 485,280 Z" fill="{s}" stroke-linejoin="round"/>'
            '<path d="M902,842 C910,818 940,818 950,848 M858,834 C866,812 894,812 902,840 M818,826 C826,806 850,806 858,832" '
            'fill="none" stroke-width="8"/>'
            f'<path d="M415,760 C430,745 455,750 458,770 M600,935 C680,945 760,945 830,940" fill="none" stroke="{LINE}" stroke-width="8"/>'
            '</g>')


def ear(a: dict) -> str:
    s = _skin(a)
    return (f'<g transform="translate(-707 -620)">'
            f'<path d="M600,250 C790,230 900,380 890,560 C882,690 800,760 775,860 C755,950 700,1010 625,1010 C565,1010 528,970 '
            f'535,925 C540,885 575,870 590,840 C600,815 590,790 575,760 C548,700 520,640 515,560 C508,430 520,300 600,250 Z" '
            f'fill="{s}" stroke-linejoin="round"/>'
            f'<path d="M612,322 C760,312 830,420 820,560 C812,660 760,712 735,792" fill="none" stroke="{LINE}" stroke-width="12"/>'
            f'<path d="M642,420 C720,420 760,500 742,590 C730,640 702,672 692,702" fill="none" stroke="{LINE}" stroke-width="10"/>'
            f'<path d="M600,560 C640,540 690,580 680,640 C672,690 622,702 600,682 Z" fill="{SKIN2}" stroke-width="8"/>'
            '<path d="M560,600 C592,596 602,640 576,660" fill="none" stroke-width="9"/>'
            '</g>')


def head(a: dict) -> str:
    s = _skin(a)
    return (f'<g transform="translate(-556 -592)">'
            f'<path d="M330,290 C420,190 640,180 740,280 C790,330 805,400 800,450 L860,560 C868,575 860,590 840,592 L812,596 '
            f'L816,640 C840,648 842,670 822,680 C838,700 836,722 818,732 C822,780 790,815 735,822 C700,826 670,840 660,880 '
            f'L660,1000 L390,1000 L392,900 C300,860 245,760 245,620 C245,470 270,360 330,290 Z" fill="{s}" stroke-linejoin="round"/>'
            '<path d="M700,432 C715,420 735,420 748,432" fill="none" stroke-width="9"/>'
            '<path d="M690,395 C712,382 740,382 760,392" fill="none" stroke-width="8"/>'
            f'<path d="M452,500 C502,490 522,540 517,580 C512,622 482,640 457,630 C440,600 440,540 452,500 Z" fill="{SKIN2}" stroke-width="9"/>'
            '<path d="M465,525 C490,525 498,560 485,590" fill="none" stroke-width="7"/>'
            '</g>')


def hand(a: dict) -> str:
    s = _skin(a)
    fingers = [(-104, -210, 46, 250, -6), (-52, -250, 48, 290, -2), (4, -240, 48, 280, 2), (58, -190, 42, 230, 7)]
    out = []
    for x, y, w, h, rot in fingers:
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{w / 2:.0f}" fill="{s}" '
                   f'transform="rotate({rot} {x + w / 2} {y + h})"/>')
        out.append(f'<path d="M{x + 12},{y + 26} C{x + 20},{y + 20} {x + w - 20},{y + 20} {x + w - 12},{y + 26}" fill="none" '
                   f'stroke="{LINE}" stroke-width="6" transform="rotate({rot} {x + w / 2} {y + h})"/>')
    out.append(f'<rect x="-150" y="-60" width="60" height="170" rx="30" fill="{s}" transform="rotate(-38 -120 100)"/>')
    out.append(f'<path d="M-112,-30 C-118,40 -110,110 -80,150 L-70,235 L80,235 L84,150 C108,110 118,40 110,-20 '
               f'C60,-36 -60,-40 -112,-30 Z" fill="{s}" stroke-linejoin="round"/>')
    out.append(f'<path d="M-60,40 C-20,70 40,70 80,30 M-40,110 C0,125 40,120 70,100" fill="none" stroke="{LINE}" stroke-width="7"/>')
    return "".join(out)


def eye(a: dict) -> str:
    iris = a.get("data-fill", "#3b82c4")
    return ('<path d="M-150,0 C-90,-80 90,-80 150,0 C90,80 -90,80 -150,0 Z" fill="#ffffff" stroke-linejoin="round"/>'
            f'<circle cx="0" cy="0" r="56" fill="{iris}"/><circle cx="0" cy="0" r="26" fill="#1d1b1a"/>'
            '<circle cx="18" cy="-18" r="10" fill="#ffffff" stroke="none"/>'
            '<path d="M-150,0 C-90,-95 90,-95 150,0" fill="none" stroke-width="10"/>')


def plane(a: dict) -> str:
    body = a.get("data-fill", "#ffffff")
    return ('<path d="M-40,40 L60,150 L120,150 L70,40 Z" fill="#9aa5b1"/>'
            '<path d="M-200,-10 C-200,-50 -150,-60 -100,-60 L190,-60 C250,-60 290,-30 290,0 C290,30 250,60 190,60 L-100,60 '
            f'C-150,60 -200,40 -200,-10 Z" fill="{body}"/>'
            '<path d="M-170,-50 L-230,-150 L-170,-150 L-110,-60 Z" fill="#e8452c"/>'
            '<path d="M-40,-30 L40,-140 L100,-140 L70,-30 Z" fill="#9aa5b1"/>'
            '<g fill="#3b82c4" stroke="none"><circle cx="0" cy="0" r="14"/><circle cx="60" cy="0" r="14"/>'
            '<circle cx="120" cy="0" r="14"/><circle cx="180" cy="0" r="14"/></g>'
            '<path d="M230,-35 C260,-30 275,-15 280,0 L230,0 Z" fill="#3b82c4" stroke="none"/>')


def thermometer(a: dict) -> str:
    lvl = max(0.0, min(1.0, float(a.get("data-level", 0.5))))
    top = 160 - 360 * lvl
    return ('<rect x="-30" y="-260" width="60" height="420" rx="30" fill="#ffffff"/>'
            f'<rect x="-12" y="{top:.0f}" width="24" height="{200 - top:.0f}" rx="12" fill="#e03131" stroke="none"/>'
            '<circle cx="0" cy="200" r="58" fill="#e03131"/>'
            '<path d="M30,-200 L50,-200 M30,-140 L50,-140 M30,-80 L50,-80 M30,-20 L50,-20 M30,40 L50,40 M30,100 L50,100" '
            'fill="none" stroke-width="6"/>')


def _block(face: str, top: str, side: str, extra: str) -> str:
    return (f'<path d="M-165,-60 L95,-60 L95,125 L-165,125 Z" fill="{face}" stroke-linejoin="round"/>'
            f'<path d="M-165,-60 L-95,-125 L165,-125 L95,-60 Z" fill="{top}" stroke-linejoin="round"/>'
            f'<path d="M95,-60 L165,-125 L165,60 L95,125 Z" fill="{side}" stroke-linejoin="round"/>' + extra)


def metal_block(a: dict) -> str:
    return _block(a.get("data-fill", "#aab4bf"), "#cfd6dd", "#87929e",
                  '<path d="M-130,-20 L-40,-20 M-120,10 L-70,10 M40,90 L80,60" fill="none" stroke="#ffffff" stroke-width="10"/>')


def wood_block(a: dict) -> str:
    return _block(a.get("data-fill", "#c98b4f"), "#ddaa74", "#a8703c",
                  '<path d="M-150,-20 C-90,-34 -10,-6 80,-24 M-150,30 C-80,16 0,44 80,26 M-150,80 C-70,66 10,94 80,76" '
                  'fill="none" stroke="#8a5a2b" stroke-width="7"/>'
                  '<ellipse cx="-40" cy="52" rx="22" ry="10" fill="none" stroke="#8a5a2b" stroke-width="6"/>')


def ice_cube(a: dict) -> str:
    return ('<path d="M-130,-50 L70,-50 L70,120 L-130,120 Z" fill="#d6effa" stroke-linejoin="round"/>'
            '<path d="M-130,-50 L-70,-110 L130,-110 L70,-50 Z" fill="#eef8fd" stroke-linejoin="round"/>'
            '<path d="M70,-50 L130,-110 L130,60 L70,120 Z" fill="#b9e2f5" stroke-linejoin="round"/>'
            '<path d="M-105,-20 L-105,40 M-85,-25 L-85,0" fill="none" stroke="#ffffff" stroke-width="12"/>')


def mug(a: dict) -> str:
    c = a.get("data-fill", "#e8452c")
    return (f'<path d="M-120,-60 L80,-60 L70,120 C68,140 50,150 30,150 L-70,150 C-90,150 -108,140 -110,120 Z" fill="{c}" '
            'stroke-linejoin="round"/>'
            '<path d="M78,-20 C150,-24 150,90 72,86" fill="none" stroke-width="22"/>'
            '<ellipse cx="-20" cy="-60" rx="100" ry="18" fill="#6b3d1d"/>'
            '<path d="M-60,-100 C-80,-130 -40,-150 -60,-180 M-10,-100 C-30,-130 10,-150 -10,-180 M40,-100 C20,-130 60,-150 40,-180" '
            'fill="none" stroke="#9aa5b1" stroke-width="8"/>')


def pan(a: dict) -> str:
    return ('<path d="M-280,-30 L120,-30 L100,40 C95,60 80,70 60,70 L-220,70 C-240,70 -255,60 -260,40 Z" fill="#3a3f45" '
            'stroke-linejoin="round"/>'
            '<path d="M120,-10 L280,-40 L286,-14 L124,16 Z" fill="#6b3d1d"/>'
            '<path d="M-250,-30 L100,-30" fill="none" stroke="#7d8790" stroke-width="10"/>')


def flame(a: dict) -> str:
    return ('<path d="M0,130 C-80,130 -95,50 -60,-10 C-30,-60 -10,-90 0,-130 C20,-80 90,-30 80,50 C76,100 50,130 0,130 Z" '
            'fill="#ff922b" stroke-linejoin="round"/>'
            '<path d="M0,110 C-40,110 -45,60 -25,30 C-10,8 0,-20 0,-40 C14,-10 45,20 40,60 C38,90 25,110 0,110 Z" '
            'fill="#ffd23f" stroke="none"/>')


def weight(a: dict) -> str:
    return ('<path d="M-140,-120 L140,-120 L200,200 L-200,200 Z" fill="#5b6470" stroke-linejoin="round"/>'
            '<path d="M-60,-120 C-60,-210 60,-210 60,-120" fill="none" stroke-width="20"/>'
            '<path d="M-110,-90 L-80,-90" fill="none" stroke="#8a939d" stroke-width="10"/>')


def hose(a: dict) -> str:
    c = a.get("data-fill", "#2f9e44")
    straight = a.get("data-state", "kinked") == "straight"
    d = ("M-250,0 C-120,0 0,0 120,0 C200,0 260,0 310,0" if straight else
         "M-250,-150 C-120,-150 -60,-140 10,-90 L120,10 L10,110 C-60,160 -120,170 -250,170")
    tap_y = -40 if straight else -190
    return (f'<path d="{d}" fill="none" stroke="#433026" stroke-width="72" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="{d}" fill="none" stroke="{c}" stroke-width="54" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<rect x="-330" y="{tap_y}" width="80" height="80" rx="12" fill="#9aa5b1"/>')


def molecule(a: dict) -> str:
    c = a.get("data-fill", "#3b82c4")
    return ('<path d="M-70,40 L0,-40 L80,40" fill="none" stroke-width="16"/>'
            f'<circle cx="0" cy="-40" r="70" fill="{c}"/><circle cx="-80" cy="50" r="48" fill="#ffffff"/>'
            '<circle cx="90" cy="50" r="48" fill="#ffffff"/>'
            '<circle cx="-18" cy="-62" r="14" fill="#ffffff" stroke="none"/>')


def spoon(a: dict) -> str:
    c = a.get("data-fill", "#aab4bf")
    hi = "#ffffff" if c.lower() in ("#aab4bf", "#9aa5b1", "#cfd6dd") else "#8a5a2b"
    return (f'<path d="M-22,-110 C-30,20 -18,190 -14,250 C-12,272 12,272 14,250 C18,190 30,20 22,-110 Z" fill="{c}" stroke-linejoin="round"/>'
            f'<ellipse cx="0" cy="-190" rx="68" ry="96" fill="{c}"/>'
            f'<path d="M-30,-240 C-40,-210 -40,-170 -28,-140 M0,40 L0,200" fill="none" stroke="{hi}" stroke-width="9"/>')


def bowl(a: dict) -> str:
    c = a.get("data-fill", "#3b82c4")
    return (f'<ellipse cx="0" cy="-40" rx="200" ry="44" fill="{c}"/>'
            '<path d="M-205,-40 C-200,60 -110,110 0,110 C110,110 200,60 205,-40 C150,-8 -150,-8 -205,-40 Z" fill="#ffffff" '
            'stroke-linejoin="round"/>'
            '<path d="M-60,110 L-80,150 L80,150 L60,110" fill="#ffffff" stroke-linejoin="round"/>'
            '<path d="M-120,-46 C-90,-56 -60,-36 -30,-46" fill="none" stroke="#ffffff" stroke-width="8"/>')


def bench(a: dict) -> str:
    c = a.get("data-fill", "#c98b4f")
    leg = "#5b6470"
    return (f'<path d="M-250,20 L-250,150 M250,20 L250,150 M-230,-100 L-230,20 M230,-100 L230,20" fill="none" stroke="{leg}" '
            'stroke-width="26" stroke-linecap="round"/>'
            f'<rect x="-310" y="-150" width="620" height="44" rx="14" fill="{c}"/>'
            f'<rect x="-310" y="-90" width="620" height="44" rx="14" fill="{c}"/>'
            f'<rect x="-310" y="0" width="620" height="46" rx="14" fill="{c}"/>')


def slide(a: dict) -> str:
    return ('<path d="M-240,-200 L-240,230 M-150,-200 L-150,230 M-240,-120 L-150,-120 M-240,-40 L-150,-40 M-240,40 L-150,40 '
            'M-240,120 L-150,120" fill="none" stroke="#e8452c" stroke-width="18" stroke-linecap="round"/>'
            '<rect x="-270" y="-230" width="150" height="40" rx="12" fill="#e8452c"/>'
            '<path d="M-130,-220 C40,-200 80,120 280,190 L280,230 C60,170 10,-130 -130,-170 Z" fill="#cfd6dd" stroke-linejoin="round"/>'
            '<path d="M-90,-190 C40,-160 90,100 250,170" fill="none" stroke="#ffffff" stroke-width="10"/>')


def heat_sink(a: dict) -> str:
    fins = "".join(f'<rect x="{-200 + 50 * k}" y="-150" width="26" height="150" rx="6" fill="#cfd6dd"/>' for k in range(9))
    return ('<rect x="-230" y="40" width="460" height="70" rx="12" fill="#2f9e44"/>'
            '<rect x="-130" y="10" width="260" height="40" rx="8" fill="#3a3f45"/>'
            '<rect x="-215" y="-10" width="430" height="30" rx="8" fill="#aab4bf"/>' + fins +
            '<path d="M-200,110 L-200,150 M-120,110 L-120,150 M-40,110 L-40,150 M40,110 L40,150 M120,110 L120,150 M200,110 L200,150" '
            'fill="none" stroke="#b08900" stroke-width="12"/>')


def jacket(a: dict) -> str:
    c = a.get("data-fill", "#3b82c4")
    return (f'<path d="M-120,-200 C-60,-170 60,-170 120,-200 L200,-150 L215,180 C160,200 120,200 100,190 L100,210 L-100,210 '
            f'L-100,190 C-120,200 -160,200 -215,180 L-200,-150 Z" fill="{c}" stroke-linejoin="round"/>'
            '<path d="M-100,-80 C-40,-60 40,-60 100,-80 M-100,20 C-40,40 40,40 100,20 M-100,120 C-40,140 40,140 100,120 '
            'M-205,-40 L-100,-40 M100,-40 L205,-40 M-210,80 L-100,80 M100,80 L210,80" fill="none" stroke-width="7"/>'
            '<path d="M0,-175 L0,210" fill="none" stroke-width="9"/>'
            '<path d="M-60,-195 C-30,-150 30,-150 60,-195" fill="#f1f3f5" stroke-linejoin="round"/>')


def cup(a: dict) -> str:
    return ('<path d="M-90,-90 L90,-90 L66,150 L-66,150 Z" fill="#ffffff" stroke-linejoin="round"/>'
            '<rect x="-108" y="-130" width="216" height="44" rx="14" fill="#9a9a9a"/>'
            '<path d="M-84,-20 L84,-20 L76,60 L-76,60 Z" fill="#c98b4f" stroke-linejoin="round"/>'
            '<path d="M-30,-160 L30,-160 L30,-130 L-30,-130 Z" fill="#9a9a9a"/>')


def water(a: dict) -> str:
    c = a.get("data-fill", "#7cc6f2")
    return (f'<path d="M-350,-40 C-300,-80 -250,0 -200,-40 C-150,-80 -100,0 -50,-40 C0,-80 50,0 100,-40 C150,-80 200,0 250,-40 '
            f'C300,-80 330,-40 350,-40 L350,100 L-350,100 Z" fill="{c}" stroke-linejoin="round"/>'
            '<path d="M-260,20 C-230,8 -200,32 -170,20 M60,40 C90,28 120,52 150,40" fill="none" stroke="#ffffff" stroke-width="9"/>')


def rug(a: dict) -> str:
    return ('<rect x="-280" y="-20" width="260" height="60" rx="4" fill="#cfd6dd"/>'
            '<path d="M-215,-20 L-215,40 M-150,-20 L-150,40 M-85,-20 L-85,40" fill="none" stroke-width="6"/>'
            '<rect x="0" y="-40" width="280" height="80" rx="20" fill="#f783ac"/>'
            '<path d="M20,-10 C70,-30 120,10 170,-10 C210,-25 240,0 262,-10 M20,20 C70,0 120,40 170,20 C210,5 240,30 262,20" '
            'fill="none" stroke="#c2255c" stroke-width="7"/>'
            '<path d="M0,-30 L-14,-30 M0,0 L-14,0 M0,30 L-14,30 M280,-30 L294,-30 M280,0 L294,0 M280,30 L294,30" fill="none" stroke-width="6"/>')


def skin_layers(a: dict) -> str:
    s = _skin(a)
    return (f'<path d="M-350,-150 C-200,-170 -60,-130 80,-150 C200,-166 300,-140 350,-150 L350,-40 L-350,-40 Z" fill="{s}" stroke-linejoin="round"/>'
            '<rect x="-350" y="-40" width="700" height="110" fill="#f4b8a0"/>'
            '<rect x="-350" y="70" width="700" height="110" fill="#ffe8a3"/>'
            '<path d="M-220,180 C-220,60 -230,-40 -210,-120 M-210,-120 L-240,-140 M-210,-120 L-185,-145" fill="none" stroke="#3b82c4" stroke-width="12" stroke-linecap="round"/>'
            '<path d="M-60,180 C-60,60 -70,-40 -50,-120 M-50,-120 L-80,-140 M-50,-120 L-25,-145" fill="none" stroke="#e8452c" stroke-width="12" stroke-linecap="round"/>'
            '<path d="M120,180 C120,60 110,-40 130,-120 M130,-120 L100,-140 M130,-120 L155,-145" fill="none" stroke="#3b82c4" stroke-width="12" stroke-linecap="round"/>'
            '<path d="M260,180 C260,60 250,-40 270,-120 M270,-120 L240,-140 M270,-120 L295,-145" fill="none" stroke="#e8452c" stroke-width="12" stroke-linecap="round"/>'
            '<path d="M-350,-150 C-200,-170 -60,-130 80,-150 C200,-166 300,-140 350,-150" fill="none" stroke-width="10"/>')


def piggy_bank(a: dict) -> str:
    return ('<rect x="-130" y="80" width="44" height="80" rx="14" fill="#f06595"/><rect x="-60" y="96" width="44" height="70" rx="14" fill="#f06595"/>'
            '<rect x="20" y="96" width="44" height="70" rx="14" fill="#f06595"/><rect x="90" y="80" width="44" height="80" rx="14" fill="#f06595"/>'
            '<ellipse cx="0" cy="0" rx="170" ry="120" fill="#f783ac"/>'
            '<path d="M150,-30 L210,-40 L210,30 L150,25" fill="#f783ac" stroke-linejoin="round"/>'
            '<circle cx="190" cy="-8" r="6" fill="#433026" stroke="none"/><circle cx="190" cy="12" r="6" fill="#433026" stroke="none"/>'
            '<path d="M60,-110 L90,-170 L110,-100" fill="#f783ac" stroke-linejoin="round"/>'
            '<circle cx="100" cy="-40" r="12" fill="#433026" stroke="none"/>'
            '<path d="M-40,-118 L40,-118" fill="none" stroke-width="12" stroke-linecap="round"/>'
            '<path d="M-170,-10 C-210,-20 -210,-60 -185,-60" fill="none" stroke-width="8"/>')


def finger(a: dict) -> str:
    """Pointing hand (right): curled fist with knuckle lines, extended index finger with a nail, thumb on top.
    v3.3.1: redrawn — the first version read as a flat paddle in the long-form review."""
    s = _skin(a)
    return (f'<path d="M-40,-62 C40,-66 120,-62 186,-58 C212,-56 214,-24 188,-22 C130,-20 70,-22 30,-20" fill="{s}" stroke-linejoin="round"/>'
            f'<path d="M168,-54 C182,-52 184,-30 170,-28" fill="none" stroke="{LINE}" stroke-width="7"/>'
            f'<path d="M-190,-40 C-190,-80 -120,-90 -40,-70 L30,-22 C40,10 30,60 -10,72 C-60,86 -150,84 -180,60 C-200,40 -200,0 -190,-40 Z" '
            f'fill="{s}" stroke-linejoin="round"/>'
            f'<path d="M-20,-8 C10,-4 22,8 18,22 M-30,22 C0,26 12,38 8,50 M-50,50 C-24,54 -14,64 -18,74" fill="none" stroke="{LINE}" stroke-width="7"/>'
            f'<path d="M-120,-78 C-80,-110 -20,-104 10,-70 C-10,-60 -50,-58 -80,-62" fill="{s}" stroke-linejoin="round"/>'
            '<path d="M-200,-30 L-240,-30 L-240,60 L-196,60" fill="#3b82c4" stroke-linejoin="round"/>')


def puddle(a: dict) -> str:
    return ('<path d="M-150,10 C-150,-30 -60,-40 0,-34 C80,-44 150,-24 150,8 C150,40 60,46 0,40 C-70,48 -150,44 -150,10 Z" '
            'fill="#bfe4f7" stroke-linejoin="round"/>'
            '<path d="M-90,-6 C-60,-16 -30,-2 -10,-10" fill="none" stroke="#ffffff" stroke-width="8"/>')


def speaker(a: dict) -> str:
    c = a.get("data-fill", "#3a3f45")
    return (f'<path d="M-140,-50 L-70,-50 L20,-130 L20,130 L-70,50 L-140,50 Z" fill="{c}" stroke-linejoin="round"/>'
            '<path d="M60,-60 C95,-25 95,25 60,60 M95,-100 C150,-40 150,40 95,100" fill="none" stroke-width="14" stroke-linecap="round"/>')


def fan(a: dict) -> str:
    blade = '<path d="M0,0 C-20,-40 -10,-110 40,-120 C70,-80 50,-30 0,0 Z" fill="#7cc6f2"/>'
    return ('<rect x="-150" y="-150" width="300" height="300" rx="36" fill="#3a3f45"/>'
            '<circle cx="0" cy="0" r="122" fill="#e9ecef"/>'
            + "".join(f'<g transform="rotate({k * 120})">{blade}</g>' for k in range(3)) +
            '<circle cx="0" cy="0" r="26" fill="#5b6470"/>'
            '<circle cx="-118" cy="-118" r="10" fill="#adb5bd" stroke="none"/><circle cx="118" cy="-118" r="10" fill="#adb5bd" stroke="none"/>'
            '<circle cx="-118" cy="118" r="10" fill="#adb5bd" stroke="none"/><circle cx="118" cy="118" r="10" fill="#adb5bd" stroke="none"/>')


def railing(a: dict) -> str:
    """Stair handrail: a diagonal rail on two posts over a flight of steps. v3.3.1: a level rail on bars read as a
    radiator (and a level rail on posts as a table) in the long-form review; the stairs make it unmistakable."""
    c = a.get("data-fill", "#9aa5b1")
    return ('<path d="M-300,170 L-300,110 L-180,110 L-180,50 L-60,50 L-60,-10 L60,-10 L60,-70 L180,-70 L180,-130 L300,-130 '
            'L300,170 Z" fill="#dee2e6" stroke-linejoin="round"/>'
            f'<rect x="-262" y="-60" width="34" height="170" rx="8" fill="{c}"/>'
            f'<rect x="232" y="-280" width="34" height="150" rx="8" fill="{c}"/>'
            f'<path d="M-280,-70 L290,-290" fill="none" stroke="#1d1b1a" stroke-width="44" stroke-linecap="round"/>'
            f'<path d="M-280,-70 L290,-290" fill="none" stroke="{c}" stroke-width="30" stroke-linecap="round"/>'
            '<path d="M-250,-90 L250,-283" fill="none" stroke="#ffffff" stroke-width="6" stroke-linecap="round"/>')


PARTS = {"leg": leg, "ear": ear, "head": head, "hand": hand, "eye": eye, "plane": plane, "thermometer": thermometer,
         "metal_block": metal_block, "wood_block": wood_block, "ice_cube": ice_cube, "mug": mug, "pan": pan,
         "flame": flame, "weight": weight, "hose": hose, "molecule": molecule, "spoon": spoon, "bowl": bowl,
         "bench": bench, "slide": slide, "heat_sink": heat_sink, "jacket": jacket, "cup": cup, "water": water, "rug": rug,
         "skin_layers": skin_layers, "piggy_bank": piggy_bank, "finger": finger, "puddle": puddle,
         "speaker": speaker, "fan": fan, "railing": railing}
