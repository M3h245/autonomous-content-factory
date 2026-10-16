#!/usr/bin/env python3
"""experiment 1.2 - paired creative experiments on top of the Idea Engine / V3.0.1 (no LLM API key, no engine change).

  experiment.py plan     --spec input/experiments/<id>.json [--batches-dir batches]
  experiment.py prepare  --batch batches/<id> [--db factory.db]   one `factory.py init` per slot; manifest ONLY when all 6 are ready
  experiment.py ready    --batch batches/<id>                     preflight: every run exists with its assignment and rules
  experiment.py produce  --batch batches/<id> [--output-dir D:\\…]  refuses unless ready; idea_engine produce with the experiment driver
  experiment.py drive    --batch B --run R --slot N               (called per run by produce) phase A → gate → phase B
  experiment.py gate     --batch B --slot N [--measured]          the compliance check on one run (pre-audio: estimated timing);
                                                                  ok only when V3.0.1 itself recorded SCRIPT as passed
  experiment.py sync-gate --batch B --slot N                      record the gate for a run whose SCRIPT passed outside `drive`
                                                                  (e.g. after a human `factory.py reset`); runs nothing
  experiment.py check    --batch batches/<id>                     post-production check with real TTS timing (alignment verified)
  experiment.py link     --batch B [--snapshot data/analytics/latest.json] [--slot N --video-id X --published-at ISO]
  experiment.py observe  --batch B --snapshot data/analytics/latest.json   windows by the Analytics DATA CUTOFF
  experiment.py manual-template / manual --csv / report / status --batch B

Rules reach the operator twice: as `--constraint` in run.json and, binding, in the driver prompts (phase A stops before
AUDIO). Between the phases a deterministic gate checks the script; a non-compliant script is reset (HOOK or SCRIPT) and
rewritten, or the slot stops as `blocked` — phase B (audio onwards) never starts for it. After production `check`
re-verifies with the real word timing and flags any later change. Nothing is published; no metric is ever invented.
"""
from __future__ import annotations

import argparse, csv, datetime as dt, hashlib, json, os, re, shlex, shutil, statistics, subprocess, sys, types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import idea_engine as IE  # noqa: E402  (manifest format, hashing, memory, produce/deliver: reused, not copied)
import factory  # noqa: E402            (V3.0.1 state: load, PASSED, DONE, VIDEO_STAGES — read only)

SCHEMA = "cf-experiment/1"
VERSION = "1.2"
ROME, PACIFIC = "Europe/Rome", "America/Los_Angeles"
WINDOWS = {"24h": (18.0, 48.0), "72h": (60.0, 120.0)}
METRICS = ("views", "engaged_views", "stayed_to_watch", "average_view_duration_s", "average_view_percentage",
           "retention_4s", "retention_8s", "likes", "comments", "subscribers_gained")
EST_WPS, EST_GAP = 3.1, 0.3          # pre-audio timing estimate: channel's measured 2.9–3.4 words/s, ~0.3 s between beats
TREAT_START = (1.5, 7.0)             # the treatment beat must START here (s) — right after a ~1.8–2.9 s hook; it fills 3–9 s
TREAT_MIN_SHARE, TREAT_MIN_WORDS = 0.25, 2
OPENING_MIN_SHARE = 0.5
MAX_REPAIRS = 2
STOP = set("""a an the and or but so of to in on at by for with from into onto over under up down out off it its it's
is are was were be been being this that these those there here then than as if your you you're yours we our us they
their them he she his her i me my do does did not no yes can can't don't isn't aren't just very really what why how
when where which who whom whose all any some each every more most much many one two three about after before again
also only even still what's that's here's let's will would could should have has had get got""".split())


class ExpError(Exception):
    def __init__(self, msg: str, **extra):
        super().__init__(msg); self.extra = {"error": msg, **extra}


# ----------------------------------------------------------------------------- io
def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def write_json(p, obj) -> None:
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def append_jsonl(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n"); fh.flush(); os.fsync(fh.fileno())


def read_jsonl(p) -> list[dict]:
    p = Path(p)
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def sha_file(p) -> str | None:
    p = Path(p)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def exp_dir(batch) -> Path:
    return Path(batch) / "experiment"


# ----------------------------------------------------------------------------- spec + plan
REQUIRED_TOPIC = ("topic_key", "topic", "angle", "opening_line", "frame0_visual", "variant_beat_3_9", "claims")


def validate_spec(spec: dict) -> list[str]:
    errs = [f"missing '{k}'" for k in ("experiment_id", "week", "variable", "primary_metric", "pairs", "duration_s",
                                       "shared_rules", "arm_rules", "schedule") if k not in spec]
    if errs:
        return errs
    if not IE.ID_RE.match(spec["experiment_id"]):
        errs.append("experiment_id must match [A-Za-z0-9._-]{1,64}")
    if spec["primary_metric"] not in METRICS:
        errs.append(f"primary_metric must be one of {METRICS}")
    if not ({"control", "variant"} <= set(spec["arm_rules"])):
        errs.append("arm_rules needs 'control' and 'variant'")
    keys = set()
    for pi, p in enumerate(spec["pairs"]):
        if len(p.get("topics", [])) != 2:
            errs.append(f"pairs[{pi}] needs exactly 2 topics"); continue
        if not p.get("pair_id") or not p.get("match_rationale"):
            errs.append(f"pairs[{pi}] needs pair_id and match_rationale")
        for ti, t in enumerate(p["topics"]):
            errs += [f"pairs[{pi}].topics[{ti}] missing '{k}'" for k in REQUIRED_TOPIC if not t.get(k)]
            if t.get("topic_key") in keys:
                errs.append(f"duplicate topic_key {t.get('topic_key')}")
            keys.add(t.get("topic_key"))
            errs += [f"{t.get('topic_key')} claims[{ci}] needs claim and sources"
                     for ci, c in enumerate(t.get("claims", [])) if not c.get("claim") or not c.get("sources")]
            if t.get("opening_line") and len(t["opening_line"].split()) > 8:
                errs.append(f"{t.get('topic_key')}: opening_line has {len(t['opening_line'].split())} words (rule: ≤ 8)")
            if t.get("variant_beat_3_9") and len(reveal_words(t)) < 3:
                errs.append(f"{t.get('topic_key')}: variant_beat_3_9 has fewer than 3 distinctive words (cannot be checked)")
    sch = spec["schedule"]
    if len(sch.get("days", [])) != len(spec["pairs"]):
        errs.append("schedule.days needs one date per pair")
    if not sch.get("slots") or len(sch["slots"]) != 2:
        errs.append("schedule.slots needs the two daily times, e.g. ['18:00','23:00']")
    return errs


def assign_variant(experiment_id: str, pair_index: int) -> int:
    """Which topic of a pair is the variant: one recorded coin flip per experiment, alternated by pair (balanced)."""
    return (hashlib.sha256(experiment_id.encode()).digest()[0] & 1) ^ (pair_index % 2)


def constraints_for(spec: dict, slot: dict) -> list[str]:
    t, arm, d = slot["topic_spec"], slot["arm"], spec["duration_s"]
    out = [f"EXPERIMENT {spec['experiment_id']} · slot {slot['slot']} · pair {slot['pair_id']} · arm {arm.upper()} "
           f"(binding; details in experiment_assignment.json). Only the 3–9 s beat differs between the arms.",
           f"Opening (both arms): the hook's first spoken sentence is the assigned claim-first line “{t['opening_line']}” "
           f"(≤ 8 words). Reword only if the research dossier contradicts it, and then write experiment_override.json "
           f"in the run folder with the reason. A question must be answered or contradicted within about 2 s.",
           f"Frame 0 (both arms): show {t['frame0_visual']}."]
    if arm == "variant":
        out.append(f"3–9 s (VARIANT treatment): the beat right after the hook (starting about 2–7 s) delivers this second "
                   f"surprise / visual reveal: {t['variant_beat_3_9']} No setup beat, no repeat of the hook and no "
                   f"definitions or jargon between 3 and 9 s. Keep the payoff and the loop ending.")
    else:
        out.append("3–9 s (CONTROL): write the script exactly as the factory normally would after the hook — twists and "
                   "explanations are fine as usual. Only do not use the experiment's planned reveal for this topic "
                   f"(“{t['variant_beat_3_9']}”) in the first 9 s. Keep the payoff and the loop ending.")
    out += [f"Length: about {d['target']} s ({d['min']}–{d['max']} s). No spoken or caption CTA (the CTA test is a later week).",
            "Voice, caption style, music and doodle style: unchanged factory defaults.", f"Angle: {t['angle']}"]
    return out + [f"Rule: {r}" for r in spec.get("shared_rules", [])]


def build_plan(spec: dict, spec_sha: str) -> dict:
    slots, n = [], 0
    for pi, p in enumerate(spec["pairs"]):
        v = assign_variant(spec["experiment_id"], pi)
        day = spec["schedule"]["days"][pi]
        s_early, s_late = spec["schedule"]["slots"]
        variant_time = s_early if pi % 2 == 0 else s_late
        for ti, t in enumerate(p["topics"]):
            n += 1
            arm = "variant" if ti == v else "control"
            slots.append({"slot": n, "pair_id": p["pair_id"], "arm": arm, "topic_key": t["topic_key"], "topic": t["topic"],
                          "topic_spec": t, "planned_publish": {"date": day, "time": variant_time if arm == "variant" else
                                                               (s_late if variant_time == s_early else s_early), "tz": ROME}})
    for s in slots:
        s["paired_slot"] = next(x["slot"] for x in slots if x["pair_id"] == s["pair_id"] and x["slot"] != s["slot"])
        s["constraints"] = constraints_for(spec, s)
    plan = {"schema": SCHEMA, "engine": f"experiment {VERSION}", "experiment_id": spec["experiment_id"], "week": spec["week"],
            "created_at": now_iso(), "spec_sha256": spec_sha, "variable": spec["variable"], "hypothesis": spec.get("hypothesis"),
            "primary_metric": spec["primary_metric"], "secondary_metrics": spec.get("secondary_metrics", []),
            "guardrail_metric": spec.get("guardrail_metric"), "decision_rule": spec.get("decision_rule"),
            "duration_s": spec["duration_s"], "supersedes": spec.get("supersedes"),
            "randomization": "variant topic index = (sha256('<experiment_id>')[0] & 1) XOR (pair index % 2); "
                             "variant publish slot alternates by day",
            "pairs": [{"pair_id": p["pair_id"], "match_rationale": p["match_rationale"]} for p in spec["pairs"]],
            "slots": slots}
    plan["plan_sha256"] = IE.sha256_bytes(IE.canonical({k: v for k, v in plan.items() if k != "created_at"}).encode())
    return plan


def cmd_plan(a) -> dict:
    raw = Path(a.spec).read_bytes(); spec = json.loads(raw)
    errs = validate_spec(spec)
    if errs:
        raise ExpError("invalid experiment spec", details=errs)
    batch = Path(a.batches_dir) / spec["experiment_id"]; ed = exp_dir(batch); spec_sha = IE.sha256_bytes(raw)
    if (ed / "plan.json").exists():
        old = read_json(ed / "plan.json")
        if old["spec_sha256"] != spec_sha:
            raise ExpError("this experiment already has a plan from a different spec; assignments are never rewritten",
                           batch=str(batch), hint="use a new experiment_id for a changed design")
        return {"batch": str(batch), "plan": str(ed / "plan.json"), "status": "unchanged", "slots": len(old["slots"])}
    plan = build_plan(spec, spec_sha)
    batch.mkdir(parents=True, exist_ok=True)
    (batch / "input.json").write_bytes(raw)
    write_json(ed / "plan.json", plan)
    for s in plan["slots"]:
        write_json(ed / "slots" / f"{s['slot']:02d}.json", {"slot": s["slot"], "status": "assigned", "assigned_at": plan["created_at"],
                                                            "history": [{"at": plan["created_at"], "status": "assigned"}]})
    return {"batch": str(batch), "plan": str(ed / "plan.json"), "status": "created", "plan_sha256": plan["plan_sha256"],
            "assignments": [{k: s[k] for k in ("slot", "pair_id", "arm", "topic_key", "planned_publish")} for s in plan["slots"]]}


def load_plan(batch) -> dict:
    p = exp_dir(batch) / "plan.json"
    if not p.exists():
        raise ExpError("no experiment plan in this batch", batch=str(batch))
    plan = read_json(p)
    want = IE.sha256_bytes(IE.canonical({k: v for k, v in plan.items() if k not in ("created_at", "plan_sha256")}).encode())
    if want != plan["plan_sha256"]:
        raise ExpError("plan.json was edited after it was written; assignments are frozen", batch=str(batch))
    if IE.sha256_bytes((Path(batch) / "input.json").read_bytes()) != plan["spec_sha256"]:
        raise ExpError("input.json no longer matches the plan's spec", batch=str(batch))
    return plan


def plan_slot(plan: dict, n: int) -> dict:
    return next(s for s in plan["slots"] if s["slot"] == n)


def slot_rec(batch, n: int) -> dict:
    return read_json(exp_dir(batch) / "slots" / f"{n:02d}.json")


def save_slot(batch, rec: dict, status: str | None = None, **extra) -> dict:
    if status and status != rec.get("status"):
        rec["status"] = status
        rec.setdefault("history", []).append({"at": now_iso(), "status": status, **extra})
    write_json(exp_dir(batch) / "slots" / f"{rec['slot']:02d}.json", rec)
    return rec


def assignment_for(plan: dict, s: dict) -> dict:
    # the engine that wrote the plan (not this file's VERSION): assignments of an existing batch stay identical across upgrades
    return {"experiment_id": plan["experiment_id"], "plan_sha256": plan["plan_sha256"], "engine": plan.get("engine", f"experiment {VERSION}"),
            **{k: s[k] for k in ("slot", "pair_id", "arm", "paired_slot", "topic_key", "topic", "planned_publish", "constraints")},
            "opening_line": s["topic_spec"]["opening_line"], "frame0_visual": s["topic_spec"]["frame0_visual"],
            "planned_reveal": s["topic_spec"]["variant_beat_3_9"], "duration_s": plan["duration_s"]}


# ----------------------------------------------------------------------------- prepare + ready (failure-safe)
def manifest_for(batch: Path, plan: dict, db: str) -> dict:
    d = plan["duration_s"]
    # created_at = the plan's time: the runs are created after the plan, and idea_engine.run_state refuses runs older
    # than the batch ("foreign"); a manifest stamped after prepare would make every prepared run foreign.
    m = {"schema": "cf-idea-batch/1", "batch_id": batch.name, "created_at": plan["created_at"], "manifest_written_at": now_iso(),
         "engine": f"experiment {VERSION} ({SCHEMA}) via idea_engine {IE.ENGINE_VERSION}",
         "factory_version": (IE.SKILLS / "content-factory" / "VERSION").read_text().strip(),
         "ideas_file": {"path": str((batch / "input.json").resolve()), "sha256": plan["spec_sha256"], "archived_as": "input.json"},
         "memory": {"db": db, "items": None, "history_sha256": None},
         "selected": [{"slot": s["slot"], "id": s["topic_key"], "position": s["slot"], "topic": s["topic"],
                       "angle": s["topic_spec"]["angle"], "hook": s["topic_spec"]["opening_line"],
                       "visual": s["topic_spec"]["frame0_visual"], "category": s["topic_spec"].get("category"),
                       "source_hint": None, "total": None, "experiment_arm": s["arm"], "pair_id": s["pair_id"]}
                      for s in plan["slots"]],
         "production": {"runs_dir": str((batch / "runs").resolve()), "init": {"count": 1, "languages": "en", "min_s": d["min"], "max_s": d["max"]}}}
    m["manifest_sha256"] = IE.sha256_bytes(IE.canonical(IE.manifest_core(m)).encode())
    return m


def run_init(cmd: list[str]) -> tuple[int, dict]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return p.returncode, json.loads(p.stdout)
    except ValueError:
        return p.returncode or 1, {"error": "INIT_FAILED", "stderr": (p.stderr or p.stdout)[-400:]}


def cmd_prepare(a, init=run_init) -> dict:
    """Runs are created and recorded one by one; the batch manifest (which `idea_engine.py produce` requires) is written
    only after ALL slots are prepared and verified — so a partial batch can never be produced, and a failed slot can never
    be re-created by the Idea Engine without its experiment rules."""
    batch = Path(a.batch); plan = load_plan(batch)
    if (batch / "manifest.json").exists():
        return {"batch": str(batch), "status": "already prepared", "ready": cmd_ready(a)}
    db = str(IE.resolve_db(a.db)); mem = IE.ensure_memory(Path(db), False)
    runs_dir = batch / "runs"; runs_dir.mkdir(exist_ok=True)
    slots_file = batch / "slots.json"
    have = {s["slot"]: s for s in (read_json(slots_file)["slots"] if slots_file.exists() else [])}
    out = []
    for s in plan["slots"]:
        rec = slot_rec(batch, s["slot"])
        if have.get(s["slot"], {}).get("run_dir"):
            out.append({"slot": s["slot"], "run_dir": have[s["slot"]]["run_dir"], "status": "already prepared"}); continue
        d = plan["duration_s"]
        cmd = [sys.executable, str(HERE / "factory.py"), "init", "--topic", s["topic"], "--count", "1", "--languages", "en",
               "--min-s", str(d["min"]), "--max-s", str(d["max"]), "--runs-dir", str(runs_dir), "--db", mem["db"]]
        for c in s["constraints"]:
            cmd += ["--constraint", c]
        rc, res = init(cmd)
        entry = {"slot": s["slot"], "candidate_id": s["topic_key"], "topic": s["topic"], "init_exit": rc,
                 "run_dir": res.get("run") if rc == 0 else None, "init_error": None if rc == 0 else res}
        if entry["run_dir"]:
            write_json(Path(entry["run_dir"]) / "experiment_assignment.json", assignment_for(plan, s))
        have[s["slot"]] = entry
        write_json(slots_file, {"batch_id": batch.name, "slots": [have[k] for k in sorted(have)]})
        if entry["run_dir"]:
            rec["run_dir"] = entry["run_dir"]; rec.pop("init_error", None); save_slot(batch, rec, "prepared")
        else:
            rec["init_error"] = res; save_slot(batch, rec, "init_failed", note=str(res.get("error")))
        out.append({"slot": s["slot"], "run_dir": entry["run_dir"], "status": "prepared" if entry["run_dir"] else "init_failed",
                    "error": None if entry["run_dir"] else res.get("error")})
    problems = ready_problems(batch, plan, check_manifest=False)
    if problems:
        return {"batch": str(batch), "slots": out, "status": "NOT READY — manifest not written, production impossible",
                "problems": problems, "next": "fix the cause (e.g. run doctor.py) and run prepare again; only failed slots are retried"}
    write_json(batch / "manifest.json", manifest_for(batch, plan, mem["db"]))
    IE.verify_batch(batch)
    return {"batch": str(batch), "slots": out, "status": "prepared — all slots verified, manifest written",
            "next": f"experiment.py ready --batch {batch}"}


def ready_problems(batch: Path, plan: dict, check_manifest: bool = True) -> list[str]:
    probs = []
    slots_file = batch / "slots.json"
    have = {s["slot"]: s for s in (read_json(slots_file)["slots"] if slots_file.exists() else [])}
    for s in plan["slots"]:
        tag = f"slot {s['slot']} ({s['arm']}, {s['topic_key']})"
        e = have.get(s["slot"])
        if not e or not e.get("run_dir"):
            probs.append(f"{tag}: no run (init failed or not prepared)"); continue
        run = Path(e["run_dir"])
        if not (run / "state.json").exists() or not (run / "run.json").exists():
            probs.append(f"{tag}: run folder incomplete: {run}"); continue
        brief = read_json(run / "run.json")
        if brief.get("topic") != s["topic"]:
            probs.append(f"{tag}: run topic differs from the plan")
        if brief.get("constraints") != s["constraints"]:
            probs.append(f"{tag}: run.json constraints differ from the frozen plan")
        ap = run / "experiment_assignment.json"
        if not ap.exists():
            probs.append(f"{tag}: experiment_assignment.json missing")
        else:
            asg = read_json(ap)
            if asg != assignment_for(plan, s):
                probs.append(f"{tag}: experiment_assignment.json differs from the frozen plan")
        st = factory.load(run)
        v = st["videos"].get("v01")
        if v and v["stages"]["AUDIO"]["status"] in factory.DONE and not slot_rec(batch, s["slot"]).get("gate", {}).get("approved"):
            probs.append(f"{tag}: AUDIO already done without an approved experiment gate")
    if check_manifest:
        if not (batch / "manifest.json").exists():
            probs.append("manifest.json missing (prepare has not completed all slots)")
        else:
            try:
                IE.verify_batch(batch)
            except IE.BatchRefused as e:
                probs.append(f"manifest refused: {e}")
    return probs


def cmd_ready(a) -> dict:
    batch = Path(a.batch); plan = load_plan(batch)
    probs = ready_problems(batch, plan)
    res = {"batch": str(batch), "experiment_id": plan["experiment_id"], "plan_sha256": plan["plan_sha256"],
           "ready": not probs, "problems": probs,
           "slots": [{"slot": s["slot"], "pair": s["pair_id"], "arm": s["arm"], "topic": s["topic_key"],
                      "status": slot_rec(batch, s["slot"])["status"]} for s in plan["slots"]]}
    if probs and getattr(a, "strict", False):
        raise ExpError("NOT READY", **res)
    return res


# ----------------------------------------------------------------------------- the compliance check (pre- and post-audio)
def stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def content_words(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z][a-z']+", (text or "").lower().replace("’", "'")):
        if w not in STOP:
            w = re.sub(r"'s$", "", w).strip("'")
            if len(w) >= 3 and w not in STOP:
                out.add(stem(w))
    return out


def spoken_part(text: str) -> str:
    return re.sub(r"\([^)]*\)", " ", text or "")


# words that describe the production of a beat, not what is said in it (never matched against a script)
META = {stem(w) for w in "narration reveal screen on-screen show shows animate animated labelled labeled label drawn visual".split()}


def reveal_words(t: dict) -> set[str]:
    """Words that identify the planned reveal (not shared with the topic, opening, angle or frame-0 picture)."""
    base = content_words(" ".join(t.get(k, "") for k in ("topic", "opening_line", "angle", "frame0_visual", "topic_key")))
    return content_words(spoken_part(t.get("variant_beat_3_9", ""))) - base - META


def first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", (text or "").strip())[0] if text else ""


def norm_tok(w: str) -> str:
    return re.sub(r"[^0-9a-z]", "", str(w).lower().replace("’", "'"))


def beat_times(script: dict, timing: dict | None) -> tuple[list[dict], dict]:
    """Times per beat: measured from TTS word timing (alignment verified token by token) or estimated before audio."""
    beats = script.get("beats", [])
    tokens = [w for b in beats for w in b["text"].split()]
    info = {"mode": "measured" if timing else "estimated", "aligned": None, "mismatches": []}
    out, wi, t = [], 0, 0.15
    if timing:
        words = timing.get("words", [])
        mm = [(i, tokens[i], words[i].get("w", words[i].get("word"))) for i in range(min(len(tokens), len(words)))
              if norm_tok(tokens[i]) != norm_tok(words[i].get("w", words[i].get("word", "")))]
        info["aligned"] = not mm and len(tokens) == len(words)
        info["mismatches"] = mm[:5] + ([("count", len(tokens), len(words))] if len(tokens) != len(words) else [])
    for b in beats:
        n = len(b["text"].split())
        if timing and info["aligned"]:
            st, en = timing["words"][wi]["start"], timing["words"][wi + n - 1]["end"]
        else:
            t += float(b.get("pause_before") or 0)
            st, en = t, t + n / EST_WPS
            t = en + EST_GAP
        out.append({"id": b.get("id"), "role": b.get("role"), "text": b["text"], "on_screen": b.get("on_screen"),
                    "start": round(st, 2), "end": round(en, 2)})
        wi += n
    return out, info


def evaluate(script: dict, timing: dict | None, asg: dict, override: dict | None = None) -> dict:
    """The experiment gate. Both arms: opening line, question answered, alignment (measured). Variant: the planned reveal
    starts 2–7 s, no setup/hook repeat in 3–9 s. Control: the planned reveal is absent from the first 9 s."""
    beats, info = beat_times(script, timing)
    issues, notes = [], []
    if timing and not info["aligned"]:
        issues.append(f"script words do not align with the TTS timing ({info['mismatches']}); beat times untrustworthy")
    if not beats:
        return {"ok": False, "issues": ["script has no beats"], "notes": [], "timing": info}
    hook = beats[0]; fs = first_sentence(hook["text"])
    want = content_words(asg["opening_line"]); got = content_words(fs)
    share = len(want & got) / max(1, len(want))
    if len(fs.split()) > 8:
        issues.append(f"opening sentence has {len(fs.split())} words (rule ≤ 8): “{fs}”")
    if share < OPENING_MIN_SHARE:
        if override and override.get("opening_line_reason"):
            notes.append(f"opening differs from the assigned line (override: {override['opening_line_reason']})")
        else:
            issues.append(f"opening “{fs}” is not the assigned line “{asg['opening_line']}” (shared {share:.0%}); "
                          "write experiment_override.json with the research reason if the line had to change")
    if fs.endswith("?"):
        # the answer (next spoken word after the question) must start within 2 s of the question's end
        nq = len(fs.split())
        if timing and info["aligned"]:
            words = timing["words"]
            gap = (words[nq]["start"] - words[nq - 1]["end"]) if nq < len(words) else 99.0
        elif hook["text"][len(fs):].strip():
            gap = 0.0                                    # the answer continues in the same beat
        else:
            nxt = beats[1] if len(beats) > 1 else None
            gap = (nxt["start"] - hook["end"]) if nxt else 99.0
        if gap > 2.0:
            issues.append(f"opening is a question not answered within 2 s (gap {gap:.1f} s)")
    rw = set(asg.get("_reveal_words") or [])
    scored = []
    for b in beats[1:]:
        cw = content_words(b["text"]); hit = cw & rw
        scored.append({"id": b["id"], "role": b["role"], "start": b["start"], "end": b["end"], "matched": sorted(hit),
                       "share": round(len(hit) / max(1, len(rw)), 2)})
    def is_reveal(x):
        return len(x["matched"]) >= TREAT_MIN_WORDS and x["share"] >= TREAT_MIN_SHARE
    early = [x for x in scored if x["start"] < 9.0]
    treat = [x for x in scored if is_reveal(x) and TREAT_START[0] <= x["start"] <= TREAT_START[1]]
    hook_cw = content_words(hook["text"])
    if asg["arm"] == "variant":
        if not treat:
            best = max(early, key=lambda x: x["share"], default=None)
            issues.append(f"variant: the planned reveal does not start between {TREAT_START[0]} and {TREAT_START[1]} s"
                          + (f" (closest: {best['id']} at {best['start']} s, matched {best['matched']})" if best else ""))
        for b in [x for x in beats[1:] if TREAT_START[0] <= x["start"] < 9.0]:
            if treat and b["id"] == treat[0]["id"]:
                continue                  # the reveal beat itself (V3.0.1 may label it "setup")
            if b["role"] == "setup":
                issues.append(f"variant: setup beat {b['id']} starts at {b['start']} s (the 3–9 s window must carry the reveal, not setup)")
            if len(hook_cw) >= 2 and len(content_words(b["text"]) & hook_cw) >= min(3, len(hook_cw)):
                issues.append(f"variant: beat {b['id']} repeats the hook inside 3–9 s")
        long_words = sorted({w for b in beats[1:] if TREAT_START[0] <= b["start"] < 9.0 for w in re.findall(r"[A-Za-z]+", b["text"]) if len(w) >= 11})
        if long_words:
            notes.append(f"possible jargon in 3–9 s: {long_words}")
    else:
        leak = [x for x in early if is_reveal(x)]
        if leak:
            issues.append(f"control: the planned treatment reveal appears in the first 9 s ({leak[0]['id']} at {leak[0]['start']} s, "
                          f"matched {leak[0]['matched']})")
    window = [{"id": b["id"], "role": b["role"], "text": b["text"], "start": b["start"], "end": b["end"]}
              for b in beats if b["start"] < 9.0 and b["end"] > 3.0]
    return {"ok": not issues, "issues": issues, "notes": notes, "timing": info, "opening_first_sentence": fs,
            "opening_share": round(share, 2), "treatment_beat": treat[0] if treat else None, "beat_3_9": window,
            "beat_scores": scored, "beats": beats}


def asg_with_words(plan: dict, s: dict) -> dict:
    a = assignment_for(plan, s); a["_reveal_words"] = sorted(reveal_words(s["topic_spec"]))
    return a


def gate_run(batch: Path, plan: dict, s: dict, measured: bool) -> dict:
    rec = slot_rec(batch, s["slot"]); run = Path(rec["run_dir"]); v = run / "videos" / "v01"
    sp, tp = v / "script" / "script.json", v / "audio" / "timing.json"
    if not sp.exists():
        return {"ok": False, "issues": ["script.json not written yet"], "stage": "none"}
    if measured and not tp.exists():
        return {"ok": False, "issues": ["no TTS timing yet (audio not generated)"], "stage": "script"}
    ov = run / "experiment_override.json"
    res = evaluate(read_json(sp), read_json(tp) if measured else None, asg_with_words(plan, s), read_json(ov) if ov.exists() else None)
    res.update(script=str(sp), script_sha256=sha_file(sp), hook_sha256=sha_file(v / "hook" / "selected_hook.json"),
               checked_at=now_iso(), mode="measured" if measured else "pre_audio")
    return res


def script_stage(run: Path) -> dict:
    """What V3.0.1 recorded for SCRIPT (read only). A script.json can exist while SCRIPT failed: script_select writes the
    best variant even when another check (e.g. SCRIPT.VARIANTS_DISTINCT) fails the stage."""
    try:
        st = factory.load(run)
    except (OSError, ValueError) as e:
        return {"status": "unreadable", "error": str(e)}
    v = st.get("videos", {}).get("v01")
    if not v:
        return {"status": "no_video_yet"}
    e = v["stages"]["SCRIPT"]
    return {"status": e["status"], "attempt": e.get("attempt"), "result_sha256": e.get("result_sha256"), "video_status": v.get("status")}


def cmd_gate(a) -> dict:
    batch = Path(a.batch); plan = load_plan(batch); s = plan_slot(plan, a.slot)
    res = gate_run(batch, plan, s, a.measured)
    rec = slot_rec(batch, s["slot"])
    sc = script_stage(Path(rec["run_dir"])) if rec.get("run_dir") else {"status": "no_run"}
    res["factory_script"] = sc
    if sc["status"] not in factory.PASSED:      # the experiment rules passing is not enough: V3.0.1 must have passed SCRIPT
        res["ok"] = False
        res["issues"] = list(res.get("issues", [])) + [f"factory SCRIPT stage is '{sc['status']}', not passed: this script.json "
                                                        "is not approved by V3.0.1"]
    return {k: v for k, v in res.items() if k != "beats"}


SYNC_FROM = ("prepared", "blocked", "gate_failed")


def sync_gate_check(batch: Path, plan: dict, s: dict) -> tuple[list[str], dict]:
    """Every precondition of sync-gate, read only. Returns (problems, context)."""
    probs, ctx = [], {}
    tag = f"slot {s['slot']}"
    rec = slot_rec(batch, s["slot"]); ctx["slot_status"] = rec.get("status")
    if not rec.get("run_dir"):
        return [f"{tag}: no run"], ctx
    run = Path(rec["run_dir"]); ctx["run"] = str(run)
    if not (run / "state.json").exists():
        return [f"{tag}: run folder or state.json missing: {run}"], ctx
    if rec.get("status") not in SYNC_FROM:
        probs.append(f"{tag}: slot status is '{rec.get('status')}'; sync-gate only syncs {list(SYNC_FROM)}")
    if rec.get("gate", {}).get("approved"):
        probs.append(f"{tag}: gate already approved; nothing to sync")
    for lock in (run / ".lock", batch / ".lock"):
        if lock.exists():
            probs.append(f"{tag}: {lock} exists: another factory/idea_engine process is working; wait for it")
    ap = run / "experiment_assignment.json"
    if not ap.exists() or read_json(ap) != assignment_for(plan, s):
        probs.append(f"{tag}: experiment_assignment.json missing or different from the frozen plan")
    if read_json(run / "run.json").get("constraints") != s["constraints"]:
        probs.append(f"{tag}: run.json constraints differ from the frozen plan")
    try:
        IE.verify_batch(batch)
    except IE.BatchRefused as e:
        probs.append(f"manifest refused: {e}")
    st = factory.load(run); v = st.get("videos", {}).get("v01")
    if not v:
        return probs + [f"{tag}: the run has no video yet"], ctx
    stages = v["stages"]
    ctx["factory"] = {"video_status": v.get("status"), "HOOK": stages["HOOK"]["status"], "SCRIPT": stages["SCRIPT"]["status"]}
    if v.get("status") != "in_progress":
        probs.append(f"{tag}: video status is '{v.get('status')}', not in_progress")
    for name in ("HOOK", "SCRIPT"):
        if stages[name]["status"] not in factory.PASSED:
            probs.append(f"{tag}: factory {name} is '{stages[name]['status']}', not passed")
    later = factory.VIDEO_STAGES[factory.VIDEO_STAGES.index("SCRIPT") + 1:]
    ran = [k for k in later if stages[k]["status"] in factory.PASSED]
    if ran:
        probs.append(f"{tag}: stages after SCRIPT already passed {ran}; the gate can no longer precede audio")
    rp = factory.vp(run, "v01")["result"]["SCRIPT"]; sp = factory.vp(run, "v01")["script"]
    if not rp.exists() or not sp.exists():
        probs.append(f"{tag}: SCRIPT result.json or script.json missing")
    else:
        if sha_file(rp) != stages["SCRIPT"].get("result_sha256"):
            probs.append(f"{tag}: SCRIPT result.json is not the one V3.0.1 recorded (sha256 differs)")
        res = read_json(rp)
        if res.get("status") not in factory.PASSED:
            probs.append(f"{tag}: SCRIPT result.json status is '{res.get('status')}'")
        outs = [o.get("sha256") for o in res.get("outputs", []) if o.get("role") == "script"]
        if outs != [sha_file(sp)]:
            probs.append(f"{tag}: script.json is not the script the passed SCRIPT gate wrote (sha256 differs)")
    ctx["state_sha256"], ctx["script_sha256"] = sha_file(run / "state.json"), sha_file(sp)
    return probs, ctx


def cmd_sync_gate(a) -> dict:
    """Records the experiment gate for a slot whose SCRIPT passed outside `drive` (a human reset + re-record). Runs no stage,
    no Claude session, no audio, no factory command; writes only experiment_gate.json and the slot record, and only when
    every precondition and the gate itself pass. On any failure nothing is written."""
    batch = Path(a.batch); plan = load_plan(batch); s = plan_slot(plan, a.slot)
    probs, ctx = sync_gate_check(batch, plan, s)
    if probs:
        raise ExpError("sync-gate refused: preconditions not met; nothing was written", slot=s["slot"], problems=probs, context=ctx)
    res = gate_run(batch, plan, s, measured=False)
    if not res["ok"]:
        raise ExpError("sync-gate refused: the experiment gate fails on this script; nothing was written", slot=s["slot"],
                       issues=res["issues"], context=ctx)
    run = Path(ctx["run"])
    if sha_file(run / "state.json") != ctx["state_sha256"] or res["script_sha256"] != ctx["script_sha256"]:
        raise ExpError("sync-gate refused: the run changed while checking; nothing was written", slot=s["slot"])
    write_json(run / "experiment_gate.json", {k: v for k, v in res.items() if k != "beats"})
    rec = slot_rec(batch, s["slot"])
    attempts = list(rec.get("gate", {}).get("attempts", []))
    attempts.append({"at": now_iso(), "ok": True, "issues": [], "notes": res.get("notes", []), "script_sha256": res["script_sha256"],
                     "audio_already_ran": False, "source": "sync-gate", "factory_script": ctx["factory"]["SCRIPT"]})
    rec["gate"] = {**rec.get("gate", {}), "approved": True, "script_sha256": res["script_sha256"], "hook_sha256": res["hook_sha256"],
                   "attempts": attempts, "approved_at": now_iso(), "approved_by": "sync-gate"}
    save_slot(batch, rec, "gate_passed", note=f"sync-gate: SCRIPT passed in V3.0.1 outside drive (was '{ctx['slot_status']}')")
    return {"slot": s["slot"], "synced": True, "status": "gate_passed", "previous_status": ctx["slot_status"],
            "script_sha256": res["script_sha256"], "treatment_beat": res.get("treatment_beat"), "gate_file": str(run / "experiment_gate.json"),
            "next": "nothing was run; `experiment.py drive` / `produce` will skip phase A and start phase B (audio) for this slot"}


# ----------------------------------------------------------------------------- the driver (phase A → gate → phase B)
def claude_prefix() -> list[str]:
    env = os.environ.get("CF_EXPERIMENT_CLAUDE")          # test stubs only
    if env:
        return shlex.split(env, posix=os.name != "nt")
    return [shutil.which("claude") or "claude"]           # full path: also finds claude.cmd / claude.exe on Windows


CMD_UNSAFE = str.maketrans({'"': "'", "%": " percent", "&": "and", "|": "/", "<": "‹", ">": "›", "^": ""})


def claude_argv(prompt: str, batch: Path) -> list[str]:
    # the same flags as idea_engine.driver_argv (= automation-engineering's run_factory templates)
    pre = claude_prefix()
    if pre[0].lower().endswith((".cmd", ".bat")):          # npm shim: cmd.exe would re-parse these characters
        prompt = prompt.translate(CMD_UNSAFE)
    return pre + ["-p", prompt, "--permission-mode", "acceptEdits", "--permission-prompts", "none",
                              "--allowedTools", "Bash,Read,Write,Edit,WebSearch,WebFetch", "--output-format", "json",
                              "--add-dir", str(batch)]


def rules_block(asg: dict) -> str:
    r = [f"- Arm: {asg['arm'].upper()} (pair {asg['pair_id']}, paired with slot {asg['paired_slot']}).",
         f"- Opening: the hook's first spoken sentence must be “{asg['opening_line']}” (≤ 8 words, claim first). Generate the "
         "hook candidates around this exact line. If the research dossier contradicts it, use the closest accurate wording and "
         "write experiment_override.json in the run folder with the key opening_line_reason and the reason.",
         f"- Frame 0: {asg['frame0_visual']}."]
    if asg["arm"] == "variant":
        r.append(f"- 3–9 s TREATMENT: the beat right after the hook, starting about 2–7 s, is this second surprise / visual "
                 f"reveal: {asg['planned_reveal']} No setup beat, no hook repeat, no definitions or jargon before 9 s.")
    else:
        r.append("- 3–9 s CONTROL: write the beats after the hook exactly as you normally would (twists are fine). Do NOT "
                 f"use this planned reveal in the first 9 s: {asg['planned_reveal']}")
    d = asg["duration_s"]
    r += [f"- Length about {d['target']} s ({d['min']}–{d['max']} s). No CTA. Voice, captions, music, doodle style: defaults."]
    return "\n".join(r)


def phase_a_prompt(run: Path, asg: dict, feedback: str | None) -> str:
    return (f"/content-factory Continue the existing factory run at {run} — do not start a new run. It is slot {asg['slot']} of "
            f"the paired experiment {asg['experiment_id']} (plan {asg['plan_sha256'][:12]}). Read {run / 'experiment_assignment.json'} "
            f"first. These rules are binding for HOOK and SCRIPT:\n{rules_block(asg)}\n"
            "Drive the run with factory.py next/record until the SCRIPT stage is recorded as passed. Then STOP: when "
            "`factory.py next` returns run_media for AUDIO, do not run it — end your turn and report. An experiment gate "
            "checks the script before any audio is made. Never publish or upload anything."
            + (f"\nThe previous script was rejected by the experiment gate: {feedback} Rewrite it so it complies." if feedback else ""))


def phase_b_prompt(run: Path, asg: dict, script_sha: str) -> str:
    return (f"/content-factory Continue the existing factory run at {run} — do not start a new run. Slot {asg['slot']} of experiment "
            f"{asg['experiment_id']} ({asg['arm'].upper()}): the HOOK and SCRIPT were approved by the experiment gate "
            f"(script sha256 {script_sha[:16]}). Do not change the hook or the script. If any gate requires a HOOK or SCRIPT "
            "change, stop and report instead of changing it. Drive the run with factory.py next/record/media until it is "
            f"packaged, then run `factory.py package --run {run} --zip`, stop, and report escalations. Never publish or upload.")


def stage_status(run: Path, stage: str) -> str:
    v = factory.load(run)["videos"].get("v01")
    return v["stages"][stage]["status"] if v else "no_video_yet"


def run_claude(argv: list[str], log: Path, timeout_min: int) -> int | None:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_min * 60)
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        rc, out, err = None, str(e.stdout or ""), "timeout"
    except OSError as e:
        rc, out, err = None, "", f"could not start: {e}"
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(f"$ {' '.join(argv[:2])} … (exit {rc})\n--- prompt\n{argv[argv.index('-p') + 1]}\n--- stdout\n{out}\n--- stderr\n{err}\n\n")
    return rc


def factory_reset(run: Path, stage: str, note: str) -> None:
    """V3.0.1's own human-override command: re-opens HOOK or SCRIPT and marks every later stage (AUDIO …) stale."""
    p = subprocess.run([sys.executable, str(HERE / "factory.py"), "reset", "--run", str(run), "--video", "v01", "--stage", stage,
                        "--note", note[:400]], capture_output=True, text=True)
    if p.returncode != 0 or stage_status(run, stage) != "pending":
        raise ExpError("factory.py reset failed; the slot is stopped before audio", stage=stage, stderr=(p.stderr or p.stdout)[-400:])


def cmd_drive(a) -> dict:
    batch = Path(a.batch); plan = load_plan(batch); s = plan_slot(plan, int(a.slot)); run = Path(a.run)
    rec = slot_rec(batch, s["slot"])
    if Path(rec.get("run_dir", "")).resolve() != run.resolve():
        raise ExpError("run does not belong to this slot", slot=s["slot"], run=str(run))
    asg = read_json(run / "experiment_assignment.json")
    if asg != assignment_for(plan, s):
        raise ExpError("experiment_assignment.json differs from the frozen plan", slot=s["slot"])
    logs = exp_dir(batch) / "logs"; logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"{s['slot']:02d}-drive.log"
    approved = rec.get("gate", {}).get("approved")
    feedback, attempts = None, rec.get("gate", {}).get("attempts", [])
    if not approved:
        for i in range(MAX_REPAIRS + 1):
            if stage_status(run, "SCRIPT") not in factory.PASSED:
                rc = run_claude(claude_argv(phase_a_prompt(run, asg, feedback), batch), log, a.run_timeout_min)
                if stage_status(run, "SCRIPT") not in factory.PASSED:
                    rec["gate"] = {"approved": False, "attempts": attempts}
                    save_slot(batch, rec, "blocked", note=f"phase A ended without a passed SCRIPT (driver exit {rc})")
                    raise ExpError("phase A did not reach a passed SCRIPT; nothing after SCRIPT was started", slot=s["slot"], log=str(log))
            res = gate_run(batch, plan, s, measured=False)
            audio_ran = stage_status(run, "AUDIO") in factory.DONE
            attempts.append({"at": now_iso(), "ok": res["ok"], "issues": res["issues"], "notes": res.get("notes", []),
                             "script_sha256": res.get("script_sha256"), "audio_already_ran": audio_ran})
            write_json(run / "experiment_gate.json", {k: v for k, v in res.items() if k != "beats"})
            if res["ok"]:
                rec["gate"] = {"approved": True, "script_sha256": res["script_sha256"], "hook_sha256": res["hook_sha256"],
                               "attempts": attempts, "approved_at": now_iso()}
                save_slot(batch, rec, "gate_passed")
                break
            opening = any(x.startswith("opening") for x in res["issues"])
            stage = "HOOK" if opening else "SCRIPT"
            feedback = "; ".join(res["issues"])
            rec["gate"] = {"approved": False, "attempts": attempts}
            save_slot(batch, rec, "gate_failed", note=feedback[:300])
            try:
                factory_reset(run, stage, "experiment gate: " + feedback)   # also marks AUDIO onwards stale
            except ExpError:
                save_slot(batch, rec, "blocked", note="factory reset failed after a gate failure")
                raise
        else:
            save_slot(batch, rec, "blocked", note="non-compliant after the repair budget; no audio from this script is kept")
            raise ExpError("experiment gate failed after repairs; the slot is blocked before audio", slot=s["slot"],
                           issues=attempts[-1]["issues"], log=str(log))
    rec = slot_rec(batch, s["slot"])
    rc = run_claude(claude_argv(phase_b_prompt(run, asg, rec["gate"]["script_sha256"]), batch), log, a.run_timeout_min)
    sp = run / "videos" / "v01" / "script" / "script.json"
    if sha_file(sp) != rec["gate"]["script_sha256"]:
        res = gate_run(batch, plan, s, measured=False)
        rec["gate"]["changed_after_approval"] = {"at": now_iso(), "new_sha256": sha_file(sp), "still_ok": res["ok"], "issues": res["issues"]}
        save_slot(batch, rec, "noncompliant" if not res["ok"] else rec["status"], note="script changed after approval")
    return {"slot": s["slot"], "phase_b_exit": rc, "gate": rec["gate"].get("approved"), "status": rec["status"], "log": str(log)}


def cmd_produce(a) -> dict:
    batch = Path(a.batch); plan = load_plan(batch)
    probs = ready_problems(batch, plan)
    if probs:
        raise ExpError("NOT READY — production refused", problems=probs, hint="run experiment.py prepare / ready")
    if not os.environ.get("CF_EXPERIMENT_CLAUDE"):
        why = IE.preflight(types.SimpleNamespace(produce="claude", driver_cmd=None))   # claude on PATH + installed skills
        if why:
            raise ExpError("production environment not ready", hint=why)
    me = Path(__file__).resolve()
    drv = f'"{sys.executable}" "{me}" drive --batch {{batch}} --run {{run}} --slot {{slot}} --run-timeout-min {a.run_timeout_min}'
    # one slot = up to MAX_REPAIRS+1 phase-A sessions + one phase-B session
    args = types.SimpleNamespace(produce="claude", driver_cmd=drv, output_dir=a.output_dir,
                                 run_timeout_min=a.run_timeout_min * (MAX_REPAIRS + 2) + 30)
    res = IE.produce(batch, args)
    return {"driver_cmd": drv, **res}


# ----------------------------------------------------------------------------- post-production check (measured)
def cmd_check(a) -> dict:
    batch = Path(a.batch); plan = load_plan(batch); out = []
    for s in plan["slots"]:
        rec = slot_rec(batch, s["slot"])
        if not rec.get("run_dir"):
            out.append({"slot": s["slot"], "status": rec["status"]}); continue
        run = Path(rec["run_dir"]); v = run / "videos" / "v01"
        if not (v / "audio" / "timing.json").exists():
            out.append({"slot": s["slot"], "status": rec["status"], "note": "not produced yet"}); continue
        res = gate_run(batch, plan, s, measured=True)
        approved = rec.get("gate", {}).get("script_sha256")
        if approved and res["script_sha256"] != approved:
            res["issues"].append("script changed after the experiment gate approved it"); res["ok"] = False
        if not approved:
            res["issues"].append("no approved pre-audio gate on record for this slot"); res["ok"] = False
        timing = read_json(v / "audio" / "timing.json")
        dossier = run / "research" / "dossier.json"
        rec["production"] = {
            "status": "produced", "checked_at": now_iso(), "duration_s": round(timing.get("duration_s", 0), 2),
            "opening_line": res["beats"][0]["text"] if res.get("beats") else None, "opening_first_sentence": res.get("opening_first_sentence"),
            "hook_category": (read_json(v / "hook" / "selected_hook.json").get("archetype") if (v / "hook" / "selected_hook.json").exists() else None),
            "beat_3_9": res.get("beat_3_9"), "treatment_beat": res.get("treatment_beat"), "timing_alignment": res.get("timing"),
            "compliance": {"ok": res["ok"], "issues": res["issues"], "notes": res.get("notes", [])}, "beats": res.get("beats"),
            "sources": [{"title": x.get("title"), "url": x.get("url"), "publisher": x.get("publisher")}
                        for x in (read_json(dossier).get("sources", []) if dossier.exists() else [])],
            "artifacts": {"script": str(v / "script" / "script.json"), "timing": str(v / "audio" / "timing.json"),
                          "storyboard": str(v / "visual" / "storyboard.rendered.json"), "final_mp4": str(run / "package" / "v01" / "final.mp4"),
                          "dossier": str(dossier), "package_dir": str(run / "package"), "gate": str(run / "experiment_gate.json")}}
        new = rec["status"] if rec["status"] in ("published", "observed") else ("produced" if res["ok"] else "noncompliant")
        save_slot(batch, rec, new)
        out.append({"slot": s["slot"], "arm": s["arm"], "status": new, "duration_s": rec["production"]["duration_s"],
                    "opening": res.get("opening_first_sentence"), "issues": res["issues"], "timing_aligned": res["timing"]["aligned"]})
    return {"batch": str(batch), "publishable": all(x.get("status") in ("produced", "published", "observed") for x in out), "slots": out}


# ----------------------------------------------------------------------------- publication + observations
def parse_iso(s: str) -> dt.datetime:
    d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ExpError(f"timestamp without a timezone: {s}")
    return d


def tz(name: str, fallback_hours: int):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name), None
    except Exception:
        return dt.timezone(dt.timedelta(hours=fallback_hours)), f"tz database unavailable; {name} taken as UTC{fallback_hours:+d}"


def to_rome(d: dt.datetime) -> str:
    z, note = tz(ROME, 2)
    return d.astimezone(z).isoformat() + (f" ({note})" if note else "")


def analytics_cutoff(snap: dict) -> tuple[dt.datetime | None, str | None, str | None]:
    """End of the last day YouTube Analytics has processed (its days are Pacific time). The channel's daily report only
    returns processed days, so its last row is the cutoff; `until` (the requested end date) is NOT the cutoff."""
    days = sorted(r["day"] for r in snap.get("channel_daily", []) if r.get("day"))
    if not days:
        return None, None, "no daily Analytics rows in the snapshot"
    z, note = tz(PACIFIC, -7)
    last = dt.date.fromisoformat(days[-1])
    end = dt.datetime.combine(last + dt.timedelta(days=1), dt.time(0, 0), tzinfo=z)
    return end.astimezone(dt.timezone.utc), days[-1], note


def window_for(age_h: float | None) -> str:
    if age_h is None:
        return "unknown"
    if age_h <= 0:
        return "before_publication"
    for k, (lo, hi) in WINDOWS.items():
        if lo <= age_h < hi:
            return k
    return "other"


def package_title(run_dir: str | None) -> str | None:
    p = Path(run_dir) / "package" / "v01" / "publishing_package.json" if run_dir else None
    return read_json(p).get("public", {}).get("title") if p and p.exists() else None


def norm_title(t: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def cmd_link(a) -> dict:
    batch = Path(a.batch); plan = load_plan(batch); out = []
    if a.slot:
        rec = slot_rec(batch, a.slot)
        if rec.get("publication", {}).get("video_id") and rec["publication"]["video_id"] != a.video_id:
            raise ExpError(f"slot {a.slot} is already linked to {rec['publication']['video_id']}")
        pa = parse_iso(a.published_at)
        rec["publication"] = {"video_id": a.video_id, "published_at_utc": pa.astimezone(dt.timezone.utc).isoformat(),
                              "published_at_rome": to_rome(pa), "source": "manual", "linked_at": now_iso()}
        save_slot(batch, rec, "published")
        return {"linked": [{"slot": a.slot, "video_id": a.video_id}]}
    snap = read_json(a.snapshot); by_title = {}
    for v in snap.get("videos", []):
        by_title.setdefault(norm_title(v["title"]), []).append(v)
    for s in plan["slots"]:
        rec = slot_rec(batch, s["slot"])
        if rec.get("publication", {}).get("video_id"):
            out.append({"slot": s["slot"], "video_id": rec["publication"]["video_id"], "status": "already linked"}); continue
        title = package_title(rec.get("run_dir")); hits = by_title.get(norm_title(title), []) if title else []
        if len(hits) == 1 and hits[0].get("privacy") == "public":
            v = hits[0]; pa = parse_iso(v["published_at"])
            rec["publication"] = {"video_id": v["video_id"], "published_at_utc": pa.astimezone(dt.timezone.utc).isoformat(),
                                  "published_at_rome": to_rome(pa), "source": "youtube_data_api (title match)",
                                  "matched_title": v["title"], "linked_at": now_iso()}
            save_slot(batch, rec, "published"); out.append({"slot": s["slot"], "video_id": v["video_id"], "status": "linked"})
        else:
            out.append({"slot": s["slot"], "status": "not linked",
                        "why": "no package title" if not title else f"{len(hits)} public title matches — link with --slot/--video-id"})
    return {"linked": out}


def interp_retention(curve: list[dict], duration: float, t: float) -> float | None:
    if not curve or not duration:
        return None
    pts = sorted((float(r["elapsedVideoTimeRatio"]), float(r["audienceWatchRatio"])) for r in curve)
    x = t / duration
    if x < pts[0][0] or x > pts[-1][0]:
        return None
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return round(y0 + (y1 - y0) * (x - x0) / (x1 - x0) if x1 > x0 else y0, 4)
    return round(pts[-1][1], 4)


def metric(value, source: str, observed_at: str, note: str | None = None) -> dict:
    return {"value": value, "status": "ok" if value is not None else "missing", "source": source if value is not None else None,
            "observed_at": observed_at, **({"note": note} if note else {})}


def cmd_observe(a) -> dict:
    """Windows are assigned by the DATA age (Analytics cutoff − publish time), not by when the pull ran."""
    batch = Path(a.batch); plan = load_plan(batch); snap = read_json(a.snapshot)
    pulled = snap.get("pulled_at") or now_iso()
    cutoff, cutoff_day, tz_note = analytics_cutoff(snap)
    rows = {v["video_id"]: v for v in snap.get("videos", [])}; pv = snap.get("per_video", {})
    done = {(o["slot"], o["window"], o.get("analytics_cutoff_day")) for o in read_jsonl(exp_dir(batch) / "observations.jsonl") if not o.get("manual")}
    out = []
    for s in plan["slots"]:
        rec = slot_rec(batch, s["slot"]); pub = rec.get("publication")
        if not pub:
            out.append({"slot": s["slot"], "status": "not published / not linked"}); continue
        vid = pub["video_id"]; r = rows.get(vid); pub_at = parse_iso(pub["published_at_utc"])
        data_age = round((cutoff - pub_at).total_seconds() / 3600, 1) if cutoff else None
        pull_age = round((parse_iso(pulled) - pub_at).total_seconds() / 3600, 1)
        win = window_for(data_age)
        key = (s["slot"], win, cutoff_day)
        if key in done:
            out.append({"slot": s["slot"], "status": "already recorded for this data cutoff", "window": win}); continue
        src = f"youtube_analytics_api via yt_sync ({Path(a.snapshot).name}; Analytics data through {cutoff_day} PT)"
        dur = (rec.get("production") or {}).get("duration_s"); curve = (pv.get(vid) or {}).get("retention") or []
        m = {}
        if r is None or win in ("unknown", "before_publication"):
            why = "video not in snapshot" if r is None else ("no Analytics cutoff in snapshot" if win == "unknown" else
                                                             "Analytics data ends before this video was published")
            m = {k: metric(None, src, pulled, why) for k in METRICS}
        else:
            for k, rk in (("views", "views"), ("engaged_views", "engagedViews"), ("average_view_duration_s", "averageViewDuration"),
                          ("average_view_percentage", "averageViewPercentage"), ("likes", "likes"), ("comments", "comments"),
                          ("subscribers_gained", "subscribersGained")):
                m[k] = metric(r.get(rk), src, pulled, None if r.get(rk) is not None else "no Analytics row for this video yet")
            for t in (4, 8):
                val = interp_retention(curve, dur, t) if dur else None
                m[f"retention_{t}s"] = metric(val, src + " retention curve (viewers who did not swipe away; >1 = replays)", pulled,
                                              None if val is not None else ("no retention curve yet" if not curve else "duration unknown — run check"))
        m["stayed_to_watch"] = {"value": None, "status": "manual_required", "source": None, "observed_at": pulled,
                                "note": "Studio-only (How viewers engaged); no YouTube API exposes it"}
        o = {"slot": s["slot"], "video_id": vid, "window": win, "data_age_hours": data_age, "pull_age_hours": pull_age,
             "analytics_cutoff_day": cutoff_day, "analytics_cutoff_utc": cutoff.isoformat() if cutoff else None,
             "pulled_at": pulled, "observed_at": pulled, "recorded_at": now_iso(), "tz_note": tz_note, "metrics": m}
        append_jsonl(exp_dir(batch) / "observations.jsonl", o)
        if rec["status"] == "published":
            save_slot(batch, rec, "observed")
        out.append({"slot": s["slot"], "window": win, "data_age_hours": data_age, "pull_age_hours": pull_age,
                    "missing": [k for k, x in m.items() if x["status"] != "ok"]})
    return {"analytics_cutoff_day": cutoff_day, "pulled_at": pulled, "observations": out}


MANUAL_FIELDS = ("slot", "video_id", "window", "observed_at", "metric", "value", "source")


def cmd_manual_template(a) -> dict:
    batch = Path(a.batch); plan = load_plan(batch); p = exp_dir(batch) / "manual_entry.csv"
    if p.exists():
        raise ExpError(f"{p} exists; fill it in or move it away (never overwritten)")
    rows = [{"slot": s["slot"], "video_id": (slot_rec(batch, s["slot"]).get("publication") or {}).get("video_id", ""), "window": w,
             "observed_at": "", "metric": "stayed_to_watch", "value": "", "source": "youtube_studio"}
            for s in plan["slots"] for w in ("24h", "72h")]
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=MANUAL_FIELDS); w.writeheader(); w.writerows(rows)
    return {"template": str(p), "rows": len(rows),
            "how": "Studio → Content → Shorts → the video → Analytics → Engagement → How viewers engaged; percent (e.g. 38.8); "
                   "observed_at = when you read it, ISO with timezone (2026-10-16T19:05+02:00). Studio is live, so the window is "
                   "the video's age at that moment. Leave value empty if unknown."}


def cmd_manual(a) -> dict:
    batch = Path(a.batch); plan = load_plan(batch); slots = {s["slot"] for s in plan["slots"]}; added, skipped = [], []
    with open(a.csv, newline="", encoding="utf-8") as fh:
        for i, row in enumerate(csv.DictReader(fh), start=2):
            if not (row.get("value") or "").strip():
                skipped.append({"line": i, "why": "empty value (left missing)"}); continue
            try:
                slot = int(row["slot"]); val = float(row["value"]); w = row["window"].strip(); obs = parse_iso(row["observed_at"].strip()).isoformat()
            except (ValueError, KeyError, ExpError) as e:
                skipped.append({"line": i, "why": f"unreadable row: {e}"}); continue
            if slot not in slots or row["metric"] not in METRICS or w not in WINDOWS:
                skipped.append({"line": i, "why": "unknown slot, metric or window"}); continue
            append_jsonl(exp_dir(batch) / "observations.jsonl", {
                "slot": slot, "video_id": row.get("video_id") or None, "window": w, "observed_at": obs, "recorded_at": now_iso(),
                "manual": True, "metrics": {row["metric"]: {"value": val, "status": "ok", "source": (row.get("source") or "manual").strip(),
                                                            "observed_at": obs}}})
            added.append({"line": i, "slot": slot, "metric": row["metric"]})
    return {"added": added, "skipped": skipped}


# ----------------------------------------------------------------------------- report
def latest_metric(obs, slot, window, key):
    hits = [o for o in obs if o["slot"] == slot and o["window"] == window and o["metrics"].get(key, {}).get("status") == "ok"]
    if not hits:
        return None
    o = max(hits, key=lambda x: (x.get("analytics_cutoff_day") or "", x["observed_at"]))
    return {**o["metrics"][key], "window": window}


def pick(obs, slot, key):
    return latest_metric(obs, slot, "72h", key) or latest_metric(obs, slot, "24h", key)


def pct(v, key):
    return None if v is None else (round(v * 100, 1) if key.startswith("retention_") else round(v, 1))


def cmd_report(a) -> dict:
    batch = Path(a.batch); plan = load_plan(batch); obs = read_jsonl(exp_dir(batch) / "observations.jsonl")
    recs = {s["slot"]: slot_rec(batch, s["slot"]) for s in plan["slots"]}
    pm, rule = plan["primary_metric"], plan.get("decision_rule") or {"min_pairs": 7, "min_wins": 5, "min_median_gain_pp": 3}
    keys = [pm] + [k for k in plan.get("secondary_metrics", []) if k != pm] + ([plan["guardrail_metric"]] if plan.get("guardrail_metric") else [])
    pairs, diffs, wins, missing, excluded = [], [], 0, [], []
    for p in plan["pairs"]:
        ss = [s for s in plan["slots"] if s["pair_id"] == p["pair_id"]]
        v = next(s for s in ss if s["arm"] == "variant"); c = next(s for s in ss if s["arm"] == "control")
        row = {"pair_id": p["pair_id"], "variant": {"slot": v["slot"], "topic": v["topic_key"]},
               "control": {"slot": c["slot"], "topic": c["topic_key"]}, "metrics": {}, "confounders": [], "valid": True}
        for k in keys:
            mv, mc = pick(obs, v["slot"], k), pick(obs, c["slot"], k)
            vv, cv = (pct(mv["value"], k) if mv else None), (pct(mc["value"], k) if mc else None)
            row["metrics"][k] = {"variant": vv, "control": cv, "diff_pp": round(vv - cv, 1) if vv is not None and cv is not None else None,
                                 "windows": [mv["window"] if mv else None, mc["window"] if mc else None]}
            missing += [f"{p['pair_id']} {side} {k}" for side, val in (("variant", vv), ("control", cv)) if val is None]
        for side, slot in (("variant", v["slot"]), ("control", c["slot"])):
            r = recs[slot]; comp = (r.get("production") or {}).get("compliance")
            if r.get("status") in ("noncompliant", "blocked") or (comp and not comp["ok"]):
                row["valid"] = False
                row["confounders"].append(f"{side} NOT compliant: {(comp or {}).get('issues') or r.get('status')}")
            elif not comp:
                row["confounders"].append(f"{side}: no post-production check yet")
        if v["topic_key"] != c["topic_key"]:
            row["confounders"].append("different topics (matched, not identical): topic appeal is confounded with the arm")
        dv, dc = (recs[v["slot"]].get("production") or {}).get("duration_s"), (recs[c["slot"]].get("production") or {}).get("duration_s")
        if dv and dc and abs(dv - dc) > 3:
            row["confounders"].append(f"durations differ by {abs(dv - dc):.1f} s")
        if "24h" in row["metrics"][pm]["windows"]:
            row["confounders"].append("primary metric from a 24 h data window (72 h not yet available)")
        d = row["metrics"][pm]["diff_pp"]
        if d is not None and row["valid"]:
            diffs.append(d); wins += d > 0
        elif d is not None:
            excluded.append(p["pair_id"])
        pairs.append(row)
    n = len(diffs); med = round(statistics.median(diffs), 1) if diffs else None; prelim = n < rule["min_pairs"]
    if n == 0:
        rec, why = "insufficient evidence", "no valid pair has the primary metric for both arms yet"
    elif not prelim and wins >= rule["min_wins"] and med >= rule["min_median_gain_pp"]:
        rec, why = "adopt", f"{wins}/{n} pair wins and median +{med} pp meet the rule"
    elif not prelim and wins <= n - rule["min_wins"] and med <= -rule["min_median_gain_pp"]:
        rec, why = "reject", f"variant lost {n - wins}/{n} pairs, median {med} pp"
    else:
        rec = "continue testing"
        why = f"preliminary: {n} valid pair(s) of {rule['min_pairs']} needed; {wins}/{n} wins, median {med} pp" + \
              (" — direction promising" if med is not None and med >= rule["min_median_gain_pp"] and wins == n else "")
    rep = {"experiment_id": plan["experiment_id"], "week": plan["week"], "written_at": now_iso(), "primary_metric": pm, "decision_rule": rule,
           "pairs_with_primary": n, "wins": wins, "median_diff_pp": med, "preliminary": prelim, "recommendation": rec, "why": why,
           "pairs": pairs, "excluded_pairs_noncompliant": excluded, "missing": missing,
           "limitations": ["matched topics, not identical topics: topic appeal is confounded with the arm",
                           "few pairs: no statistical certainty; treat any result as directional",
                           "Analytics data lag 1–3 days (windows use the data cutoff); Stayed to watch is manual (Studio-only)",
                           "retention = share of viewers who did not swipe away still watching (replays can exceed 100%)",
                           "raw views are not used for the decision"]}
    rd = exp_dir(batch) / "reports"; stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    write_json(rd / f"report-{stamp}.json", rep); (rd / f"report-{stamp}.md").write_text(render_md(rep, plan), encoding="utf-8")
    return {"report": str(rd / f"report-{stamp}.md"), "recommendation": rec, "why": why, "missing": len(missing), "excluded": excluded}


def render_md(rep: dict, plan: dict) -> str:
    ks = list(rep["pairs"][0]["metrics"])
    L = [f"# {rep['experiment_id']} — weekly experiment report ({rep['week']})", "",
         f"Written {rep['written_at']}. Variable: {plan['variable']}. Primary metric: **{rep['primary_metric']}** (variant − control, pp).", "",
         f"**Recommendation: {rep['recommendation']}** — {rep['why']}.", "", "## Measured results (per matched pair)", "",
         "| Pair | Variant | Control | Valid | " + " | ".join(f"{k} V / C / Δ" for k in ks) + " |",
         "| --- | --- | --- | --- | " + " | ".join("---" for _ in ks) + " |"]
    f = lambda x: "missing" if x is None else f"{x}"
    for p in rep["pairs"]:
        L.append(f"| {p['pair_id']} | {p['variant']['slot']}, {p['variant']['topic']} | {p['control']['slot']}, {p['control']['topic']} | "
                 f"{'yes' if p['valid'] else 'NO'} | " + " | ".join(f"{f(m['variant'])} / {f(m['control'])} / {f(m['diff_pp'])}" for m in p["metrics"].values()) + " |")
    L += ["", f"Valid pairs with the primary metric: {rep['pairs_with_primary']} · wins: {rep['wins']} · median Δ: {f(rep['median_diff_pp'])} pp · rule: "
          f"≥{rep['decision_rule']['min_wins']} of {rep['decision_rule']['min_pairs']} pairs and median ≥ {rep['decision_rule']['min_median_gain_pp']} pp"
          + (" · **preliminary**" if rep["preliminary"] else ""), "", "## Compliance and confounders per pair", ""]
    L += [f"- {p['pair_id']}: " + ("; ".join(p["confounders"]) or "none recorded") for p in rep["pairs"]]
    L += ["", "## Missing data", ""] + ([f"- {m}" for m in rep["missing"]] or ["- none"])
    L += ["", "## Hypotheses vs evidence", "", "- Measured: only the table above (each value with source, data cutoff and time in observations.jsonl).",
          "- Hypothesis being tested: " + (plan.get("hypothesis") or "-"),
          "- Insufficient evidence: anything below the rule's pair count, from 24 h data only, or from non-compliant pairs (excluded).", "",
          "## Limitations", ""] + [f"- {x}" for x in rep["limitations"]]
    return "\n".join(L) + "\n"


def cmd_status(a) -> dict:
    batch = Path(a.batch); plan = load_plan(batch); obs = read_jsonl(exp_dir(batch) / "observations.jsonl")
    return {"experiment_id": plan["experiment_id"], "slots": [
        {"slot": s["slot"], "pair": s["pair_id"], "arm": s["arm"], "topic": s["topic_key"], "status": slot_rec(batch, s["slot"])["status"],
         "planned": s["planned_publish"], "observations": sorted({o["window"] for o in obs if o["slot"] == s["slot"]})} for s in plan["slots"]]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan"); p.add_argument("--spec", required=True); p.add_argument("--batches-dir", default=os.environ.get("CF_BATCHES_DIR", "batches"))
    p = sub.add_parser("prepare"); p.add_argument("--batch", required=True); p.add_argument("--db")
    p = sub.add_parser("ready"); p.add_argument("--batch", required=True); p.add_argument("--strict", action="store_true", default=True)
    p = sub.add_parser("produce"); p.add_argument("--batch", required=True); p.add_argument("--output-dir", default=os.environ.get("CF_OUTPUT_DIR"))
    p.add_argument("--run-timeout-min", type=int, default=120)
    p = sub.add_parser("drive"); p.add_argument("--batch", required=True); p.add_argument("--run", required=True); p.add_argument("--slot", required=True)
    p.add_argument("--run-timeout-min", type=int, default=120)
    p = sub.add_parser("gate"); p.add_argument("--batch", required=True); p.add_argument("--slot", type=int, required=True); p.add_argument("--measured", action="store_true")
    p = sub.add_parser("sync-gate"); p.add_argument("--batch", required=True); p.add_argument("--slot", type=int, required=True)
    for name in ("check", "observe", "report", "status", "manual-template", "manual", "link"):
        q = sub.add_parser(name); q.add_argument("--batch", required=True)
        if name in ("observe", "link"):
            q.add_argument("--snapshot", default="data/analytics/latest.json")
        if name == "manual":
            q.add_argument("--csv", required=True)
        if name == "link":
            q.add_argument("--slot", type=int); q.add_argument("--video-id"); q.add_argument("--published-at")
    a = ap.parse_args(argv)
    fn = {"plan": cmd_plan, "prepare": cmd_prepare, "ready": cmd_ready, "produce": cmd_produce, "drive": cmd_drive, "gate": cmd_gate, "sync-gate": cmd_sync_gate,
          "check": cmd_check, "link": cmd_link, "observe": cmd_observe, "manual-template": cmd_manual_template, "manual": cmd_manual,
          "report": cmd_report, "status": cmd_status}[a.cmd]
    try:
        if a.cmd == "link" and a.slot and not (a.video_id and a.published_at):
            raise ExpError("--slot needs --video-id and --published-at")
        res = fn(a)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        if a.cmd == "prepare" and str(res.get("status", "")).startswith("NOT READY"):
            return 2
        if a.cmd == "gate" and not res.get("ok"):
            return 3
        if a.cmd == "check" and not res.get("publishable"):
            return 3
        return 0
    except ExpError as e:
        print(json.dumps(e.extra, ensure_ascii=False, indent=1)); return 2 if a.cmd not in ("drive",) else 3
    except IE.BatchRefused as e:
        print(json.dumps(e.payload, ensure_ascii=False, indent=1)); return 2
    except EnvironmentError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False, indent=1)); return 3


if __name__ == "__main__":
    sys.exit(main())
