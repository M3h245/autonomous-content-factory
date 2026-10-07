import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from shapes import SVG, joint, bubble, fist, pop
run = Path(sys.argv[1]); d = run / "videos" / "v01" / "package"; (d / "svg").mkdir(parents=True, exist_ok=True)
def T(t, y, size, fill="#1d1b1a"):
    return f'<text x="540" y="{y}" font-family="marker" font-size="{size}" fill="{fill}" data-in="none">{t}</text>'
svgs = {
 "P1": SVG + fist("fist", 560, 1495, 1.08) + pop(800, 900, "0.1", 1.7) + T("NOT BONES", 570, 170) + "</svg>",
 "P2": SVG + joint("joint", 540, 720, 1495, 1.5) + bubble(540, 1107, 95, "0.1") + T("GAS BUBBLE", 570, 160) + "</svg>",
 "P3": SVG + fist("fist", 450, 1495, 1.08) + '<g data-lib="question" transform="translate(860 1050) scale(1.7)" data-in="pop" data-at="0.1"/>'
       + T("215 PEOPLE", 570, 165) + "</svg>",
 "P4": SVG + fist("fist", 560, 1495, 1.08) + T("60 YEARS", 570, 170) + "</svg>",
}
for k, v in svgs.items():
    (d / "svg" / f"{k}.svg").write_text(v)
c = {"video_id": "v01", "language": "en", "candidates": [
 {"id": "P1", "strategy": "curiosity", "title": "What actually pops when you crack your knuckles?",
  "opening_promise": "That pop isn't your bones. Here's what an MRI saw.",
  "thumbnail": {"concept": "huge fist, burst at the knuckles, 'NOT BONES' rules out the obvious answer", "text": "NOT BONES",
                "svg": "svg/P1.svg", "depicts": ["f1"]},
  "description": "Scientists filmed a knuckle cracking inside an MRI: the joint pulls apart and a gas cavity forms in the fluid.",
  "hashtags": ["#science", "#humanbody", "#knucklecracking"], "claim_ids": ["f1", "f2"], "caption_cta": "Do you crack yours?"},
 {"id": "P2", "strategy": "mechanism", "title": "An MRI filmed a knuckle crack as it happened",
  "opening_promise": "What pops when a knuckle cracks? An MRI caught it happening.",
  "thumbnail": {"concept": "joint cross-section filling the frame, one big bubble in the gap", "text": "GAS BUBBLE",
                "svg": "svg/P2.svg", "depicts": ["f1", "f7"]},
  "description": "Inside an MRI, a cracking knuckle shows a gas cavity snapping open in the joint fluid. A 2018 model says the sound may still come from a partial collapse.",
  "hashtags": ["#science", "#mri", "#knucklecracking"], "claim_ids": ["f1", "f2", "f4"], "caption_cta": "Do you crack yours?"},
 {"id": "P3", "strategy": "question", "title": "Does cracking your knuckles cause arthritis?",
  "opening_promise": "Cracking your knuckles: what actually pops, and is it hurting your joints?",
  "thumbnail": {"concept": "fist with a big question mark; '215 PEOPLE' signals there is real evidence behind the answer", "text": "215 PEOPLE",
                "svg": "svg/P3.svg", "depicts": ["f5"]},
  "description": "What pops when you crack your knuckles, and what a study of 215 people found about arthritis.",
  "hashtags": ["#science", "#arthritis", "#knucklecracking"], "claim_ids": ["f1", "f5"], "caption_cta": "Do you crack yours?"},
 {"id": "P4", "strategy": "story", "title": "He cracked one hand for 60 years to test it",
  "opening_promise": "One doctor ran a 60-year experiment on his own knuckles.",
  "thumbnail": {"concept": "fist with '60 YEARS'", "text": "60 YEARS", "svg": "svg/P4.svg", "depicts": ["f6"]},
  "description": "A doctor cracked only his left hand for 60 years and compared both hands.",
  "hashtags": ["#science", "#ignobel", "#knucklecracking"], "claim_ids": ["f6"], "caption_cta": "Do you crack yours?"}]}
(d / "package_candidates.json").write_text(json.dumps(c, indent=1))
print("ok")
