"""Storyboard + doodle scenes for the Moon-illusion video (script A, 9 beats). Night scenes use a navy background with
white text/strokes (the ink outline would vanish on dark); explanation scenes stay on paper."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mshapes import NIGHT, SVG, hand_nail, moon, skyline, stars, text, tube  # noqa: E402

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
# b1 "Can your fingernail cover the giant Moon?" — frame 0 of hook h3 (hero, paper)
S["s1"] = (SVG + moon("moon", 600, 690, 340) + skyline() + hand_nail(230, 420, 0.9, attrs='data-in="slide-up" data-at="0.25"')
           + text("FINGERNAIL TEST", 215, 90)
           + stars([(930, 330, 0.8)], "w:cover") + "</svg>")
# b2 "Yes. At arm's length, it covers the same amount of Moon, low or high." — split, night
BG["s2"] = NIGHT
S["s2"] = (SVG + moon("low", 290, 790, 245, outline=False) + moon("high", 795, 500, 245, outline=False)
           + text("YES", 330, 150, x=290, fill=W_, attrs='data-in="pop" data-at="w:yes"')
           + nail(290, 790, "w:length") + nail(795, 500, "w:same")
           + text("LOW", 520, 70, x=290, family="hand", fill=W_, attrs='data-in="pop" data-at="w:low"')
           + text("HIGH", 830, 70, x=795, family="hand", fill=W_, attrs='data-in="pop" data-at="w:high"')
           + stars([(560, 300, 0.6), (960, 820, 0.5), (90, 420, 0.5)], "w:covers") + "</svg>")
# b3 "So the giant Moon isn't really giant." — text-led, paper
S["s3"] = (SVG + text("NOT GIANT", 330, 170, attrs='data-in="write" data-at="w:isn\'t"')
           + moon("normal", 540, 740, 190, attrs='data-in="none" data-loop="pulse"') + skyline(1040)
           + '<g data-lib="cross" transform="translate(860 560) scale(1.2)" data-in="pop" data-at="w:really"/>' + "</svg>")
# b4 "Photos with the same settings show the same width near the horizon and high up." — split of two photos, paper
S["s4"] = (SVG + photo("photo1", 70, 470, 440, 560, 860, "0") + photo("photo2", 570, 470, 440, 560, 620, "w:settings")
           + ruler(198, 382, 1080 - 30, "w:width") + ruler(698, 882, 1080 - 30, "w:width")
           + text("SAME WIDTH", 300, 120, attrs='data-in="write" data-at="w:same"')
           + text("HORIZON", 1000, 52, x=290, family="hand", attrs='data-in="pop" data-at="w:horizon"')
           + text("HIGH UP", 1000, 52, x=790, family="hand", attrs='data-in="pop" data-at="w:high"') + "</svg>")
# b5 "And down low, the Moon is actually about 1.5 percent farther away." — hero, night
BG["s5"] = NIGHT
S["s5"] = (SVG + moon("lowmoon", 700, 760, 290, outline=False) + skyline(1040, fill="#0f1a36")
           + eye(170, 900, "w:low", 0.9)
           + f'<path d="M270,890 L420,850" fill="none" stroke="#ffd23f" stroke-width="12" data-in="draw" data-at="w:farther"/>'
           + text("1.5% FARTHER", 230, 116, fill=W_, attrs='data-in="write" data-at="w:percent"')
           + stars([(140, 420, 0.6), (420, 360, 0.5)], "w:actually") + "</svg>")
# b6 "The leading idea: your brain thinks the horizon Moon is far away, so it sees it bigger." — hero (brain), paper
S["s6"] = (SVG + '<g data-lib="brain" data-face="think" data-fill="p4" transform="translate(540 700) scale(2.1)" data-in="none" data-loop="wiggle"/>'
           + '<path d="M90,1040 L990,1040" fill="none" stroke="#5b4636" stroke-width="7" data-in="none"/>'
           + '<g data-lib="sparkle" data-fill="p0" transform="translate(230 560) scale(0.9)" data-in="pop" data-at="w:brain"/>'
           + moon("far", 860, 980, 60, attrs='data-in="pop" data-at="w:horizon"')
           + text("FAR AWAY", 215, 88, x=310, attrs='data-in="write" data-at="w:far"')
           + '<g data-lib="arrow" data-from="760,860" data-to="840,950" data-bend="0.2" data-in="draw" data-at="w:away"/>'
           + text("= BIGGER", 215, 88, x=780, attrs='data-in="pop" data-at="w:bigger"') + "</svg>")
# b7 "Scientists still argue about the exact cause." — character, paper
S["s7"] = (SVG + '<path d="M80,1046 C400,1038 700,1052 1000,1043" fill="none" stroke="#5b4636" stroke-width="7" data-in="none"/>'
           + '<g data-lib="dude" data-pose="point" data-face="angry" data-acc="glasses,coat" transform="translate(300 1040) scale(1.6)" data-in="none"/>'
           + '<g data-lib="dude" data-pose="shrug" data-face="meh" data-acc="coat" transform="translate(780 1040) scale(1.6)" data-in="pop" data-at="w:still"/>'
           + '<g data-lib="question" transform="translate(960 480) scale(1.1)" data-in="pop" data-at="w:argue"/>'
           + '<g data-lib="exclaim" transform="translate(120 480) scale(1.1)" data-in="pop" data-at="w:exact"/>'
           + text("STILL DEBATED", 215, 104, attrs='data-in="write" data-at="w:scientists"') + "</svg>")
# b8 "But you can shrink it yourself: look through a rolled-up paper tube." — hero (view through the tube), night
BG["s8"] = NIGHT
S["s8"] = (SVG + '<g id="view" data-in="none"><circle cx="560" cy="620" r="300" fill="#0f1a36" stroke="#f2e6c9" stroke-width="40"/></g>'
           + moon("tiny", 560, 620, 70, attrs='data-in="pop" data-at="w:tube"', outline=False)
           + eye(150, 1000, "w:look", 0.8) + tube(215, 965, 360, 850, 130, attrs='data-in="slide-up" data-at="w:shrink"')
           + text("SHRINK IT", 215, 130, fill=W_, attrs='data-in="write" data-at="w:shrink"')
           + stars([(150, 420, 0.6), (960, 380, 0.6), (930, 960, 0.5)], "w:yourself") + "</svg>")
# b9 loop "Or just use your fingernail. Save this for the next big Moon." — back to the opening (hero, paper)
S["s9"] = (SVG + moon("moon", 600, 690, 340) + skyline() + hand_nail(230, 420, 0.9, attrs='data-in="slide-up" data-at="w:fingernail"')
           + text("FINGERNAIL TEST", 215, 90, attrs='data-in="none"')
           + text("SAVE FOR THE NEXT MOON", 330, 68, family="marker", attrs='data-in="pop" data-at="w:save"')
           + stars([(960, 480, 0.8)], "w:next") + "</svg>")
for k, s in S.items():
    (v / "svg" / f"{k}.svg").write_text(s)
cams = {"s1": {"drift": "none"}, "s2": {"drift": "in"}, "s3": {"drift": "none", "punch": [{"at": "w:giant#2", "zoom": 1.05, "hold": 0.6}]},
        "s4": {"drift": "out"}, "s5": {"drift": "right"}, "s6": {"drift": "none"},
        "s7": {"drift": "none", "shake": ["w:argue"]}, "s8": {"drift": "in"}, "s9": {"drift": "none"}}
trans = {"s2": "flash", "s3": "cut", "s4": "paper", "s5": "whip", "s6": "paper", "s7": "pop", "s8": "whip-up", "s9": "fade"}
scenes = [{"id": k, "beat_ids": [f"b{k[1:]}"], "visual": {"kind": "doodle", "svg_path": f"svg/{k}.svg"}, "camera": cams[k],
           **({"transition": {"type": trans[k]}} if k in trans else {}), **({"bg": BG[k]} if k in BG else {})} for k in S]
(v / "storyboard.json").write_text(json.dumps({"video_id": "v01", "style": {"palette": ["#ffd23f", "#e8452c", "#3b82c4", "#2f9e44", "#f783ac"],
                                                                         "paper": "plain", "mood": "night, calm, curious"}, "scenes": scenes}, indent=1))
print("wrote", len(S), "scenes")
