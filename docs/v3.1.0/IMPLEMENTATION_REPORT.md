# v3.1.0 — implementation report (2026-10-18)

**Status: release candidate in the D: working tree.**
- No commit, tag or release.
- The production database, `memory/dump.json` and YouTube data are unchanged. The writes are proposed in
  WINDOWS_SYNC_PROPOSAL.md and await approval.

## What was built (by pillar)

| pillar | delivered | files |
|---|---|---|
| P1 architecture | One source of truth (Windows `factory.db`), the role of every store, writers and evidence rules, cloud→Windows flow, recovery/rollback. Insert-only reconciliation with run validation, conflict detection, stale-plan guard, backup and verification | `docs/v3.1.0/ARCHITECTURE.md`, `content-database/scripts/reconcile.py` (new) |
| P2 ingestion | Existing evidence-based publication import and immutable snapshot store, audited and kept. New: fixed-age KPIs from the daily per-video rows, maturity classes, NULL+status for missing data, lifetime values labelled with their age. Metric definitions and denominators documented | `content-analytics/scripts/learning.py kpis`, `docs/v3.1.0/METRICS.md` |
| P3 analysis → decisions | Creative attributes read from each run's own files (with source hashes). Group comparisons with shrinkage, bootstrap interval, confidence, guardrail; findings / directives / next hypothesis / hypothesis tracking / registered experiments. Shared bounded reader. Consumers: idea_engine (category priors), factory init (guidance into constraints, format priors into SELECTION weights, record in run.json), hook_engine (bounded re-ranking of passing candidates, `learning_influence`, coverage check) | `learning.py`, `learning_apply.py` (new); `idea_engine.py`, `factory.py`, `hook_engine.py` (modified) |
| P4 quality | 27 new tests across three files, the full regression suite, a historical validation on disposable copies, a sync tool with expected-value guards | `test_learning.py` (15), `test_reconcile.py` (5), `test_learning_loop.py` (7); `docs/v3.1.0/VALIDATION.md`; `%TEMP%\cf_v310_work\v310_sync.py` |

## Files changed in `D:\autonomous-content-factory` (uncommitted)

**Modified**
- `skills/content-factory/scripts/factory.py`: init `--learning`; the HOOK gate passes `--learning`.
- `skills/content-factory/scripts/idea_engine.py`: learning resolution, `apply_learning`, records, LEARNING_CHANGED.
- `skills/hook-engineering/scripts/hook_engine.py`: `--learning`, bonus, `learning_influence`, HOOK.LEARNING_COVERAGE.
- `skills/content-factory/tests/test_idea_engine.py`: also clears `CF_LEARNING`.
- `skills/content-factory/{VERSION → 3.1.0, CHANGELOG.md, SKILL.md, PROJECT_STATE.md}`, `PROJECT_STATE.md`.
- `skills/{content-analytics,content-database,hook-engineering}/SKILL.md`.

**Added**
- `skills/content-analytics/scripts/{learning.py, learning_apply.py}` and `tests/test_learning.py`.
- `skills/content-database/scripts/reconcile.py` and `tests/test_reconcile.py`.
- `skills/content-factory/tests/test_learning_loop.py`.
- `docs/v3.1.0/{ROADMAP, AUDIT, ARCHITECTURE, METRICS, VALIDATION, WINDOWS_SYNC_PROPOSAL, IMPLEMENTATION_REPORT}.md`.

**Backups and size**
- The originals of every modified file are in `checkpoints/v3.1.0-pre/backup/`, with `BACKUP_SHA256SUMS.txt`.
- Size: about 0.4 MB of text (1 818 lines of new code and tests). No media added to the repository.
- Original line endings (CRLF) are kept on the modified files.

**Database tables affected:** none in production. On disposable copies: `publications`, `yt_*`, and `runs`, `ideas`,
`videos`, `assets`, `stage_results` (VALIDATION.md).

## Tests actually executed

Linux only: the cloud container (Python 3.13) and the PC's Linux VM (Python 3.10).

Full suite, 2026-10-18, cloud container with Python 3.13, on the final code:

| test | result |
|---|---|
| skills/content-analytics/tests/test_analytics.py | OK |
| skills/content-analytics/tests/test_ingest_analytics.py | OK |
| skills/content-analytics/tests/test_ingest_youtube.py | OK |
| skills/content-analytics/tests/test_learning.py | OK |
| skills/content-database/tests/test_cfdb_export_import.py | OK |
| skills/content-database/tests/test_cfdb_publish.py | OK |
| skills/content-database/tests/test_reconcile.py | OK |
| tools/youtube_sync/test_yt_sync.py | OK |
| test_cf_common_identity | Ran 1 test in 0.002s  OK |
| test_stage_order | Ran 3 tests in 6.273s  OK |
| test_phase0_regressions | Ran 4 tests in 3.215s  OK |
| test_tts_cache | Ran 1 test in 46.881s  OK |
| test_visual_audit | Ran 9 tests in 1.793s  OK |
| test_reviewer | Ran 11 tests in 7.948s  OK |
| test_futile_retry | Ran 4 tests in 18.102s  OK |
| test_phase2_script | Ran 7 tests in 21.970s  OK |
| test_phase3 | Ran 14 tests in 0.615s  OK |
| test_phase35 | Ran 22 tests in 1.309s  OK |
| test_factory_review | Ran 2 tests in 103.529s  OK |
| test_phase2_hooks | Ran 10 tests in 190.319s  OK |
| test_phase4 | Ran 49 tests in 67.103s  OK |
| test_phase5 | Ran 27 tests in 115.975s  FAILED (failures=1) |
| test_final_media_metadata | Ran 8 tests in 10.608s  OK |
| test_idea_engine | Ran 31 tests in 69.996s  OK |
| test_experiment | Ran 28 tests in 11.079s  OK (skipped=1) |
| test_video_count | Ran 13 tests in 9.464s  OK |
| test_learning_loop | Ran 7 tests in 70.685s  OK |
| smoke_v2 | SMOKE TEST PASSED |
| bad_videos A | OK |
| bad_videos B | OK |
| bad_videos C | OK |
| bad_videos D | OK |

**The only failure is `test_phase5 …test_shipped_memory_knows_every_earlier_topic`.**
- It also fails on the unchanged baseline code.
- It reads the live `memory/dump.json`, which lacks the 8 runs of 2026-10-04…07 (the memory gap in AUDIT.md and
  WINDOWS_SYNC_PROPOSAL.md W0).
- It passes once W0 and W5 are applied.

**On the PC's Linux VM** (Python 3.10, the D: files after the copy, with byte-identical hashes): test_learning,
test_reconcile, test_ingest_analytics, test_ingest_youtube and test_cfdb_export_import pass.

**Windows-native:** not run.

## Acceptance criteria

| # | criterion | status |
|---|---|---|
| 1 | repeated ingestion without duplicate or incorrect publications | **met** on copies: the second publication import gave 0 inserts / 8 unchanged; the second snapshot import was unchanged; the 8 rows equal the Windows dry run |
| 2 | missing metrics are unavailable/immature, never 0 | **met**: tests `test_maturity_age_matched_values_and_nulls_not_zeros`, `test_api_error_is_not_a_zero`; on real data, 4 videos have NULL |
| 3 | mappings evidence-based and auditable | **met**: publications only via uploaded-file evidence; attributes carry source hashes; duplicate run folders reported |
| 4 | analysis with findings, evidence, uncertainty, next experiments | **met**: `LEARNING_REPORT.md` / `learning_summary.json` |
| 5 | topic selection and script generation consume the analysis | **met**: idea_engine, factory init (constraints + weights), hook_engine. On real data, today only the script guidance has evidence strong enough to act on (VALIDATION.md §4) |
| 6 | a test shows different findings → different decisions | **met**: `test_learning_loop.py` (topic, CLI batch, hook with real rendering and review) |
| 7 | full representative pipeline still works | **met for the tested scope**: regression suites incl. smoke_v2, phases 3–5, bad videos. No new video was rendered with a summary |
| 8 | production DB unchanged unless approved | **met**: sha256 `df3f6be7…` before and after |
| 9 | documented, validated cloud → Windows path | **met**: ARCHITECTURE.md §3; `reconcile.py` validated in the cloud and on the PC VM; `v310_sync.py W3` dry run and apply on a copy |
| 10 | roadmap, report, tests, risks, release status documented | **met**: this folder |

## Unresolved risks and limits
1. **Memory gap (found in Phase 4).** The canonical DB lacks the 8 runs of 2026-10-04…07, so batch 20261017 repeated two
   unpublished topics (fingers, onions). The fix is W0, insert-only from git HEAD's dump.
2. **Windows-native tests not run.** The OAuth-dependent steps and every `--apply` must run on Windows by the owner.
3. **Small sample.**
   - 10 videos have D3 data; every finding is low confidence.
   - The scene-density finding is confounded with duration and the absence of a setup beat.
4. **The primary metric is an API proxy.** "Stayed to watch" is not available from any API.
5. **The script influence is advisory.** It is guidance in the brief; `script_select` scoring does not yet use priors
   (a later item).
6. **The category is known for only 5 of 18 videos.** Topic priors will stay empty until idea batches keep
   assigning categories and those videos mature.
7. **The `.claude/skills` installed copies are stale.**
8. **The batch 20261017 deliverables on D: carry a C2PA box** added by the file-transfer tool. Their streams are
   identical, and `ingest_youtube`'s fingerprint ignores C2PA boxes.

## Release status and next task
- **Done (2026-10-18/19):** W0–W5 applied to the production database (WINDOWS_SYNC_PROPOSAL.md); the full Windows test
  suite was run (the three pre-existing Windows failures were fixed in v3.1.1); v3.1.0 committed and tagged.
- **Next roadmap task:** repeat `learning.py analyze` after each new snapshot, and automate the loop (v3.2).
  The first hypothesis worth a controlled test is still the owner's H1 (opening form), because the question arm has only
  2 videos with D3 data.
