"""Storyboard + doodle scenes for the flamingo video, fix round (hook h4, script B, 7 beats; one scene per beat)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fshapes import DEEP, SVG, flamingo, ground, sway, text, water  # noqa: E402

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


def stand_left(x, top, reach, base=1040, at="w:propped"):
    """Lab stand at x whose arm reaches left to x - reach and clamps down onto the bird's back."""
    return (f'<g data-in="slide-left" data-at="{at}"><rect x="{x - 14}" y="{top}" width="28" height="{base - top}" fill="#9aa5b1"/>'
            f'<rect x="{x - 90}" y="{base - 22}" width="180" height="22" rx="8" fill="#6b7785"/>'
            f'<rect x="{x - reach}" y="{top + 30}" width="{reach}" height="22" fill="#9aa5b1"/>'
            f'<path d="M{x - reach},{top + 52} l0,46" fill="none" stroke="#6b7785" stroke-width="14"/></g>')


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
# b1 "Why do flamingos rest on one leg?" — frame 0 from the selected hook h4 (hero in water)
S["s1"] = (SVG + water(1040) + flamingo("bird", 560, 1030, 0.76)
           + '<g data-lib="question" transform="translate(860 520) scale(1.1)" data-in="pop" data-at="0.2" data-loop="bob"/>'
           + text("WHY ONE LEG?", 215, 120)
           + '<g data-lib="sparkle" data-fill="#7cc6f2" transform="translate(200 900) scale(0.8)" data-in="pop" data-at="w:flamingos"/>'
           + '<g data-lib="sparkle" data-fill="p0" transform="translate(240 560) scale(0.7)" data-in="pop" data-at="w:leg"/>' + "</svg>")
# b2 "In 2017, scientists tested a dead flamingo." — character: a scientist, then the dead bird slides in
S["s2"] = (SVG + ground() + '<g data-lib="dude" data-pose="point" data-face="think" data-acc="glasses,coat" transform="translate(300 1040) scale(1.6)" data-in="none"/>'
           + text("2017 TEST", 215, 120, attrs='data-in="write" data-at="w:2017"')
           + '<g data-lib="magnifier" transform="translate(600 470) scale(0.9)" data-in="pop" data-at="w:scientists"/>'
           + flamingo("dead", 800, 1040, 0.52, face="dead", attrs='data-in="slide-left" data-at="w:tested"')
           + '<g data-lib="exclaim" transform="translate(960 420) scale(0.9)" data-in="pop" data-at="w:dead"/>' + "</svg>")
# b3 "Propped on one leg, it held steady with no muscle working." — hero on the stand
S["s3"] = (SVG + ground() + flamingo("deadone", 500, 1040, 0.68, face="dead") + stand_left(870, 500, 270)
           + text("NO MUSCLE", 215, 120, attrs='data-in="write" data-at="w:muscle"')
           + '<g data-lib="check" transform="translate(190 700) scale(1.6)" data-in="draw" data-at="w:steady"/>' + "</svg>")
# b4 "On two legs, it wouldn't." — hero, tipping
S["s4"] = (SVG + ground() + '<g transform="rotate(-9 540 1040)">' + flamingo("deadtwo", 540, 1040, 0.74, legs=2, face="dead",
                                                                             attrs='data-in="none" data-loop="tremble"') + "</g>"
           + '<g data-lib="lines" transform="translate(150 520) scale(1.2)" data-in="draw" data-at="w:two"/>'
           + '<g data-lib="cross" transform="translate(860 520) scale(1.4)" data-in="pop" data-at="w:wouldn\'t"/>'
           + text("WOBBLY", 215, 120, attrs='data-in="write" data-at="w:legs"') + "</svg>")
# b5 "Live birds at Zoo Atlanta swayed less when they dozed off." — split: awake bird sways a lot, dozing bird barely
S["s5"] = (SVG + ground() + flamingo("awake", 300, 1040, 0.56) + flamingo("asleep", 790, 1040, 0.56, sleep=True, flip=True)
           + text("ZOO ATLANTA", 215, 110, attrs='data-in="write" data-at="w:zoo"')
           + '<g data-in="pop" data-at="w:swayed"><path d="M110,560 q-50,70 0,140" fill="none" stroke="#e8452c" stroke-width="10"/>'
           + '<path d="M490,560 q50,70 0,140" fill="none" stroke="#e8452c" stroke-width="10"/></g>'
           + sway(790, 640, "w:less", w=170)
           + '<g data-lib="zz" transform="translate(930 430) scale(1.0)" data-in="pop" data-at="w:dozed" data-loop="float"/>' + "</svg>")
# b6 "In a 2010 zoo study, more did it in water and in the cold. That may save heat." — hero in cold water
S["s6"] = (SVG + water(1040) + flamingo("wader", 620, 1030, 0.66) + thermometer(190, 470, "w:cold")
           + text("2010 STUDY", 215, 120, attrs='data-in="write" data-at="w:2010"')
           + '<g data-lib="sparkle" data-fill="#7cc6f2" transform="translate(900 860) scale(0.9)" data-in="pop" data-at="w:water"/>'
           + '<g data-lib="heart" data-fill="p1" transform="translate(470 650) scale(0.7)" data-in="pop" data-at="w:heat" data-loop="pulse"/>'
           + text("KEEPS WARM?", 318, 72, family="hand", attrs='data-in="write" data-at="w:save"') + "</svg>")
# b7 "So one leg isn't hard work. It's how a flamingo rests." — split: armchair = one leg
S["s7"] = (SVG + ground() + armchair(300, 1040, 1.0, at="w:rests") + flamingo("rest", 800, 1040, 0.62, face="happy", flip=True)
           + text("HARD WORK?", 215, 110, attrs='data-in="write" data-at="w:hard"')
           + '<path d="M170,180 L910,196" fill="none" stroke="#e8452c" stroke-width="14" data-in="draw" data-at="w:isn\'t"/>'
           + '<g data-lib="sparkle" data-fill="p0" transform="translate(800 330) scale(0.8)" data-in="pop" data-at="w:flamingo"/>'
           + text("=", 760, 140, x=560, attrs='data-in="pop" data-at="w:rests"') + "</svg>")
for k, s in S.items():
    (v / "svg" / f"{k}.svg").write_text(s)
beats = {f"s{i}": [f"b{i}"] for i in range(1, 8)}
cams = {"s1": {"drift": "none"}, "s2": {"drift": "in"}, "s3": {"drift": "none", "punch": [{"at": "w:steady", "focus": "#deadone", "zoom": 1.06, "hold": 0.8}]},
        "s4": {"drift": "out", "shake": ["w:wouldn't"]}, "s5": {"drift": "right"}, "s6": {"drift": "in"},
        "s7": {"drift": "none", "punch": [{"at": "w:rests", "zoom": 1.05, "hold": 0.7}]}}
trans = {"s2": "cut", "s3": "paper", "s4": "whip", "s5": "paper", "s6": "whip-up", "s7": "pop"}
scenes = [{"id": k, "beat_ids": beats[k], "visual": {"kind": "doodle", "svg_path": f"svg/{k}.svg"}, "camera": cams[k],
           **({"transition": {"type": trans[k]}} if k in trans else {})} for k in S]
(v / "storyboard.json").write_text(json.dumps({"video_id": "v01", "style": {"palette": ["#ffd23f", "#e8452c", "#3b82c4", "#2f9e44", "#f783ac"],
                                                                         "paper": "plain", "mood": "warm, playful"}, "scenes": scenes}, indent=1))
print("wrote", len(S), "scenes")
