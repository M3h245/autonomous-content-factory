"""Factory integration: `factory.py media` runs QA → independent review (separate process) → routes the failure.

    CF_FIXTURE_DIR=… python -m unittest content-factory/tests/test_factory_review.py
Reuses fixture C (bad pacing/audio/ending) from CF_FIXTURE_DIR, building it if missing (~2 min).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT / "content-factory" / "scripts"))
import factory as F  # noqa: E402
import fixture_kit as fk  # noqa: E402

FX = Path(os.environ.get("CF_FIXTURE_DIR") or tempfile.mkdtemp(prefix="cf_fx_")) / "C_pacing"
FACT = ROOT / "content-factory" / "scripts" / "factory.py"


def staged_run(backend: str) -> Path:
    if not (FX / "subtitles" / "final.mp4").exists():
        fk.fixture_C_pacing(FX)
    out = subprocess.run([sys.executable, str(FACT), "init", "--topic", "fingers", "--count", "1", "--min-s", "3", "--max-s", "60",
                          "--review-backend", backend, "--runs-dir", tempfile.mkdtemp()], capture_output=True, text=True, check=True).stdout
    run = Path(json.loads(out)["run"])
    st = F.load(run)
    for g in st["global"].values():
        g.update(status="passed", attempt=1)
    st["videos"]["v01"] = F.unit("en", None, "i1")
    for s in ("HOOK", "SCRIPT", "AUDIO", "VISUAL_PLAN", "VIDEO", "SUBTITLES"):
        st["videos"]["v01"]["stages"][s].update(status="passed", attempt=1)
    F.save(run, st)
    p = F.vp(run, "v01")
    for src, dst in ((FX / "audio", p["audio"]), (FX / "script", p["script"].parent), (FX / "video", p["video"]),
                     (FX / "subtitles", p["subs"])):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    for f in (p["timing"], p["script"]):            # the fixture was built as video "fx"; this run calls it v01
        d = json.loads(f.read_text())
        d["video_id"] = "v01"
        f.write_text(json.dumps(d))
    return run


class FactoryReview(unittest.TestCase):
    def test_media_runs_independent_review_and_routes(self):
        run = staged_run("heuristic")
        r = subprocess.run([sys.executable, str(FACT), "media", "--run", str(run), "--video", "v01", "--steps", "2"],
                           capture_output=True, text=True)
        d = json.loads(r.stdout[r.stdout.index("{"):])
        st = F.load(run)
        qa = json.loads(F.vp(run, "v01")["result"]["QA"].read_text())
        ids = {c["id"] for c in qa["gate"]["checks"]}
        self.assertEqual(qa["status"], "failed")
        self.assertTrue({"REV.PACING_RETENTION", "REV.AUDIO_BALANCE", "REV.ENDING_QUALITY"} <= {e["code"] for e in qa["errors"]}, qa["errors"])
        self.assertFalse([i for i in ids if i.startswith("V.")], "no self-review items in the QA verdict")
        self.assertEqual(qa["metrics"]["independent_review"]["judge"], "heuristic")
        b = [e for e in st["events"] if e.get("boundary") == "independent_review"]
        self.assertTrue(b and b[-1]["authoring_modules_loaded"] == [] and b[-1]["reviewer_pid"] != os.getpid())
        self.assertEqual((d["action"], d["stage"]), ("rerun", "SCRIPT"))       # earliest failing route wins
        self.assertEqual(st["videos"]["v01"]["stages"]["AUDIO"]["status"], "stale")

    def test_subagent_backend_hands_out_an_independent_review(self):
        run = staged_run("subagent")
        r = subprocess.run([sys.executable, str(FACT), "media", "--run", str(run), "--video", "v01", "--steps", "2"],
                           capture_output=True, text=True)
        d = json.loads(r.stdout[r.stdout.index("{"):])
        self.assertEqual((d["action"], d.get("independent")), ("review", True))
        self.assertIn("review_packet.py", " ".join(d["build"]))
        self.assertIn("--backend", d["review"])
        self.assertEqual(F.load(run)["videos"]["v01"]["stages"]["QA"]["status"], "pending_review")


if __name__ == "__main__":
    unittest.main()
