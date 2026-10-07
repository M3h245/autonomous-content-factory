"""Storyboard + doodle scenes for the flamingo video (one scene per beat of script B)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fshapes import DEEP, SVG, flamingo, ground, text, water  # noqa: E402

run = Path(sys.argv[1])
v = run / "videos" / "v01" / "visual"
(v / "svg").mkdir(parents=True, exist_ok=True)


def padlock(cx, cy, at, s=1.0):
    return (f'<g data-in="pop" data-at="{at}"><path d="M{cx - 34 * s},{cy} L{cx - 34 * s},{cy - 40 * s} C{cx - 34 * s},{cy - 92 * s} '
            f'{cx + 34 * s},{cy - 92 * s} {cx + 34 * s},{cy - 40 * s} L{cx + 34 * s},{cy}" fill="none" stroke="#555" stroke-width="{12 * s}"/>'
            f'<rect x="{cx - 56 * s}" y="{cy - 6 * s}" width="{112 * s}" height="{92 * s}" rx="{14 * s}" fill="#ffd23f"/>'
            f'<circle cx="{cx}" cy="{cy + 34 * s}" r="{11 * s}" fill="#5b4636"/></g>')


def stand(x, top, base=1040, at="w:propped"):
    return (f'<g data-in="slide-left" data-at="{at}"><rect x="{x - 14}" y="{top}" width="28" height="{base - top}" fill="#9aa5b1"/>'
            f'<rect x="{x - 90}" y="{base - 22}" width="180" height="22" rx="8" fill="#6b7785"/>'
            f'<rect x="{x}" y="{top + 30}" width="150" height="22" fill="#9aa5b1"/>'
            f'<path d="M{x + 150},{top + 10} q30,31 0,62" fill="none" stroke="#6b7785" stroke-width="14"/></g>')


def thermometer(cx, top, at):
    return (f'<g data-in="pop" data-at="{at}"><rect x="{cx - 34}" y="{top}" width="68" height="360" rx="34" fill="white"/>'
            f'<circle cx="{cx}" cy="{top + 400}" r="64" fill="#3b82c4"/><rect x="{cx - 16}" y="{top + 250}" width="32" height="140" fill="#3b82c4"/>'
            + "".join(f'<path d="M{cx + 34},{top + 60 + k * 60} l26,0" fill="none" stroke="#555" stroke-width="5"/>' for k in range(4)) + "</g>")


def armchair(cx, base, s=1.0, at="w:armchair", gid="chair"):
    X = lambda dx: cx + dx * s  # noqa: E731
    Y = lambda dy: base - dy * s  # noqa: E731
    return (f'<g id="{gid}" data-in="pop" data-at="{at}">'
            f'<rect x="{X(-170)}" y="{Y(560)}" width="{340 * s}" height="{330 * s}" rx="{70 * s}" fill="#e8452c"/>'
            f'<rect x="{X(-220)}" y="{Y(300)}" width="{440 * s}" height="{150 * s}" rx="{40 * s}" fill="#c23b24"/>'
            f'<rect x="{X(-250)}" y="{Y(380)}" width="{90 * s}" height="{240 * s}" rx="{40 * s}" fill="#e8452c"/>'
            f'<rect x="{X(160)}" y="{Y(380)}" width="{90 * s}" height="{240 * s}" rx="{40 * s}" fill="#e8452c"/>'
            f'<rect x="{X(-200)}" y="{Y(150)}" width="{36 * s}" height="{150 * s}" fill="#5b4636"/>'
            f'<rect x="{X(164)}" y="{Y(150)}" width="{36 * s}" height="{150 * s}" fill="#5b4636"/></g>')


S = {}
# b1 "One leg or two: which tires a flamingo?" — frame 0 from the selected hook h3 (split)
S["s1"] = (SVG + ground() + flamingo("one", 300, 1040, 0.72) + flamingo("two", 790, 1040, 0.72, legs=2, flip=True)
           + '<g data-lib="question" transform="translate(545 560) scale(1.0)" data-in="pop" data-at="0.25" data-loop="bob"/>'
           + text("1 LEG OR 2?", 215, 120)
           + '<g data-lib="sparkle" data-fill="p0" transform="translate(160 620) scale(0.8)" data-in="pop" data-at="w:leg"/>'
           + '<g data-lib="sweat" transform="translate(900 300) scale(1.1)" data-in="pop" data-at="w:tires"/>'
           + '<g data-lib="sparkle" data-fill="p4" transform="translate(940 620) scale(0.8)" data-in="pop" data-at="w:flamingo"/>' + "</svg>")
# b2 "Two legs. And a dead flamingo showed it." — text-led answer
S["s2"] = (SVG + ground() + text("TWO LEGS", 330, 170, attrs='data-in="pop" data-at="0.05"')
           + flamingo("tired", 300, 1040, 0.5, legs=2, attrs='data-in="none"')
           + '<g data-lib="sweat" transform="translate(390 540) scale(0.9)" data-in="pop" data-at="w:legs"/>'
           + flamingo("dead", 780, 1040, 0.5, face="dead", attrs='data-in="slide-left" data-at="w:dead"')
           + '<g data-lib="magnifier" transform="translate(860 640) scale(0.8)" data-in="pop" data-at="w:showed"/>' + "</svg>")
# b3 "In 2017, researchers propped one up. On one leg, it locked in place, no muscle needed." — hero
S["s3"] = (SVG + ground() + flamingo("deadone", 500, 1040, 0.68, face="dead") + stand(860, 520)
           + text("2017", 480, 110, x=190, attrs='data-in="pop" data-at="w:2017"')
           + padlock(500, 890, "w:locked", 0.9)
           + text("NO MUSCLE", 215, 120, attrs='data-in="write" data-at="w:muscle"')
           + '<g data-lib="check" transform="translate(190 700) scale(1.6)" data-in="draw" data-at="w:place"/>' + "</svg>")
# b4 "On two legs, it wouldn't stay steady." — hero, tipping
S["s4"] = (SVG + ground() + '<g transform="rotate(-9 540 1040)">' + flamingo("deadtwo", 540, 1040, 0.74, legs=2, face="dead",
                                                                             attrs='data-in="none" data-loop="tremble"') + "</g>"
           + '<g data-lib="lines" transform="translate(150 520) scale(1.2)" data-in="draw" data-at="w:two"/>'
           + '<g data-lib="cross" transform="translate(860 520) scale(1.4)" data-in="pop" data-at="w:steady"/>'
           + text("WOBBLY", 215, 120, attrs='data-in="write" data-at="w:wouldn\'t"') + "</svg>")
# b5 "Live birds at Zoo Atlanta swayed less when they dozed off." — panel (sway trace)
S["s5"] = (SVG + '<g id="board" data-in="none"><rect x="90" y="520" width="900" height="420" rx="36" fill="#e7f5ff"/></g>'
           + '<path d="M140,730 q40,-120 80,0 t80,0 t80,0 t80,0 t80,0" fill="none" stroke="#e8452c" stroke-width="10" data-in="draw" data-at="w:swayed"/>'
           + '<path d="M540,730 q40,-26 80,0 t80,0 t80,0 t80,0 t80,0" fill="none" stroke="#3b82c4" stroke-width="10" data-in="draw" data-at="w:dozed"/>'
           + text("AWAKE", 610, 64, x=320, family="hand", attrs='data-in="pop" data-at="w:live"')
           + text("ASLEEP", 610, 64, x=760, family="hand", attrs='data-in="pop" data-at="w:dozed"')
           + text("SWAY", 300, 120, attrs='data-in="write" data-at="w:swayed"')
           + '<g data-lib="zz" transform="translate(880 470) scale(1.0)" data-in="pop" data-at="w:off" data-loop="float"/>' + "</svg>")
# b6 "There's a second reason: they tuck a leg more in cold water, so it may save heat." — hero in cold water
S["s6"] = (SVG + water(1040) + flamingo("wader", 620, 1030, 0.66) + thermometer(190, 470, "w:cold")
           + text("REASON 2", 215, 120, attrs='data-in="write" data-at="w:second"')
           + '<g data-lib="sparkle" data-fill="#7cc6f2" transform="translate(900 860) scale(0.9)" data-in="pop" data-at="w:water"/>'
           + '<g data-lib="heart" data-fill="p1" transform="translate(470 650) scale(0.7)" data-in="pop" data-at="w:heat" data-loop="pulse"/>'
           + text("KEEPS WARM?", 318, 72, family="hand", attrs='data-in="write" data-at="w:save"') + "</svg>")
# b7 "One leg isn't a balancing act. It's a flamingo's armchair." — split: armchair = one leg
S["s7"] = (SVG + ground() + armchair(300, 1040, 1.0, at="w:balancing") + flamingo("rest", 800, 1040, 0.62, face="happy", flip=True)
           + text("BALANCING ACT?", 215, 96, attrs='data-in="write" data-at="w:balancing"')
           + '<path d="M120,180 L960,196" fill="none" stroke="#e8452c" stroke-width="14" data-in="draw" data-at="w:act"/>'
           + text("=", 760, 140, x=560, attrs='data-in="pop" data-at="w:armchair"') + "</svg>")
# b8 loop "So next time you see one on one leg, it's resting." — back to the opening one-legged flamingo
S["s8"] = (SVG + ground() + flamingo("one", 540, 1040, 0.72)
           + '<g data-lib="sparkle" data-fill="p0" transform="translate(250 560) scale(0.9)" data-in="pop" data-at="w:see"/>'
           + '<g data-lib="zz" transform="translate(830 420) scale(1.8)" data-in="pop" data-at="w:resting" data-loop="float"/>'
           + text("RESTING", 215, 130, attrs='data-in="write" data-at="w:resting"') + "</svg>")
for k, s in S.items():
    (v / "svg" / f"{k}.svg").write_text(s)
beats = {"s1": ["b1"], "s2": ["b2"], "s3": ["b3"], "s4": ["b4"], "s5": ["b5"], "s6": ["b6"], "s7": ["b7"], "s8": ["b8"]}
cams = {"s1": {"drift": "none"}, "s2": {"drift": "in"}, "s3": {"drift": "none", "punch": [{"at": "w:locked", "focus": "#deadone", "zoom": 1.06, "hold": 0.8}]},
        "s4": {"drift": "out", "shake": ["w:steady"]}, "s5": {"drift": "right"}, "s6": {"drift": "in"},
        "s7": {"drift": "none", "punch": [{"at": "w:armchair", "zoom": 1.05, "hold": 0.7}]}, "s8": {"drift": "none"}}
trans = {"s2": "cut", "s3": "paper", "s4": "whip", "s5": "paper", "s6": "whip-up", "s7": "pop", "s8": "flash"}
scenes = [{"id": k, "beat_ids": beats[k], "visual": {"kind": "doodle", "svg_path": f"svg/{k}.svg"}, "camera": cams[k],
           **({"transition": {"type": trans[k]}} if k in trans else {})} for k in S]
(v / "storyboard.json").write_text(json.dumps({"video_id": "v01", "style": {"palette": ["#ffd23f", "#e8452c", "#3b82c4", "#2f9e44", "#f783ac"],
                                                                         "paper": "plain", "mood": "warm, playful"}, "scenes": scenes}, indent=1))
print("wrote", len(S), "scenes")
