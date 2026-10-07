---
name: video-quality-assurance
description: Independent QA of a finished short video before it ships — full-decode integrity, container spec, duration window, loudness and true peak, black or frozen frames, audio dropouts, hook timing, caption overlap, burn-in proof and OCR caption agreement — followed by a structured vision review of a contact sheet and the first frame (caption readability, collisions, visual-narration match, artifacts, unsupported claims, safety). Every failure returns a fix route so the responsible stage is regenerated. Use for "check this video", "is it ready to post", "QA my shorts", or the content factory QA stage. Not for post-publication analytics.
---

# Video Quality Assurance

**Stage:** QA · **Error codes:** `QA.*` (automatic), `V.*` (vision review) · **Gate:** `scripts/qa_video.py check` → `finalize`

## Activation
Every factory video after SUBTITLES; any "is this ready?" request on an MP4.

## Responsibilities
Be the skeptical last line: measure what can be measured, then actually look. A pass means you would post it.

## Inputs → outputs
| In | Out |
|---|---|
| `subtitles/final.mp4`, `video/video_nosubs.mp4`, `audio/timing.json`, `subtitles/captions.ass`, dossier (for claims) | `qa/qa_report.json`, `qa/contact_sheet.jpg` (15 frames), `qa/hook.jpg`, `qa/review_template.json`, `qa/review.json`, `qa/result.json` |

## Workflow
1. `qa_video.py check --video … --timing … --captions … --nosubs … --out-dir … --result … [--min-s --max-s]`.
   Failures route automatically. If all automatic checks pass, status is `pending_review` (exit 3).
2. View `contact_sheet.jpg` and `hook.jpg`. Answer every item in `review_template.json` (see
   `references/review-checklist.md`) in `review.json`: `{"reviewer": "claude-vision", "items": [{"id", "passed", "note"}]}`.
   Be specific in notes; fail an item rather than rationalize it.
3. `qa_video.py finalize --out-dir … --review … --result …`, then `factory.py record`.

## Independent review (Phase 1)
After the automatic checks, the review is done by an INDEPENDENT reviewer, never by the author:
1. `review_packet.py build …` — builds the packet (final artifacts + deterministic measurements only; authoring
   files are refused, the author's self-review is stripped; every file hash-pinned in manifest.json).
2. `reviewer.py review --packet … --out … --backend auto|heuristic|anthropic|subagent` — separate process,
   objective checks + 11 rubric dimensions (1-5 with evidence; explanation for every score < 4), writes
   review_report.json/.md and boundary_log.json. Exit 0 PASS · 2 FAIL · 3 awaiting a subagent/human judgment.
3. `qa_video.py finalize --out-dir … --independent …/review_report.json --result …` — QA verdict = technical
   checks + reviewer (`REV.<DIMENSION>` checks with repair routes). `--review review.json` (author self-review) is
   legacy and not used by the factory.
The factory runs these automatically for heuristic/anthropic judges and hands out a review task for subagent/human.
Rubric, anchors, caps and gate: `references/review-rubric.md`, `references/review-policy.json`.

## Quality gate
Blocking: DECODE_OK (full decode, no errors), CONTAINER_SPEC, PLATFORM_MAX (≤180 s), AV_DURATION, CAPTIONS_PRESENT, CAPTION_OVERLAP, BURNED_IN,
V.CAPTIONS_READABLE, V.NO_ARTIFACTS, V.SAFE_AND_ORIGINAL, V.CLAIMS_SUPPORTED.
Major: DURATION_TARGET, LOUDNESS (−14 ±1.5 LUFS), TRUE_PEAK ≤ −1 dBTP, NO_BLACK, NO_FREEZE (≥3 s), NO_DROPOUT,
HOOK_AUDIO ≤0.4 s, HOOK_CAPTION ≤0.6 s, OCR_MATCH (≥60 % samples; polarity-aware — light or dark-ink captions), V.NO_COLLISION, V.HOOK_FRAME, V.VISUALS_MATCH.
Minor: FASTSTART.

## Failure recovery
Each check carries its fix route (e.g. NO_FREEZE → shorter shots; OCR_MATCH → bigger captions; V.CLAIMS_SUPPORTED →
SCRIPT revise_claims). The orchestrator reruns from the earliest responsible stage.

## Scripts · References
`scripts/qa_video.py check|finalize` · `references/review-checklist.md`

## Dependencies
ffmpeg/ffprobe, numpy, Pillow; tesseract for OCR (English verified; other languages need their traineddata).

## Interactions
Reads outputs of voice/video/subtitle production; its routes target any upstream stage; PACKAGE requires QA passed.
