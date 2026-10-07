# PHASE 3.5 REPORT — Retention + CTA + Conversion · final-media metadata · v2.0.0-alpha7 · 2026-10-07

**Status: PASS WITH LIMITATIONS.** Every Phase 3.5 gate is implemented and unit-tested. Deliberately bad CTAs are
rejected for the intended reasons. A fresh RESEARCH → PACKAGE run with a CTA passed every gate and the independent
review with zero resets and zero escalations, and its replay was deterministic. Publishable media now carry only
standard metadata. The limitations at the end are honest, non-blocking items.

## What was built
- **CTA engine** (`short-form-script/scripts/cta.py`, contract `script.cta`):
  - Each video records a decision: a CTA, or a deliberate "no CTA" with its reason. New runs (`cta_engine: v1`) must
    decide.
  - 9 types, 3 placements (`integrated` / `after_payoff` / `on_screen_only`), 3 modalities.
  - Deterministic gates run on the estimated timeline at SCRIPT and on the real one at VIDEO. They check that the CTA
    is outside the hook, after the payoff, short enough (spoken ≤ min(2.8 s, 12 % of runtime)), and that the video still
    ends well (loop line stays last; the ending stands without the CTA). They also enforce a single declared CTA,
    relevance and no stock outro, no repetition against `cta_history.json`, and an on-screen CTA really visible in its
    window.
- **Independent review**: four CTA dimensions (quality, naturalness, relevance, retention risk), applied only when a
  CTA is present. Failed CTA gates count as objective failures, separate from judgement. `ending_quality` gains
  "ending stands without the CTA". The packet holds only the CTA as the viewer gets it, never the author's reason.
- **Final-media metadata policy** (`asset-provenance/scripts/media_clean.py`):
  - **MP4**: stream copy with the container metadata and H.264 SEI user data removed. Picture and sound stay
    MD5-identical.
  - **JPEG**: a lossless segment stripper. Pixels stay identical.
  - **AAC**: encoded with +bitexact, so no encoder string sits inside the audio.
  - **PACKAGE gates (blocking)**: PKG.MEDIA_METADATA_CLEAN audits every publishable file; PKG.FINAL_DECODES;
    PKG.DISCLOSURE requires the platform AI labels plus the disclosure line in the description, so the policy can never
    remove disclosure.

## Platform guidance (verified 2026-10-07, before implementing)
- YouTube's end-screen help says end screens need videos of at least 25 s and does not mention Shorts.
- Shorts link onward with a **related video** set in YouTube Studio. It appears below the channel handle and needs
  advanced feature access.

So the factory reserves no end-screen zone. A part_2 CTA adds that manual step to `metadata.json`. One assumption is an
inference, not verified on Google's pages: that Shorts loop. On that inference, a spoken CTA after the loop line is
blocked.

## Bad-CTA evidence
- **Unit fixtures (each fails on its own rule)**:
  - a CTA in the hook → NOT_IN_HOOK
  - a CTA inside the payoff → AFTER_PAYOFF
  - a 20-word CTA → DURATION
  - a CTA after the loop → ENDING
  - "like and subscribe" → RELEVANCE
  - a repeat from history → NOT_REPEATED
  - a hidden second CTA → SINGLE
  - an ending that only works with the CTA → STANDALONE_ENDING / AFTER_PAYOFF
  - a mismatched schema → SCHEMA
  - an on-screen CTA never shown → ON_SCREEN_SHOWN
- **Rendered fixture D** (a generic "like and subscribe" after the loop line):
  - VIDEO fails VID.CTA_ENDING, VID.CTA_RELEVANCE and VID.CTA_DURATION.
  - The reviewer returns FAIL with relevance 1 and retention risk 1, routed to SCRIPT revise_cta.

## Fresh run — "Why your knuckles crack" (sources verified)
Sources: *PLoS ONE* 2015 MRI; *Scientific Reports* 2018 model; *JABFM* 2011 arthritis study; Ig Nobel 2009.

| item | result |
|---|---|
| hooks | 5 candidates measured with real TTS. 3 rejected (too long by 0.02-0.3 s, small subject, safe margin); h3 selected, scores 4/5/5 |
| script | variant A (integrated comment CTA) PASS 4/4/4/4 and CTA 4/4/4/5; variant B (deliberate no-CTA) FAIL on clarity, pacing, callback |
| CTA | comment, integrated on the loop line, spoken + on screen: "Do you crack yours?" at 30.81-32.02 s (1.21 s), after the payoff |
| VIDEO | all 11 CTA gates pass on the real timeline; music 17.0 dB; SFX 0.80/s; masking SIR p5 12.8 dB |
| review | PASS: hook 4, first frame 5, clarity 3, sync 4, pacing 4, audio 4, subtitles 4, ending 4, title 4, cover 4, overall 4; CTA 4/4/4/5 |
| PACKAGE | metadata audit clean (3 files); decodes; disclosure labels present; independent check: 0 forbidden strings, standard tags only, cover without EXIF/comment |
| totals | 4 retries, 4 regenerations, **0 resets, 0 escalations** |
| replay | 0 retries; review PASS; 11/11 identical (9 bytes + 2 run-path-only) |

The 4 retries:
1. A source tier: *JABFM* was given by its website rather than its DOI.
2. The reviewer stemming bug, now fixed.
3. A real 4.5 s motion gap in the MRI scene.
4. The same gap again, because of an operator mistake: my edit never ran, so VISUAL_PLAN and VIDEO repeated with
   identical inputs.

Visual inspection of the rendered video covered the first 2 s frame by frame, the CTA ending, and a contact sheet of
the whole video. It also found a text-on-text overlap in scene 6 ("215" over "people studied") before rendering, which
was fixed.

## Tests (all green)
- **New**: test_phase35 (22), bad fixture D.
- **Regression**: cf_common identity, stage order, Phase 0 regressions, TTS cache, visual audit 9, reviewer 10,
  futile retry 4, Phase 2 hooks 10, Phase 2 script 7, Phase 3 (14), bad videos A/B/C, factory review 2, smoke.
- **v1**: Ken Burns + karaoke.
- No Phase 0-3 gate was weakened. CTA.DECIDED applies only to new runs, so older runs replay unchanged.

## Limitations
1. **CTA judgement is heuristic** (no real-model LLM judge; taste dimensions are capped at 4).
2. **No measured conversion effect.** The CTA rules are a-priori retention safeguards; real effect needs analytics
   after publishing.
3. **message_clarity 3** on the knuckle video: acceptable under the policy (minimum 3) but not strong.
4. **No text-on-text overlap gate.** The scene-6 collision was caught by eye only.
5. **No futile-resubmission guard for VISUAL_PLAN.** An identical resubmission (my operator mistake) is not detected
   there; the guard covers only deterministic stages and hooks.
6. **YouTube "altered/synthetic" label** is still decided by the unchanged provenance logic (False for cartoon visuals
   with AI narration). It was not re-reviewed in this phase.
7. **Byte reproducibility across environments** is still unproven (carried from Phase 3).
