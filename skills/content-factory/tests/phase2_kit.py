"""Phase 2 fixture kit: hook-candidate sets with real frame-0 doodle SVGs + a small dossier; script variants."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
HOOK_ENGINE = ROOT / "hook-engineering/scripts/hook_engine.py"
SCRIPT_SELECT = ROOT / "short-form-script/scripts/script_select.py"
H = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920">'
DOSSIER = {"topic": "Why fingers wrinkle in water", "sources": [{"id": "s1", "url": "https://pmc.ncbi.nlm.nih.gov/x", "title": "t"}],
           "facts": [{"id": f"f{i}", "claim": c, "source_ids": ["s1"], "risk": "low"} for i, c in enumerate([
               "Fingers with a damaged median nerve do not wrinkle in water.",
               "Nerves narrow blood vessels under the fingertip and the skin folds.",
               "Doctors have used water wrinkling as a bedside nerve test.",
               "One idea is that wrinkles work like rain treads for grip.",
               "A 2013 study found wrinkled fingers moved wet objects faster."], start=1)]}


def finger(fid="finger", x0=280, x1=600, top=340, wr=True, nerve=False) -> str:
    w = x1 - x0
    s = f'<g id="{fid}" data-in="none"><path d="M{x0},1040 L{x0},{top + 140} C{x0},{top - 20} {x1},{top - 20} {x1},{top + 140} L{x1},1040 Z" fill="#f6c9a8"/>'
    if wr:
        s += f'<g data-in="none" data-inside="#{fid}">' + "".join(
            f'<path d="M{x0 + 34},{top + 70 + k * 46} q{(w - 68) / 10},-14 {(w - 68) / 5},0 t{(w - 68) / 5},0 t{(w - 68) / 5},0 t{(w - 68) / 5},0 t{(w - 68) / 5},0" '
            'fill="none" stroke="#b97a5a" stroke-width="6"/>' for k in range(4)) + "</g>"
    if nerve:
        cx = (x0 + x1) / 2
        s += (f'<path d="M{cx},1030 L{cx - 30},880 L{cx + 25},760 L{cx - 20},640" fill="none" stroke="#ffd23f" stroke-width="12" '
              f'data-in="none" data-loop="pulse" data-inside="#{fid}"/>')
    return s + "</g>"


WATER = '<path d="M60,900 q46,-22 92,0 t92,0 t92,0 t92,0 t92,0 t92,0 t92,0 t92,0 t92,0 t92,0" fill="none" stroke="p2" stroke-width="8" data-in="none"/>'
STRONG_SVG = H + finger(nerve=True) + WATER + ('<g data-lib="cross" transform="translate(830 620) scale(1.5)" data-in="draw" data-at="0.1" data-dur="0.3"/>'
                                               '<text x="540" y="215" font-family="marker" font-size="104" data-in="none">NOT WATER</text></svg>')


def cand(hid, spoken, svg_name, on_screen="NOT WATER", mech=None, fact_ids=("f1", "f2"), **extra) -> dict:
    return {"hook_id": hid, "spoken_text": spoken, "visual_concept": "finger in water", "on_screen_text": on_screen,
            "curiosity_mechanism": mech or f"mechanism_{hid}", "tension": "myth vs cause", "target_emotion": "surprise",
            "first_frame_concept": f"concept {hid}", "first_frame_subject": "wrinkled finger", "first_frame_text": on_screen,
            "visual_action": "cross strikes at 0.1 s", "payoff_connection": "nerves narrow vessels", "why_it_should_work": "AUTHOR-REASONING-SECRET",
            "first_frame_svg": f"svg/{svg_name}.svg", "fact_ids": list(fact_ids), **extra}


def write_set(d: Path, svgs: dict[str, str], cands: list[dict]) -> Path:
    (d / "svg").mkdir(parents=True, exist_ok=True)
    for k, v in svgs.items():
        (d / "svg" / f"{k}.svg").write_text(v, encoding="utf-8")
    (d / "dossier.json").write_text(json.dumps(DOSSIER), encoding="utf-8")
    (d / "hooks.json").write_text(json.dumps({"video_id": "t", "language": "en", "topic": DOSSIER["topic"], "candidates": cands}), encoding="utf-8")
    return d


def select_hooks(d: Path, attempt: int = 1) -> dict:
    subprocess.run([PY, str(HOOK_ENGINE), "select", "--hooks", d / "hooks.json", "--dossier", d / "dossier.json", "--out-dir", d,
                    "--result", d / "result.json", "--attempt", str(attempt)], capture_output=True, text=True)
    scored = json.loads((d / "hooks.scored.json").read_text()) if (d / "hooks.scored.json").exists() else {}
    return {"result": json.loads((d / "result.json").read_text()), "scored": scored}


def select_script(d: Path, hook_json: Path, variants: list[dict], min_s=10, max_s=60) -> dict:
    (d / "script_variants.json").write_text(json.dumps({"video_id": "t", "language": "en", "hook_id": "h1", "variants": variants}))
    (d / "dossier.json").write_text(json.dumps(DOSSIER))
    subprocess.run([PY, str(SCRIPT_SELECT), "select", "--variants", d / "script_variants.json", "--hook", hook_json, "--dossier",
                    d / "dossier.json", "--out", d / "script.json", "--result", d / "result.json", "--min-s", str(min_s), "--max-s", str(max_s)],
                   capture_output=True, text=True)
    return {"result": json.loads((d / "result.json").read_text()),
            "scored": json.loads((d / "script_variants.scored.json").read_text()) if (d / "script_variants.scored.json").exists() else {}}


def beat(i, role, text, claims, **k):
    return {"id": i, "role": role, "text": text, "claim_ids": claims, "visual_intent": f"visual for {i}", **k}
