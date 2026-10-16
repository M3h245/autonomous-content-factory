# Experiments (cf-experiment/1, experiment layer 1.1): paired creative tests on top of the Idea Engine

Each week tests one variable: control against variant, judged on the channel's own measurements. The production engine (V3.0.1) is not changed.
An experiment is an ordinary idea batch (`batches/<experiment_id>/`). The Idea Engine verifies and delivers its runs.
Each run is driven by the experiment driver (`experiment.py drive`), which enforces the arm rules before any audio is made.
Everything experiment-specific lives in `batches/<id>/experiment/`.

## Workflow (Windows PowerShell, run from the project folder)

    python .claude\skills\content-factory\scripts\doctor.py
    python .claude\skills\content-factory\scripts\experiment.py plan    --spec input\experiments\<id>.json
    python .claude\skills\content-factory\scripts\experiment.py prepare --batch batches\<id>      (exit 0 only when all slots are ready)
    python .claude\skills\content-factory\scripts\experiment.py ready   --batch batches\<id>      (exit 0 = GO for production)
    python .claude\skills\content-factory\scripts\experiment.py produce --batch batches\<id> [--output-dir D:\Youtube\...]
    python .claude\skills\content-factory\scripts\experiment.py check   --batch batches\<id>      (exit 0 = every slot publishable)
    (upload by hand at the planned times)
    python tools\youtube_sync\yt_sync.py pull                                                    (writes <repo>\data\analytics)
    python .claude\skills\content-factory\scripts\experiment.py link    --batch batches\<id>
    python .claude\skills\content-factory\scripts\experiment.py observe --batch batches\<id>      (each day; windows come from the data cutoff)
    python .claude\skills\content-factory\scripts\experiment.py manual-template --batch batches\<id>   → fill Stayed to watch
    python .claude\skills\content-factory\scripts\experiment.py manual  --batch batches\<id> --csv batches\<id>\experiment\manual_entry.csv
    python .claude\skills\content-factory\scripts\experiment.py report  --batch batches\<id>

Do not use `idea_engine.py produce` for an experiment batch. It runs the generic driver, which never sees the gate.
`experiment.py produce` calls the Idea Engine with the experiment driver.

## When SCRIPT passed outside the driver (experiment layer 1.2)

If `drive` stopped a slot because V3.0.1 escalated SCRIPT, the owner may fix it with a human `factory.py reset` and a
re-recorded SCRIPT pass. After that, the slot record still says `blocked`. Sync it without running anything:

    python .claude\skills\content-factory\scripts\experiment.py gate      --batch batches\<id> --slot N   (read only; ok needs SCRIPT passed)
    python .claude\skills\content-factory\scripts\experiment.py sync-gate --batch batches\<id> --slot N   (writes the gate record only)

`sync-gate` refuses, and writes nothing, unless every precondition holds: frozen plan and assignment, SCRIPT passed and
recorded, no later stage passed, no lock, and the gate ok.

After a sync, the next `drive` or `produce` for that slot skips phase A and starts phase B, which is audio.

## Guarantees

**plan**
- Write-once and self-hashed: `plan_sha256` covers everything except `created_at`.
- The same spec is a no-op. A changed spec or an edited plan.json is refused.
- To change a design, give it a new experiment_id. The old batch moves to `batches/_superseded/` and its files stay unchanged.
- Assignment is one recorded coin flip per experiment, alternated by pair. This balances the arms across topic lists.

**prepare** (failure-safe)
- Runs one `factory.py init` per slot and records each slot as soon as it is done.
- The arm rules are stored twice: in run.json (`--constraint`) and in `experiment_assignment.json` in the run.
- `manifest.json` is the file `idea_engine.py produce` requires. Prepare writes it only after all slots exist and every
  run's constraints and assignment equal the frozen plan. A partial batch therefore cannot be produced.
- A rerun re-initialises only the failed slots. Existing runs and assignments stay byte-identical.

**ready**
- The preflight. It checks that every slot has a run, that its topic, constraints and assignment match the plan, and that
  no run has audio without an approved gate.
- It also checks that the manifest verifies. `produce` refuses unless ready passes.

**gate** (1.2): read only; `ok` also requires V3.0.1 to have recorded SCRIPT as passed.

**drive**: the dedicated driver, one per run, called by produce.
1. Phase A starts a Claude Code session (your Claude login; no API key). Its prompt contains the experiment ID, plan hash,
   arm, opening line, frame-0 picture and the arm rule. The session drives HOOK and SCRIPT and stops before AUDIO.
2. Then the **gate** checks script.json:
   - The hook's first sentence is ≤ 8 words and shares at least 50% of the assigned line's content words. A different
     line is allowed only with `experiment_override.json` giving the research reason.
   - An opening question is answered within 2 s.
   - Variant: a beat carrying the planned reveal (its distinctive words, at least 2 and 25%) starts at 1.5–7 s. No setup
     beat or hook repeat in that window.
   - Control: the planned reveal does not appear in the first 9 s. Other twists are allowed.
3. A failing script is re-opened with V3.0.1's own `factory.py reset`: HOOK for opening problems, SCRIPT otherwise. This
   marks AUDIO and every later stage stale. The script is then rewritten with the gate's feedback.
4. After 2 repairs a slot that still fails is `blocked`: no audio, no phase B.
5. Phase B (audio → package) may not change the hook or script. If the script's sha256 changes anyway, the slot becomes
   `noncompliant`.

**check**
- Re-runs the gate with the real TTS word timing. Script tokens and timing words must align one-to-one, otherwise the
  slot is flagged.
- Requires the approved script hash. Records the production evidence.
- Exits 3 unless every slot is publishable.

**observe**
- The window is chosen by the **data age**: the end of the last processed Analytics day (Pacific time; the last row of
  the channel daily report) minus the publish time. Pull time is not used.
- Windows: 24h = 18–48 h of data, 72h = 60–120 h.
- Each observation records `data_age_hours`, `pull_age_hours`, `analytics_cutoff_day` and `analytics_cutoff_utc`.
  The same cutoff is never recorded twice.
- Every metric has a value, source, time and status. Stayed to watch stays `manual_required` (Studio-only) and is never
  substituted.

**report**
- Primary metric: the 72 h reading, or 24 h when 72 h is missing (flagged). Pairs with a non-compliant or blocked run are
  excluded and listed.
- Adopt only with ≥ min_wins of min_pairs and a median ≥ threshold. Below min_pairs the result is "continue testing"
  (preliminary).
- Raw views never decide.

## Not automatic
- Uploading.
- Studio-only metrics (Stayed to watch, Shown in feed).
- Production itself, which needs the Windows machine with the TTS stack and Claude Code.
