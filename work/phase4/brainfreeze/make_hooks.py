import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from bfshapes import SVG, glass, cone, head, pain, cube, text
run = Path(sys.argv[1]); d = run / "videos" / "v01" / "hook"; (d / "svg").mkdir(parents=True, exist_ok=True)
svgs = {
 "h1": SVG + glass("glass", 540, 1380, 800) + '<g data-lib="burst" data-r="80" data-n="9" data-fill="p0" transform="translate(830 560)" data-in="pop" data-at="0.2"/>'
       + text("1 IN 2", 260, 150) + "</svg>",
 "h2": SVG + head("head", 540, 950, 330, "wince") + pain(540, 680, "0.15", 1.2) + text("NOT FROZEN", 260, 130) + "</svg>",
 "h3": SVG + glass("glass", 300, 1350, 700, 340, True) + cone("cone", 790, 1350, 0.85)
       + '<g data-lib="question" transform="translate(545 760) scale(1.1)" data-in="pop" data-at="0.25"/>' + text("SIP OR GULP?", 260, 120) + "</svg>",
 "h4": SVG + head("head", 540, 1000, 320, "shock") + pain(540, 730, "0.2", 1.1) + text("MOUTH → FOREHEAD?", 260, 92) + "</svg>",
 "h5": SVG + cone("cone", 540, 1400, 1.25) + '<g data-lib="lines" transform="translate(240 900) scale(1.6)" data-in="draw" data-at="0.2"/>' + text("2x THE RISK", 260, 120) + "</svg>",
}
for k, v in svgs.items():
    (d / "svg" / f"{k}_frame0.svg").write_text(v)
C = lambda **k: k
cands = [
 C(hook_id="h1", spoken_text="Gulp ice water, and half of people get brain freeze.", visual_concept="Big glass of ice water with a straw; a burst at the rim.",
   on_screen_text="1 IN 2", curiosity_mechanism="surprising_statistic", tension="it's not a rare thing — it's a coin flip", target_emotion="surprise",
   first_frame_concept="huge glass of ice water with a red straw", first_frame_subject="glass of ice water", first_frame_text="1 IN 2",
   visual_action="burst pops at the straw at 0.2 s", payoff_connection="the 77-person ice-water experiment (f3)", why_it_should_work="a concrete number for a feeling everyone knows",
   first_frame_svg="svg/h1_frame0.svg", fact_ids=["f3"]),
 C(hook_id="h2", spoken_text="Brain freeze isn't your brain freezing.", visual_concept="Wincing face, blue pain zigzag over the forehead.",
   on_screen_text="NOT FROZEN", curiosity_mechanism="misconception_reversal", tension="the name lies", target_emotion="curiosity",
   first_frame_concept="big wincing face with a pain zigzag on the forehead", first_frame_subject="face", first_frame_text="NOT FROZEN",
   visual_action="pain zigzag draws across the forehead at 0.15 s", payoff_connection="the pain is referred from the palate (f1, f8)", why_it_should_work="flips the literal reading of the name",
   first_frame_svg="svg/h2_frame0.svg", fact_ids=["f1", "f8"]),
 C(hook_id="h3", spoken_text="Sip or gulp? One doubles your odds of brain freeze.", visual_concept="Ice water glass vs ice cream cone with a question mark between.",
   on_screen_text="SIP OR GULP?", curiosity_mechanism="forced_choice", tension="viewers pick a side before the answer", target_emotion="curiosity",
   first_frame_concept="glass and cone side by side, question mark between them", first_frame_subject="glass of ice water", first_frame_text="SIP OR GULP?",
   visual_action="question mark pops at 0.25 s", payoff_connection="gulping vs slow eating experiments (f3, f5)", why_it_should_work="a choice invites a guess, the video settles it",
   first_frame_svg="svg/h3_frame0.svg", fact_ids=["f3", "f5"]),
 C(hook_id="h4", spoken_text="Cold hits your mouth. So why does your forehead hurt?", visual_concept="Shocked face, pain zigzag on forehead.",
   on_screen_text="MOUTH → FOREHEAD?", curiosity_mechanism="body_puzzle", tension="the pain is in the wrong place", target_emotion="puzzlement",
   first_frame_concept="shocked face with forehead pain lines", first_frame_subject="face", first_frame_text="MOUTH → FOREHEAD?",
   visual_action="pain zigzag at 0.2 s", payoff_connection="referred pain from the palate (f1, f8)", why_it_should_work="names the odd geography of the pain",
   first_frame_svg="svg/h4_frame0.svg", fact_ids=["f1", "f8"]),
 C(hook_id="h5", spoken_text="Eat ice cream fast, and brain freeze doubles.", visual_concept="Big ice cream cone with speed lines.",
   on_screen_text="2x THE RISK", curiosity_mechanism="consequence", tension="something you do every summer doubles the odds", target_emotion="surprise",
   first_frame_concept="giant cone with speed lines", first_frame_subject="ice cream cone", first_frame_text="2x THE RISK",
   visual_action="speed lines draw at 0.2 s", payoff_connection="the 145-student randomised trial (f5)", why_it_should_work="a cause the viewer controls",
   first_frame_svg="svg/h5_frame0.svg", fact_ids=["f5"]),
]
(d / "hooks.json").write_text(json.dumps({"video_id": "v01", "language": "en", "topic": "Why ice cream gives you brain freeze", "candidates": cands}, indent=1))
print("ok")
