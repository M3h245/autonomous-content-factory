"""Authoring aid (not a gate): preview a storyboard's doodle scenes with the real narration timing and print what the
engine measures — layout class, main subject signature and height, empty cells, actors, cue problems, event gaps,
frame-0 stats — so a VISUAL_PLAN draft is checked before it spends one of the stage's three gate attempts.

  python work/phase5/scenecheck.py RUN OUT_DIR
"""
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1].parent
for s in ("video-production", "visual-storyboarding"):
    sys.path.insert(0, str(REPO / "skills" / s / "scripts"))
import doodle_engine as de  # noqa: E402
import storyboard_tool as SB  # noqa: E402
from PIL import Image  # noqa: E402

run, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
v = run / "videos" / "v01"
sb = json.loads((v / "visual" / "storyboard.json").read_text())
timing = json.loads((v / "audio" / "timing.json").read_text())
style = sb["style"]
rows, ims = [], []
for sc_ in sb["scenes"]:
    svg = (v / "visual" / sc_["visual"]["svg_path"]).read_text()
    words = SB.scene_words_timed(sc_, timing)
    dur = (words[-1]["end"] + 0.6) if words else 4.0
    sc = de.DoodleScene(svg, style.get("palette"), words, dur, style, scene_id=sc_["id"], camera=sc_.get("camera"), bg=sc_.get("bg"))
    png = out / f"{sc_['id']}.png"
    de.render_still(sc, png, t=max(0.0, dur - 0.05), scale=1, paper=de.Paper(style.get("paper", "plain")))
    ims.append(Image.open(png).convert("RGB").resize((216, 384)))
    comp = sc.composition()
    ents = sorted(a.at for a in sc.root.walk() if a is not sc.root and a.anim != "none")
    punches = sorted(p["at"] for p in sc.camera["punch"])
    ev = sorted(set([0.0] + ents + punches + [dur]))
    gaps = [round(b - a, 2) for a, b in zip(ev, ev[1:])]
    cue = SB.doodle_cue_problems(svg + json.dumps(sc_.get("camera", {})), words)
    hs0 = sc.hook_stats()       # every scene: something on the page at t=0, labels clear of the edges under a punch-in
    edge = [t["text"] for t in hs0["texts_t0"] if min(t["bbox"][0], 1080 - t["bbox"][2]) < 60] if sc.camera["punch"] else []
    rows.append({"id": sc_["id"], "dur": round(dur, 2), "layout": comp["layout"], "sig": comp["main_signature"],
                 "subj": comp["main_subject"], "h": comp["main_height_ratio"], "empty": comp["empty_cells"],
                 "actors": sum(1 for _ in sc.root.walk()) - 1, "max_gap": max(gaps) if gaps else None,
                 "cue_problems": cue, "elements_t0": hs0["elements_at_t0"], "edge_labels_with_punch": edge, "warnings": [w for w in sc.warnings if "not spoken" not in w][:3]})
    if sc_ is sb["scenes"][0]:
        hs = sc.hook_stats()
        rows[-1]["frame0"] = {k: hs[k] for k in ("subject", "subject_height_ratio", "elements_at_t0", "first_visual_event_s",
                                                  "visual_events_first_1_5s")} | {"texts": [(t["text"], t["inside_safe"], t["size_px"]) for t in hs["texts_t0"]]}
for r in rows:
    print(json.dumps(r, ensure_ascii=False))
lay = [r["layout"] for r in rows]
sig = [r["sig"] for r in rows]
print("layouts", lay)
print("repeat>2 layouts:", [i for i in range(2, len(lay)) if lay[i] == lay[i - 1] == lay[i - 2]],
      "| repeat>2 subjects:", [i for i in range(2, len(sig)) if sig[i] == sig[i - 1] == sig[i - 2]],
      "| most common subject share:", round(max(sig.count(s) for s in sig) / len(sig), 2))
strip = Image.new("RGB", (226 * len(ims), 384), "white")
for i, im in enumerate(ims):
    strip.paste(im, (i * 226, 0))
strip.save(out / "strip.jpg", quality=85)
print(out / "strip.jpg")
