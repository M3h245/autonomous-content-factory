"""Phase 5 (v3.0.0) — production readiness.

Reproducible TTS · run locks · no silent failures · capability gating · doodle-fallback gate · whole-number claim checks ·
content memory (default database, topic and hook repetition, automatic ingest) · batch isolation.

    cd skills && python -m unittest content-factory.tests.test_phase5        (~4 min; TTS tests skip without Kokoro)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent
for p in (ROOT / "content-factory" / "scripts", ROOT / "content-database" / "scripts", Path(__file__).resolve().parent):
    sys.path.insert(0, str(p))
import cfdb  # noqa: E402
import factory as F  # noqa: E402
import phase2_kit as K  # noqa: E402
from cf_common import StageResult, read_json, write_json  # noqa: E402

PY = sys.executable
FACT = ROOT / "content-factory" / "scripts" / "factory.py"
CFDB = ROOT / "content-database" / "scripts" / "cfdb.py"
TTS = ROOT / "voice-production" / "scripts" / "tts.py"
SB = ROOT / "visual-storyboarding" / "scripts" / "storyboard_tool.py"
KOKORO = all((Path(os.environ.get("CF_CACHE", Path.home() / ".cache" / "content-factory")) / "kokoro" / f).exists()
             for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"))
KNUCKLES = REPO / "fixtures" / "phase4_package_run" / "2026-10-07-why-your-knuckles-crack"
SEED = REPO / "seeds" / "2026-10-07-why-ice-cream-gives-you-brain-fr"

PAST = ["Why fingers wrinkle in water", "Why onions make you cry", "Why your knuckles crack",
        "Why ice cream gives you brain freeze", "Why you can't tickle yourself"]
PAST_TITLES = ["Eating fast doubles your odds of brain freeze", "Pruney fingers? Not water. Nerves."]
REPEATS = ["Why do fingers wrinkle in water?", "Why do our fingers get wrinkly in the bath", "Why cutting onions makes you cry",
           "Why onions make your eyes water", "What makes your knuckles crack", "Is cracking your knuckles bad?",
           "What causes brain freeze", "Why can't you tickle yourself?", "Brain freeze", "Knuckle cracking",
           "why do onions make us cry", "Why ice cream hurts your head"]
NEW = ["Why flamingos stand on one leg", "Why the Moon looks bigger near the horizon", "Why leap years skip some century years",
       "Why cats always land on their feet", "Why your voice sounds weird on recordings", "Why we get goosebumps",
       "Why ice floats on water", "Why your fingers get cold first", "Why bread goes stale", "How water towers work",
       "Why your stomach growls", "Why flamingos are pink", "Why the sky is blue", "Why you yawn", "Why cold water feels wet"]


def tmpdir(tag: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=f"p5{tag}_"))


def init(runs: Path, topic: str, *extra: str, count: int = 1, env: dict | None = None) -> tuple[int, dict]:
    p = subprocess.run([PY, str(FACT), "init", "--topic", topic, "--count", str(count), "--runs-dir", str(runs), *extra],
                       capture_output=True, text=True, env=env)
    try:
        return p.returncode, json.loads(p.stdout)
    except ValueError:
        return p.returncode, {"raw": (p.stdout + p.stderr)[-2000:]}


def fact(run: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, str(FACT), *args, "--run", str(run)], capture_output=True, text=True)


def memory_with(db: Path, topics=PAST, titles=PAST_TITLES) -> None:
    con = cfdb.connect(str(db))
    for i, t in enumerate(topics):
        cfdb.upsert(con, "runs", {"run_id": f"past-{i}", "topic": t, "created_at": "2026-10-01", "brief_json": "{}", "status": "done"})
    for i, t in enumerate(titles):
        cfdb.upsert(con, "videos", {"video_id": "v01", "run_id": f"past-t{i}", "title": t, "hook": t})
    con.commit()
    con.close()


# ============================================================================= reproducible TTS
@unittest.skipUnless(KOKORO, "Kokoro model not installed (setup_env.py)")
class SeededTTS(unittest.TestCase):
    """Phase 5 finding: unseeded random ops in the Kokoro graph made every fresh synthesis different; earlier replays
    matched only through the sentence cache. Seeded per sentence, the voice is a pure function of its inputs."""

    def synth(self, work: Path, cpus: str | None) -> bytes:
        work.mkdir(parents=True, exist_ok=True)
        beats = [{"id": "b1", "role": "hook", "text": "Flamingos sleep on one leg.", "claim_ids": []},
                 {"id": "b2", "role": "value", "text": "Even asleep, they barely sway.", "claim_ids": []},
                 {"id": "b3", "role": "payoff", "text": "And a dead one can still balance.", "claim_ids": []}]
        write_json(work / "s.json", {"video_id": "t", "language": "en", "beats": beats,
                                     "publish": {"title_options": ["t"], "description": "", "hashtags": []}})
        cmd = [PY, str(TTS), "synth", "--script", work / "s.json", "--out-dir", work, "--result", work / "r.json", "--voice",
               "af_heart", "--min-s", "0.5", "--max-s", "99"]
        if cpus and shutil.which("taskset"):
            cmd = ["taskset", "-c", cpus] + cmd
        env = {**os.environ, "CF_TTS_CACHE_DIR": str(work / "cache")}       # empty cache: real synthesis, no reuse
        p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stdout[-800:] + p.stderr[-800:])
        self.assertEqual(read_json(work / "r.json")["metrics"]["tts_cache"]["hits"], 0)
        return (work / "voice.wav").read_bytes()

    def test_fresh_synthesis_is_identical_across_processes_and_cpu_sets(self):
        d = tmpdir("tts")
        a = self.synth(d / "a", None)
        b = self.synth(d / "b", "0" if (os.cpu_count() or 1) > 1 else None)
        self.assertEqual(a, b, "two fresh syntheses of the same script must be byte-identical")
        shutil.rmtree(d, ignore_errors=True)


# ============================================================================= run locks
class RunLock(unittest.TestCase):
    def setUp(self):
        self.runs = tmpdir("lock")
        rc, out = init(self.runs, "lock test", "--no-db")
        self.assertEqual(rc, 0, out)
        self.run_ = Path(out["run"])
        self.lock = self.run_ / ".lock"

    def tearDown(self):
        shutil.rmtree(self.runs, ignore_errors=True)

    def test_second_mutating_process_is_refused(self):
        self.lock.write_text(json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "cmd": "media"}))
        p = fact(self.run_, "next")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("LOCKED", p.stderr + p.stdout)
        self.assertEqual(json.loads(self.lock.read_text(encoding="utf-8"))["pid"], os.getpid(), "a live owner's lock is never taken")
        self.lock.unlink()
        self.assertEqual(fact(self.run_, "next").returncode, 0)
        self.assertFalse(self.lock.exists(), "the lock is released when the command ends")

    def test_lock_of_a_dead_process_is_taken_over(self):
        dead = subprocess.Popen([PY, "-c", "pass"])
        dead.wait()
        self.lock.write_text(json.dumps({"pid": dead.pid, "host": socket.gethostname(), "cmd": "media"}))
        p = fact(self.run_, "next")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(self.lock.exists())

    def test_unlock_is_audited(self):
        self.lock.write_text(json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "cmd": "media"}))
        p = subprocess.run([PY, str(FACT), "unlock", "--run", str(self.run_), "--note", "media process killed by OOM"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(self.lock.exists())
        ev = [e for e in read_json(self.run_ / "state.json")["events"] if e.get("stage") == "LOCK"]
        self.assertEqual(ev[-1]["decision"]["note"], "media process killed by OOM")

    def test_shared_file_lock_waits_for_the_holder(self):
        lk, order = self.runs / ".cta_history.lock", []

        def holder():
            with F.FileLock(lk, "holder"):
                order.append("held")
                time.sleep(0.6)
            order.append("released")
        t = threading.Thread(target=holder)
        t.start()
        while not order:
            time.sleep(0.01)
        with F.FileLock(lk, "waiter", wait_s=10):
            order.append("acquired")
        t.join()
        self.assertEqual(order, ["held", "released", "acquired"])


# ============================================================================= no silent failures
class NoSilentFailures(unittest.TestCase):
    def setUp(self):
        self.runs = tmpdir("silent")
        rc, out = init(self.runs, "silent failures", "--no-db")
        self.assertEqual(rc, 0, out)
        self.run_ = Path(out["run"])

    def tearDown(self):
        shutil.rmtree(self.runs, ignore_errors=True)

    def test_an_envelope_is_never_recorded_twice(self):
        res = self.run_ / "research" / "result.json"
        sr = StageResult("RESEARCH", "content-research", attempt=1)
        sr.fail("RES.ENOUGH_FACTS", "3 facts", fix=F.fix("RESEARCH", "expand"))
        sr.finalize(res)
        st = F.load(self.run_)
        self.assertEqual(F.record(self.run_, st, res)["action"], "rerun")
        with self.assertRaises(SystemExit) as cm:      # the gate crashed before writing: the old verdict is still there
            F.record(self.run_, st, res)
        self.assertIn("STALE_RESULT", str(cm.exception))

    def test_media_stage_that_writes_no_result_becomes_an_error(self):
        st = F.load(self.run_)
        for s in F.GLOBAL_STAGES:
            st["global"][s]["status"] = "passed"
        st["videos"]["v01"] = F.unit("en", None, "i1")
        for s in ("HOOK", "SCRIPT"):
            st["videos"]["v01"]["stages"][s]["status"] = "passed"
        F.save(self.run_, st)
        orig = F.media_cmds
        F.media_cmds = lambda *a: [[PY, "-c", "import sys; print('boom', file=sys.stderr); sys.exit(1)"]]
        try:
            F.cmd_media(argparse.Namespace(run=str(self.run_), video="v01", steps=1))
        finally:
            F.media_cmds = orig
        res = read_json(F.vp(self.run_, "v01")["result"]["AUDIO"])
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["errors"][0]["code"], "INTERNAL.NO_RESULT")
        self.assertIn("boom", res["errors"][0]["message"])
        audio = F.load(self.run_)["videos"]["v01"]["stages"]["AUDIO"]
        self.assertEqual((audio["status"], audio["fix_params"]["action"]), ("pending", "retry"))

    def test_crash_envelope_without_video_id_is_recorded(self):
        st = F.load(self.run_)
        for s_ in F.GLOBAL_STAGES:
            st["global"][s_]["status"] = "passed"
        st["videos"]["v01"] = F.unit("en", None, "i1")
        for s_ in ("HOOK", "SCRIPT"):
            st["videos"]["v01"]["stages"][s_]["status"] = "passed"
        F.save(self.run_, st)
        res = F.vp(self.run_, "v01")["result"]["AUDIO"]
        sr = StageResult("AUDIO", "voice-production", None, attempt=1)    # what stage_main writes when a script crashes
        sr.fail("INTERNAL.EXCEPTION", "TypeError: boom", retryable=True)
        sr.finalize(res, status="error")
        st = F.load(self.run_)
        d = F.record(self.run_, st, res)
        self.assertEqual((d["action"], d["stage"], d["video_id"]), ("rerun", "AUDIO", "v01"))
        self.assertEqual(read_json(res)["video_id"], "v01")

    def test_missing_capabilities(self):
        def caps(**on):
            return {"capabilities": {k: {"available": v} for k, v in on.items()}}
        full = {"tts.kokoro": True, "video.render": True, "subtitles.burn": True, "visual.doodle": True}
        self.assertEqual(F.missing_capabilities(caps(**full), {"visual_style": "doodle"}), [])
        no_doodle = {**full, "visual.doodle": False}
        self.assertEqual([m["capability"] for m in F.missing_capabilities(caps(**no_doodle), {"visual_style": "doodle"})], ["visual.doodle"])
        self.assertEqual(F.missing_capabilities(caps(**no_doodle), {"visual_style": "illustrated"}), [])
        eleven = {**full, "tts.kokoro": False, "tts.elevenlabs": True}
        self.assertEqual(F.missing_capabilities(caps(**eleven), {}), [])
        self.assertEqual([m["capability"] for m in F.missing_capabilities(caps(**{**full, "tts.kokoro": False}), {})], ["tts"])

    def test_init_refuses_a_machine_that_cannot_render_doodles(self):
        fake = tmpdir("fakeskia")
        (fake / "skia.py").write_text("raise ImportError('libEGL.so.1: cannot open shared object file: No such file or directory')\n")
        env = {**os.environ, "PYTHONPATH": str(fake) + os.pathsep + os.environ.get("PYTHONPATH", "")}
        before = {p.name for p in self.runs.iterdir()}
        rc, out = init(self.runs, "no doodles here", "--no-db", env=env)
        self.assertEqual(rc, 2, out)
        self.assertEqual(out["error"], "CAPABILITY_MISSING")
        self.assertEqual(out["missing"][0]["capability"], "visual.doodle")
        self.assertIn("libegl1", out["missing"][0]["fix"])
        self.assertEqual({p.name for p in self.runs.iterdir()}, before, "a refused init leaves no half-made run behind")
        shutil.rmtree(fake, ignore_errors=True)


# ============================================================================= gates
class Gates(unittest.TestCase):
    def test_claim_numbers_match_whole_numbers_only(self):
        import package_engine as PE
        cited = [{"claim": "A 2013 study tested 200 people; 1.5% had it, versus 27% of the others."}]
        ids = lambda t: [x["id"] for x in PE.claim_check(t, cited, "title")]   # noqa: E731
        self.assertIn("CLAIM.UNSUPPORTED_NUMBER", ids("2 in 5 people have it"))       # "2" used to match "200"
        self.assertIn("CLAIM.UNSUPPORTED_NUMBER", ids("5% of people"))                 # "5" ≠ "1.5"
        self.assertIn("CLAIM.UNSUPPORTED_NUMBER", ids("20 people"))                    # "20" ≠ "200"
        self.assertEqual(ids("27% of 200 people, a 2013 study"), [])
        self.assertEqual(ids("only 1.5%"), [])

    def test_doodle_scene_rendered_by_a_fallback_fails(self):
        d = tmpdir("fallback")
        (d / "svg").mkdir()
        (d / "svg" / "s1.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920"><g data-in="none"><rect')
        (d / "svg" / "s2.svg").write_text(K.STRONG_SVG)
        beats = [{"id": "b1", "role": "hook", "text": "Flamingos rest on one leg.", "claim_ids": []},
                 {"id": "b2", "role": "value", "text": "Not water. Nerves.", "claim_ids": []},
                 {"id": "b3", "role": "payoff", "text": "That is the trick.", "claim_ids": []}]
        write_json(d / "script.json", {"video_id": "t", "language": "en", "beats": beats,
                                       "publish": {"title_options": ["t"], "description": "", "hashtags": []}})
        write_json(d / "storyboard.json", {"video_id": "t", "style": {"palette": ["#ffd23f", "#e8452c", "#3b82c4"]}, "scenes": [
            {"id": "s1", "beat_ids": ["b1"], "visual": {"kind": "doodle", "svg_path": "svg/s1.svg"}},
            {"id": "s2", "beat_ids": ["b2", "b3"], "visual": {"kind": "doodle", "svg_path": "svg/s2.svg"}}]})
        subprocess.run([PY, str(SB), "render", "--storyboard", d / "storyboard.json", "--script", d / "script.json", "--out-dir", d,
                        "--result", d / "result.json", "--auto-fallback"], capture_output=True, text=True)
        res = read_json(d / "result.json")
        bad = {e["code"]: e for e in res["errors"]}
        self.assertIn("VIS.DOODLE_FALLBACK", bad, [e["code"] for e in res["errors"]])
        self.assertEqual(bad["VIS.DOODLE_FALLBACK"]["severity"], "major")
        self.assertEqual(res["status"], "failed")
        shutil.rmtree(d, ignore_errors=True)

    def test_paper_transition_renders_its_first_frame(self):
        sys.path.insert(0, str(ROOT / "video-production" / "scripts"))
        import doodle_engine as de
        sv = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920"><circle cx="540" cy="700" r="300" fill="#ffd23f" data-in="none"/></svg>'
        scenes = [de.DoodleScene(sv, None, [], 2.0, {}, scene_id=k, camera={"drift": "none"}) for k in ("a", "b")]
        shots = [{"id": "a", "start": 0.0, "end": 2.0}, {"id": "b", "start": 2.0, "end": 4.0, "transition": {"type": "paper"}}]
        tl = de.Timeline(shots, scenes, 4.0, de.Paper())
        kind, dur = tl.trans[1]
        self.assertEqual(kind, "paper")
        tl.frame(2.0 - dur / 2)       # q = 0: skia returns no colour filter for a fully transparent dim (crashed before)
        tl.frame(2.0)

    def test_media_audit_ignores_random_bytes_but_catches_real_paths(self):
        sys.path.insert(0, str(ROOT / "asset-provenance" / "scripts"))
        import media_clean as MC
        d = tmpdir("audit")
        clip = d / "clip.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=white:s=64x64:d=0.2", "-c:v", "libx264",
                        "-fflags", "+bitexact", "-flags:v", "+bitexact", "-bsf:v", "filter_units=remove_types=6", str(clip)], check=True)
        MC.clean(clip, d / "clean.mp4")                 # a deliverable is always cleaned before the audit
        base = (d / "clean.mp4").read_bytes()
        self.assertTrue(MC.audit(d / "clean.mp4")["clean"])
        noisy, leak = d / "noisy.mp4", d / "leak.mp4"
        noisy.write_bytes(base + b"\x00\x93{Z:\\\\[\x07")             # the 6 random bytes found in a real final.mp4
        leak.write_bytes(base + b"\x00D:\\\\shorts-ai\\\\factory\x00")    # a real (JSON-escaped) Windows path
        self.assertEqual([f["value"] for f in MC.audit(noisy)["findings"]], [])
        self.assertTrue(any("shorts-ai" in f["value"] for f in MC.audit(leak)["findings"]))
        shutil.rmtree(d, ignore_errors=True)

    def test_doctor_names_the_missing_system_library(self):
        import doctor
        doctor.IMPORT_ERRORS["skia"] = "ImportError: libEGL.so.1: cannot open shared object file: No such file or directory"
        self.assertIn("apt-get install -y libegl1", doctor.import_fix("skia", "skia-python"))
        doctor.IMPORT_ERRORS.pop("skia")
        self.assertEqual(doctor.import_fix("svgelements", "svgelements"), "pip install svgelements")


# ============================================================================= content memory
class PackageJudgmentCoverage(unittest.TestCase):
    """An external package judgment must cover every candidate it is applied to, and not a changed packet."""
    def test_uncovered_or_stale_candidates_fail(self):
        packets = REPO / "fixtures" / "phase4_package_run"
        run = next(packets.iterdir())
        tmp = tmpdir("judg")
        shutil.copytree(run, tmp / run.name)
        pk_dir = tmp / run.name / "videos" / "v01" / "package"
        p = subprocess.run([PY, str(ROOT / "content-factory" / "scripts" / "package_engine.py"), "select",
                            "--candidates", pk_dir / "package_candidates.json", "--script", tmp / run.name / "videos/v01/script/script.json",
                            "--timing", tmp / run.name / "videos/v01/audio/timing.json", "--final", tmp / run.name / "videos/v01/subtitles/final.mp4",
                            "--dossier", tmp / run.name / "research/dossier.json", "--out-dir", tmp / "out"], capture_output=True, text=True)
        self.assertTrue((tmp / "out" / "review" / "packets" / "P1").exists(), p.stderr[-800:])
        pk = sorted(str(x) for x in (tmp / "out" / "review" / "packets").iterdir())
        sha = hashlib.sha256((Path(pk[0]) / "manifest.json").read_bytes()).hexdigest()      # packet P1
        j = tmp / "judgment.json"
        write_json(j, {"candidates": {"P1": {"scores": {"curiosity": 5}, "packet_manifest_sha256": sha},
                                      "P2": {"scores": {"curiosity": 5}, "packet_manifest_sha256": "0" * 64}}})
        subprocess.run([PY, str(ROOT / "video-quality-assurance" / "scripts" / "reviewer.py"), "review-package", "--packets", *pk,
                        "--out", str(tmp / "rv"), "--judgment", str(j)], capture_output=True, text=True)
        res = {r["candidate"]: r for r in read_json(tmp / "rv" / "package_reviews.json")["results"]}
        ids = lambda c: [f["id"] for f in res[c]["failures"]]  # noqa: E731
        self.assertNotIn("JUDGMENT.MISSING", ids("P1"))
        self.assertNotIn("JUDGMENT.STALE", ids("P1"))
        self.assertIn("JUDGMENT.STALE", ids("P2"))
        for c in res:
            if c not in ("P1", "P2"):
                self.assertIn("JUDGMENT.MISSING", ids(c))
                self.assertEqual(res[c]["verdict"], "FAIL")
        shutil.rmtree(tmp, ignore_errors=True)


class ContentMemory(unittest.TestCase):
    def test_topic_rule_calibration(self):
        con = cfdb.connect(":memory:")
        for i, t in enumerate(PAST):
            cfdb.upsert(con, "runs", {"run_id": f"r{i}", "topic": t})
        for i, t in enumerate(PAST_TITLES):
            cfdb.upsert(con, "videos", {"video_id": "v01", "run_id": f"t{i}", "title": t})
        for t in REPEATS:
            self.assertTrue(cfdb.topic_repeats(con, t)[0], f"{t!r} repeats an earlier topic")
        for t in NEW:
            self.assertEqual(cfdb.topic_repeats(con, t)[0], [], f"{t!r} is a new topic")

    def test_memory_is_on_by_default_and_refuses_a_repeated_topic(self):
        runs = tmpdir("mem")
        rc, out = init(runs, "Why flamingos stand on one leg")
        self.assertEqual(rc, 0, out)
        run = Path(out["run"])
        self.assertEqual(out["memory"]["db"], str((runs / "factory.db").resolve()))
        for f in ("history.json", "weights.json"):
            self.assertTrue((run / f).exists(), f)
        self.assertIn("--history", F.gate_cmd(run, F.load(run), "SELECTION", None))
        memory_with(runs / "factory.db")
        before = sorted(p.name for p in runs.iterdir())
        rc, out = init(runs, "why do onions make us cry")
        self.assertEqual(rc, 2, out)
        self.assertEqual(out["error"], "TOPIC_REPEATED")
        self.assertEqual(out["repeats"][0]["text"], "Why onions make you cry")
        self.assertEqual(sorted(p.name for p in runs.iterdir()), before, "a refused topic creates no run")
        rc, out = init(runs, "why do onions make us cry", "--allow-similar-topic", "follow-up: what the gas does to the eye")
        self.assertEqual(rc, 0, out)
        brief = read_json(Path(out["run"]) / "run.json")
        self.assertEqual(brief["memory"]["topic_check"]["override"], "follow-up: what the gas does to the eye")
        self.assertTrue(brief["memory"]["topic_check"]["repeats"])
        hist = read_json(Path(out["run"]) / "history.json")
        self.assertIn("topic", {x["kind"] for x in hist["items"]})
        shutil.rmtree(runs, ignore_errors=True)

    def test_no_db_opts_out(self):
        runs = tmpdir("nodb")
        rc, out = init(runs, "Why flamingos stand on one leg", "--no-db")
        self.assertEqual(rc, 0, out)
        self.assertIsNone(out["memory"]["db"])
        self.assertFalse((Path(out["run"]) / "history.json").exists())
        self.assertFalse((runs / "factory.db").exists())
        shutil.rmtree(runs, ignore_errors=True)

    def test_shipped_memory_knows_every_earlier_topic(self):
        dump = REPO / "memory" / "dump.json"
        if not dump.exists():
            self.skipTest(f"no {dump}")
        d = tmpdir("seedmem")
        p = subprocess.run([PY, str(CFDB), "import", "--db", str(d / "f.db"), "--in", str(dump)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        for t in ["Why do fingers wrinkle in water?", "Why onions make you cry", "Why do knuckles crack?", "What causes brain freeze?",
                  "Why can't you tickle yourself?"]:
            out = json.loads(subprocess.run([PY, str(CFDB), "topic-check", "--db", str(d / "f.db"), "--text", t],
                                            capture_output=True, text=True).stdout)
            self.assertTrue(out["repeats"], t)
        shutil.rmtree(d, ignore_errors=True)

    def test_a_past_hook_is_not_selected_again(self):
        d = tmpdir("hookmem")
        fill = K.H + K.finger() + K.WATER + '<text x="540" y="215" font-family="marker" font-size="96" data-in="none">FILLER</text></svg>'
        svgs = {"x": K.STRONG_SVG, **{f"f{i}": fill for i in range(4)}}
        line = "Pruney fingers? Not water. Nerves."
        cands = [K.cand("x", line, "x", "NOT WATER", mech="target")] + \
                [K.cand(f"f{i}", f"Filler number {i} about {w} things.", f"f{i}", "FILLER", mech=f"filler_{i}")
                 for i, w in enumerate(["blue", "green", "loud", "quiet"])]
        K.write_set(d, svgs, cands)
        write_json(d / "history.json", {"items": [{"kind": "hook", "text": "Pruney fingers? Not water — nerves!", "ref": "v01"}]})
        subprocess.run([PY, str(K.HOOK_ENGINE), "select", "--hooks", d / "hooks.json", "--dossier", d / "dossier.json", "--out-dir", d,
                        "--result", d / "result.json", "--history", d / "history.json"], capture_output=True, text=True)
        scored, res = read_json(d / "hooks.scored.json"), read_json(d / "result.json")
        x = next(c for c in scored["candidates"] if c["hook_id"] == "x")
        self.assertEqual(x["status"], "repeated_past")
        self.assertNotEqual(scored.get("selected"), "x")
        codes = {e["code"] for e in res["errors"]}
        self.assertIn("HOOK.NOT_REPEATED", codes)
        self.assertNotIn("HOOK.FUTILE_RESUBMISSION", codes, "a repeat of a past video is a new-strategy rerun, not an escalation")
        shutil.rmtree(d, ignore_errors=True)

    @unittest.skipUnless((KNUCKLES / "videos" / "v01" / "package" / "package_candidates.json").exists(), "phase 4 fixture missing")
    def test_package_remembers_the_run_and_blocks_its_repeat(self):
        runs = tmpdir("ingest")
        run = runs / KNUCKLES.name
        shutil.copytree(KNUCKLES, run)
        shutil.rmtree(run / "package" / "v01", ignore_errors=True)
        db = runs / "factory.db"
        st = read_json(run / "state.json")
        st["brief"]["memory"] = {"db": str(db)}
        write_json(run / "state.json", st)
        p = fact(run, "package")
        self.assertEqual(p.returncode, 0, p.stdout[-1500:] + p.stderr[-1500:])
        self.assertIn('"memory"', p.stdout)
        stats = json.loads(subprocess.run([PY, str(CFDB), "stats", "--db", str(db)], capture_output=True, text=True).stdout)
        self.assertEqual((stats["runs"], stats["videos"]), (1, 1))
        rc, out = init(runs, "What makes your knuckles crack?")
        self.assertEqual((rc, out.get("error")), (2, "TOPIC_REPEATED"), out)
        shutil.rmtree(runs, ignore_errors=True)


    def test_a_failed_repackage_ships_nothing(self):
        runs = tmpdir("repkg")
        run = runs / KNUCKLES.name
        shutil.copytree(KNUCKLES, run)
        p = fact(run, "package", "--zip")
        self.assertEqual(p.returncode, 0, p.stdout[-1500:] + p.stderr[-1500:])
        zp = run / f"{run.name}_package.zip"
        self.assertTrue(zp.exists())
        self.assertEqual(F.load(run)["videos"]["v01"]["status"], "packaged")
        cands = read_json(run / "videos" / "v01" / "package" / "package_candidates.json")["candidates"]
        write_json(run / "videos" / "v01" / "package" / "package_judgment.json",      # an external judge rejects every package
                   {"candidates": {c["id"]: {"scores": {"accuracy": 2}, "notes": {"accuracy": "overstated"}} for c in cands}})
        p = fact(run, "package", "--zip")
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse(zp.exists())                                                  # no run zip to upload
        for n in ("final.mp4", "PUBLISHING_PACKAGE.md", "thumbnail.jpg"):              # nothing left from the last attempt
            self.assertFalse((run / "package" / "v01" / n).exists(), n)
        self.assertEqual(read_json(run / "package" / "v01" / "result.json")["status"], "failed")
        self.assertNotEqual(F.load(run)["videos"]["v01"]["status"], "packaged")
        shutil.rmtree(runs, ignore_errors=True)

    def test_a_remade_video_is_not_checked_against_its_own_old_cta(self):
        runs = tmpdir("cta")
        run = runs / KNUCKLES.name
        shutil.copytree(KNUCKLES, run)
        shutil.rmtree(run / "package" / "v01", ignore_errors=True)
        other = {"run": "2026-01-01-another-run", "video_id": "v01", "type": "save", "text": "Save this for later."}
        write_json(runs / "cta_history.json", {"ctas": [{"run": run.name, "video_id": "v01", "type": "save", "text": "OLD CTA"}, other]})
        args = F.cta_history_args(run, "v01")
        self.assertEqual(read_json(args[1])["ctas"], [other])            # the SCRIPT/VIDEO gates see other videos only
        p = fact(run, "package")
        self.assertEqual(p.returncode, 0, p.stdout[-1500:] + p.stderr[-1500:])
        cta = read_json(run / "videos" / "v01" / "script" / "script.json").get("cta") or {}
        own = [h for h in read_json(runs / "cta_history.json")["ctas"] if h["run"] == run.name]
        self.assertEqual([h["text"] for h in own], [" ".join(x for x in (cta.get("spoken", ""), cta.get("on_screen", "")) if x)]
                         if cta.get("needed") else [])                   # the old entry is replaced, or dropped without a CTA
        self.assertIn(other, read_json(runs / "cta_history.json")["ctas"])
        shutil.rmtree(runs, ignore_errors=True)


# ============================================================================= batch isolation
def ideas_for(dossier: dict, n: int) -> dict:
    fmts = ["explainer", "myth-bust", "listicle", "question", "story", "comparison"]
    titles = ["What the palate tells the forehead", "The myth of the frozen brain", "Three ways to stop it fast",
              "Does gulping make it worse?", "The student trial that timed ice cream", "Ice water versus an ice cube"]
    angles = ["nerve signals and referred pain", "why nothing in your head freezes", "warm tongue, slow pace, breathe out",
              "a test of fast versus slow sips", "145 students and a stopwatch", "how much of the mouth gets cold"]
    fids = [f["id"] for f in dossier["facts"]]
    return {"ideas": [{"id": f"i{k + 1}", "title": titles[k], "angle": angles[k], "format": fmts[k], "pillar": "human body",
                       "value_add": f"a concrete, checkable takeaway number {k} for the viewer", "fact_ids": [fids[k % len(fids)]], "required_capabilities": [],
                       "scores": {"audience_value": 4, "curiosity": 4, "originality": 4, "evidence_strength": 4,
                                  "visual_potential": 4, "brand_safety": 5}} for k in range(n)]}


class BatchIsolation(unittest.TestCase):
    def test_three_videos_stay_independent(self):
        runs = tmpdir("batch")
        rc, out = init(runs, "batch isolation test", "--no-db", count=3)
        self.assertEqual(rc, 0, out)
        run = Path(out["run"])
        dossier = read_json(SEED / "research" / "dossier.json")
        authored = {"RESEARCH": ("research/dossier.json", dossier), "IDEATION": ("ideation/ideas.json", ideas_for(dossier, 6))}
        for stage in ("RESEARCH", "IDEATION", "SELECTION"):
            nx = json.loads(fact(run, "next").stdout)
            self.assertEqual((nx["action"], nx["stage"]), ("do_stage", stage), nx)
            if stage in authored:
                write_json(run / authored[stage][0], authored[stage][1])
            subprocess.run(nx["gate"], capture_output=True, text=True)
            rec = json.loads(subprocess.run(nx["then"], capture_output=True, text=True).stdout)
            self.assertEqual(rec["action"], "proceed", (stage, rec, read_json(F.result_path(run, stage, None))["errors"]))
        st = F.load(run)
        self.assertEqual(sorted(st["videos"]), ["v01", "v02", "v03"])
        dirs = {v: F.vp(run, v)["dir"] for v in st["videos"]}
        self.assertEqual(len(set(dirs.values())), 3)
        # v01's HOOK fails with no automatic fix: only v01 stops, the batch moves on to v02
        res = F.vp(run, "v01")["result"]["HOOK"]
        sr = StageResult("HOOK", "hook-engineering", "v01", attempt=1)
        sr.fail("HOOK.SELECTED", "no candidate passes")
        sr.finalize(res)
        rec = json.loads(subprocess.run([PY, str(FACT), "record", "--run", str(run), "--result", str(res)], capture_output=True, text=True).stdout)
        self.assertEqual(rec["action"], "escalate", rec)
        nx = json.loads(fact(run, "next").stdout)
        self.assertEqual((nx["action"], nx["stage"], nx["video_id"]), ("do_stage", "HOOK", "v02"))
        self.assertTrue(all(str(dirs["v02"]) in w for w in nx["write"]), nx["write"])
        st = F.load(run)
        self.assertEqual(st["videos"]["v01"]["status"], "escalated")
        for v in ("v02", "v03"):
            self.assertEqual(st["videos"][v]["status"], "in_progress")
            self.assertEqual(st["videos"][v]["regenerations"], 0)
            self.assertTrue(all(s["status"] in ("pending", "skipped") for s in st["videos"][v]["stages"].values()))
            self.assertFalse(F.vp(run, v)["result"]["HOOK"].exists())
        shutil.rmtree(runs, ignore_errors=True)

    def test_operator_reset_gives_later_stages_a_fresh_budget(self):
        runs = tmpdir("reset")
        rc, out = init(runs, "reset budget test", "--no-db")
        self.assertEqual(rc, 0, out)
        run = Path(out["run"])
        dossier = read_json(SEED / "research" / "dossier.json")
        authored = {"RESEARCH": ("research/dossier.json", dossier), "IDEATION": ("ideation/ideas.json", ideas_for(dossier, 6))}
        for stage in ("RESEARCH", "IDEATION", "SELECTION"):
            nx = json.loads(fact(run, "next").stdout)
            if stage in authored:
                write_json(run / authored[stage][0], authored[stage][1])
            subprocess.run(nx["gate"], capture_output=True, text=True)
            subprocess.run(nx["then"], capture_output=True, text=True)
        st = F.load(run)
        stages = st["videos"]["v01"]["stages"]
        for k in ("HOOK", "SCRIPT", "AUDIO", "VISUAL_PLAN", "VIDEO"):     # a video that used most of its budget, then escalated
            stages[k].update(status="passed", attempt=2)
        stages["VIDEO"].update(status="failed", attempt=3, fix_params={"action": "remix", "music_carve_db": 14.0})
        st["videos"]["v01"]["status"] = "escalated"
        F.save(run, st)
        p = fact(run, "reset", "--video", "v01", "--stage", "HOOK", "--note", "test")
        self.assertEqual(p.returncode, 0, p.stderr)
        stages = F.load(run)["videos"]["v01"]["stages"]
        self.assertEqual((stages["HOOK"]["status"], stages["HOOK"]["attempt"]), ("pending", 0))
        for k in ("SCRIPT", "AUDIO", "VISUAL_PLAN", "VIDEO"):
            self.assertEqual((stages[k]["status"], stages[k]["attempt"]), ("stale", 0), k)
        self.assertNotIn("fix_params", stages["VIDEO"])
        ev = F.load(run)["events"][-1]["decision"]
        self.assertEqual((ev["action"], ev["note"]), ("human_reset", "test"))
        shutil.rmtree(runs, ignore_errors=True)

    def test_runs_in_one_folder_never_share_state(self):
        runs = tmpdir("tworuns")
        rc1, a = init(runs, "same day same topic")
        rc2, b = init(runs, "same day same topic")       # nothing was packaged yet, so memory has no repeat to report
        self.assertEqual((rc1, rc2), (0, 0), (a, b))
        ra, rb = Path(a["run"]), Path(b["run"])
        self.assertNotEqual(ra, rb)
        self.assertTrue(rb.name.endswith("-2"))
        self.assertEqual(a["memory"]["db"], b["memory"]["db"], "one memory per runs folder")
        self.assertNotEqual(read_json(ra / "state.json")["run_id"], read_json(rb / "state.json")["run_id"])
        shutil.rmtree(runs, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
