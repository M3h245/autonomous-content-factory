"""Hook candidates (contract hook_candidates) + frame-0 SVGs for the flamingo video."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fshapes import SVG, flamingo, ground, text, water  # noqa: E402

run = Path(sys.argv[1])
h = run / "videos" / "v01" / "hook"
(h / "svg").mkdir(parents=True, exist_ok=True)
SV = {
    "h1": SVG + ground() + flamingo("bird", 560, 1040, 0.78, face="dead")
    + '<g data-lib="question" transform="translate(860 560) scale(1.1)" data-in="pop" data-at="0.25" data-loop="bob"/>'
    + text("DEAD, ON ONE LEG?", 215, 100) + "</svg>",
    "h2": SVG + ground() + flamingo("bird", 560, 1040, 0.78, face="happy")
    + '<g data-lib="cross" transform="translate(860 560) scale(1.1)" data-in="pop" data-at="0.25"/>'
    + text("NOT A BALANCING ACT", 215, 88) + "</svg>",
    "h3": SVG + water(1040) + flamingo("bird", 560, 1030, 0.8, sleep=True)
    + '<g data-lib="question" transform="translate(860 520) scale(1.1)" data-in="pop" data-at="0.2" data-loop="bob"/>'
    + text("SLEEPING, NOT FALLING", 215, 84) + "</svg>",
    "h4": SVG + water(1040) + flamingo("bird", 560, 1030, 0.8)
    + '<g data-lib="question" transform="translate(860 520) scale(1.1)" data-in="pop" data-at="0.2" data-loop="bob"/>'
    + text("WHY ONE LEG?", 215, 120) + "</svg>",
    "h5": SVG + ground() + flamingo("bird", 380, 1040, 0.76, sleep=True)
    + '<g data-lib="dude" data-pose="shrug" data-face="nervous" transform="translate(820 1040) scale(1.25)" data-in="pop" data-at="0.2"/>'
    + text("COULD YOU?", 215, 120) + "</svg>",
}
for k, s in SV.items():
    (h / "svg" / f"{k}_frame0.svg").write_text(s)


def cand(hid, spoken, on_screen, mech, concept, subject, action, facts, payoff, tension, emotion, why):
    return {"hook_id": hid, "spoken_text": spoken, "visual_concept": concept, "on_screen_text": on_screen, "curiosity_mechanism": mech,
            "tension": tension, "target_emotion": emotion, "first_frame_concept": concept, "first_frame_subject": subject,
            "first_frame_text": on_screen, "visual_action": action, "payoff_connection": payoff, "why_it_should_work": why,
            "first_frame_svg": f"svg/{hid}_frame0.svg", "fact_ids": facts}


C = [cand("h1", "How does a dead flamingo stay on one leg?", "DEAD, ON ONE LEG?", "surprising_claim",
          "flamingo with X eyes standing on one leg on the ground, question mark", "flamingo with X eyes", "question mark pops at 0.25 s",
          ["f2", "f6"], "the 2017 cadaver test: held upright, it settled on one leg with no muscle (f2, f6)",
          "a dead bird should not hold a pose", "surprise", "an impossible-sounding fact the next 10 s prove"),
     cand("h2", "One leg isn't a balancing act for flamingos.", "NOT A BALANCING ACT", "misconception_reversal",
          "relaxed flamingo on one leg, a cross beside it", "smiling flamingo on one leg", "cross pops at 0.25 s",
          ["f6"], "the pose is held by the body's mechanics (f6)", "contradicts 'hard balancing act'", "curiosity",
          "flips what everyone assumes"),
     cand("h3", "Why doesn't a sleeping flamingo fall over?", "SLEEPING, NOT FALLING", "visual_mystery",
          "flamingo asleep on one leg in water, head on its back, question mark", "sleeping flamingo", "question mark pops at 0.2 s",
          ["f5", "f6"], "dozing birds sway less (f5) because the pose is passive (f6)", "sleep should mean falling", "intrigue",
          "a mystery in one picture"),
     cand("h4", "Why do flamingos rest on one leg?", "WHY ONE LEG?", "question",
          "flamingo on one leg in water, question mark", "flamingo on one leg", "question mark pops at 0.2 s",
          ["f2", "f6", "f7"], "cadaver test (f2, f6) and the water/heat study (f7)", "everyone has wondered", "curiosity",
          "asks exactly what the video answers"),
     cand("h5", "Try sleeping on one leg like a flamingo.", "COULD YOU?", "direct_challenge",
          "sleeping flamingo on one leg next to a nervous person shrugging", "flamingo asleep beside a person", "person pops at 0.2 s",
          ["f5", "f6"], "flamingos sway less asleep (f5); for them it takes little effort (f6)", "you would fall, it does not", "playful",
          "puts the viewer in the bird's place")]
(h / "hooks.json").write_text(json.dumps({"video_id": "v01", "language": "en", "topic": "Why flamingos stand on one leg",
                                          "candidates": C}, indent=1, ensure_ascii=False))
print("wrote", len(C), "candidates")
