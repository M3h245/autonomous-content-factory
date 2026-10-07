"""Package candidates (contract package_candidates) + 1080x1920 doodle thumbnails for the flamingo video."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fshapes import SVG, flamingo, text, water  # noqa: E402

run = Path(sys.argv[1])
d = run / "videos" / "v01" / "package"
(d / "svg").mkdir(parents=True, exist_ok=True)


def reeds(x, base=1480, n=3, h=330):
    return "".join(f'<path d="M{x + k * 34},{base} q{-20 + k * 20},{-h / 2} {-10 + k * 14},{-h + k * 30}" fill="none" stroke="#2f9e44" '
                   f'stroke-width="12" data-in="none"/>' for k in range(n))


def dumbbell_crossed(cx, cy):
    return (f'<g data-in="none"><rect x="{cx - 110}" y="{cy - 14}" width="220" height="28" fill="#5b6475"/>'
            f'<rect x="{cx - 150}" y="{cy - 60}" width="44" height="120" rx="10" fill="#5b6475"/>'
            f'<rect x="{cx + 106}" y="{cy - 60}" width="44" height="120" rx="10" fill="#5b6475"/></g>'
            f'<g data-lib="cross" transform="translate({cx} {cy}) scale(1.3)" data-in="none"/>')


def padlock(cx, cy, s=1.4):
    return (f'<g data-in="none"><path d="M{cx - 34 * s},{cy} L{cx - 34 * s},{cy - 40 * s} C{cx - 34 * s},{cy - 92 * s} '
            f'{cx + 34 * s},{cy - 92 * s} {cx + 34 * s},{cy - 40 * s} L{cx + 34 * s},{cy}" fill="none" stroke="#555" stroke-width="{12 * s}"/>'
            f'<rect x="{cx - 56 * s}" y="{cy - 6 * s}" width="{112 * s}" height="{92 * s}" rx="{14 * s}" fill="#ffd23f"/>'
            f'<circle cx="{cx}" cy="{cy + 34 * s}" r="{11 * s}" fill="#5b4636"/></g>')


def thermo(cx, top):
    return (f'<g data-in="none"><rect x="{cx - 40}" y="{top}" width="80" height="380" rx="40" fill="white"/>'
            f'<circle cx="{cx}" cy="{top + 420}" r="74" fill="#3b82c4"/><rect x="{cx - 18}" y="{top + 270}" width="36" height="150" fill="#3b82c4"/></g>')


T = {
    "P1": SVG + water(1478, 40, 1040) + reeds(900) + flamingo("bird", 600, 1470, 0.8) + thermo(190, 820)
    + '<g data-lib="sparkle" data-fill="#7cc6f2" transform="translate(930 760) scale(1.1)" data-in="none"/>' + text("IN WATER", 590, 160) + "</svg>",
    "P2": SVG + water(1478, 40, 1040) + reeds(70) + reeds(900) + flamingo("bird", 560, 1470, 0.8, face="dead") + padlock(565, 1290)
    + text("NO MUSCLE", 590, 150) + "</svg>",
    "P3": SVG + water(1478, 40, 1040) + flamingo("bird", 640, 1470, 0.84, sleep=True)
    + '<g data-in="none"><rect x="96" y="860" width="250" height="170" rx="16" fill="#c99a62"/>'
    + '<rect x="150" y="1030" width="26" height="440" fill="#8a6a43"/><rect x="266" y="1030" width="26" height="440" fill="#8a6a43"/></g>'
    + text("ZOO ATLANTA", 590, 140) + "</svg>",
    "P4": SVG + '<rect x="250" y="1430" width="600" height="60" rx="14" fill="#9aa5b1" data-in="none"/>'
    + flamingo("bird", 550, 1430, 0.78) + '<path d="M180,1080 q-60,90 0,180" fill="none" stroke="#3b82c4" stroke-width="14" data-in="none"/>'
    + '<path d="M900,1080 q60,90 0,180" fill="none" stroke="#3b82c4" stroke-width="14" data-in="none"/>'
    + text("SWAYED LESS", 590, 140) + "</svg>",
}
for k, s in T.items():
    (d / "svg" / f"{k}.svg").write_text(s)
TAGS = ["#flamingo", "#animals", "#science", "#biology"]
C = [
    {"id": "P1", "strategy": "curiosity", "title": "One leg saves a flamingo muscle, and maybe heat",
     "opening_promise": "One leg or two: which one saves a flamingo effort?",
     "thumbnail": {"concept": "flamingo on one leg in water beside a cold thermometer", "text": "IN WATER", "svg": "svg/P1.svg", "depicts": ["f7", "f8"]},
     "description": "Scientists propped up a dead flamingo in 2017: on one leg it locked in place with no muscle. They also do it more in water and as it gets colder, which may save heat.",
     "hashtags": TAGS, "claim_ids": ["f2", "f6", "f7", "f8"], "rationale": "both supported reasons in one line"},
    {"id": "P2", "strategy": "myth_bust", "title": "A dead flamingo propped up stayed on one leg",
     "opening_promise": "A dead flamingo showed which pose takes muscle.",
     "thumbnail": {"concept": "X-eyed flamingo on one leg with a padlock on the ankle", "text": "NO MUSCLE", "svg": "svg/P2.svg", "depicts": ["f2", "f6"]},
     "description": "In a 2017 study, a flamingo body held upright settled onto one leg with no muscle activity, but would not stay steady on two legs.",
     "hashtags": TAGS, "claim_ids": ["f2", "f3", "f6"], "rationale": "the most surprising measured fact"},
    {"id": "P3", "strategy": "story", "title": "Live flamingos swayed less when they dozed off",
     "opening_promise": "Sleeping flamingos sway less, not more.",
     "thumbnail": {"concept": "flamingo asleep on one leg in water beside a zoo sign board", "text": "ZOO ATLANTA", "svg": "svg/P3.svg", "depicts": ["f5"]},
     "description": "At Zoo Atlanta, flamingos standing on one leg swayed less when they dozed off, a sign the pose takes very little muscular effort.",
     "hashtags": TAGS, "claim_ids": ["f4", "f5", "f6"], "rationale": "the zoo measurement as a small story"},
    {"id": "P4", "strategy": "mechanism", "title": "How a flamingo rests on one leg with little muscle",
     "opening_promise": "On one leg, a flamingo's body holds itself up.",
     "thumbnail": {"concept": "flamingo on a force plate with sway arcs either side", "text": "SWAYED LESS", "svg": "svg/P4.svg", "depicts": ["f4", "f5"]},
     "description": "A 2017 study found the one-legged pose needs very little muscle: a dead flamingo locked onto one leg, and dozing birds swayed less.",
     "hashtags": TAGS, "claim_ids": ["f2", "f5", "f6"], "rationale": "how it works, for viewers who want the mechanism"},
]
(d / "package_candidates.json").write_text(json.dumps({"video_id": "v01", "language": "en", "candidates": C}, indent=1, ensure_ascii=False))
print("wrote", len(C), "packages")
