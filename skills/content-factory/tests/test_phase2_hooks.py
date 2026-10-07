"""Phase 2 hook engine: frame-0 rendering + independent scoring + selection (A-G, L, M, N).

    python -m unittest discover -s content-factory/tests -p "test_phase2_hooks.py" -v      (~1-2 min)
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase2_kit as K  # noqa: E402

H, F, W = K.H, K.finger, K.WATER


def one(svg: str, spoken="Pruney fingers? Not water. Nerves.", on_screen="NOT WATER", **extra):
    """Score a single candidate inside an otherwise valid, diverse set (the other four are irrelevant fillers)."""
    d = Path(tempfile.mkdtemp(prefix="p2h_"))
    fill = H + F() + W + '<text x="540" y="215" font-family="marker" font-size="96" data-in="none">FILLER</text></svg>'
    svgs = {"x": svg, **{f"f{i}": fill for i in range(4)}}
    cands = [K.cand("x", spoken, "x", on_screen, mech="target", **extra)] + \
            [K.cand(f"f{i}", f"Filler number {i} about {w} things.", f"f{i}", "FILLER", mech=f"filler_{i}") for i, w in
             enumerate(["blue", "green", "loud", "quiet"])]
    r = K.select_hooks(K.write_set(d, svgs, cands))
    x = next(c for c in r["scored"]["candidates"] if c["hook_id"] == "x")
    return x, r


def ids(x):
    return {f["id"] for f in x["review"]["failures"]}


class Phase2Hooks(unittest.TestCase):
    def test_A_strong_visual_hook_passes(self):
        x, r = one(K.STRONG_SVG)
        s = x["review"]["scores"]
        self.assertEqual(x["review"]["verdict"], "PASS", x["review"]["failures"])
        self.assertTrue(s["hook_strength"] >= 4 and s["first_frame_clarity"] >= 4 and s["visual_verbal_sync"] >= 4, s)
        m = x["measurements"]
        self.assertGreaterEqual(m["subject_height_ratio"], 0.35)
        self.assertEqual(m["texts_t0"][0]["on_screen"], "NOT WATER")

    def test_B_empty_first_frame(self):
        x, _ = one(H + F().replace('data-in="none"', 'data-in="pop" data-at="1.2"', 1) + "</svg>")
        self.assertIn("FRAME0.BLANK", ids(x))
        self.assertEqual(x["review"]["scores"]["first_frame_clarity"], 1)

    def test_C_tiny_subject_fails_unless_documented(self):
        tiny = H + '<g transform="translate(470 560) scale(0.25)">' + F() + "</g>" + W + \
            '<text x="540" y="215" font-family="marker" font-size="96" data-in="none">NOT WATER</text>' + \
            '<g data-lib="sparkle" transform="translate(800 500)" data-in="pop" data-at="0.2"/></svg>'
        x, _ = one(tiny)
        self.assertIn("FRAME0.SUBJECT_SMALL", ids(x))
        self.assertLessEqual(x["review"]["scores"]["first_frame_clarity"], 3)
        x, _ = one(tiny.replace("<svg ", '<svg data-hook-exception="scale contrast: a tiny finger in a huge bath is the joke" ', 1))
        self.assertNotIn("FRAME0.SUBJECT_SMALL", ids(x))
        self.assertIn("exception", " ".join(x["review"]["evidence"]["first_frame_clarity"]))

    def test_D_cropped_hook_text(self):
        x, _ = one(K.STRONG_SVG.replace('<text x="540" y="215"', '<text x="960" y="215"'), on_screen="NOT WATER")
        self.assertTrue({"FRAME0.TEXT_CROPPED", "FRAME0.NEGATION_HIDDEN", "FRAME0.TEXT_OUTSIDE_SAFE"} & ids(x), ids(x))
        self.assertEqual(x["review"]["verdict"], "FAIL")

    def test_E_hidden_negative_word(self):
        x, _ = one(K.STRONG_SVG.replace('<text x="540" y="215"', '<text x="150" y="215"'))
        self.assertIn("FRAME0.NEGATION_HIDDEN", ids(x))
        self.assertLessEqual(x["review"]["scores"]["first_frame_clarity"], 1)

    def test_F_weak_verbal_hook(self):
        x, _ = one(K.STRONG_SVG, spoken="In this video we talk a little bit about fingers.", on_screen="FINGERS")
        self.assertLessEqual(x["review"]["scores"]["hook_strength"], 2)
        self.assertIn("generic opener", " ".join(x["review"]["evidence"]["hook_strength"]))

    def test_G_hook_without_supported_payoff(self):
        x, _ = one(K.STRONG_SVG, fact_ids=["f99"])
        self.assertIn("HOOK.UNSUPPORTED_PROMISE", ids(x))

    def test_L_M_N_selection_failure_and_no_blind_retry(self):
        d = Path(tempfile.mkdtemp(prefix="p2sel_"))
        strong2 = K.STRONG_SVG.replace("NOT WATER", "NOT THE WATER")
        weak = H + F() + W + "</svg>"                       # one element group, no text, no early event
        svgs = {"s1": K.STRONG_SVG, "s2": strong2, "w1": weak, "w2": weak.replace("280", "290"), "w3": weak.replace("280", "300")}
        cands = [K.cand("s1", "Pruney fingers? Not water. Nerves.", "s1", "NOT WATER", mech="reversal"),
                 K.cand("s2", "Fingers prune. Not from water.", "s2", "NOT THE WATER", mech="claim", fact_ids=["f1"]),
                 K.cand("w1", "Fingers get wrinkly.", "w1", "", mech="plain"),
                 K.cand("w2", "Bath time is long.", "w2", "", mech="flat"),
                 K.cand("w3", "Water is wet sometimes.", "w3", "", mech="dull")]
        r = K.select_hooks(K.write_set(d, svgs, cands))
        rows = {c["hook_id"]: c for c in r["scored"]["candidates"]}
        totals = {k: v.get("total") for k, v in rows.items() if v["review"]["verdict"] == "PASS"}
        sel = r["scored"]["selected"]                                                       # L: strongest passing candidate,
        best = max(totals.values())                                                         #    ties → shorter spoken line
        self.assertEqual(totals[sel], best)
        tied = [k for k, v in totals.items() if v == best]
        self.assertEqual(sel, min(tied, key=lambda k: rows[k]["estimated_duration_s"]))
        self.assertNotIn(sel, {"w1", "w2", "w3"})
        self.assertTrue((d / "opening_brief.json").exists())
        ob = json.loads((d / "opening_brief.json").read_text())["opening_beat"]
        for k in ("subject", "subject_size_target", "composition", "first_frame_state", "on_screen_text", "spoken_line",
                  "visual_action", "emphasis_words", "camera_intent", "safe_margin"):
            self.assertIn(k, ob)
        # M: a set where nothing passes → structured failure, nothing selected
        d2 = Path(tempfile.mkdtemp(prefix="p2none_"))
        r2 = K.select_hooks(K.write_set(d2, {k: weak.replace("280", str(280 + i)) for i, k in enumerate("abcde")},
                                        [K.cand(k, f"Plain line {k} about baths.", k, "", mech=f"m{k}") for k in "abcde"]))
        res = r2["result"]
        self.assertEqual(res["status"], "failed")
        sel = next(e for e in res["errors"] if e["code"] == "HOOK.SELECTED")
        self.assertEqual(sel["fix_route"]["params"]["strategy"], "change")
        self.assertEqual(len(sel["fix_route"]["params"]["failed"]), 5)
        self.assertFalse((d2 / "selected_hook.json").exists())
        # N: resubmitting the identical failed set is refused, not re-scored; no automatic route (→ escalation)
        r3 = K.select_hooks(d2, attempt=2)
        codes = {e["code"]: e for e in r3["result"]["errors"]}
        self.assertIn("HOOK.FUTILE_RESUBMISSION", codes)
        self.assertIsNone(codes["HOOK.FUTILE_RESUBMISSION"]["fix_route"])
        self.assertTrue(all(c["status"] == "repeated_failed" for c in r3["scored"]["candidates"]))

    def test_author_reasoning_never_reaches_the_reviewer(self):
        x, r = one(K.STRONG_SVG)
        pk = Path(x["frame0"]).parent / "packet"
        blob = "".join(p.read_text(errors="ignore") for p in pk.rglob("*.json"))
        self.assertNotIn("AUTHOR-REASONING-SECRET", blob)
        self.assertNotIn("curiosity_mechanism", blob)

    def test_diversity_gate(self):
        d = Path(tempfile.mkdtemp(prefix="p2div_"))
        cands = [K.cand(f"c{i}", "Pruney fingers are not water, they are nerves.", "x", mech="same") for i in range(5)]
        r = K.select_hooks(K.write_set(d, {"x": K.STRONG_SVG}, cands))
        div = next(e for e in r["result"]["errors"] if e["code"] == "HOOK.DIVERSITY")
        self.assertEqual(div["severity"], "major")


if __name__ == "__main__":
    unittest.main()
