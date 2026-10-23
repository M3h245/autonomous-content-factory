# Platform targets and policies (checked 2026-10-20 — re-verify before relying on them; not legal advice)

## Technical targets used by the gates
Short (9:16): 1080×1920, 30 fps, H.264 High yuv420p, AAC 48 kHz stereo, faststart; integrated loudness −14 LUFS ±1.5,
true peak ≤ −1 dBTP; captions centred at 63 % of height with 90 px side margins (clear of bottom UI and right-side buttons).
Long (16:9, v3.3): 1920×1080, everything else identical; captions centred at 86 % of height (no Shorts UI band to clear).
Every stage takes `--aspect vertical|wide` so the canvas, viewBox guard, caption PlayRes and QA container spec all agree.

**Duration windows + classification (v3.3).** What YouTube *calls* the upload decides which feed serves it, how it is
monetised and whether watch time counts toward the YPP threshold. It depends on **aspect ratio AND duration**:
(`factory.py init --aspect auto|vertical|wide`; `video_kind` in the brief is derived by `cf_common.video_kind`):
- **short** (`video_kind: "short"`): a **square or vertical** upload of **≤ 180 s** — a Short by definition, served in
  the Shorts feed. Its watch time does **not** count toward the 4,000 watch-hour threshold
  (support.google.com/youtube/answer/72851; answer/15424877). 15–180 s.
- **long** (`video_kind: "long"`): a **16:9** upload, or any upload longer than 3 minutes — served on the Watch Page,
  where watch hours count. v3.3 renders it 1920×1080 with the doodle engine (which now takes any canvas via
  `set_canvas`). `qa_video.py` gates duration against `max(180, brief.max_s)`.

**Length is a revenue choice, cited** (`factory.length_choice`, support.google.com/youtube/answer/2467968):
< 2 min → no mid-rolls, no Watch-While; 2–8 min → Watch-While ads; ≥ 5 min → ad pods possible; > 8 min → mid-rolls can
be turned on. The brief records the `length_choice.band` up front so the target is deliberate, not "~5 min".

**Monetisation thresholds.** YPP entry: 1,000 subscribers + 4,000 public watch hours / 365 d **or** 10 M Shorts views
/ 90 d. From **2027-02-01** the bar rises to **8,000 watch hours / 365 d** or **20 M Shorts views / 90 d**; the monthly
Shorts pool needs 10 M views / 90 d (answer/12843009, answer/12504220). Consequence: Shorts grow reach and followers;
**only long-form watch hours** open the watch-hour door.

**End screens (16:9 long-form only).** Last 5–20 s of a video ≥ 25 s; up to 4 elements including a **Subscribe**
element; the tail must be left free. The factory leaves a calm 5 s tail (`render_video.py END_SCREEN_TAIL_S`,
`VID.END_SCREEN_TAIL`) and tells the human to add the end screen (answer/6388789). Not applied to Shorts.

**Title/thumbnail A/B test (16:9 long-form only).** Studio → Test & compare, up to 3 titles/thumbs, decided by
**watch time** over ~2 weeks — not CTR, and **not available on Shorts** (answer/16391400). PACKAGE emits 3 title
variants and an `ab_test` block for long-form.

## Monetization: YouTube "inauthentic content" (since 15 July 2025)
YouTube renamed "repetitious content" to "inauthentic content": mass-produced, templated, low-variation videos — and
"AI-generated content made with generic or unoriginal templates … channels where content feels interchangeable from
video to video" — are not eligible for the Partner Program; reviewers look at the channel as a whole (theme,
most-viewed, newest uploads, metadata) (support.google.com/youtube/answer/1311392). This is the **highest policy risk
for a template factory**, so v3.3 adds a hard gate: `PKG.PACKAGING_VARIATION` fails when a video's title shape,
thumbnail text or opening promise is a near-duplicate (> 0.6 Jaccard) of an earlier video in the run or the channel's
history (`factory.db` `videos`). Every idea still carries a concrete value-add; batches vary format and angle; novelty
is checked against history; templates rotate across batches.

**Hashtags.** Up to **3 description hashtags** appear next to the title; more than **60** ⇒ *all* are ignored **and**
over-tagging "may result in the removal of your video … from search". Do **not** put `#` in the title
(answer/6390658). The gate caps at 8 and forbids `#` in titles (`script_lint.py SCRIPT.HASHTAGS`,
`SCRIPT.NO_HASH_IN_TITLE`).

## AI labels (realism test)
- YouTube: label realistic altered/synthetic depictions (and AI-generated music); an AI voiceover alone does not
  require the label; stylized/animated visuals do not.
- TikTok: label AI-generated or significantly edited realistic people, scenes, images or audio (the factory labels
  realistic synthetic voices conservatively).
- Instagram/Meta: "AI info" for photorealistic images or realistic-sounding synthetic audio.
- EU AI Act transparency duties (Art. 50) apply from 2 August 2026. The factory keeps the description disclosure line,
  and the platform labels in metadata.json for the owner to set at upload. Owner decision (v3.0.1): the media files
  carry **no** embedded AI-label or machine-readable AI marking (none had been embedded since Phase 3.5; v3.0.1
  makes that a tested guarantee). Whether Art. 50(2) machine-readable marking applies to this channel as a provider is
  the owner's call; if it does, the marking has to be added outside the factory.

## AI labels (realism test)
- YouTube: label realistic altered/synthetic depictions (and AI-generated music); an AI voiceover alone does not
  require the label; stylized/animated visuals do not.
- TikTok: label AI-generated or significantly edited realistic people, scenes, images or audio (the factory labels
  realistic synthetic voices conservatively).
- Instagram/Meta: "AI info" for photorealistic images or realistic-sounding synthetic audio.
- EU AI Act transparency duties (Art. 50) apply from 2 August 2026. The factory keeps the description disclosure line,
  and the platform labels in metadata.json for the owner to set at upload. Owner decision (v3.0.1): the media files
  carry **no** embedded AI-label or machine-readable AI marking (none had been embedded since Phase 3.5; v3.0.1
  makes that a tested guarantee). Whether Art. 50(2) machine-readable marking applies to this channel as a provider is
  the owner's call; if it does, the marking has to be added outside the factory.
