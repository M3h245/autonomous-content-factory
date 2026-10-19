# v3.1.0 — Phase 4: historical analysis and feedback-loop validation (2026-10-18)

All runs below used **disposable copies**. The canonical `factory.db` (sha256 `df3f6be7…`) was only read and copied,
and was byte-identical before and after.

## 1. Data used

| input | identity |
|---|---|
| canonical DB copy | `factory.ro-copy.db`, sha256 `df3f6be78e998ad9…` (18 runs, 10 publications, 0 metrics) |
| snapshot A | `data/analytics/20261017-002712/snapshot.json`, sha256 `6df0d2b5…`, pulled 2026-10-16 22:27Z, cutoff 2026-10-14 PT |
| snapshot B | `%TEMP%\cf_postsched_20261017\snap_20261018-000100\20261018-020127\snapshot.json`, sha256 `c87bbf95…`, pulled 2026-10-18 00:01Z, cutoff 2026-10-15 PT |
| run evidence | 18 published runs: `batches/20261007-234143-af248f8d` (5), `batches/20261009-113024-9de025b0` (5), `runs/cloud-runs-20261016` (8). JSON files only, 779 files |
| categories | `batches/*/manifest.json` (author-assigned; available for 5 of the 18) |
| cloud batch | `batches/20261017-111912-debac568` (10 packaged runs, cloud copy; JSON + `package/*/final.mp4`) |

## 2. Ingestion on the disposable copy (on the PC's Linux VM, D: code)

| step | result |
|---|---|
| `ingest_youtube --publications-only --apply`, run 1 | insert **8**, unchanged 0, conflict 0, legacy_channel 4, held_not_public 0 (only the outputs of 2026-10-14…17 and `cloud-runs-20261016` were scanned, so the 10 older ids show as unmapped, and their existing rows are untouched) |
| the same command, run 2 | insert **0**, unchanged **8**, conflict 0. Idempotent |
| the 8 inserted rows vs. the Windows dry run of 2026-10-18 00:01Z | **identical** (run_id and published_at for all 8) |
| `ingest_analytics --apply` snapshot A / snapshot B / snapshot B again | 3 992 obs (insert) / 4 592 obs (insert) / `unchanged (snapshot already imported)` |
| result | publications 18; yt_snapshots 2, yt_videos 44, yt_observations 8 584, yt_metric_defs 15 |

## 3. Analysis (`learning.py attributes` + `analyze`)

- **Attributes:** 18 / 18 videos, 0 gaps. The category is known for 5 of them.
- **KPIs:** maturity is d7 for 2 videos, d3 for 8, early for 4 and none for 4. **10** videos have the primary metric
  (D3 engaged share). The 4 videos from 10-16…17 have **NULL** values (no Analytics rows yet), not zeros.
- **Summary:** `L-2026-10-15-dd8c1cdcc0` (sha256 `264c764a…`). Overall confidence **low**.

**Findings (correlation only):**
- **Appears to work (low confidence).** Scene density ≥2.5 scenes per 10 s: D3 engaged share 43.5 % vs 30.2 %.
  n=3 vs 7, 80 % interval +7.3…+19.4 pp, guardrail +22.4 pp.
  - **Confounded:** the 3 dense videos (`jmBHg0foZpk`, `pnv9BCRE5uA`, `gA9bRm4L2zs`) are also the 3 shortest
    (28–31 s), and none has a setup beat.
- **Unclear: the guardrail fails.**
  - Misconception-reversal hooks: +9.0 pp engaged share, but avg view % −8.9 pp.
  - No setup beat: +11.8 pp, but avg view % −7.8 pp.
- **Unclear: the interval includes zero.** Surprising-claim hooks, explainer vs. myth-bust, statement titles and the
  21:00Z slot.
- **Under-powered (n<3 on one side).**
  - Opening form: only 2 question openers have D3 data.
  - Category: 1 video per category.
  - Duration and first-explanation time: every mature video is ≥26 s and explains after 4 s, so there is no
    contrast.

**Directives the next batch receives:**
- topic: **none**;
- hook: **none**;
- script: has_setup_beat=yes ×0.971; scene density ≥2.5/10 s ×1.035; scene density <2.5/10 s ×0.977.
- The script directives reach the writer as guidance. `script_select` scoring is unchanged in 3.1.0.

**Next hypothesis:** `H-scene_density_bucket-2.5_per_10s_or_more`. The owner's pre-registered `H1-2026W43-opening-form`
is listed under registered experiments and is not replaced.

## 4. Downstream decisions on real inputs

| consumer | input | without learning | with `L-2026-10-15-dd8c1cdcc0` | changed? |
|---|---|---|---|---|
| `idea_engine select --count 5` | `input/ideas_batch_02.json` vs the copy DB | night sky, room spinning, snowflakes, rubber band, ghost colour | the same 5 | **no**: no category evidence (each multiplier ×1.000, with the reason recorded in ranking.json) |
| factory SELECTION (`select_ideas`) | the 10 runs of batch 20261017, real ideas | i1 in all 10 | i1 in all 10 | **no**: there is no format directive |
| `factory.py init --learning` | new topic "Why do cats always land on their feet?" | 0 learning constraints | **3 script-guidance constraints** in run.json; `learning` reference; `learning.json` copied | **yes**: the script writer's brief changes |
| `hook_engine select --learning` | real hook sets (candidates + SVG) of the 10 runs of batch 20261017, re-rendered and re-reviewed | h5 h3 h2 h1 h2 h4 h3 h3 h5 h2 | identical | **no**: there is no hook directive, and every bonus is 0.000 (recorded in `learning_influence`) |

### Why the hook result is "no change" (policy amendment)
The first implementation issued directives whenever n≥3 per side, including those with an interval spanning zero.
With that rule, the real summary gave surprising-claim hooks a ×1.006 prior. The effect was +0.6 pp, with an interval
of −3.3…+7.7 pp. Because 8 of the 10 real hook sets had several passing candidates tied at review total 14, that
+0.06-point tie-breaker changed **5 of the 9** completed replays and selected `surprising_claim` in 7 of 9 runs, against
2 of 9 without learning. That is overfitting to noise, and it removes the diversity needed to compare strategies. The
rule now also requires the 80 % interval to exclude zero (ROADMAP amendment; test
`test_unestablished_direction_makes_no_directive`). Both replays are kept as evidence in
`%TEMP%\cf_v310_work\evidence\` (`hook_replay_v1policy.log`, `hook_replay_v2.log`).

### That different findings do produce different decisions
`content-factory/tests/test_learning_loop.py` shows it with controlled summaries on the real engines:
- **idea_engine:** a "space" vs. a "nature" prior picks different topics, at both the unit level and the CLI level on
  the 50-candidate fixture file.
- **hook_engine:** two real-rendered candidates tie at review total 14. A statement prior selects `hs` and a question
  prior selects `hq`. A favoured candidate that **fails** the review is never selected.
- **factory init:** the summary, its guidance and the format priors land in the run.

## 5. Cloud → Windows reconciliation (batch 20261017)

| where | result |
|---|---|
| cloud copy of the canonical DB | plan: insert 220 (10 runs, 30 ideas, 10 videos, 100 assets, 70 stage_results), identical 0, conflict 0; apply: verified; a re-plan gives 0 insert / 220 identical; a second apply writes nothing |
| PC (Linux VM, D: code, copy of the canonical DB with the same sha256) from the 10 transferred bundles | SHA256SUMS 10/10 OK. Plan: insert 220, conflict 0, 0 invalid runs. `v310_sync.py W3` dry run, and `--apply` on a copy: inserted 220, verified |
| after W1+W2+W3 (preview on copies) | runs 28, ideas 48, videos 28, assets 304, stage_results 196, publications 18, metrics 0, weights 0, yt_snapshots 2, yt_videos 44, yt_observations 8 584, yt_metric_defs 15 |

## 6. Limits of this validation
- The Windows-native runs of the new tests and of `v310_sync.py` have **not** been executed. Every run above was on
  Linux (the cloud container with Python 3.13, or the PC's Linux VM with Python 3.10).
- `v310_sync.py W1` was not dry-run through the wrapper on the VM, because hashing every output file over the
  Windows mount exceeds the 3-minute limit. Its underlying command produced the expected 8/10/0 in the 2026-10-18
  Windows dry run and on the disposable copy.
- No new video was produced end to end with a learning summary. The generation decision (the run brief, and the HOOK
  re-ranking on real candidates) was validated. The media chain is covered by the regression suites (smoke_v2,
  phase 3/4/5, bad videos).
