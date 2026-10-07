import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from bfshapes import SVG, glass, cone, head, pain, cube
run = Path(sys.argv[1]); d = run / "videos" / "v01" / "package"; (d / "svg").mkdir(parents=True, exist_ok=True)
def T(t, y=570, size=160):
    return f'<text x="540" y="{y}" font-family="marker" font-size="{size}" fill="#1d1b1a" data-in="none">{t}</text>'
svgs = {
 "P1": SVG + glass("glass", 540, 1490, 780, 520, straw_h=0)
       + '<g data-lib="burst" data-r="90" data-n="9" data-fill="p1" transform="translate(820 1240)" data-in="none"/>' + T("HALF GOT IT", 570, 150) + "</svg>",
 "P2": SVG + head("head", 540, 1110, 380, "wince") + pain(540, 830, "0", 1.7)
       + '<g data-lib="arrow" data-from="600,1300" data-to="700,900" data-bend="0.45" data-in="none"/>' + T("REFERRED", 570, 150) + "</svg>",
 "P3": SVG + cone("cone", 560, 1490, 0.95)
       + '<g data-lib="lines" transform="translate(200 1080) scale(2.0)" data-in="none"/>'
       + '<g data-lib="burst" data-r="95" data-n="9" data-fill="p1" transform="translate(880 1280)" data-in="none"/>' + T("27% vs 13%", 570, 160) + "</svg>",
 "P4": SVG + cube("cube", 540, 1090, 2.9).replace("#e7f5ff", "#a5d8ff") + '<g data-lib="sparkle" data-fill="#7cc6f2" transform="translate(860 800) scale(1.2)" data-in="none"/>'
       + T("ONLY 12%", 570, 170) + "</svg>",
}
for k, v in svgs.items():
    (d / "svg" / f"{k}.svg").write_text(v)
tags = ["#science", "#brainfreeze", "#icecream"]
c = {"video_id": "v01", "language": "en", "candidates": [
 {"id": "P1", "strategy": "question", "title": "Sip or gulp: which one doubles brain freeze?",
  "opening_promise": "Sip or gulp? Two experiments settle it.",
  "thumbnail": {"concept": "one huge glass of ice water with a straw; 'HALF GOT IT' teases the gulp result without naming the winner",
                "text": "HALF GOT IT", "svg": "svg/P1.svg", "depicts": ["f3"]},
  "description": "Gulping ice water gave half of 77 volunteers brain freeze; an ice cube on the palate, one in eight. A school trial found the same with fast ice cream.",
  "hashtags": tags, "claim_ids": ["f3", "f4", "f5"], "caption_cta": "Do you sip or gulp?",
  "rationale": "the video's own question; the thumbnail adds the evidence hint"},
 {"id": "P2", "strategy": "myth_bust", "title": "Brain freeze isn't your brain freezing",
  "opening_promise": "Brain freeze starts in your mouth, not your brain.",
  "thumbnail": {"concept": "big wincing face, pain zigzag on the forehead, arrow up from the mouth", "text": "REFERRED",
                "svg": "svg/P2.svg", "depicts": ["f1", "f8"]},
  "description": "Cold on the roof of your mouth sets it off, and the ache shows up in your forehead. It's referred pain, and it fades within 10 minutes.",
  "hashtags": tags, "claim_ids": ["f1", "f2", "f8"], "caption_cta": "Do you sip or gulp?",
  "rationale": "name-vs-reality reversal"},
 {"id": "P3", "strategy": "utility", "title": "Eating fast doubles your odds of brain freeze",
  "opening_promise": "One habit doubles your odds of brain freeze.",
  "thumbnail": {"concept": "giant cone with speed lines; the two trial numbers", "text": "27% vs 13%", "svg": "svg/P3.svg", "depicts": ["f5"]},
  "description": "In a randomised trial with 145 students, eating ice cream in under 5 seconds caused brain freeze in 27%, versus 13% for slow eaters.",
  "hashtags": tags, "claim_ids": ["f5"], "caption_cta": "Do you sip or gulp?",
  "rationale": "actionable takeaway with a number"},
 {"id": "P4", "strategy": "contrast", "title": "Ice water vs an ice cube: which triggers brain freeze?",
  "opening_promise": "Same cold, very different odds of brain freeze.",
  "thumbnail": {"concept": "one giant ice cube, 'ONLY 12%' (the cube result; the gulp result is the reveal)", "text": "ONLY 12%", "svg": "svg/P4.svg", "depicts": ["f3"]},
  "description": "In one experiment, gulped ice water triggered brain freeze in half of 77 people; an ice cube held on the palate in one in eight.",
  "hashtags": tags, "claim_ids": ["f3"], "caption_cta": "Do you sip or gulp?",
  "rationale": "two stimuli, two numbers"}]}
(d / "package_candidates.json").write_text(json.dumps(c, indent=1))
print("ok")
