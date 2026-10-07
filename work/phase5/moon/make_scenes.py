"""Storyboard + doodle scenes for the Moon-illusion video, fix round (hook h5, script B, 7 beats). Night scenes use a navy background with
white text/strokes (the ink outline would vanish on dark); explanation scenes stay on paper."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mshapes import NIGHT, SVG, camera, moon, skyline, stars, text, tube  # noqa: E402

run = Path(sys.argv[1])
v = run / "videos" / "v01" / "visual"
(v / "svg").mkdir(parents=True, exist_ok=True)
W_ = "#ffffff"


def nail(cx, cy, at, s=1.0):
    return (f'<g data-in="pop" data-at="{at}"><rect x="{cx - 70 * s}" y="{cy - 85 * s}" width="{140 * s}" height="{170 * s}" rx="{60 * s}" '
            f'fill="#ffe8de" fill-opacity="0.8" data-outline="none"/></g>')


def photo(gid, x, y, w, h, mcy, at):
    return (f'<g id="{gid}" data-in="drop" data-at="{at}"><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="white"/>'
            f'<rect x="{x + 24}" y="{y + 24}" width="{w - 48}" height="{h - 110}" fill="{NIGHT}" data-outline="none"/>'
            f'<circle cx="{x + w / 2}" cy="{mcy}" r="92" fill="#fff3b0" data-outline="none"/></g>')


def ruler(x0, x1, y, at):
    return (f'<g data-in="draw" data-at="{at}"><path d="M{x0},{y} L{x1},{y} M{x0},{y - 22} L{x0},{y + 22} M{x1},{y - 22} L{x1},{y + 22}" '
            f'fill="none" stroke="#e8452c" stroke-width="9"/></g>')


def eye(cx, cy, at, s=1.0):
    return (f'<g data-in="pop" data-at="{at}"><ellipse cx="{cx}" cy="{cy}" rx="{90 * s}" ry="{52 * s}" fill="white" data-outline="none"/>'
            f'<circle cx="{cx + 14 * s}" cy="{cy}" r="{34 * s}" fill="#3b82c4" data-outline="none"/>'
            f'<circle cx="{cx + 18 * s}" cy="{cy}" r="{14 * s}" fill="#111" data-outline="none"/></g>')


S, BG = {}, {}
# b1 "Your camera says the Moon never grew." — frame 0 of hook h5 (hero, paper)
S["s1"] = (SVG + moon("moon", 600, 700, 345) + skyline() + camera(240, 560, 0.75, attrs='data-in="pop" data-at="0.2"')
           + text("CAMERA SAYS SAME", 215, 84)
           + stars([(930, 330, 0.8)], "w:says") + stars([(120, 330, 0.6)], "w:never") + "</svg>")
# b2 "Same-setting photos show the same width near the horizon and high up." — split of two photos, paper
S["s2"] = (SVG + photo("photo1", 70, 470, 440, 560, 860, "0") + photo("photo2", 570, 470, 440, 560, 620, "w:photos")
           + ruler(198, 382, 1080 - 30, "w:width") + ruler(698, 882, 1080 - 30, "w:width")
           + text("SAME WIDTH", 300, 120, attrs='data-in="write" data-at="w:same"')
           + text("HORIZON", 1000, 52, x=290, family="hand", attrs='data-in="pop" data-at="w:horizon"')
           + text("HIGH UP", 1000, 52, x=790, family="hand", attrs='data-in="pop" data-at="w:high"') + "</svg>")
# b3 "And down low, it's about 1.5 percent farther away." — hero, night
BG["s3"] = NIGHT
S["s3"] = (SVG + moon("lowmoon", 700, 760, 290, outline=False) + skyline(1040, fill="#0f1a36")
           + eye(170, 900, "w:low", 0.9)
           + '<path d="M270,890 L420,850" fill="none" stroke="#ffd23f" stroke-width="12" data-in="draw" data-at="w:farther"/>'
           + text("1.5% FARTHER", 230, 116, fill=W_, attrs='data-in="write" data-at="w:1.5"')
           + stars([(140, 420, 0.6), (420, 360, 0.5)], "w:about") + "</svg>")
# b4 "It's your brain." — hero (brain), paper
S["s4"] = (SVG + '<g data-lib="brain" data-face="think" data-fill="p4" transform="translate(540 720) scale(2.4)" data-in="none" data-loop="wiggle"/>'
           + text("YOUR BRAIN", 215, 130, attrs='data-in="pop" data-at="w:your"')
           + '<g data-lib="sparkle" data-fill="p0" transform="translate(200 560) scale(0.9)" data-in="pop" data-at="w:brain"/>'
           + '<g data-lib="sparkle" data-fill="p2" transform="translate(880 900) scale(0.8)" data-in="pop" data-at="w:brain"/>' + "</svg>")
# b5 "A leading explanation: it judges the horizon Moon farther away, so it sees it bigger." — panel: far → bigger, paper
S["s5"] = (SVG + '<path d="M80,1000 L1000,1000" fill="none" stroke="#5b4636" stroke-width="7" data-in="none"/>'
           + moon("horizon", 760, 750, 252, attrs='data-in="none" data-loop="pulse"')
           + text("LEADING EXPLANATION", 215, 80, attrs='data-in="write" data-at="w:leading"')
           + eye(170, 640, "w:judges", 1.0)
           + '<g data-lib="arrow" data-from="290,640" data-to="500,700" data-bend="-0.15" data-in="draw" data-at="w:horizon"/>'
           + text("FAR AWAY", 420, 84, x=330, attrs='data-in="write" data-at="w:farther"')
           + text("= BIGGER", 420, 84, x=800, attrs='data-in="pop" data-at="w:bigger"') + "</svg>")
# b6 "Scientists still argue about the exact cause." — character, paper
S["s6"] = (SVG + '<path d="M80,1046 C400,1038 700,1052 1000,1043" fill="none" stroke="#5b4636" stroke-width="7" data-in="none"/>'
           + '<g data-lib="dude" data-pose="point" data-face="angry" data-acc="glasses,coat" transform="translate(300 1040) scale(1.6)" data-in="none"/>'
           + '<g data-lib="dude" data-pose="shrug" data-face="meh" data-acc="coat" transform="translate(780 1040) scale(1.6)" data-in="pop" data-at="w:still"/>'
           + '<g data-lib="question" transform="translate(960 480) scale(1.1)" data-in="pop" data-at="w:argue"/>'
           + '<g data-lib="exclaim" transform="translate(120 480) scale(1.1)" data-in="pop" data-at="w:exact"/>'
           + text("STILL DEBATED", 215, 104, attrs='data-in="write" data-at="w:scientists"') + "</svg>")
# b7 "Try a rolled-up paper tube: the giant Moon shrinks." — hero (view through the tube), night
BG["s7"] = NIGHT
S["s7"] = (SVG + '<g id="view" data-in="none"><circle cx="560" cy="620" r="300" fill="#0f1a36" stroke="#f2e6c9" stroke-width="40"/></g>'
           + moon("tiny", 560, 620, 70, attrs='data-in="pop" data-at="w:giant"', outline=False)
           + eye(150, 1000, "w:try", 0.8) + tube(215, 965, 360, 850, 130, attrs='data-in="slide-up" data-at="w:rolled-up"')
           + text("SHRINK IT", 215, 130, fill=W_, attrs='data-in="write" data-at="w:shrinks"')
           + stars([(150, 420, 0.6), (960, 380, 0.6), (930, 960, 0.5)], "w:paper") + "</svg>")
for k, s in S.items():
    (v / "svg" / f"{k}.svg").write_text(s)
cams = {"s1": {"drift": "none"}, "s2": {"drift": "out"}, "s3": {"drift": "right"}, "s4": {"drift": "in"},
        "s5": {"drift": "none"}, "s6": {"drift": "none", "shake": ["w:argue"]}, "s7": {"drift": "in"}}
trans = {"s2": "paper", "s3": "whip", "s4": "flash", "s5": "paper", "s6": "pop", "s7": "fade"}
scenes = [{"id": k, "beat_ids": [f"b{k[1:]}"], "visual": {"kind": "doodle", "svg_path": f"svg/{k}.svg"}, "camera": cams[k],
           **({"transition": {"type": trans[k]}} if k in trans else {}), **({"bg": BG[k]} if k in BG else {})} for k in S]
(v / "storyboard.json").write_text(json.dumps({"video_id": "v01", "style": {"palette": ["#ffd23f", "#e8452c", "#3b82c4", "#2f9e44", "#f783ac"],
                                                                         "paper": "plain", "mood": "night, calm, curious"}, "scenes": scenes}, indent=1))
print("wrote", len(S), "scenes")
