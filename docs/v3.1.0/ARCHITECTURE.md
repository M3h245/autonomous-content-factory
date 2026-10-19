# v3.1.0 — data architecture, source of truth, synchronisation and recovery

## 1. One source of truth

**`C:\Users\M3H245\content-factory\runs\factory.db` on the owner's Windows PC is the canonical production database.**
Every other copy of the data is derived from it, a backup of it, or a candidate waiting to enter it.

| store | role | who writes it | may it overwrite canonical rows? |
|---|---|---|---|
| `factory.db` (Windows) | **canonical**: runs, ideas, videos, assets, stage results, publications, metrics, weights, `yt_*` analytics | the tools listed in §2, on the owner's machine, after approval | — |
| `memory/dump.json` | portable JSON **export** of factory.db (`cfdb.py export`) for git history and new machines | `cfdb.py export`, only after an approved write | no. It is an export. Re-import it only into an empty or disposable database |
| `factory.db.bak-*`, `runs/backup-*`, `memory/backup-*` | point-in-time backups made before every write | the writing tool itself | no. They are only for rollback (§5) |
| `factory.cloud-snapshot-*.db`, `/home/claude/*` cloud databases | **disposable** working copies | cloud sessions | **never**. Cloud work reaches the canonical DB only through `reconcile.py` (§3) |
| run folders (`batches/*/runs/*`, `runs/cloud-runs-*`) | evidence of how each video was made (hook, script, timing, storyboard, package, provenance) | `factory.py` | they are inputs; `cfdb ingest-run` / `reconcile.py` turn them into rows |
| `outputs/<date>/<NN_slug>/` | upload-ready copies of the packages | idea_engine or manual delivery | no DB role. Upload evidence is matched to these files by `ingest_youtube.py` |
| `data/analytics/<stamp>/snapshot.json` | immutable yt_sync pulls (YouTube Data + Analytics API) | `yt_sync.py pull` | they are inputs to `ingest_analytics.py` |
| `data/learning/<stamp>/learning_summary.json`, `data/learning/latest.json` | derived analysis read by generation | `learning.py analyze` | derived, never a source. Regenerated from the DB at any time |

## 2. Writers of the canonical database (each one alone, each with its own evidence rule)

| data | only writer | evidence rule |
|---|---|---|
| runs, ideas, videos, assets, stage_results | `factory.py package` (on the PC) → `cfdb.py ingest-run`; from other machines **only** `reconcile.py apply` | a finished, validated run folder |
| publications | `ingest_youtube.py --publications-only --apply` | uploaded file = factory output file = run hash, or owner confirmation; public now and not scheduled; legacy ids refused |
| yt_snapshots / yt_videos / yt_observations | `ingest_analytics.py --apply` | a yt_sync snapshot, kept verbatim; missing values stored as NULL with a status |
| metrics / weights | `cfdb.py log-feedback` (CSV path, unchanged) | content-analytics feedback |
| — | `cfdb.py publish` | **not used in the v3.1.0 workflow**: it checks only the time format |

Every `--apply` copies the database to `<db>.bak-<timestamp>` first and writes in one transaction.

## 3. Cloud → Windows synchronisation (`content-database/scripts/reconcile.py`)

1. **In the cloud:** finish the runs and package them. Then hand the run folders (JSON + `package/*/final.mp4` +
   provenance) to the PC as a new folder, for example `runs/cloud-runs-<date>/`. Never overwrite an existing folder.
2. **On the PC (read-only):**
   ```
   python skills/content-database/scripts/reconcile.py plan --db C:\Users\M3H245\content-factory\runs\factory.db --run <dir> --run <dir> … --out plan.json
   ```
   - Each run is validated: every global stage passed, every video is packaged, and `final.mp4` matches its recorded sha256.
   - Each row is classified:
     - **insert:** new key;
     - **identical:** same values (the volatile `videos.created_at` is ignored);
     - **conflict:** same key, different values. A conflict is **never** written.
   - Identity is the full primary key. A generic `v01` only matches together with its `run_id`.
3. **The owner reviews `plan.json`** and approves.
4. **Apply:**
   ```
   reconcile.py apply --db … --plan plan.json --report applied.json
   ```
   - It refuses if the plan is stale (the DB or the source changed since `plan`).
   - It takes a backup, uses plain `INSERT` in one transaction, re-reads the rows and compares the counts.
5. **Afterwards:** run `cfdb.py export` to `memory/dump.json` (a separate, approved step).

publications, metrics, weights and `yt_*` rows are **not** reconciled from the cloud. They are written only by their
own evidence tools, which the owner runs on the PC because the OAuth token and the output files are there.

## 4. Analytics and learning flow

```
yt_sync pull ──► snapshot.json ──► ingest_youtube --publications-only ──► publications      (evidence-based links)
                              └──► ingest_analytics ───────────────────► yt_* tables       (immutable, NULL = missing)
run folders ──► learning.py attributes ──► attributes.json
yt_* + publications + attributes ──► learning.py analyze ──► learning_summary.json + LEARNING_REPORT.md
                                                              └──► data/learning/latest.json
latest.json ──► idea_engine select (category priors) ──► factory init --learning (guidance, format priors)
           └──► hook_engine select --learning (re-ranks passing hooks) ──► run.json / selected_hook.json record it
next analyze ──► hypothesis_tracking (videos made under a summary or experiment arm vs the rest)
```

The four steps are separate commands, and each one can be re-run idempotently:
- a publication import (`ingest_youtube --publications-only`);
- a metrics import (`ingest_analytics`);
- the analysis (`learning.py`);
- a dump export (`cfdb.py export`).

## 5. Recovery and rollback

| situation | action |
|---|---|
| a write went wrong | close every factory process, then copy the `factory.db.bak-<stamp>` named in the tool's report over `factory.db`. Each report also gives the backup's sha256 |
| a snapshot was imported by mistake | restore the backup taken by that `ingest_analytics --apply`. The tables are additive, so nothing earlier was changed |
| a learning summary is wrong | delete or replace `data/learning/latest.json`, or run batches with `--no-learning`. The summary is derived and no DB row depends on it |
| a reconcile conflict | decide by hand. The plan lists both values. reconcile never resolves a conflict on its own |
| dump.json out of date | `cfdb.py export --db factory.db --out memory/dump.json` (approved step) |
| a cloud database disagrees with Windows | Windows wins. Re-plan from the cloud run folders; never copy a cloud `.db` over the canonical file |
