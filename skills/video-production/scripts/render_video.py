#!/usr/bin/env python3
"""video-production — assemble the VIDEO stage: shots → motion → transitions → audio mix → video_nosubs.mp4.

  render_video.py --storyboard sb_timed.json --voice voice.wav --out-dir DIR --result DIR/result.json
                  [--timing timing.json] [--engine auto|doodle|kenburns] [--music procedural|pad|none|PATH]
                  [--music-license "..."] [--sfx auto|none] [--lufs -14] [--fps 30]

Engines
  doodle    (v2, default whenever a scene is `kind: doodle`): hand-drawn scenes animated element by element on
            narration words, boiling marker lines, camera punch-ins, page transitions, synced SFX — doodle_engine.py
  kenburns  (v1): zoompan over rendered stills/footage with xfade transitions.
Audio: voice + self-generated music bed (`procedural` = seeded playful marimba/pizz/shaker bed; `pad` = v1 drone)
ducked under speech + procedural SFX on animation events (doodle engine) → two-pass loudnorm.

Input storyboard must be retimed (`storyboard_tool.py retime`): each entry in `shots` has start/end seconds,
visual (doodle svg or a 2160x3840 PNG / video file), motion and transition.
Captions are NOT burned here — subtitle-production does that on top of this master.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import (FORMATS, X264_THREADS, StageResult, decode_errors, emit, exit_for, ffmpeg_bin, ffprobe, fix,  # noqa: E402
                       media_duration, read_json, run, stage_main, write_json)

W, H = 1080, 1920
XFADE = {"fade", "slideleft", "slideup", "wipeleft", "circleopen", "dissolve"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv"}


def set_size(w: int, h: int) -> None:
    """v3.3: switch the output size to the brief's aspect (16:9 long-form = 1920x1080)."""
    global W, H, LONG
    W, H = int(w), int(h)
    LONG = h < w   # 16:9 marks the run long: pacing and ending rules follow the format (see below)


LONG = False
# v3.3 format-scaling of the gate thresholds. Shorts cadence (a visual event every ≤3 s, median ≤1.8 s, shots ≤5 s)
# is a retention device for the 3-second swipe decision — it does NOT apply to long-form, where YouTube's own guidance
# is about structure, not shot length. Long-form keeps the anti-dead-air rule (MOTION_GAP) but relaxes cadence.
PACING = {"short": (3.0, 1.8), "long": (6.0, 3.5)}       # (max gap between events, median gap)
SHOT_MAX_S = {"short": 5.0, "long": 12.0}
END_SCREEN_TAIL_S = 5.0   # D2: the last 5 s must be visually calm and free for a Subscribe end screen (16:9 only)
# (support.google.com/youtube/answer/6388789: end screens occupy the last 5-20 s of a video ≥25 s)


def motion_expr(kind: str, strength: float, n: int) -> tuple[str, str, str]:
    p = f"(on/{max(n - 1, 1)})"
    e = f"({p}*{p}*(3-2*{p}))"  # smoothstep easing
    s = max(0.02, strength)
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    return {
        "zoom_in": (f"1+{s}*{e}", cx, cy),
        "zoom_out": (f"1+{s}*(1-{e})", cx, cy),
        "pan_left": (f"{1 + s}", f"(iw-iw/zoom)*(1-{e})", cy),
        "pan_right": (f"{1 + s}", f"(iw-iw/zoom)*{e}", cy),
        "pan_up": (f"{1 + s}", cx, f"(ih-ih/zoom)*(1-{e})"),
        "pan_down": (f"{1 + s}", cx, f"(ih-ih/zoom)*{e}"),
        "static": (f"1+0.02*{e}", cx, cy),
    }.get(kind, (f"1+{s}*{e}", cx, cy))


def render_shot(src: str, frames: int, motion: dict, fps: int, out: Path) -> None:
    if Path(src).suffix.lower() in VIDEO_EXT:  # footage: cover-crop to the output aspect, loop if short
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps},setsar=1,format=yuv420p"
        cmd = [ffmpeg_bin(), "-y", "-v", "error", "-stream_loop", "-1", "-i", src, "-an", "-vf", vf, "-frames:v", frames]
    else:
        z, x, y = motion_expr(motion.get("type", "zoom_in"), float(motion.get("strength", 0.12)), frames)
        sw, sh = W * 2, H * 2   # 2x headroom for pan/zoom; follows the output aspect (2160x3840 portrait, 3840x2160 wide)
        vf = (f"scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={sw}:{sh},"
              f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={fps},setsar=1,format=yuv420p")
        cmd = [ffmpeg_bin(), "-y", "-v", "error", "-i", src, "-vf", vf, "-frames:v", frames]
    run(cmd + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-threads", X264_THREADS, "-r", fps, str(out)])


def procedural_bed(duration: float, path: Path, seed: int = 7, sr: int = 48000) -> None:
    """Soft pad (i–VI–III–VII in A minor), slow attacks, gentle stereo detune. Self-generated, royalty-free."""
    rng = np.random.default_rng(seed)
    chords = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]
    beat = 4.0
    t = np.arange(int(duration * sr)) / sr
    out = np.zeros((t.size, 2))
    for k in range(int(np.ceil(duration / beat)) + 1):
        a, b = int(k * beat * sr), int(min((k + 1) * beat + 1.0, duration) * sr)
        if a >= t.size:
            break
        tt = t[a:b] - k * beat
        env = np.minimum(1, tt / 1.2) * np.minimum(1, np.maximum(0, (beat + 1.0 - tt)) / 1.0)
        for note in chords[k % 4]:
            f = 440 * 2 ** ((note - 69) / 12)
            for ch, det in enumerate((-0.6, 0.6)):
                ph = rng.uniform(0, 2 * np.pi)
                out[a:b, ch] += env * (np.sin(2 * np.pi * (f + det) * tt + ph) + 0.3 * np.sin(2 * np.pi * 2 * (f + det) * tt))
    kernel = np.ones(64) / 64  # mellow the top end
    for ch in range(2):
        out[:, ch] = np.convolve(out[:, ch], kernel, mode="same")
    out *= 0.25 / (np.max(np.abs(out)) or 1)
    fade = int(sr * 1.5)
    out[:fade] *= np.linspace(0, 1, fade)[:, None]
    out[-fade:] *= np.linspace(1, 0, fade)[:, None]
    sf.write(path, out.astype(np.float32), sr, subtype="PCM_16")


def loudnorm(inp: Path, out: Path, lufs: float, tp: float = -1.5) -> dict:
    p = run([ffmpeg_bin(), "-hide_banner", "-i", inp, "-af", f"loudnorm=I={lufs}:TP={tp}:LRA=11:print_format=json",
             "-f", "null", "-"], check=True)
    m = json.loads(re.findall(r"\{[^{}]*\}", p.stderr, re.S)[-1])
    af = (f"loudnorm=I={lufs}:TP={tp}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,"
          f"aresample=48000")
    run([ffmpeg_bin(), "-y", "-v", "error", "-i", inp, "-af", af, "-ac", "2", "-c:a", "pcm_s16le", out])
    return m


def measure_loudness(path: Path) -> tuple[float, float]:
    p = run([ffmpeg_bin(), "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"])
    i = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", p.stderr)[-1])
    peak = float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", p.stderr)[-1])
    return i, peak


def first_frame_ink(video: Path) -> float:
    """Share of clearly dark (ink) pixels in frame 0 — a blank first frame kills the hook."""
    import subprocess
    raw = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(video), "-frames:v", "1", "-vf",
                          "scale=270:480,format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    arr = np.frombuffer(raw, dtype=np.uint8)
    return float((arr < 110).mean()) if arr.size else 0.0


def empty_runs(video: Path, fps: float = 4.0, ink_min: float = 0.003) -> tuple[float, float]:
    """Longest stretch (s) where the picture is essentially blank paper, and when it starts."""
    import subprocess
    w, h = 135, 240
    raw = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(video), "-vf", f"fps={fps},scale={w}:{h},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, h, w)
    empty = (frames < 110).mean(axis=(1, 2)) < ink_min
    best, start, run_len, run_start = 0, 0.0, 0, 0
    for i, e in enumerate(empty):
        run_len, run_start = (run_len + 1, run_start if run_len else i) if e else (0, i)
        if run_len > best:
            best, start = run_len, run_start / fps
    return best / fps, start


MIX_POLICY_DB = (16.0, 18.0)   # Phase 3: music under voice during speech — owner chose mix A (17 dB + 12 dB carve) by ear, 2026-10-07


def frame_similarity(video: Path, t0: float, t1: float) -> float:
    """1 − mean |Δ| of two downscaled grayscale frames (loop check: does the ending return to the opening?)."""
    import subprocess

    def grab(t):
        raw = subprocess.run([ffmpeg_bin(), "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(video), "-frames:v", "1", "-vf",
                              "scale=54:96,format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
        return np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
    a_, b_ = grab(t0), grab(t1)
    n = min(a_.size, b_.size)
    return float(1 - np.abs(a_[:n] - b_[:n]).mean() / 255) if n else 0.0


def load_voice_48k(voice: Path, work: Path) -> np.ndarray:
    tmp = work / "voice_48k.wav"
    run([ffmpeg_bin(), "-y", "-v", "error", "-i", voice, "-ar", "48000", "-ac", "1", "-c:a", "pcm_f32le", tmp])
    data, _ = sf.read(tmp, dtype="float32")
    return data if data.ndim == 1 else data.mean(axis=1)


def is_doodle(shots: list[dict]) -> bool:
    return any(s.get("visual", {}).get("kind") == "doodle" or s.get("visual", {}).get("used_kind") == "doodle" for s in shots)


def render_doodle(sb: dict, timing: dict, base: Path, video_only: Path, fps: int) -> tuple[object, int]:
    import doodle_engine as de  # local import: only the doodle path needs skia
    de.set_canvas(W, H)   # v3.3: keep the engine canvas in step with this stage's output size
    tl = de.build_timeline(sb, timing, base)
    n = de.render_video(tl, video_only, fps=fps, ffmpeg=ffmpeg_bin())
    return tl, n


@stage_main("VIDEO", "video-production")
def main_cmd(a) -> int:
    sb = read_json(a.storyboard)
    out = Path(a.out_dir).resolve()
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)
    # v3.3: the brief's aspect decides the output size. 16:9 long-form = 1920x1080; shorts stay 1080x1920. The
    # storyboard carries the canvas it was authored for; --aspect overrides for legacy storyboards.
    sc0 = (sb.get("style", {}) or {}).get("canvas") or sb.get("canvas")
    if sc0:
        set_size(int(sc0[0]), int(sc0[1]))
    elif a.aspect:
        set_size(*(formats[a.aspect]))
    sr = StageResult("VIDEO", "video-production", sb.get("video_id"), attempt=a.attempt)
    sr.input(a.storyboard, "storyboard_timed"); sr.input(a.voice, "voice_audio")
    shots = sb.get("shots")
    if not shots:
        sr.fail("VID.NOT_RETIMED", "storyboard has no `shots`; run storyboard_tool.py retime first",
                fix=fix("VIDEO", "retime"), retryable=True)
        return exit_for(sr.finalize(a.result))
    base = Path(a.storyboard).resolve().parent
    for shot in shots:  # relative visual paths are relative to the storyboard file
        for key in ("path", "svg_path"):
            if shot["visual"].get(key) and not Path(shot["visual"][key]).is_absolute():
                shot["visual"][key] = str(base / shot["visual"][key])
    fps = a.fps
    voice_dur = media_duration(a.voice)
    engine = a.engine if a.engine != "auto" else ("doodle" if is_doodle(shots) else "kenburns")
    seed = int.from_bytes(str(sb.get("video_id", "v")).encode()[:4].ljust(4, b"0"), "little") % 100000
    video_only = work / "video_only.mp4"
    tl, trans = None, []
    if engine == "doodle":
        timing_path = Path(a.timing) if a.timing else Path(a.voice).with_name("timing.json")
        if not timing_path.exists():
            sr.fail("VID.NO_TIMING", f"doodle engine needs word timings ({timing_path})", fix=fix("AUDIO", "resynthesize"),
                    retryable=True)
            return exit_for(sr.finalize(a.result))
        sr.input(timing_path, "voice_timing")
        timing = read_json(timing_path)
        timing["duration_s"] = voice_dur
        tl, _ = render_doodle(sb, timing, base, video_only, fps)
    else:
        total = round(voice_dur * fps)
        starts = [round(s["start"] * fps) for s in shots] + [total]
        use_xfade = any(s.get("transition", {}).get("type", "cut") in XFADE for s in shots[1:])
        trans = [0]  # frames of overlap per boundary; a cut inside an xfade chain is a 1-frame fade
        for s in shots[1:]:
            t = s.get("transition", {})
            if not use_xfade:
                trans.append(0)
            elif t.get("type", "cut") in XFADE:
                trans.append(max(2, round(float(t.get("duration") or 0.25) * fps)))
            else:
                trans.append(1)
        left = [t // 2 for t in trans]
        right = [t - l for t, l in zip(trans, left)] + [0]
        segs = []
        for i, shot in enumerate(shots):
            f0, f1 = starts[i] - left[i], starts[i + 1] + right[i + 1]
            seg = work / f"shot_{i:02d}.mp4"
            render_shot(shot["visual"]["path"], f1 - f0, shot.get("motion", {}), fps, seg)
            segs.append((seg, f0, f1))
        if not use_xfade:
            lst = work / "concat.txt"
            lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p, _, _ in segs), encoding="utf-8")
            run([ffmpeg_bin(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", video_only])
        else:
            inputs, chain, label = [], [], "[0:v]"
            for p, _, _ in segs:
                inputs += ["-i", p]
            for i in range(1, len(segs)):
                kind = shots[i].get("transition", {}).get("type", "cut")
                kind = kind if kind in XFADE else "fade"
                dur, off = trans[i] / fps, (starts[i] - left[i]) / fps
                nxt = f"[x{i}]"
                chain.append(f"{label}[{i}:v]xfade=transition={kind}:duration={dur:.4f}:offset={off:.4f}{nxt}")
                label = nxt
            run([ffmpeg_bin(), "-y", "-v", "error", *inputs, "-filter_complex", ";".join(chain), "-map", label,
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-threads", X264_THREADS, "-pix_fmt", "yuv420p", "-r", fps, video_only])

    # ---------------- audio: voice + music bed (ducked) + SFX → loudness normalized
    import audio_design as ad
    voice = load_voice_48k(Path(a.voice), work)
    music, music_meta = None, None
    if a.music in ("procedural", "playful"):
        music, music_meta = ad.playful_bed(voice.size / ad.SR, seed=seed)
        sr.provenance({"role": "music", "path": str(work / "music_bed.wav"), "source": "generated", "license": "self-generated",
                       "generator": {"tool": "audio_design.playful_bed (numpy synthesis)", **music_meta},
                       "realistic": False, "ai_generated_music": False})
    elif a.music == "pad":
        procedural_bed(voice.size / ad.SR, work / "music_bed.wav")
        music, _ = sf.read(work / "music_bed.wav", dtype="float32")
        sr.provenance({"role": "music", "path": str(work / "music_bed.wav"), "source": "generated", "license": "self-generated",
                       "generator": {"tool": "procedural pad (numpy)", "seed": 7}, "realistic": False, "ai_generated_music": False})
    elif a.music not in (None, "none"):
        tmp = work / "music_48k.wav"
        run([ffmpeg_bin(), "-y", "-v", "error", "-stream_loop", "-1", "-i", a.music, "-t", f"{voice_dur:.3f}", "-ar", "48000",
             "-ac", "2", "-c:a", "pcm_f32le", tmp])
        music, _ = sf.read(tmp, dtype="float32")
        music = ad._norm(music, 0.9)
        sr.provenance({"role": "music", "path": str(a.music), "source": "user-provided",
                       "license": a.music_license or "unknown", "realistic": False})
    if music is not None:
        sf.write(work / "music_bed.wav", music.astype(np.float32), ad.SR)
    sfx, used = None, []
    if tl is not None and a.sfx != "none":
        capped, cap_info = ad.cap_events(tl.events(), voice.size / ad.SR, max_rate=a.sfx_max_rate)
        sfx, used = ad.schedule_sfx(capped, voice.size / ad.SR, seed=seed, density=a.sfx_density)
        sfx, protect_info = ad.protect_speech(voice, sfx)   # refined below once the music level is known
        sf.write(work / "sfx.wav", sfx.astype(np.float32), ad.SR)
        sr.provenance({"role": "sfx", "path": str(work / "sfx.wav"), "source": "generated", "license": "self-generated",
                       "generator": {"tool": "audio_design SFX synthesis (numpy)", "events": len(used)}, "realistic": False,
                       "ai_generated_music": False})
    music_db = a.music_gain_db
    if music is not None and a.music_under_voice_db is not None and not a.fixed_music_gain:   # closed loop on the measured ratio
        mu0 = ad.mix_report(voice, music, sfx, music_db=music_db, used=used, carve_db=a.music_carve_db).get("music_under_voice_db")
        if mu0 is not None:
            music_db = round(music_db + (mu0 - a.music_under_voice_db), 2)
    if sfx is not None and music is not None:      # combined check: SFX may only use the room the music leaves
        env_m = ad.speech_envelope(ad._norm(voice, 0.7))
        sfx, protect_info = ad.protect_speech(voice, sfx, music_bed=ad.music_component(music, voice.size, env_m, music_db,
                                                                                       carve_db=a.music_carve_db))
    mixed = ad.mix(voice, music, sfx, music_db=music_db, carve_db=a.music_carve_db)
    mix_report = ad.mix_report(voice, music, sfx, music_db=music_db, used=used, carve_db=a.music_carve_db)
    mix_report.update(music_gain_db_used=music_db, music_target_db=a.music_under_voice_db, music_carve_db=a.music_carve_db,
                      sfx_cap=cap_info if tl is not None else None, speech_protection=protect_info if tl is not None else None,
                      masking=ad.speech_masking(voice, mixed))
    mix_path = work / "mix.wav"
    sf.write(mix_path, mixed.astype(np.float32), ad.SR, subtype="FLOAT")
    norm = work / "mix_norm.wav"
    loudnorm(mix_path, norm, a.lufs)
    norm_audio, _ = sf.read(norm, dtype="float32")
    mix_report["ending"] = ad.ending_report(norm_audio if norm_audio.ndim == 2 else norm_audio[:, None], music)
    write_json(work / "mix_report.json", mix_report)
    final = out / "video_nosubs.mp4"
    run([ffmpeg_bin(), "-y", "-v", "error", "-i", video_only, "-i", norm, "-map", "0:v", "-map", "1:a",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-flags:a", "+bitexact", "-fflags", "+bitexact",
         "-shortest", "-movflags", "+faststart", final])
    audit = None
    if tl is not None:
        write_json(work / "sound_design.json", {"music": music_meta, "sfx": used, "events": tl.events()})
        audit = tl.audit()
        write_json(work / "visual_audit.json", audit)

    # ---------------- gate
    info = ffprobe(final)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    au = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"]["duration"])
    i_lufs, peak = measure_loudness(final)
    bad = decode_errors(final)
    sr.check("VID.DECODE_OK", not bad, "blocking", "; ".join(bad) or "every packet decodes", len(bad), 0,
             fix("VIDEO", "rerender"))
    sr.check("VID.SPEC", (v["width"], v["height"], v["pix_fmt"], v["codec_name"]) == (W, H, "yuv420p", "h264")
             and au is not None and int(au["sample_rate"]) == 48000, "blocking",
             f"{v['width']}x{v['height']} {v['pix_fmt']} {v['codec_name']}", fix=fix("VIDEO", "rerender"))
    sr.check("VID.DURATION_MATCH", abs(dur - voice_dur) <= 0.12, "blocking", f"video {dur:.2f}s vs voice {voice_dur:.2f}s",
             round(dur, 3), round(voice_dur, 3), fix("VIDEO", "rerender"))
    sr.check("VID.LOUDNESS", a.lufs - 1.5 <= i_lufs <= a.lufs + 1.5, "major", f"integrated {i_lufs} LUFS",
             i_lufs, [a.lufs - 1.5, a.lufs + 1.5], fix("VIDEO", "remix", lufs=a.lufs))
    sr.check("VID.PEAK", peak <= -0.5, "major", f"sample peak {peak} dBFS", peak, -0.5, fix("VIDEO", "remix", lufs=a.lufs - 1))
    if tl is not None:
        ev = [t for t in tl.visual_events() if 0 <= t < voice_dur] + [voice_dur]
        gaps = [(round(b - a_, 2), round(a_, 2)) for a_, b in zip([0.0] + ev[:-1], ev)]
        worst = max(gaps)
        sr.check("VID.MOTION_GAP", worst[0] <= a.max_motion_gap, "major",
                 f"longest stretch without a new visual event {worst[0]}s (starting {worst[1]}s)",
                 worst[0], a.max_motion_gap, fix("VISUAL_PLAN", "add_entrances", at_s=worst[1], max_gap=a.max_motion_gap))
        ink = first_frame_ink(video_only)
        sr.check("VID.FIRST_FRAME", ink >= 0.004, "major", f"ink coverage of frame 0 = {ink:.2%} (hook needs a drawing at t=0)",
                 round(ink, 4), 0.004, fix("VISUAL_PLAN", "redesign_scene", scene="first", hint="data-in=none at 0 for the hook subject"))
        blank_s, blank_at = empty_runs(video_only)
        sr.check("VID.EMPTY_FRAMES", blank_s <= 0.5, "major",
                 f"longest blank-paper stretch {blank_s:.2f}s (starting {blank_at:.2f}s)", round(blank_s, 2), 0.5,
                 fix("VISUAL_PLAN", "add_entrances", at_s=round(blank_at, 2), hint="put something on the page at t=0"))
        warns = [f"{sc.__class__.__name__}[{i}]: {w}" for i, sc in enumerate(tl.scenes) for w in getattr(sc, "warnings", [])]
        sr.check("VID.SCENE_LINT", not warns, "minor", "; ".join(warns[:8]) or "scenes parsed cleanly", len(warns), 0,
                 fix("VISUAL_PLAN", "repair_scene"))
        def ev(kinds):
            return [{"scene": i["scene"], "actor": i["actor"], "at_s": i.get("first_s"), **{k: v for k, v in i["detail"].items()
                     if k in ("text", "on_screen", "lost_words", "over_px", "side", "over", "container", "min_size_px")}}
                    for i in audit["issues"] if i["kind"] in kinds]
        mc, tc, oc, oh, ct, sm = (ev({"meaning_cropped"}), ev({"text_cropped", "text_offscreen"}), ev({"off_canvas"}),
                                  ev({"overhang"}), ev({"containment"}), ev({"text_small"}))
        sr.check("VID.MEANING_CROPPED", not mc, "blocking", f"on-screen text loses a negation (meaning flips): {mc[:3]}",
                 len(mc), 0, fix("VISUAL_PLAN", "repair_scene", issues=mc[:5], hint="keep every word of a label in frame "
                                 "through camera moves (centre the punch or move the label inward)"))
        sr.check("VID.TEXT_CROPPED", not tc, "major", f"labels partly/fully outside the frame: {tc[:3]}", len(tc), 0,
                 fix("VISUAL_PLAN", "repair_scene", issues=tc[:5]))
        sr.check("VID.CONTAINMENT", not ct, "blocking", f"elements escape their data-inside container: {ct[:3]}", len(ct), 0,
                 fix("VISUAL_PLAN", "repair_scene", issues=ct[:5]))
        sr.check("VID.OFF_CANVAS", not oc, "major", f"settled elements outside the frame (not during a punch-in): {oc[:3]}",
                 len(oc), 0, fix("VISUAL_PLAN", "repair_scene", issues=oc[:5]))
        sr.check("VID.OVERHANG", not oh, "major", f"lines run past the edge of the shape they sit on: {oh[:3]}", len(oh), 0,
                 fix("VISUAL_PLAN", "repair_scene", issues=oh[:5]))
        sr.check("VID.TEXT_SMALL", not sm, "minor", f"labels smaller than 34 px on screen: {sm[:3]}", len(sm), 0,
                 fix("VISUAL_PLAN", "repair_scene", issues=sm[:5]))
        hk0 = audit["hook"].get("visual_events_first_1_5s", 0)
        sr.check("VID.OPENING_DENSITY", hk0 >= 2, "major", f"{hk0} visual event(s) in the first 1.5 s", hk0, 2,
                 fix("VISUAL_PLAN", "add_entrances", scene="first", window_s=1.5))
        evs = sorted(set([0.0] + [t for t in tl.visual_events() if 0 <= t < voice_dur] + [voice_dur]))
        gaps_ = [b - c for c, b in zip(evs, evs[1:])] or [voice_dur]
        cad_max, cad_med = PACING["long" if LONG else "short"]
        sr.check("VID.PACING_CADENCE", max(gaps_) <= cad_max and float(np.median(gaps_)) <= cad_med, "major",
                 f"longest gap {max(gaps_):.2f}s (≤{cad_max}), median {float(np.median(gaps_)):.2f}s (≤{cad_med})",
                 round(max(gaps_), 2), cad_max,
                 fix("VISUAL_PLAN", "add_entrances", at_s=round(evs[gaps_.index(max(gaps_))], 2)))
        if LONG and voice_dur >= 25:
            # D2 (v3.3): end screens occupy the last 5-20 s of a >=25 s video and must be readable, so the tail is
            # deliberately calm — almost no new visual events and no camera punch-in over the end-screen zone.
            # punch `at` values are scene-local, so the shot start is added to compare against global time.
            tail = [t for t in tl.visual_events() if t >= voice_dur - END_SCREEN_TAIL_S]
            punches = [sh["start"] + p["at"] for sh, sc in zip(tl.shots, tl.scenes)
                       for p in (sc.camera or {}).get("punch", []) if sh["start"] + p["at"] >= voice_dur - END_SCREEN_TAIL_S]
            sr.check("VID.END_SCREEN_TAIL", len(tail) <= 2 and not punches, "major",
                     f"{len(tail)} visual event(s) and {len(punches)} punch-in(s) in the last {END_SCREEN_TAIL_S:g}s "
                     f"(end-screen zone must stay calm)", len(tail), 2,
                     fix("VISUAL_PLAN", "add_entrances", hint="quiet the last 5 s: no new entrances or punch-ins for the end screen"))
        if a.script and Path(a.script).exists():
            beats_ = read_json(a.script)["beats"]
            if beats_ and beats_[-1].get("role") == "loop":
                comp = audit.get("composition", [])
                same = len(comp) >= 2 and comp[-1].get("main_signature") and comp[-1]["main_signature"] == comp[0]["main_signature"]
                sim = frame_similarity(video_only, 0.0, voice_dur - 0.05)
                sr.check("VID.LOOP_ENDING", bool(same) or sim >= 0.85, "major",
                         f"loop beat: last scene subject {'matches' if same else 'differs from'} the opening; last/first frame similarity {sim:.2f}",
                         round(sim, 3), 0.85, fix("VISUAL_PLAN", "redesign_scene", scene="last", hint="call back to the opening frame"))
        sr.metric("visual_audit_composition", audit.get("composition"))
        hk = audit["hook"]
        exc = hk.get("hook_exception")
        sr.check("VID.FIRST_FRAME_SUBJECT", hk.get("subject_height_ratio", 0) >= 0.35 or bool(exc), "major" if not exc else "minor",
                 f"main subject {hk.get('subject_height_ratio', 0):.0%} of frame height at t=0" + (f" (exception: {exc})" if exc else ""),
                 hk.get("subject_height_ratio"), 0.35, fix("VISUAL_PLAN", "redesign_scene", scene="first", subject_height_target=0.35))
        bad_t = [t for t in hk.get("texts_t0", []) if t["lost_words"] or not t["inside_safe"] or t["size_px"] < 60]
        sr.check("VID.HOOK_TEXT_T0", not bad_t, "major", f"frame-0 text not fully readable: {[(t['text'], t['on_screen'], t['size_px']) for t in bad_t]}",
                 len(bad_t), 0, fix("VISUAL_PLAN", "redesign_scene", scene="first", problems=[t["text"] for t in bad_t]))
        ev0 = hk.get("first_visual_event_s")
        sr.check("VID.FIRST_EVENT", (ev0 is not None and ev0 <= 0.5) or bool(hk.get("idle_motion_at_t0")), "major",
                 f"first visual event at {ev0} s", ev0, 0.5, fix("VISUAL_PLAN", "add_entrances", at_s=0.0))
        sr.output(work / "visual_audit.json", "visual_audit", "application/json")
        sr.metric("engine", "doodle"); sr.metric("sfx_events", len(used)); sr.metric("first_frame_ink", round(ink, 4))
        sr.metric("visual_audit", {"issues": len(audit["issues"]), "hook": audit["hook"]})
        sr.metric("music", music_meta)
        sr.metric("transitions", [k for k, _ in tl.trans[1:]])
    else:
        lens = [s["end"] - s["start"] for s in shots]
        shot_max = SHOT_MAX_S["long" if LONG else "short"]
        sr.check("VID.SHOT_PACING", max(lens) <= shot_max, "major", f"longest shot {max(lens):.2f}s", round(max(lens), 2), shot_max,
                 fix("VISUAL_PLAN", "retime", max_shot=min(3.2, shot_max)))
        sr.metric("engine", "kenburns"); sr.metric("transitions", sum(1 for t in trans if t))
    if a.script and Path(a.script).exists():       # Phase 3.5: CTA placement on the real timeline
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "short-form-script" / "scripts"))
        import cta as CTA
        scr, tm_ = read_json(a.script), read_json(a.timing)
        hist = [h["text"] for h in read_json(a.cta_history)["ctas"]] if a.cta_history and Path(a.cta_history).exists() else []
        cr = CTA.check(scr, tm_["sentences"], voice_dur, labels=(audit or {}).get("labels") if tl is not None else None,
                       history=hist, title=(scr.get("publish", {}).get("title_options") or [""])[0], timeline="actual")
        write_json(work / "cta_report.json", cr)
        sr.output(work / "cta_report.json", "cta_report", "application/json")
        for ck in cr["checks"]:
            if ck["id"] == "CTA.SCHEMA" and ck["passed"]:
                continue
            sr.check("VID." + ck["id"].replace(".", "_"), ck["passed"], ck["severity"], ck["evidence"],
                     fix=None if ck["passed"] else fix("SCRIPT" if ck["id"] != "CTA.ON_SCREEN_SHOWN" else "VISUAL_PLAN",
                                                       "revise_cta", check=ck["id"], evidence=ck["evidence"][:200]))
        sr.metric("cta", cr["metrics"])
    mu = mix_report.get("music_under_voice_db")
    if music is not None and a.music_under_voice_db is not None:
        lo_, hi_ = MIX_POLICY_DB     # the policy range is judged here, whatever level a fix route asked for
        sr.check("VID.MIX_BALANCE", mu is not None and lo_ <= mu <= hi_, "major",
                 f"music {mu} dB under the voice (policy {lo_}-{hi_} dB; requested {a.music_under_voice_db})", mu, [lo_, hi_],
                 fix("VIDEO", "remix", music_under_voice_db=17.0))
    if tl is not None:
        sps = mix_report.get("sfx_per_s") or 0
        sr.check("VID.SFX_DENSITY", sps <= a.sfx_max_rate + 1e-6, "major", f"{sps} SFX/s (cap {a.sfx_max_rate})", sps, a.sfx_max_rate,
                 fix("VIDEO", "remix", sfx_max_rate=a.sfx_max_rate))
    mk = mix_report["masking"]
    below_n = round(mk["frames_below_10db"] * mk["speech_frames"])
    # >2 % of active-speech frames AND at least 3 frames (150 ms): on ~200-frame videos this equals the 2 % rule; it only
    # stops one or two frames from deciding a very short clip
    sr.check("VID.SPEECH_MASKING", mk["sir_p5_db"] >= 10 and not (mk["frames_below_10db"] > 0.02 and below_n >= 3), "major",
             f"speech-band SIR p5 {mk['sir_p5_db']} dB, median {mk['sir_median_db']} dB, {mk['frames_below_10db']:.1%} "
             f"({below_n} of {mk['speech_frames']}) speech frames < 10 dB",
             mk["sir_p5_db"], 10, fix("VIDEO", "remix", music_carve_db=min(16.0, a.music_carve_db + 2)))
    en = mix_report["ending"]
    # v3.3 (D2): a long-form video keeps a calm music tail for the end screen, so it does not have to be silent —
    # a music bed faded ≥6 dB and a tail quieter than −30 dBFS is accepted instead. Shorts keep the strict −45 dB rule.
    if LONG:
        end_ok = (en["tail_30ms_dbfs"] <= -45) or (en["music_fade_db"] is not None and en["music_fade_db"] >= 6
                                                   and en["tail_30ms_dbfs"] <= -30)
    else:
        end_ok = en["tail_30ms_dbfs"] <= -45 and (en["music_fade_db"] is None or en["music_fade_db"] >= 6)
    sr.check("VID.CLEAN_ENDING", end_ok,
             "major",
             f"last 30 ms {en['tail_30ms_dbfs']} dBFS (≤ −45, or ≤ −30 with a ≥6 dB music fade on long-form); "
             f"music fade {en['music_fade_db']} dB", en["tail_30ms_dbfs"], -45,
             fix("VIDEO", "remix"))
    sr.output(work / "mix_report.json", "mix_report", "application/json")
    sr.metric("mix", {k: mix_report.get(k) for k in ("music_under_voice_db", "sfx_per_s", "sfx_near_voice_share")})
    sr.metric("duration_s", round(dur, 2)); sr.metric("lufs", i_lufs); sr.metric("peak_dbfs", peak)
    sr.metric("shots", len(shots))
    sr.output(final, "video_nosubs", "video/mp4")
    res = sr.finalize(a.result)
    emit(res)
    return exit_for(res)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--storyboard", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--timing", help="voice timing.json (default: timing.json next to the voice file)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--result", required=True)
    ap.add_argument("--engine", choices=["auto", "doodle", "kenburns"], default="auto")
    ap.add_argument("--aspect", choices=["vertical", "wide"],
                    help="output size when the storyboard carries no canvas: vertical=1080x1920, wide=1920x1080")
    ap.add_argument("--music", default="procedural", help="procedural (playful bed) | pad (v1 drone) | none | path to a licensed track")
    ap.add_argument("--music-license", help="license string for a provided track (required for provenance)")
    ap.add_argument("--music-gain-db", type=float, default=-19.0)
    ap.add_argument("--sfx", choices=["auto", "none"], default="auto")
    ap.add_argument("--sfx-density", type=float, default=1.0, help="0.5 = calmer, 1.5 = busier sound design")
    ap.add_argument("--sfx-max-rate", type=float, default=0.8, help="hard cap on SFX per second (Phase 3)")
    ap.add_argument("--music-under-voice-db", type=float, default=17.0,
                    help="closed-loop music level below the voice during speech (Phase 3 target 16-18 dB; none = fixed gain)")
    ap.add_argument("--script", help="script.json (enables the loop-ending check)")
    ap.add_argument("--cta-history", help="cta_history.json of earlier packaged videos")
    ap.add_argument("--fixed-music-gain", action="store_true",
                    help="use --music-gain-db as is (no closed-loop level control; legacy runs and bad-video fixtures)")
    ap.add_argument("--music-carve-db", type=float, default=12.0,
                    help="dynamic cut of the music's speech band (300-4000 Hz) while the voice speaks (Phase 3; 0 = off)")
    ap.add_argument("--max-motion-gap", type=float, default=3.5)
    ap.add_argument("--lufs", type=float, default=-14.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--attempt", type=int, default=1)
    a = ap.parse_args()
    return main_cmd(a)


if __name__ == "__main__":
    sys.exit(main())
