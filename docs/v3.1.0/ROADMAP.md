# v3.1.0 roadmap — analytics and feedback loop

**Status:** draft. It was written before implementation, 2026-10-18. **Base:** HEAD `3ffd0f1` + the approved, uncommitted
analytics diff (see AUDIT.md §1). **Version:** 3.0.1 → **3.1.0**. This is a minor version: it adds features and
keeps every stage contract.

**Goal.** Historical YouTube performance changes the next batch's topic, hook and script decisions. The change is
bounded and explainable, it records which evidence influenced which video, and its outcome is measured afterwards.

## Pillars, work items, dependencies

### P1 — Canonical architecture and data integrity
| id | work item | depends on | acceptance |
|---|---|---|---|
| P1.1 | `docs/v3.1.0/ARCHITECTURE.md`: source of truth (Windows `factory.db`), role of every store, data flow, recovery and rollback | audit | reviewed against AUDIT.md §2 |
| P1.2 | `content-database/scripts/reconcile.py plan|apply`: cloud run folders or a cloud dump → canonical DB. Rows are classified insert / identical / conflict by primary key (run_id is the identity; a generic `v01` is never joined across runs). It never runs `INSERT OR REPLACE`. Every run folder is validated (state DONE, packaged final.mp4 hash = recorded hash). `apply` takes a backup, writes inserts only in one transaction, re-verifies and writes a reconciliation report | P1.1 | T-REC-* tests |
| P1.3 | Cloud workers must not establish a competing source: docs + `reconcile` refuses a dump whose rows would overwrite | P1.2 | test conflict → exit 2, no write |

### P2 — Reliable analytics ingestion (audit first, extend only the gaps)
| id | work item | depends on | acceptance |
|---|---|---|---|
| P2.1 | Keep `yt_sync pull` → `ingest_youtube --publications-only` → `ingest_analytics` as three separate steps; document them as the only import path (`cfdb publish` is not used) | audit | docs |
| P2.2 | `learning.py kpis`: per-video KPIs **at a fixed age** from the daily per-video rows of the latest snapshot that covers that age (D1, D3, D7): views, engaged views, engaged share. Lifetime-at-cutoff values (avg view %, avg view duration, retention at 3 s, subscribers per 1 000 views) carry their age. Maturity classes `none / early / d3 / d7`. Missing = `null` with a status, never 0 | P2.1 | T-KPI-* |
| P2.3 | Metric definitions and denominators: `docs/v3.1.0/METRICS.md` | — | doc |

### P3 — Analysis that changes future videos
| id | work item | depends on | acceptance |
|---|---|---|---|
| P3.1 | `learning.py attributes`: creative attributes per run, read from the run's own files with source and hash. Opening form, curiosity mechanism, hook words and spoken seconds, first-payoff time, beat roles and count, has-setup, scene count and density, duration, format, title form, CTA beat, topic category (only where an ideas file gave one), learning reference | — | T-ATTR-* |
| P3.2 | `learning.py analyze`: group comparisons on mature-enough videos; shrinkage toward the channel mean; bootstrap interval; confidence `insufficient/low/medium/high` from n and the interval; correlation wording only; findings, evidence, next experiment → `learning_summary.json` (`cf-learning/1`) + `LEARNING_REPORT.md` | P2.2, P3.1 | T-LRN-* |
| P3.3 | Directives in the summary: bounded priors (low ±5 %, medium ±10 %, high ±15 %; none below n=3 per group) for topic category, format, opening form and curiosity mechanism; written guidance for hooks and scripts; the hypothesis to test | P3.2 | T-LRN-bounds |
| P3.4 | **Consumers:** `idea_engine.py` reads the latest summary (auto: `$CF_LEARNING` or `data/learning/latest.json`; `--learning`, `--no-learning`). Category/format priors multiply the score, MMR diversity is kept, and the influence is recorded in ranking/selected/manifest. `factory.py init --learning` copies the summary into the run, records it in `run.json` and adds the hook/script guidance to the constraints. `hook_engine.py select` adds a bounded bonus among **passing** candidates (it can never make a failing one selectable), checks that the candidate set covers the preferred and the tested forms (HOOK.LEARNING_COVERAGE, minor), and records `learning_influence` in selected_hook.json and in result metrics | P3.3 | T-LOOP-* |
| P3.5 | After publication: `analyze` reads each run's learning reference and reports, per hypothesis, the videos made under it and their result vs. the rest | P3.4 | T-LRN-hypothesis |

### P4 — End-to-end quality and release readiness
| id | work item | acceptance |
|---|---|---|
| P4.1 | Tests: schema, ingestion idempotency (duplicate snapshot import), conflicting mapping, delayed analytics, legacy videos, API failure in a snapshot, maturity, comparison, bounds, feedback loop (two different summaries → two different decisions in idea_engine **and** hook_engine), no-learning = old behaviour, reconcile | all pass on Linux; the Windows run is listed separately |
| P4.2 | Historical validation on a **disposable copy** of the canonical DB with the two real snapshots: publications-only + analytics ingest → attributes → analyze → idea_engine select on a real ideas file with vs. without learning → hook selection on a real run's candidates | `docs/v3.1.0/VALIDATION.md` names files, rows, metrics and decisions |
| P4.3 | Regression: the existing suites (analytics, database, yt_sync, idea_engine, experiment, video count, stage order, phase 2 hooks, factory review) | no new failure |
| P4.4 | Windows sync proposal (Phase 5): exact DB changes, counts, conflicts, backup, rollback; **no write before approval** | `docs/v3.1.0/WINDOWS_SYNC_PROPOSAL.md` |
| P4.5 | Docs: SKILL.md (content-analytics, content-factory), CHANGELOG, VERSION 3.1.0, IMPLEMENTATION_REPORT.md | reviewed |

## Mandatory release scope vs. later
**Mandatory for 3.1.0:** P1.1–P1.3, P2.1–P2.3, P3.1–P3.5, P4.1–P4.5.

**Later, not in 3.1.0:**
- Studio CSV import for "Stayed to watch";
- automatic scheduled `yt_sync` pulls;
- TikTok and Instagram;
- LLM-based attribute classification;
- visual-change rate measured from rendered frames;
- `script_select` scoring by learning (3.1.0 gives the script writer guidance only);
- a learned title model.

## Release blockers
1. The owner's approval of the production DB writes (8 publications, `yt_*` tables, reconciliation of batch 20261017).
2. The tests on Windows (only the owner's machine can run them with the real OAuth token and paths).
3. The canonical version and cleanup scope are approved before any tag or GitHub release.

## Exclusions
- No change to the production DB, `memory/dump.json` or YouTube data without approval.
- No commit, push, tag or release.
- No deletion of any media, asset, backup or historical file.
- No change to research, voice, render, QA or packaging gates. Experiment specs are not touched.
- No publishing.

## Statistical policy (fixed before seeing results)
- **Primary comparison metric:** engaged-view share at D3 (`engagedViews_D3 / views_D3`, API proxy for "viewed vs.
  swiped away"), on videos with ≥3 Analytics days.
- **Secondary metrics:**
  - views at D3;
  - avg view % (lifetime at cutoff; age shown);
  - retention at 3 s.
- **Guardrail:** avg view %.
- A group needs n≥3 to be reported with an effect and n≥3 on each side to produce any directive.
- *Amended during implementation (2026-10-18, before release):* a directive also needs the 80 % interval to exclude 0.
  With the first rule, a +0.6 pp effect with an interval of −3.3…+7.7 pp acted as a tie-breaker and moved 6 of the 10
  replayed hook choices onto one mechanism. That is overfitting to noise and loses the diversity the brief asks for
  (VALIDATION.md §3).
- Effect = shrunk difference of means (prior strength k=5 toward the channel mean).
- Interval = 2 000 deterministic bootstrap resamples, 80 %.
- **Confidence levels:**
  - **low:** interval overlaps 0, or either side has n<6;
  - **medium:** interval excludes 0 and both sides n≥6;
  - **high:** medium, both sides n≥10, and the same sign in the previous snapshot.
- Correlation wording only. One video never makes a finding.
