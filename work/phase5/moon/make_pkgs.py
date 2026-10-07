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
    "P2": SVG + moon("moon", 690, 1060, 290)
    + '<g data-in="none"><ellipse cx="190" cy="1220" rx="110" ry="64" fill="white"/><circle cx="208" cy="1220" r="40" fill="#3b82c4"/>'
    + '<circle cx="212" cy="1220" r="16" fill="#111"/></g>'
    + '<path d="M300,1190 L420,1150" fill="none" stroke="#e8452c" stroke-width="14" data-in="none"/>'
    + text("1.5% FARTHER", 600, 140) + "</svg>",
    "P3": SVG + '<g data-lib="brain" data-face="think" data-fill="p4" transform="translate(400 1010) scale(2.3)" data-in="none"/>'
    + moon("far", 850, 1330, 118) + text("FAR AWAY", 600, 160) + "</svg>",
}
for k, s in T.items():
    (d / "svg" / f"{k}.svg").write_text(s)
TAGS = ["#moon", "#space", "#illusion", "#science"]
C = [
    {"id": "P1", "strategy": "contrast", "title": "Your camera says the Moon never grew",
     "opening_promise": "Same settings, same width: the Moon never grew.",
     "thumbnail": {"concept": "one big moon with an equal-width ruler under it", "text": "SAME WIDTH", "svg": "svg/P1.svg", "depicts": ["f1"]},
     "description": "Photos taken with the same settings show the horizon Moon the same width as the high Moon. A leading explanation for the bigger look: your brain judges it farther away.",
     "hashtags": TAGS, "claim_ids": ["f1", "f5"], "rationale": "the measurement against what your eyes say"},
    {"id": "P2", "strategy": "myth_bust", "title": "The giant horizon Moon isn't bigger",
     "opening_promise": "The giant Moon is actually a bit farther away.",
     "thumbnail": {"concept": "an eye looking at a big low moon along a distance line", "text": "1.5% FARTHER", "svg": "svg/P2.svg", "depicts": ["f2"]},
     "description": "At the horizon the Moon is about 1.5 percent farther from you than overhead, so it is very slightly smaller in the sky. The bigger look is an illusion.",
     "hashtags": TAGS, "claim_ids": ["f2", "f3"], "rationale": "the misconception, with a backwards-sounding fact on the cover"},
    {"id": "P3", "strategy": "mechanism", "title": "Your brain sees the horizon Moon bigger",
     "opening_promise": "The camera says same size. Your brain disagrees.",
     "thumbnail": {"concept": "a thinking brain beside a moon low on the horizon", "text": "FAR AWAY", "svg": "svg/P3.svg", "depicts": ["f5"]},
     "description": "A leading explanation: the brain judges the horizon Moon to be farther away, so it sees it as larger. Scientists still do not agree on the exact cause.",
     "hashtags": TAGS, "claim_ids": ["f4", "f5"], "rationale": "the mechanism, with its uncertainty"},
]
(d / "package_candidates.json").write_text(json.dumps({"video_id": "v01", "language": "en", "candidates": C}, indent=1, ensure_ascii=False))
print("wrote", len(C), "packages")
