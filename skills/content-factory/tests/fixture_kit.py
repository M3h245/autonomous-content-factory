"""Build small test videos through the REAL stage scripts (no TTS, no network) and review them independently.

Used by test_bad_videos.py and smoke tests. A fixture = beats (spoken text) + doodle scene SVG bodies + options.
The synthetic "voice" is tone bursts with exact word timings, so every stage gate, the visual audit, the packet
builder and the reviewer run exactly as in production.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
SB = ROOT / "visual-storyboarding/scripts/storyboard_tool.py"
RV = ROOT / "video-production/scripts/render_video.py"
SP = ROOT / "subtitle-production/scripts/subtitles.py"
QA = ROOT / "video-quality-assurance/scripts/qa_video.py"
PK = ROOT / "video-quality-assurance/scripts/review_packet.py"
RW = ROOT / "video-quality-assurance/scripts/reviewer.py"
PALETTE = ["#ffd23f", "#e8452c", "#3b82c4", "#2f9e44", "#f783ac"]


def run(cmd: list, ok=(0, 2)) -> dict:
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if p.returncode not in ok:
        raise RuntimeError(f"{Path(str(cmd[1])).name} exit {p.returncode}: {(p.stderr or p.stdout)[-800:]}")
    out = p.stdout.strip()
    try:
        return json.loads(out[out.index("{"):]) if "{" in out else {}
    except json.JSONDecodeError:
        return {}


def voice(work: Path, beats: list[tuple[str, str]], lead: float = 0.08, tail: float = 0.3, word_s: float = 0.2) -> None:
    sr = 24000
    t, words, sig, sents = lead, [], [np.zeros(int(lead * sr))], []
    rng = np.random.default_rng(3)
    k = 0
    for bi, (_bid, text) in enumerate(beats):
        for si, sent in enumerate([x.strip() for x in text.replace("? ", "?|").replace(". ", ".|").split("|") if x.strip()]):
            s0 = t
            for w in sent.split():
                d = word_s + 0.025 * len(w)
                n = int(d * sr)
                sig.append(np.sin(2 * np.pi * (170 + 35 * (k % 4)) * np.arange(n) / sr) * np.hanning(n) * 0.5 + rng.normal(0, 0.01, n))
                words.append({"w": w, "start": round(t, 3), "end": round(t + d, 3), "sentence": len(sents)})
                gap = 0.07
                sig.append(np.zeros(int(gap * sr)))
                t += d + gap
                k += 1
            sents.append({"i": len(sents), "text": sent, "beat_id": f"b{bi + 1}", "start": round(s0, 3), "end": round(t - 0.07, 3)})
            sig.append(np.zeros(int(0.18 * sr)))
            t += 0.18
    sig.append(np.zeros(int(tail * sr)))
    audio = np.concatenate(sig).astype(np.float32)
    (work / "audio").mkdir(parents=True, exist_ok=True)
    sf.write(work / "audio" / "voice.wav", audio, sr)
    json.dump({"video_id": "fx", "language": "en", "audio_path": str(work / "audio/voice.wav"), "duration_s": round(len(audio) / sr, 3),
               "backend": "synthetic", "words": words, "sentences": sents}, open(work / "audio" / "timing.json", "w", encoding="utf-8"))


def build(work: Path, beats, scenes: dict, cameras: dict | None = None, title: str = "Why fingers wrinkle in water",
          lead=0.08, tail=0.3, music_gain_db=-19.0, font_scale=1.0, min_s=3, max_s=60, roles=None, cta=None) -> dict:
    """Render a fixture through VISUAL_PLAN → VIDEO → SUBTITLES → QA check, then packet + independent review."""
    work.mkdir(parents=True, exist_ok=True)
    voice(work, beats, lead, tail)
    (work / "script").mkdir(exist_ok=True)
    json.dump({"video_id": "fx", "language": "en", "beats": [{"id": b, "role": r, "text": t} for (b, t), r in
                                                             zip(beats, roles or ["hook", "value", "payoff", "loop", "value", "value"])],
               "publish": {"title_options": [title], "description": "test fixture", "hashtags": ["#test"]},
               **({"cta": cta} if cta else {})}, open(work / "script/script.json", "w", encoding="utf-8"))
    (work / "visual/svg").mkdir(parents=True, exist_ok=True)
    sc = []
    for i, (sid, body) in enumerate(scenes.items()):
        (work / f"visual/svg/{sid}.svg").write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920">{body}</svg>', encoding="utf-8")
        sc.append({"id": sid, "beat_ids": [beats[i][0]], "visual": {"kind": "doodle", "svg_path": f"svg/{sid}.svg"},
                   "camera": (cameras or {}).get(sid, {"drift": "none"}), "transition": {"type": "cut"}})
    json.dump({"video_id": "fx", "style": {"palette": PALETTE}, "scenes": sc}, open(work / "visual/storyboard.json", "w", encoding="utf-8"))
    r = {}
    r["visual_plan"] = run([PY, SB, "render", "--storyboard", work / "visual/storyboard.json", "--script", work / "script/script.json",
                            "--out-dir", work / "visual", "--result", work / "visual/result.json", "--timing", work / "audio/timing.json"])
    run([PY, SB, "retime", "--storyboard", work / "visual/storyboard.rendered.json", "--timing", work / "audio/timing.json",
         "--out", work / "video/storyboard.timed.json"], ok=(0,))
    r["video"] = run([PY, RV, "--storyboard", work / "video/storyboard.timed.json", "--voice", work / "audio/voice.wav",
                      *(["--script", work / "script/script.json"] if cta else []), "--timing",
                      work / "audio/timing.json", "--out-dir", work / "video", "--result", work / "video/result.json",
                      "--music-gain-db", music_gain_db,
                      *(["--fixed-music-gain", "--music-carve-db", "0"] if music_gain_db != -19.0 else [])])   # a deliberately bad, uncorrected mix
    r["subtitles"] = run([PY, SP, "run", "--timing", work / "audio/timing.json", "--video", work / "video/video_nosubs.mp4",
                          "--out-dir", work / "subtitles", "--result", work / "subtitles/result.json", "--overlays",
                          work / "video/storyboard.timed.json", "--font-scale", font_scale])
    r["qa"] = run([PY, QA, "check", "--video", work / "subtitles/final.mp4", "--timing", work / "audio/timing.json", "--captions",
                   work / "subtitles/captions.ass", "--nosubs", work / "video/video_nosubs.mp4", "--out-dir", work / "qa", "--result",
                   work / "qa/result.json", "--min-s", min_s, "--max-s", max_s], ok=(0, 2, 3))
    run([PY, PK, "build", "--final", work / "subtitles/final.mp4", "--timing", work / "audio/timing.json", "--captions",
         work / "subtitles/captions.ass", "--publish", work / "script/script.json", "--out", work / "packet", "--min-s", min_s, "--max-s", max_s,
         "--measure", f"qa_report={work / 'qa/qa_report.json'}", "--measure", f"visual_audit={work / 'video/work/visual_audit.json'}",
         "--measure", f"mix_report={work / 'video/work/mix_report.json'}", "--measure", f"subtitles_result={work / 'subtitles/result.json'}",
         *(["--measure", f"cta_report={work / 'video/work/cta_report.json'}"] if (work / "video/work/cta_report.json").exists() else [])],
        ok=(0,))
    run([PY, RW, "review", "--packet", work / "packet", "--out", work / "review", "--backend", "heuristic"])
    r["review"] = json.load(open(work / "review/review_report.json"))
    return r


# ----------------------------------------------------------------------------- the three bad fixtures
FINGER = ('<path d="M330,1040 L330,460 C330,310 650,310 650,460 L650,1040 Z" fill="#f6c9a8"/>')


def fixture_A_crop(work: Path) -> dict:
    """Real Phase 0 failure types: a punch-in crops 'NOT' (meaning flips), a label hangs off the right edge,
    wrinkle lines run past the finger outline."""
    beats = [("b1", "Pruney fingers are not water. It is your nerves."), ("b2", "Your nerves squeeze tiny blood vessels."),
             ("b3", "So pruney fingers mean your nerves work.")]
    wr = "".join(f'<path d="M350,{420 + k * 44} q27,-14 53,0 t53,0 t53,0 t53,0 t53,0 t53,0 t53,0" fill="none" stroke="#b97a5a" stroke-width="6"/>'
                 for k in range(4))
    scenes = {
        "s1": f'<g id="finger" data-in="none">{FINGER}</g><g data-in="draw" data-at="w:pruney">{wr}</g>'
              '<text x="250" y="230" font-family="marker" font-size="100" data-in="pop" data-at="w:not">NOT WATER</text>'
              '<g id="brain" transform="translate(880 520)" data-in="pop" data-at="w:nerves"><g data-lib="brain" data-fill="p4"/></g>',
        "s2": f'<g data-in="none">{FINGER}</g><text x="1010" y="300" font-size="70" data-in="write" data-at="w:squeeze">nerves</text>'
              '<g data-lib="arrow" data-from="200,800" data-to="320,700" data-in="draw" data-at="w:vessels"/>',
        "s3": f'<g data-in="none">{FINGER}</g><g data-lib="check" transform="translate(820 400)" data-in="draw" data-at="w:work"/>'
              '<text x="540" y="200" font-size="64" data-in="write" data-at="w:mean">nerves work</text>',
    }
    cams = {"s1": {"drift": "none", "punch": [{"at": "w:nerves", "focus": [930, 520], "zoom": 1.25, "hold": 1.0}]}}
    return build(work, beats, scenes, cams)


def fixture_B_hook(work: Path) -> dict:
    """Weak/confusing hook: late speech, a long throat-clearing first line, blank first frame, nothing happens early."""
    beats = [("b1", "In this video we are going to talk a little bit about something that happens in the bath sometimes."),
             ("b2", "Fingers can get wrinkly after a long time in warm water."), ("b3", "Nerves play a role in that process.")]
    scenes = {
        "s1": f'<g data-in="pop" data-at="w:bath">{FINGER}</g>',
        "s2": f'<g data-in="none">{FINGER}</g><g data-lib="sweat" transform="translate(800 500)" data-in="pop" data-at="w:water"/>'
              '<text x="540" y="220" font-size="64" data-in="write" data-at="w:wrinkly">wrinkly</text>',
        "s3": '<g data-lib="brain" data-fill="p4" transform="translate(540 600) scale(1.5)" data-in="pop" data-at="w:nerves"/>'
              '<text x="540" y="230" font-size="64" data-in="write" data-at="w:role">nerves</text>'
              '<g data-lib="arrow" data-from="300,900" data-to="420,760" data-in="draw" data-at="w:process"/>',
    }
    return build(work, beats, scenes, lead=1.1, title="Fingers")


def fixture_C_pacing(work: Path) -> dict:
    """Poor pacing/audio/subtitles/ending: one static picture for most of the video, music fighting the voice,
    tiny captions, a long dead tail and no callback at the end."""
    beats = [("b1", "Why do fingers wrinkle in warm water?"),
             ("b2", "Warm water enters the skin through sweat ducts and the body responds with signals that travel along "
                    "nerves to tiny vessels which then narrow over several minutes while you sit in the bath."),
             ("b3", "Anyway that is about it for today.")]
    scenes = {
        "s1": f'<g data-in="none">{FINGER}</g><text x="540" y="220" font-size="64" data-in="write" data-at="w:wrinkle">why?</text>'
              '<g data-lib="question" transform="translate(860 420)" data-in="pop" data-at="w:warm"/>',
        "s2": f'<g data-in="none">{FINGER}</g><g data-lib="sweat" transform="translate(820 500)" data-in="none"/>'
              '<g data-lib="arrow" data-from="200,700" data-to="320,640" data-in="none"/>',
        "s3": f'<g data-in="none">{FINGER}</g><g data-lib="sweat" transform="translate(820 500)" data-in="none"/>'
              '<g data-lib="arrow" data-from="200,700" data-to="320,640" data-in="none"/>',
    }
    return build(work, beats, scenes, tail=3.2, music_gain_db=4.0, font_scale=0.5)


def fixture_D_bad_cta(work: Path) -> dict:
    """Bad CTA on a decent short: a generic 'like and subscribe' bolted on after the loop line (breaks the loop,
    unrelated to the content) — the CTA gates and the reviewer must reject it for those reasons."""
    beats = [("b1", "Pruney fingers are not water. They are nerves."), ("b2", "Your nerves squeeze tiny blood vessels."),
             ("b3", "So the skin folds into wrinkles."), ("b4", "Not water. Nerves."), ("b5", "Like and subscribe for more videos!")]
    scenes = {
        "s1": f'<g id="finger" data-in="none">{FINGER}</g><text x="540" y="230" font-family="marker" font-size="100" data-in="none">NOT WATER</text>'
              '<g data-lib="sparkle" transform="translate(860 520)" data-in="pop" data-at="0.2"/><g data-lib="brain" data-fill="p4" transform="translate(860 820)" data-in="pop" data-at="0.9"/>',
        "s2": '<rect x="120" y="560" width="840" height="400" fill="#f6c9a8" data-in="none"/>'
              + "".join(f'<ellipse cx="{x}" cy="760" rx="90" ry="30" fill="p1" data-in="pop" data-at="w:squeeze"/>' for x in (260, 540, 820))
              + '<text x="540" y="300" font-size="64" data-in="write" data-at="w:nerves">blood vessels</text>',
        "s3": f'<g data-in="none">{FINGER}</g><text x="540" y="230" font-family="marker" font-size="100" data-in="write" data-at="w:folds">FOLDS</text>'
              '<g data-lib="check" transform="translate(830 500)" data-in="draw" data-at="w:wrinkles"/>',
        "s4": f'<g data-in="none">{FINGER}</g><text x="540" y="230" font-family="marker" font-size="100" data-in="none">NOT WATER</text>'
              '<g data-lib="heart" data-fill="p1" transform="translate(830 600) scale(0.6)" data-in="pop" data-at="w:nerves"/>',
        "s5": '<g data-lib="dude" data-pose="arms-up" data-face="happy" transform="translate(540 1040) scale(1.6)" data-in="none"/>'
              '<text x="540" y="230" font-family="marker" font-size="96" data-in="write" data-at="w:like">SUBSCRIBE</text>',
    }
    cta = {"needed": True, "decision_reason": "fixture", "type": "subscribe", "placement": "after_payoff", "modality": "spoken",
           "beat_id": "b5", "spoken": "Like and subscribe for more videos!"}
    return build(work, beats, scenes, roles=["hook", "value", "payoff", "loop", "cta"], cta=cta)
