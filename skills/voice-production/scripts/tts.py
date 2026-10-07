#!/usr/bin/env python3
"""voice-production — synthesize narration + word-level timing for the AUDIO stage.

  tts.py setup                      # download Kokoro model files into the cache (GitHub releases)
  tts.py voices                     # list local voices
  tts.py synth --script script.json --out-dir DIR --result DIR/result.json [--backend kokoro|elevenlabs]
               [--voice af_heart] [--speed 1.0] [--min-s 15 --max-s 60] [--lexicon lexicon.json] [--no-cache]

Outputs: voice.wav (mono 24 kHz PCM16), timing.json (cf voice_timing schema), result.json (stage envelope).
Word timings come from the TTS model itself (Kokoro phoneme durations, ElevenLabs character alignment),
so subtitles are synchronized by construction rather than estimated.
"""
from __future__ import annotations

import argparse
import base64
import difflib
import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import (StageResult, cache_dir, emit, exit_for, fix, log, read_json,  # noqa: E402
                       stage_main, validate_artifact, write_json)

SR = 24000
KOKORO_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/"
KOKORO_FILES = ["kokoro-v1.0.onnx", "voices-v1.0.bin"]  # fp32 model: ~5x faster than int8 on CPUs tested
LANG = {  # script language -> (kokoro/espeak code, default voice)
    "en": ("en-us", "af_heart"), "en-us": ("en-us", "af_heart"), "en-gb": ("en-gb", "bf_emma"),
    "it": ("it", "if_sara"), "es": ("es", "ef_dora"), "fr": ("fr-fr", "ff_siwis"),
    "pt": ("pt-br", "pf_dora"), "hi": ("hi", "hf_alpha"), "ja": ("ja", "jf_alpha"), "zh": ("cmn", "zf_xiaoxiao"),
}
STRIP = set(" ˈˌ.,!?;:—–-…\"'()[]«»¿¡“”‘’")


# ----------------------------------------------------------------------------- text helpers
MAX_PAUSE = 1.5


def sentences_from_script(script: dict) -> list[dict]:
    """Sentences in order; the first/last sentence of a beat carry that beat's intentional pause_before/pause_after."""
    out = []
    for beat in script["beats"]:
        parts = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", beat["text"].strip()) if s.strip()]
        for k, p in enumerate(parts):
            out.append({"text": p, "beat_id": beat["id"],
                        "pause_before": min(MAX_PAUSE, float(beat.get("pause_before") or 0)) if k == 0 else 0.0,
                        "pause_after": min(MAX_PAUSE, float(beat.get("pause_after") or 0)) if k == len(parts) - 1 else 0.0})
    return out


def word_tokens(sentence: str) -> list[str]:
    """Whitespace tokens; punctuation-only tokens are glued to the previous word for display."""
    toks: list[str] = []
    for t in sentence.split():
        if toks and not re.search(r"\w", t):
            toks[-1] += " " + t
        else:
            toks.append(t)
    return toks


def apply_lexicon(tokens: list[str], lexicon: dict) -> str:
    out = []
    for t in tokens:
        core = re.sub(r"^\W+|\W+$", "", t)
        out.append(t.replace(core, lexicon[core.lower()]) if core and core.lower() in lexicon else t)
    return " ".join(out)


# ----------------------------------------------------------------------------- alignment
def align_phonemes(words: list[str], word_ph: list[str], timings) -> list[tuple[float, float]]:
    """Map timed phonemes (sentence-level) to words via sequence alignment of phoneme strings."""
    a_chars, a_owner = [], []
    for wi, ph in enumerate(word_ph):
        for ch in ph:
            if ch not in STRIP:
                a_chars.append(ch)
                a_owner.append(wi)
    b = [(t.phoneme, t.start, t.end) for t in timings if t.phoneme not in STRIP]
    owner_b = [None] * len(b)
    sm = difflib.SequenceMatcher(None, "".join(a_chars), "".join(x[0] for x in b), autojunk=False)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            owner_b[blk.b + k] = a_owner[blk.a + k]
    last = 0
    for i in range(len(owner_b)):  # unmatched phonemes inherit the previous owner
        if owner_b[i] is None:
            owner_b[i] = last
        last = owner_b[i]
    spans: list[list[float] | None] = [None] * len(words)
    for (ph, s, e), wi in zip(b, owner_b):
        if spans[wi] is None:
            spans[wi] = [s, e]
        else:
            spans[wi][0], spans[wi][1] = min(spans[wi][0], s), max(spans[wi][1], e)
    out, prev_end = [], (b[0][1] if b else 0.0)
    for wi in range(len(words)):  # words with no phonemes get a zero-length slot at the previous end
        s, e = spans[wi] if spans[wi] else (prev_end, prev_end)
        s = max(s, prev_end)
        e = max(e, s)
        out.append((s, e))
        prev_end = e
    return out


def proportional(words: list[str], t0: float, t1: float) -> list[tuple[float, float]]:
    w = np.array([max(1, len(re.sub(r"\W", "", x))) for x in words], dtype=float)
    edges = t0 + (t1 - t0) * np.concatenate([[0], np.cumsum(w)]) / w.sum()
    return [(float(edges[i]), float(edges[i + 1])) for i in range(len(words))]


# ----------------------------------------------------------------------------- backends
class KokoroBackend:
    name = "kokoro-onnx"

    def __init__(self, voice: str | None, lang: str, speed: float):
        from kokoro_onnx import Kokoro
        d = cache_dir() / "kokoro"
        missing = [f for f in KOKORO_FILES if not (d / f).exists()]
        if missing:
            raise RuntimeError(f"Kokoro model files missing {missing}; run `tts.py setup`")
        self.files = (str(d / KOKORO_FILES[0]), str(d / KOKORO_FILES[1]))
        self.k = Kokoro(*self.files)
        self.lang, self.voice, self.speed = lang, voice, speed
        if voice not in self.k.get_voices():
            raise ValueError(f"voice {voice!r} not available; see `tts.py voices`")
        from importlib.metadata import version
        self.model_id = f"Kokoro-82M v1.0 (onnx fp32, kokoro-onnx {version('kokoro-onnx')}, seeded per sentence)"

    def sentence(self, text: str, words: list[str]):
        # Phase 5 finding: the Kokoro graph contains random ops that ONNX Runtime seeds when a session is created, so the
        # same sentence came out different on every fresh synthesis (earlier replays matched only through the cache).
        # A fresh session seeded from the sentence's own inputs makes the audio a pure function of them — independent of
        # synthesis order, cache state and CPU count (verified 1/2/4 CPUs).
        import onnxruntime as rt
        from kokoro_onnx import Kokoro
        seed = json.dumps([text, self.voice, float(self.speed), self.lang], ensure_ascii=False)
        rt.set_seed(int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) & 0x7FFFFFFF)
        k = Kokoro(*self.files)
        audio, sr, timings = k.create_timed(text, voice=self.voice, speed=self.speed, lang=self.lang)
        assert sr == SR
        if timings:
            word_ph = [self.k.tokenizer.phonemize(w, self.lang) for w in words]
            spans, method = align_phonemes(words, word_ph, timings), "model-phoneme-durations"
        else:
            nz = np.flatnonzero(np.abs(audio) > 0.01)
            spans = proportional(words, nz[0] / SR if nz.size else 0, nz[-1] / SR if nz.size else len(audio) / SR)
            method = "proportional-estimate"
        return np.asarray(audio, dtype=np.float32), spans, method


class ElevenLabsBackend:
    """POST /v1/text-to-speech/{voice_id}/with-timestamps — returns PCM + character alignment."""
    name = "elevenlabs"

    def __init__(self, voice: str, model: str = "eleven_multilingual_v2", speed: float = 1.0):
        self.key = os.environ.get("ELEVENLABS_API_KEY")
        if not self.key:
            raise RuntimeError("ELEVENLABS_API_KEY is not set (keep it in the environment, never in files or chat)")
        self.base = os.environ.get("CF_ELEVENLABS_BASE", "https://api.elevenlabs.io")
        self.voice, self.model_id, self.speed = voice, model, speed

    def sentence(self, text: str, words: list[str]):
        url = f"{self.base}/v1/text-to-speech/{self.voice}/with-timestamps?output_format=pcm_24000"
        body = json.dumps({"text": text, "model_id": self.model_id}).encode()
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"xi-api-key": self.key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        pcm = np.frombuffer(base64.b64decode(data["audio_base64"]), dtype="<i2").astype(np.float32) / 32768.0
        al = data.get("alignment") or data.get("normalized_alignment")
        chars, starts, ends = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
        spans, wi, cur = [], 0, None
        for ch, s, e in zip(chars, starts, ends):  # group aligned characters into whitespace words
            if ch.isspace():
                if cur:
                    spans.append(tuple(cur)); cur = None
                continue
            cur = [s, e] if cur is None else [cur[0], e]
        if cur:
            spans.append(tuple(cur))
        if len(spans) != len(words):  # punctuation-only tokens were merged; fall back to proportional
            nz = np.flatnonzero(np.abs(pcm) > 0.01)
            return pcm, proportional(words, nz[0] / SR, nz[-1] / SR), "proportional-estimate"
        return pcm, spans, "provider-character-alignment"


# ----------------------------------------------------------------------------- sentence cache
TTS_CACHE_VERSION = 2   # v2 (Phase 5): seeded Kokoro synthesis; v1 entries hold unseeded audio and are never mixed in


def runtime_versions(backend: str) -> dict:
    """Inference-runtime versions that change the audio bytes (Phase 3 finding: a fresh install shifted Kokoro output by
    up to 8 ms). Part of the cache key and recorded in timing.json so cross-environment drift is visible."""
    if backend != "kokoro-onnx":
        return {}
    from importlib.metadata import PackageNotFoundError, version
    out = {}
    for pkg in ("onnxruntime", "kokoro-onnx", "numpy"):
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            out[pkg] = None
    return out


class SentenceCache:
    """Content-addressed cache of raw per-sentence TTS output (audio + word spans + timing method).

    Key = sha256 over everything that changes what the MODEL produces: cache-format version, backend, model id
    (incl. package version), model file names+sizes, voice, speed, language, the exact text sent to the model (after the
    lexicon) and the word tokens the spans are aligned to. Assembly parameters (lead, gaps, tail, peak normalisation)
    are applied after the cache, so changing them never re-synthesises but always changes the output correctly.
    Writes are atomic (tmp + rename) and every read is validated; a damaged entry is treated as a miss and rewritten.
    """

    def __init__(self, tts, lang: str, enabled: bool = True):
        self.enabled = enabled and os.environ.get("CF_TTS_CACHE", "1") != "0"
        self.dir = Path(os.environ.get("CF_TTS_CACHE_DIR") or cache_dir() / "tts") / f"v{TTS_CACHE_VERSION}"
        files = []
        if getattr(tts, "name", "") == "kokoro-onnx":
            d = cache_dir() / "kokoro"
            files = [(f, (d / f).stat().st_size) for f in KOKORO_FILES if (d / f).exists()]
        self.base = {"v": TTS_CACHE_VERSION, "backend": tts.name, "model": getattr(tts, "model_id", tts.name),
                     "model_files": files, "voice": getattr(tts, "voice", None), "speed": float(getattr(tts, "speed", 1.0)),
                     "lang": lang, "runtime": runtime_versions(getattr(tts, "name", ""))}
        self.hits, self.misses, self.rejected, self.detail = 0, 0, 0, []

    def key(self, text: str, words: list[str]) -> str:
        blob = json.dumps({**self.base, "text": text, "words": words}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def get_or_make(self, tts, text: str, words: list[str]):
        k = self.key(text, words)
        path = self.dir / k[:2] / f"{k}.npz"
        if self.enabled and path.exists():
            try:
                with np.load(path, allow_pickle=False) as z:
                    audio = z["audio"].astype(np.float32)
                    spans = [tuple(x) for x in z["spans"].tolist()]
                    method = str(z["method"])
                if audio.size and np.isfinite(audio).all() and len(spans) == len(words):
                    self.hits += 1
                    self.detail.append({"key": k[:16], "hit": True, "text": text[:48]})
                    return audio, spans, method
            except Exception:  # noqa: BLE001 — unreadable entry: fall through and re-synthesise
                pass
            self.rejected += 1
        audio, spans, method = tts.sentence(text, words)
        self.misses += 1
        self.detail.append({"key": k[:16], "hit": False, "text": text[:48]})
        if self.enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.parent / f".{k}.{os.getpid()}.tmp.npz"
            np.savez(tmp, audio=np.asarray(audio, np.float32), spans=np.asarray(spans, np.float64).reshape(-1, 2),
                     method=np.asarray(method))
            os.replace(tmp, path)
        return audio, spans, method


# ----------------------------------------------------------------------------- commands
def cmd_setup(_a) -> int:
    d = cache_dir() / "kokoro"
    d.mkdir(parents=True, exist_ok=True)
    for f in KOKORO_FILES:
        dest = d / f
        if dest.exists() and dest.stat().st_size > 1_000_000:
            log(f"ok {dest}")
            continue
        log(f"downloading {f} …")
        tmp = dest.with_suffix(".part")
        urllib.request.urlretrieve(KOKORO_RELEASE + f, tmp)
        os.replace(tmp, dest)
    print(json.dumps({"kokoro_dir": str(d), "files": {f: (d / f).stat().st_size for f in KOKORO_FILES}}))
    return 0


def cmd_voices(_a) -> int:
    from kokoro_onnx import Kokoro
    d = cache_dir() / "kokoro"
    print(" ".join(Kokoro(str(d / KOKORO_FILES[0]), str(d / KOKORO_FILES[1])).get_voices()))
    return 0


@stage_main("AUDIO", "voice-production")
def cmd_synth(a) -> int:
    script = read_json(a.script)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sr = StageResult("AUDIO", "voice-production", script.get("video_id"), attempt=a.attempt)
    sr.input(a.script, "script")
    errs = validate_artifact(script, "script")
    if errs:
        sr.fail("AUDIO.SCRIPT_INVALID", "; ".join(errs[:5]), fix=fix("SCRIPT", "repair_schema"))
        return exit_for(sr.finalize(a.result))
    lang_code, default_voice = LANG.get(script["language"].lower(), (None, None))
    lexicon = read_json(a.lexicon) if a.lexicon else {}
    if a.backend == "kokoro":
        if not lang_code:
            sr.fail("AUDIO.LANGUAGE_UNSUPPORTED", f"Kokoro has no voice for '{script['language']}'",
                    fix=fix("AUDIO", "switch_backend", backend="elevenlabs"))
            return exit_for(sr.finalize(a.result))
        tts = KokoroBackend(a.voice or default_voice, lang_code, a.speed)
    else:
        tts = ElevenLabsBackend(a.voice, speed=a.speed)

    cache = SentenceCache(tts, lang_code or script["language"], enabled=not a.no_cache)
    sents = sentences_from_script(script)
    chunks, words, sent_rows, t, methods = [], [], [], 0.0, set()
    lead = np.zeros(int(SR * a.lead_s), dtype=np.float32)
    chunks.append(lead)
    t = a.lead_s
    if sents and sents[0]["pause_before"]:          # an intentional silence before the very first line
        chunks.append(np.zeros(int(SR * sents[0]["pause_before"]), dtype=np.float32))
        t += sents[0]["pause_before"]
    intentional = set()                              # sentence indices preceded by an intentional pause
    for i, s in enumerate(sents):
        toks = word_tokens(s["text"])
        audio, spans, method = cache.get_or_make(tts, apply_lexicon(toks, lexicon) if lexicon else s["text"], toks)
        methods.add(method)
        nz = np.flatnonzero(np.abs(audio) > 0.003)  # trim to speech, keep 30 ms margins
        a0 = max(0, (nz[0] if nz.size else 0) - int(0.03 * SR))
        a1 = min(len(audio), (nz[-1] if nz.size else len(audio)) + int(0.03 * SR))
        audio = audio[a0:a1]
        off = t - a0 / SR
        s_end = t + len(audio) / SR
        prev_end = words[-1]["end"] if words else 0.0
        for tok, (ws, we) in zip(toks, spans):
            # aligners can stretch the last word over trailing silence that trimming removed: keep every word inside
            # its own sentence's audio and in order, so the next sentence never starts "before" this one ends
            st_ = min(max(off + ws, prev_end, t), s_end)
            en_ = min(max(off + we, st_), s_end)
            words.append({"w": tok, "start": round(st_, 3), "end": round(en_, 3), "sentence": i})
            prev_end = en_
        sent_rows.append({"i": i, "text": s["text"], "beat_id": s["beat_id"], "start": round(t, 3),
                          "end": round(t + len(audio) / SR, 3),
                          **({"pause_before": s["pause_before"]} if s["pause_before"] else {}),
                          **({"pause_after": s["pause_after"]} if s["pause_after"] else {})})
        chunks.append(audio)
        t += len(audio) / SR
        nxt_beat = sents[i + 1]["beat_id"] if i + 1 < len(sents) else None
        gap = a.beat_gap if nxt_beat != s["beat_id"] else a.sentence_gap
        if nxt_beat is not None and nxt_beat != s["beat_id"]:
            planned = s["pause_after"] + sents[i + 1]["pause_before"]
            if planned > 0:
                gap = max(gap, min(MAX_PAUSE, planned))
                intentional.add(i + 1)
        if nxt_beat is not None:
            chunks.append(np.zeros(int(SR * gap), dtype=np.float32))
            t += gap
    chunks.append(np.zeros(int(SR * a.tail_s), dtype=np.float32))
    audio = np.concatenate(chunks)
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = audio * (0.89 / peak)  # -1 dBFS peak; loudness is normalized at the video mix
    wav = out / "voice.wav"
    sf.write(wav, audio, SR, subtype="PCM_16")
    duration = len(audio) / SR
    timing = {"video_id": script["video_id"], "language": script["language"], "audio_path": str(wav),
              "sample_rate": SR, "duration_s": round(duration, 3), "backend": tts.name, "runtime": runtime_versions(tts.name),
              "voice": a.voice or default_voice, "speed": a.speed, "timing_method": sorted(methods),
              "words": words, "sentences": sent_rows}
    write_json(out / "timing.json", timing)

    # ---------------- gate
    expected = sum(len(word_tokens(s["text"])) for s in sents)
    speech = sum(r["end"] - r["start"] for r in sent_rows)
    wps = len(words) / max(speech, 1e-6)
    gaps = [words[k + 1]["start"] - words[k]["end"] for k in range(len(words) - 1)]
    sr.check("AUDIO.SCHEMA", not validate_artifact(timing, "voice_timing"), "blocking", "timing.json schema")
    sr.check("AUDIO.ALL_SENTENCES", len(sent_rows) == len(sents), "blocking", "every sentence synthesized")
    sr.check("AUDIO.WORD_COVERAGE", len(words) == expected, "blocking", f"{len(words)}/{expected} words timed",
             len(words), expected, fix("AUDIO", "resynthesize"))
    sr.check("AUDIO.TIMING_MONOTONIC", all(w["end"] >= w["start"] for w in words) and all(g >= -0.02 for g in gaps),
             "blocking", "word times monotonic", fix=fix("AUDIO", "resynthesize"))
    if duration > a.max_s:
        # always a real step (≥ +3 %, 2 % headroom): a speed that rounds back to the current one would just repeat the failure
        need = max(a.speed * duration / a.max_s * 1.02, a.speed + 0.03)
        route = fix("AUDIO", "speed_up", speed=round(need, 3)) \
            if need <= 1.15 else fix("SCRIPT", "shorten", target_s=a.max_s, current_s=round(duration, 1))
        sr.check("AUDIO.DURATION_IN_RANGE", False, "major", f"{duration:.1f}s > max {a.max_s}s", round(duration, 2), a.max_s, route)
    elif duration < a.min_s:
        sr.check("AUDIO.DURATION_IN_RANGE", False, "major", f"{duration:.1f}s < min {a.min_s}s", round(duration, 2), a.min_s,
                 fix("SCRIPT", "lengthen", target_s=a.min_s, current_s=round(duration, 1)))
    else:
        sr.check("AUDIO.DURATION_IN_RANGE", True, "major", value=round(duration, 2), threshold=[a.min_s, a.max_s])
    sr.check("AUDIO.SPEECH_RATE", 1.8 <= wps <= 3.8, "minor", f"{wps:.2f} words/s", round(wps, 2), [1.8, 3.8])
    # intentional pauses (pause_before/after on beats) are delivery, not dead air: judge only the other gaps
    unplanned = [g for k, g in enumerate(gaps) if words[k + 1]["sentence"] not in intentional
                 or words[k + 1]["sentence"] == words[k]["sentence"]]
    sr.check("AUDIO.MAX_GAP", max(unplanned or [0]) <= 0.75, "major", "no unplanned dead air > 0.75 s between words",
             round(max(unplanned or [0]), 3), 0.75, fix("AUDIO", "resynthesize", sentence_gap=0.12, beat_gap=0.18))
    sr.metric("intentional_pauses", [{"before_sentence": i, "seconds": round(sent_rows[i]["start"] - sent_rows[i - 1]["end"], 3)}
                                     for i in sorted(intentional)])
    sr.check("AUDIO.HOOK_START", words[0]["start"] <= 0.35, "major", "first word starts within 0.35 s",
             words[0]["start"], 0.35, fix("AUDIO", "resynthesize", lead_s=0.05))
    sr.metric("duration_s", round(duration, 2)); sr.metric("words", len(words)); sr.metric("words_per_s", round(wps, 2))
    sr.metric("tts_cache", {"enabled": cache.enabled, "hits": cache.hits, "misses": cache.misses,
                            "rejected_entries": cache.rejected, "sentences": len(sents), "version": TTS_CACHE_VERSION,
                            "detail": cache.detail})
    sr.output(wav, "voice_audio", "audio/wav"); sr.output(out / "timing.json", "voice_timing", "application/json")
    sr.provenance({"role": "voiceover", "path": str(wav), "source": "generated", "license": "self-generated",
                   "generator": {"tool": tts.name, "model": getattr(tts, "model_id", tts.name), "voice": timing["voice"],
                                 "speed": a.speed, "model_license": "Apache-2.0" if tts.name == "kokoro-onnx" else "provider ToS"},
                   "synthetic_voice": True, "realistic_human_voice": True})
    res = sr.finalize(a.result)
    emit(res)
    return exit_for(res)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup")
    sub.add_parser("voices")
    s = sub.add_parser("synth")
    s.add_argument("--script", required=True)
    s.add_argument("--out-dir", required=True)
    s.add_argument("--result", required=True)
    s.add_argument("--backend", choices=["kokoro", "elevenlabs"], default="kokoro")
    s.add_argument("--voice")
    s.add_argument("--speed", type=float, default=1.0)
    s.add_argument("--min-s", type=float, default=15)
    s.add_argument("--max-s", type=float, default=60)
    s.add_argument("--lead-s", type=float, default=0.08)
    s.add_argument("--tail-s", type=float, default=0.5)
    s.add_argument("--sentence-gap", type=float, default=0.16)
    s.add_argument("--beat-gap", type=float, default=0.24)
    s.add_argument("--lexicon")
    s.add_argument("--no-cache", action="store_true", help="always re-synthesise (also: CF_TTS_CACHE=0)")
    s.add_argument("--attempt", type=int, default=1)
    a = ap.parse_args()
    return {"setup": cmd_setup, "voices": cmd_voices, "synth": cmd_synth}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
