# v3.2.0 — long-form specification (P3)

**Written 2026-10-19.** This is the design for the first non-short format. It records the niche (from the channel's own
data), the exact pipeline changes, and the decisions that were made *before* measuring, so the result can be judged
honestly.

## 1. The niche, derived from the channel's data — not invented

Every one of the 36 runs in `memory/dump.json` is an everyday-science explainer in the form **"Why does X?"** or
**"How does X?"**:

| domain | examples from the channel |
|---|---|
| physics / everyday | metal feels colder than wood, glass transparent, straw looks snapped, soap bubbles, soda fizz, ice cubes crack, buttered toast lands butter-side down |
| biology / body | yawning is contagious, octopus blue blood, knuckles crack, brain freeze, fingers wrinkle, onions make you cry, geckos climb, cats' eyes glow |
| perception | faces in clouds, mirror "reverses", your voice on a recording, wetness without sensors, Moon looks bigger |
| astronomy / earth | stars twinkle, ocean blue, Sun is white not yellow, V-shaped flocks, flamingos, leap years, night sky dark |

**Long-form niche = the same identity, only deeper.** Not a new audience; the existing followers are the seed audience,
and a long-form video is the natural "more" behind a short they liked. Working name of the format:
**"The everyday-science deep-dive"**.

## 2. The format

- **Length:** 3–8 minutes (target 5). Duration window `--min-s 180 --max-s 480`.
- **Aspect:** **portrait 9:16, 1080×1920 — for the first version only.** The doodle engine, renderer, subtitles and QA
  all hardcode 1080×1920, and doodle scenes are authored with `viewBox="0 0 1080 1920"`. Re-authoring to 16:9 touches
  `render_video.py`, `doodle_engine.py`, `doodle_lib.py`, `subtitles.py`, `qa_video.py` **and every scene's geometry** —
  too much risk to answer the only question that matters now: *does a 3–8 minute version of this content hold attention
  and earn watch time?* 16:9 is deferred to v3.3, once long-form has proven itself.
- **Structure (beats):** cold open (a surprising claim, ≤ 20 s) → 3–5 chapters, each answering a sub-question that a
  short would have answered in one line → a short recap → a soft CTA. Chapters get a title card.
- **Visuals / voice / music:** unchanged — the existing doodle engine, Kokoro voices, seeded procedural music bed. This
  keeps provenance, licences and QA identical to the shorts.
- **Metadata:** real description (not a one-liner), chapter timestamps, an end screen. `references/platform-policies.md`
  gains a long-form section (below).

## 3. Pipeline changes required (exact)

| # | file | change | why |
|---|---|---|---|
| 1 | `video-quality-assurance/scripts/qa_video.py` | `PLATFORM_MAX_S = 180.0` → read the run brief's `max_s` (or a `--video-kind short\|long` flag) instead of a constant | the QA gate currently rejects anything over 180 s |
| 2 | `content-factory/scripts/factory.py` | `init` accepts a long window (`--min-s 180 --max-s 480`) and records `video_kind: "long"` in the brief; the HOOK gate's first-30-s budget applies instead of the 3-s budget for long runs | the hook/CTA budgets are short-tuned |
| 3 | `short-form-script/scripts/cta.py` | ~~add a long-form CTA limit set~~ — **cancelled, see §4b**; the 2.8 s speech cap is correct for long-form too (write a ~7-word CTA) | the cap is the speech budget, not a share of runtime; scaling it would produce a rambling outro |
| 4 | `content-factory/references/platform-policies.md` | long-form section: portrait long-form caveat, chapter markers, description length, end screen, the same AI-label rules | policy is short-only today; it even says "hard ceiling 180 s" |
| 5 | `video-quality-assurance/references/review-rubric.md` | long-form review variant: chapter presence, pacing over 30 s windows, no dead air, hook-within-20-s | the short rubric does not cover these |
| 6 | `content-analytics/scripts/learning.py` | long-form gets its **own** metric window (D7 primary), fixed before the first result is seen | 5–8 min videos accumulate watch time slower than shorts; mixing them would bias the shorts' D3 metric |

Items 1–3 are code; 4–5 are docs; 6 is the statistics guard.

## 4. Pre-registered measurement (fixed before we see the result)

- **Primary metric for long-form:** engaged-view share at **D7** (not D3 — a 5-min video's cohort matures slower).
- **Compare like with like:** the long-form videos form their own group; they are **not** pooled with the shorts in the
  D3 comparison. `learning.py` records `video_kind` as an attribute so the split happens automatically.
- **Success definition (before measuring):** a long-form video "works" if its D7 engaged share is **at or above the
  channel's short-form median** for the same maturity class, and (secondary) it is **monetisable** — i.e. YouTube
  reports it as eligible for the Partner Program once the channel meets the threshold. If it fails, the next iteration
  changes the format (chapter pacing first, then 16:9), not the niche.
- **No re-tuning after seeing:** the first three long-form videos are the sample; the rule above decides.

## 4b. What differed in practice (recorded while producing the first long-form, 2026-10-20)

Written after the first long-form went through RESEARCH → SCRIPT at `--min-s 180 --max-s 480`, before it shipped. Three
findings, all recorded so the next long-form is cheaper and so the design above is not mistaken for what happened:

1. **The CTA budget does NOT scale with runtime.** `cta.py` caps a spoken CTA at `min(2.8 s, 12 % of runtime)`. For a
   5-minute video 12 % is ~36 s, so the binding limit is the flat **2.8 s** — every long-form CTA must stay around
   **7 words**, exactly like a short. Design item 3 ("add a long-form limit set") is therefore *not* needed: leave the
   cap alone and write a 7-word CTA. (The first attempt used a 6.2 s CTA and failed `CTA.DURATION`.)
2. **Sentence-length rules are not relaxed for long-form.** The SCRIPT and video reviewers still require average ≤16
   words/sentence, every sentence ≤24 words, and at least one ≤6-word line. The first long-form draft averaged 14–16
   words with 27–29-word sentences and failed `SCRIPT.SELECTED` on `message_clarity`/`pacing_retention`. The fix was to
   write shorter sentences, **not** to change the thresholds. A 3-minute video is not a licence for long sentences.
3. **Chapters/title cards were not implemented in the first long-form.** The script uses the existing beat roles
   (`hook → setup → value → twist → payoff → cta → loop`) repeated across more beats, not a chapter structure with title
   cards. That is a deliberate deferral: prove the length works before adding chapter furniture. The stated structure in
   §2 is the target, not the first artefact.
4. **The storyboard scales linearly with beats, and the composition gates bite.** A 3-minute variant with 25 beats
   needs 25 doodle scenes (one per beat) just to clear `VIS.VISUAL_VARIETY` (`need = ceil(words / 2.8 / 7)` distinct
   visuals). At that count the Phase 3 composition gates become the real work: `VIS.LAYOUT_REPEAT` (no layout more than
   twice in a row) and `VIS.SUBJECT_REPEAT` (no main subject more than twice in a row, and ≤50 % share) both failed on
   the first pass. Design the 25 scenes *as a sequence of layouts and subjects*, not scene by scene, or expect a second
   pass. Also: labels whose baseline sits below ~y=1000 collide with the caption band (y 1060–1360) — keep labels above
   ~y=1000 in every scene.
5. **The duration estimator is ~14 % optimistic for `af_heart` — size long scripts against the REAL rate.** `estimate.py`
   is calibrated on `am_michael`; for `af_heart` the estimator predicted 180.8 s for a script the TTS actually spoke in
   **158.4 s** (measured rate **2.948 words/s**, not the ~2.6 the estimator assumes). The SCRIPT gate passed on the
   estimate; only the AUDIO gate (`AUDIO.DURATION_IN_RANGE`) caught it and routed back to SCRIPT with `lengthen`. So the
   long-form SCRIPT↔AUDIO loop is real: a script that passes SCRIPT on the estimate can still fail AUDIO. When a long
   script is written, size it with `words / 2.95` s, not with `estimate_script` — and leave ≥10 s of headroom above
   `min_s`. (Fixed here by lengthening longB 467 → 550 words: ~187 s real.)

## 5. Cost and risk

| risk | mitigation |
|---|---|
| A 6-min doodle video may be monotonous | chapters + title cards + varied camera punch-ins; measure pacing in the QA rubric |
| Render time grows (~3× real time, so ~20 min per 6-min video) → may exceed `idea_engine --run-timeout-min 180` | raise the timeout for long runs; render on the owner's machine or a worker with time budget |
| Portrait long-form is unusual on YouTube | accepted for v1 as a deliberate test; 16:9 is v3.3 |
| The first long-form may simply not work | that is a valid, valuable result — it tells us whether to invest in 16:9 and b-roll, or to stay short |

## 6. What this is NOT

- Not 16:9 (deferred), not b-roll (deferred), not a new visual engine.
- Not a change to any short-form gate — long-form is an additive variant.
- Not automatic publishing; the owner publishes.
