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
    "h1": SVG + water(1040) + flamingo("bird", 560, 1030, 0.78, face="dead") + text("ZERO MUSCLE", 215, 112)
    + '<g data-lib="sparkle" data-fill="p0" transform="translate(830 700) scale(1.2)" data-in="pop" data-at="0.25" data-loop="pulse"/>' + "</svg>",
    "h2": SVG + ground() + flamingo("bird", 560, 1040, 0.78, face="happy")
    + '<g data-lib="sparkle" data-fill="p0" transform="translate(250 520) scale(1.1)" data-in="pop" data-at="0.2" data-loop="pulse"/>'
    + text("EASIER THAN TWO", 215, 100) + "</svg>",
    "h3": SVG + ground() + flamingo("one", 300, 1040, 0.72) + flamingo("two", 790, 1040, 0.72, legs=2, flip=True, attrs='data-in="none"')
    + '<g data-lib="question" transform="translate(545 560) scale(1.0)" data-in="pop" data-at="0.25" data-loop="bob"/>'
    + text("1 LEG OR 2?", 215, 120) + "</svg>",
    "h4": SVG + water(1040) + flamingo("bird", 560, 1030, 0.8, sleep=True)
    + '<g data-lib="zz" transform="translate(330 450) scale(1.3)" data-in="pop" data-at="0.2" data-loop="float"/>'
    + text("FAST ASLEEP", 215, 120) + "</svg>",
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


C = [cand("h1", "Even a dead flamingo balances on one leg.", "ZERO MUSCLE", "surprising_claim",
          "flamingo on one leg in water with X eyes, check mark", "flamingo with X eyes", "check mark draws at 0.25 s",
          ["f2", "f6"], "cadaver test: the pose holds with no muscle (f2, f6)", "how can something dead balance?", "surprise",
          "an impossible-sounding image the video proves"),
     cand("h2", "One leg is the easy pose for flamingos.", "EASIER THAN TWO", "misconception_reversal",
          "relaxed flamingo on one leg on the ground, sparkle", "smiling flamingo on one leg", "sparkle pops at 0.2 s",
          ["f3", "f6"], "two legs could not be held stable (f3); one leg is passive (f6)", "contradicts 'hard balancing act'",
          "curiosity", "flips what everyone assumes"),
     cand("h3", "One leg or two: which tires a flamingo?", "1 LEG OR 2?", "forced_choice",
          "two flamingos side by side, one leg vs two legs, question mark between", "two flamingos", "question mark pops at 0.25 s",
          ["f2", "f3"], "the lab compared both poses (f2, f3)", "viewer picks before the answer", "curiosity",
          "a choice invites a guess"),
     cand("h4", "Why doesn't a sleeping flamingo fall over?", "FAST ASLEEP", "visual_mystery",
          "flamingo asleep on one leg in water, head on its back, zz floating", "sleeping flamingo", "zz pops at 0.2 s",
          ["f5", "f6"], "dozing birds sway less (f5) because the pose is passive (f6)", "sleep should mean falling", "intrigue",
          "a mystery in one picture"),
     cand("h5", "Try sleeping on one leg like a flamingo.", "COULD YOU?", "direct_challenge",
          "sleeping flamingo on one leg next to a nervous person shrugging", "flamingo asleep beside a person", "person pops at 0.2 s",
          ["f5", "f6"], "flamingos sway less asleep (f5); for them it is effortless (f6)", "you would fall, it does not", "playful",
          "puts the viewer in the bird's place")]
(h / "hooks.json").write_text(json.dumps({"video_id": "v01", "language": "en", "topic": "Why flamingos stand on one leg",
                                          "candidates": C}, indent=1, ensure_ascii=False))
print("wrote", len(C), "candidates")
