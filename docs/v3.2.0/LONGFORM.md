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
| 3 | `short-form-script/scripts/cta.py` | a long-form variant: `short_video_s` gate already allows a spoken CTA at ≥20 s, but the `max_share_of_runtime` of 12 % is short-tuned — add a long-form limit set | a 6-min video's CTA budget must scale sensibly |
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
