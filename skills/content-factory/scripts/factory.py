#!/usr/bin/env python3
"""content-factory orchestrator — run state, stage routing, gate bookkeeping and regeneration.

  factory.py init    --topic "..." --count 5 [--languages en,it] [--platforms youtube_shorts,tiktok,instagram_reels]
                     [--min-s 20 --max-s 45] [--voices en=af_heart,it=if_sara] [--music procedural]
                     [--caption-style karaoke] [--db factory.db] [--runs-dir DIR]
  factory.py next    --run RUN               # the single next action: stage, video, skill to load, files to write, gate
  factory.py record  --run RUN --result PATH # register a stage envelope → proceed | review | rerun(+params) | escalate
  factory.py media   --run RUN --video v01   # AUDIO→VIDEO→SUBTITLES→QA(check) with automatic regeneration
  factory.py package --run RUN [--video v01 ...] [--zip]
  factory.py status  --run RUN

State lives in RUN/state.json; every stage writes a cf stage_result envelope (see references/orchestration-spec.md).
A failed gate is never propagated: `record` routes the earliest fix_route, marks downstream stages stale, and
re-runs within the retry budget, otherwise escalates with the structured errors.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import (GLOBAL_STAGES, SCHEMAS, STAGE_OWNER, STAGES, VIDEO_STAGES, StageResult, fix, now_iso,  # noqa: E402
                       read_json, skill_script, skills_root, slug, validate, write_json)

PY = sys.executable
PASSED = {"passed", "passed_with_warnings"}
DONE = PASSED | {"skipped"}
MEDIA = ["AUDIO", "VIDEO", "SUBTITLES", "QA"]
MAX_ATTEMPTS = {"RESEARCH": 3, "IDEATION": 3, "SELECTION": 2, "HOOK": 3, "SCRIPT": 3, "LOCALIZE": 3,
                "VISUAL_PLAN": 3, "AUDIO": 3, "VIDEO": 3, "SUBTITLES": 3, "QA": 3, "PACKAGE": 3}
MAX_REGEN_PER_VIDEO = 8
DEFAULT_VOICES = {"en": "af_heart", "it": "if_sara", "es": "ef_dora", "fr": "ff_siwis", "pt": "pf_dora", "hi": "hf_alpha",
                  "ja": "jf_alpha", "zh": "zf_xiaoxiao"}   # must match tts.py LANG defaults (estimator uses the same voice)
DETERMINISTIC = {"AUDIO", "VIDEO", "SUBTITLES"}   # same inputs + same parameters → same output (TTS cache, seeded render)


def S(skill: str, script: str) -> str:
    return str(skill_script(skill, script))


def vp(run, vid: str) -> dict:
    run = Path(run)
    v = run / "videos" / vid
    d = {"dir": v, "hooks": v / "hook" / "hooks.json", "hooks_scored": v / "hook" / "hooks.scored.json",
         "script": v / "script" / "script.json", "storyboard": v / "visual" / "storyboard.json", "visual": v / "visual",
         "rendered": v / "visual" / "storyboard.rendered.json", "audio": v / "audio", "timing": v / "audio" / "timing.json",
         "voice": v / "audio" / "voice.wav", "video": v / "video", "timed": v / "video" / "storyboard.timed.json",
         "nosubs": v / "video" / "video_nosubs.mp4", "subs": v / "subtitles", "final": v / "subtitles" / "final.mp4",
         "ass": v / "subtitles" / "captions.ass", "qa": v / "qa", "review": v / "qa" / "review.json"}
    d["result"] = {"HOOK": v / "hook" / "result.json", "SCRIPT": v / "script" / "result.json",
                   "LOCALIZE": v / "localize" / "result.json", "VISUAL_PLAN": v / "visual" / "result.json",
                   "AUDIO": v / "audio" / "result.json", "VIDEO": v / "video" / "result.json",
                   "SUBTITLES": v / "subtitles" / "result.json", "QA": v / "qa" / "result.json",
                   "PACKAGE": run / "package" / vid / "result.json"}
    return d


GLOBAL_RESULT = {"RESEARCH": ("research", "result.json"), "IDEATION": ("ideation", "result.json"),
                 "SELECTION": ("selection", "result.json")}


def result_path(run: Path, stage: str, vid: str | None) -> Path:
    return run.joinpath(*GLOBAL_RESULT[stage]) if stage in GLOBAL_STAGES else vp(run, vid)["result"][stage]


def load(run: Path) -> dict:
    return read_json(run / "state.json")


def save(run: Path, st: dict) -> None:
    write_json(run / "state.json", st)


def entry(st: dict, stage: str, vid: str | None) -> dict:
    return st["global"][stage] if stage in GLOBAL_STAGES else st["videos"][vid]["stages"][stage]


# ----------------------------------------------------------------------------- gate commands
def gate_cmd(run: Path, st: dict, stage: str, vid: str | None) -> list:
    b, n = st["brief"], st["brief"]["count"]
    r = run
    if stage == "RESEARCH":
        return [PY, S("content-research", "dossier_tool.py"), "validate", "--dossier", r / "research" / "dossier.json",
                "--min-facts", max(5, 2 * n), "--result", r / "research" / "result.json"]
    if stage == "IDEATION":
        return [PY, S("content-strategy", "select_ideas.py"), "validate", "--ideas", r / "ideation" / "ideas.json",
                "--count", n, "--dossier", r / "research" / "dossier.json", "--result", r / "ideation" / "result.json"]
    if stage == "SELECTION":
        cmd = [PY, S("content-strategy", "select_ideas.py"), "select", "--ideas", r / "ideation" / "ideas.json", "--count", n,
               "--caps", r / "capabilities.json", "--out", r / "selection" / "selection.json", "--result", r / "selection" / "result.json"]
        for flag, p in (("--history", r / "history.json"), ("--trends", r / "research" / "trends.json"), ("--weights", r / "weights.json")):
            if p.exists():
                cmd += [flag, p]
        return cmd
    p, v = vp(r, vid), st["videos"][vid]
    v2 = b.get("hook_engine", "v1") == "v2"          # Phase 2 hook + script engines (new runs); v1 lint for older runs
    voice = b.get("voices", {}).get(v["language"]) or DEFAULT_VOICES.get(v["language"].split("-")[0], "af_heart")
    att = str(entry(st, stage, vid).get("attempt", 1))
    if stage == "HOOK" and v2:
        return [PY, S("hook-engineering", "hook_engine.py"), "select", "--hooks", p["hooks"], "--dossier", r / "research" / "dossier.json",
                "--out-dir", p["dir"] / "hook", "--result", p["result"]["HOOK"], "--voice", voice, "--attempt", att]
    if stage == "SCRIPT" and v2:
        return [PY, S("short-form-script", "script_select.py"), "select", "--variants", p["script"].with_name("script_variants.json"),
                "--hook", p["dir"] / "hook" / "selected_hook.json", "--dossier", r / "research" / "dossier.json", "--out", p["script"],
                "--result", p["result"]["SCRIPT"], "--min-s", b["min_s"], "--max-s", b["max_s"], "--voice", voice, "--attempt", att] + \
            (["--require-cta-decision"] if b.get("cta_engine") else []) + \
            (["--cta-history", r.parent / "cta_history.json"] if (r.parent / "cta_history.json").exists() else [])
    if stage == "HOOK":
        cmd = [PY, S("hook-engineering", "hook_lint.py"), "--hooks", p["hooks"], "--result", p["result"]["HOOK"]]
        return cmd + (["--weights", r / "weights.json"] if (r / "weights.json").exists() else [])
    if stage == "SCRIPT":
        return [PY, S("short-form-script", "script_lint.py"), "--script", p["script"], "--dossier", r / "research" / "dossier.json",
                "--hooks", p["hooks_scored"], "--min-s", b["min_s"], "--max-s", b["max_s"], "--result", p["result"]["SCRIPT"]]
    if stage == "LOCALIZE":
        return [PY, S("multilingual-content", "ml_check.py"), "--source", vp(r, v["source"])["script"], "--target", p["script"],
                "--caps", r / "capabilities.json", "--min-s", b["min_s"], "--max-s", b["max_s"], "--result", p["result"]["LOCALIZE"]]
    if stage == "VISUAL_PLAN":
        cmd = [PY, S("visual-storyboarding", "storyboard_tool.py"), "render", "--storyboard", p["storyboard"], "--script",
               p["script"], "--out-dir", p["visual"], "--result", p["result"]["VISUAL_PLAN"], "--auto-fallback"]
        ob = p["dir"] / "hook" / "opening_brief.json"
        return cmd + (["--timing", p["timing"]] if p["timing"].exists() else []) + (["--opening", ob] if ob.exists() else [])
    if stage == "PACKAGE":
        return [PY, str(Path(__file__).with_name("package_run.py")), "--run", r, "--video", vid]
    raise ValueError(stage)


WRITES = {"RESEARCH": ["research/dossier.json", "optional: research/signals.json → trend_score.py → research/trends.json"],
          "IDEATION": ["ideation/ideas.json"], "SELECTION": [],
          "HOOK": ["videos/{v}/hook/hooks.json (v2: contract hook_candidates — ≥5 different hooks, each with a frame-0 doodle "
                   "SVG under videos/{v}/hook/svg/; hook-engineering/SKILL.md)"],
          "SCRIPT": ["videos/{v}/script/script_variants.json (v2: two complete, structurally different variants opening with "
                     "videos/{v}/hook/selected_hook.json; the gate writes script.json)"], "LOCALIZE": ["videos/{v}/script/script.json (translated from source)"],
          "VISUAL_PLAN": ["videos/{v}/visual/storyboard.json",
                          "videos/{v}/visual/svg/*.svg (doodle scenes: visual-storyboarding/references/doodle-scene-guide.md)"],
          "PACKAGE": []}
WRITES_PACKAGE_V1 = ["videos/{v}/package/package_candidates.json (Phase 4: contract package_candidates — ≥3 complete, genuinely "
                     "different packages: title + opening promise + 1080x1920 doodle thumbnail SVG under videos/{v}/package/svg/ + "
                     "description + hashtags + claim_ids; content-factory/references/packaging.md)"]


def task(run: Path, st: dict, stage: str, vid: str | None) -> dict:
    e = entry(st, stage, vid)
    skill = STAGE_OWNER[stage]
    gate = [str(x) for x in gate_cmd(run, st, stage, vid)] + ["--attempt", str(e.get("attempt", 0) + 1)]
    return {"action": "do_stage", "stage": stage, "video_id": vid, "skill": skill,
            "skill_md": str(skills_root() / skill / "SKILL.md"), "attempt": e.get("attempt", 0) + 1,
            "fix_params": e.get("fix_params"), "source_video": (st["videos"].get(vid) or {}).get("source") if vid else None,
            "write": [str(run / w.format(v=vid)) for w in (WRITES_PACKAGE_V1 if stage == "PACKAGE" and st["brief"].get("package_engine")
                                                             else WRITES[stage])], "gate": gate,
            "brief_hint": ({"visual_style": st["brief"].get("visual_style", "doodle"),
                            "opening_brief": str(vp(run, vid)["dir"] / "hook" / "opening_brief.json")} if stage == "VISUAL_PLAN"
                           else {"selected_hook": str(vp(run, vid)["dir"] / "hook" / "selected_hook.json"),
                                 "estimate": f"python {S('voice-production', 'estimate.py')} script --script <variant.json>"}
                           if stage == "SCRIPT" else None),
            "then": [PY, str(Path(__file__).resolve()), "record", "--run", str(run), "--result", str(result_path(run, stage, vid))]}


def review_decision(run: Path, vid: str) -> dict:
    p = vp(run, vid)
    st = load(run)
    if review_backend(st) in ("subagent", "human"):
        build, review, final = review_cmds(run, st, vid)
        return {"action": "review", "video_id": vid, "skill": "video-quality-assurance", "independent": True,
                "steps": ["run `build` (packet)", "run `review` → writes review_request.md",
                          "hand ONLY the packet folder to a fresh reviewer (new Claude Code agent or a human); they write judgment.json",
                          "run `review` again (merges the judgment)", "run `finalize`", "run `then_record`"],
                "build": [str(x) for x in build], "review": [str(x) for x in review], "finalize": [str(x) for x in final],
                "then_record": [PY, str(Path(__file__).resolve()), "record", "--run", str(run), "--result", str(p["result"]["QA"])]}
    return {"action": "review", "video_id": vid, "skill": "video-quality-assurance",
            "view_images": [str(p["qa"] / "contact_sheet.jpg"), str(p["qa"] / "hook.jpg")],
            "template": str(p["qa"] / "review_template.json"), "write": str(p["review"]),
            "then": [PY, S("video-quality-assurance", "qa_video.py"), "finalize", "--out-dir", str(p["qa"]), "--review",
                     str(p["review"]), "--result", str(p["result"]["QA"])],
            "then_record": [PY, str(Path(__file__).resolve()), "record", "--run", str(run), "--result", str(p["result"]["QA"])]}


def next_action(run: Path, st: dict) -> dict:
    if st.get("status") == "escalated":
        return {"action": "escalated", "events": st["events"][-3:]}
    for stg in GLOBAL_STAGES:
        if st["global"][stg]["status"] not in DONE:
            return task(run, st, stg, None)
    for vid, v in st["videos"].items():
        if v.get("status") == "escalated":
            continue
        for stg in VIDEO_STAGES:
            e = v["stages"][stg]
            if e["status"] in DONE:
                continue
            if stg in MEDIA:
                if e["status"] == "pending_review":
                    return review_decision(run, vid)
                return {"action": "run_media", "video_id": vid,
                        "cmd": [PY, str(Path(__file__).resolve()), "media", "--run", str(run), "--video", vid]}
            return task(run, st, stg, vid)
    return {"action": "done", "escalated": [k for k, v in st["videos"].items() if v.get("status") == "escalated"],
            "package_dir": str(run / "package")}


# ----------------------------------------------------------------------------- recording + regeneration
def unit(lang: str, source: str | None, idea: str) -> dict:
    stages = {s: {"status": "pending", "attempt": 0} for s in VIDEO_STAGES}
    for s in (("HOOK", "SCRIPT", "VISUAL_PLAN") if source else ("LOCALIZE",)):
        stages[s]["status"] = "skipped"
    return {"language": lang, "source": source, "idea_id": idea, "status": "in_progress", "regenerations": 0, "stages": stages}


def create_units(run: Path, st: dict) -> None:
    langs = st["brief"]["languages"]
    for s in read_json(run / "selection" / "selection.json")["selected"]:
        st["videos"].setdefault(s["video_id"], unit(langs[0], None, s["idea_id"]))
        for lang in langs[1:]:
            st["videos"].setdefault(f"{s['video_id']}-{lang}", unit(lang, s["video_id"], s["idea_id"]))


def escalate(st: dict, res: dict, why: str) -> dict:
    vid = res.get("video_id")
    d = {"action": "escalate", "stage": res["stage"], "video_id": vid, "why": why,
         "errors": [{k: x.get(k) for k in ("code", "severity", "message", "fix_route")} for x in res["errors"]]}
    if vid:
        st["videos"][vid]["status"] = "escalated"
    else:
        st["status"] = "escalated"
    st["events"].append({"ts": now_iso(), "stage": "REGENERATION", "video_id": vid, "decision": d})
    return d


def route(run: Path, st: dict, res: dict) -> dict:
    stage, vid = res["stage"], res.get("video_id")
    cands = [x for x in res["errors"] if x["severity"] in ("blocking", "major")] or res["errors"]
    routed = [x for x in cands if x.get("fix_route")]
    if routed:
        x = min(routed, key=lambda x: STAGES.index(x["fix_route"]["stage"]))
        target, action, params = x["fix_route"]["stage"], x["fix_route"]["action"], dict(x["fix_route"].get("params") or {})
    elif res["status"] == "error" or any(x.get("retryable") for x in cands):
        target, action, params = stage, "retry", {}
    else:
        return escalate(st, res, "no automatic fix route; human decision needed")
    if target == "VISUAL_PLAN" and action == "retime":  # deterministic: re-cut shots during VIDEO
        target, params = "VIDEO", {"max_shot": params.get("max_shot", 3.0)}
    if target == "QA" and action == "complete_review":
        st["videos"][vid]["stages"]["QA"]["status"] = "pending_review"
        return review_decision(run, vid)
    in_global = target in GLOBAL_STAGES
    scope = st["global"] if in_global else st["videos"][vid]["stages"]
    order = GLOBAL_STAGES if in_global else VIDEO_STAGES
    te = scope[target]
    if target == stage and target in DETERMINISTIC and not any(x["code"].startswith("INTERNAL.") for x in cands):
        old = {k: v for k, v in (te.get("fix_params") or {}).items() if k != "action"}
        new = {k: v for k, v in {**old, **params}.items() if k != "action"}
        if old == new:  # same stage, same inputs, same parameters: a deterministic rerun reproduces the failure
            d = escalate(st, res, f"REGEN.FUTILE_RETRY: {target} is deterministic and the route would rerun it with "
                                  f"identical inputs and parameters {new}; it cannot change {[x['code'] for x in cands]}. "
                                  f"Fix the cause (code, upstream artifact or parameters) and reset.")
            d["futile_retry"] = True
            return d
    regen = st.get("global_regenerations", 0) if in_global else st["videos"][vid].get("regenerations", 0)
    if te.get("attempt", 0) >= MAX_ATTEMPTS.get(target, 3) or regen >= MAX_REGEN_PER_VIDEO:
        return escalate(st, res, f"retry budget exhausted for {target} (attempts={te.get('attempt', 0)}, regenerations={regen})")
    te["status"] = "pending"
    te["fix_params"] = {**te.get("fix_params", {}), **params, "action": action}
    for later in order[order.index(target) + 1:]:
        if scope[later]["status"] != "skipped":
            scope[later]["status"] = "stale"
    if in_global:
        st["global_regenerations"] = regen + 1
    else:
        st["videos"][vid]["regenerations"] = regen + 1
    d = {"action": "rerun", "stage": target, "video_id": None if in_global else vid, "fix_action": action,
         "params": params, "because": [x["code"] for x in cands], "skill": STAGE_OWNER[target],
         "skill_md": str(skills_root() / STAGE_OWNER[target] / "SKILL.md")}
    st["events"].append({"ts": now_iso(), "stage": "REGENERATION", "video_id": vid, "decision": d})
    return d


def issue(st: dict, d: dict) -> dict:
    """Log that a task/review was handed out, so record() can measure the stage's real wall-clock time."""
    if d.get("action") in ("do_stage", "review"):
        st["events"].append({"ts": now_iso(), "t": time.time(), "issued": d["action"],
                             "stage": d.get("stage", "QA"), "video_id": d.get("video_id")})
    return d


def _since_issue(st: dict, stage: str, vid: str | None) -> float | None:
    """Seconds since the FIRST time this stage was handed out after its previous record (re-issuing does not reset)."""
    first = None
    for e in reversed(st["events"]):
        if e.get("stage") != stage or e.get("video_id") != vid:
            continue
        if e.get("issued"):
            first = e["t"]
        elif "status" in e:
            break
    return round(time.time() - first, 2) if first else None


def _gate_seconds(res: dict) -> float | None:
    try:
        return round((dt.datetime.fromisoformat(res["finished_at"]) - dt.datetime.fromisoformat(res["started_at"])).total_seconds(), 1)
    except (KeyError, TypeError, ValueError):
        return None


def record(run: Path, st: dict, result: Path, wall_s: float | None = None) -> dict:
    res = read_json(result)
    vid0, stage0 = res.get("video_id"), res.get("stage")
    if stage0 in VIDEO_STAGES and vid0 in st.get("videos", {}):
        blocking = [s for s in VIDEO_STAGES[: VIDEO_STAGES.index(stage0)] if st["videos"][vid0]["stages"][s]["status"] not in DONE]
        if blocking:   # Phase 3 finding: an out-of-order record silently corrupted state
            raise SystemExit(f"OUT_OF_ORDER: refusing to record {stage0} for {vid0} while {blocking} are not done")
    errs = validate(res, SCHEMAS["stage_result"])
    if errs:
        raise SystemExit(f"invalid stage envelope {result}: {errs[:3]}")
    stage, vid = res["stage"], res.get("video_id")
    ev = {"ts": now_iso(), "stage": stage, "video_id": vid, "skill": res["skill"], "status": res["status"],
          "attempt": res.get("attempt"), "result": str(result),
          "wall_s": wall_s if wall_s is not None else _since_issue(st, stage, vid),
          "gate_s": _gate_seconds(res), "failed": [x["code"] for x in res["errors"] if x["severity"] in ("blocking", "major")],
          "warnings": [x["code"] for x in res["errors"] if x["severity"] == "minor"]}
    tc = res.get("metrics", {}).get("tts_cache")
    if tc:
        ev["tts_cache"] = {k: tc[k] for k in ("hits", "misses", "rejected_entries", "sentences") if k in tc}
    if res["skill"] in ("trend-intelligence", "asset-provenance"):  # advisory envelopes; owners record elsewhere
        st["events"].append({**ev, "advisory": True})
        return {"action": "proceed", "advisory": True, "stage": stage}
    e = entry(st, stage, vid)
    e.update(status=res["status"], attempt=max(e.get("attempt", 0), res.get("attempt", 1)), result=str(result))
    st["events"].append(ev)
    if res["status"] in PASSED:
        e.pop("fix_params", None)
        if stage == "SELECTION":
            create_units(run, st)
        if vid and stage == "PACKAGE":
            st["videos"][vid]["status"] = "packaged"
        return {"action": "proceed", "stage": stage, "video_id": vid}
    if res["status"] == "pending_review":
        return review_decision(run, vid)
    return route(run, st, res)


# ----------------------------------------------------------------------------- media chain
def media_cmds(run: Path, st: dict, stage: str, vid: str) -> list[list]:
    b, v, p = st["brief"], st["videos"][vid], vp(run, vid)
    e = v["stages"][stage]
    fp, att = e.get("fix_params") or {}, str(e.get("attempt", 0) + 1)
    if stage == "AUDIO":
        cmd = [PY, S("voice-production", "tts.py"), "synth", "--script", p["script"], "--out-dir", p["audio"], "--result",
               p["result"]["AUDIO"], "--min-s", b["min_s"], "--max-s", b["max_s"], "--attempt", att]
        voice = fp.get("voice") or b.get("voices", {}).get(v["language"])
        cmd += ["--voice", voice] if voice else []
        for k, flag in (("speed", "--speed"), ("lead_s", "--lead-s"), ("sentence_gap", "--sentence-gap"),
                        ("beat_gap", "--beat-gap"), ("backend", "--backend")):
            if k in fp:
                cmd += [flag, fp[k]]
        return [cmd]
    if stage == "VIDEO":
        rendered = p["rendered"] if p["rendered"].exists() else vp(run, v["source"])["rendered"]
        return [[PY, S("visual-storyboarding", "storyboard_tool.py"), "retime", "--storyboard", rendered, "--timing", p["timing"],
                 "--out", p["timed"], "--max-shot", fp.get("max_shot", 3.6)],
                [PY, S("video-production", "render_video.py"), "--storyboard", p["timed"], "--voice", p["voice"], "--script", p["script"],
                 *(["--cta-history", run.parent / "cta_history.json"] if (run.parent / "cta_history.json").exists() else []),
                 "--timing", p["timing"], "--out-dir", p["video"], "--result", p["result"]["VIDEO"], "--music", b.get("music", "procedural"),
                 "--lufs", fp.get("lufs", -14), "--attempt", att]
                + [x for k, flag in (("music_under_voice_db", "--music-under-voice-db"), ("music_carve_db", "--music-carve-db"),
                                     ("sfx_max_rate", "--sfx-max-rate"), ("music_gain_db", "--music-gain-db")) if k in fp
                   for x in (flag, fp[k])]]   # fix-route audio parameters reach the renderer
    if stage == "SUBTITLES":
        cmd = [PY, S("subtitle-production", "subtitles.py"), "run", "--timing", p["timing"], "--video", p["nosubs"], "--out-dir",
               p["subs"], "--result", p["result"]["SUBTITLES"], "--overlays", p["timed"], "--style",
               b.get("caption_style", "auto"), "--attempt", att]
        for k, flag in (("font_scale", "--font-scale"), ("max_words", "--max-words"), ("font", "--font"), ("y", "--y")):
            if k in fp:
                cmd += [flag, fp[k]]
        return [cmd]
    return [[PY, S("video-quality-assurance", "qa_video.py"), "check", "--video", p["final"], "--timing", p["timing"],
             "--captions", p["ass"], "--nosubs", p["nosubs"], "--out-dir", p["qa"], "--result", p["result"]["QA"],
             "--min-s", b["min_s"], "--max-s", b["max_s"], "--attempt", att]]


def review_backend(st: dict) -> str:
    b = st["brief"].get("review_backend", "auto")
    if b == "auto":
        return "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "heuristic"
    return b


def review_cmds(run: Path, st: dict, vid: str) -> list[list]:
    """Authoring → review boundary: build the packet from finished artifacts, run the reviewer as its own process,
    then fold its report into the QA envelope."""
    b, p = st["brief"], vp(run, vid)
    v = st["videos"][vid]
    pkt, rv = p["qa"] / "review_packet", p["qa"] / "independent_review"
    script = p["script"] if p["script"].exists() else vp(run, v["source"])["script"]
    build = [PY, S("video-quality-assurance", "review_packet.py"), "build", "--final", p["final"], "--timing", p["timing"],
             "--captions", p["ass"], "--publish", script, "--out", pkt, "--min-s", b["min_s"], "--max-s", b["max_s"],
             "--measure", f"qa_report={p['qa'] / 'qa_report.json'}", "--measure", f"subtitles_result={p['result']['SUBTITLES']}"]
    for name, path in (("visual_audit", p["video"] / "work" / "visual_audit.json"), ("mix_report", p["video"] / "work" / "mix_report.json"),
                       ("cta_report", p["video"] / "work" / "cta_report.json")):
        if path.exists():
            build += ["--measure", f"{name}={path}"]
    if (run / "research" / "dossier.json").exists():
        build += ["--dossier", run / "research" / "dossier.json"]
    review = [PY, S("video-quality-assurance", "reviewer.py"), "review", "--packet", pkt, "--out", rv, "--backend", review_backend(st)]
    final = [PY, S("video-quality-assurance", "qa_video.py"), "finalize", "--out-dir", p["qa"], "--independent",
             rv / "review_report.json", "--result", p["result"]["QA"]]
    return [build, review, final]


def run_review(run: Path, st: dict, vid: str) -> dict:
    """Run the three review commands; returns {"status": done|awaiting|error, ...} and logs the boundary."""
    p = vp(run, vid)
    cmds = review_cmds(run, st, vid)
    out = {}
    for i, cmd in enumerate(cmds):
        r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
        print(f"[REVIEW] {Path(str(cmd[1])).name} exit={r.returncode} {r.stdout.strip()[-300:]}", file=sys.stderr)
        if i == 1 and r.returncode == 3:
            return {"status": "awaiting", "request": str(p["qa"] / "independent_review" / "review_request.md")}
        if i < 2 and r.returncode not in (0, 2):
            return {"status": "error", "step": Path(str(cmd[1])).name, "stderr": (r.stderr or r.stdout)[-400:]}
    log = p["qa"] / "independent_review" / "boundary_log.json"
    if log.exists():
        b = read_json(log)
        st["events"].append({"ts": now_iso(), "stage": "QA", "video_id": vid, "boundary": "independent_review",
                             "reviewer_pid": b["process"]["pid"], "judge": b["judge"], "packet_manifest_sha256": b["manifest_sha256"],
                             "files_read": len(b["files_read"]), "authoring_modules_loaded": b["authoring_modules_loaded"]})
    return {"status": "done"}


def cmd_media(a) -> int:
    run = Path(a.run).resolve()
    budget = getattr(a, "steps", None) or 14     # --steps N: process at most N media steps, then return (resumable)
    for _ in range(budget):
        st = load(run)
        v = st["videos"][a.video]
        if v.get("status") == "escalated":
            print(json.dumps({"action": "escalated", "video_id": a.video}))
            return 2
        todo = next((s for s in VIDEO_STAGES if v["stages"][s]["status"] not in DONE), None)
        if todo is None or todo not in MEDIA:
            nxt = next_action(run, st)
            print(json.dumps({"action": "media_done" if todo is None else "media_paused", "video_id": a.video,
                              "waiting_for": todo, "next": nxt["action"], "next_stage": nxt.get("stage")}))
            return 0
        if v["stages"][todo]["status"] == "pending_review":
            if review_backend(st) in ("heuristic", "anthropic"):
                t0 = time.time()
                rr = run_review(run, st, a.video)
                if rr["status"] == "error":
                    sr = StageResult("QA", "content-factory", a.video, attempt=v["stages"]["QA"].get("attempt", 1))
                    sr.fail("REV.REVIEWER_ERROR", f"{rr['step']}: {rr['stderr']}", fix=fix("QA", "retry"), retryable=True)
                    sr.finalize(vp(run, a.video)["result"]["QA"])
                decision = record(run, st, vp(run, a.video)["result"]["QA"], wall_s=round(time.time() - t0, 2))
                save(run, st)
                print(json.dumps({k: decision.get(k) for k in ("action", "stage", "fix_action", "params", "because")}), file=sys.stderr)
                if decision["action"] == "proceed" or (decision["action"] == "rerun" and decision["stage"] in MEDIA):
                    continue
                print(json.dumps(decision, indent=1))
                return 2
            print(json.dumps(issue(st, review_decision(run, a.video)), indent=1))
            save(run, st)
            return 3
        res_path = vp(run, a.video)["result"][todo]
        t0 = time.time()
        for i, cmd in enumerate(media_cmds(run, st, todo, a.video)):
            p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
            print(f"[{todo}] {Path(str(cmd[1])).name} exit={p.returncode} {p.stdout.strip()[-600:]}", file=sys.stderr)
            if p.returncode != 0 and i == 0 and todo == "VIDEO":  # retime failed → storyboard/beat mismatch
                sr = StageResult("VIDEO", "content-factory", a.video, attempt=v["stages"]["VIDEO"].get("attempt", 0) + 1)
                sr.fail("VID.RETIME_FAILED", (p.stderr or p.stdout)[-400:], fix=fix("VISUAL_PLAN", "remap_beats"), retryable=True)
                sr.finalize(res_path)
                break
        decision = record(run, st, res_path, wall_s=round(time.time() - t0, 2))
        auto_review = decision.get("action") == "review" and review_backend(st) in ("heuristic", "anthropic")
        if decision.get("action") == "review" and not auto_review:
            issue(st, decision)
        save(run, st)
        if auto_review:            # an automatic independent reviewer takes over in the next loop iteration
            continue
        print(json.dumps({k: decision.get(k) for k in ("action", "stage", "fix_action", "params", "because")}), file=sys.stderr)
        if decision["action"] == "proceed" or (decision["action"] == "rerun" and decision["stage"] in MEDIA):
            continue
        print(json.dumps(decision, indent=1))
        return 3 if decision["action"] == "review" else 2
    if getattr(a, "steps", None):
        print(json.dumps({"action": "media_step_limit", "video_id": a.video, "next": next_action(run, load(run))["action"]}))
        return 0
    return 2


# ----------------------------------------------------------------------------- commands
def cmd_init(a) -> int:
    runs = Path(a.runs_dir).resolve()
    rid = f"{dt.date.today().isoformat()}-{slug(a.topic, 32)}"
    run, k = runs / rid, 1
    while run.exists():
        k += 1
        run = runs / f"{rid}-{k}"
    brief = {"run_id": run.name, "topic": a.topic, "count": a.count, "languages": a.languages.split(","),
             "platforms": a.platforms.split(","), "duration_s": {"min": a.min_s, "max": a.max_s}, "min_s": a.min_s,
             "max_s": a.max_s, "voices": dict(x.split("=", 1) for x in a.voices.split(",") if "=" in x) if a.voices else {},
             "music": a.music, "caption_style": a.caption_style, "visual_style": a.visual_style,
             "review_backend": a.review_backend, "hook_engine": "v2", "cta_engine": "v1", "package_engine": "v1",
             "audience": a.audience, "tone": a.tone,
             "constraints": a.constraint or [], "created_at": now_iso()}
    errs = validate(brief, SCHEMAS["brief"])
    if errs:
        print(json.dumps({"error": "invalid brief", "details": errs}))
        return 2
    for d in ("research", "ideation", "selection", "videos", "package"):
        (run / d).mkdir(parents=True, exist_ok=True)
    write_json(run / "run.json", brief)
    st = {"run_id": run.name, "brief": brief, "status": "in_progress", "created_at": now_iso(),
          "global": {s: {"status": "pending", "attempt": 0} for s in GLOBAL_STAGES}, "videos": {}, "events": []}
    save(run, st)
    subprocess.run([PY, str(Path(__file__).with_name("doctor.py")), "--out", str(run / "capabilities.json")], capture_output=True)
    if a.db and Path(a.db).exists():
        db = S("content-database", "cfdb.py")
        subprocess.run([PY, db, "history", "--db", a.db, "--out", str(run / "history.json")], capture_output=True)
        subprocess.run([PY, db, "weights", "--db", a.db, "--out", str(run / "weights.json")], capture_output=True)
    print(json.dumps({"run": str(run), "next": next_action(run, st)}, indent=1))
    return 0


def cmd_status(a) -> int:
    run = Path(a.run).resolve()
    st = load(run)
    print(f"run {st['run_id']}  status={st.get('status')}  topic={st['brief']['topic']!r}")
    print("  global: " + "  ".join(f"{s}={st['global'][s]['status']}" for s in GLOBAL_STAGES))
    for vid, v in st["videos"].items():
        cells = "  ".join(f"{s}={v['stages'][s]['status']}({v['stages'][s].get('attempt', 0)})" for s in VIDEO_STAGES
                          if v["stages"][s]["status"] != "skipped")
        print(f"  {vid} [{v['language']}] {v.get('status')} regen={v.get('regenerations', 0)}: {cells}")
    return 0

def cmd_report(run: Path, out: str | None = None) -> int:
    """Numerical baseline of a run from its event log (attempt history survives result.json overwrites)."""
    st = load(run)
    out_dir = Path(out) if out else run / "report"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [e for e in st["events"] if "status" in e and not e.get("issued") and not e.get("advisory")]
    regen = [e["decision"] for e in st["events"] if e.get("stage") == "REGENERATION" and "decision" in e]
    order = GLOBAL_STAGES + VIDEO_STAGES
    stages = {}
    for e in rows:
        k = (e["stage"], e.get("video_id"))
        g = stages.setdefault(k, {"stage": e["stage"], "video_id": e.get("video_id"), "attempts": 0, "wall_s": 0.0,
                                  "gate_s": 0.0, "history": []})
        g["attempts"] += 1
        g["wall_s"] = round(g["wall_s"] + (e.get("wall_s") or 0), 2)
        g["gate_s"] = round(g["gate_s"] + (e.get("gate_s") or 0), 1)
        g["final_status"] = e["status"]
        g["history"].append({"attempt": e.get("attempt"), "status": e["status"], "failed": e.get("failed", []),
                             "warnings": e.get("warnings", []), "wall_s": e.get("wall_s")})
        if e.get("tts_cache"):
            g["tts_cache"] = e["tts_cache"]
        res = Path(e["result"])
        if res.exists():
            r = read_json(res)
            g["artifacts"] = [{"role": o["role"], "path": o["path"], "sha256": (o.get("sha256") or "")[:16]} for o in r.get("outputs", [])]
    table = sorted(stages.values(), key=lambda g: (g["video_id"] or "", order.index(g["stage"]) if g["stage"] in order else 99))
    for g in table:  # a retry = a recorded failure that sent the stage (or one upstream) round again
        g["records"] = g.pop("attempts")
        g["failures"] = sum(1 for h in g["history"] if h["status"] == "failed")
        g["retries"] = g["failures"]
    pkg = {}
    for vid in st["videos"]:
        d = run / "package" / vid
        if d.exists():
            pkg[vid] = {"dir": str(d), "files": sorted(f.name for f in d.iterdir() if f.is_file())}
    t_issue = [e["t"] for e in st["events"] if e.get("issued")]
    report = {"run_id": st["run_id"], "topic": st["brief"]["topic"], "status": st.get("status"),
              "videos": {k: {"status": v.get("status"), "regenerations": v.get("regenerations", 0)} for k, v in st["videos"].items()},
              "stages": table, "regenerations": regen, "packages": pkg,
              "totals": {"stage_wall_s": round(sum(g["wall_s"] for g in table), 1),
                         "retries": sum(g["retries"] for g in table), "regenerations": len(regen),
                         "human_resets": sum(1 for d in regen if d.get("action") == "human_reset"),
                         "escalations": sum(1 for d in regen if d.get("action") == "escalate"),
                         "first_issue_to_last_event_s": round((max(e.get("t", 0) for e in st["events"] if e.get("t")) or 0) -
                                                              min(t_issue), 1) if t_issue else None}}
    write_json(out_dir / "report.json", report)
    md = [f"# Run report — {st['run_id']}", "", f"Topic: {st['brief']['topic']}", "",
          "| stage | video | final | records | failures | wall s | gate s | failed (per attempt) | cache |", "|---|---|---|---|---|---|---|---|---|"]
    for g in table:
        fails = "; ".join(f"a{h['attempt']}: {','.join(h['failed']) or '—'}" for h in g["history"])
        cache = f"{g['tts_cache']['hits']} hit / {g['tts_cache']['misses']} miss" if g.get("tts_cache") else ""
        md.append(f"| {g['stage']} | {g['video_id'] or '—'} | {g['final_status']} | {g['records']} | {g['failures']} | {g['wall_s']} | {g['gate_s']} | {fails} | {cache} |")
    md += ["", f"Total stage wall time: {report['totals']['stage_wall_s']} s · failed attempts: {report['totals']['retries']} · "
           f"regenerations: {report['totals']['regenerations']} · escalations: {report['totals']['escalations']} · "
           f"human resets: {report['totals']['human_resets']}", ""]
    for vid, p_ in pkg.items():
        md.append(f"Package {vid}: {p_['dir']} ({', '.join(p_['files'])})")
    (out_dir / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(out_dir / "report.json"), "markdown": str(out_dir / "report.md"), "totals": report["totals"]}))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("--topic", required=True); i.add_argument("--count", type=int, default=5)
    i.add_argument("--languages", default="en"); i.add_argument("--platforms", default="youtube_shorts,tiktok,instagram_reels")
    i.add_argument("--min-s", type=float, default=20); i.add_argument("--max-s", type=float, default=45)
    i.add_argument("--voices"); i.add_argument("--music", default="procedural")
    i.add_argument("--caption-style", default="auto", choices=["auto", "doodle", "karaoke", "word", "clean"],
                   help="auto = doodle captions for doodle storyboards, karaoke otherwise")
    i.add_argument("--visual-style", default="doodle", choices=["doodle", "illustrated"],
                   help="doodle = animated hand-drawn scenes (v2 engine); illustrated = v1 stills with Ken Burns")
    i.add_argument("--review-backend", default="auto", choices=["auto", "heuristic", "anthropic", "subagent", "human"],
                   help="independent reviewer judge: auto = anthropic if ANTHROPIC_API_KEY else heuristic")
    i.add_argument("--audience", default="general"); i.add_argument("--tone", default="curious, clear, friendly")
    i.add_argument("--constraint", action="append"); i.add_argument("--db")
    i.add_argument("--runs-dir", default=os.environ.get("CF_RUNS_DIR", str(Path.home() / "content-factory" / "runs")))
    for name in ("next", "status"):
        s = sub.add_parser(name); s.add_argument("--run", required=True)
    r = sub.add_parser("record"); r.add_argument("--run", required=True); r.add_argument("--result", required=True)
    m = sub.add_parser("media"); m.add_argument("--run", required=True); m.add_argument("--video", required=True)
    m.add_argument("--steps", type=int, help="run at most N media stages (or one review) then return; call again to resume")
    z = sub.add_parser("reset", help="human override after an escalation: re-open a stage with a fresh retry budget")
    z.add_argument("--run", required=True); z.add_argument("--video"); z.add_argument("--stage", required=True, choices=STAGES)
    z.add_argument("--note", default="")
    rp = sub.add_parser("report", help="per-stage baseline: wall time, status, attempts, cache use, artifacts")
    rp.add_argument("--run", required=True); rp.add_argument("--out", help="default RUN/report")
    p = sub.add_parser("package"); p.add_argument("--run", required=True); p.add_argument("--video", action="append")
    p.add_argument("--zip", action="store_true")
    a = ap.parse_args()
    if a.cmd == "init":
        return cmd_init(a)
    if a.cmd == "status":
        return cmd_status(a)
    run = Path(a.run).resolve()
    if a.cmd == "next":
        st = load(run)
        d = issue(st, next_action(run, st))
        save(run, st)
        print(json.dumps(d, indent=1))
        return 0
    if a.cmd == "report":
        return cmd_report(run, a.out)
    if a.cmd == "record":
        st = load(run)
        d = record(run, st, Path(a.result).resolve())
        save(run, st)
        print(json.dumps(d, indent=1))
        return 0 if d["action"] in ("proceed", "review") else 2
    if a.cmd == "media":
        return cmd_media(a)
    if a.cmd == "reset":
        st = load(run)
        scope, order = (st["global"], GLOBAL_STAGES) if a.stage in GLOBAL_STAGES else (st["videos"][a.video]["stages"], VIDEO_STAGES)
        scope[a.stage].update(status="pending", attempt=0)
        scope[a.stage].pop("fix_params", None)
        for later in order[order.index(a.stage) + 1:]:
            if scope[later]["status"] != "skipped":
                scope[later]["status"] = "stale"
        if a.video:
            st["videos"][a.video].update(status="in_progress", regenerations=0)
        else:
            st["status"] = "in_progress"
        st["events"].append({"ts": now_iso(), "stage": "REGENERATION", "video_id": a.video,
                             "decision": {"action": "human_reset", "stage": a.stage, "note": a.note}})
        save(run, st)
        print(json.dumps(next_action(run, st), indent=1))
        return 0
    if a.cmd == "package":
        st = load(run)
        vids = a.video or [k for k, v in st["videos"].items() if v["stages"]["QA"]["status"] in PASSED]
        cmd = [PY, str(Path(__file__).with_name("package_run.py")), "--run", str(run)] + [x for v in vids for x in ("--video", v)]
        rc = subprocess.run(cmd + (["--zip"] if a.zip else [])).returncode
        for vid in vids:
            rp = vp(run, vid)["result"]["PACKAGE"]
            if rp.exists():
                print(json.dumps(record(run, st, rp)))
        save(run, st)
        return rc
    return 1


if __name__ == "__main__":
    sys.exit(main())
