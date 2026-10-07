"""Storyboard + doodle scenes for the leap-year video (script B, 8 beats): number- and text-led layouts."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lshapes import SVG, calendar, cell, earth, orbit, quarter_clock, text  # noqa: E402

run = Path(sys.argv[1])
v = run / "videos" / "v01" / "visual"
(v / "svg").mkdir(parents=True, exist_ok=True)
CX, CY, CW, CH = 190, 340, 700, 720


def mark(kind, x, y, at, s=1.0):
    return f'<g data-lib="{kind}" transform="translate({x} {y}) scale({s})" data-in="pop" data-at="{at}"/>'


S = {}
# b1 "Leap years aren't every four years." — frame 0 of hook h2 (hero calendar)
S["s1"] = (SVG + calendar("cal", CX, CY, CW, CH, "FEB", "", hl=(0, 4)) + mark("cross", 900, 300, "0.25")
           + text("NOT EVERY 4", 215, 124) + mark("sparkle", *cell(CX, CY, CW, CH, 0, 4), "w:every", 0.7) + "</svg>")
# b2 "Most are. But century years only count if they divide by 400." — text-led rule
S["s2"] = (SVG + text("MOST ARE", 215, 110, attrs='data-in="write" data-at="w:most"') + mark("check", 905, 160, "w:are", 1.0)
           + text("CENTURY YEARS", 430, 84, family="hand", attrs='data-in="write" data-at="w:century"')
           + text("ONLY IF", 590, 90, attrs='data-in="pop" data-at="w:only"')
           + text("÷ 400", 870, 230, attrs='data-in="pop" data-at="w:divide"') + "</svg>")
# b3 "So 2000 had a leap day. 1900 didn't, and 2100 won't." — grid of three calendar pages
S["s3"] = (SVG + calendar("c2000", 60, 420, 300, 330, "2000", attrs='data-in="pop" data-at="w:2000"', head="#2f9e44")
           + calendar("c1900", 390, 420, 300, 330, "1900", attrs='data-in="pop" data-at="w:1900"')
           + calendar("c2100", 720, 420, 300, 330, "2100", attrs='data-in="pop" data-at="w:2100"')
           + mark("check", 210, 900, "w:leap", 1.3) + mark("cross", 540, 900, "w:didn't", 1.3) + mark("cross", 870, 900, "w:won't", 1.3)
           + text("FEB 29?", 215, 120, attrs='data-in="none"') + "</svg>")
# b4 "Why? The year of the seasons is about 365.24 days." — panel: the orbit
S["s4"] = (SVG + orbit(540, 660, 420, 230) + earth(960, 660, 60, attrs='data-in="pop" data-at="w:year"')
           + text("WHY?", 215, 130, attrs='data-in="pop" data-at="w:why"')
           + text("365.24 DAYS", 1005, 110, attrs='data-in="write" data-at="w:365.24"')
           + '<g data-lib="arrow" data-from="938,525" data-to="620,394" data-bend="0.2" data-in="draw" data-at="w:days"/>'
           + mark("sparkle", 150, 370, "w:seasons", 0.8) + "</svg>")
# b5 "A leap day every 4 years makes it 365.25, a bit too long." — text-led: the overshoot
S["s5"] = (SVG + text("365.25", 560, 230, attrs='data-in="pop" data-at="w:365.25"') + quarter_clock(540, 860, 170, attrs='data-in="pop" data-at="w:leap"')
           + text("TOO LONG", 215, 120, attrs='data-in="write" data-at="w:long"') + mark("sweat", 760, 760, "w:bit", 1.2)
           + mark("exclaim", 860, 900, "w:too", 1.1) + mark("sparkle", 300, 760, "w:makes", 0.7) + "</svg>")
# b6 "By the 1500s that had added up to 10 days, so in 1582 ten days were dropped." — hero calendar, days torn out
X6, W6 = 260, 640
x0, y0 = cell(X6, CY, W6, CH, 1, 0)
x1, y1 = cell(X6, CY, W6, CH, 3, 2)
S["s6"] = (SVG + calendar("oct", X6, CY, W6, CH, "OCT", "1582", attrs='data-in="none"', head="#3b82c4")
           + text("10 DAYS OFF", 215, 120, attrs='data-in="write" data-at="w:10"')
           + mark("clock", 135, 560, "w:1500s", 0.6)
           + f'<g data-in="pop" data-at="w:dropped"><rect x="{x0 - 45}" y="{y0 - 50}" width="{x1 - x0 + 90}" height="{y1 - y0 + 100}" '
             f'rx="16" fill="#ffd23f" fill-opacity="0.85"/></g>'
           + f'<path d="M{x0 - 20},{y0 - 25} L{x1 + 20},{y1 + 25}" fill="none" stroke="#e8452c" stroke-width="14" data-in="draw" data-at="w:dropped"/>'
           + mark("burst", 900, 1000, "w:1582", 0.9) + "</svg>")
# b7 "Skipping 3 century leap days every 400 years cancels the extra." — split: +3 vs −3
S["s7"] = (SVG + '<g id="plus" data-in="none"><circle cx="297" cy="720" r="242" fill="#e8452c"/></g>'
           + '<g id="minus" data-in="pop" data-at="w:skipping"><circle cx="783" cy="720" r="242" fill="#3b82c4"/></g>'
           + text("+3", 780, 170, x=297, fill="white", attrs='data-in="none"')
           + text("−3", 780, 170, x=783, fill="white", attrs='data-in="pop" data-at="w:3"')
           + text("PER 400 YEARS", 215, 104, attrs='data-in="write" data-at="w:400"')
           + mark("check", 540, 380, "w:cancels", 1.0) + "</svg>")
# b8 loop "So, every four years? Almost." — back to the February page
S["s8"] = (SVG + calendar("cal", CX, CY, CW, CH, "FEB", "", hl=(0, 4))
           + mark("question", 960, 470, "w:every", 0.85) + text("ALMOST.", 215, 140, attrs='data-in="pop" data-at="w:almost"')
           + mark("sparkle", *cell(CX, CY, CW, CH, 0, 4), "w:years", 0.7) + "</svg>")
for k, s in S.items():
    (v / "svg" / f"{k}.svg").write_text(s)
cams = {"s1": {"drift": "none"}, "s2": {"drift": "in"}, "s3": {"drift": "none"}, "s4": {"drift": "out"}, "s5": {"drift": "none"},
        "s6": {"drift": "in"}, "s7": {"drift": "none", "shake": ["w:cancels"]}, "s8": {"drift": "none"}}
trans = {"s2": "cut", "s3": "whip", "s4": "fade", "s5": "pop", "s6": "whip-up", "s7": "flash", "s8": "cut"}
scenes = [{"id": k, "beat_ids": [f"b{k[1:]}"], "visual": {"kind": "doodle", "svg_path": f"svg/{k}.svg"}, "camera": cams[k],
           **({"transition": {"type": trans[k]}} if k in trans else {})} for k in S]
(v / "storyboard.json").write_text(json.dumps({"video_id": "v01", "style": {"palette": ["#ffd23f", "#e8452c", "#3b82c4", "#2f9e44", "#f783ac"],
                                                                         "paper": "plain", "mood": "crisp, numeric, playful"}, "scenes": scenes}, indent=1))
print("wrote", len(S), "scenes")
