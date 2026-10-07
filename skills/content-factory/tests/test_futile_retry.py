"""Futile-retry guard: a deterministic stage is never re-run with identical inputs and parameters.

    python -m unittest discover -s content-factory/tests -p "test_futile_retry.py" -v
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
from cf_common import StageResult, fix  # noqa: E402


def run_with(stage: str, fix_params=None):
    out = subprocess.run([sys.executable, str(ROOT / "content-factory/scripts/factory.py"), "init", "--topic", "futile",
                          "--count", "1", "--runs-dir", tempfile.mkdtemp()], capture_output=True, text=True, check=True).stdout
    run = Path(json.loads(out)["run"])
    st = F.load(run)
    st["videos"]["v01"] = F.unit("en", None, "i1")
    for s in F.VIDEO_STAGES[: F.VIDEO_STAGES.index(stage)]:
        if st["videos"]["v01"]["stages"][s]["status"] != "skipped":
            st["videos"]["v01"]["stages"][s].update(status="passed", attempt=1)
    st["videos"]["v01"]["stages"][stage].update(status="failed", attempt=1, **({"fix_params": fix_params} if fix_params else {}))
    return run, st


def failed(stage, code, route, internal=False):
    sr = StageResult(stage, "x", "v01", attempt=1)
    if internal:
        sr.fail("INTERNAL.EXCEPTION", "crash", retryable=True)
    else:
        sr.check(code, False, "major", "bad", fix=route)
    return sr.finalize(Path(tempfile.mkdtemp()) / "r.json")


class FutileRetry(unittest.TestCase):
    def test_identical_deterministic_retry_escalates_immediately(self):
        run, st = run_with("AUDIO")
        d = F.route(run, st, failed("AUDIO", "AUDIO.TIMING_MONOTONIC", fix("AUDIO", "resynthesize")))
        self.assertEqual(d["action"], "escalate")
        self.assertTrue(d.get("futile_retry"))
        self.assertEqual(st["videos"]["v01"]["stages"]["AUDIO"]["attempt"], 1, "no retry budget may be spent")

    def test_changed_parameters_are_retried(self):
        run, st = run_with("AUDIO")
        d = F.route(run, st, failed("AUDIO", "AUDIO.DURATION_IN_RANGE", fix("AUDIO", "speed_up", speed=1.03)))
        self.assertEqual((d["action"], d["stage"]), ("rerun", "AUDIO"))
        run, st = run_with("VIDEO", {"action": "remix", "lufs": -14})
        d = F.route(run, st, failed("VIDEO", "VID.LOUDNESS", fix("VIDEO", "remix", lufs=-15)))
        self.assertEqual(d["action"], "rerun")

    def test_same_parameters_again_is_futile(self):
        run, st = run_with("VIDEO", {"action": "remix", "lufs": -15})
        d = F.route(run, st, failed("VIDEO", "VID.LOUDNESS", fix("VIDEO", "remix", lufs=-15)))
        self.assertTrue(d.get("futile_retry"), d)

    def test_crashes_and_upstream_routes_still_retry(self):
        run, st = run_with("SUBTITLES")
        d = F.route(run, st, failed("SUBTITLES", None, None, internal=True))
        self.assertEqual(d["action"], "rerun")
        run, st = run_with("VIDEO")
        d = F.route(run, st, failed("VIDEO", "VID.EMPTY_FRAMES", fix("VISUAL_PLAN", "add_entrances", at_s=3)))
        self.assertEqual((d["action"], d["stage"]), ("rerun", "VISUAL_PLAN"))


if __name__ == "__main__":
    unittest.main()
