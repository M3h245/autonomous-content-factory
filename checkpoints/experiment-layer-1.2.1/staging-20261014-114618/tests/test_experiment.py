"""Experiment layer 1.1 (cf-experiment/1): spec + frozen plan, failure-safe prepare/ready, the dedicated driver (phase A →
gate → phase B) with a stub `claude`, the pre-audio compliance gate, control/variant discrimination, word-timing alignment,
observation windows by the Analytics data cutoff, manual entry, weekly report, yt_sync default output folder.

`factory.py init` and `claude` are replaced by stubs here (the real ones need the production machine and a Claude login);
`factory.py reset` and the Idea Engine's `verify_batch` / `run_state` / `produce` are the real ones.

    cd skills && python -m unittest content-factory.tests.test_experiment          (~30 s)
"""
from __future__ import annotations

import copy, csv, hashlib, importlib.util, json, os, shutil, subprocess, sys, tempfile, types, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent if (ROOT.parent / "memory").exists() else ROOT.parent.parent   # skills/ (repo) or .claude/skills/ (installed)
SCRIPTS = ROOT / "content-factory" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import experiment as EX  # noqa: E402
import idea_engine as IE  # noqa: E402
import factory  # noqa: E402

SPEC = REPO / "input" / "experiments" / "EXP-2026W42-beat3to9-c.json"
OLD_SPEC = REPO / "input" / "experiments" / "_superseded" / "EXP-2026W42-beat3to9-b.json"
CFDB = ROOT / "content-database" / "scripts" / "cfdb.py"
CONTROL_B2 = "Scientists argued about this for over a century before agreeing."


class A:  # argparse stand-in
    def __init__(self, **k):
        self.__dict__.update(k)


def compliant_beats(asg: dict) -> list[dict]:
    reveal = EX.spoken_part(asg["planned_reveal"]).strip()
    b2 = ("twist", reveal) if asg["arm"] == "variant" else ("twist", CONTROL_B2)
    rows = [("hook", asg["opening_line"]), b2, ("value", "The mechanism in plain words for a few seconds more."),
            ("payoff", "So that is what is really going on."), ("loop", "Watch it again and look for it.")]
    return [{"id": f"b{i+1}", "role": r, "text": t, "on_screen": None} for i, (r, t) in enumerate(rows)]


def timing_for(beats: list[dict], wps: float = 3.0) -> dict:
    words, t = [], 0.1
    for b in beats:
        for w in b["text"].split():
            words.append({"w": w, "start": round(t, 3), "end": round(t + 1 / wps - 0.02, 3), "sentence": 0}); t += 1 / wps
        t += 0.3
    return {"duration_s": round(t, 2), "words": words}


STUB = r'''
import json, os, re, sys
from pathlib import Path
sys.path.insert(0, os.environ["STUB_SCRIPTS"]); sys.path.insert(0, os.environ["STUB_TESTS"])
import factory
from test_experiment import compliant_beats, timing_for, CONTROL_B2
argv = sys.argv[1:]; prompt = argv[argv.index("-p") + 1]
run = Path(re.search(r"factory run at (.+?) — do not start", prompt).group(1))
with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"run": str(run), "prompt": prompt, "argv_tail": argv[argv.index("-p") + 2:]}) + "\n")
asg = json.loads((run / "experiment_assignment.json").read_text(encoding="utf-8"))
mode = os.environ.get("STUB_MODE", "good"); st = factory.load(run)
v = st["videos"].setdefault("v01", factory.unit("en", None, "i1")); d = run / "videos" / "v01"
if "Then STOP" in prompt:                                  # phase A: hook + script, then stop before AUDIO
    cnt = run / "stub_phase_a_calls"; n = int(cnt.read_text(encoding="utf-8")) + 1 if cnt.exists() else 1; cnt.write_text(str(n), encoding="utf-8")
    beats = compliant_beats(asg)
    if mode == "bad" or (mode == "bad-then-good" and n == 1):
        if asg["arm"] == "variant":                        # setup instead of the reveal
            beats[1] = {"id": "b2", "role": "setup", "text": "Let me explain some background first about how this works.", "on_screen": None}
        else:                                              # control leaks the planned reveal
            beats[1] = {"id": "b2", "role": "twist", "text": asg["planned_reveal"].split("(")[0], "on_screen": None}
    if mode == "bad-opening":
        beats[0]["text"] = "Here is a fun fact about science today."
    (d / "script").mkdir(parents=True, exist_ok=True); (d / "hook").mkdir(parents=True, exist_ok=True)
    (d / "script" / "script.json").write_text(json.dumps({"beats": beats}), encoding="utf-8")
    (d / "hook" / "selected_hook.json").write_text(json.dumps({"text": beats[0]["text"], "archetype": "claim"}), encoding="utf-8")
    for s in ("HOOK", "SCRIPT"):
        v["stages"][s]["status"] = "passed"
    if mode == "runs-audio":                               # misbehaving operator: makes audio in phase A anyway
        v["stages"]["AUDIO"]["status"] = "passed"
elif "approved by the experiment gate" in prompt:        # phase B: audio onwards
    sp = d / "script" / "script.json"; sc = json.loads(sp.read_text(encoding="utf-8"))
    if mode == "b-changes":
        sc["beats"][1] = {"id": "b2", "role": "setup", "text": "Some background first, as usual.", "on_screen": None}
        sp.write_text(json.dumps(sc), encoding="utf-8")
    (d / "audio").mkdir(parents=True, exist_ok=True)
    (d / "audio" / "timing.json").write_text(json.dumps(timing_for(sc["beats"])), encoding="utf-8")
    for s in ("LOCALIZE", "VISUAL_PLAN", "AUDIO", "VIDEO", "SUBTITLES", "QA"):
        if v["stages"][s]["status"] != "skipped":
            v["stages"][s]["status"] = "passed"
factory.save(run, st)
print(json.dumps({"ok": True}))
'''


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cf_exp_"))
        self.spec = json.loads(SPEC.read_text(encoding="utf-8"))
        self.spec_path = self.tmp / "spec.json"; self.spec_path.write_text(json.dumps(self.spec), encoding="utf-8")
        self.batches = self.tmp / "batches"
        self.db = self.tmp / "factory.db"
        subprocess.run([sys.executable, str(CFDB), "import", "--db", str(self.db), "--in", str(REPO / "memory" / "dump.json")],
                       check=True, capture_output=True)
        stub = self.tmp / "stub_claude.py"; stub.write_text(STUB, encoding="utf-8")
        self.stub_log = self.tmp / "claude_calls.jsonl"
        self._env = {k: os.environ.get(k) for k in ("CF_EXPERIMENT_CLAUDE", "STUB_LOG", "STUB_SCRIPTS", "STUB_TESTS", "STUB_MODE")}
        os.environ.update(CF_EXPERIMENT_CLAUDE=f"{sys.executable} {stub}", STUB_LOG=str(self.stub_log),
                          STUB_SCRIPTS=str(SCRIPTS), STUB_TESTS=str(Path(__file__).resolve().parent), STUB_MODE="good")

    def tearDown(self):
        for k, v in self._env.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------------------------------------------------------------- helpers
    def plan(self, spec_path=None):
        return EX.cmd_plan(A(spec=str(spec_path or self.spec_path), batches_dir=str(self.batches)))

    @property
    def batch(self):
        return self.batches / self.spec["experiment_id"]

    def stub_init(self, fail_slots=(), calls=None):
        """Writes what `factory.py init` writes: run.json (brief with the constraints) and state.json."""
        def init(cmd):
            topic = cmd[cmd.index("--topic") + 1]
            if calls is not None:
                calls.append(topic)
            if any(self.spec_topic(n) == topic for n in fail_slots):
                return 2, {"error": "CAPABILITY_MISSING"}
            cons = [cmd[i + 1] for i, x in enumerate(cmd) if x == "--constraint"]
            runs = Path(cmd[cmd.index("--runs-dir") + 1]).resolve(); run = runs / topic[:24].replace(" ", "-").replace("?", "")
            run.mkdir(parents=True)
            i = lambda k: cmd[cmd.index(k) + 1]
            brief = {"run_id": run.name, "topic": topic, "count": int(i("--count")), "languages": i("--languages").split(","),
                     "platforms": ["youtube_shorts", "tiktok", "instagram_reels"],   # factory.py init defaults
                     "duration_s": {"min": float(i("--min-s")), "max": float(i("--max-s"))}, "min_s": float(i("--min-s")),
                     "max_s": float(i("--max-s")), "voices": {}, "music": "procedural", "caption_style": "auto",
                     "visual_style": "doodle", "review_backend": "auto", "hook_engine": "v2", "cta_engine": "v1",
                     "package_engine": "v1", "audience": "general", "tone": "curious, clear, friendly", "constraints": cons, "created_at": EX.now_iso(), "memory": {"db": i("--db")}}
            (run / "run.json").write_text(json.dumps(brief), encoding="utf-8")
            factory.save(run, {"run_id": run.name, "brief": brief, "status": "in_progress", "created_at": brief["created_at"],
                               "global": {s: {"status": "passed", "attempt": 1} for s in factory.GLOBAL_STAGES}, "videos": {},
                               "events": []})
            return 0, {"run": str(run)}
        return init

    def spec_topic(self, slot):
        return EX.load_plan(self.batch)["slots"][slot - 1]["topic"]

    def prepared(self, **kw):
        self.plan()
        r = EX.cmd_prepare(A(batch=str(self.batch), db=str(self.db)), init=self.stub_init(**kw))
        return r, EX.load_plan(self.batch)

    def run_of(self, slot) -> Path:
        return Path(EX.slot_rec(self.batch, slot)["run_dir"])

    def drive(self, slot):
        return EX.cmd_drive(A(batch=str(self.batch), run=str(self.run_of(slot)), slot=str(slot), run_timeout_min=2))

    def calls(self):
        return EX.read_jsonl(self.stub_log)

    # ---------------------------------------------------------------- spec + plan (fix 1: new -c spec, -b preserved)
    def test_c_spec_valid_and_b_preserved(self):
        self.assertEqual(EX.validate_spec(self.spec), [])
        self.assertEqual(self.spec["experiment_id"], "EXP-2026W42-beat3to9-c")
        self.assertIn("EXP-2026W42-beat3to9-b", json.dumps(self.spec.get("supersedes")))
        self.assertEqual(hashlib.sha256(OLD_SPEC.read_bytes()).hexdigest(),
                         "bcfc778b4f5a404660d0d98a7df22e25ca8ced2bcb8a469fb000932a19b93244")      # -b untouched
        openings = {t["topic_key"]: t["opening_line"] for p in self.spec["pairs"] for t in p["topics"]}
        self.assertEqual(openings["blind-spot"], "Each eye has a hole in its view.")
        self.assertEqual(openings["mirror-eye-movement"], "Your mirror can't show your eyes moving.")
        after = next(t for p in self.spec["pairs"] for t in p["topics"] if t["topic_key"] == "afterimage-colors")
        self.assertNotIn("20", after["variant_beat_3_9"]); self.assertIn("YOUR EYES ADD THIS", after["variant_beat_3_9"])

    def test_spec_errors_are_listed(self):
        bad = copy.deepcopy(self.spec)
        bad["pairs"][0]["topics"][0]["opening_line"] = "one two three four five six seven eight nine"
        bad["pairs"][1]["topics"][1]["claims"] = [{"claim": "x"}]
        bad["pairs"][2]["topics"][0]["variant_beat_3_9"] = "(show it)"
        errs = EX.validate_spec(bad)
        self.assertTrue(any("9 words" in e for e in errs)); self.assertTrue(any("needs claim and sources" in e for e in errs))
        self.assertTrue(any("distinctive words" in e for e in errs))

    def test_plan_balanced_alternating_and_control_rule_is_normal(self):
        self.assertEqual(self.plan()["status"], "created")
        plan = EX.load_plan(self.batch)
        self.assertEqual(len(plan["slots"]), 6)
        for p in ("P1", "P2", "P3"):
            self.assertEqual(sorted(s["arm"] for s in plan["slots"] if s["pair_id"] == p), ["control", "variant"])
        vt = [next(s for s in plan["slots"] if s["pair_id"] == p and s["arm"] == "variant")["planned_publish"]["time"] for p in ("P1", "P2", "P3")]
        self.assertEqual(vt, ["18:00", "23:00", "18:00"])
        self.assertEqual([s["paired_slot"] for s in plan["slots"]], [2, 1, 4, 3, 6, 5])
        self.assertIn(sum(1 for s in plan["slots"] if s["arm"] == "variant" and s["slot"] % 2 == 1), (1, 2))
        c = next(s for s in plan["slots"] if s["arm"] == "control"); ctext = " ".join(c["constraints"])
        self.assertIn("exactly as the factory normally would", ctext); self.assertIn("twists", ctext)
        self.assertNotIn("no second surprise", ctext.lower())
        self.assertEqual(plan["engine"], f"experiment {EX.VERSION}")

    def test_plan_write_once_and_edits_refused(self):
        self.plan(); p = self.batch / "experiment" / "plan.json"; first = p.read_bytes()
        self.assertEqual(self.plan()["status"], "unchanged"); self.assertEqual(p.read_bytes(), first)
        other = copy.deepcopy(self.spec); other["hypothesis"] = "changed"
        p2 = self.tmp / "spec2.json"; p2.write_text(json.dumps(other), encoding="utf-8")
        with self.assertRaises(EX.ExpError):
            self.plan(p2)
        self.assertEqual(p.read_bytes(), first)
        d = json.loads(first); d["slots"][0]["arm"] = "variant" if d["slots"][0]["arm"] == "control" else "control"
        p.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaises(EX.ExpError):
            EX.load_plan(self.batch)

    # ---------------------------------------------------------------- fix 4: failure-safe prepare / ready (evidence 1)
    def test_prepare_partial_failure_writes_no_manifest_and_production_is_impossible(self):
        r, plan = self.prepared(fail_slots=(4,))
        self.assertTrue(r["status"].startswith("NOT READY"))
        self.assertFalse((self.batch / "manifest.json").exists())
        with self.assertRaises(IE.BatchRefused):
            IE.verify_batch(self.batch)                       # `idea_engine.py produce` refuses the batch
        rd = EX.cmd_ready(A(batch=str(self.batch)))
        self.assertFalse(rd["ready"]); self.assertTrue(any("slot 4" in p for p in rd["problems"]))
        with self.assertRaises(EX.ExpError):
            EX.cmd_produce(A(batch=str(self.batch), output_dir=None, run_timeout_min=1))
        self.assertEqual(self.calls(), [])                     # no driver was started
        self.assertEqual(EX.main(["ready", "--batch", str(self.batch)]), 2)
        self.assertEqual(EX.main(["produce", "--batch", str(self.batch), "--run-timeout-min", "1"]), 2)

    def test_rerun_retries_only_failed_slot_and_assignments_survive(self):
        _, plan = self.prepared(fail_slots=(4,))
        before = {s["slot"]: (self.run_of(s["slot"]) / "experiment_assignment.json").read_bytes()
                  for s in plan["slots"] if s["slot"] != 4}
        calls = []
        r2 = EX.cmd_prepare(A(batch=str(self.batch), db=str(self.db)), init=self.stub_init(calls=calls))
        self.assertEqual(calls, [self.spec_topic(4)])
        self.assertTrue(r2["status"].startswith("prepared"))
        for n, b in before.items():                           # byte-identical after the rerun
            self.assertEqual((self.run_of(n) / "experiment_assignment.json").read_bytes(), b)
        m = IE.verify_batch(self.batch)
        for s in plan["slots"]:
            run = self.run_of(s["slot"])
            self.assertEqual(json.loads((run / "run.json").read_text(encoding="utf-8"))["constraints"], s["constraints"])
            self.assertEqual(json.loads((run / "experiment_assignment.json").read_text(encoding="utf-8")), EX.assignment_for(plan, s))
            sl = next(x for x in json.loads((self.batch / "slots.json").read_text(encoding="utf-8"))["slots"] if x["slot"] == s["slot"])
            self.assertNotEqual(IE.run_state(run, sl, m)["status"], "foreign")   # manifest created_at precedes the runs
        self.assertTrue(EX.cmd_ready(A(batch=str(self.batch)))["ready"])
        # a third prepare and the Idea Engine's own re-preparation change nothing
        self.assertEqual(EX.cmd_prepare(A(batch=str(self.batch), db=str(self.db)), init=self.stub_init(calls=calls))["status"], "already prepared")
        IE.produce(self.batch, types.SimpleNamespace(produce="none"))
        self.assertEqual(calls, [self.spec_topic(4)])
        self.assertTrue(EX.cmd_ready(A(batch=str(self.batch)))["ready"])

    def test_ready_detects_tampered_assignment_or_constraints(self):
        _, plan = self.prepared()
        self.assertTrue(EX.cmd_ready(A(batch=str(self.batch)))["ready"])
        ap = self.run_of(2) / "experiment_assignment.json"; a = json.loads(ap.read_text(encoding="utf-8"))
        a["arm"] = "variant" if a["arm"] == "control" else "control"; ap.write_text(json.dumps(a), encoding="utf-8")
        rp = self.run_of(5) / "run.json"; b = json.loads(rp.read_text(encoding="utf-8")); b["constraints"] = b["constraints"][:2]; rp.write_text(json.dumps(b), encoding="utf-8")
        rd = EX.cmd_ready(A(batch=str(self.batch)))
        self.assertFalse(rd["ready"])
        self.assertTrue(any("slot 2" in p and "assignment" in p for p in rd["problems"]))
        self.assertTrue(any("slot 5" in p and "constraints" in p for p in rd["problems"]))
        with self.assertRaises(EX.ExpError):
            self.drive(2)

    # ---------------------------------------------------------------- fix 2: driver gets the rules (evidence 2)
    def test_driver_prompt_carries_assignment_and_gate_precedes_audio(self):
        _, plan = self.prepared()
        for s in plan["slots"]:
            r = self.drive(s["slot"]); self.assertTrue(r["gate"])
        calls = self.calls(); self.assertEqual(len(calls), 12)           # 6 × (phase A + phase B)
        for s in plan["slots"]:
            mine = [c for c in calls if c["run"] == str(self.run_of(s["slot"]))]
            a, b = mine[0]["prompt"], mine[1]["prompt"]
            self.assertIn(plan["experiment_id"], a); self.assertIn(plan["plan_sha256"][:12], a)
            self.assertIn(f"Arm: {s['arm'].upper()}", a); self.assertIn(s["topic_spec"]["opening_line"], a)
            self.assertIn(s["topic_spec"]["frame0_visual"], a); self.assertIn(s["topic_spec"]["variant_beat_3_9"], a)
            self.assertIn("TREATMENT" if s["arm"] == "variant" else "CONTROL", a)
            self.assertIn("do not run it", a); self.assertIn("Never publish", a)
            self.assertIn("Do not change the hook or the script", b)
            self.assertEqual(mine[0]["argv_tail"][:4], ["--permission-mode", "acceptEdits", "--permission-prompts", "none"])
            rec = EX.slot_rec(self.batch, s["slot"])
            self.assertEqual(rec["status"], "gate_passed"); self.assertFalse(rec["gate"]["attempts"][0]["audio_already_ran"])
            self.assertTrue((self.run_of(s["slot"]) / "experiment_gate.json").exists())

    def test_produce_uses_the_experiment_driver_for_every_slot(self):
        _, plan = self.prepared()
        res = EX.cmd_produce(A(batch=str(self.batch), output_dir=None, run_timeout_min=2))
        self.assertIn(" drive --batch {batch} --run {run} --slot {slot}", res["driver_cmd"])
        self.assertEqual(len(res["slots"]), 6)
        runs = {c["run"] for c in self.calls() if "Then STOP" in c["prompt"]}
        self.assertEqual(runs, {str(self.run_of(s["slot"])) for s in plan["slots"]})
        self.assertTrue(all(EX.slot_rec(self.batch, s["slot"])["gate"]["approved"] for s in plan["slots"]))

    def test_produce_preflight_and_windows_cmd_shim(self):
        self.prepared()
        os.environ.pop("CF_EXPERIMENT_CLAUDE")
        old = EX.shutil.which; EX.shutil.which = lambda name: None          # no claude on PATH
        try:
            with self.assertRaises(EX.ExpError) as cm:
                EX.cmd_produce(A(batch=str(self.batch), output_dir=None, run_timeout_min=1))
            self.assertIn("environment", str(cm.exception)); self.assertEqual(self.calls(), [])
            EX.shutil.which = lambda name: r"C:\Users\x\AppData\Roaming\npm\claude.cmd"
            argv = EX.claude_argv('say "hi" & 59% <ok> | ^', Path("b"))
            self.assertTrue(argv[0].endswith("claude.cmd")); self.assertFalse(set('"&%<>|^') & set(argv[2]))
        finally:
            EX.shutil.which = old

    # ---------------------------------------------------------------- fix 2: non-compliant script blocked before audio (evidence 3)
    def test_noncompliant_script_is_blocked_before_audio(self):
        _, plan = self.prepared(); os.environ["STUB_MODE"] = "bad"
        for s in plan["slots"][:2]:                                      # one variant, one control (pair P1)
            with self.assertRaises(EX.ExpError) as cm:
                self.drive(s["slot"])
            self.assertIn("blocked before audio", str(cm.exception))
            run = self.run_of(s["slot"]); mine = [c for c in self.calls() if c["run"] == str(run)]
            self.assertEqual(len(mine), EX.MAX_REPAIRS + 1)               # only phase-A sessions
            self.assertTrue(all("Then STOP" in c["prompt"] for c in mine))
            self.assertIn("rejected by the experiment gate", mine[1]["prompt"])
            v = factory.load(run)["videos"]["v01"]["stages"]
            self.assertNotIn(v["AUDIO"]["status"], factory.DONE)
            self.assertFalse((run / "videos" / "v01" / "audio" / "timing.json").exists())
            self.assertEqual(v["SCRIPT"]["status"], "pending")            # reset by the real `factory.py reset`
            ev = [e for e in factory.load(run)["events"] if e.get("decision", {}).get("action") == "human_reset"]
            self.assertEqual(len(ev), EX.MAX_REPAIRS + 1)
            rec = EX.slot_rec(self.batch, s["slot"])
            self.assertEqual(rec["status"], "blocked"); self.assertFalse(rec["gate"]["approved"])
            self.assertTrue(rec["gate"]["attempts"][-1]["issues"])
        self.assertEqual(EX.main(["drive", "--batch", str(self.batch), "--run", str(self.run_of(1)), "--slot", "1",
                                  "--run-timeout-min", "1"]), 3)

    def test_bad_opening_resets_hook_and_repair_then_passes(self):
        _, plan = self.prepared(); os.environ["STUB_MODE"] = "bad-opening"
        with self.assertRaises(EX.ExpError):
            self.drive(1)
        self.assertEqual(factory.load(self.run_of(1))["videos"]["v01"]["stages"]["HOOK"]["status"], "pending")
        os.environ["STUB_MODE"] = "bad-then-good"
        r = self.drive(3); self.assertTrue(r["gate"])
        rec = EX.slot_rec(self.batch, 3)
        self.assertEqual([x["ok"] for x in rec["gate"]["attempts"]], [False, True])

    def test_script_changed_in_phase_b_is_flagged_noncompliant(self):
        _, plan = self.prepared()
        v = next(s for s in plan["slots"] if s["arm"] == "variant")
        os.environ["STUB_MODE"] = "b-changes"
        r = self.drive(v["slot"])
        self.assertEqual(r["status"], "noncompliant")
        self.assertIn("changed_after_approval", EX.slot_rec(self.batch, v["slot"])["gate"])
        chk = EX.cmd_check(A(batch=str(self.batch)))
        row = next(x for x in chk["slots"] if x["slot"] == v["slot"])
        self.assertEqual(row["status"], "noncompliant"); self.assertFalse(chk["publishable"])

    # ---------------------------------------------------------------- fix 3: control vs variant discrimination (evidence 4)
    def test_compliant_scripts_pass_their_arm_and_fail_the_other(self):
        self.plan(); plan = EX.load_plan(self.batch)
        for s in plan["slots"]:
            asg = EX.asg_with_words(plan, s); beats = compliant_beats(asg); sc = {"beats": beats}
            other = dict(asg, arm="control" if asg["arm"] == "variant" else "variant")
            for timing in (None, timing_for(beats)):                       # pre-audio estimate and measured
                ok = EX.evaluate(sc, timing, asg); bad = EX.evaluate(sc, timing, other)
                self.assertTrue(ok["ok"], (s["topic_key"], s["arm"], ok["issues"]))
                self.assertFalse(bad["ok"], (s["topic_key"], other["arm"]))
                key = "appears in the first 9 s" if other["arm"] == "control" else "does not start between"
                self.assertTrue(any(key in i for i in bad["issues"]), bad["issues"])

    def test_control_may_have_its_own_twist_and_variant_rules(self):
        self.plan(); plan = EX.load_plan(self.batch)
        c = EX.asg_with_words(plan, next(s for s in plan["slots"] if s["arm"] == "control"))
        beats = compliant_beats(c); beats[1] = {"id": "b2", "role": "twist", "text": "But here is the twist nobody expects about it.", "on_screen": None}
        self.assertTrue(EX.evaluate({"beats": beats}, None, c)["ok"])      # a normal second surprise is allowed in control
        v = EX.asg_with_words(plan, next(s for s in plan["slots"] if s["arm"] == "variant"))
        vb = compliant_beats(v); vb.insert(1, {"id": "bx", "role": "setup", "text": "First some background.", "on_screen": None})
        r = EX.evaluate({"beats": vb}, None, v)
        self.assertFalse(r["ok"]); self.assertTrue(any("setup" in i for i in r["issues"]))
        vb = compliant_beats(v); vb.insert(1, {"id": "by", "role": "value", "text": v["opening_line"], "on_screen": None})
        self.assertTrue(any("repeats the hook" in i for i in EX.evaluate({"beats": vb}, None, v)["issues"]))

    def test_opening_question_and_override(self):
        self.plan(); plan = EX.load_plan(self.batch); a = EX.asg_with_words(plan, plan["slots"][0])
        beats = compliant_beats(a)
        beats[0]["text"] = "Here is a fun fact about science."
        r = EX.evaluate({"beats": beats}, None, a); self.assertTrue(any(i.startswith("opening") for i in r["issues"]))
        r = EX.evaluate({"beats": beats}, None, a, {"opening_line_reason": "dossier: the claim needs a qualifier"})
        self.assertFalse(any(i.startswith("opening") for i in r["issues"])); self.assertTrue(r["notes"])
        beats[0]["text"] = "One two three four five six seven eight nine."
        self.assertTrue(any("9 words" in i for i in EX.evaluate({"beats": beats}, None, a, {"opening_line_reason": "x"})["issues"]))
        q = compliant_beats(a); q[0]["text"] = "Does each eye have a hole in its view?"; q[1]["pause_before"] = 3.0
        self.assertTrue(any("not answered within 2 s" in i for i in EX.evaluate({"beats": q}, None, a)["issues"]))
        q[1]["pause_before"] = 0
        self.assertFalse(any("question" in i for i in EX.evaluate({"beats": q}, None, a)["issues"]))
        tm = timing_for(q); n = len(q[0]["text"].split())
        for w in tm["words"][n:]:
            w["start"] += 2.5; w["end"] += 2.5                                 # measured silence after the question
        self.assertTrue(any("not answered" in i for i in EX.evaluate({"beats": q}, tm, a)["issues"]))

    # ---------------------------------------------------------------- word-to-TTS alignment
    def test_alignment_verified_and_mismatch_flagged(self):
        self.plan(); plan = EX.load_plan(self.batch)
        a = EX.asg_with_words(plan, next(s for s in plan["slots"] if s["arm"] == "variant"))
        beats = compliant_beats(a); tm = timing_for(beats)
        r = EX.evaluate({"beats": beats}, tm, a); self.assertTrue(r["timing"]["aligned"]); self.assertTrue(r["ok"])
        tm2 = copy.deepcopy(tm); tm2["words"][5]["w"] = "banana"
        r = EX.evaluate({"beats": beats}, tm2, a)
        self.assertFalse(r["timing"]["aligned"]); self.assertTrue(any("do not align" in i for i in r["issues"]))
        tm3 = copy.deepcopy(tm); tm3["words"].pop()
        self.assertFalse(EX.evaluate({"beats": beats}, tm3, a)["timing"]["aligned"])

    def test_real_produced_runs_align_token_for_token(self):
        runs = sorted(p.parents[3] for p in (REPO / "batches").glob("2026*/runs/*/videos/v01/audio/timing.json"))
        if not runs:
            self.skipTest("no produced runs in this checkout")
        for run in runs:
            sc = json.loads((run / "videos/v01/script/script.json").read_text(encoding="utf-8"))
            tm = json.loads((run / "videos/v01/audio/timing.json").read_text(encoding="utf-8"))
            beats, info = EX.beat_times(sc, tm)
            self.assertTrue(info["aligned"], (run.name, info["mismatches"]))
            est, _ = EX.beat_times(sc, None)
            self.assertLess(abs(est[1]["start"] - beats[1]["start"]), 1.0, run.name)   # pre-audio estimate is close

    # ---------------------------------------------------------------- post-production check, link, observe, report
    def produced_batch(self):
        _, plan = self.prepared()
        for s in plan["slots"]:
            self.drive(s["slot"])
            run = self.run_of(s["slot"]); (run / "package" / "v01").mkdir(parents=True, exist_ok=True)
            (run / "package" / "v01" / "publishing_package.json").write_text(json.dumps({"public": {"title": f"Title {s['slot']}"}}), encoding="utf-8")
        chk = EX.cmd_check(A(batch=str(self.batch)))
        self.assertTrue(chk["publishable"], chk)
        return plan

    def snapshot(self, pulled_at, videos, per_video, last_day):
        p = self.tmp / f"snap-{len(list(self.tmp.glob('snap-*')))}.json"
        daily = [{"day": d} for d in ([last_day] if last_day else [])]
        p.write_text(json.dumps({"pulled_at": pulled_at, "until": pulled_at[:10], "videos": videos, "per_video": per_video,
                                 "channel_daily": daily}), encoding="utf-8")
        return p

    def vids(self, plan, published="2026-10-09T16:00:00Z", **over):
        return [{"video_id": f"vid{s['slot']}", "title": f"Title {s['slot']}", "privacy": "public", "published_at": published,
                 "views": 1000, "engagedViews": 350, "averageViewDuration": 15, "averageViewPercentage": 55.0, "likes": 12,
                 "comments": 1, "subscribersGained": 0, **over} for s in plan["slots"]]

    def test_observation_window_uses_analytics_cutoff_not_pull_time(self):
        plan = self.produced_batch(); vids = self.vids(plan)
        curve = [{"elapsedVideoTimeRatio": x / 100, "audienceWatchRatio": 1.1 - x / 100} for x in range(1, 101)]
        per = {v["video_id"]: {"retention": curve} for v in vids}
        # the real situation on 13 Oct: pulled 2026-10-13 16:06Z, Analytics processed through 2026-10-10 (PT)
        snap = self.snapshot("2026-10-13T16:06:08+00:00", vids, per, "2026-10-10")
        self.assertTrue(all(x["status"] == "linked" for x in EX.cmd_link(A(batch=str(self.batch), snapshot=str(snap), slot=None))["linked"]))
        o = EX.cmd_observe(A(batch=str(self.batch), snapshot=str(snap)))
        self.assertEqual(o["analytics_cutoff_day"], "2026-10-10")
        for x in o["observations"]:
            self.assertEqual(x["data_age_hours"], 39.0)        # cutoff 2026-10-11T07:00Z − publish 2026-10-09T16:00Z
            self.assertEqual(x["pull_age_hours"], 96.1)        # by pull time it would have been labelled 72h
            self.assertEqual(x["window"], "24h")
        rows = EX.read_jsonl(self.batch / "experiment" / "observations.jsonl"); self.assertEqual(len(rows), 6)
        r0 = rows[0]
        self.assertEqual(r0["analytics_cutoff_utc"], "2026-10-11T07:00:00+00:00")
        self.assertIsNone(r0["metrics"]["stayed_to_watch"]["value"]); self.assertEqual(r0["metrics"]["stayed_to_watch"]["status"], "manual_required")
        self.assertIn("data through 2026-10-10", r0["metrics"]["views"]["source"])
        self.assertIsNotNone(r0["metrics"]["retention_8s"]["value"])
        EX.cmd_observe(A(batch=str(self.batch), snapshot=str(snap)))      # same cutoff again: not duplicated
        self.assertEqual(len(EX.read_jsonl(self.batch / "experiment" / "observations.jsonl")), 6)
        snap2 = self.snapshot("2026-10-14T09:00:00+00:00", vids, per, "2026-10-12")
        o2 = EX.cmd_observe(A(batch=str(self.batch), snapshot=str(snap2)))
        self.assertTrue(all(x["window"] == "72h" and x["data_age_hours"] == 87.0 for x in o2["observations"]))

    def test_observe_without_cutoff_or_before_publication_records_missing(self):
        plan = self.produced_batch(); vids = self.vids(plan, published="2026-10-12T16:00:00Z")
        snap = self.snapshot("2026-10-13T16:06:08+00:00", vids, {}, "2026-10-10")
        EX.cmd_link(A(batch=str(self.batch), snapshot=str(snap), slot=None))
        o = EX.cmd_observe(A(batch=str(self.batch), snapshot=str(snap)))
        self.assertTrue(all(x["window"] == "before_publication" for x in o["observations"]))
        row = EX.read_jsonl(self.batch / "experiment" / "observations.jsonl")[0]
        self.assertTrue(all(m["value"] is None for m in row["metrics"].values()))
        snap2 = self.snapshot("2026-10-15T16:06:08+00:00", vids, {}, None)
        o2 = EX.cmd_observe(A(batch=str(self.batch), snapshot=str(snap2)))
        self.assertTrue(all(x["window"] == "unknown" for x in o2["observations"]))

    def test_manual_entry_and_report_excludes_noncompliant(self):
        plan = self.produced_batch()
        for s in plan["slots"]:
            EX.cmd_link(A(batch=str(self.batch), snapshot=None, slot=s["slot"], video_id=f"v{s['slot']}",
                          published_at="2026-10-15T18:00:00+02:00"))
        vids, per = [], {}
        for s in plan["slots"]:
            vids.append({"video_id": f"v{s['slot']}", "title": "x", "privacy": "public", "published_at": "2026-10-15T16:00:00Z",
                         "views": 999999 if s["arm"] == "control" else 10, "engagedViews": 300, "averageViewDuration": 15,
                         "averageViewPercentage": 55.0, "likes": 10, "comments": 0, "subscribersGained": 0})
            top = 0.85 if s["arm"] == "variant" else 0.70
            per[f"v{s['slot']}"] = {"retention": [{"elapsedVideoTimeRatio": x / 100, "audienceWatchRatio": top} for x in range(1, 101)]}
        snap = self.snapshot("2026-10-19T09:00:00+00:00", vids, per, "2026-10-18")   # data age 79 h → 72h
        EX.cmd_observe(A(batch=str(self.batch), snapshot=str(snap)))
        t = EX.cmd_manual_template(A(batch=str(self.batch)))
        with self.assertRaises(EX.ExpError):
            EX.cmd_manual_template(A(batch=str(self.batch)))
        with open(t["template"], encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        rows[0]["value"] = "41.5"; rows[0]["observed_at"] = "2026-10-16T19:00:00+02:00"
        rows[2]["value"] = "38.0"; rows[2]["observed_at"] = "bad-date"
        with open(t["template"], "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=EX.MANUAL_FIELDS); w.writeheader(); w.writerows(rows)
        mres = EX.cmd_manual(A(batch=str(self.batch), csv=t["template"]))
        self.assertEqual(len(mres["added"]), 1); self.assertTrue(any("unreadable" in s["why"] for s in mres["skipped"]))
        EX.cmd_report(A(batch=str(self.batch)))
        data = json.loads(sorted((self.batch / "experiment" / "reports").glob("*.json"))[-1].read_text(encoding="utf-8"))
        self.assertEqual((data["pairs_with_primary"], data["wins"], data["median_diff_pp"]), (3, 3, 15.0))
        self.assertTrue(data["preliminary"]); self.assertEqual(data["recommendation"], "continue testing")
        self.assertTrue(any("stayed_to_watch" in x for x in data["missing"]))
        self.assertNotIn("views", data["pairs"][0]["metrics"])
        rec = EX.slot_rec(self.batch, 1); EX.save_slot(self.batch, rec, "noncompliant")   # one non-compliant run
        EX.cmd_report(A(batch=str(self.batch)))
        data = json.loads(sorted((self.batch / "experiment" / "reports").glob("*.json"))[-1].read_text(encoding="utf-8"))
        self.assertEqual(data["pairs_with_primary"], 2); self.assertEqual(data["excluded_pairs_noncompliant"], ["P1"])

    def test_report_without_data_is_insufficient(self):
        self.prepared()
        self.assertEqual(EX.cmd_report(A(batch=str(self.batch)))["recommendation"], "insufficient evidence")

    # ---------------------------------------------------------------- 1.2: gate requires V3.0.1's SCRIPT pass; sync-gate
    def recovered_run(self, slot: int, script_status="passed", compliant=True):
        """The state after a human `factory.py reset` + re-recorded SCRIPT: SCRIPT passed in V3.0.1, slot still `blocked`."""
        plan = EX.load_plan(self.batch); s = EX.plan_slot(plan, slot); run = self.run_of(slot)
        asg = EX.assignment_for(plan, s); beats = compliant_beats(asg)
        if not compliant:                                    # breaks the arm rule only (factory checks would not see it)
            beats[1]["text"] = CONTROL_B2 if asg["arm"] == "variant" else asg["planned_reveal"].split("(")[0]
        d = run / "videos" / "v01"; (d / "script").mkdir(parents=True, exist_ok=True); (d / "hook").mkdir(parents=True, exist_ok=True)
        sp = d / "script" / "script.json"; sp.write_text(json.dumps({"beats": beats}), encoding="utf-8")
        (d / "hook" / "selected_hook.json").write_text(json.dumps({"spoken_text": beats[0]["text"]}), encoding="utf-8")
        rp = d / "script" / "result.json"
        rp.write_text(json.dumps({"stage": "SCRIPT", "status": script_status, "attempt": 1,
                                  "outputs": [{"role": "script", "sha256": EX.sha_file(sp)}]}), encoding="utf-8")
        st = factory.load(run); v = st["videos"].setdefault("v01", factory.unit("en", None, "i1"))
        v["stages"]["HOOK"]["status"] = "passed"
        v["stages"]["SCRIPT"].update(status=script_status, attempt=1, result=str(rp), result_sha256=EX.sha_file(rp))
        for k in ("AUDIO", "VISUAL_PLAN", "VIDEO", "SUBTITLES", "QA", "PACKAGE"):
            v["stages"][k]["status"] = "stale"
        factory.save(run, st)
        rec = EX.slot_rec(self.batch, slot); rec["gate"] = {"approved": False, "attempts": []}
        EX.save_slot(self.batch, rec, "blocked", note="phase A ended without a passed SCRIPT (driver exit 0)")
        return plan, s, run

    def snapshot_files(self) -> dict:
        return {p.relative_to(self.batch).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(self.batch.rglob("*")) if p.is_file()}

    def no_execution(self):
        """Every way sync-gate could run something: a subprocess, a Claude session, a factory reset, drive or produce."""
        def boom(*a, **k):
            raise AssertionError("sync-gate must not execute anything")
        saved = (EX.subprocess.run, EX.run_claude, EX.factory_reset, EX.cmd_drive, EX.cmd_produce, IE.produce)
        EX.subprocess.run = boom; EX.run_claude = boom; EX.factory_reset = boom; EX.cmd_drive = boom; EX.cmd_produce = boom; IE.produce = boom
        def restore():
            EX.subprocess.run, EX.run_claude, EX.factory_reset, EX.cmd_drive, EX.cmd_produce, IE.produce = saved
        self.addCleanup(restore)

    def test_gate_is_not_ok_while_factory_script_is_not_passed(self):
        self.prepared()
        for status in ("failed", "pending"):
            self.recovered_run(2, script_status=status)
            r = EX.cmd_gate(A(batch=str(self.batch), slot=2, measured=False))
            self.assertFalse(r["ok"]); self.assertEqual(r["factory_script"]["status"], status)
            self.assertTrue(any("factory SCRIPT stage" in i for i in r["issues"]))
            self.assertEqual(EX.main(["gate", "--batch", str(self.batch), "--slot", "2"]), 3)
        self.recovered_run(2)
        r = EX.cmd_gate(A(batch=str(self.batch), slot=2, measured=False))
        self.assertTrue(r["ok"], r["issues"]); self.assertEqual(r["factory_script"]["status"], "passed")
        self.assertFalse((self.run_of(2) / "experiment_gate.json").exists())     # gate is read only

    def test_sync_gate_records_only_the_gate(self):
        _, plan = self.prepared(); _, s, run = self.recovered_run(2)
        hist_before = EX.slot_rec(self.batch, 2)["history"]; before = self.snapshot_files()
        self.no_execution()
        r = EX.cmd_sync_gate(A(batch=str(self.batch), slot=2))
        self.assertTrue(r["synced"]); self.assertEqual((r["previous_status"], r["status"]), ("blocked", "gate_passed"))
        after = self.snapshot_files()
        changed = {k for k in after if before.get(k) != after[k]}
        self.assertEqual(changed, {"experiment/slots/02.json", (run / "experiment_gate.json").relative_to(self.batch).as_posix()})
        rec = EX.slot_rec(self.batch, 2)
        self.assertEqual(rec["history"][:len(hist_before)], hist_before)               # history kept, one entry appended
        self.assertEqual(len(rec["history"]), len(hist_before) + 1); self.assertIn("sync-gate", rec["history"][-1]["note"])
        g = rec["gate"]
        self.assertTrue(g["approved"]); self.assertEqual(g["approved_by"], "sync-gate")
        self.assertEqual(g["script_sha256"], EX.sha_file(run / "videos/v01/script/script.json"))
        self.assertEqual(g["attempts"][-1]["source"], "sync-gate")
        st = factory.load(run)["videos"]["v01"]["stages"]
        self.assertEqual([st[k]["status"] for k in ("SCRIPT", "AUDIO")], ["passed", "stale"])   # no stage ran
        self.assertEqual(self.calls(), [])                                             # no Claude session
        self.assertTrue(EX.cmd_ready(A(batch=str(self.batch)))["ready"])
        with self.assertRaises(EX.ExpError):                                           # a second sync changes nothing
            EX.cmd_sync_gate(A(batch=str(self.batch), slot=2))
        self.assertEqual(self.snapshot_files(), after)

    def test_after_sync_drive_skips_phase_a(self):
        _, plan = self.prepared(); self.recovered_run(2)
        EX.cmd_sync_gate(A(batch=str(self.batch), slot=2))
        self.drive(2)
        prompts = [c["prompt"] for c in self.calls()]
        self.assertEqual(len(prompts), 1); self.assertIn("approved by the experiment gate", prompts[0])

    def test_sync_gate_refuses_without_writing(self):
        cases = {
            "script failed": lambda run: self.recovered_run(2, script_status="failed"),
            "arm rule broken": lambda run: self.recovered_run(2, compliant=False),
            "audio already passed": lambda run: self._edit_state(run, lambda v: v["stages"]["AUDIO"].update(status="passed")),
            "video escalated": lambda run: self._edit_state(run, lambda v: v.update(status="escalated")),
            "result not the recorded one": lambda run: (run / "videos/v01/script/result.json").write_text(
                (run / "videos/v01/script/result.json").read_text(encoding="utf-8") + " ", encoding="utf-8"),
            "script edited after the gate": lambda run: (run / "videos/v01/script/script.json").write_text(
                (run / "videos/v01/script/script.json").read_text(encoding="utf-8") + " ", encoding="utf-8"),
            "run locked": lambda run: (run / ".lock").write_text("{}", encoding="utf-8"),
            "batch locked": lambda run: (self.batch / ".lock").write_text("{}", encoding="utf-8"),
            "assignment tampered": lambda run: (run / "experiment_assignment.json").write_text("{}", encoding="utf-8"),
            "slot already approved": lambda run: EX.save_slot(self.batch, {**EX.slot_rec(self.batch, 2),
                                                                           "gate": {"approved": True, "attempts": []}}, None),
            "slot already produced": lambda run: EX.save_slot(self.batch, EX.slot_rec(self.batch, 2), "produced"),
        }
        _, plan = self.prepared()
        self.no_execution()
        for name, breakit in cases.items():
            with self.subTest(name):
                _, s, run = self.recovered_run(2)
                for lk in (run / ".lock", self.batch / ".lock"):
                    if lk.exists():
                        lk.unlink()
                ap = run / "experiment_assignment.json"; EX.write_json(ap, EX.assignment_for(plan, s))
                breakit(run)
                before = self.snapshot_files()
                with self.assertRaises(EX.ExpError) as cm:
                    EX.cmd_sync_gate(A(batch=str(self.batch), slot=2))
                self.assertIn("nothing was written", str(cm.exception))
                self.assertEqual(self.snapshot_files(), before, name)
                self.assertFalse((run / "experiment_gate.json").exists())
        for lk in (self.run_of(2) / ".lock", self.batch / ".lock"):
            if lk.exists():
                lk.unlink()
        self.assertEqual(EX.main(["sync-gate", "--batch", str(self.batch), "--slot", "1"]), 2)   # slot 1: SCRIPT never passed

    def _edit_state(self, run, fn):
        st = factory.load(run); fn(st["videos"]["v01"]); factory.save(run, st)

    def test_assignment_keeps_the_plan_engine_after_an_upgrade(self):
        _, plan = self.prepared()
        a = json.loads((self.run_of(1) / "experiment_assignment.json").read_text(encoding="utf-8"))
        self.assertEqual(a["engine"], plan["engine"])
        old = dict(plan, engine="experiment 1.1")
        self.assertEqual(EX.assignment_for(old, plan["slots"][0])["engine"], "experiment 1.1")

    # ---------------------------------------------------------------- yt_sync default output folder
    def test_yt_sync_default_out_is_repo_data_analytics(self):
        p = REPO / "tools" / "youtube_sync" / "yt_sync.py"
        spec = importlib.util.spec_from_file_location("yt_sync_t", p); m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        self.assertEqual(m.DEFAULT_OUT, (REPO / "data" / "analytics").resolve())


if __name__ == "__main__":
    unittest.main()
