"""Independent reviewer: data boundary, rubric validity, policy, LLM/subagent backends (mock server, no network).

    python -m unittest discover -s content-factory/tests -p "test_reviewer.py" -v
"""
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QAS = ROOT / "video-quality-assurance" / "scripts"
sys.path.insert(0, str(QAS))
import reviewer as R  # noqa: E402

PY = sys.executable
PK, RW = QAS / "review_packet.py", QAS / "reviewer.py"


def make_inputs(d: Path) -> dict:
    """A 3-second 1080x1920 clip (paper + a box + tone) with timing, captions, script publish block and QA report."""
    d.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0xfbf7ee:s=1080x1920:d=3:r=30", "-f", "lavfi",
                    "-i", "sine=f=220:d=3:sample_rate=48000", "-vf", "drawbox=x=330:y=400:w=320:h=640:color=0xf6c9a8:t=fill",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(d / "final.mp4")], check=True)
    words = [{"w": w, "start": 0.1 + 0.3 * i, "end": 0.35 + 0.3 * i, "sentence": 0} for i, w in enumerate("Fingers are not soggy".split())]
    json.dump({"language": "en", "words": words, "sentences": [{"i": 0, "text": "Fingers are not soggy", "beat_id": "b1", "start": 0.1,
               "end": 1.25}]}, open(d / "timing.json", "w"))
    (d / "captions.ass").write_text("[V4+ Styles]\nStyle: Doodle,Permanent Marker,136,&H0,&H0,&H0,&H0,0,0,0,0,100,100,1,0,1,8,2,5,0,0,0,1\n"
                                    "[Events]\nDialogue: 1,0:00:00.10,0:00:01.25,Doodle,,0,0,0,,{\\an5\\pos(540,1210)}Fingers are not\n")
    json.dump({"beats": [{"id": "b1", "text": "SECRET-BEAT-STRUCTURE"}], "publish": {"title_options": ["Why fingers prune"],
               "description": "d", "hashtags": ["#x"]}}, open(d / "script.json", "w"))
    json.dump({"checks": [{"id": "QA.LOUDNESS", "passed": True, "severity": "major"},
                          {"id": "V.HOOK_FRAME", "passed": True, "severity": "major", "message": "author self-review"}],
               "metrics": {"lufs": -14.0, "true_peak_dbtp": -2.0, "ocr_rate": 1.0}, "review": {"reviewer": "author"}},
              open(d / "qa_report.json", "w"))
    return {"final": d / "final.mp4", "timing": d / "timing.json", "captions": d / "captions.ass", "publish": d / "script.json",
            "qa": d / "qa_report.json"}


def build_packet(i: dict, out: Path, extra=()) -> subprocess.CompletedProcess:
    return subprocess.run([PY, str(PK), "build", "--final", i["final"], "--timing", i["timing"], "--captions", i["captions"],
                           "--publish", i["publish"], "--measure", f"qa_report={i['qa']}", *extra, "--out", out],
                          capture_output=True, text=True)


def review(packet: Path, out: Path, *args, env=None) -> tuple[int, dict]:
    p = subprocess.run([PY, str(RW), "review", "--packet", packet, "--out", out, *args], capture_output=True, text=True,
                       env={**os.environ, **(env or {})})
    last = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else "{}"
    return p.returncode, json.loads(last)


def judgment(score=4, expl=""):
    return {d: {"score": score, "evidence": f"seen in contact sheet ({d})", "explanation": expl} for d in R.DIMS}


class Reviewer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="rev_"))
        cls.inp = make_inputs(cls.tmp / "in")
        p = build_packet(cls.inp, cls.tmp / "packet")
        assert p.returncode == 0, p.stderr
        cls.packet = cls.tmp / "packet"

    # ---- boundary
    def test_builder_refuses_authoring_inputs(self):
        sb = self.tmp / "in" / "storyboard.json"
        sb.write_text("{}")
        p = build_packet(self.inp, self.tmp / "bad_packet", ["--measure", f"plan={sb}"])
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("BOUNDARY", p.stderr + p.stdout)

    def test_packet_contains_no_creative_state(self):
        man = json.loads(Path(self.packet / "manifest.json").read_text())
        self.assertFalse([f for f in man["files"] if R.forbidden(f)])
        blob = "".join((self.packet / f).read_text(errors="ignore") for f in man["files"] if f.endswith(".json"))
        self.assertNotIn("SECRET-BEAT-STRUCTURE", blob, "beat structure leaked into the packet")
        qa = json.loads(Path(self.packet / "measurements" / "qa_report.json").read_text())
        self.assertFalse([c for c in qa["checks"] if c["id"].startswith("V.")], "author self-review leaked")
        self.assertNotIn("review", qa)

    def test_packet_access_is_whitelisted_and_hash_verified(self):
        cp = self.tmp / "packet_copy"
        shutil.copytree(self.packet, cp)
        pk = R.Packet(cp)
        with self.assertRaises(R.BoundaryError):
            pk.path("../in/script.json")
        with self.assertRaises(R.BoundaryError):
            pk.path("text/notes.txt")
        (cp / "text" / "publish.json").write_text('{"title": "tampered"}')
        with self.assertRaises(R.BoundaryError):
            pk.path("text/publish.json")
        self.assertEqual(len(pk.refused), 2)

    def test_reviewer_process_is_isolated_and_logged(self):
        code, d = review(self.packet, self.tmp / "rv_h", "--backend", "heuristic")
        self.assertIn(code, (0, 2))
        log = json.loads(Path(self.tmp / "rv_h" / "boundary_log.json").read_text())
        man = json.loads(Path(self.packet / "manifest.json").read_text())
        self.assertEqual(log["authoring_modules_loaded"], [])
        self.assertTrue({r["name"] for r in log["files_read"]} <= set(man["files"]))
        self.assertNotEqual(log["process"]["pid"], os.getpid())
        rep = json.loads(Path(self.tmp / "rv_h" / "review_report.json").read_text())
        for dname, v in rep["scores"].items():
            self.assertTrue(v["evidence"], dname)
            if v["score"] < 4:
                self.assertTrue(v["explanation"].strip(), f"{dname} scored {v['score']} without explanation")

    # ---- judgments + policy
    def test_judgment_validation(self):
        self.assertEqual(R.validate_judgment(judgment(4)), [])
        bad = judgment(4)
        bad["hook_strength"] = {"score": 2, "evidence": "x", "explanation": ""}
        self.assertTrue(R.validate_judgment(bad))
        bad["hook_strength"] = {"score": 7, "evidence": "x", "explanation": "y"}
        self.assertTrue(R.validate_judgment(bad))

    def test_merge_rules(self):
        heur = {d: {"score": 3, "evidence": ["h"], "cap": 5 if d not in R.TASTE else 4} for d in R.DIMS}
        m = R.merge(heur, judgment(5), "anthropic")
        self.assertEqual(m["hook_strength"]["score"], 5)            # taste: the LLM decides
        self.assertEqual(m["subtitle_readability"]["score"], 3)     # measurable: capped by the measurement

    def test_judge_routes_spoken_hook_to_HOOK(self):
        heur = {d: {"score": 4, "evidence": ["✓ visual subject at frame 0"], "cap": 4} for d in R.DIMS}
        pol = json.loads(Path(R.DEFAULT_POLICY).read_text())
        j = judgment(4)
        j["hook_strength"] = {"score": 3, "evidence": "opening question", "explanation": "the spoken line answers itself"}
        hook = lambda m: [f for f in R.decide(m, [], pol)[1] if f["id"] == "hook_strength"][0]["fix_route"]["stage"]
        self.assertEqual(hook(R.merge(heur, j, "subagent")), "VISUAL_PLAN")      # unchanged without fix_stage
        j["hook_strength"]["fix_stage"] = "HOOK"
        self.assertEqual(R.validate_judgment(j), [])
        self.assertEqual(hook(R.merge(heur, j, "subagent")), "HOOK")
        j["hook_strength"]["fix_stage"] = "VIDEO"
        self.assertTrue(R.validate_judgment(j))

    def test_policy(self):
        pol = json.loads(Path(R.DEFAULT_POLICY).read_text())
        ok = {d: {"score": 4, "explanation": "", "evidence": ["e"]} for d in R.DIMS}
        self.assertEqual(R.decide(ok, [], pol)[0], "PASS")
        weak = {**ok, "hook_strength": {"score": 3, "explanation": "frame 0 plain", "evidence": ["e"]}}
        self.assertEqual(R.decide(weak, [], pol)[0], "FAIL")
        low = {**ok, "audio_balance": {"score": 2, "explanation": "music loud", "evidence": ["e"]}}
        self.assertEqual(R.decide(low, [], pol)[0], "FAIL")
        obj = [{"id": "AUDIT.MEANING_CROPPED", "severity": "blocking", "evidence": "x"}]
        self.assertEqual(R.decide(ok, obj, pol)[0], "FAIL")

    def test_zero_valued_measurements_are_not_treated_as_missing(self):
        """Regression (Phase 2): `x or default` turned a label at 0.0 s into 99 s and a 0.0 dBTP peak into −9."""
        g = R.gather(R.Packet(self.packet))
        g["audit"] = {"hook": {"first_text_s": 0.0, "elements_at_t0": 2, "text_at_t0": True, "visual_events_first_1_5s": 2,
                               "subject_bbox_share_t0": 0.2}, "issues": [], "scenes": [{"scene": "s1"}], "labels": []}
        h = R.heuristic(g)
        self.assertIn("✓ on-screen text by 2.0 s: first label at 0.0", h["hook_strength"]["evidence"])
        g["qa_metrics"] = {**g["qa_metrics"], "true_peak_dbtp": 0.0}
        self.assertEqual(R.heuristic(g)["audio_balance"]["score"], 1)       # 0.0 dBTP is clipping, not "missing"

    # ---- backends
    def test_anthropic_backend_against_mock(self):
        seen = {}

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                seen["body"] = body
                reply = {"content": [{"type": "text", "text": json.dumps(judgment(4))}]}
                self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps(reply).encode())

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.handle_request, daemon=True).start()
        code, d = review(self.packet, self.tmp / "rv_a", "--backend", "anthropic",
                         env={"CF_ANTHROPIC_BASE_URL": f"http://127.0.0.1:{srv.server_port}", "ANTHROPIC_API_KEY": "test"})
        srv.server_close()
        self.assertIn(code, (0, 2), d)
        self.assertEqual(d["judge"], "anthropic")
        req = json.dumps(seen["body"])
        self.assertEqual(sum(1 for c in seen["body"]["messages"][0]["content"] if c["type"] == "image"), 5)
        for leak in ("SECRET-BEAT-STRUCTURE", "storyboard", "data-at", "hooks"):
            self.assertNotIn(leak, req)

    def test_subagent_flow(self):
        out = self.tmp / "rv_s"
        code, d = review(self.packet, out, "--backend", "subagent")
        self.assertEqual((code, d["verdict"]), (3, "AWAITING_JUDGMENT"))
        self.assertIn(str(self.packet), (out / "review_request.md").read_text())
        Path(out / "judgment.json").write_text(json.dumps(judgment(4)))
        code, d = review(self.packet, out, "--backend", "subagent")
        self.assertEqual(d["judge"], "subagent")
        bad = judgment(4)
        bad["ending_quality"] = {"score": 2, "evidence": "x", "explanation": ""}
        Path(out / "judgment.json").write_text(json.dumps(bad))
        code, d = review(self.packet, out, "--backend", "subagent")
        self.assertEqual((code, d["verdict"]), (1, "ERROR"))


if __name__ == "__main__":
    unittest.main()
