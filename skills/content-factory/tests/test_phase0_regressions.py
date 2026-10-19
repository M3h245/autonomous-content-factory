"""Regressions for bugs found by the Phase 0 end-to-end run (2026-10-05).

    python -m unittest discover -s content-factory/tests -p "test_phase0_regressions.py" -v
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "video-production" / "scripts"))
sys.path.insert(0, str(ROOT / "visual-storyboarding" / "scripts"))


class Regressions(unittest.TestCase):
    def test_spoken_numbers_are_word_cues(self):
        import doodle_engine as de
        words = [{"w": "In", "start": 0.1}, {"w": "2013,", "start": 0.3}, {"w": "wrinkled", "start": 0.8}]
        svg = ('<svg viewBox="0 0 1080 1920"><path d="M0,0 L9,9" data-at="w:2013"/>'
               '<path d="M0,0 L9,9" data-at="w:2"/></svg>')
        sc = de.DoodleScene(svg, words=words, duration=2)
        self.assertEqual([round(a.at, 2) for a in sc.root.children], [0.24, 0.74])  # word "2013"; index 2 = "wrinkled"
        self.assertEqual(sc.warnings, [])

    def test_lint_accepts_spoken_numbers(self):
        import storyboard_tool as sb
        words = [{"w": "In"}, {"w": "2013,"}, {"w": "faster."}]
        self.assertEqual(sb.doodle_cue_problems('<g data-at="w:2013"/>', words), [])
        self.assertTrue(sb.doodle_cue_problems('<g data-at="w:2014"/>', words))     # not spoken, beyond 3 words

    def test_speed_up_route_is_never_a_no_op(self):
        src = (ROOT / "voice-production" / "scripts" / "tts.py").read_text(encoding="utf-8")
        self.assertIn("a.speed + 0.03", src, "speed_up must always step by >=3%")
        for duration, max_s, speed in ((45.0, 45.0, 1.0), (45.004, 45.0, 1.0), (46.0, 45.0, 1.0)):
            need = max(speed * duration / max_s * 1.02, speed + 0.03)
            self.assertGreaterEqual(round(need, 3), speed + 0.03)

    def test_report_counts_failures_not_records(self):
        F = ROOT / "content-factory" / "scripts" / "factory.py"
        out = subprocess.run([sys.executable, str(F), "init", "--topic", "report test", "--count", "1", "--runs-dir",
                              tempfile.mkdtemp()], capture_output=True, text=True, check=True).stdout
        run = Path(json.loads(out)["run"])
        st = json.loads((run / "state.json").read_text(encoding="utf-8"))
        res = run / "research" / "result.json"
        res.parent.mkdir(parents=True, exist_ok=True)
        for status in ("failed", "passed"):
            res.write_text(json.dumps({"stage": "RESEARCH", "status": status, "started_at": "2026-10-05T00:00:00+00:00",
                                       "finished_at": "2026-10-05T00:00:01+00:00", "errors": [], "outputs": []}), encoding="utf-8")
            st["events"].append({"ts": "x", "stage": "RESEARCH", "video_id": None, "status": status, "attempt": 1,
                                 "result": str(res), "wall_s": 1.0})
        (run / "state.json").write_text(json.dumps(st), encoding="utf-8")
        subprocess.run([sys.executable, str(F), "report", "--run", str(run)], check=True, capture_output=True)
        rep = json.loads((run / "report" / "report.json").read_text(encoding="utf-8"))
        row = next(g for g in rep["stages"] if g["stage"] == "RESEARCH")
        self.assertEqual((row["records"], row["failures"], row["retries"]), (2, 1, 1))


if __name__ == "__main__":
    unittest.main()
