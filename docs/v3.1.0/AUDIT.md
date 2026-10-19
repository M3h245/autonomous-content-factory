# v3.1.0 — Phase 1 audit (read-only) · 2026-10-18

Everything below was observed on 2026-10-18 between 00:00 and 00:40 UTC. Production files were read, not changed.
The database was inspected through a byte-identical copy (`sha256 df3f6be7…` for both the original and the copy).

## 1. Canonical project and version

| item | observed |
|---|---|
| Project root | `D:\autonomous-content-factory` (the Desktop copy is not mounted and was not used) |
| Git | branch `main`, `origin` = `github.com/M3h245/autonomous-content-factory`, HEAD `3ffd0f1` (2026-10-16), **1 commit ahead of origin**, not pushed |
| Last tag | `v3.0.0`. Later work (v3.0.1, Idea Engine 1.0, experiment layer 1.0–1.2.1, video count) is committed but untagged |
| `skills/content-factory/VERSION` | `3.0.1` |
| Uncommitted, modified | `memory/dump.json`, `content-analytics/{SKILL.md, analytics.py, ingest_youtube.py}`, `content-database/{SKILL.md, cfdb.py}`, `tools/youtube_sync/{README.md, yt_sync.py}`. This is the approved combined diff A/B/C1/C2 of 2026-10-17 plus the 2026-10-17 dump export |
| Uncommitted, new | `content-analytics/scripts/{ingest_analytics.py, legacy_channel.py}` and their tests, `content-database/tests/`, `tools/youtube_sync/test_yt_sync.py`, `analytics/`, `.agents/`, 13 `checkpoints/*` folders, superseded experiment specs |
| Installed skills | `.claude/skills/` also reports VERSION 3.0.1, but **11 files differ** from `skills/`, so it is stale |

**Conclusion.** The canonical code is the **D: working tree** (HEAD `3ffd0f1` plus the uncommitted, approved analytics changes).
The cloud copies (`/home/claude/acf`, `cloud-runs-20261016`) are working copies, not sources of truth. The next version
number is **3.1.0**: it is a minor version because it adds features (learning and feedback, reconciliation) without
breaking the stage contracts.

## 2. Data stores and their roles

| store | role (observed) | status |
|---|---|---|
| `C:\Users\M3H245\content-factory\runs\factory.db` | **canonical production database** | 18 runs, 18 ideas, 18 videos, 204 assets, 126 stage results, **10 publications, 0 metrics, 0 weights**, **no `yt_*` tables** |
| `memory/dump.json` (working tree) | JSON export of factory.db (`exported_at 2026-10-17T11:22:50Z`) | same counts as the DB. HEAD still has the 2026-10-07 export (8 runs) |
| `runs/factory.cloud-snapshot-20261016-1257.db`, `factory.db.bak-*` (2), `runs/backup-20261010-0030/`, `memory/backup-20261010-0030/` | backups and old cloud snapshot | not canonical. **Kept**, as the brief requires (no deletion during discovery) |
| `checkpoints/v3.0.0/memory-dump.json`, `skills/content-factory/tests/fixtures/memory_dump_v3.0.0.json` | frozen test fixtures | read only by tests |
| `data/analytics/20261017-002712/snapshot.json` | yt_sync snapshot (pulled 2026-10-16 22:27Z, Analytics cutoff **2026-10-14**) | in the repo |
| `%TEMP%\cf_postsched_20261017\snap_20261018-000100\…\snapshot.json` | yt_sync snapshot (pulled 2026-10-18 00:01Z, cutoff **2026-10-15**) | outside the repo |
| `analytics/2026-10-16/*` | earlier vidIQ-era exports and dry-run reports | historical evidence; not ingestible (ingest_analytics refuses vidIQ JSON) |
| Run folders (creative evidence) | 10 runs under `batches/20261007-234143-af248f8d`, `batches/20261009-113024-9de025b0`; 8 runs under `runs/cloud-runs-20261016` | all 18 published factory runs have hook, script, timing, storyboard and package files |
| `batches/20261017-111912-debac568` (10 runs) | produced in the cloud on 2026-10-17. The deliverables are in `outputs/2026-10-18-22` | the **PC copy of the run state is stale** (RESEARCH). The full state exists only in the cloud working copy. **This is the concrete case that Pillar 1's sync path must solve** |

**Found later in Phase 4: memory gap.** git HEAD's `memory/dump.json` (2026-10-07) holds 8 runs from 2026-10-04…07
that the canonical DB does not have. The 2026-10-17 export overwrote the working-tree dump without them. The
topic-repetition memory therefore forgot those topics, and batch 20261017 repeated two of them (fingers, onions).
They were unpublished, so the repeat is in memory only. The proposed fix is W0 in WINDOWS_SYNC_PROPOSAL.md.

## 3. Analytics code (existing, before 3.1.0)

| component | what it does | gap for the brief |
|---|---|---|
| `tools/youtube_sync/yt_sync.py` | read-only OAuth pull. Collects video metadata (privacy, publishAt, publishedAt, fileDetails) and per-video Analytics: totals, **daily views / engagedViews / likes / subscribersGained**, retention curve (100 points), traffic sources | none blocking. Studio's "Stayed to watch" is **not available from any API**; `engagedViews / views` is the documented proxy |
| `ingest_youtube.py --publications-only` | evidence-based run↔video linking (uploaded file = output file = run hash; owner confirmation), public-time check, `held_not_public`, legacy guard, insert-only, idempotent, backup on `--apply` | none. This is the **safe import path** that replaces `cfdb.py publish` |
| `ingest_analytics.py` | stores snapshots as immutable `yt_snapshots / yt_videos / yt_observations` with per-value status (`ok / missing / not_yet_processed / not_applicable / …`). It never writes zeros for missing data | none for storage. **Nothing reads these tables yet** |
| `analytics.py analyze` | CSV-export KPIs, feature shrinkage, bounded weights `format:* / pillar:*` | works only on Studio CSV exports, not on the API snapshots. No age normalisation, no maturity. Its weights are read only by `select_ideas.py` (factory SELECTION) |
| `cfdb.py publish` | operator-supplied publication | format check only. **Not used** in 3.1.0's import path (see the risk below) |
| `cfdb.py ingest-run` | ingest a packaged run | `INSERT OR REPLACE`: a second ingest from another machine **silently overwrites** rows. There is no conflict detection, which is a Pillar 1 gap |

`cfdb.py publish` risk (from the brief): the current implementation takes `--run-id` explicitly and inserts only, so it
does not pick "the latest run". It does, however, accept any time the operator gives it. 3.1.0 therefore uses only
`ingest_youtube.py --publications-only`.

## 4. Does analysis reach generation today?

| consumer | reads learning? |
|---|---|
| `select_ideas.py select` (factory SELECTION) | yes, `weights.json` `format:` / `pillar:` multipliers. **But the weights table is empty**, so the effect is nil |
| `idea_engine.py` (the batch path actually used for every batch since 2026-10-07) | **no**: fixed `WEIGHTS` and `QUALITY_FLOOR` |
| `hook_engine.py select` (HOOK v2) | **no** |
| `script_select.py` | **no** |
| `experiment.py` | records experiment arms and reads snapshots for its own experiments. It does not feed defaults |

**Conclusion.** The loop is **open**. No historical performance currently changes any topic, hook or script decision.

## 5. The 22 channel videos (snapshot 2026-10-18)

- **4 legacy channel videos** (`KHutHAMv2_A, cFwkqgRnV9I, QqI7w_BZaWE, aRJAjjHVx9g`, 2023). Labelled `legacy_channel`
  and never linked.
- **18 factory videos.** All 18 are mapped by `uploaded_file` evidence. 10 already have publication rows; 8 are
  `insert` in the dry run (2026-10-14…17); **0 conflicts, 0 unmapped, 0 held_not_public**.
- **Maturity at the Analytics cutoff 2026-10-15 (Pacific):**
  - 2026-10-09…10 (4 videos): 6–7 days of data;
  - 2026-10-11…13 (6 videos): 3–5 days;
  - 2026-10-14…15 (4 videos): 1–2 days;
  - 2026-10-16…17 (4 videos): **no Analytics yet**. Analytics totals are `null`, not 0. Only the public view counter exists.
- Ranges over the 14 videos with Analytics:
  - engaged-view share (`engagedViews / views`): **0.18–0.52**;
  - average view percentage: **42.5–126.6 %** (Shorts can exceed 100 % with loops);
  - subscribers gained: 0–2 per video.

## 6. Creative attributes available (inspected, not assumed)

The following were inspected in every one of the 18 run folders:

- `selected_hook.json`: spoken line, `curiosity_mechanism` (8 types observed), on-screen text, first-frame subject.
- `script.json`: beats with roles `hook / setup / value / twist / payoff / loop`, and title options.
- `audio/timing.json`: duration and word timings.
- `visual/storyboard.json`: 6–8 scenes.
- `package_selection.json`: the chosen title.
- `selection.json`: format (`explainer / myth-bust`).

Not available from the files:

- An inspected visual-change rate inside scenes (only scene count and duration).
- A CTA flag beyond beat roles. No `cta` beat appears in the 18 runs.
- Studio-only metrics.

## 7. Baseline tests (cloud copy of the D: tree, Linux, Python 3.13)

| test | result |
|---|---|
| content-analytics test_analytics / test_ingest_analytics / test_ingest_youtube | OK |
| content-database test_cfdb_export_import / test_cfdb_publish | OK |
| tools/youtube_sync test_yt_sync | OK |
| content-factory test_cf_common_identity, test_stage_order, test_video_count, test_phase2_hooks (10), test_factory_review (2) | OK |
| content-factory test_idea_engine (31), test_experiment (28, 1 skipped) | OK (they need the repo's `fixtures/` and `memory/`) |

Windows verification of these tests was **not** run in this phase.

## 8. Missing permissions, data or implementation

1. There are no per-video Studio-only metrics (Stayed to watch, Shown in feed). Use the API proxy and document it.
2. The canonical DB has no `yt_*` tables and 8 publications are still unwritten. **Both need owner approval** (Phase 5).
3. There is no learning layer, and no consumer of learning in `idea_engine` or the hook and script engines.
4. There is no conflict-safe cloud→Windows reconciliation. The batch 20261017 run state is cloud-only.
5. The sample is small: 4 videos with ≥6 days of data, 14 with any Analytics. All findings will be low confidence.
