# PHASE 3 REPORT — Visual + Audio · v2.0.0-alpha6 · 2026-10-07

**Status: PASS.** Every objective Phase 3 gate is implemented, unit-tested and met by a fresh RESEARCH → PACKAGE run.
The final code reproduced that run in a new environment with zero interventions, and a second replay in that
environment was byte-identical. The owner's listening calibration is done (2026-10-07: **mix A** — 17 dB + 12 dB carve,
the existing default). The limitations at the end are carried, non-blocking items.

## What was built
- **Composition** (engine): layout class from geometry, a main-subject signature that ignores position and scale,
  subject height, and a 3×3 dead-space grid. Gates: VIS.LAYOUT_REPEAT, VIS.SUBJECT_REPEAT, VIS.SUBJECT_SIZE,
  VIS.DEAD_SPACE, VIS.OPENING_DENSITY.
- **Pacing**: VID.OPENING_DENSITY (≥2 events in 1.5 s), VID.PACING_CADENCE (max gap ≤3 s, median ≤1.8 s),
  VID.LOOP_ENDING.
- **Audio**: closed-loop music level (17 dB; policy 16-18), dynamic speech-band carve (12 dB), SFX budget ≤0.8/s with
  priority, spacing and a tail guard, music-aware speech protection, an active-speech masking metric, a clean-ending
  check.
- **Hook engine**: measures hook lines with the real TTS (this phase found the estimate had passed a 3.5 s hook).
- **Reproducibility**: TTS runtime versions are in the cache key and in timing.json; setup_env pins onnxruntime
  1.29.0 and kokoro-onnx 0.6.1.

## Baseline vs Phase 3 (measured)
| item | alpha5 wrinkle video | Phase 3 onion video (final code) |
|---|---|---|
| main-subject repetition | finger in 60 % of non-loop scenes, 3 in a row (VIS.SUBJECT_REPEAT FAIL) | onion 40 %, at most 2 in a row (PASS) |
| layouts | hero, panel, panel, split, split, hero | hero, grid, hero, character, text_led, hero |
| visual events in the first 1.5 s | 1 (FAIL) | 2 (PASS) |
| music under voice (speech) | 24.7 dB | 17.0 dB (+12 dB speech-band carve) |
| SFX per second | 1.26 | 0.76 |
| speech masking (active speech: SIR p5 / frames <10 dB) | n/a | 12.5 dB / 1.4 % |
| ending | — | last 30 ms −61.1 dBFS, music fade 14.1 dB, loop similarity 0.97 |
| independent review | — | PASS, every dimension ≥4 (first frame 5) |

## Audio decision evidence
With the alpha5 wrinkle mix at 16-18 dB and no carve, music masked 16-24 % of active-speech frames
(SIR p5 5.6-7.3 dB). Three combinations pass:
- 17 dB with a 12 dB carve (the requested level)
- 20-22 dB with a 6 dB carve
- the old 24.7 dB with no carve

After protection, SFX on their own never masked speech. The owner listened to all three (`listening_pack/`:
A = 17/12, B = 21/6, C = 24.7/0) on 2026-10-07 and chose **A**, the existing default — so no code change was needed. Waveform evidence is in `onion_audio_evidence.png`: the voice dominates,
the music rises only in pauses, and the SFX land mostly in gaps.

## Runs — honest account
| run | code / environment | retries | regenerations | resets | escalations | result |
|---|---|---|---|---|---|---|
| fresh 2026-10-06 | development code | 7 | 10 | 3 | 1 | PACKAGE, review PASS |
| replay 2026-10-06 | same | 0 | 0 | 0 | 0 | 9/11 byte-identical (other 2 differ only by run path) |
| replay A 2026-10-07 | final code, fresh environment | 0 | 0 | 0 | 0 | review PASS; audio differs from 10-06 by ≤8 ms (runtime) |
| replay B 2026-10-07 | same as A | 0 | 0 | 0 | 0 | 11/11 identical to A (9 bytes + 2 path-only) |

Resets in the fresh run, by cause:
- **Two were operator harness mistakes.** A blind loop re-ran a failing RESEARCH gate, and an old SCRIPT result was
  recorded out of order. The factory now refuses out-of-order records.
- **One followed a real design flaw**: SFX protection ignored the music.

The remaining retries were real defects the system caught:
- unsupported medium-risk facts
- a 3.5 s hook with no tension device
- near-duplicate hook lines
- small subjects and dead space
- speech masking
- a gate tokenisation bug

The video was inspected visually: the first 2 s frame by frame, plus a whole-video contact sheet of the final code's output.

## Tests (all green on the final code)
- **New**: test_phase3 (14).
- **Regression**: cf_common identity, stage order, Phase 0 regressions, TTS cache, visual audit 9, reviewer 10, futile
  retry 4, Phase 2 hooks 10, Phase 2 script 7, bad videos A/B/C, factory review 2, smoke.
- **v1 regression**: Ken Burns render + karaoke captions on a rebuilt fixture (see limitation 6).

Fixture updates (no gate was loosened):
- The smoke fixture now meets the composition and opening rules and uses a harmonic synthetic voice.
- Bad fixture C renders its loud mix with `--fixed-music-gain --music-carve-db 0`: the same 9.4 dB as in Phase 1.
- test_tts_cache's corruption step no longer depends on filesystem order.

## Checkpoint integrity finding (2026-10-07)
Between sessions the outputs storage rewrites standalone `.mp4`/`.jpg` files: the container grows by ~6 KB, but the
decoded video and audio are identical (stream MD5) and the embedded provenance/AI-label tags are kept. Zips, `.md` and
`.json` files are never altered. So the standalone media hashes in alpha2-alpha5 now fail `sha256sum -c`, while their
zipped copies verify. Those checkpoints were left untouched. From alpha6 on, the **zips are authoritative**:
`phase3-media.zip` holds the media, and the loose files are convenience copies only.

A second finding, the same day: the 756 MB `phase3-artifacts.zip` vanished from the outputs storage between sessions,
while zips up to ~334 MB survived. The artifacts were rebuilt from the local copies as four parts of 130-190 MB each
(`phase3-artifacts-part*.zip`). Rule from now on: keep every checkpoint file under 250 MB.

## Limitations
1. ~~Music level not confirmed by ear~~ — closed 2026-10-07: owner chose A.
2. ~~12 dB carve may sound thin~~ — closed: judged acceptable by the owner (phone speaker + headphones).
3. The reviewer is still heuristic (no real-model LLM judge).
4. "THE CHAIN" scene shows only its title for about 1 s. It passes the gates because text counts as content.
5. Frame 0 shows "TEAR GAS?" about 0.5 s before the gas appears.
6. Byte reproducibility is proven within one environment only. A reinstall shifted Kokoro output by up to 8 ms; the
   runtime is now pinned and recorded but not yet re-proven on a second fresh install. The original v1 regression
   fixture was lost with a sandbox reset; it was rebuilt from the saved tickle artifacts (same script and art, as
   stills) and is now saved in the checkpoint.
7. VID.SPEECH_MASKING was defined in this phase with a 3-frame minimum (equal to the 2 % rule on ~200-frame videos).
