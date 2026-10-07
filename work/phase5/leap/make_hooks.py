"""Hook candidates (contract hook_candidates) + frame-0 SVGs for the leap-year video."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lshapes import SVG, calendar, cell, text  # noqa: E402

run = Path(sys.argv[1])
h = run / "videos" / "v01" / "hook"
(h / "svg").mkdir(parents=True, exist_ok=True)
CX, CY, CW, CH = 190, 340, 700, 720          # one big calendar page, ~37 % of the frame height


def x29(at="0.25"):
    x, y = cell(CX, CY, CW, CH, 0, 4)
    return f'<g data-lib="cross" transform="translate({x} {y}) scale(1.1)" data-in="pop" data-at="{at}"/>'


def q29(at="0.25"):
    x, y = cell(CX, CY, CW, CH, 0, 4)
    return f'<g data-lib="question" transform="translate({x} {y}) scale(0.8)" data-in="pop" data-at="{at}" data-loop="bob"/>'


SV = {
    "h1": SVG + calendar("cal", CX, CY, CW, CH, "FEB", "1900", hl=(0, 4)) + x29() + text("NO FEB 29", 215, 124) + "</svg>",
    "h2": SVG + calendar("cal", CX, CY, CW, CH, "FEB", "", hl=(0, 4))
    + '<g data-lib="cross" transform="translate(900 300) scale(1.0)" data-in="pop" data-at="0.25"/>' + text("NOT EVERY 4", 215, 124) + "</svg>",
    "h3": SVG + calendar("cal", CX, CY, CW, CH, "FEB", "2000", hl=(0, 4)) + q29() + text("2000: LEAP?", 215, 124) + "</svg>",
    "h4": SVG + calendar("cal", CX, CY, CW, CH, "FEB", "1800", hl=(0, 4))
    + '<g data-lib="question" transform="translate(940 330) scale(1.0)" data-in="pop" data-at="0.25" data-loop="bob"/>'
    + text("CENTURY YEARS?", 215, 100) + "</svg>",
    "h5": SVG + calendar("cal", CX, CY, CW, CH, "FEB", "2100", hl=(0, 4)) + x29() + text("2100: NO LEAP DAY", 215, 90) + "</svg>",
}
for k, s in SV.items():
    (h / "svg" / f"{k}_frame0.svg").write_text(s)


def cand(hid, spoken, on_screen, mech, concept, subject, action, facts, payoff, tension, emotion, why):
    return {"hook_id": hid, "spoken_text": spoken, "visual_concept": concept, "on_screen_text": on_screen, "curiosity_mechanism": mech,
            "tension": tension, "target_emotion": emotion, "first_frame_concept": concept, "first_frame_subject": subject,
            "first_frame_text": on_screen, "visual_action": action, "payoff_connection": payoff, "why_it_should_work": why,
            "first_frame_svg": f"svg/{hid}_frame0.svg", "fact_ids": facts}


C = [cand("h1", "The year 1900 had no leap day.", "NO FEB 29", "surprising_claim", "February 1900 calendar page, day 29 crossed out",
          "calendar page", "cross pops on day 29 at 0.25 s", ["f6"], "the divide-by-400 rule (f6)", "everyone thinks every 4th year", "surprise",
          "a concrete date that breaks the rule people know"),
     cand("h2", "Leap years aren't every four years.", "NOT EVERY 4", "misconception_reversal", "blank February calendar page with a cross beside it",
          "calendar page", "cross pops at 0.25 s", ["f3", "f6"], "Julian every-4 vs Gregorian rule (f3, f6)", "contradicts school knowledge",
          "curiosity", "flips a rule everyone learned"),
     cand("h3", "Quick: was 2000 a leap year?", "2000: LEAP?", "quiz", "February 2000 calendar page, question mark on day 29",
          "calendar page", "question mark pops at 0.25 s", ["f6"], "2000 divides by 400 (f6)", "viewer answers before the reveal", "playful",
          "a quiz invites a guess"),
     cand("h4", "Why do century years skip leap day?", "CENTURY YEARS?", "question", "February 1800 calendar page with a question mark",
          "calendar page", "question mark pops at 0.25 s", ["f6", "f8"], "dropping 3 leap days per 400 years (f6, f8)", "a rule without a reason",
          "curiosity", "asks the exact question the video answers"),
     cand("h5", "Every four years? Not in 2100.", "2100: NO LEAP DAY", "prediction", "February 2100 calendar page, day 29 crossed out",
          "calendar page", "cross pops on day 29 at 0.25 s", ["f6"], "2100 will not be a leap year (f6)", "a future surprise", "surprise",
          "a near-future date makes the rule personal")]
(h / "hooks.json").write_text(json.dumps({"video_id": "v01", "language": "en", "topic": "Why leap years skip some century years",
                                          "candidates": C}, indent=1, ensure_ascii=False))
print("wrote", len(C), "candidates")
