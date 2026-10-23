#!/usr/bin/env python3
"""hook_engine — Phase 2 HOOK stage: ≥5 multi-channel hook candidates → frame-0 renders → independent review →
selection (or a structured failure) → opening brief for the Visual Plan.

  hook_engine.py select --hooks hook/hooks.json --dossier research/dossier.json --out-dir hook/ --result hook/result.json
                        [--voice am_michael] [--speed 1.0] [--attempt N]

A hook is verbal + visual + on-screen + tension + topic signal. Each candidate (contract `hook_candidates`) carries
its own frame-0 doodle SVG (`first_frame_svg`, relative to hooks.json). The engine renders frame 0 and t=1 s with the
real doodle engine, measures frame 0 deterministically (subject height, elements, text visibility/size/safe area,
hidden negations, first visual event), estimates the spoken length with the calibrated voice model, and hands each
candidate to the independent reviewer (`reviewer.py review-hooks`) as its own packet — without the author's
reasoning (`why_it_should_work`, mechanism, emotion, concept prose stay out). A candidate is selectable only if
hook_strength, first_frame_clarity and visual/verbal coherence all reach the policy thresholds (≥4) with no
objective failure. Candidates identical to previously failed ones are never re-scored (hooks.history.json).
Outputs: hooks.scored.json, selected_hook.json, opening_brief.json, hook_report.md, candidates/<id>/frame0.png …
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
for sib in ("video-production", "voice-production", "video-quality-assurance"):
    sys.path.insert(0, str(ROOT / sib / "scripts"))
from cf_common import StageResult, emit, exit_for, fix, read_json, validate_artifact, write_json  # noqa: E402

sys.path.insert(0, str(ROOT / "content-analytics" / "scripts"))
import learning_apply as LA  # noqa: E402  (v3.1.0: shared read side of the learning summary)


def load_learning(path):
    return LA.load(path)

FUTURE_MODES = ["doodle", "motion_graphics", "diagram", "kinetic_typography", "generated_visual", "character", "hybrid"]
STOP = set("a an the and or but so of to in on at for with is are was were be it its this that you your we they i as by from "
           "do does did can will just".split())


def cwords(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", t.lower()) if w not in STOP and len(w) > 2}


def jaccard(a: str, b: str) -> float:
    x, y = cwords(a), cwords(b)
    return len(x & y) / max(1, len(x | y))


def fingerprint(c: dict, svg: str) -> str:
    return hashlib.sha256(json.dumps([c["spoken_text"].strip().lower(), c.get("on_screen_text", "").strip().lower(), svg],
                                     ensure_ascii=False).encode()).hexdigest()[:20]


def measure_spoken(text: str, voice: str, speed: float, work: Path) -> float | None:
    """Exact spoken length from the real TTS (sentence cache makes it cheap and pre-warms the AUDIO stage); None if no TTS.
    The estimate under-predicted short hooks by ~0.45 s in two real runs, so selection must not rely on it alone."""
    tts = ROOT / "voice-production" / "scripts" / "tts.py"
    work.mkdir(parents=True, exist_ok=True)
    beats = [{"id": "b1", "role": "hook", "text": text, "claim_ids": []}, {"id": "b2", "role": "value", "text": "Filler.", "claim_ids": []},
             {"id": "b3", "role": "payoff", "text": "Filler.", "claim_ids": []}]
    (work / "s.json").write_text(json.dumps({"video_id": "hook", "language": "en", "beats": beats,
                                             "publish": {"title_options": ["h"], "description": "", "hashtags": []}}),
                                 encoding="utf-8")
    p = subprocess.run([sys.executable, str(tts), "synth", "--script", work / "s.json", "--out-dir", work, "--result", work / "r.json",
                        "--voice", voice, "--speed", str(speed), "--min-s", "0.5", "--max-s", "99"], capture_output=True, text=True)
    t = work / "timing.json"
    if p.returncode not in (0, 2) or not t.exists():
        return None
    sents = [x for x in json.loads(t.read_text(encoding="utf-8"))["sentences"] if x["beat_id"] == "b1"]
    return round(sents[-1]["end"] - sents[0]["start"], 2) if sents else None


def word_times(text: str, voice: str, speed: float, lead: float = 0.08) -> list[dict]:
    import estimate as E
    out, t = [], lead
    for si, sent in enumerate(E.split_sentences(text)):
        if si:
            t += E.ASSEMBLY["sentence_gap"]
        dur = E.sentence_seconds(sent, voice, speed)
        toks = sent.split()
        syl = [max(1, sum(E.syllables(x) for x in E.spoken(w).split())) for w in toks]
        for w, s in zip(toks, syl):
            d = dur * s / sum(syl)
            out.append({"w": w, "start": round(t, 3), "end": round(t + d, 3)})
            t += d
    return out


def render(svg_text: str, words: list[dict], palette: list[str], frames: dict[str, float], out_dir: Path) -> tuple[dict, list]:
    import doodle_engine as de
    import skia
    sc = de.DoodleScene(svg_text, palette, words, max(3.5, (words[-1]["end"] if words else 3) + 0.6), {"wobble": 2.6},
                        scene_id="hook", camera={"drift": "none"})
    paper = de.Paper()
    for name, t in frames.items():
        surf = skia.Surface.MakeRasterN32Premul(de.W, de.H)   # v3.2 speed: same pixels as MakeRaster(ImageInfo), ~50x faster
        sc.draw(surf.getCanvas(), t, paper, camera=True)
        surf.makeImageSnapshot().save(str(out_dir / f"{name}.png"), skia.kPNG)
    return sc.hook_stats(), sc.warnings


def opening_brief(c: dict, stats: dict, svg_rel: str, review: dict) -> dict:
    emph = [w.strip(",.?!") for w in c["spoken_text"].split() if re.search(r"n't$|^(not|no|never|only|why|nerves?)$", w.lower().strip(",.?!"))]
    return {"version": 1, "visual_mode": "doodle", "future_modes": FUTURE_MODES,
            "note": "Interface for the Visual Plan; Phase 3 may route the opening to another mode without changing these fields.",
            "opening_beat": {"hook_id": c["hook_id"], "spoken_line": c["spoken_text"], "on_screen_text": c.get("on_screen_text", ""),
                             "subject": c["first_frame_subject"], "subject_size_target": {"min_height_ratio": 0.35,
                                                                                         "measured": stats.get("subject_height_ratio")},
                             "composition": c["first_frame_concept"], "first_frame_text": c.get("first_frame_text", ""),
                             "first_frame_state": {"elements_at_t0": stats.get("elements_at_t0"), "texts_at_t0": [t["text"] for t in stats.get("texts_t0", [])],
                                                   "subject_bbox": stats.get("subject_bbox")},
                             "visual_action": c["visual_action"], "emphasis_words": emph or [],
                             "camera_intent": "hold frame 0 (no drift needed to read it); punch-in only on an emphasis word, centred, never cropping text",
                             "safe_margin": {"x_ratio": 0.05, "y_ratio": 0.05, "text_min_px": 60},
                             "frame0_svg": svg_rel, "hook_exception": c.get("hook_exception") or stats.get("hook_exception"),
                             "review_scores": {d: v["score"] for d, v in review["scores"].items()}}}


def cmd_select(a) -> int:
    hooks_path = Path(a.hooks)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    d = read_json(hooks_path)
    sr = StageResult("HOOK", "hook-engineering", d.get("video_id"), attempt=a.attempt)
    sr.input(hooks_path, "hook_candidates")
    errs = validate_artifact(d, "hook_candidates")
    sr.check("HOOK.SCHEMA", not errs, "blocking", "; ".join(errs[:6]) or "contract hook_candidates", fix=fix("HOOK", "repair_schema"))
    if errs:
        return exit_for(sr.finalize(a.result))
    cands = d["candidates"]
    dossier = read_json(a.dossier) if a.dossier and Path(a.dossier).exists() else {"facts": [], "sources": []}
    hist_path = out / "hooks.history.json"
    hist = read_json(hist_path) if hist_path.exists() else {"failed": {}}
    # ---- set-level diversity (five rewrites of one sentence are not five hooks)
    mechs = {c["curiosity_mechanism"].strip().lower() for c in cands}
    sims = [(x["hook_id"], y["hook_id"], round(jaccard(x["spoken_text"], y["spoken_text"]), 2))
            for i, x in enumerate(cands) for y in cands[i + 1:]]
    near = [s for s in sims if s[2] >= 0.6]
    concepts = [c["first_frame_concept"].strip().lower() for c in cands]
    sr.check("HOOK.DIVERSITY", len(mechs) >= 4 and not near and len(set(concepts)) == len(concepts), "major",
             f"{len(mechs)} distinct mechanisms; near-duplicate lines {near}; duplicate frame-0 concepts "
             f"{len(concepts) - len(set(concepts))}", len(mechs), 4, fix("HOOK", "regenerate", diversify=True, near_duplicates=near))
    # ---- Phase 5: a hook the channel already used (content memory, history.json) is never selected again
    past = [x["text"] for x in (read_json(a.history).get("items", []) if a.history and Path(a.history).exists() else [])
            if x.get("kind") == "hook" and x.get("text")]
    repeated_past = {}
    for c in cands:
        m = max(((jaccard(c["spoken_text"], h), h) for h in past), default=(0.0, ""))
        if m[0] >= 0.6:                                   # same threshold as HOOK.DIVERSITY's near-duplicate lines
            repeated_past[c["hook_id"]] = {"similarity": round(m[0], 2), "past_hook": m[1]}
    if repeated_past:
        sr.check("HOOK.NOT_REPEATED", False, "minor", f"candidates repeating an earlier video's hook (not selectable): "
                 f"{repeated_past}", fix=fix("HOOK", "regenerate", strategy="change", repeated_past=repeated_past))
    # ---- render + measure + packet per candidate
    import estimate as E
    from review_packet import write_packet
    facts = {f["id"]: f for f in dossier.get("facts", [])}
    rows, packets = [], []
    for c in cands:
        cid = c["hook_id"]
        svg_file = (hooks_path.parent / c["first_frame_svg"]).resolve()
        cdir = out / "candidates" / cid
        cdir.mkdir(parents=True, exist_ok=True)
        row = {"hook_id": cid, "spoken_text": c["spoken_text"], "on_screen_text": c.get("on_screen_text", ""),
               "curiosity_mechanism": c["curiosity_mechanism"]}
        try:
            svg = svg_file.read_text(encoding="utf-8")
        except OSError as exc:
            row.update(status="error", reason=f"first_frame_svg unreadable: {exc}")
            rows.append(row)
            continue
        fp = fingerprint(c, svg)
        row["fingerprint"] = fp
        est = sum(E.sentence_seconds(s, a.voice, a.speed) for s in E.split_sentences(c["spoken_text"])) + \
            E.ASSEMBLY["sentence_gap"] * (len(E.split_sentences(c["spoken_text"])) - 1)
        real = measure_spoken(c["spoken_text"], a.voice, a.speed, out / "candidates" / cid / "tts")
        row["estimated_duration_s"] = round(est, 2)
        row["measured_duration_s"] = real
        est = real if real is not None else est   # judge the hook on what the voice will really say (Phase 3 finding)
        if fp in hist["failed"]:
            row.update(status="repeated_failed", reason=f"identical to a candidate that failed in attempt "
                       f"{hist['failed'][fp]['attempt']}: {hist['failed'][fp]['reasons'][:3]}")
            rows.append(row)
            continue
        if cid in repeated_past:
            row.update(status="repeated_past", reason=f"repeats an earlier video's hook ({repeated_past[cid]['similarity']}): "
                       f"{repeated_past[cid]['past_hook'][:80]!r}")
            rows.append(row)
            continue
        try:
            stats, warns = render(svg, word_times(c["spoken_text"], a.voice, a.speed), d.get("palette") or
                                  ["#ffd23f", "#e8452c", "#3b82c4", "#2f9e44", "#f783ac"], {"frame0": 0.0, "frame_1s": 1.0}, cdir)
        except Exception as exc:  # noqa: BLE001
            row.update(status="error", reason=f"frame 0 did not render: {exc}")
            rows.append(row)
            continue
        row.update(status="rendered", frame0=str(cdir / "frame0.png"), measurements=stats, render_warnings=warns)
        pk = cdir / "packet"
        promised = c.get("fact_ids") or []
        write_packet(pk, {"frames/frame0.png": cdir / "frame0.png", "frames/frame_1s.png": cdir / "frame_1s.png",
                          "text/hook.json": {"spoken_text": c["spoken_text"], "on_screen_text": c.get("on_screen_text", ""),
                                             "estimated_duration_s": round(est, 2), "duration_source": "tts" if real is not None else "estimate",
                                             "video_kind": getattr(a, "video_kind", None) or d.get("video_kind", "short"),
                                             "topic": d["topic"]},
                          "evidence/claims.json": {"facts": [facts[i] for i in facts], "promised_fact_ids": promised},
                          "measurements/frame0.json": stats}, "hook candidate")
        man = read_json(pk / "manifest.json")
        man["candidate_id"] = cid
        write_json(pk / "manifest.json", man)
        packets.append(str(pk))
        rows.append(row)
    rendered = [r for r in rows if r["status"] == "rendered"]
    repeated = [r for r in rows if r["status"] in ("repeated_failed", "repeated_past")]
    sr.check("HOOK.FRAME0_RENDERED", all(r["status"] != "error" for r in rows), "blocking",
             "; ".join(f"{r['hook_id']}: {r['reason']}" for r in rows if r["status"] == "error") or "all frame-0 SVGs render",
             fix=fix("HOOK", "repair_frames"))
    if repeated and not rendered and all(r["status"] == "repeated_failed" for r in repeated):
        sr.check("HOOK.FUTILE_RESUBMISSION", False, "blocking",
                 f"every candidate is identical to one that already failed ({[r['hook_id'] for r in repeated]}); "
                 "re-scoring them cannot change the result — write new candidates with a different strategy")
        write_json(out / "hooks.scored.json", {"candidates": rows, "selected": None})
        return exit_for(sr.finalize(a.result))
    # ---- independent review (separate process, packets only)
    reviews = {}
    if packets:
        rv = subprocess.run([sys.executable, str(ROOT / "video-quality-assurance/scripts/reviewer.py"), "review-hooks",
                             "--packets", *packets, "--out", str(out / "review")], capture_output=True, text=True)
        if rv.returncode != 0:
            sr.fail("HOOK.REVIEW_ERROR", (rv.stderr or rv.stdout)[-500:], fix=fix("HOOK", "retry"), retryable=True)
            return exit_for(sr.finalize(a.result))
        reviews = {r["candidate"]: r for r in read_json(out / "review" / "hook_reviews.json")["results"]}
    for r in rendered:
        rv = reviews.get(r["hook_id"])
        r["review"] = {"verdict": rv["verdict"], "scores": {k: v["score"] for k, v in rv["scores"].items()},
                       "failures": rv["failures"], "evidence": {k: v["evidence"] for k, v in rv["scores"].items()}}
        r["total"] = sum(r["review"]["scores"].values())
        if rv["verdict"] != "PASS":
            hist["failed"][r["fingerprint"]] = {"hook_id": r["hook_id"], "attempt": a.attempt,
                                                "reasons": [f.get("id") for f in rv["failures"]]}
    write_json(hist_path, hist)
    # ---- v3.1.0: evidence from published videos re-ranks PASSING candidates only (bounded bonus, recorded)
    learning = load_learning(a.learning) if getattr(a, "learning", None) else None
    for r in rendered:
        b, why = LA.hook_bonus(learning, LA.opening_form(r["spoken_text"]), r["curiosity_mechanism"]) if learning else (0.0, [])
        r["opening_form"] = LA.opening_form(r["spoken_text"])
        r["learning_bonus"], r["learning_reasons"] = b, why
    passing_plain = sorted([r for r in rendered if r["review"]["verdict"] == "PASS"],
                           key=lambda r: (-r["total"], r["estimated_duration_s"]))
    passing = sorted(passing_plain, key=lambda r: (-(r["total"] + r["learning_bonus"]), r["estimated_duration_s"]))
    sel = passing[0] if passing else None
    influence = None
    if learning:
        pref = {"opening_form": LA.preferred_levels(learning, "opening_form") + LA.tested_levels(learning, "opening_form"),
                "curiosity_mechanism": LA.preferred_levels(learning, "curiosity_mechanism") +
                LA.tested_levels(learning, "curiosity_mechanism")}
        have = {"opening_form": {LA.opening_form(c["spoken_text"]) for c in cands},
                "curiosity_mechanism": {c["curiosity_mechanism"].strip().lower() for c in cands}}
        miss = {k: sorted(set(v) - have[k]) for k, v in pref.items() if set(v) - have[k]}
        sr.check("HOOK.LEARNING_COVERAGE", not miss, "minor",
                 f"candidate set lacks evidence-preferred or tested levels {miss}" if miss else
                 f"candidates cover the evidence-preferred and tested levels ({learning['summary_id']})",
                 fix=fix("HOOK", "regenerate", strategy="add", missing_levels=miss) if miss else None)
        influence = {"summary_id": learning["summary_id"], "summary_sha256": learning.get("_sha256"),
                     "selected": sel["hook_id"] if sel else None,
                     "without_learning": passing_plain[0]["hook_id"] if passing_plain else None,
                     "changed_choice": bool(sel and passing_plain and sel["hook_id"] != passing_plain[0]["hook_id"]),
                     "bonuses": {r["hook_id"]: r["learning_bonus"] for r in rendered},
                     "reasons": sel["learning_reasons"] if sel else [],
                     "rule": f"bonus = {LA.HOOK_BONUS_SCALE:g} x (opening-form prior x mechanism prior - 1), capped at "
                             f"±{LA.MAX_HOOK_BONUS}; only candidates that passed the independent review are re-ranked"}
        sr.metric("learning_influence", influence)
    by_id = {c["hook_id"]: c for c in cands}
    write_json(out / "hooks.scored.json", {"topic": d["topic"], "selected": sel["hook_id"] if sel else None, "candidates": rows,
                                           "diversity": {"mechanisms": sorted(mechs), "pairwise_similarity": sims}})
    if sel:
        c = by_id[sel["hook_id"]]
        write_json(out / "selected_hook.json", {**c, "estimated_duration_s": sel["estimated_duration_s"], "review": sel["review"],
                                                "measurements": sel["measurements"],
                                                **({"learning_influence": influence} if influence else {})})
        write_json(out / "opening_brief.json", opening_brief(c, sel["measurements"], c["first_frame_svg"], reviews[sel["hook_id"]]))
        sr.output(out / "selected_hook.json", "selected_hook", "application/json")
        sr.output(out / "opening_brief.json", "opening_brief", "application/json")
    why = [{"hook_id": r["hook_id"], "reasons": [f"{f.get('id')}{(' ' + str(f.get('score'))) if f.get('score') else ''}: "
                                                 f"{str(f.get('evidence'))[:120]}" for f in r["review"]["failures"]]}
           for r in rendered if r["review"]["verdict"] != "PASS"] + \
          [{"hook_id": r["hook_id"], "reasons": [r["reason"]]} for r in repeated]
    sr.check("HOOK.SELECTED", sel is not None, "blocking",
             f"selected {sel['hook_id']} ({sel['review']['scores']})" if sel else
             f"no candidate reaches hook ≥4, first frame ≥4 and coherence ≥4: {why}",
             fix=None if sel else fix("HOOK", "regenerate", strategy="change", failed=why,
                                      tried_mechanisms=sorted(mechs)))
    lines = [f"# Hook selection — {d['topic']}", "", f"selected: **{sel['hook_id'] if sel else 'none'}**", ""] + \
        ([f"learning {influence['summary_id']}: without it **{influence['without_learning']}**; bonuses "
          f"{influence['bonuses']}; {'changed the choice' if influence['changed_choice'] else 'did not change the choice'}", ""]
         if influence else []) + [
             "| id | mechanism | spoken | on screen | est s | hook | frame 0 | coherence | verdict |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        s = (r.get("review") or {}).get("scores", {})
        lines.append(f"| {r['hook_id']} | {r['curiosity_mechanism']} | {r['spoken_text']} | {r['on_screen_text']} | "
                     f"{r.get('estimated_duration_s')} | {s.get('hook_strength', '—')} | {s.get('first_frame_clarity', '—')} | "
                     f"{s.get('visual_verbal_sync', '—')} | {(r.get('review') or {}).get('verdict', r['status'])} |")
    (out / "hook_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    sr.output(out / "hooks.scored.json", "hooks_scored", "application/json")
    sr.metric("candidates", len(cands)); sr.metric("selected", sel["hook_id"] if sel else None)
    sr.metric("scores", {r["hook_id"]: (r.get("review") or {}).get("scores") for r in rows})
    res = sr.finalize(a.result)
    emit(res)
    return exit_for(res)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    s.add_argument("--hooks", required=True); s.add_argument("--dossier"); s.add_argument("--out-dir", required=True)
    s.add_argument("--result", required=True); s.add_argument("--voice", default="am_michael"); s.add_argument("--speed", type=float, default=1.0)
    s.add_argument("--attempt", type=int, default=1)
    s.add_argument("--history", help="content memory export (cfdb.py history): candidates repeating a past hook are not selectable")
    s.add_argument("--learning", help="learning summary (cf-learning/1): bounded bonus for passing candidates, recorded")
    s.add_argument("--video-kind", default="short", choices=["short", "long"],
                   help="hook window: short = 3.2 s (Shorts heuristic), long = 8.0 s (YouTube's 5-10 s long-form guidance)")
    a = ap.parse_args()
    return cmd_select(a)


if __name__ == "__main__":
    sys.exit(main())
