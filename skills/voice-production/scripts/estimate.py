#!/usr/bin/env python3
"""estimate — spoken-duration model calibrated on the real TTS voice (replaces flat words-per-second guesses).

  estimate.py script --script script.json [--voice am_michael] [--speed 1.0]      → per-beat / total seconds (JSON)
  estimate.py calibrate --voice am_michael [--corpus references/calibration_corpus.txt]
        synthesises the corpus with the real TTS (sentence cache makes reruns free), fits the model, writes
        references/voice_calibration.json
  estimate.py fit --timing a/timing.json b/timing.json …     fit from existing runs' timing.json (no synthesis)

Model per voice (seconds at speed 1.0, divided by speed):
  sentence = a·syllables + b·words + c·commas + d·(question?) + e
Syllables are counted on the SPOKEN form (numbers expanded: "2013" → "twenty thirteen", "0.2" → "zero point two").
Whole-script estimates mirror tts.py assembly exactly: lead, per-sentence audio, sentence gaps inside a beat, beat
gaps between beats, explicit pause_before/pause_after on beats, tail.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CALIB = HERE.parent / "references" / "voice_calibration.json"
CORPUS = HERE.parent / "references" / "calibration_corpus.txt"
ASSEMBLY = {"lead": 0.08, "tail": 0.5, "sentence_gap": 0.16, "beat_gap": 0.24}   # tts.py defaults
ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen " \
       "eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _num(n: int) -> str:
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else " " + ONES[n % 10])
    if n < 1000:
        return ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + _num(n % 100))
    if n < 1_000_000:
        return _num(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + _num(n % 1000))
    return _num(n // 1_000_000) + " million" + ("" if n % 1_000_000 == 0 else " " + _num(n % 1_000_000))


def spoken(text: str) -> str:
    def year_or_num(m: re.Match) -> str:
        s = m.group(0)
        if "." in s:
            a, b = s.split(".", 1)
            return f"{_num(int(a or 0))} point {' '.join(ONES[int(c)] for c in b)}"
        n = int(s.replace(",", ""))
        if 1100 <= n <= 2099 and n % 100 != 0 and "," not in s:   # read as a year
            return f"{_num(n // 100)} {('oh ' + ONES[n % 100]) if n % 100 < 10 else _num(n % 100)}"
        return _num(n)
    # thousands separators only when exactly three digits follow ("1,200"); "2013, wrinkled" keeps its comma
    t = re.sub(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?", year_or_num, text)
    return t.replace("%", " percent").replace("&", " and ")


def syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and not w.endswith(("le", "ee", "ye")) and n > 1:
        n -= 1
    if w.endswith("ed") and not w.endswith(("ted", "ded")) and n > 1:
        n -= 1
    return max(1, n)


def features(text: str) -> list[float]:
    sp = spoken(text)
    words = sp.split()
    return [sum(syllables(w) for w in words), len(words), text.count(",") + text.count(";") + text.count(":"),
            1.0 if text.strip().endswith("?") else 0.0, 1.0]


def load_calib() -> dict:
    return json.loads(CALIB.read_text(encoding="utf-8")) if CALIB.exists() else {}


def coef_for(voice: str) -> list[float]:
    c = load_calib()
    if voice in c:
        return c[voice]["coef"]
    if c:  # unknown voice: average of calibrated voices
        return list(np.mean([v["coef"] for v in c.values()], axis=0))
    return [0.19, 0.05, 0.12, 0.05, 0.25]          # uncalibrated fallback (≈ Kokoro English)


def sentence_seconds(text: str, voice: str = "am_michael", speed: float = 1.0) -> float:
    return max(0.25, float(np.dot(coef_for(voice), features(text)))) / max(speed, 0.5)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def estimate_script(script: dict, voice: str = "am_michael", speed: float = 1.0, **asm) -> dict:
    a = {**ASSEMBLY, **{k: v for k, v in asm.items() if v is not None}}
    t, beats, pending = a["lead"], [], 0.0
    for bi, b in enumerate(script["beats"]):
        sents = split_sentences(b["text"])
        pb = min(1.5, float(b.get("pause_before") or 0))
        # mirrors tts.py: gap between beats = max(beat_gap, previous pause_after + this pause_before), capped 1.5 s
        t += pb if bi == 0 else max(a["beat_gap"], min(1.5, pending + pb))
        start = t
        for si, s in enumerate(sents):
            if si:
                t += a["sentence_gap"]
            t += sentence_seconds(s, voice, speed)
        beats.append({"id": b["id"], "role": b.get("role"), "start": round(start, 2), "end": round(t, 2),
                      "seconds": round(t - start, 2), "sentences": len(sents)})
        pending = min(1.5, float(b.get("pause_after") or 0))
    total = t + a["tail"]
    return {"voice": voice, "speed": speed, "total_s": round(total, 2), "speech_s": round(sum(x["seconds"] for x in beats), 2),
            "beats": beats, "hook_s": beats[0]["seconds"] if beats else 0.0, "calibrated": voice in load_calib()}


def estimate_sentences(script: dict, voice: str = "am_michael", speed: float = 1.0, **asm) -> list[dict]:
    """Sentence-level estimated timeline (text, start, end, beat id) mirroring tts.py assembly incl. intentional pauses."""
    a = {**ASSEMBLY, **{k: v for k, v in asm.items() if v is not None}}
    t, out, pending = a["lead"], [], 0.0
    for bi, b in enumerate(script["beats"]):
        pb = min(1.5, float(b.get("pause_before") or 0))
        t += pb if bi == 0 else max(a["beat_gap"], min(1.5, pending + pb))
        for si, sent in enumerate(split_sentences(b["text"])):
            if si:
                t += a["sentence_gap"]
            d = sentence_seconds(sent, voice, speed)
            out.append({"text": sent, "start": round(t, 3), "end": round(t + d, 3), "beat_id": b["id"]})
            t += d
        pending = min(1.5, float(b.get("pause_after") or 0))
    return out


def fit(samples: list[tuple[str, float, float]]) -> tuple[list[float], float]:
    X = np.array([features(t) for t, _, _ in samples])
    y = np.array([d * sp for _, d, sp in samples])          # normalise to speed 1.0
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    mae = float(np.mean(np.abs(X @ coef - y)))
    return [round(float(c), 5) for c in coef], round(mae, 3)


def save_calib(voice: str, coef: list[float], mae: float, n: int, source: str) -> None:
    c = load_calib()
    c[voice] = {"coef": coef, "features": ["syllables", "words", "commas", "question", "bias"], "mae_s": mae, "samples": n,
                "source": source}
    CALIB.parent.mkdir(parents=True, exist_ok=True)
    CALIB.write_text(json.dumps(c, indent=1), encoding="utf-8")


def samples_from_timing(paths: list[str]) -> dict[str, list]:
    out: dict[str, list] = {}
    for p in paths:
        t = json.loads(Path(p).read_text(encoding="utf-8"))
        v, sp = t.get("voice", "am_michael"), float(t.get("speed", 1.0))
        for s in t["sentences"]:
            out.setdefault(v, []).append((s["text"], s["end"] - s["start"], sp))
    return out


def cmd_calibrate(a) -> int:
    import subprocess
    import tempfile
    lines = [ln.strip() for ln in Path(a.corpus).read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    beats = [{"id": f"b{i + 1}", "role": "value", "text": s, "claim_ids": []} for i, s in enumerate(lines)]
    beats[0]["role"] = "hook"
    with tempfile.TemporaryDirectory() as td:
        sp = Path(td) / "script.json"
        sp.write_text(json.dumps({"video_id": "calib", "language": "en", "beats": beats,
                                  "publish": {"title_options": ["c"], "description": "", "hashtags": []}}))
        subprocess.run([sys.executable, str(HERE / "tts.py"), "synth", "--script", sp, "--out-dir", td, "--result",
                        Path(td) / "r.json", "--voice", a.voice, "--min-s", "1", "--max-s", "9999"], check=False, capture_output=True)
        smp = samples_from_timing([str(Path(td) / "timing.json")])[a.voice]
    coef, mae = fit(smp)
    save_calib(a.voice, coef, mae, len(smp), f"corpus {Path(a.corpus).name}")
    print(json.dumps({"voice": a.voice, "coef": coef, "mae_s": mae, "samples": len(smp)}))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("script"); s.add_argument("--script", required=True); s.add_argument("--voice", default="am_michael")
    s.add_argument("--speed", type=float, default=1.0)
    c = sub.add_parser("calibrate"); c.add_argument("--voice", default="am_michael"); c.add_argument("--corpus", default=str(CORPUS))
    f = sub.add_parser("fit"); f.add_argument("--timing", nargs="+", required=True)
    a = ap.parse_args()
    if a.cmd == "script":
        print(json.dumps(estimate_script(json.loads(Path(a.script).read_text(encoding="utf-8")), a.voice, a.speed), indent=1))
    elif a.cmd == "calibrate":
        return cmd_calibrate(a)
    else:
        for v, smp in samples_from_timing(a.timing).items():
            coef, mae = fit(smp)
            save_calib(v, coef, mae, len(smp), "timing files")
            print(json.dumps({"voice": v, "coef": coef, "mae_s": mae, "samples": len(smp)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
