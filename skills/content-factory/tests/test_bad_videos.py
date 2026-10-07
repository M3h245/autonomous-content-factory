"""Bad videos must be rejected by the independent reviewer — for the right reasons (≈1.5-2 min each).

    python -m unittest content-factory/tests/test_bad_videos.py -k A   (one at a time on slow machines)
Fixtures are rendered through the real stages by fixture_kit.py; set CF_FIXTURE_DIR to keep them.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_kit as fk  # noqa: E402

BASE = Path(os.environ.get("CF_FIXTURE_DIR") or tempfile.mkdtemp(prefix="cf_fx_"))


def scores(rv):
    return {d: v["score"] for d, v in rv["scores"].items()}


class BadVideos(unittest.TestCase):
    def test_A_crop_and_meaning_reversal(self):
        rv = fk.fixture_A_crop(BASE / "A_crop")["review"]
        ids = {f["id"] for f in rv["failures"]}
        self.assertEqual(rv["verdict"], "FAIL")
        self.assertTrue({"AUDIT.MEANING_CROPPED", "AUDIT.TEXT_CROPPED", "AUDIT.OVERHANG"} <= ids, ids)
        self.assertLessEqual(scores(rv)["visual_verbal_sync"], 2)
        self.assertEqual(scores(rv)["overall_publishability"], 1)

    def test_B_weak_confusing_hook(self):
        rv = fk.fixture_B_hook(BASE / "B_hook")["review"]
        s = scores(rv)
        self.assertEqual(rv["verdict"], "FAIL")
        self.assertLessEqual(s["hook_strength"], 2)
        self.assertLessEqual(s["first_frame_clarity"], 2)
        hook = next(f for f in rv["failures"] if f["id"] == "hook_strength")
        self.assertIn("speech onset", str(hook["evidence"]))
        self.assertEqual(hook["fix_route"]["stage"], "HOOK")
        self.assertIn("FIRST_FRAME.BLANK", {f["id"] for f in rv["failures"]})

    def test_C_pacing_audio_subtitles_ending(self):
        rv = fk.fixture_C_pacing(BASE / "C_pacing")["review"]
        s = scores(rv)
        self.assertEqual(rv["verdict"], "FAIL")
        self.assertLessEqual(s["pacing_retention"], 2)
        self.assertLessEqual(s["audio_balance"], 2)
        self.assertLessEqual(s["ending_quality"], 2)
        self.assertLessEqual(s["subtitle_readability"], 3)
        routes = {f["id"]: f["fix_route"]["stage"] for f in rv["failures"] if f.get("fix_route")}
        self.assertEqual((routes["pacing_retention"], routes["audio_balance"]), ("VISUAL_PLAN", "VIDEO"))

    def test_D_bad_cta(self):
        r = fk.fixture_D_bad_cta(BASE / "D_bad_cta")
        import json
        vid = {e["code"] for e in json.loads((BASE / "D_bad_cta" / "video" / "result.json").read_text())["errors"]}
        self.assertTrue({"VID.CTA_ENDING", "VID.CTA_RELEVANCE"} <= vid, vid)              # VIDEO gate, real timeline
        rv = r["review"]
        ids = {f["id"] for f in rv["failures"]}
        self.assertEqual(rv["verdict"], "FAIL")
        self.assertTrue({"CTA.ENDING", "CTA.RELEVANCE"} <= ids, ids)                    # deterministic, objective layer
        s = scores(rv)
        self.assertLessEqual(s["cta_relevance"], 2)
        self.assertLessEqual(s["cta_retention_risk"], 2)
        self.assertEqual(next(f for f in rv["failures"] if f["id"] == "CTA.ENDING")["fix_route"]["action"], "revise_cta")


if __name__ == "__main__":
    unittest.main()
