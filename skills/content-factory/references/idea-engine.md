# Idea Engine — batch topic selection above V3.0.1

`scripts/idea_engine.py` turns a file of about 50 topic ideas into N finished publishing packages (`--count N`, default
2). It decides
**which** topics to make. V3.0.1 still decides **how** each video is made: research, hooks, script, voice, visuals,
audio, captions, QA, review, packaging, media metadata, platform disclosure and memory ingest are all unchanged.

```
input/ideas.json ─► validate ─► memory filter ─► offline research screen ─► score ─► rank ─► pick N (diverse)
   (≈50, by hand        │            │ the factory's own DB                         │ explainable     │ fail if < N
    or from a chat)     │            │ and rules                                     │ weights         │
                        ▼            ▼                                               ▼                 ▼
               batches/<batch-id>/  candidates · filtered · research · ranking · selected · manifest.json
                                    ─► N × `factory.py init` (one isolated V3.0.1 run per topic, in runs/)
                                    ─► N × the existing unattended driver (`claude -p "/content-factory …"`)
                                    ─► each verified package copied to the output folder (HDD) ─► report.json / report.md
```

## No LLM API needed

- The engine is plain Python: no API key, no network, no LLM. You write the ideas file yourself or paste it from a
  ChatGPT/Claude chat (prompt template below).
- **Production** of each selected topic is V3.0.1's job. It runs unattended through the existing driver, Claude Code
  in headless mode (`claude -p`, the same command as `automation-engineering/assets/templates/run_factory.*`). A
  Claude subscription login on the machine is enough; no API key is needed.
- `ANTHROPIC_API_KEY` stays optional, as in V3.0.1. Without it, V3.0.1's QA reviewer uses its heuristic judge
  (CLOUD_HANDOFF rule 3; Phase 5 found that judge generous).
- **Future generators.** The ideas file is the whole interface. A later automatic generator, API-based or not, only
  has to write `input/ideas.json` in this format, with its name in `"generator"`. Nothing in the engine has to change.

## The ideas file (`input/ideas.json`)

Schema: `schemas/idea_candidates.schema.json`. Example: `input/ideas.example.json`. The engine's own checks
(`idea_engine.py validate`) are stricter than the schema.

```json
{
  "version": "1.0",
  "generated_at": "2026-10-07",
  "generator": "chatgpt",
  "candidates": [
    {
      "id": "metal-feels-colder",
      "topic": "Why does metal feel colder than wood at the same temperature?",
      "angle": "Metal pulls heat out of your hand faster, so your skin reads the speed of heat loss, not the temperature.",
      "hook": "Metal isn't colder than wood. It's faster.",
      "visual": "a hand touching a metal bar and a wooden plank, with heat arrows leaving the hand",
      "category": "counterintuitive",
      "source_hint": "https://www.nist.gov/",
      "notes": null
    }
  ]
}
```

| field | required | meaning |
|---|---|---|
| `id` | yes | unique in the file: 1–64 letters, digits, `.`, `_` or `-` |
| `topic` | yes | one question or claim (≤200 characters) |
| `angle` | no | the answer or mechanism the video pays off (≤400) |
| `hook` | no | a hook idea (≤200). V3.0.1's hook engine writes and picks the real hook; this one is passed on as a constraint |
| `visual` | no | one concrete thing to draw (≤300) |
| `category` | no | free text. Suggested: curiosity, science, everyday, psychology, technology, nature, human_body, space, history, engineering, strange_facts, counterintuitive, discoveries, common_questions, visual_phenomena. There are no quotas |
| `source_hint` | no | a URL or name, or a list of them. Never treated as verified |
| `notes` | no | yours; ignored |

Do **not** add scores: the engine scores every candidate itself and ignores unknown fields (it reports them).

**What makes the whole file invalid** (nothing is processed; every problem is listed):
- malformed JSON (with its line and column)
- a duplicate key
- no `candidates` list, or an empty one
- `version` other than `"1.0"`
- more than 500 candidates
- duplicate ids, or a missing or badly formed id

**What makes one candidate invalid** (kept, reported, never silently dropped):
- a missing or empty `topic`
- an over-long field
- a field of the wrong type

Outside 30–80 candidates the report warns but processes everything.

## Prompt template (copy into ChatGPT or Claude, paste the answer into `input/ideas.json`)

```
I run a faceless short-video channel (YouTube Shorts, TikTok, Instagram Reels; English; 20–45 seconds; animated
hand-drawn doodle style). Each video answers ONE surprising "why/how" question with one clear mechanism.

Give me 50 NEW video topic candidates as ONE JSON object in exactly the format below, and nothing else:
no prose, no markdown code fences.

Rules:
- One specific question or claim per topic, which can be answered with one mechanism in under 45 seconds.
- True and checkable. No medical, financial or legal advice, no exaggeration, no clickbait ("you won't believe",
  "shocking", "100%").
- Every candidate on a different subject. Mix categories naturally; there are no quotas.
- "angle": the actual answer in one or two sentences.
- "hook": an optional spoken first line of under 9 words.
- "visual": optional; one concrete thing to draw.
- "source_hint": a reputable source URL or name if you know one, otherwise null. Do not invent URLs.
- Do not include scores or rankings.
- Do not repeat these topics, which the channel has already made:
  <paste the list printed by the command in "Avoid wasted candidates" below>

Format:
{"version": "1.0", "generated_at": "YYYY-MM-DD", "generator": "chatgpt", "candidates": [
  {"id": "short-unique-id", "topic": "…", "angle": "…", "hook": "…", "visual": "…", "category": "…",
   "source_hint": null, "notes": null}
]}
```

**Avoid wasted candidates.** The list of topics already made comes from memory:
`python -c "import json; [print(r['topic']) for r in json.load(open('memory/dump.json'))['tables']['runs']]"`.
The engine refuses repeats in any case.

## How to run

**Once per machine** (the existing V3.0.1 setup; Claude Code finds skills only under `.claude/skills/`):

```
python skills/automation-engineering/scripts/install_skills.py --project D:\shorts-ai\factory   # from this repository
cd D:\shorts-ai\factory
mkdir memory
copy <repo>\memory\dump.json memory\                       # the channel memory (or point CF_DB at your factory.db)
python .claude\skills\content-factory\scripts\setup_env.py --out capabilities.json
claude                                                         # log in once (subscription login; no API key needed)
```

**Each batch**, from that project folder: paste the prompt above into a chat, save the answer as `input\ideas.json`,
then validate and run it. `validate`, `select` and `--produce none` also work straight from this repository
(`python3 skills/content-factory/scripts/idea_engine.py …`). Production needs the installed project folder; without it
the engine prepares the runs and stops with exit 3.

```
# Windows (PowerShell)
python .claude\skills\content-factory\scripts\idea_engine.py validate --ideas-file input\ideas.json
python .claude\skills\content-factory\scripts\idea_engine.py run --ideas-file input\ideas.json --output-dir D:\shorts\packages

# Linux / macOS
python3 .claude/skills/content-factory/scripts/idea_engine.py validate --ideas-file input/ideas.json
python3 .claude/skills/content-factory/scripts/idea_engine.py run --ideas-file input/ideas.json --output-dir /mnt/hdd/shorts
```

N is `--count N` on `select` and `run`: the number of topics, runs and videos in the batch (each run makes one
video). Without `--count` it is **2** (5 before 2026-10-14). It must be a positive whole number from 1 to 50;
`0`, `-1`, `2.5`, `abc` and the like are refused with exit 2 before anything is read or written.

| command | does |
|---|---|
| `validate --ideas-file F` | checks the file and prints every problem; writes nothing |
| `select --ideas-file F [--count N]` | builds a batch up to `manifest.json`, prints the N winners, and stops (nothing is produced) |
| `run --ideas-file F [--count N] [--output-dir D]` | `select`, then production of the N runs, then delivery and the report |
| `produce --batch batches/<id> [--output-dir D]` | (re)produces an existing batch: only slots that are not packaged yet are driven again |

Options:
- `--count N` (`select` and `run`; default 2; a positive whole number, 1–50)
- `--db` (memory; default `$CF_DB`, else `$CF_RUNS_DIR/factory.db`, else `~/content-factory/runs/factory.db`, the same
  resolution as `factory.py init`)
- `--batches-dir` (default `$CF_BATCHES_DIR` or `batches`)
- `--output-dir` (default `$CF_OUTPUT_DIR`)
- `--languages en`, `--min-s 20`, `--max-s 45` (passed to `factory.py init`)
- `--produce claude|none` (`none` creates the N V3.0.1 runs and stops)
- `--driver-cmd "CMD … {run} …"` (your own production command per run; placeholders `{run} {batch} {topic} {slot}`)
- `--run-timeout-min 180`
- `--allow-empty-memory` (a deliberately fresh channel)
- `--allow-reused-input` (run the same file again on purpose)

`.env` in the project folder is read for `CF_*` paths, as the run_factory templates do. Existing environment
variables win.

Exit codes:
- **0**: done
- **2**: invalid file or `--count`, fewer than N usable candidates, a stale batch, or a run that did not deliver (see the report)
- **3**: environment not ready (`NO_MEMORY`, or the driver is missing). The runs prepared so far are kept for `produce`.

## Outputs

```
batches/<YYYYMMDD-HHMMSS-sha8>/          one folder per batch; never reused
  input.json        byte copy of the ideas file (its sha256 is in the manifest)
  candidates.json   every candidate, normalised, with valid/problems/warnings
  filtered.json     memory verdict per valid candidate: topic repeats, novelty, nearest past items, hook repeats
  research.json     offline screen per candidate (see "Research")
  ranking.json      weights, then every scored candidate: rank, total, 9 components, the reasons for each
  selected.json     the N winners (with the selection step and why) and every eligible candidate not chosen
  manifest.json     what production will make: winners, ideas-file sha256, memory fingerprint, init settings, its own sha256
  slots.json        slot → V3.0.1 run folder (or the init refusal)
  runs/<run-id>/    the N V3.0.1 runs (each its own folder, state, lock and package)
  logs/NN-<run>.<attempt>.log   driver output per attempt (never overwritten)
  report.json, report.md
<output-dir>/<batch-id>/NN-<run-id>/package/…  plus <run-id>_package.zip     verified copy of each delivered package
```

The report answers:
- how many candidates were supplied, how many were invalid and why
- which were rejected by memory (and what they repeat), for quality, or as duplicates
- the top candidates with their totals, and why each winner was chosen
- per run: success or failure with V3.0.1's own reasons (failed gate codes, escalation, next action), and where the
  package is

## Memory filter (V3.0.1's memory, no second database)

The engine opens the factory's content database (`content-database/scripts/cfdb.py`, the same file `init` uses) and
applies the factory's existing rules unchanged:
- **Topic repetition** (`cfdb.topic_repeats`, the rule behind init's `TOPIC_REPEATED`). A candidate is rejected when it
  restates an earlier run topic or video title. That means a character-trigram cosine of at least 0.6, at least two
  shared content stems ("cracking your knuckles" vs "why your knuckles crack"), or every stem contained in the earlier
  topic. A rephrasing is caught by the stems, not by the wording.
- **Novelty** (the SELECTION rule). Topic + angle is compared with every remembered title, hook, idea and topic. A
  candidate below 0.35 novelty is rejected, which catches ideas the factory proposed before but never made.
- **Hook repetition** (the hook engine's rule, Jaccard ≥ 0.6 to a used hook). The candidate is flagged and its hook
  score drops. V3.0.1 never reuses that hook anyway.

Selection only reads the memory. After a run is packaged, `factory.py package` ingests it, so the same topic is
refused next time. After production, the engine also exports the memory to `./memory/dump.json` when that folder
exists, as the run_factory templates do.

If the database is missing:
- it is seeded from `./memory/dump.json` (the templates' rule);
- with neither, the engine stops with `NO_MEMORY` (exit 3) instead of filtering against an empty memory.

`init` re-checks every winner against the memory at hand-off. Keep one database for every entry point. Set `CF_RUNS_DIR` (or `CF_DB`) in the project's
`.env`, as `env.example` does; the run_factory templates and this engine both read it.

## Research

The factory's only research path is the RESEARCH stage of each run. There, the agent searches, writes a dossier, and
`dossier_tool.py` gates it (source tiers; tier-1 or two independent sources for high-risk claims). Without an agent
there is nothing that could verify a fact, so the engine **does not pretend to research**. `research.json` says
`"mode": "offline", "web_research": "not performed"` for every candidate.

What the offline screen grades is only what is in the file:
- risk terms (medical, financial, legal);
- numbers and records, which make a claim medium risk;
- exaggeration and clickbait phrasing;
- the tier of each `source_hint` URL under the RESEARCH gate's own tier list. Hints are never marked verified, and
  none are ever added.

Facts are researched, sourced and gated by V3.0.1 for the N winners only.

## Scoring (deterministic and explainable)

Every component is 0–1, and `ranking.json` lists the reasons that produced it. The total is the weighted sum. The
lexicons and regular expressions are at the top of `idea_engine.py`.

| component | weight | what raises it |
|---|---|---|
| novelty | 0.15 | distance from everything in memory, rescaled above the 0.35 rejection line |
| curiosity | 0.15 | posed as a question; a contrast word (hook_lint's list); a number or name; relatable ("you", home); a surprise marker |
| hook_potential | 0.15 | hook spoken in ≤3.2 s at hook_lint's words-per-second rate; contrast; specific; tension. Penalised: throat-clearing opener, clickbait (zero), a used hook. No hook: 0.3, neutral |
| visual_potential | 0.12 | a visual idea supplied; concrete, drawable nouns. Penalised: abstract subjects |
| clarity | 0.10 | topic of 3–14 words; one question; an angle of 6–45 words |
| short_form_fit | 0.10 | a single subject (not a list or overview); the angle names a mechanism |
| payoff | 0.10 | the angle picks up the topic's words, gives an explanation, and is an answer rather than another question |
| factual_confidence | 0.08 | low risk; no exaggeration |
| research_quality | 0.05 | best source-hint tier (1 → 1.0 … 4 → 0.15; none → 0.35, unknown rather than bad) |

Rejected before scoring:
- invalid candidates (validation)
- memory repeats
- clickbait in the topic or angle (quality)

Rejected after scoring:
- totals below **0.40** (quality; a bare topic with nothing else scores ≈0.45)
- near-duplicates inside the file, judged by the same topic rule as memory. The higher-scored phrasing is kept.

## Choosing the N winners

Maximal marginal relevance, the same shape as V3.0.1's SELECTION:
- `0.75 · total − 0.25 · similarity to the winners already picked`
- similarity is the maximum of the trigram cosines of topic + angle, of hook and of visual, plus stem overlap, with
  +0.15 when the category is the same
- a candidate on the same subject as a winner is never picked

The winners therefore differ in subject, angle, hook and visual concept. There are no category quotas.

Ties break on the position in the file. There is no randomness, so the same file and the same memory always give the
same ranking and the same winners. If fewer than N usable, mutually different candidates remain, the batch stops
with `TOO_FEW_CANDIDATES` (exit 2): no manifest, no runs, and no invented topics. Add more ideas and run again.

## How V3.0.1 is invoked

1. **Hand-off: one `factory.py init` per winner**:
   `init --topic <topic> --count 1 --languages en --min-s 20 --max-s 45 --runs-dir batches/<id>/runs --db <memory>`,
   with constraints `Angle (from the idea batch): …`, `Hook idea (optional; the hook engine decides): …` and
   `Visual idea (optional): …`.
   - `init` itself re-checks the topic against memory and the machine's capabilities.
   - A refusal (`TOPIC_REPEATED`, `CAPABILITY_MISSING`, `MEMORY_FAILED`) is recorded for that slot only.
2. **Production: the existing unattended driver per run, one at a time**:
   `claude -p "/content-factory Continue the existing factory run at <run> …" --permission-mode acceptEdits
   --permission-prompts none --allowedTools "Bash,Read,Write,Edit,WebSearch,WebFetch" --output-format json
   --add-dir <batch>`.
   - The environment has `CF_DB` (the batch's memory) and `CF_RUNS_DIR` (the batch's runs).
   - The agent drives `factory.py next/record/media` through every gate and ends with `factory.py package --zip`.
   - Retries, regeneration and escalation are V3.0.1's own. The driver runs once per run per `produce`, so a rerun of
     `produce` retries only the runs that are not packaged.
3. **Verification and delivery.** Only V3.0.1's state is evidence. A run is delivered when every video is `packaged`,
   its PACKAGE stage passed, and `package/<vid>/result.json` is byte-identical to the envelope `record` stored
   (sha256).
   - The package is copied to `<output-dir>/<batch-id>/NN-<run>/`, together with the zip.
   - Every file is verified against the run's `checksums.sha256`, before and after the copy.
   - An existing output folder is never overwritten. An identical one counts as delivered; a different one is refused.

## Determinism and stale protection

- **The batch folder and its inputs.**
  - Every `select`/`run` makes a new batch folder (time + input hash), so a batch is never reused.
  - An ideas file already used by a batch is refused (`IDEAS_FILE_ALREADY_USED`) unless `--allow-reused-input` is
    given.
- **The manifest.**
  - `manifest.json` carries a sha256 over its content.
  - `produce` refuses a batch (`STALE_MANIFEST`) if the manifest was edited, if it names another folder, or if
    `input.json` no longer matches.
  - `produce` also refuses (`MEMORY_MISSING`) if the memory database it was selected against is gone, rather than let
    `init` start an empty one.
- **The runs.**
  - A run in `slots.json` that is outside the batch's `runs/`, has another topic, is older than the batch, or is
    missing is refused and never driven.
  - A package whose result no longer matches V3.0.1's record is not delivered.
- **Locking and isolation.**
  - One `produce` per batch (`batches/<id>/.lock`, the factory's FileLock).
  - Each run keeps V3.0.1's own `RUN/.lock`.
  - Runs live only under the batch, so the normal `CF_RUNS_DIR` is never touched.

## Troubleshooting

| message | meaning / fix |
|---|---|
| `INVALID_IDEAS_FILE` | the file is not usable as a whole. Fix every listed problem (`validate` prints them with line and column) |
| `IDEAS_FILE_MISSING` | save the JSON at `input/ideas.json` or pass `--ideas-file` |
| `IDEAS_FILE_ALREADY_USED` | this exact file was already run. Write a fresh list, or pass `--allow-reused-input` |
| `NO_MEMORY` (exit 3) | no database at the resolved path and no `memory/dump.json`. Point `--db`/`CF_DB` at the factory database |
| `TOO_FEW_CANDIDATES` | the report lists why each candidate dropped out. Add fresh ideas |
| `environment_error` (exit 3) | `claude` is not on PATH, or `.claude/skills/content-factory` is not installed. The runs are prepared: fix it and `produce --batch …` |
| slot `init_failed` | `factory.py init` refused it (the reason is in the report). A repeat means memory changed since selection. `CAPABILITY_MISSING`: run `setup_env.py` |
| slot `not_packaged` | the run stopped. Its failed gate codes and V3.0.1's next action are in the report, and the driver output is in `logs/`. Run `produce --batch …` again, or continue the run by hand (`factory.py next --run …`) |
| slot `delivery_failed` | the output folder already holds different content (never overwritten), or a checksum failed |
| `STALE_MANIFEST` / `MEMORY_MISSING` | the batch was changed after selection, or its memory is gone. Start a new batch with `run` |
| `LOCKED` | another `produce` is working on this batch. A dead process's lock is taken over |

## Limitations

- **Production still needs the Claude Code agent.** Authoring (research, hooks, scripts, scenes, packages) is
  model work inside V3.0.1, so `run` needs `claude` and a login on the machine. With `--produce none`, the engine
  stops after preparing the N runs.
- **The research screen is offline.** No candidate is fact-checked before selection; V3.0.1's RESEARCH gate does that
  per run. A winner can therefore still escalate at RESEARCH, and the report then shows the slot as `not_packaged`.
- **Scoring is a transparent heuristic, not a prediction of views.** It ranks what the text of each candidate shows.
- Production runs one video at a time, and a full batch takes as long as N V3.0.1 runs.
