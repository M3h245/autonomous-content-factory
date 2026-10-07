#!/usr/bin/env python3
"""script_select — Phase 2 SCRIPT stage: two complete script variants → deterministic checks → independent review →
the stronger variant becomes script.json (or a structured failure).

  script_select.py select --variants script/script_variants.json --hook hook/selected_hook.json --dossier research/dossier.json
                          --out script/script.json --result script/result.json [--min-s 20 --max-s 45]
                          [--voice am_michael] [--speed 1.0] [--attempt N]

Each variant (contract `script_variants`) is a full script: beats (hook → setup → explanation/evidence → payoff →
ending) with claim_ids, visual_intent, optional emphasis and intentional pause_before/pause_after, plus publish.
Deterministic checks per variant: the opening IS the selected hook (blocking), the hook's promised facts are paid off
(blocking), claims trace to the dossier (blocking), no generic intro, explanation starts by 8 s, hook not repeated
mid-script, calibrated duration inside the window, visual intent on every beat, pauses used sparingly.
The two variants must differ in structure/rhythm, not wording. Each variant is reviewed independently
(`reviewer.py review-script`, estimated transcript + public hook + publish + claims + check results; no beat roles
or visual intents); selection needs clarity, pacing, payoff coherence and hook ≥ 4.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
for sib in ("voice-production", "video-quality-assurance"):
    sys.path.insert(0, str(ROOT / sib / "scripts"))
from cf_common import StageResult, emit, exit_for, fix, read_json, validate_artifact, write_json  # noqa: E402

GENERIC = ["today we", "in this video", "let's talk", "lets talk", "we're going to", "we are going to", "welcome", "hey guys",
           "before we start", "a little bit about"]
STOP = set("a an the and or but so of to in on at for with is are was were be it its this that you your we they i as by from "
           "do does did can will just".split())


def norm(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()


def cw(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", t.lower()) if w not in STOP and len(w) > 2}


def check_variant(v: dict, hook: dict, facts: set, lo: float, hi: float, voice: str, speed: float,
                  cta_history: list | None = None, topic: str = "", require_cta: bool = False) -> dict:
    import estimate as E
    beats = v["beats"]
    sents = E.estimate_sentences({"beats": beats}, voice, speed)
    est = E.estimate_script({"beats": beats}, voice, speed)
    checks = []

    def c(cid, ok, sev, ev):
        checks.append({"id": cid, "passed": bool(ok), "severity": sev, "evidence": ev})
    opening_ok = beats[0]["role"] == "hook" and norm(beats[0]["text"]) == norm(hook["spoken_text"])
    c("SCRIPT.HOOK_IS_OPENING", opening_ok, "blocking", f"beat 1 = '{beats[0]['text'][:60]}' vs hook '{hook['spoken_text'][:60]}'")
    c("SCRIPT.HOOK_ON_SCREEN", norm(beats[0].get("on_screen", "")) == norm(hook.get("on_screen_text", "")), "minor",
      f"'{beats[0].get('on_screen', '')}' vs '{hook.get('on_screen_text', '')}'")
    body = " ".join(b["text"] for b in beats[1:3]).lower()
    c("SCRIPT.NO_GENERIC_INTRO", not any(g in body for g in GENERIC), "major", "beats 2-3 checked for throat-clearing")
    after = [b for b in beats[1:] if b.get("claim_ids")]
    expl_start = next((x["start"] for x in sents if after and x["beat_id"] == after[0]["id"]), None)
    c("SCRIPT.FAST_EXPLANATION", expl_start is not None and expl_start <= 8.0, "major", f"first evidence beat starts at {expl_start}s")
    promised = set(hook.get("fact_ids") or [])
    used_after = {i for b in beats[1:] for i in b.get("claim_ids", [])}
    c("SCRIPT.PROMISE_PAID", promised <= used_after, "blocking", f"hook promises {sorted(promised)}; body uses {sorted(used_after)}")
    used = {i for b in beats for i in b.get("claim_ids", [])}
    c("SCRIPT.CLAIMS_TRACEABLE", used <= facts, "blocking", f"unknown claim ids {sorted(used - facts)}")
    mid = [b for b in beats[1:-1] if norm(hook["spoken_text"]) in norm(b["text"])]
    c("SCRIPT.HOOK_NOT_REPEATED", not mid, "major", f"hook repeated in {[b['id'] for b in mid]}")
    c("SCRIPT.DURATION", lo <= est["total_s"] <= hi - 0.5, "major", f"calibrated estimate {est['total_s']}s (window {lo}-{hi}, 0.5 s margin)")
    c("SCRIPT.VISUAL_INTENT", all((b.get("visual_intent") or "").strip() for b in beats), "major",
      f"beats without visual intent: {[b['id'] for b in beats if not (b.get('visual_intent') or '').strip()]}")
    pauses = [b["id"] for b in beats if b.get("pause_before") or b.get("pause_after")]
    bad_p = [b["id"] for b in beats for k in ("pause_before", "pause_after") if b.get(k) is not None and not 0 <= float(b[k]) <= 1.5]
    c("SCRIPT.PAUSES", len(pauses) <= 2 and not bad_p, "major", f"pauses on {pauses}; out of range {bad_p}")
    import cta as CTA                                  # Phase 3.5: CTA decision gated on the estimated timeline
    cta_res = CTA.check({"beats": beats, "cta": v.get("cta")}, sents, est["total_s"], history=cta_history, topic=topic,
                        title=(v.get("publish", {}).get("title_options") or [""])[0], timeline="estimate")
    checks += cta_res["checks"]
    if require_cta:   # runs created with cta_engine v1 (Phase 3.5+); older runs replay unchanged
        c("CTA.DECIDED", v.get("cta") is not None, "major", "every variant records a CTA decision (needed true/false + reason)")
    lens = [len(x["text"].split()) for x in sents]
    return {"cta": cta_res, "checks": checks, "estimate": est, "sentences": sents, "explanation_start_s": expl_start, "hook_is_opening": opening_ok,
            "hook_repeated_mid": bool(mid), "rhythm": {"sentences": len(lens), "mean_words": round(float(np.mean(lens)), 2),
                                                       "std_words": round(float(np.std(lens)), 2)},
            "roles": [b["role"] for b in beats], "script_fact_ids": sorted(used)}


def public_cta(res: dict) -> dict:
    """The CTA as the audience gets it — type, words, on-screen text, timing — for the independent reviewer."""
    c = res.get("cta") or {}
    if not c.get("needed"):
        return {"present": False}
    return {"present": True, "type": c.get("type"), "placement": c.get("placement"), "modality": c.get("modality"),
            "spoken": c.get("spoken", ""), "on_screen": c.get("on_screen", ""), "window_s": res.get("window")}


def distinct(a: dict, b: dict, va: dict, vb: dict) -> tuple[bool, dict]:
    ta = " ".join(x["text"] for x in va["beats"][1:])
    tb = " ".join(x["text"] for x in vb["beats"][1:])
    jac = len(cw(ta) & cw(tb)) / max(1, len(cw(ta) | cw(tb)))
    ra, rb = a["rhythm"], b["rhythm"]
    structure = a["roles"] != b["roles"] or abs(len(a["roles"]) - len(b["roles"])) >= 1
    rhythm = abs(ra["mean_words"] - rb["mean_words"]) / max(ra["mean_words"], 1e-6) >= 0.15 or \
        abs(ra["std_words"] - rb["std_words"]) / max(ra["std_words"], 1e-6) >= 0.25 or abs(ra["sentences"] - rb["sentences"]) >= 2
    return (structure or rhythm) and jac < 0.7, {"role_sequences_differ": structure, "rhythm_differs": rhythm,
                                                "body_word_overlap": round(jac, 2), "rhythm_a": ra, "rhythm_b": rb}


def cmd_select(a) -> int:
    from review_packet import write_packet
    vpath = Path(a.variants)
    out_dir = Path(a.result).parent
    d = read_json(vpath)
    sr = StageResult("SCRIPT", "short-form-script", d.get("video_id"), attempt=a.attempt)
    sr.input(vpath, "script_variants"); sr.input(a.hook, "selected_hook")
    errs = validate_artifact(d, "script_variants")
    for v in d.get("variants", []):
        errs += [f"{v.get('variant_id')}: {e}" for e in validate_artifact({"video_id": d.get("video_id", "v"), "language": d.get("language", "en"),
                                                                          "beats": v.get("beats", []), "publish": v.get("publish", {})}, "script")]
    sr.check("SCRIPT.SCHEMA", not errs, "blocking", "; ".join(errs[:6]) or "contract script_variants", fix=fix("SCRIPT", "repair_schema"))
    if errs:
        return exit_for(sr.finalize(a.result))
    hook = read_json(a.hook)
    dossier = read_json(a.dossier) if a.dossier and Path(a.dossier).exists() else {"facts": []}
    facts = {f["id"] for f in dossier.get("facts", [])}
    hist = [h["text"] for h in read_json(a.cta_history)["ctas"]] if a.cta_history and Path(a.cta_history).exists() else []
    res = {v["variant_id"]: check_variant(v, hook, facts, a.min_s, a.max_s, a.voice, a.speed, hist, dossier.get("topic", ""),
                                        a.require_cta_decision)
           for v in d["variants"]}
    vs = d["variants"]
    ok, info = distinct(res[vs[0]["variant_id"]], res[vs[1]["variant_id"]], vs[0], vs[1])
    sr.check("SCRIPT.VARIANTS_DISTINCT", ok, "major", f"{info}", fix=fix("SCRIPT", "regenerate", make_distinct=True, detail=info))
    packets = []
    for v in vs:
        r = res[v["variant_id"]]
        pk = out_dir / "variants" / v["variant_id"] / "packet"
        sents = r["sentences"]
        write_packet(pk, {"text/transcript.json": {"text": " ".join(x["text"] for x in sents), "estimated_duration_s": r["estimate"]["total_s"],
                                                   "sentences": [{"text": x["text"], "start": x["start"], "end": x["end"]} for x in sents]},
                          "text/hook.json": {"spoken_text": hook["spoken_text"], "on_screen_text": hook.get("on_screen_text", "")},
                          "text/publish.json": {"title": (v["publish"].get("title_options") or [""])[0],
                                                "description": v["publish"].get("description", ""), "target_duration_s": [a.min_s, a.max_s]},
                          "evidence/claims.json": {"facts": dossier.get("facts", []), "promised_fact_ids": hook.get("fact_ids") or [],
                                                   "script_fact_ids": r["script_fact_ids"]},
                          "measurements/script_checks.json": {k: r[k] for k in ("checks", "explanation_start_s", "hook_is_opening",
                                                                                 "hook_repeated_mid", "rhythm")},
                          # what the viewer will hear/see as the CTA, and where (no author reasoning)
                          "text/cta.json": public_cta(r["cta"]),
                          # the independent HOOK-stage verdict on this exact hook (frame 0 + line), not author reasoning
                          "measurements/hook_review.json": {"scores": (hook.get("review") or {}).get("scores", {}),
                                                            "verdict": (hook.get("review") or {}).get("verdict")}}, "script variant")
        man = read_json(pk / "manifest.json"); man["candidate_id"] = v["variant_id"]; write_json(pk / "manifest.json", man)
        packets.append(str(pk))
    rv = subprocess.run([sys.executable, str(ROOT / "video-quality-assurance/scripts/reviewer.py"), "review-script", "--packets", *packets,
                         "--out", str(out_dir / "review")], capture_output=True, text=True)
    if rv.returncode != 0:
        sr.fail("SCRIPT.REVIEW_ERROR", (rv.stderr or rv.stdout)[-500:], fix=fix("SCRIPT", "retry"), retryable=True)
        return exit_for(sr.finalize(a.result))
    reviews = {r["candidate"]: r for r in read_json(out_dir / "review" / "script_reviews.json")["results"]}
    rows = []
    for v in vs:
        r, rw = res[v["variant_id"]], reviews[v["variant_id"]]
        hard = [c for c in r["checks"] if not c["passed"] and c["severity"] in ("blocking", "major")]
        rows.append({"variant_id": v["variant_id"], "structure": v["structure"], "estimated_s": r["estimate"]["total_s"],
                     "rhythm": r["rhythm"], "checks": r["checks"], "scores": {k: x["score"] for k, x in rw["scores"].items()},
                     "evidence": {k: x["evidence"] for k, x in rw["scores"].items()}, "review_failures": rw["failures"],
                     "verdict": "PASS" if rw["verdict"] == "PASS" and not hard else "FAIL"})
    passing = sorted([x for x in rows if x["verdict"] == "PASS"], key=lambda x: (-sum(x["scores"].values()), x["estimated_s"]))
    sel = passing[0] if passing else None
    write_json(out_dir / "script_variants.scored.json", {"selected": sel["variant_id"] if sel else None, "distinctness": info, "variants": rows})
    if sel:
        v = next(x for x in vs if x["variant_id"] == sel["variant_id"])
        script = {"video_id": d["video_id"], "language": d["language"], "hook_id": d["hook_id"], "variant_id": v["variant_id"],
                  "beats": v["beats"], "publish": v["publish"], **({"cta": v["cta"]} if v.get("cta") is not None else {})}
        write_json(a.out, script)
        sr.output(Path(a.out), "script", "application/json")
        ob = Path(a.hook).with_name("opening_brief.json")
        if ob.exists():  # the Visual Plan gets the final opening line, emphasis and timing
            b = read_json(ob)
            b["opening_beat"].update(spoken_line=v["beats"][0]["text"], emphasis_words=v["beats"][0].get("emphasis") or
                                     b["opening_beat"].get("emphasis_words", []), on_screen_text=v["beats"][0].get("on_screen") or
                                     b["opening_beat"]["on_screen_text"], estimated_hook_s=res[v["variant_id"]]["estimate"]["hook_s"],
                                     visual_intent=v["beats"][0].get("visual_intent", ""))
            write_json(ob, b)
    why = [{"variant": x["variant_id"], "reasons": [f"{c['id']}: {c['evidence']}" for c in x["checks"] if not c["passed"] and c["severity"] != "minor"]
            + [f"{f.get('id')} {f.get('score', '')}" for f in x["review_failures"]]} for x in rows if x["verdict"] != "PASS"]
    sr.check("SCRIPT.SELECTED", sel is not None, "blocking", f"selected {sel['variant_id']} {sel['scores']}" if sel else
             f"no variant passes: {why}", fix=None if sel else fix("SCRIPT", "regenerate", failed=why))
    L = ["# Script variants", "", f"selected: **{sel['variant_id'] if sel else 'none'}** · distinct: {ok} {info}", "",
         "| variant | structure | est s | clarity | pacing | payoff | hook | verdict |", "|---|---|---|---|---|---|---|---|"]
    for x in rows:
        s = x["scores"]
        L.append(f"| {x['variant_id']} | {x['structure']} | {x['estimated_s']} | {s.get('message_clarity')} | {s.get('pacing_retention')} | "
                 f"{s.get('payoff_coherence')} | {s.get('hook_strength')} | {x['verdict']} |")
    (out_dir / "script_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    sr.metric("selected", sel["variant_id"] if sel else None); sr.metric("variants", {x["variant_id"]: x["scores"] for x in rows})
    sr.metric("est_duration_s", sel["estimated_s"] if sel else None)
    r_ = sr.finalize(a.result)
    emit(r_)
    return exit_for(r_)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    s.add_argument("--variants", required=True); s.add_argument("--hook", required=True); s.add_argument("--dossier")
    s.add_argument("--out", required=True); s.add_argument("--result", required=True)
    s.add_argument("--min-s", type=float, default=20); s.add_argument("--max-s", type=float, default=45)
    s.add_argument("--voice", default="am_michael"); s.add_argument("--speed", type=float, default=1.0)
    s.add_argument("--attempt", type=int, default=1)
    s.add_argument("--cta-history", help="cta_history.json of earlier packaged videos (CTA.NOT_REPEATED)")
    s.add_argument("--require-cta-decision", action="store_true", help="every variant must carry a cta object (new runs)")
    a = ap.parse_args()
    return cmd_select(a)


if __name__ == "__main__":
    sys.exit(main())
