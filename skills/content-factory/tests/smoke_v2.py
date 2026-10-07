#!/usr/bin/env python3
"""End-to-end smoke test of the v2 media chain — no TTS, no network, ~1 minute on one CPU.

  python smoke_v2.py [--keep DIR]

Builds a synthetic 6 s "voice" (tone bursts) with matching word timings, a 3-scene doodle storyboard, then runs the
real stage scripts exactly as factory.py does: VISUAL_PLAN render → retime → VIDEO → SUBTITLES → QA check, and a
negative test that a corrupted master is rejected by the decode gate. Exit 0 = all assertions passed.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]          # folder that holds all factory skills
PY = sys.executable
WORDS = [("Try", "b1"), ("to", "b1"), ("tickle", "b1"), ("yourself.", "b1"), ("Your", "b2"), ("brain", "b2"),
         ("spoils", "b2"), ("it.", "b2"), ("Add", "b3"), ("a", "b3"), ("robot.", "b3")]
SCENES = {
    # Phase 2 opening rules: subject ≥35 % of frame height, ≥2 elements + text at t=0, a visual event ≤0.5 s
    "s1": '<g data-lib="dude" data-pose="tickle-self" data-face="meh" transform="translate(540 1040) scale(1.9)" data-in="none"/>'
          '<text x="540" y="200" font-family="marker" font-size="96" data-in="none">TICKLE?</text>'
          '<g data-lib="feather" data-fill="p1" transform="translate(230 560)" data-in="pop" data-at="0.2"/>'
          # Phase 3: a second early event and no dead half of the frame
          '<g data-lib="question" transform="translate(860 600)" data-in="pop" data-at="0.8"/>',
    "s2": '<g data-lib="brain" data-fill="p4" data-face="smug" transform="translate(540 700) scale(1.8)" data-in="pop" data-at="0"/>'
          '<g data-lib="bubble" data-text="SPOILER!" data-w="460" data-h="170" data-tail="down" transform="translate(540 260)" '
          'data-in="pop" data-at="w:spoils"/>',
    "s3": '<g data-lib="robot" data-fill="#cfd8dc" transform="translate(540 800) scale(1.3)" data-in="drop" data-at="0"/>'
          '<g data-lib="heart" data-fill="p1" transform="translate(800 360)" data-in="pop" data-at="w:robot"/>'
          '<text x="540" y="220" font-family="marker" font-size="96" data-in="write" data-at="w:add">+0.2 s</text>'
          '<g data-lib="feather" data-fill="p1" transform="translate(200 860) scale(0.8)" data-in="none"/>'
          '<g data-lib="clock" transform="translate(880 860) scale(0.6)" data-in="none"/>',
}


def run(cmd: list, expect: tuple[str, ...] = ("passed",)) -> dict:
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    out = p.stdout.strip()
    try:
        res = json.loads(out[out.index("{"):]) if "{" in out else {}
    except json.JSONDecodeError:
        res = {}
    status = res.get("status", f"exit {p.returncode}")
    ok = status in expect
    print(f"  {'OK ' if ok else 'FAIL'} {Path(str(cmd[1])).name} {cmd[2] if len(cmd) > 2 and not str(cmd[2]).startswith('-') else ''}"
          f"-> {status} {[c['id'] for c in res.get('failed_checks', [])]}")
    if not ok:
        print(p.stderr[-1500:], file=sys.stderr)
        raise SystemExit(1)
    return res


def build(work: Path) -> None:
    (work / "script").mkdir(parents=True); (work / "audio").mkdir(); (work / "visual" / "svg").mkdir(parents=True)
    sr, t, words, sig = 24000, 0.08, [], []
    rng = np.random.default_rng(1)
    for i, (w, beat) in enumerate(WORDS):
        d = 0.18 + 0.03 * len(w)
        n = int(d * sr)
        f0, tt = 180 + 40 * (i % 3), np.arange(n) / sr
        # harmonic-rich like a voice (energy up to ~3 kHz), so speech-band masking checks see real "speech"
        tone = sum(np.sin(2 * np.pi * h * f0 * tt) / h for h in range(1, 15)) * np.hanning(n) * 0.35
        sig.append(np.zeros(int((t - sum(len(x) for x in sig) / sr) * sr)))
        sig.append(tone + rng.normal(0, 0.01, n))
        words.append({"w": w, "start": round(t, 3), "end": round(t + d, 3), "sentence": int(beat[1]) - 1})
        t += d + (0.25 if w.endswith(".") else 0.08)
    audio = np.concatenate(sig + [np.zeros(int(0.3 * sr))]).astype(np.float32)
    sf.write(work / "audio" / "voice.wav", audio, sr)
    dur = len(audio) / sr
    sents = []
    for k in range(3):
        ws = [w for w in words if w["sentence"] == k]
        sents.append({"i": k, "text": " ".join(w["w"] for w in ws), "beat_id": f"b{k + 1}", "start": ws[0]["start"], "end": ws[-1]["end"]})
    timing = {"video_id": "smoke", "language": "en", "audio_path": str(work / "audio" / "voice.wav"), "duration_s": round(dur, 3),
              "backend": "synthetic", "words": words, "sentences": sents}
    (work / "audio" / "timing.json").write_text(json.dumps(timing), encoding="utf-8")
    beats = [{"id": s["beat_id"], "role": r, "text": s["text"]} for s, r in zip(sents, ("hook", "value", "payoff"))]
    (work / "script" / "script.json").write_text(json.dumps({"video_id": "smoke", "language": "en", "beats": beats,
        "publish": {"title_options": ["smoke"], "description": "", "hashtags": []}}), encoding="utf-8")
    scenes = []
    for i, (sid, body) in enumerate(SCENES.items()):
        (work / "visual" / "svg" / f"{sid}.svg").write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920">'
            f'<path d="M80,1046 C400,1038 700,1052 1000,1043" data-in="none"/>{body}</svg>', encoding="utf-8")
        scenes.append({"id": sid, "beat_ids": [f"b{i + 1}"], "visual": {"kind": "doodle", "svg_path": f"svg/{sid}.svg"},
                       "camera": {"drift": "in", "punch": ["w:brain"] if sid == "s2" else []},
                       **({"transition": {"type": ["whip", "paper"][i - 1]}} if i else {})})
    (work / "visual" / "storyboard.json").write_text(json.dumps({"video_id": "smoke", "style": {
        "palette": ["#ffd23f", "#e8452c", "#3b82c4", "#2f9e44", "#f783ac"]}, "scenes": scenes}), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keep", help="keep artifacts in this folder")
    a = ap.parse_args()
    work = Path(a.keep) if a.keep else Path(tempfile.mkdtemp(prefix="cf_smoke_"))
    if work.exists() and a.keep:
        shutil.rmtree(work)
    build(work)
    sb, vs, sp, qa = (ROOT / "visual-storyboarding/scripts/storyboard_tool.py", ROOT / "video-production/scripts/render_video.py",
                      ROOT / "subtitle-production/scripts/subtitles.py", ROOT / "video-quality-assurance/scripts/qa_video.py")
    print(f"smoke test in {work}")
    r = run([PY, sb, "render", "--storyboard", work / "visual/storyboard.json", "--script", work / "script/script.json",
             "--out-dir", work / "visual", "--result", work / "visual/result.json", "--timing", work / "audio/timing.json"])
    assert r["metrics"]["cue_timing"] == "narration", r["metrics"]
    subprocess.run([PY, sb, "retime", "--storyboard", work / "visual/storyboard.rendered.json", "--timing",
                    work / "audio/timing.json", "--out", work / "video/storyboard.timed.json"], check=True, capture_output=True)
    v = run([PY, vs, "--storyboard", work / "video/storyboard.timed.json", "--voice", work / "audio/voice.wav", "--timing",
             work / "audio/timing.json", "--out-dir", work / "video", "--result", work / "video/result.json"],
            expect=("passed", "passed_with_warnings"))
    assert v["metrics"]["engine"] == "doodle" and v["metrics"]["sfx_events"] > 0, v["metrics"]
    s = run([PY, sp, "run", "--timing", work / "audio/timing.json", "--video", work / "video/video_nosubs.mp4", "--out-dir",
             work / "subtitles", "--result", work / "subtitles/result.json", "--overlays", work / "video/storyboard.timed.json"])
    assert s["metrics"]["style"] == "doodle", s["metrics"]
    run([PY, qa, "check", "--video", work / "subtitles/final.mp4", "--timing", work / "audio/timing.json", "--captions",
         work / "subtitles/captions.ass", "--nosubs", work / "video/video_nosubs.mp4", "--out-dir", work / "qa", "--result",
         work / "qa/result.json", "--min-s", "3", "--max-s", "20", "--ocr", "off"], expect=("pending_review",))
    # negative test: a corrupted final must be rejected, not silently passed
    bad = work / "qa_bad"
    corrupt = work / "subtitles/final_corrupt.mp4"
    shutil.copy(work / "subtitles/final.mp4", corrupt)
    with open(corrupt, "r+b") as f:
        size = corrupt.stat().st_size
        rng = __import__("random").Random(7)   # deterministic damage (unseeded bytes made this check flaky, Phase 4)
        for k in range(2, 8):
            f.seek(size * k // 9); f.write(rng.randbytes(4096))
    run([PY, qa, "check", "--video", corrupt, "--timing", work / "audio/timing.json", "--captions", work / "subtitles/captions.ass",
         "--nosubs", work / "video/video_nosubs.mp4", "--out-dir", bad, "--result", bad / "result.json", "--min-s", "3",
         "--max-s", "20", "--ocr", "off"], expect=("failed",))
    res = json.loads((bad / "result.json").read_text())
    assert any(c["id"] == "QA.DECODE_OK" and not c["passed"] for c in res["gate"]["checks"]), "decode gate missed corruption"
    print("SMOKE TEST PASSED")
    if not a.keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
