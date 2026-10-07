"""Hook candidates (contract hook_candidates) + frame-0 SVGs for the Moon-illusion video."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mshapes import SVG, camera, hand_nail, moon, skyline, stars, text  # noqa: E402

run = Path(sys.argv[1])
h = run / "videos" / "v01" / "hook"
(h / "svg").mkdir(parents=True, exist_ok=True)
SV = {
    "h1": SVG + moon("moon", 540, 700, 345) + skyline() + text("NOT BIGGER", 215, 120)
    + stars([(150, 420, 0.7), (930, 360, 0.6)], "0.2") + "</svg>",
    "h2": SVG + moon("moon", 560, 710, 345) + skyline()
    + '<g data-lib="arrow" data-from="110,330" data-to="300,520" data-bend="0.25" data-in="draw" data-at="0.25"/>'
    + text("FARTHER AWAY", 215, 116) + "</svg>",
    "h3": SVG + moon("moon", 600, 690, 340) + skyline() + hand_nail(230, 420, 0.9, attrs='data-in="slide-up" data-at="0.25"')
    + text("DOES IT SHRINK?", 215, 96) + "</svg>",
    "h4": SVG + moon("big", 430, 710, 345) + moon("small", 870, 470, 95, attrs='data-in="pop" data-at="0.25"') + skyline()
    + text("SAME MOON?", 215, 124) + "</svg>",
    "h5": SVG + moon("moon", 600, 700, 345) + skyline() + camera(240, 560, 0.75, attrs='data-in="pop" data-at="0.2"')
    + text("CAMERA SAYS SAME", 215, 84) + "</svg>",
}
for k, s in SV.items():
    (h / "svg" / f"{k}_frame0.svg").write_text(s)


def cand(hid, spoken, on_screen, mech, concept, subject, action, facts, payoff, tension, emotion, why):
    return {"hook_id": hid, "spoken_text": spoken, "visual_concept": concept, "on_screen_text": on_screen, "curiosity_mechanism": mech,
            "tension": tension, "target_emotion": emotion, "first_frame_concept": concept, "first_frame_subject": subject,
            "first_frame_text": on_screen, "visual_action": action, "payoff_connection": payoff, "why_it_should_work": why,
            "first_frame_svg": f"svg/{hid}_frame0.svg", "fact_ids": facts}


C = [cand("h1", "That huge horizon Moon isn't actually bigger.", "NOT BIGGER", "misconception_reversal",
          "giant moon rising behind rooftops, stars", "giant moon", "stars pop at 0.2 s", ["f1", "f3"],
          "photos show the same width (f1); it is an illusion (f3)", "your eyes say otherwise", "surprise", "contradicts what everyone has seen"),
     cand("h2", "The rising Moon is actually a bit farther away.", "FARTHER AWAY", "surprising_claim",
          "giant moon over rooftops with a distance arrow from the street", "giant moon", "arrow draws at 0.25 s", ["f2"],
          "about 1.5 percent farther at the horizon (f2)", "bigger but farther?", "curiosity", "a fact that sounds backwards"),
     cand("h3", "Hold up a fingernail: does the giant Moon shrink?", "DOES IT SHRINK?", "direct_challenge",
          "giant moon over rooftops, an index finger rising beside it", "giant moon", "finger slides up at 0.25 s", ["f7"],
          "at arm's length a fingernail covers about the same amount of Moon, low or high (f7)", "a test the viewer can do",
          "playful", "invites the viewer to try"),
     cand("h4", "Same Moon, two sizes. Which one is real?", "SAME MOON?", "visual_mystery",
          "giant low moon beside a small high moon over rooftops", "two moons", "small moon pops at 0.25 s", ["f1", "f3"],
          "same width in photos (f1); the brain makes the difference (f3)", "two sizes of one thing", "intrigue", "a puzzle in one picture"),
     cand("h5", "Your camera says the Moon never grew.", "CAMERA SAYS SAME", "contradiction",
          "giant moon over rooftops with a camera pointing at it", "giant moon", "camera pops at 0.2 s", ["f1"],
          "photos show the same width (f1)", "camera vs eyes", "surprise", "pits a measurement against perception")]
(h / "hooks.json").write_text(json.dumps({"video_id": "v01", "language": "en", "topic": "Why the Moon looks bigger near the horizon",
                                          "candidates": C}, indent=1, ensure_ascii=False))
print("wrote", len(C), "candidates")
