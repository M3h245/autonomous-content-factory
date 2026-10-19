# v3.1.0 — Windows synchronisation proposal (Phase 5) · **applied 2026-10-18/19**

> **Status:** steps W0–W5 were **applied to the production database** on 2026-10-18/19, each with its own approval and
> its dry run matching the expected numbers. The result is: runs 36, ideas 66, videos 36, assets 364, stage_results 240,
> publications 18, yt_snapshots 2, yt_videos 44, yt_observations 8 584, yt_metric_defs 15; `data/learning/latest.json`
> written; `memory/dump.json` re-exported from the 36-run database. The original proposal text below is kept as the
> record of what was planned.

**Target:** `C:\Users\M3H245\content-factory\runs\factory.db`. Current sha256 is `df3f6be78e998ad9…`, with 18 runs,
10 publications, 0 metrics, 0 weights and no `yt_*` tables.

**Tool:** `%TEMP%\cf_v310_work\v310_sync.py`.
- Each step is a dry run unless `--apply` is given.
- `--apply` refuses to run unless the dry run reproduces the expected numbers below exactly.
- Every database write is made by the factory's own tool, which first copies the DB to `factory.db.bak-<stamp>` and
  writes in one transaction.
- Everything is logged to `%TEMP%\cf_v310_work\sync_log.jsonl` with the DB hashes before and after.

Each step needs its **own approval**. They are independent but are meant to run in this order.

| step | what changes | expected | reversible by |
|---|---|---|---|
| **W0** restore lost memory | inserts the 8 runs of 2026-10-04…07 (knuckles, brain freeze, tickle, **fingers wrinkle**, **onions**, leap years, flamingos, Moon) that the canonical DB lacks. Source: git HEAD's `memory/dump.json` (`dump_head_3ffd0f1.json`, sha256 `98ceed9e…`). `reconcile.py --dump`, insert-only | runs +8 · ideas +18 · videos +8 · assets +60 · stage_results +44 = 138 inserts · 0 conflicts | the backup written by reconcile |
| **W1** publications | `publications` +8 rows: `5FWLuP9lc1Y`, `vCuzzYfnt7w`, `tcBDWOrizAE`, `gE8M4hstGX4`, `5tAtz6GpzGI`, `ZujG2hN8718`, `8kuNEkzy2KE`, `oxB07d4YRx8`, each with its verified public `publishedAt` | insert 8 · unchanged 10 · conflict 0 · held_not_public 0 · legacy_channel 4 | the backup written by ingest_youtube |
| **W2** analytics | copies the 2026-10-18 snapshot to `data/analytics/20261018-020127/snapshot.json` (new file). Creates `yt_*` and imports both snapshots | yt_snapshots 2 · yt_videos 44 · yt_observations 8 584 (3 992 + 4 592) · yt_metric_defs 15 | the backups written by ingest_analytics (one per snapshot) |
| **W3** cloud batch 20261017 | unpacks the 10 verified bundles into the **new** folder `runs\cloud-runs-20261017\` (it refuses if the folder exists), then `reconcile.py plan` + `apply` | runs +10 · ideas +30 · videos +10 · assets +100 · stage_results +70 = 220 inserts · 0 conflicts · 0 invalid runs | the backup written by reconcile, and `W3_applied.json` |
| **W4** learning | writes `data/learning/<stamp>/` and **`data/learning/latest.json`**. From then on `idea_engine` and every `factory.py init` it starts use the evidence (bounded, recorded; `--no-learning` to opt out) | the same findings as VALIDATION.md §3; the only directives are 3 script ones | delete `data/learning/latest.json` |
| **W5** dump | `memory/dump.json` ← `cfdb.py export`. The old dump is copied first to `memory/backup-v310-<stamp>/dump.json` | dump counts = DB counts | restore the copied dump |

**Why W0.** The canonical DB has the 18 runs from 2026-10-08 onwards, but not the 8 earlier runs that git HEAD's dump
holds. The 2026-10-17 export then replaced the working-tree dump with the 18-run state. The topic-repetition check
therefore no longer knows those topics: batch 20261017 made **fingers** and **onions** videos that repeat the
unpublished runs of 2026-10-05 and 2026-10-06. Nothing was published twice; the duplicates are in memory only.
`test_phase5 …test_shipped_memory_knows_every_earlier_topic` fails for this reason on both the old and the new code.
W0 dry run + apply was verified on a copy: 138 inserted and verified; afterwards `topic-check` for fingers finds
2026-10-05.

**Database after W0–W3** (previewed on copies): runs 36, ideas 66, videos 36, assets 364, stage_results 240,
publications 18, metrics 0, weights 0, yt_snapshots 2, yt_videos 44, yt_observations 8 584, yt_metric_defs 15.

Without W0 the figures are: runs 28, ideas 48, videos 28, assets 304, stage_results 196,
publications 18, metrics 0, weights 0, yt_snapshots 2, yt_videos 44, yt_observations 8 584, yt_metric_defs 15.

## How the owner runs a step (PowerShell, from any folder)
```
python -B "$env:TEMP\cf_v310_work\v310_sync.py" W1            # dry run: prints the plan and "matches_proposal": true
python -B "$env:TEMP\cf_v310_work\v310_sync.py" W1 --apply    # only after approving W1
```
Then the same for W0, W2, W3, W4 and W5, in the order W0 → W5.

## Rollback
1. Close every factory process.
2. Restore the database: copy the `factory.db.bak-<stamp>` named in that step's log entry over `factory.db`. Use the
   earliest backup to undo several steps.
3. Undo the non-database parts:
   - W2: the snapshot file can stay. It is immutable input, and deleting it is the owner's choice.
   - W3: the `runs\cloud-runs-20261017\` folder can stay. It is evidence, and deleting it is the owner's choice.
   - W4: delete `data\learning\latest.json`.
   - W5: copy `memory\backup-v310-<stamp>\dump.json` back.

## Not included (separate decisions)
- **`batches\20261017-111912-debac568\runs\*` on D:.** This is a stale copy stuck at RESEARCH. It is left untouched;
  after W3 the authoritative run folders are in `runs\cloud-runs-20261017\`. `learning.py` prefers the complete folder
  and reports the duplicate.
- **The installed copies in `.claude\skills\`.** They are stale (11 files differed before 3.1.0) and are not changed
  here.
- **Git.** No commit, push, tag or GitHub release until the version and the cleanup scope are approved.
- **Analytics CSV import, `metrics`/`weights` tables.** Not used by the API path.
