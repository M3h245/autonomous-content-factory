# Content memory

Two different things live here; only one of them is in git.

| file | what it is | in git? |
|---|---|---|
| `snapshot.json` | A small seed export (runs, ideas, videos, assets, publications) so a fresh clone can refuse repeated topics before it has ever run. ~200 KB. | **yes** — this is the shipped memory |
| `dump.json` | The *working* export, re-written after every production run from the live database. Grows every run. | **no** — git-ignored (P5.1) |
| `backup-*/` | Dated copies of the memory directory. | **no** |

## Where the live memory actually is

The source of truth is the SQLite **factory database**, never the JSON dump:

- `--db PATH` on `factory.py` / `idea_engine.py`, else
- `$CF_DB`, else
- `$CF_RUNS_DIR/factory.db`, else
- `~/content-factory/runs/factory.db` (default runs directory).

`cfdb.py` owns the schema (`runs`, `ideas`, `videos`, `assets`, `stage_results`, `publications`, `metrics`,
`weights`, `yt_*`). The database is created and seeded on first use, and every run is ingested into it after PACKAGE.

## Seeding and export

- `idea_engine.ensure_memory` refuses to run against a missing database until it can seed one: it tries
  `memory/dump.json` first (the working copy on this machine), then the shipped `memory/snapshot.json`.
- After a production run the engine exports the database to `memory/dump.json` (`cfdb.py export`). That file is a
  convenience export for humans and for the cloud handoff — it is not needed by the factory itself, and it is never
  committed.
- To refresh the shipped snapshot deliberately (before a release, say) run
  `python tools/make_memory_snapshot.py`, which strips the bulky `yt_*` analytics rows and the per-stage bookkeeping
  from the live dump and writes `memory/snapshot.json`.

Restoring a machine from the dump:

```
python skills/content-database/scripts/cfdb.py import --db runs/factory.db --in memory/dump.json
```
