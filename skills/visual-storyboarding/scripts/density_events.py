#!/usr/bin/env python3
"""density_events.py — fill motion gaps in doodle scenes by binding new entrances to narration words.

Why this exists: `VID.MOTION_GAP` / `VID.PACING_CADENCE` (video-production) fail when a scene goes longer than
`max_motion_gap` (3.5 s) without a *new* visual event. A hand-authored storyboard very easily puts all its entrances in
the first second and leaves the rest of a 6-10 s scene still, which is exactly what happened on the first long-form
run. The pipeline only *reports* this (`fix_action: add_entrances` with an `at_s`); nothing in the factory actually
adds the entrances. This tool does that one job, deterministically.

  density_events.py --storyboard DIR/storyboard.json --timing DIR/audio/timing.json --max-gap 3.5 [--dry-run]

For every scene it:
  1. loads the SVG and finds the narration words of that scene (real AUDIO timings);
  2. simulates the engine's entrance times (so it measures what the renderer will actually do, not a guess);
  3. while the largest gap (including the tail after the last entrance) exceeds `--max-gap`, picks the *earliest*
     unused word that lands after the current last entrance and appends a small idle-animated accent
     (sparkle / question / star / exclaim ...) bound to that word with `data-at="w:<word>"`;
  4. writes the SVG back only if every new accent keeps the scene's composition and geometry gates green.

Accents are placed along the bottom margin and the side rails, never in the caption band (y 1060-1360) and never in the
safe-area edges, so a density fix cannot break VIS/TEXT/OVERHANG gates. Idempotent: a scene already dense enough is
left byte-identical.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
for _p in (str(_HERE.parents[2] / "video-production" / "scripts"), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# accents that read as "something just happened" without changing what the scene depicts, with the idle loop that suits
# each one. Kept small and few so a scene never turns into confetti.
ACCENTS = [
    ("sparkle", "pulse", "#e03131"),
    ("question", "bob", "#1c7ed6"),
    ("star", "pulse", "#f59f00"),
    ("sparkle", "tremble", "#2f9e44"),
    ("exclaim", "tremble", "#e03131"),
    ("sparkle", "pulse", "#7048e8"),
]

# anchor boxes (x, y) the accents cycle through: left rail, right rail, bottom-left, bottom-right, bottom-centre.
# All sit between the drawing (which the storyboard keeps above ~y=1000) and the caption band (y 1060-1360) is avoided
# by keeping y <= 1010 or >= 1400.
ANCHORS = [(170, 1440), (910, 1440), (540, 1500), (170, 1600), (910, 1600), (540, 1660)]
# v3.3.1: 16:9 (1920x1080) — the portrait anchors are off-canvas there, so every accent failed the geometry gate and
# long-form scenes were never densified. Wide anchors sit on the side rails and the lower corners, above the caption
# band (y >= 864) and inside the 5 % safe margin.
ANCHORS_WIDE = [(150, 330), (1770, 330), (150, 600), (1770, 600), (170, 790), (1750, 790)]


def anchors() -> list[tuple[int, int]]:
    import doodle_engine as de
    return ANCHORS_WIDE if de.W > de.H else ANCHORS


def _nw(w: str) -> str:
    return "".join(c for c in w.lower() if c.isalnum() or c == "'")


def scene_words_timed(scene: dict, timing: dict) -> list[dict]:
    sent_ids = {r["i"] for r in timing["sentences"] if r.get("beat_id") in set(scene.get("beat_ids", []))}
    ws = [w for w in timing["words"] if w["sentence"] in sent_ids]
    if not ws:
        return []
    t0 = max(0.0, ws[0]["start"] - 0.08)
    return [{"w": w["w"], "start": round(w["start"] - t0, 3), "end": round(w["end"] - t0, 3)} for w in ws]


def entrance_times(svg: str, words: list[dict], style: dict, scene_id: str) -> list[float]:
    """The times the engine will actually fire entrances, by building the scene the way the renderer does."""
    import doodle_engine as de
    dur = (words[-1]["end"] + 0.6) if words else 4.0
    sc = de.DoodleScene(svg, style["palette"], words, dur, style, scene_id=scene_id)
    return sorted({round(a.at, 3) for a in sc.root.walk() if a.at is not None and a.anim != "none"}), dur


def gate_ok(svg: str, words: list[dict], style: dict, scene_id: str) -> bool:
    """True when the scene still passes the local composition/geometry/cue checks after an edit."""
    import doodle_engine as de
    import storyboard_tool as ST
    dur = (words[-1]["end"] + 0.6) if words else 4.0
    sc = de.DoodleScene(svg, style["palette"], words, dur, style, scene_id=scene_id)
    if [w for w in sc.warnings if "not spoken" not in w]:
        return False
    if sc.audit_geometry():
        return False
    if ST.doodle_cue_problems(svg, words):
        return False
    comp = sc.composition()
    if comp.get("layout") in ("hero", "split", "character", "scatter") and comp.get("main_height_ratio", 1) < 0.18:
        return False
    if comp.get("empty_cells", 0) >= 5:
        return False
    return True


def accent_svg(kind: str, loop: str, colour: str, x: int, y: int, word: str, n: int) -> str:
    sc = 0.9 if y < 1000 else 1.1   # smaller on the 16:9 rails
    return (f'<g id="dens{n}" data-lib="{kind}" data-fill="{colour}" '
            f'transform="translate({x} {y}) scale({sc})" data-in="pop" data-at="w:{word}" data-loop="{loop}"/>')


def densify(svg: str, words: list[dict], style: dict, scene_id: str, max_gap: float,
            dry: bool = False) -> tuple[str, list[dict]]:
    times, dur = entrance_times(svg, words, style, scene_id)
    added: list[dict] = []
    used: set[int] = set()
    body = svg.rsplit("</svg>", 1)[0]
    n = 0
    for _ in range(40):                                     # bounded: at most 40 accents per scene
        times, dur = entrance_times(body + "</svg>", words, style, scene_id)
        if not times:
            break
        spans = [(a, b) for a, b in zip(times, times[1:])] + [(times[-1], dur)]
        a0, b0 = max(spans, key=lambda ab: ab[1] - ab[0])
        if b0 - a0 <= max_gap:
            break
        # v3.3.1: fill the WORST gap (interior or tail), not only the tail after the last entrance: interior gaps
        # were never filled, so the render kept failing VID.MOTION_GAP one scene at a time. Within the gap take the
        # latest word that still closes it, so one accent covers a whole max_gap window instead of stacking up.
        # A cue `w:<word>` binds to the word's FIRST occurrence in the scene, so repeated words are skipped.
        first = lambda i: all(_nw(x["w"]) != _nw(words[i]["w"]) for x in words[:i])  # noqa: E731
        ok = lambda i: i not in used and first(i)  # noqa: E731
        win = [i for i, w in enumerate(words) if ok(i) and a0 + 0.35 < w["start"] <= min(b0, a0 + max_gap) - 0.15]
        pick = max(win, key=lambda i: words[i]["start"]) if win else \
            next((i for i, w in enumerate(words) if ok(i) and a0 + 0.35 < w["start"] < b0 - 0.35), None)
        if pick is None:
            break
        kind, loop, colour = ACCENTS[n % len(ACCENTS)]
        anc = anchors()
        x, y = anc[n % len(anc)]
        frag = accent_svg(kind, loop, colour, x, y, words[pick]["w"], n)
        trial = body + frag + "</svg>"
        if not gate_ok(trial, words, style, scene_id):
            used.add(pick)
            continue
        body = body + frag
        used.add(pick)
        added.append({"scene": scene_id, "word": words[pick]["w"], "at_s": words[pick]["start"],
                      "kind": kind, "anchor": [x, y]})
        n += 1
    return body + "</svg>", added


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--storyboard", required=True)
    ap.add_argument("--timing", required=True)
    ap.add_argument("--max-gap", type=float, default=3.5)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    sb = json.load(open(a.storyboard, encoding="utf-8"))
    timing = json.load(open(a.timing, encoding="utf-8"))
    sb_dir = Path(a.storyboard).resolve().parent
    style = sb.get("style", {})
    canvas = style.get("canvas") or sb.get("canvas")
    if canvas:                                   # v3.3.1: measure and place on the storyboard's own canvas
        import doodle_engine as de
        de.set_canvas(int(canvas[0]), int(canvas[1]))
    total, touched = [], 0
    wide = bool(canvas) and int(canvas[0]) > int(canvas[1])
    for k, scene in enumerate(sb["scenes"]):
        if wide and k == len(sb["scenes"]) - 1:
            continue        # v3.3.1: the closing 16:9 scene carries the end-screen zone, which must stay calm
        words = scene_words_timed(scene, timing)
        if not words:
            continue
        p = Path(scene["visual"]["svg_path"])
        if not p.is_absolute():
            p = sb_dir / p
        svg = p.read_text(encoding="utf-8")
        # v3.3.1: aim 0.25 s under the gate: the scene-local timeline here and the render's global one differ by a
        # few frames (shot starts, transitions), and a 3.54 s gap against a 3.5 s limit cost a 30-minute re-render.
        new, added = densify(svg, words, style, scene["id"], max(1.0, a.max_gap - 0.25), dry=a.dry_run)
        if added:
            touched += 1
            total += added
            if not a.dry_run:
                p.write_text(new, encoding="utf-8")
    print(json.dumps({"scenes_touched": touched, "accents_added": len(total), "added": total}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
