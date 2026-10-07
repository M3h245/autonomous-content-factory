---
name: subtitle-production
description: Creates word-synchronized captions for short videos and hard-burns them into the picture — hand-lettered doodle captions with a marker swipe on the spoken word (v2 default for doodle videos), karaoke-style chunks with the spoken word highlighted, one-word, or clean two-line styles — exports SRT and VTT, fits a platform-safe area, checks glyph coverage, renders right-to-left scripts such as Persian and Arabic correctly, and proves the captions are burned into the pixels. Use for "add subtitles or captions", "word-by-word captions", "burn subs into this video", "my ASS file isn't showing", or the content factory SUBTITLES stage. Needs word timings (timing.json). Not for translating text or writing scripts.
---

# Subtitle Production

**Stage:** SUBTITLES · **Error codes:** `SUB.*` · **Gate:** `scripts/subtitles.py run` (gate built in)

## Activation
Every factory video (media chain); any captioning request where word timings exist (from voice-production, or an
aligner such as WhisperX run on the user's machine and converted to `timing.json`).

## Responsibilities
Captions that appear exactly when each word is spoken, are always legible, and are part of the final pixels —
a sidecar file alone is never the deliverable.

## Inputs → outputs
| In | Out |
|---|---|
| `audio/timing.json`, `video/video_nosubs.mp4`, optional timed storyboard (title overlays) | `subtitles/captions.ass` (burned), `captions.srt` + `captions.vtt` (upload), `final.mp4`, `result.json` |

## Workflow
`subtitles.py run --timing … --video … --out-dir … --result … [--style auto|doodle|karaoke|word|clean] [--max-words 3] [--y 0.63] [--font-scale 1.0] [--font auto]`
- auto (default): `doodle` when the timed storyboard contains doodle scenes, else `karaoke`.
- doodle: Permanent Marker ink with a white edge, a yellow marker swipe behind the spoken word (a layer-0 copy of
  the line, so it is glyph-aligned in any script), slight per-chunk tilt that snaps in. Sized from the font's real
  libass metrics (cap height ≈70 px). Latin scripts; RTL text falls back to karaoke + Vazirmatn.
- karaoke: 1–3 words, breaks at punctuation/sentences/pauses, active word yellow, pop-in per chunk.
- Fonts bundled (OFL): Anton (Latin display), Archivo Black, Vazirmatn Bold (Arabic script). Auto-selects Vazirmatn for
  RTL text, sets auto base direction and HarfBuzz shaping — verified to render Persian joined and in correct order.
- Caption centre at 63 % height, 90 px side margins: clear of platform UI at bottom and right.

## Quality gate
SUB.DECODE_OK, COVERAGE, NO_OVERLAP, SYNC, FITS_SAFE_AREA, GLYPH_COVERAGE, BURNED_IN (blocking) · MIN_DISPLAY ≥0.25 s (major).
DECODE_OK fully decodes final.mp4 — BURNED_IN alone would also "pass" a corrupted file.
BURNED_IN compares the caption band of `final.mp4` against the master at three caption times.

## Failure recovery
Too wide → smaller `font_scale` or fewer words; missing glyphs → switch font; flicker → raise `max_words`;
burn-in not detected → reburn; QA readability/collision issues → `font_scale` 1.1 or `y` 0.70.

## Scripts · References
`scripts/subtitles.py` · `assets/fonts/` (+ OFL licenses) · `references/caption-styles.md`

## Dependencies
ffmpeg with libass + FriBidi + HarfBuzz, fontTools, Pillow, numpy.

## Interactions
Timing from voice-production; master from video-production; QA re-verifies burn-in and OCR; fonts listed in provenance.
