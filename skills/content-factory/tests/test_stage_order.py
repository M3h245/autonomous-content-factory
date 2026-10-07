"""AUDIO precedes VISUAL_PLAN; a VISUAL_PLAN fix never invalidates the voice-over; the media chain pauses for VISUAL_PLAN.

    python -m unittest discover -s content-factory/tests -p "test_stage_order.py" -v
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "content-factory" / "scripts"))
import factory as F  # noqa: E402
from cf_common import VIDEO_STAGES, StageResult, fix, write_json  # noqa: E402

FACTORY = ROOT / "content-factory" / "scripts" / "factory.py"


def fresh_run(tmp: Path) -> Path:
    out = subprocess.run([sys.executable, str(FACTORY), "init", "--topic", "order test", "--count", "1", "--runs-dir", str(tmp)],
                         capture_output=True, text=True, check=True).stdout
    run = Path(json.loads(out)["run"])
    st = F.load(run)
    for g in st["global"].values():
        g.update(status="passed", attempt=1)
    st["videos"]["v01"] = F.unit("en", None, "i1")
    for s in ("HOOK", "SCRIPT", "AUDIO"):
        st["videos"]["v01"]["stages"][s].update(status="passed", attempt=1)
    F.save(run, st)
    p = F.vp(run, "v01")
    p["timing"].parent.mkdir(parents=True, exist_ok=True)
    write_json(p["timing"], {"words": [], "sentences": []})
    return run


class StageOrder(unittest.TestCase):
    def test_order(self):
        self.assertLess(VIDEO_STAGES.index("AUDIO"), VIDEO_STAGES.index("VISUAL_PLAN"))

    def test_media_pauses_for_visual_plan_and_gate_gets_timing(self):
        run = fresh_run(Path(tempfile.mkdtemp()))
        out = subprocess.run([sys.executable, str(FACTORY), "media", "--run", str(run), "--video", "v01"],
                             capture_output=True, text=True)
        d = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual((d["action"], d["waiting_for"], d["next_stage"]), ("media_paused", "VISUAL_PLAN", "VISUAL_PLAN"))
        self.assertEqual(F.load(run)["videos"]["v01"]["stages"]["AUDIO"]["attempt"], 1, "AUDIO must not re-run")
        nxt = json.loads(subprocess.run([sys.executable, str(FACTORY), "next", "--run", str(run)], capture_output=True,
                                        text=True, check=True).stdout)
        self.assertEqual(nxt["stage"], "VISUAL_PLAN")
        self.assertIn("--timing", nxt["gate"], "VISUAL_PLAN gate must plan cues against the real narration")
        self.assertTrue(any(e.get("issued") == "do_stage" for e in F.load(run)["events"]), "task issue not logged")

    def test_visual_plan_fix_keeps_audio(self):
        run = fresh_run(Path(tempfile.mkdtemp()))
        st = F.load(run)
        for s in ("VISUAL_PLAN", "VIDEO"):
            st["videos"]["v01"]["stages"][s].update(status="passed", attempt=1)
        sr = StageResult("VIDEO", "video-production", "v01", attempt=2)
        sr.check("VID.EMPTY_FRAMES", False, "major", "blank page", 0.8, 0.5, fix("VISUAL_PLAN", "add_entrances", at_s=3.0))
        res = F.vp(run, "v01")["result"]["VIDEO"]
        res.parent.mkdir(parents=True, exist_ok=True)
        sr.finalize(res)
        d = F.record(run, st, res, wall_s=1.0)
        stages = st["videos"]["v01"]["stages"]
        self.assertEqual((d["action"], d["stage"]), ("rerun", "VISUAL_PLAN"))
        self.assertEqual(stages["AUDIO"]["status"], "passed", "a VISUAL_PLAN fix must not invalidate AUDIO")
        self.assertEqual(stages["VISUAL_PLAN"]["status"], "pending")
        self.assertTrue(all(stages[s]["status"] == "stale" for s in ("VIDEO", "SUBTITLES", "QA", "PACKAGE")))


if __name__ == "__main__":
    unittest.main()
