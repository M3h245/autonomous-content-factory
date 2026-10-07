---
name: video-production
description: Assembles vertical 1080x1920 videos — the v2 doodle engine (hand-drawn scenes animated element by element on narration words, boiling marker lines, camera punch-ins, page transitions, synced procedural sound effects) or v1 Ken Burns motion on stills/footage — with a seeded royalty-free music bed ducked under the narration and two-pass loudness normalization to -14 LUFS, then gates the result (decode integrity, spec, duration match, loudness, peak, motion gaps, blank frames, first frame). Use for "render the video", "assemble these images and the voiceover into a short", "add motion or music", or the content factory VIDEO stage. Not for burning captions (subtitle-production), QA verdicts (video-quality-assurance), or generative AI video.
---

# Video Production

**Stage:** VIDEO · **Error codes:** `VID.*` · **Gate:** `scripts/render_video.py` (gate built in)

## Activation
Every factory video (run by `factory.py media` after retime); standalone assembly requests.

## Responsibilities
A clean master without captions: correct spec, something new on screen every few seconds, sound design that supports
the jokes, music that never fights the voice, broadcast-sane loudness.

## Inputs → outputs
| In | Out |
|---|---|
| timed storyboard (`video/storyboard.timed.json`, from `storyboard_tool.py retime`), `audio/voice.wav`, `audio/timing.json` (doodle word cues) | `video/video_nosubs.mp4` (H.264 yuv420p 30 fps, AAC 48 kHz stereo), `video/work/*` (incl. `sound_design.json`, `music_bed.wav`, `sfx.wav`), `result.json` |

## Workflow
1. Retime (done by the media chain): `storyboard_tool.py retime --storyboard … --timing … --out … --max-shot 3.6`.
2. `render_video.py --storyboard … --voice … --timing … --out-dir … --result … [--engine auto|doodle|kenburns]
   [--music procedural|pad|none|PATH --music-license "…"] [--sfx auto|none] [--sfx-density 1.0] [--lufs -14]`.
3. Doodle engine (`scripts/doodle_engine.py`, auto when any scene is `kind: doodle`): parses each scene SVG, expands
   `data-lib` components (`scripts/doodle_lib.py`), resolves `w:` cues against the real word timings, renders frames
   with Skia (discrete+corner path effects = marker wobble, re-seeded 10×/s) straight into x264, and reports animation
   events. Entrances cued at t=0 start during the incoming transition so pages never arrive blank. ≈40 ms/frame.
4. Ken Burns engine (v1): zoompan on a 2× source (smoothstep easing) or cover-crop footage; xfade where requested.
5. Audio (`scripts/audio_design.py`): `procedural` = seeded marimba/pizzicato/shaker bed (key, tempo, progression vary
   per video), `pad` = v1 drone. SFX (pop, scribble, whoosh, page, boing, thump, ding) synthesised and placed on the
   doodle events with spacing/density rules. Music ducked −9 dB under speech, SFX −3 dB; loudnorm two-pass to −14 LUFS.

## Phase 3: audio mix + visual pacing gates
Music level is a closed loop: `--music-under-voice-db 17` (policy 16-18 dB; VID.MIX_BALANCE judges the policy range
whatever a fix route asks) with a dynamic speech-band carve while the voice speaks (`--music-carve-db 12`).
SFX: deterministic budget ≤0.8/s, ≥0.35 s apart, nothing running into the last 0.15 s (priority: transitions,
camera punches, accents, pops, slides, scribbles), then speech protection that only lets SFX use the room the music
leaves (music + SFX stay 12 dB under the voice in the speech band). Gates: VID.SFX_DENSITY, VID.SPEECH_MASKING
(active-speech SIR p5 ≥10 dB; fail if >2 % of active-speech frames AND ≥3 frames are below 10 dB), VID.CLEAN_ENDING
(last 30 ms ≤ −45 dBFS, music fade ≥6 dB), VID.OPENING_DENSITY (≥2 events in 1.5 s), VID.PACING_CADENCE (max gap ≤3 s,
median ≤1.8 s), VID.LOOP_ENDING (loop beat returns to the opening subject or frame). `--fixed-music-gain` disables
level control (legacy / bad-video fixtures). Calibrated by ear 2026-10-07: the owner chose mix A (17 dB + 12 dB carve)
over B (21/6) and C (24.7/0) after listening on phone speaker and headphones; these defaults are now confirmed.

Phase 3.5: with `--script`, VIDEO runs the CTA gates on the real timeline (VID.CTA_*; on-screen CTA text must appear
in the visual audit labels during the CTA window) and writes work/cta_report.json; AAC is encoded with +bitexact.

## Quality gate
VID.DECODE_OK (every packet decodes), VID.SPEC, VID.DURATION_MATCH ±0.12 s, VID.NOT_RETIMED, VID.NO_TIMING (blocking) ·
VID.LOUDNESS ±1.5 LU, VID.PEAK ≤ −0.5 dBFS (major) · Ken Burns: VID.SHOT_PACING longest shot ≤5 s (major) ·
Doodle: VID.MOTION_GAP ≤3.5 s without a new visual event, VID.EMPTY_FRAMES ≤0.5 s of blank paper,
VID.FIRST_FRAME ink ≥0.4 % (major), VID.SCENE_LINT (minor).

## Failure recovery
Loudness/peak → `remix` with a lower target; pacing → retime with shorter max shot (automatic); spec/duration/decode →
rerender; motion gap / blank frames / first frame → VISUAL_PLAN adds entrances or redesigns the named scene. A user-supplied track without `--music-license` is blocked later by asset-provenance.

## Scripts
`scripts/render_video.py` (stage + gate) · `scripts/doodle_engine.py` (`still --svg … --out …` for quick previews) ·
`scripts/doodle_lib.py` (component library) · `scripts/audio_design.py` · `assets/fonts/` (Patrick Hand, Permanent
Marker, Vazirmatn + licenses)

## Dependencies
ffmpeg ≥ 6 (libx264, zoompan, xfade, loudnorm, ebur128), numpy, soundfile; doodle: skia-python, svgelements
(arabic-reshaper + python-bidi only for RTL labels). Doodle ≈2× real time, Ken Burns ≈4.5× on one vCPU.

## Interactions
Consumes visual-storyboarding and voice-production outputs; feeds subtitle-production; music provenance goes to asset-provenance.
