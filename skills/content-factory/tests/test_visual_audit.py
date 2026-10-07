"""Deterministic visual audit (doodle_engine.Timeline.audit): crop, meaning reversal, overhang, containment, size.

    python -m unittest discover -s content-factory/tests -p "test_visual_audit.py" -v
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "video-production" / "scripts"))
import doodle_engine as de  # noqa: E402

FINGER = '<path d="M330,1040 L330,460 C330,310 650,310 650,460 L650,1040 Z" fill="#f6c9a8"/>'
WORDS = [{"w": w, "start": 0.2 + 0.4 * i, "end": 0.5 + 0.4 * i} for i, w in enumerate("fingers are not water it is nerves".split())]


def audit(body: str, camera: dict | None = None, duration: float = 4.0) -> list:
    svg = f'<svg viewBox="0 0 1080 1920">{body}</svg>'
    sc = de.DoodleScene(svg, words=WORDS, duration=duration, camera=camera or {"drift": "none"}, scene_id="t")
    tl = de.Timeline([{"id": "s1", "start": 0.0, "visual": {"kind": "doodle"}}], [sc], duration, de.Paper())
    return tl.audit()["issues"]


def kinds(issues, at_least="minor"):
    order = {"minor": 0, "major": 1, "blocking": 2}
    return sorted({(i["kind"], i["severity"]) for i in issues if order[i["severity"]] >= order[at_least]})


class VisualAudit(unittest.TestCase):
    def test_clean_scene_has_no_issues(self):
        body = f'<g id="finger" data-in="none">{FINGER}</g><text x="540" y="200" font-size="80" data-in="none">NOT WATER</text>'
        self.assertEqual(kinds(audit(body), "major"), [])

    def test_punch_in_cropping_a_negation_is_blocking(self):
        body = f'<g data-in="none">{FINGER}</g><text x="250" y="230" font-size="100" data-in="none">NOT WATER</text>'
        iss = audit(body, {"drift": "none", "punch": [{"at": 1.0, "focus": [930, 520], "zoom": 1.25, "hold": 1.5}]})
        mc = [i for i in iss if i["kind"] == "meaning_cropped"]
        self.assertTrue(mc, kinds(iss))
        self.assertEqual(mc[0]["severity"], "blocking")
        self.assertIn("NOT", mc[0]["detail"]["lost_words"])

    def test_label_off_the_edge_is_cropped_text(self):
        iss = audit('<text x="1010" y="300" font-size="70" data-in="none">nerves</text>')
        self.assertTrue({("text_cropped", "major"), ("text_offscreen", "major")} & set(kinds(iss)), kinds(iss))

    def test_lines_poking_out_of_a_shape_are_an_overhang(self):
        wr = "".join(f'<path d="M350,{420 + k * 44} q27,-14 53,0 t53,0 t53,0 t53,0 t53,0 t53,0 t53,0" fill="none"/>' for k in range(4))
        iss = audit(f'<g id="finger" data-in="none">{FINGER}</g><g data-in="none">{wr}</g>')
        self.assertIn(("overhang", "major"), kinds(iss))

    def test_declared_containment_is_enforced(self):
        bad = "".join(f'<path d="M350,{420 + k * 44} l420,0" fill="none"/>' for k in range(3))
        good = "".join(f'<path d="M360,{520 + k * 44} l250,0" fill="none"/>' for k in range(3))
        iss = audit(f'<g id="finger" data-in="none">{FINGER}</g><g data-in="none" data-inside="#finger">{bad}</g>')
        self.assertIn(("containment", "blocking"), kinds(iss))
        iss = audit(f'<g id="finger" data-in="none">{FINGER}</g><g data-in="none" data-inside="#finger">{good}</g>')
        self.assertNotIn(("containment", "blocking"), kinds(iss))

    def test_punch_cropping_scenery_is_only_minor(self):
        body = f'<g data-in="none">{FINGER}</g><rect x="880" y="700" width="180" height="200" fill="p1" data-in="none"/>'
        iss = audit(body, {"drift": "none", "punch": [{"at": 1.0, "focus": [400, 700], "zoom": 1.3, "hold": 1.5}]})
        self.assertIn(("off_canvas_punch", "minor"), kinds(iss))
        self.assertNotIn(("off_canvas", "major"), kinds(iss))

    def test_small_text(self):
        self.assertIn(("text_small", "major"), kinds(audit('<text x="540" y="400" font-size="22" data-in="none">tiny</text>')))
        self.assertIn(("text_small", "minor"), kinds(audit('<text x="540" y="400" font-size="30" data-in="none">small</text>')))

    def test_entrances_are_not_flagged_while_moving(self):
        body = f'<g data-in="slide-left" data-at="0.5">{FINGER}</g>'
        self.assertEqual(kinds(audit(body), "major"), [])

    def test_hook_stats(self):
        h = de.Timeline([{"id": "s1", "start": 0.0, "visual": {"kind": "doodle"}}],
                        [de.DoodleScene(f'<svg viewBox="0 0 1080 1920"><g data-in="none">{FINGER}</g>'
                                        '<text x="540" y="200" font-size="80" data-in="none">NOT WATER</text></svg>',
                                        words=WORDS, duration=3, camera={"drift": "none"})], 3.0, de.Paper()).audit()["hook"]
        self.assertEqual((h["elements_at_t0"], h["text_at_t0"]), (2, True))


if __name__ == "__main__":
    unittest.main()
