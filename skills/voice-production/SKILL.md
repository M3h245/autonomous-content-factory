---
name: voice-production
description: Produces narration for short videos with word-level timing taken from the TTS model itself — local Kokoro voices (English, Italian, Spanish, French, Portuguese, Hindi, Japanese, Chinese; free, no API key) or ElevenLabs when a key and network access exist — plus pronunciation lexicons, pacing control and an audio gate (word coverage, duration window, dead air, hook onset). Use for "voice this script", "make a voiceover", "text to speech", "redo the narration faster or with another voice", or the content factory AUDIO stage. Not for music, sound design, or cloning a real person's voice.
---

# Voice Production

**Stage:** AUDIO · **Error codes:** `AUDIO.*` · **Gate:** `scripts/tts.py synth` (gate built in)

## Activation
Every factory video (run by `factory.py media`); any standalone voiceover request.

## Responsibilities
Natural narration plus exact word timings — the timing file is what makes captions synchronized word by word.

## Inputs → outputs
| In | Out |
|---|---|
| `script.json`, voice id, speed, optional `lexicon.json` (`{"rayleigh": "ray-lee"}`) | `audio/voice.wav` (24 kHz mono), `audio/timing.json` (words + sentences with start/end), `result.json` |

## Workflow
1. Once per machine/session: `python scripts/tts.py setup` (downloads Kokoro fp32 model + voices from GitHub releases, ~354 MB).
2. Choose a voice per language (`references/voices.md`; defaults en=af_heart, it=if_sara, es=ef_dora, fr=ff_siwis, pt=pf_dora).
3. `tts.py synth --script … --out-dir … --result … [--voice …] [--speed 1.0] [--min-s --max-s]`.
   Each sentence is synthesized separately (exact sentence boundaries), timings come from the model's phoneme
   durations aligned to words; pauses: 0.16 s within a beat, 0.24 s between beats.
4. ElevenLabs (`--backend elevenlabs --voice VOICE_ID`) only where `ELEVENLABS_API_KEY` is set and egress exists
   (the user's machine); timings come from the provider's character alignment.

## Duration estimate + intentional pauses (Phase 2)
`scripts/estimate.py` predicts spoken duration from syllables of the spoken form (numbers expanded), words, commas
and questions with per-voice coefficients fitted on real Kokoro output (`references/voice_calibration.json`,
`estimate.py calibrate --voice …` on `references/calibration_corpus.txt`); it mirrors the assembly (lead, gaps,
pauses, tail). Beats may carry `pause_before`/`pause_after` (≤1.5 s): applied at assembly (no re-synthesis, cache
intact), recorded in timing.json and in the `intentional_pauses` metric, and excluded from the AUDIO.MAX_GAP dead-air
check.

Reproducibility (Phase 3): audio bytes depend on the inference runtime. setup_env.py pins onnxruntime 1.29.0 and
kokoro-onnx 0.6.1; the TTS cache key and timing.json (`runtime`) include the installed versions, so a cache never mixes
runtimes and cross-environment drift is visible.

## Quality gate
AUDIO.SCHEMA, ALL_SENTENCES, WORD_COVERAGE, TIMING_MONOTONIC (blocking) · DURATION_IN_RANGE, MAX_GAP ≤0.75 s,
HOOK_START ≤0.35 s (major) · SPEECH_RATE 1.8–3.8 words/s (minor).

## Failure recovery
Too long by ≤15 % → automatic `speed_up`; longer → SCRIPT `shorten`; dead air → resynthesize with tighter gaps;
unsupported language → `switch_backend`; mispronunciation (from QA/user) → add a lexicon entry and rerun.

## Scripts · References
`scripts/tts.py setup|voices|synth` · `references/voices.md`

## Dependencies
kokoro-onnx, onnxruntime, soundfile, numpy (CPU only; ≈1.25× real time on one vCPU). Optional ElevenLabs API.

## Interactions
Input from short-form-script / multilingual-content; `timing.json` drives visual retiming (visual-storyboarding),
video length (video-production) and captions (subtitle-production); provenance record marks synthetic voice.
