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


def stand_left(x, top, reach, base=1480):
    return (f'<g data-in="none"><rect x="{x - 14}" y="{top}" width="28" height="{base - top}" fill="#9aa5b1"/>'
            f'<rect x="{x - 90}" y="{base - 22}" width="180" height="22" rx="8" fill="#6b7785"/>'
            f'<rect x="{x - reach}" y="{top + 30}" width="{reach}" height="22" fill="#9aa5b1"/>'
            f'<path d="M{x - reach},{top + 52} l0,46" fill="none" stroke="#6b7785" stroke-width="14"/></g>')


def ground(y=1482):
    return f'<path d="M80,{y} C400,{y - 8} 700,{y + 6} 1000,{y - 3}" fill="none" stroke="#5b4636" stroke-width="9" data-in="none"/>'


T = {
    "P1": SVG + '<rect x="130" y="1400" width="820" height="70" rx="16" fill="#9aa5b1" data-in="none"/>'
    + flamingo("bird", 540, 1400, 0.96, sleep=True)
    + '<path d="M180,880 q-80,130 0,260" fill="none" stroke="#3b82c4" stroke-width="22" data-in="none"/>'
    + '<path d="M900,880 q80,130 0,260" fill="none" stroke="#3b82c4" stroke-width="22" data-in="none"/>' + text("SWAYED LESS", 590, 140) + "</svg>",
    "P2": SVG + '<rect x="110" y="1410" width="860" height="80" rx="14" fill="#c99a62" data-in="none"/>'
    + flamingo("bird", 560, 1410, 0.78, face="dead")
    + '<g data-lib="check" transform="translate(210 1040) scale(2.2)" data-in="none"/>'
    + '<g data-lib="exclaim" transform="translate(900 1040) scale(1.5)" data-in="none"/>' + text("NO MUSCLE", 565, 150) + "</svg>",
    "P3": SVG + water(1478, 40, 1040) + reeds(900) + flamingo("bird", 600, 1470, 0.8) + thermo(190, 820)
    + text("2010 STUDY", 590, 150) + "</svg>",
}
for k, s in T.items():
    (d / "svg" / f"{k}.svg").write_text(s)
TAGS = ["#flamingo", "#animals", "#science", "#biology"]
C = [
    {"id": "P1", "strategy": "question", "title": "Why flamingos rest on one leg",
     "opening_promise": "Two clues to why flamingos rest on one leg.",
     "thumbnail": {"concept": "flamingo asleep on one leg on a force plate, sway marks either side", "text": "SWAYED LESS", "svg": "svg/P1.svg", "depicts": ["f5"]},
     "description": "In 2017, a dead flamingo propped on one leg held steady with no muscle working. A 2010 zoo study found more birds did it in water and in the cold, which may save heat.",
     "hashtags": TAGS, "claim_ids": ["f2", "f5", "f6", "f7", "f8"], "rationale": "the viewer's own question, answered by two studies"},
    {"id": "P2", "strategy": "myth_bust", "title": "A dead flamingo held steady on one leg",
     "opening_promise": "Why rest on one leg? A dead flamingo showed it.",
     "thumbnail": {"concept": "X-eyed flamingo on one leg on a lab bench, a check mark beside it", "text": "NO MUSCLE", "svg": "svg/P2.svg", "depicts": ["f2"]},
     "description": "In a 2017 study, a dead flamingo held upright settled into a stable one-legged pose with no muscle activity, but would not stay steady on two legs.",
     "hashtags": TAGS, "claim_ids": ["f2", "f3", "f6"], "rationale": "the most surprising measured fact"},
    {"id": "P3", "strategy": "utility", "title": "One leg in cold water may save heat",
     "opening_promise": "Resting on one leg may also keep a flamingo warm.",
     "thumbnail": {"concept": "flamingo on one leg in water beside a cold thermometer", "text": "2010 STUDY", "svg": "svg/P3.svg", "depicts": ["f7", "f8"]},
     "description": "A 2010 zoo study found more flamingos rested on one leg in water than on land, and fewer as it got warmer, which suggests the pose helps keep heat.",
     "hashtags": TAGS, "claim_ids": ["f7", "f8"], "rationale": "the second, hedged reason as its own angle"},
]
(d / "package_candidates.json").write_text(json.dumps({"video_id": "v01", "language": "en", "candidates": C}, indent=1, ensure_ascii=False))
print("wrote", len(C), "packages")
