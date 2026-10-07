# Packaging (Phase 4)

The video is finished when PACKAGE starts. Packaging decides how it is *presented*: title, thumbnail, the first caption
line (the package's opening promise), description, hashtags and how the copy lines up with the video's CTA. The video's
spoken hook is fixed; every package must be coherent with it.

## What the operator writes

`videos/<v>/package/package_candidates.json` (contract `package_candidates`) and one SVG per candidate under
`videos/<v>/package/svg/`. At least **3 complete, genuinely different packages**:

| field | rule |
|---|---|
| `strategy` | curiosity · mechanism · question · challenge · myth_bust · contrast · utility · story — one per candidate |
| `title` | ≤55 chars, ≤10 words; about what the video actually says; its focus must get real airtime; no bait |
| `opening_promise` | first caption line (≤120 chars); shares words with the video's opening line |
| `thumbnail.svg` | 1080×1920 doodle scene (same engine/palette as the video); rendered settled, no camera |
| `thumbnail.text` | 0-4 words, exactly what the SVG shows; complements the title — never repeats it |
| `thumbnail.depicts` | dossier fact ids the picture shows (a thumbnail may not show something the evidence doesn't) |
| `description` | ≤400 chars, describes what is said |
| `hashtags` | 2-6, relevant |
| `claim_ids` | dossier facts every claim in title/promise/description rests on |
| `caption_cta` | optional; may only echo the video's own CTA |

Thumbnail layout that passes: one big subject (≥40 % of the central square's height, ≥85 % inside it), text 140-170 px
marker in dark ink in the top of the central square (y≈480-640), ≥24 px clear of the subject, no tiny details,
≤3 empty cells of the 3×3 grid over the central square. The central 1080×1080 square (y 420-1500) survives every
platform crop: Reels grid, TikTok 3:4, YouTube's ≈3:2 rendering of Shorts thumbnails.

## Gates (deterministic, `package_engine.py`)

Per candidate — blocking: unknown fact ids, unsupported number/absolute/health-or-causal term, a claim the cited fact
negates ("causes arthritis" vs "no link"), title not about the video, thumbnail missing/wrong size, unknown `depicts`.
Major: title length/words, caps/!!/bait phrases, title focus never paid off or not said in the video, opening promise
unrelated to the opening, thumbnail words/size/headline/contrast at 168 px/text outside the central square/text over
the subject/small or off-centre subject/two competing subjects/dead space/clutter/text not said in the video/CTA on the
thumbnail, copy CTA conflicting with the video's CTA or asking for two things, hashtag format/relevance.

Set — blocking: <3 candidates; <3 candidates that pass every deterministic gate; no 3 viable candidates that are
mutually distinct (strategy, title words, thumbnail words, opening promise, perceptual hash of the thumbnail).

## Independent review (`reviewer.py review-package`)

One hash-pinned packet per candidate: finished copy, thumbnail (full + 168 px), the video's first frame, transcript,
video CTA, evidence and measurements — never the strategy, concept, rationale or SVG. Nine dimensions (1-5):
title strength, curiosity, accuracy, thumbnail readability, title/thumbnail complementarity, hook/package coherence,
promise/payoff (incl. airtime of the title's focus), clickbait risk (5 = safe), CTA coherence. Thresholds in
`review-policy.json → package_thresholds`. An optional external judgment (`videos/<v>/package/package_judgment.json`,
written by a fresh agent or a human who saw only the packets) can lower a score, never raise it. Since v3.0.0 it must
cover every candidate it is applied to: a candidate it does not name fails JUDGMENT.MISSING (judge the new packet or
remove the file), and an entry carrying `packet_manifest_sha256` that differs from the current packet fails
JUDGMENT.STALE. A failed PACKAGE leaves no deliverables and no run zip behind.

Selection: the PASS candidate with the highest total (ties: accuracy, clickbait safety, shorter title, id).
Every other candidate is recorded with its reasons.

## Output (`package/<v>/`)

`thumbnail.jpg` (= `cover.jpg`), `thumbnail_crops.jpg`, `metadata.json` (selected title/description/captions, cover
steps per platform, AI labels), `publishing_package.json` + `PUBLISHING_PACKAGE.md` (public copy, video reference,
covers, review result, rejected alternatives; internal references kept in a separate section). Media metadata policy
(asset-provenance SKILL.md; tightened in v3.0.1): video and images are cleaned losslessly to playback-only metadata,
with no embedded AI-label metadata, and audited. Disclosure lives in metadata.json for manual upload;
PKG.DISCLOSURE still blocks without labels.
Public-copy check covers the authored copy only — the AI-disclosure line names the tools on purpose.
