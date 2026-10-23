# v3.2.0 roadmap — unattended growth loop, and the first long-form format

**Status:** plan, written 2026-10-19 after v3.1.1. **Base:** `main` at the v3.1.1 commit. **Version:** 3.1.1 → **3.2.0**
(a minor version: new capabilities, no stage contract broken, `--no-learning`-style escape hatches kept).

**Goal.** Turn v3.1.0's *infrastructure* for learning into an actual *growth loop*, and add the first non-short format.
Two sentences:
1. The feedback loop runs itself on a schedule (pull → ingest → analyze → steer the next batch), so the owner only
   reviews and publishes.
2. The factory can produce a **long-form** video (3–8 min) in the channel's own niche, because shorts give views and
   followers but do not monetise well — the owner's reason for starting v3.2 with this agent.

**Owner decisions already taken (2026-10-19):**
- The independent QA judge becomes an **agent** (online, can check today's topics, broader reach) rather than a
  local-only model. The owner's words: a local judge limits the factory to the owner's own thinking; the agent can
  check what is trending now.
- Long-form starts in v3.2. **Format:** the agent proposes (see P3); the niche follows the channel's own data (P3.1).
- Version number is not important; correctness and value are.

---

## What v3.1.1 leaves behind (the honest baseline)

Measured on 2026-10-19, from the live data, not from memory:

| fact | evidence |
|---|---|
| The loop is **manual**. | No scheduler/loop script exists (`Get-ChildItem *schedul*,*loop*` → only a test file). Four hand-run steps: `yt_sync pull` → `ingest_youtube` → `ingest_analytics` → `learning.py analyze` → `idea_engine --learning`. |
| The sample is **tiny**. | `data/learning/latest.json`: almost every comparison is `n=1 vs 4`, `n=2 vs 8`, `n=3 vs 7`; confidence `insufficient`/`low` except one `medium`. |
| Steering covers **topic and hook only**. | `learning_apply.py` has no key for `title`, `hashtag`, `caption`, `thumbnail` or `publish time`. `title_form` is *measured* but never *applied*. |
| Publish time is **measured, not chosen**. | `publish_slot_utc 16h vs 21h` is in the summary; nothing acts on it (upload is manual). |
| The first experiment has **not run**. | `next_experiment` is now `H-scene_density_bucket…` (`prepared`, not started). |
| Shorts plateau. | 18 published videos: best `OaHGH2WGTpg` 1 944 views, median ≈ 1 200, several ≈ 3. |

Everything below is chosen to remove exactly these gaps, in the order that makes the next thing meaningful.

---

## Pillars

### P1 — The loop runs itself (highest value)
| id | work item | acceptance |
|---|---|---|
| P1.1 | `skills/content-analytics/scripts/growth_loop.py`: one command that does `yt_sync pull` → `ingest_youtube --publications-only` → `ingest_analytics` → `learning.py attributes\|kpis\|analyze` → writes `data/learning/latest.json`, with a `--dry-run` and a machine-readable `loop_log.json`. Every step keeps its own exit codes; a failed step stops the loop and reports (never a silent partial). | a single command reproduces W1–W4's effect on a disposable copy; each step's output is attributed in `loop_log.json` |
| P1.2 | Scheduling: a Windows Task Scheduler entry (daily) using the `automation-engineering` template, set to run the loop **and then** an ideas-file batch with the fresh `--learning`. Nothing publishes. | a scheduled task file + a `.ps1` that runs headless; verified once by hand |
| P1.3 | A "loop health" summary: last successful pull, snapshot age, videos awaiting D3/D7, how many directives are active. Appended to `LEARNING_REPORT.md`. | one table the owner can read in 10 seconds |

**Out of scope (P1):** unattended **upload**. Publishing stays human (a hard rule since Phase 0). "Scheduled publish" (P2.3)
means the *factory* proposes a slot; the owner still clicks publish.

### P2 — Steering reaches title, caption, hashtags and the publish slot
| id | work item | acceptance |
|---|---|---|
| P2.1 | New `learning_apply` functions: `title_bonus(s, title_form)`, `caption_style(s)`, `hashtag_hints(s)`, `publish_slot(s)`. Same rules as the existing ones — bounded (≤ ±15 %), evidence-only, a level with no evidence returns 1.0 / no hint, every influence recorded. | unit tests: with a summary that has a `title_form` directive, the chosen title option changes; without evidence, nothing changes |
| P2.2 | Consumers: the **PACKAGE** stage (`package_engine.py` title/copy) reads the title/hashtag hints; **SUBTITLES** reads the caption-style hint; the delivery step prints the recommended publish slot. | the influence appears in `package_selection.json` and `metadata.json` / the report |
| P2.3 | `learning.py analyze` starts **emitting** the directives P2.1 needs (it already measures `title_form`; add `caption_style`, `publish_slot_utc`, `hashtag_count`), under the same pre-registered rule (n≥3 per side, 80 % interval excludes 0, guardrail). | a directive appears only when the rule is met; VALIDATION.md gains a section |

### P3 — Long-form: the first ≥3-minute format
| id | work item | acceptance |
|---|---|---|
| P3.1 | **Niche from data.** All 36 runs are "Why does X?" / "How does X?" everyday science (physics, biology, perception, astronomy) — see `memory/dump.json`. Long-form keeps that identity, only deeper: 5–8 min, same visual language. Documented in `docs/v3.2.0/LONGFORM.md` with the topic list it was derived from. | the doc names the 36 topics and the chosen niche |
| P3.2 | **Format decision (made 2026-10-19, test-first):** the first long-form is **portrait 9:16 (1080×1920), 3–8 min**, not 16:9. Reason: the doodle engine, renderer, captions and QA all hardcode 1080×1920 (`render_video.py W,H`, `doodle_engine.py`, `doodle_lib.py`, `subtitles.py`, `qa_video.py`), and doodle scenes are authored with `viewBox="0 0 1080 1920"`. Re-authoring to 16:9 touches 5+ modules and every scene's geometry — too much risk to test *whether long-form is worth it at all*. Portrait long-form answers the learning question (does 3–8 min hold attention and earn watch time?) this week. **16:9 becomes v3.3**, once long-form has proven itself. Structure: cold open (a surprising claim) → 3–5 chapters, each a sub-question the short would have answered in one line → a short recap → a soft CTA. Visuals: the existing doodle engine. Voice: existing Kokoro. Music: existing seeded bed. | `factory.py init --min-s 180 --max-s 480` (no new flag needed if the ceiling is raised); `qa_video.py`'s `PLATFORM_MAX_S` and `references/platform-policies.md`'s "hard ceiling 180 s" gain a `--format`-aware value |
| P3.3 | **Platform policy.** Long-form has different gates: 16:9, longer hook budget (first 30 s), chapter markers, a real description, an end screen. `references/platform-policies.md` gains a long-form section; the QA rubric gains a long-form variant (chapter presence, pacing over 30 s, no dead air). | a reviewed long-form rubric; QA accepts a 6-min fixture |
| P3.4 | **First real long-form video** produced end-to-end and shown to the owner, with the same provenance/QA/captions discipline as the shorts. | one `final.mp4`, 3–8 min, passed QA, in `CF_OUTPUT_DIR` |

**Format proposal detail (P3.2).** Three options were weighed:
- **(A) Same doodle engine, longer** — lowest new work, on-brand, all gates already pass. **Recommended.**
- (B) Voiceover + real stock b-roll — closer to "monetisable" content but needs a new asset pipeline and new licences.
- (C) Avatar/slideshow — a whole new engine; not justified yet.
Start with (A); revisit (B) if long-form (A) earns watch time.

### P4 — The judge is an agent
| id | work item | acceptance |
|---|---|---|
| P4.1 | Keep `reviewer.py`'s packet boundary exactly as it is (it is the reason the judge is independent). Add a first-class `--review-backend agent` that hands the packet to **this** agent (OpenCode) instead of the Anthropic API or a local model. | `review-request.md` → `agent` writes `judgment.json`; the boundary log records it |
| P4.2 | Give the agent, *outside the packet*, a "context brief": today's trending topics in the niche (web search), the channel's own best/worst, and the pre-registered rubric. The packet itself still contains **no creative state** — the context brief is separate and its hash recorded, so independence is provable. | the boundary log shows what the agent saw; a test asserts the packet carries no creative state |
| P4.3 | Make the agent's verdict the production default (replacing "heuristic fallback is fine"); document that a failed agent review is a real fail. | one full run judged by the agent, end to end |

### P5 — Cleanup, speed, and release hygiene
| id | work item | acceptance |
|---|---|---|
| P5.1 | `memory/dump.json` is 5 MB and re-exported every run; move the *working* copy out of git (keep a small shipped snapshot) and document where the live DB lives. | tests still find a memory file; the repo no longer grows 5 MB per commit. **DONE in v3.3** — `memory/dump.json` is git-ignored and `memory/snapshot.json` (195 KB, all runs/ideas/videos/assets) ships; `memory/README.md` documents the live DB (`$CF_DB` / `$CF_RUNS_DIR/factory.db`); `idea_engine` seeds from dump then snapshot; `tools/make_memory_snapshot.py` refreshes it. |
| P5.2 | One `PROJECT_STATE.md` (root or skill, not both nearly identical); the other becomes a pointer. | a single source of truth. **DONE in v3.3** — the root file is canonical and updated; `skills/content-factory/PROJECT_STATE.md` is a 5-line pointer. |
| P5.3 | Windows tests in CI (GitHub Actions `windows-latest`), so the locale/lock class of bug can never return unnoticed. | a green Windows job. **DONE in v3.3** — `.github/workflows/windows-tests.yml` runs the whole suite on `windows-latest` with `tools/run_tests_isolated.py` (which now exits non-zero on any failure/timeout). |
| P5.4 | Tag and release: `v3.1.1` now, `v3.2.0` at the end, each with the skills zip in `checkpoints/`. | tags exist; GitHub releases created. **v3.1.1 is tagged; v3.2.0/v3.3.0 wait for owner approval of the v3.3.0 commit.** |

---

## Order and dependencies

```
P5.4 (tag v3.1.1 now)  ──►  P1.1 ──► P1.2 ──► P1.3
                                   │
                                   ▼
                            P2.3 ──► P2.1 ──► P2.2        (needs fresh directives from the now-automatic loop)
P4.1 ──► P4.2 ──► P4.3                                    (independent of P1; enables unattended runs)
P3.1 ──► P3.2 ──► P3.3 ──► P3.4                           (the long-form track; P3.4 last, needs P4 for review)
P5.1 P5.2 P5.3                                            (alongside, no dependency)
```

**Suggested sequence for the owner's stated priority (long-form monetisation):**
1. P5.4 tag v3.1.1 (safety net) — *done in this session*.
2. P3.1 → P3.2 skeleton (long-form run **works** for one video, gates relaxed to 3–8 min) — a first long-form by the
   end of the first working block.
3. P4 (agent judge) — needed before long-form is trusted.
4. P1 (loop runs itself) — then the loop steers with real data.
5. P2 (steering reaches title/caption/slot) — once P2.3's directives exist.
6. P5.1–P5.3 hygiene alongside.

---

## Statistical policy (unchanged, restated)

The v3.1.0 pre-registered rule stands: primary metric = engaged-view share at D3; a directive needs n≥3 per side, an
80 % interval excluding 0, and the avg-view-% guardrail no worse than 5 pp. Long-form gets its **own** metric window
(D7 primary, because 5–8 min videos accumulate slower) — fixed before the first long-form is measured, not after.

## P6. Thumbnail taste (found while producing the first long-form, 2026-10-20)

Raised by the owner after looking at the live channel: *"some of the thumbnails are really weak — is that checked by
anything, or made at random?"* Answer, from reading the code: **not random, but also not judged.**

- `package_engine.py` builds **3 candidate packages** (P1/P2/P3, different cover strategies) and selects one by score;
  the cover is rendered from a doodle SVG. So it is deterministic and gated — 18 checks: `THUMB.SIZE`,
  `THUMB.HEADLINE_SIZE`, `THUMB.CONTRAST` (measured at the real 168-px shelf size), `THUMB.TEXT_CORE_SAFE`,
  `THUMB.SUBJECT`, `THUMB.SINGLE_SUBJECT`, `THUMB.TEXT_OVERLAP`, `THUMB.WORDS`, `THUMB.NOT_IN_VIDEO`,
  `THUMB.DEPICTS_KNOWN`, `THUMB.CTA`, plus `CLAIM.*` / `CLICKBAIT.*`.
- **But every one of those is mechanical/geometric.** Not one of them asks *"is this cover interesting?"* A cover can
  pass all 18 and still be dull. That is exactly the gap the owner saw. `reviewer.py::score_package` has a
  `thumbnail_readability` dimension and a `thumbnail_coherence` dimension, but both score geometric signal, not taste
  (the reviewer even labels the latter *"a designed cover is a Phase 4 deliverable"*).

- **P6.1 — leftover slow path (bug, do first, small). — DONE in v3.3.** `package_engine.py::render_thumb` used
  `skia.Surface.MakeRaster(ImageInfo...)`, the exact call identified in PERFORMANCE.md as making blits ~50× slower
  than `Surface.MakeRasterN32Premul`. Fixed in v3.3 across all three remaining sites (`package_engine.py`,
  `hook_engine.py`, `doodle_engine.render_still`); `render_frames_png.py` is a throwaway debug harness and stays as
  it is. The rendered covers are byte-equal apart from the documented ±1–3/255 grain rounding.
- **P6.2 — a real cover judge.** Extend the agent judge (P4) to the package stage: render the cover, show it to the
  agent at shelf size **and** full size alongside the title and the video's promise, and score *taste* — one clear
  focal subject, an emotional or curiosity hook in the picture, the text adding what the title does not say, and
  whether it would win a click next to the channel's existing covers. Route a failure back to `PACKAGE` /
  `redesign_cover`. **DONE in v3.3** — `thumbnail_appeal` is a judge-only package dimension (the heuristic returns a
  neutral 3 and says "not judged"; the external judge is authoritative and may raise as well as lower), the package
  review has a `--backend subagent` await flow (`package_review_request.md` → exit 3 → `package_judgment.json`),
  `package_engine select` builds a hashed channel-covers context brief from `factory.db` (`PKG.AWAITING_JUDGMENT`
  blocks selection until the judgment exists), and a low score routes to `PACKAGE` / `redesign_cover`.

Sequencing: P6.1 can go with P5 hygiene now; P6.2 rides on P4 (the agent judge), because it is the same machinery
pointed at a different artifact.

## Exclusions
- No automatic publishing or uploading, ever.
- No deletion of media, assets, backups or history.
- No change to research/voice/render/QA/packaging **gates** for shorts; the long-form track adds a variant, it does
  not weaken the short one.
- Experiment specs are not edited outside a new registered experiment (P3.4 long-form gets its own arm).
