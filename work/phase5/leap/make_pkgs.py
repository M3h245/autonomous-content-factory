"""Package candidates (contract package_candidates) + 1080x1920 doodle thumbnails for the leap-year video."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lshapes import SVG, calendar, cell, text  # noqa: E402

run = Path(sys.argv[1])
d = run / "videos" / "v01" / "package"
(d / "svg").mkdir(parents=True, exist_ok=True)


def lib(kind, x, y, s=1.0):
    return f'<g data-lib="{kind}" transform="translate({x} {y}) scale({s})" data-in="none"/>'


# P1: one big February page, day 29 crossed out
X1, Y1, W1, H1 = 170, 780, 740, 720
p1 = SVG + calendar("cal", X1, Y1, W1, H1, "", "", hl=(0, 4)) + lib("cross", *cell(X1, Y1, W1, H1, 0, 4), 1.4) + text("NOT IN 1900", 590, 150) + "</svg>"
# P2: the 400 rule as one big badge
p2 = (SVG + '<g data-in="none"><circle cx="540" cy="1110" r="380" fill="#3b82c4"/></g>'
      + lib("check", 540, 1110, 3.2) + text("÷ 400", 590, 170) + "</svg>")
# P3: October 1582, a block of days struck out (wider page than P1)
X3, Y3, W3, H3 = 110, 760, 860, 640
x0, y0 = cell(X3, Y3, W3, H3, 1, 0)
x1, y1 = cell(X3, Y3, W3, H3, 4, 2)
p3 = (SVG + calendar("oct", X3, Y3, W3, H3, "", "", head="#3b82c4")
      + f'<g data-in="none"><rect x="{x0 - 50}" y="{y0 - 45}" width="{x1 - x0 + 100}" height="{y1 - y0 + 90}" rx="16" fill="#ffd23f"/></g>'
      + f'<path d="M{x0 - 20},{y0 - 20} L{x1 + 20},{y1 + 20}" fill="none" stroke="#e8452c" stroke-width="20" data-in="none"/>'
      + text("−10 DAYS", 590, 170) + "</svg>")
# P4: the overshoot as one big quarter-day clock
p4 = (SVG + '<g data-in="none"><circle cx="540" cy="1100" r="390" fill="#b9d6f2"/>'
      '<path d="M540,1100 L540,710 A390,390 0 0 1 930,1100 Z" fill="#ffd23f"/>'
      '<path d="M540,1100 L540,790 M540,1100 L760,1100" fill="none" stroke="#1d1b1a" stroke-width="16"/></g>'
      + text("365.25", 590, 170) + "</svg>")
for k, s in {"P1": p1, "P2": p2, "P3": p3, "P4": p4}.items():
    (d / "svg" / f"{k}.svg").write_text(s)
TAGS = ["#LeapYear", "#calendar", "#history", "#science"]
C = [
    {"id": "P1", "strategy": "myth_bust", "title": "Leap years aren't every four years",
     "opening_promise": "Leap years aren't every four years.",
     "thumbnail": {"concept": "a February page with day 29 crossed out", "text": "NOT IN 1900", "svg": "svg/P1.svg", "depicts": ["f6"]},
     "description": "A century year is a leap year only if it divides by 400: 2000 was, 1900 was not, and 2100 will not be. The rule keeps the calendar in step with the seasons.",
     "hashtags": TAGS, "claim_ids": ["f3", "f6"], "rationale": "flips the rule everyone learned, exactly as the video opens"},
    {"id": "P2", "strategy": "curiosity", "title": "Why 1900 had no leap day",
     "opening_promise": "1900 had no leap day, but 2000 did.",
     "thumbnail": {"concept": "one big badge with the divide-by-400 rule", "text": "÷ 400", "svg": "svg/P2.svg", "depicts": ["f6"]},
     "description": "Century years are leap years only if they divide by 400. That is why 2000 had a leap day, 1900 did not, and 2100 will not.",
     "hashtags": TAGS, "claim_ids": ["f6"], "rationale": "a concrete date that breaks the rule"},
    {"id": "P3", "strategy": "story", "title": "In 1582, ten days were dropped",
     "opening_promise": "Too many leap years: by 1582, ten days had to go.",
     "thumbnail": {"concept": "an October page with a block of days struck out", "text": "−10 DAYS", "svg": "svg/P3.svg", "depicts": ["f5"]},
     "description": "By the 1500s the old calendar had drifted about 10 days, so in 1582 Thursday 4 October was followed by Friday 15 October. The century rule stops it drifting again.",
     "hashtags": TAGS, "claim_ids": ["f4", "f5", "f6"], "rationale": "the strange historical moment behind the rule"},
    {"id": "P4", "strategy": "mechanism", "title": "Why century years skip leap day",
     "opening_promise": "A leap day every four years overshoots the seasons.",
     "thumbnail": {"concept": "one big quarter-day clock under the number 365.25", "text": "365.25", "svg": "svg/P4.svg", "depicts": ["f3"]},
     "description": "A leap day every 4 years makes the average year 365.25 days, a little longer than the seasons. Skipping three century leap days every 400 years fixes it.",
     "hashtags": TAGS, "claim_ids": ["f1", "f3", "f6", "f8"], "rationale": "explains the arithmetic behind the rule"},
]
(d / "package_candidates.json").write_text(json.dumps({"video_id": "v01", "language": "en", "candidates": C}, indent=1, ensure_ascii=False))
print("wrote", len(C), "packages")
