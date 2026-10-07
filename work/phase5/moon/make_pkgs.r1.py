"""Package candidates (contract package_candidates) + 1080x1920 doodle thumbnails for the Moon-illusion video."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mshapes import SVG, hand_nail, moon, text  # noqa: E402

run = Path(sys.argv[1])
d = run / "videos" / "v01" / "package"
(d / "svg").mkdir(parents=True, exist_ok=True)
T = {
    "P1": SVG + moon("moon", 540, 1060, 300)
    + '<g data-in="none"><path d="M200,1420 L880,1420 M200,1385 L200,1455 M880,1385 L880,1455" fill="none" stroke="#e8452c" stroke-width="14"/></g>'
    + text("SAME WIDTH", 600, 150) + "</svg>",
    "P3": SVG + moon("moon", 690, 1060, 290)
    + '<g data-in="none"><ellipse cx="190" cy="1220" rx="110" ry="64" fill="white"/><circle cx="208" cy="1220" r="40" fill="#3b82c4"/>'
    + '<circle cx="212" cy="1220" r="16" fill="#111"/></g>'
    + '<path d="M300,1190 L420,1150" fill="none" stroke="#e8452c" stroke-width="14" data-in="none"/>'
    + text("1.5% FARTHER", 600, 140) + "</svg>",
    "P4": SVG + moon("moon", 650, 1060, 290) + hand_nail(220, 860, 1.0, attrs='data-in="none"') + text("LOW OR HIGH", 600, 150) + "</svg>",
    "P5": SVG + '<g data-lib="brain" data-face="think" data-fill="p4" transform="translate(540 1040) scale(2.5)" data-in="none"/>'
    + moon("far", 900, 1400, 70) + text("FAR AWAY", 600, 160) + "</svg>",
}
for k, s in T.items():
    (d / "svg" / f"{k}.svg").write_text(s)
TAGS = ["#moon", "#space", "#illusion", "#science"]
CTA = "Save this for the next big Moon."
C = [
    {"id": "P1", "strategy": "myth_bust", "title": "Why the horizon Moon seems bigger",
     "opening_promise": "The giant Moon isn't really giant.",
     "thumbnail": {"concept": "one big moon with an equal-width ruler under it", "text": "SAME WIDTH", "svg": "svg/P1.svg", "depicts": ["f1"]},
     "description": "Same-setting photos show the horizon Moon the same width as the high Moon, and it is about 1.5 percent farther away. The extra size comes from your brain.",
     "hashtags": TAGS, "claim_ids": ["f1", "f2", "f3"], "caption_cta": CTA, "rationale": "the misconception, settled by a measurement"},
    {"id": "P3", "strategy": "curiosity", "title": "The rising Moon is actually farther away",
     "opening_promise": "The giant Moon is actually a bit farther away.",
     "thumbnail": {"concept": "an eye looking at a big low moon along a distance line", "text": "1.5% FARTHER", "svg": "svg/P3.svg", "depicts": ["f2"]},
     "description": "At the horizon the Moon is about 1.5 percent farther from you than overhead, yet it looks bigger. A leading explanation: your brain judges it farther away and scales it up.",
     "hashtags": TAGS, "claim_ids": ["f2", "f5"], "rationale": "a backwards-sounding fact"},
    {"id": "P4", "strategy": "question", "title": "Can your fingernail cover the giant Moon?",
     "opening_promise": "Can your fingernail cover the giant Moon?",
     "thumbnail": {"concept": "an index finger beside a big moon", "text": "LOW OR HIGH", "svg": "svg/P4.svg", "depicts": ["f7"]},
     "description": "Hold a fingernail at arm's length: it covers the same amount of Moon low or high. A rolled-up paper tube makes the giant horizon Moon shrink.",
     "hashtags": TAGS, "claim_ids": ["f7", "f8"], "caption_cta": CTA, "rationale": "the video's own challenge"},
    {"id": "P5", "strategy": "mechanism", "title": "Your brain sees the horizon Moon bigger",
     "opening_promise": "Your fingernail says the giant Moon never grew.",
     "thumbnail": {"concept": "a thinking brain with a small far-away moon", "text": "FAR AWAY", "svg": "svg/P5.svg", "depicts": ["f5"]},
     "description": "The leading idea is apparent distance: your brain judges the horizon Moon farther away, so it sees it bigger. Scientists still argue about the exact cause.",
     "hashtags": TAGS, "claim_ids": ["f4", "f5"], "rationale": "the mechanism, with its uncertainty"},
]
(d / "package_candidates.json").write_text(json.dumps({"video_id": "v01", "language": "en", "candidates": C}, indent=1, ensure_ascii=False))
print("wrote", len(C), "packages")
