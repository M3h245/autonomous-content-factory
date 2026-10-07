---
name: content-database
description: The content factory's memory — a portable SQLite store of runs, ideas, videos, assets, stage results, publications, metrics and learned weights — with novelty search against past titles, hooks and angles, history export for idea selection, publication logging, and JSON export and import for persistence across sessions. Use when a factory run starts or ends, to check "have I already made a video like this", to log where a video was published, to import or export the factory database, or to store analytics feedback. Not a general-purpose database helper.
---

# Content Database

**Stages:** cross-cutting (run start, PACKAGE, ANALYTICS) · **Script:** `scripts/cfdb.py`

## Activation
Start of a run (import + history/weights), end of a run (ingest + export), publication logging, novelty questions.

## Responsibilities
Remember everything the factory made and learned so batches don't repeat themselves and feedback compounds.

## Inputs → outputs
| In | Out |
|---|---|
| run folders, `feedback.json`, publication URLs/ids, `dump.json` from an earlier session | `factory.db`, `history.json`, `weights.json`, `dump.json` |

## Workflow
- New session: if the user uploads `dump.json` → `cfdb.py import --db factory.db --in dump.json`.
- Memory is on by default (v3.0.0): `factory.py init` uses `--db`, else `CF_DB`, else `<runs-dir>/factory.db`
  (`--no-db` only for tests). Before creating the run it runs `cfdb.py topic-check` and refuses a topic that repeats an
  earlier run topic or video title (TOPIC_REPEATED; override `--allow-similar-topic REASON`, recorded). Then
  `history` and `weights` are written into the run; the HOOK gate never selects a hook already in the history.
- After PACKAGE: `factory.py package` ingests the run automatically (idempotent). Then `cfdb.py export --db factory.db
  --out dump.json` and deliver `dump.json` with the package (claude.ai sandboxes reset; this file is the memory).
  The repository ships `memory/dump.json` (every topic made so far).
- Novelty check: `cfdb.py similar --db factory.db --text "candidate title or hook"` (char-trigram cosine).
- Topic check: `cfdb.py topic-check --db factory.db --text "…"` → `{topic, checked, repeats}` (repeat = trigram cosine
  ≥0.6, ≥2 shared content stems, or one topic containing the other).
- After upload by the user: `cfdb.py publish --video v01 --platform youtube --url … --platform-id …`.

## Quality gate
Upserts are idempotent (primary keys per run/video/stage/attempt); `stats` must show the ingested counts.
Novelty below 0.35 makes content-strategy reject an idea.

## Failure recovery
Corrupt or missing DB → rebuild from `dump.json` or by re-ingesting run folders.

## Persistence options
1. `dump.json` delivered with every package (default, verified). 2. Google Drive connector for the small JSON dump
(text upload works; videos are too large to pass through the connector). 3. A published artifact with a `db`
capability is available on claude.ai but not provisioned by default.

## Scripts
`scripts/cfdb.py init|ingest-run|similar|topic-check|history|publish|log-feedback|weights|export|import|stats`

## Interactions
content-strategy (history, weights), hook-engineering (weights), content-analytics (metrics), content-factory (run ingest).
