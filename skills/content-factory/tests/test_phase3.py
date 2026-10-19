"""Phase 3 rules: composition/layout classifier, variety gates, SFX cap, speech protection, masking, carving, ending.

    python -m unittest discover -s content-factory/tests -p "test_phase3.py" -v          (~30 s)
"""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for p in ("video-production/scripts", "visual-storyboarding/scripts", "content-factory/scripts"):
    sys.path.insert(0, str(ROOT / p))
import audio_design as ad  # noqa: E402
import doodle_engine as de  # noqa: E402
import storyboard_tool as sbt  # noqa: E402
from cf_common import StageResult  # noqa: E402

H = '<svg viewBox="0 0 1080 1920">'
FINGER = lambda x0=380, x1=700, top=340: (f'<g id="f{x0}" data-in="none"><path d="M{x0},1040 L{x0},{top + 140} C{x0},{top - 20} {x1},{top - 20} '  # noqa: E731
                                          f'{x1},{top + 140} L{x1},1040 Z" fill="#f6c9a8"/></g>')


def comp(body: str) -> dict:
    return de.DoodleScene(H + body + "</svg>", duration=3.0).composition()


def gates(comps: list[dict], roles=None, n15=2) -> dict:
    scenes = [{"id": f"s{i + 1}", "beat_ids": [f"b{i + 1}"], "visual": {"composition": c, "frame0": {"visual_events_first_1_5s": n15}}}
              for i, c in enumerate(comps)]
    sr = StageResult("VISUAL_PLAN", "t", "v")
    sbt.comp_gates(sr, scenes, roles or {})
    return {c["id"]: c for c in sr.d["gate"]["checks"]}


def fake(layout, sig, h=0.35, empty=1):
    return {"layout": layout, "main_signature": sig, "main_subject": sig, "main_height_ratio": h, "empty_cells": empty}


class Composition(unittest.TestCase):
    def test_layout_classes(self):
        self.assertEqual(comp(FINGER())["layout"], "hero")
        self.assertEqual(comp(FINGER(150, 450) + FINGER(630, 930))["layout"], "split")
        self.assertEqual(comp('<rect x="120" y="560" width="840" height="400" fill="#f6c9a8" data-in="none"/>')["layout"], "panel")
        self.assertEqual(comp('<text x="540" y="600" font-family="marker" font-size="220" data-in="none">2 : 1</text>'
                              '<g data-lib="sparkle" transform="translate(900 300) scale(0.6)" data-in="none"/>')["layout"], "text_led")
        self.assertEqual(comp('<g data-lib="dude" transform="translate(540 1040) scale(1.3)" data-in="none"/>')["layout"], "character")
        self.assertEqual(comp(FINGER(80, 330) + FINGER(400, 650) + FINGER(720, 970))["layout"], "grid")

    def test_signature_is_position_and_scale_invariant(self):
        a = comp(FINGER(380, 700))["main_signature"]
        b = comp(f'<g transform="translate(-200 100) scale(0.9)">{FINGER(380, 700)}</g>')["main_signature"]
        c = comp('<rect x="120" y="560" width="840" height="400" fill="#f6c9a8" data-in="none"/>')["main_signature"]
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_dead_space(self):
        self.assertGreaterEqual(comp('<circle cx="200" cy="200" r="60" fill="red" data-in="none"/>')["empty_cells"], 5)
        # two tall fingers fill the middle and bottom rows; the top row (y 96-414) is honestly mostly empty → 3
        self.assertLessEqual(comp(FINGER(150, 450) + FINGER(630, 930))["empty_cells"], 3)


class VarietyGates(unittest.TestCase):
    def test_layout_repeat(self):
        self.assertFalse(gates([fake("hero", "a"), fake("hero", "b"), fake("hero", "c")])["VIS.LAYOUT_REPEAT"]["passed"])
        self.assertTrue(gates([fake("hero", "a"), fake("hero", "b"), fake("split", "c")])["VIS.LAYOUT_REPEAT"]["passed"])

    def test_subject_repeat_run_and_share(self):
        g = gates([fake("hero", "f"), fake("split", "f"), fake("panel", "f"), fake("hero", "x")])
        self.assertFalse(g["VIS.SUBJECT_REPEAT"]["passed"])                           # 3 in a row
        g = gates([fake("hero", "f"), fake("panel", "x"), fake("split", "f"), fake("grid", "y"), fake("hero", "f")])
        self.assertFalse(g["VIS.SUBJECT_REPEAT"]["passed"])                           # 3 of 5 = 60 %

    def test_loop_callback_is_exempt(self):
        cs = [fake("hero", "f"), fake("panel", "x"), fake("split", "y"), fake("grid", "f"), fake("hero", "f")]
        roles = {"b5": "loop"}
        self.assertTrue(gates(cs, roles)["VIS.SUBJECT_REPEAT"]["passed"])            # 2 of 4 non-loop scenes = 50 %

    def test_subject_size_and_dead_space_and_opening_density(self):
        g = gates([fake("hero", "a", h=0.15), fake("split", "b", empty=6)], n15=1)
        self.assertEqual((g["VIS.SUBJECT_SIZE"]["passed"], g["VIS.SUBJECT_SIZE"]["severity"]), (False, "major"))
        self.assertFalse(g["VIS.DEAD_SPACE"]["passed"])
        self.assertFalse(g["VIS.OPENING_DENSITY"]["passed"])
        g = gates([fake("hero", "a", h=0.22), fake("split", "b")], n15=2)
        self.assertEqual(g["VIS.SUBJECT_SIZE"]["severity"], "minor")
        self.assertTrue(g["VIS.OPENING_DENSITY"]["passed"])


def speech(dur=6.0, seed=0):
    """Tone-burst 'speech' with real pauses: 0.25 s syllables, 0.08 s gaps, a 0.6 s pause every 6 syllables."""
    sr, t, out = ad.SR, 0.2, np.zeros(int(dur * ad.SR))
    k = 0
    while t < dur - 0.4:
        n = int(0.25 * sr)
        tt = np.arange(n) / sr
        out[int(t * sr): int(t * sr) + n] = 0.5 * np.sin(2 * np.pi * (180 + 40 * (k % 3)) * tt) * np.hanning(n) * \
            (1 + 0.5 * np.sin(2 * np.pi * 900 * tt))
        t += 0.33 + (0.6 if k % 6 == 5 else 0)
        k += 1
    return out.astype(np.float32)


class OpeningTokenisation(unittest.TestCase):
    def test_punctuated_hook_text_counts_as_visible(self):
        """Regression (Phase 3 run): 'TEAR GAS?' on screen was reported as not visible because 'GAS?' != 'GAS'."""
        import re
        shown, want = "TEAR GAS?", re.findall(r"[A-Za-z0-9']+", "TEAR GAS?".upper())
        src = (ROOT / "visual-storyboarding/scripts/storyboard_tool.py").read_text(encoding="utf-8")
        self.assertIn('got = set(re.findall(r"[A-Za-z0-9\']+", shown.upper()))', src)
        self.assertTrue(all(w in set(re.findall(r"[A-Za-z0-9']+", shown.upper())) for w in want))


class RuntimePinning(unittest.TestCase):
    def test_runtime_versions_in_cache_key_and_pinned(self):
        """Regression (2026-10-07): a fresh install shifted Kokoro output by up to 8 ms. The cache must not mix runtimes,
        and the reference runtime is pinned."""
        sys.path.insert(0, str(ROOT / "voice-production/scripts"))
        import tts
        rv = tts.runtime_versions("kokoro-onnx")
        self.assertIn("onnxruntime", rv)
        self.assertEqual(tts.runtime_versions("elevenlabs"), {})
        src = (ROOT / "voice-production/scripts/tts.py").read_text(encoding="utf-8")
        self.assertIn('"runtime": runtime_versions(getattr(tts, "name", ""))', src)
        setup = (ROOT / "content-factory/scripts/setup_env.py").read_text(encoding="utf-8")
        self.assertIn('"onnxruntime==', setup)
        self.assertIn('"kokoro-onnx==', setup)


class Audio(unittest.TestCase):
    def test_sfx_cap(self):
        ev = [{"t": 0.1 * i, "kind": "pop", "dur": 0.13, "id": f"p{i}"} for i in range(100)] + \
             [{"t": 3.05, "kind": "whoosh", "dur": 0.3, "id": "transition:whip"}, {"t": 9.9, "kind": "boing", "dur": 0.5, "id": "late"}]
        kept, info = ad.cap_events(ev, 10.0)
        self.assertLessEqual(len(kept), 8)
        ts = sorted(e["t"] for e in kept)
        self.assertTrue(all(b - a >= 0.35 - 1e-9 for a, b in zip(ts, ts[1:])))
        self.assertIn("transition:whip", {e["id"] for e in kept})                   # transitions win the budget
        self.assertNotIn("late", {e["id"] for e in kept})                           # would run into the ending
        self.assertEqual(ad.cap_events(ev, 10.0), (kept, info))                     # deterministic

    def test_speech_protection_and_masking(self):
        v = speech()
        n = v.size
        noise = np.random.default_rng(1).normal(0, 1, n)
        loud = np.stack([ad._band(noise, 300, 4000) * 0.4] * 2, axis=1)            # SFX right on top of the voice
        prot, info = ad.protect_speech(v, loud)
        self.assertGreater(info["frames_attenuated"], 0)
        bad = ad.speech_masking(v, ad.mix(v, None, loud))
        good = ad.speech_masking(v, ad.mix(v, None, prot))
        self.assertLess(bad["sir_p5_db"], 10)
        self.assertGreaterEqual(good["sir_p5_db"], 10)
        self.assertLess(good["speech_frames"], good["envelope_frames"])            # pauses inside the envelope excluded

    def test_carving_cuts_only_the_speech_band_during_speech(self):
        v = speech()
        env = ad.speech_envelope(ad._norm(v, 0.7))
        noise = np.random.default_rng(2).normal(0, 0.3, (v.size, 2))
        flat = ad.music_component(noise, v.size, env, -10.0, 0.0, 0.0)[:, 0]
        cut = ad.music_component(noise, v.size, env, -10.0, 0.0, 12.0)[:, 0]
        sp, quiet = env > 0.9, env < 0.05
        mid = lambda x, m: np.sqrt(np.mean(ad._band(x, 300, 4000)[m] ** 2))       # noqa: E731
        low = lambda x, m: np.sqrt(np.mean(ad._band(x, 20, 250)[m] ** 2))         # noqa: E731
        self.assertLess(20 * np.log10(mid(cut, sp) / mid(flat, sp)), -9)            # speech band cut while talking
        self.assertAlmostEqual(20 * np.log10(low(cut, sp) / low(flat, sp)), 0, delta=1.0)
        self.assertAlmostEqual(20 * np.log10(mid(cut, quiet) / mid(flat, quiet)), 0, delta=1.5)

    def test_closed_loop_level_and_determinism(self):
        v = speech()
        bed, _ = ad.playful_bed(v.size / ad.SR, seed=3)
        mdb = -19.0
        mu0 = ad.mix_report(v, bed, None, music_db=mdb, carve_db=12)["music_under_voice_db"]
        mdb += mu0 - 17.0
        self.assertAlmostEqual(ad.mix_report(v, bed, None, music_db=mdb, carve_db=12)["music_under_voice_db"], 17.0, delta=0.3)
        a = ad.mix(v, bed, None, music_db=mdb, carve_db=12)
        b = ad.mix(v, bed, None, music_db=mdb, carve_db=12)
        self.assertTrue(np.array_equal(a, b))

    def test_ending(self):
        v = speech(4)
        bed, _ = ad.playful_bed(v.size / ad.SR, seed=4)
        good = ad.ending_report(ad.mix(v, bed, None, music_db=-10), bed)
        self.assertLessEqual(good["tail_30ms_dbfs"], -45)
        self.assertGreaterEqual(good["music_fade_db"], 6)
        clicky = np.stack([np.r_[np.zeros(v.size - 1000), 0.5 * np.ones(1000)]] * 2, axis=1)
        self.assertGreater(ad.ending_report(clicky, None)["tail_30ms_dbfs"], -45)


if __name__ == "__main__":
    unittest.main()
