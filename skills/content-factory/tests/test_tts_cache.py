"""TTS sentence cache: reuse, invalidation on every model-affecting input, corruption recovery (real Kokoro, ~1-2 min).

    python -m unittest discover -s content-factory/tests -p "test_tts_cache.py" -v
Skips when the Kokoro model files are not installed (run voice-production/scripts/tts.py setup).
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TTS = ROOT / "voice-production" / "scripts" / "tts.py"
CACHE_ROOT = Path(os.environ.get("CF_CACHE", Path.home() / ".cache" / "content-factory"))
BEATS = [("b1", "hook", "Octopuses taste with their arms."), ("b2", "value", "Each sucker is a tiny tongue."),
         ("b3", "payoff", "Weird, right?")]


def have_kokoro() -> bool:
    return all((CACHE_ROOT / "kokoro" / f).exists() for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"))


@unittest.skipUnless(have_kokoro(), "Kokoro model not installed")
class TtsCache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="tts_cache_test_"))
        cls.env = {**os.environ, "CF_TTS_CACHE_DIR": str(cls.tmp / "cache")}

    def synth(self, name, beats=BEATS, extra=(), lexicon=None):
        d = self.tmp / name
        d.mkdir(parents=True, exist_ok=True)
        script = {"video_id": "t", "language": "en", "beats": [{"id": i, "role": r, "text": t, "claim_ids": []} for i, r, t in beats],
                  "publish": {"title_options": ["t"], "description": "", "hashtags": []}}
        (d / "script.json").write_text(json.dumps(script))
        cmd = [sys.executable, str(TTS), "synth", "--script", str(d / "script.json"), "--out-dir", str(d), "--result",
               str(d / "result.json"), "--min-s", "1", "--max-s", "60", "--voice", "am_michael", *extra]
        if lexicon is not None:
            (d / "lex.json").write_text(json.dumps(lexicon))
            cmd += ["--lexicon", str(d / "lex.json")]
        subprocess.run(cmd, capture_output=True, text=True, env=self.env)
        res = json.loads((d / "result.json").read_text())
        failed = {e["code"] for e in res["errors"]}
        self.assertNotIn("AUDIO.TIMING_MONOTONIC", failed, f"{name}: word timings overlap")  # regression (Phase 0 run)
        wav = hashlib.sha256((d / "voice.wav").read_bytes()).hexdigest()
        return res["metrics"]["tts_cache"], wav

    def test_cache_behaviour(self):
        c, wav0 = self.synth("cold")
        self.assertEqual((c["hits"], c["misses"]), (0, 3), c)                       # 3 sentences, cold cache
        c, wav1 = self.synth("warm")
        self.assertEqual((c["hits"], c["misses"]), (3, 0), c)                       # identical input → all reused
        self.assertEqual(wav0, wav1, "a cached rerun must reproduce the voice-over byte for byte")
        changed = [BEATS[0], BEATS[1], ("b3", "payoff", "Strange, right?")]
        c, _ = self.synth("text", beats=changed)
        self.assertEqual((c["hits"], c["misses"]), (2, 1), c)                       # only the edited sentence
        c, _ = self.synth("voice", extra=["--voice", "af_heart"])
        self.assertEqual(c["misses"], 3, c)                                         # voice is part of the key
        c, _ = self.synth("speed", extra=["--speed", "1.1"])
        self.assertEqual(c["misses"], 3, c)                                         # speed is part of the key
        c, _ = self.synth("lexicon", lexicon={"octopuses": "OCK-toe-puss-iz"})
        self.assertEqual((c["hits"], c["misses"]), (2, 1), c)                       # pronunciation edit → that sentence
        c, wav_gap = self.synth("gap", extra=["--beat-gap", "0.4"])
        self.assertEqual((c["hits"], c["misses"]), (3, 0), c)                       # assembly change: no re-synthesis…
        self.assertNotEqual(wav_gap, wav0, "…but the assembled audio must change")
        # simulate torn writes on every entry (picking one via rglob order was filesystem-dependent: it could hit an
        # entry of the af_heart / speed runs that the next synth never reads)
        for entry in (self.tmp / "cache").rglob("*.npz"):
            entry.write_bytes(b"truncated")
        c, wav2 = self.synth("corrupt")
        self.assertEqual((c["rejected_entries"], c["misses"]), (3, 3), c)           # damaged entries rejected, rebuilt
        c, _ = self.synth("rebuilt")
        self.assertEqual((c["hits"], c["misses"]), (3, 0), c)
        c, _ = self.synth("nocache", extra=["--no-cache"])
        self.assertEqual((c["enabled"], c["misses"]), (False, 3), c)


if __name__ == "__main__":
    unittest.main()
