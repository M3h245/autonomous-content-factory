# work/phase5 — operator scripts of the Phase 5 fresh runs (v3.0.0)

Authoring helpers, not factory code. Every gate ran through the factory loop (`op.py step` = next → gate → record),
so every attempt is counted in the runs' events.

| path | what |
|---|---|
| `op.py` | `step RUN` (one stage through next → gate → record), `media RUN` (AUDIO → VIDEO → SUBTITLES → QA), `peek RUN` |
| `scenecheck.py` | authoring aid: per-scene layout, subject, empty cells, cadence gaps, cue problems, strip of final frames |
| `make_seed.py` | builds `seeds/<run>/` (brief + final authored inputs) from a finished run, for `work/phase4/replay.py` |
| `build_memory_seed.py` | built the first `memory/dump.json` from the five Phase 0–4 topics |
| `flamingo/`, `moon/`, `leap/` | per-topic shapes and the scripts that wrote hooks, script variants, scenes and packages. `*.r1.*` are the versions before the Phase 5 fix round (flamingo: after the round-1 SCRIPT reset) |
| `tools/pkgcheck.py` | authoring aid: previews package_engine's deterministic thumbnail/copy checks, schema and dHash diversity (no gate, no state) |
| `tools/media_audit_indep.sh` | independent audit of a publishing package (ffprobe tags, `strings`, full decode, AI labels) |
| `tools/full_regression.sh` | the full regression (CLOUD_HANDOFF "Tests" + test_phase5 + v1); one summary line per suite |
| `tools/cmp_runs.py` | compares two runs' `package/` trees file by file (bytes, or bytes after normalising run paths) |

The per-topic `make_*.py` scripts take the run folder as their only argument and write into it, e.g.
`python3 work/phase5/leap/make_scenes.py runs/2026-10-07-why-leap-years-skip-some-century`.
