"""v3.3 format patch: aspect/kind resolution, hook windows, packaging-variation tokenising and the aspect-aware
thumbnail crop preview. Pure-function coverage — no render, no network, no DB.

    python -m unittest skills.content-factory.tests.test_v33_format -v
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CF = ROOT / "content-factory" / "scripts"
sys.path.insert(0, str(CF))

import cf_common as C  # noqa: E402
import package_run as PR  # noqa: E402


class FormatContract(unittest.TestCase):
    def test_formats_are_the_right_encodings(self):
        self.assertEqual((C.FORMATS["short"]["width"], C.FORMATS["short"]["height"]), (1080, 1920))
        self.assertEqual((C.FORMATS["long"]["width"], C.FORMATS["long"]["height"]), (1920, 1080))
        self.assertEqual(C.FORMATS["long"]["viewbox"], "0 0 1920 1080")
        self.assertEqual(C.format_of("nonsense"), C.FORMATS["short"])   # unknown kind falls back to short

    def test_video_kind_is_aspect_and_duration(self):
        # the whole point of v3.3: a vertical/short upload is a Short regardless of duration
        self.assertEqual(C.video_kind("vertical", 60), "short")
        self.assertEqual(C.video_kind("vertical", 180.0), "short")      # boundary is inclusive
        self.assertEqual(C.video_kind("vertical", 181), "long")         # >3 min vertical leaves the Shorts feed
        self.assertEqual(C.video_kind("wide", 60), "long")              # 16:9 is never a Short
        self.assertEqual(C.video_kind("wide", 400), "long")

    def test_hook_window_per_kind(self):
        self.assertEqual(C.HOOK_WINDOW_S["short"], 3.2)
        self.assertEqual(C.HOOK_WINDOW_S["long"], 8.0)                  # YouTube's 5-10 s long-form guidance

    def test_brief_schema_accepts_aspect_and_kind(self):
        brief_schema = C.SCHEMAS["brief"]
        errs = C.validate({"run_id": "r", "topic": "t", "count": 1, "languages": ["en"], "platforms": ["youtube"],
                           "video_kind": "long", "aspect": "wide"}, brief_schema)
        self.assertEqual(errs, [])
        bad = C.validate({"run_id": "r", "topic": "t", "count": 1, "languages": ["en"], "platforms": ["youtube"],
                          "aspect": "square"}, brief_schema)
        self.assertTrue(bad)                                            # only vertical|wide are legal


class PackagingVariation(unittest.TestCase):
    def test_tokens_drop_stopwords_and_punctuation(self):
        t = PR._tokens("Why Does Time Seem to Speed Up?")
        self.assertIn("time", t)
        self.assertIn("speed", t)
        self.assertNotIn("why", t)          # stop-word
        self.assertNotIn("to", t)
        self.assertNotIn("?", t)

    def test_jaccard_is_symmetric_and_bounded(self):
        a, b = {"a", "b"}, {"b", "c"}
        self.assertAlmostEqual(PR._jac(a, b), 1 / 3)
        self.assertEqual(PR._jac(a, a), 1.0)
        self.assertEqual(PR._jac(a, set()), 0.0)

    def test_near_duplicate_titles_exceed_the_threshold(self):
        a = PR._tokens("Why time feels faster as you get older")
        b = PR._tokens("Why time feels faster when you get older")
        self.assertGreater(PR._jac(a, b), 0.6)                          # would fail PKG.PACKAGING_VARIATION
        c = PR._tokens("How your brain decides what to remember")
        self.assertLess(PR._jac(a, c), 0.6)


class CoverPreview(unittest.TestCase):
    def test_wide_preview_is_a_single_16_9_band(self):
        try:
            from PIL import Image
        except ImportError:                                             # pragma: no cover
            self.skipTest("PIL not available")
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "thumb.jpg"
            Image.new("RGB", (1920, 1080), (200, 100, 50)).save(src, "JPEG")
            vertical = Path(td) / "v.jpg"
            wide = Path(td) / "w.jpg"
            PR.crops_preview(src, vertical, "vertical")
            PR.crops_preview(src, wide, "wide")
            with Image.open(vertical) as vi:
                vw, _ = vi.size
            with Image.open(wide) as wi:
                ww, wh = wi.size
            # five vertical strips vs one 16:9 strip: the wide output is much narrower and has no 9:16 sliver
            self.assertLess(ww, vw)
            self.assertAlmostEqual(ww / wh, 480 * (16 / 9) / 480, delta=0.05)


if __name__ == "__main__":
    unittest.main()
