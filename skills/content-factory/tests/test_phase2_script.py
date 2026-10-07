"""Phase 2 script layer: hook→script integration, payoff, distinct variants, duration estimate vs real TTS, pauses.

    python -m unittest discover -s content-factory/tests -p "test_phase2_script.py" -v     (~1-2 min; I/J need Kokoro)
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT / "voice-production/scripts")); sys.path.insert(0, str(ROOT / "short-form-script/scripts"))
import estimate as E  # noqa: E402
import phase2_kit as K  # noqa: E402
import script_select as SS  # noqa: E402

B = K.beat
HOOK = {"hook_id": "h1", "spoken_text": "Pruney fingers? Not water. Nerves.", "on_screen_text": "NOT WATER", "fact_ids": ["f1", "f2"],
        "review": {"verdict": "PASS", "scores": {"hook_strength": 4, "first_frame_clarity": 5, "visual_verbal_sync": 5}}}
PUB = {"title_options": ["Pruney fingers are your nerves"], "description": "d", "hashtags": ["#x"]}
KOKORO = all((Path(os.environ.get("CF_CACHE", Path.home() / ".cache/content-factory")) / "kokoro" / f).exists()
             for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"))


def variant_a():
    return [B("b1", "hook", HOOK["spoken_text"], ["f1"], on_screen="NOT WATER"),
            B("b2", "setup", "Wrinkles aren't water soaking in.", ["f1"]),
            B("b3", "value", "If the main hand nerve is damaged, those fingers stay smooth.", ["f1"]),
            B("b4", "value", "Healthy nerves squeeze the vessels under your skin, and it folds.", ["f2"]),
            B("b5", "twist", "Why? Maybe grip. In 2013, wrinkled fingers handled wet objects faster.", ["f5"]),
            B("b6", "payoff", "So the wrinkles are your nerves at work.", ["f2"], pause_before=0.4),
            B("b7", "loop", "Not water. Nerves.", ["f1"])]


def variant_b():
    return [B("b1", "hook", HOOK["spoken_text"], ["f1"], on_screen="NOT WATER"),
            B("b2", "setup", "Here is the proof doctors use: a damaged hand nerve means no wrinkles at all, even after a long bath.", ["f1", "f3"]),
            B("b3", "value", "The reason is that your nerves narrow the tiny blood vessels under each fingertip until the skin pulls into folds.", ["f2"]),
            B("b4", "payoff", "So next time you look at pruney fingers, you are looking at nerves doing their job.", ["f2"]),
            B("b5", "loop", "Not water. Nerves.", ["f1"])]


class Phase2Script(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="p2s_"))
        (self.d / "selected_hook.json").write_text(json.dumps(HOOK))

    def run_sel(self, variants):
        return K.select_script(self.d, self.d / "selected_hook.json", variants)

    def checks(self, r, vid):
        v = next(x for x in r["scored"]["variants"] if x["variant_id"] == vid)
        return {c["id"]: c for c in v["checks"]}

    def test_H_hook_script_mismatch_blocks(self):
        bad = variant_a()
        bad[0] = B("b1", "hook", "Ever looked at your fingers after a bath?", ["f1"])
        r = self.run_sel([{"variant_id": "A", "structure": "x", "beats": bad, "publish": PUB},
                          {"variant_id": "B", "structure": "y", "beats": variant_b(), "publish": PUB}])
        c = self.checks(r, "A")["SCRIPT.HOOK_IS_OPENING"]
        self.assertEqual((c["passed"], c["severity"]), (False, "blocking"))
        a = next(x for x in r["scored"]["variants"] if x["variant_id"] == "A")
        self.assertEqual(a["verdict"], "FAIL")
        self.assertLessEqual(a["scores"]["hook_strength"], 2)

    def test_G_promise_not_paid_off(self):
        unpaid = [b if b["id"] == "b1" else {**b, "claim_ids": ["f5"]} for b in variant_a()]
        r = self.run_sel([{"variant_id": "A", "structure": "x", "beats": unpaid, "publish": PUB},
                          {"variant_id": "B", "structure": "y", "beats": variant_b(), "publish": PUB}])
        self.assertFalse(self.checks(r, "A")["SCRIPT.PROMISE_PAID"]["passed"])
        a = next(x for x in r["scored"]["variants"] if x["variant_id"] == "A")
        self.assertLessEqual(a["scores"]["payoff_coherence"], 2)

    def test_K_variants_must_really_differ(self):
        ra, rb = (SS.check_variant({"beats": v}, HOOK, {f"f{i}" for i in range(1, 6)}, 10, 60, "am_michael", 1.0)
                  for v in (variant_a(), variant_b()))
        ok, info = SS.distinct(ra, rb, {"beats": variant_a()}, {"beats": variant_b()})
        self.assertTrue(ok, info)
        reworded = [{**b, "text": b["text"].replace("squeeze", "narrow").replace("handled", "moved")} for b in variant_a()]
        rc = SS.check_variant({"beats": reworded}, HOOK, {f"f{i}" for i in range(1, 6)}, 10, 60, "am_michael", 1.0)
        ok2, info2 = SS.distinct(ra, rc, {"beats": variant_a()}, {"beats": reworded})
        self.assertFalse(ok2, info2)

    def test_selection_picks_a_passing_variant_and_writes_script(self):
        rambling = variant_b()
        rambling[2] = B("b3", "value", "The reason, which researchers have looked at for decades in many different labs and settings, is that your "
                                       "nerves narrow the tiny blood vessels under each fingertip until the skin folds.", ["f2"])
        r = self.run_sel([{"variant_id": "A", "structure": "mechanism", "beats": variant_a(), "publish": PUB},
                          {"variant_id": "B", "structure": "long-sentence explainer", "beats": rambling, "publish": PUB}])
        rows = {x["variant_id"]: x for x in r["scored"]["variants"]}
        self.assertEqual(rows["B"]["verdict"], "FAIL")
        self.assertLessEqual(rows["B"]["scores"]["message_clarity"], 2)              # a 32-word sentence is hard to follow by ear
        self.assertEqual(r["scored"]["selected"], "A")
        self.assertEqual(json.loads((self.d / "script.json").read_text())["beats"][0]["text"], HOOK["spoken_text"])

    def test_numbers_are_spoken_forms(self):
        self.assertEqual(E.spoken("In 2013, 30 people"), "In twenty thirteen, thirty people")
        self.assertEqual(E.spoken("0.2 s"), "zero point two s")
        self.assertEqual(E.spoken("measured 1,200 times"), "measured one thousand two hundred times")

    @unittest.skipUnless(KOKORO, "Kokoro not installed")
    def test_I_duration_estimate_matches_real_tts(self):
        beats = [B("b1", "hook", "Why does popcorn pop?", []), B("b2", "value", "Every kernel holds a tiny drop of water.", []),
                 B("b3", "value", "Heat turns it into steam, and the pressure builds until the hull bursts at about 180 degrees.", []),
                 B("b4", "payoff", "The fluffy part is starch that puffed up and set in a split second.", [])]
        (self.d / "s.json").write_text(json.dumps({"video_id": "t", "language": "en", "beats": beats, "publish": PUB}))
        subprocess.run([sys.executable, str(ROOT / "voice-production/scripts/tts.py"), "synth", "--script", self.d / "s.json", "--out-dir",
                        self.d, "--result", self.d / "r.json", "--voice", "am_michael", "--min-s", "1", "--max-s", "99"], capture_output=True)
        actual = json.loads((self.d / "timing.json").read_text())["duration_s"]
        new = E.estimate_script({"beats": beats}, "am_michael", 1.0)["total_s"]
        old = sum(len(b["text"].split()) / 3.0 for b in beats) + 0.2 * (len(beats) - 1)
        self.assertLessEqual(abs(new - actual) / actual, 0.08, f"new {new} vs actual {actual}")
        self.assertLess(abs(new - actual), abs(old - actual), f"old {old}, new {new}, actual {actual}")

    @unittest.skipUnless(KOKORO, "Kokoro not installed")
    def test_J_intentional_pause_is_in_the_audio(self):
        def synth(pause):
            beats = [B("b1", "hook", "Here is a quick fact.", []), B("b2", "value", "Octopuses have three hearts.", []),
                     B("b3", "payoff", "And blue blood.", [], pause_before=pause)]
            out = self.d / f"p{pause}"
            out.mkdir()
            (out / "s.json").write_text(json.dumps({"video_id": "t", "language": "en", "beats": beats, "publish": PUB}))
            subprocess.run([sys.executable, str(ROOT / "voice-production/scripts/tts.py"), "synth", "--script", out / "s.json", "--out-dir", out,
                            "--result", out / "r.json", "--voice", "am_michael", "--min-s", "1", "--max-s", "99"], capture_output=True)
            return json.loads((out / "timing.json").read_text()), json.loads((out / "r.json").read_text()), out
        t, r, out = synth(0.8)
        s = t["sentences"]
        gap = s[2]["start"] - s[1]["end"]
        self.assertGreaterEqual(gap, 0.78)
        self.assertLessEqual(gap, 0.85)
        self.assertEqual(s[2].get("pause_before"), 0.8)
        audio, sr = sf.read(out / "voice.wav")
        seg = audio[int((s[1]["end"] + 0.05) * sr): int((s[2]["start"] - 0.05) * sr)]
        self.assertLess(float(np.sqrt(np.mean(seg ** 2))), 0.01, "the pause must be silent")
        self.assertNotIn("AUDIO.MAX_GAP", {e["code"] for e in r["errors"]}, "an intentional pause is not dead air")
        self.assertEqual(r["metrics"]["intentional_pauses"][0]["before_sentence"], 2)
        t2, r2, _ = synth(0.3)                                        # change only the pause → no re-synthesis
        self.assertEqual(r2["metrics"]["tts_cache"]["misses"], 0)
        self.assertAlmostEqual(t2["sentences"][2]["start"] - t2["sentences"][1]["end"], 0.3, delta=0.03)
        est = E.estimate_sentences({"beats": [B("b1", "hook", "Here is a quick fact.", []), B("b2", "value", "Octopuses have three hearts.", []),
                                              B("b3", "payoff", "And blue blood.", [], pause_before=0.8)]}, "am_michael")
        self.assertAlmostEqual(est[2]["start"] - est[1]["end"], 0.8, delta=0.01)   # the estimator mirrors the assembly


if __name__ == "__main__":
    unittest.main()
