import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from bfshapes import SVG, glass, cone, head, pain, cube, text
run = Path(sys.argv[1]); v = run / "videos" / "v01" / "visual"; (v / "svg").mkdir(parents=True, exist_ok=True)
def dots(n, filled, cx0, cy, gap=110, r=38, at="w:half", cols=None, color="#3b82c4", pre="d"):
    cols = cols or n
    o = ""
    for k in range(n):
        x = cx0 + (k % cols) * gap; y = cy + (k // cols) * gap
        o += f'<circle cx="{x}" cy="{y}" r="{r}" fill="#ffffff" data-in="pop" data-at="{0.1 + 0.03 * k:.2f}"/>'
    for k in range(filled):
        x = cx0 + (k % cols) * gap; y = cy + (k // cols) * gap
        o += f'<circle cx="{x}" cy="{y}" r="{r - 6}" fill="{color}" stroke="none" data-in="pop" data-at="{at}"/>'
    return o
S = {}
S["s1"] = (SVG + glass("glass", 300, 1040, 620, 320, straw_h=60) + cone("cone", 790, 1040, 0.78)
           + '<g data-lib="question" transform="translate(545 640) scale(1.0)" data-in="pop" data-at="0.25" data-loop="bob"/>'
           + text("SIP OR GULP?", 230, 120) + '<g data-lib="burst" data-r="70" data-n="9" data-fill="p1" transform="translate(545 900)" data-in="pop" data-at="w:doubles"/>'
           + text("2x", 925, 90, x=545, attrs='data-in="pop" data-at="w:doubles"') + "</svg>")
S["s2"] = (SVG + head("head", 540, 700, 300, "shock")
           + '<g data-lib="arrow" data-from="930,1040" data-to="600,880" data-bend="-0.3" data-in="draw" data-at="w:cold"/>'
           + '<g data-lib="sparkle" data-fill="#7cc6f2" transform="translate(950 1010) scale(0.8)" data-in="pop" data-at="w:cold"/>'
           + text("ROOF OF YOUR MOUTH", 230, 76, attrs='data-in="write" data-at="w:roof"') + "</svg>")
S["s3"] = (SVG + head("head", 540, 720, 290, "wince") + pain(540, 500, "w:forehead", 1.3)
           + '<g data-lib="arrow" data-from="610,860" data-to="660,520" data-bend="0.4" data-in="draw" data-at="w:referred"/>'
           + text("REFERRED PAIN", 230, 110, attrs='data-in="write" data-at="w:referred"')
           + '<g id="frozenbrain" data-in="pop" data-at="w:frozen"><g data-lib="brain" transform="translate(880 990) scale(0.75)"/>'
           + '<g data-lib="cross" transform="translate(880 975) scale(0.5)" data-inside="frozenbrain"/></g>' + "</svg>")
S["s4"] = (SVG + '<g id="board" data-in="none"><rect x="90" y="520" width="900" height="420" rx="40" fill="#e7f5ff"/></g>'
           + dots(10, 5, 220, 660, 160, 52, "w:half", cols=5)
           + text("77 PEOPLE GULPED", 230, 96, attrs='data-in="write" data-at="w:77"')
           + text("HALF", 420, 100, x=330, attrs='data-in="pop" data-at="w:half"')
           + '<g data-lib="clock" transform="translate(800 400) scale(0.55)" data-in="pop" data-at="w:15"/>'
           + text("~15 s", 425, 80, x=610, attrs='data-in="write" data-at="w:seconds"') + "</svg>")
S["s5"] = (SVG + cube("cube", 540, 650, 2.4) + dots(8, 1, 155, 1000, 110, 36, "w:one", color="#e8452c")
           + text("1 IN 8", 230, 140, attrs='data-in="write" data-at="w:eight"')
           + '<g data-lib="sparkle" data-fill="#7cc6f2" transform="translate(900 420)" data-in="pop" data-at="w:palate"/>' + "</svg>")
S["s6"] = (SVG + cone("fast", 290, 700, 0.5) + cone("slow", 790, 700, 0.5)
           + '<g data-lib="lines" transform="translate(120 520) scale(1.1)" data-in="draw" data-at="w:fast"/>'
           + '<rect x="200" y="810" width="180" height="230" fill="#e8452c" data-in="grow-up" data-at="w:27"/>'
           + '<rect x="700" y="930" width="180" height="110" fill="#3b82c4" data-in="grow-up" data-at="w:13"/>'
           + text("27%", 765, 84, x=290, attrs='data-in="pop" data-at="w:27"') + text("13%", 885, 84, x=790, attrs='data-in="pop" data-at="w:13"')
           + text("FAST vs SLOW", 230, 110, attrs='data-in="write" data-at="w:school"') + "</svg>")
S["s7"] = (SVG + cone("cone", 540, 1040, 0.85)
           + '<g data-lib="check" transform="translate(860 520) scale(1.3)" data-in="draw" data-at="w:slow"/>'
           + text("SLOW DOWN", 230, 130, attrs='data-in="write" data-at="w:slow"')
           + '<g data-lib="sparkle" data-fill="p0" transform="translate(220 560) scale(0.9)" data-in="pop" data-at="w:speed"/>' + "</svg>")
S["s8"] = (SVG + glass("glass", 300, 1040, 600, 360, straw=False) + cone("cone", 800, 1040, 0.62)
           + '<g data-lib="clock" transform="translate(545 560) scale(0.75)" data-in="pop" data-at="w:fades"/>'
           + text("GONE IN 10 MIN", 380, 80, attrs='data-in="write" data-at="w:minutes"')
           + text("DO YOU SIP OR GULP?", 230, 84, attrs='data-in="write" data-at="w:sip"') + "</svg>")
for k, s in S.items():
    (v / "svg" / f"{k}.svg").write_text(s)
cams = {"s1": {"drift": "none"}, "s2": {"drift": "none"}, "s3": {"drift": "none", "punch": [{"at": "w:referred", "zoom": 1.05}]},
        "s4": {"drift": "in"}, "s5": {"drift": "none", "punch": [{"at": "w:eight", "zoom": 1.05}]}, "s6": {"drift": "out"},
        "s7": {"drift": "in"}, "s8": {"drift": "none"}}
trans = {"s2": "whip", "s3": "cut", "s4": "paper", "s5": "whip-up", "s6": "pop", "s7": "paper", "s8": "cut"}
scenes = []
for i, k in enumerate(S):
    sc = {"id": k, "beat_ids": [f"b{i + 1}"], "visual": {"kind": "doodle", "svg_path": f"svg/{k}.svg"}, "camera": cams[k]}
    if k in trans:
        sc["transition"] = {"type": trans[k]}
    scenes.append(sc)
(v / "storyboard.json").write_text(json.dumps({"video_id": "v01", "style": {"palette": ["#ffd23f", "#e8452c", "#3b82c4", "#2f9e44", "#f783ac"],
                                                                           "paper": "plain", "mood": "cool, playful"}, "scenes": scenes}, indent=1))
print("ok")
