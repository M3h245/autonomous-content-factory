# Phase 5 report — v3.0.0 (productionization + validation) · 2026-10-07

**Verdict: PASS WITH LIMITATIONS. v3.0.0 is the final release; development is frozen.**

The factory now runs brief → PACKAGE without manual steps except the defined operator decisions. It is
deterministic across machines, remembers what it has made, and refuses to ship what its gates reject. Three fresh
videos ran through every gate. With the factory's default judges all three reached PACKAGE. A packet-only
independent judge accepted one (leap years) and rejected two (flamingos, Moon) after one fix round each. In both
rejected cases the factory, given that judgment, refused to package them. That is the intended behaviour, and the
main lesson for production is to **run with an LLM judge, not the heuristic one** (limitation 1).

Nothing was published. No secrets are in the repository. Every file is under 100 MB.

## 1. What changed (production fixes, each with a test)
| Found during Phase 5 | Fix | Test |
|---|---|---|
| setup_env reported success while skia could not load libEGL; doodle scenes silently fell back to procedural art | doctor names the missing library and the fix; setup_env exits 3 on a missing core capability; `init` refuses (CAPABILITY_MISSING); VIS.DOODLE_FALLBACK (major) | test_phase5 NoSilentFailures, Gates |
| Kokoro is non-deterministic (random ops); alpha8 replays matched only through the TTS cache | fresh ONNX session seeded per sentence; TTS cache v2 | SeededTTS (1/2/4 CPUs, empty caches) |
| x264 bitstream changed with the CPU count | `-threads 4` on every encode (`cf_common.X264_THREADS`) | replays A/B (§5) |
| Two processes could change one run | `RUN/.lock` (LOCKED), dead/old locks taken over, audited `unlock`; cta_history under a shared lock | RunLock ×4 |
| A crash envelope without video id broke `record`; `media` could loop silently; an old envelope could be recorded twice | path-inferred video id, INTERNAL.NO_RESULT, STALE_RESULT, media_budget_exhausted | NoSilentFailures |
| Paper transition crashed at its first frame (latent since alpha8) | guard on an empty colour filter | Gates |
| PKG.MEDIA_METADATA_CLEAN flagged random bytes as a Windows path (≈1 video in 7; escalated a replay) | path pattern needs a real `X:\dir\name` shape | Gates |
| Package claim numbers matched substrings ("2" in "200") | whole numbers only (tightens the gate) | Gates |
| Memory was opt-in; nothing stopped a repeated topic or hook; `cfdb ingest-run` crashed on v2 runs | memory on by default, topic check at `init`, past hooks unselectable, automatic ingest, ingest fixed, shipped `memory/dump.json` | ContentMemory ×8 |
| After an operator `reset`, later stages kept their old attempt counts → the flamingo VIDEO escalated on its first failure on new content, with no automatic remix | `reset` gives the stage and every later stage a fresh budget | BatchIsolation reset test |
| An LLM judge's spoken-hook finding was routed to a first-scene redesign (cannot change words) | judgment may set `fix_stage` (HOOK/VISUAL_PLAN) | test_reviewer |
| A video re-made after a reset was checked against its own old CTA | gates see other videos' CTAs only; re-package replaces/drops its entry | ContentMemory CTA test |
| An external package judgment applied by candidate id only: new ids escaped it, reused ids got an old verdict | judgment must cover every candidate (JUDGMENT.MISSING), optional packet hash (JUDGMENT.STALE) | PackageJudgmentCoverage |
| **`package --zip` wrote a run zip although PKG.PACKAGING had failed**, left the last attempt's final.mp4 and upload sheet in place, and the video stayed "packaged" | package folder cleared per attempt; zip only when every video passed (stale zip removed); failed PACKAGE → in_progress | ContentMemory failed-repackage test |

No gate was loosened. Disclosure is untouched: PKG.DISCLOSURE still blocks, and the AI labels and description line
are unchanged.

## 2. Fresh end-to-end runs (3, one runs folder, one memory database)
| | Flamingos stand on one leg | Moon looks bigger near the horizon | Leap years skip some century years |
|---|---|---|---|
| character | animal character, study-based | perception/astronomy, night palette (navy scenes) | numbers/history, text-led layouts |
| final hook | h4 "Why do flamingos rest on one leg?" | h5 "Your camera says the Moon never grew." | h2 "Leap years aren't every four years." |
| final script | B, 7 beats, 23.9 s, no CTA | B, 7 beats, 23.0 s, no CTA | B, 8 beats, 38.1 s, no CTA |
| factory gates (default judges) | QA PASS · PACKAGE PASS (P1 45) | QA PASS · PACKAGE PASS (P2 44) | QA PASS · PACKAGE PASS |
| independent judge, video | **FAIL**: hook 3, ending 3, overall 3 → route HOOK | **FAIL**: message 3, ending 3, overall 3 → route SCRIPT | **PASS**: all 4, title 5 |
| independent judge, packages | 37 / 38 / 29 — none ≥ thresholds | 40 / 40 / 37 — none ≥ thresholds | P1 41 · P2 37 · P4 37 · P3 28 |
| final state | not packaged (factory refuses) | not packaged (factory refuses) | **packaged**: "Leap years aren't every four years" / NOT IN 1900 |
| failed attempts · regenerations | 5 · 10 | 5 · 7 | 3 · 3 |
| escalations · human resets | 2 · 5 | 0 · 2 | 0 · 0 |
| stage time | 831 s | 488 s | 317 s |

Counts come from `factory.py report` (every gate attempt is a recorded envelope). The external judge changed the leap
selection from the heuristic's P2 (44) to P1 (41).

### Every reset and escalation, explained
Flamingo:
1. VIDEO reset: re-render after the x264 thread fix.
2. SCRIPT reset: round-1 judge accuracy findings ("Two legs." answered "which tires"; two studies merged).
3. PACKAGE escalation and reset: 3 failed attempts on my thumbnails (unsaid title word, dead space, OCR'd "zz", dHash
   near-duplicate, headline below 140 px).
4. HOOK reset: the fix round. The round-2 judge said "which tires" implies fatigue no study measured. The engine then
   rejected my dead-flamingo hook (on-screen text outside the safe margin) and chose h4.
5. VIDEO escalation and reset: the reset-budget defect above. After the fix, the factory's own remix route passed.

Moon:
1. SCRIPT reset: a proactive accuracy edit.
2. HOOK reset: the fix round. The judge flagged the unsupported "Yes" to "Can your fingernail cover the giant Moon?".

Leap: no resets. One VID.OVERHANG retry and two PACKAGE retries (calendar header text counted as thumbnail text,
dead space, a CamelCase hashtag), all on my authoring.

The 0-reset target was met only by leap. The resets were operator decisions on real findings, never to force a pass.

### The independent judge (fresh agent, packet only, can lower scores, never raise them)
- 6 judgments in total, each by a new agent: flamingo ×3, Moon ×2, leap ×1. Each covered the video and its package
  set.
- **Round 1 (flamingo, Moon)**: both failed on the hook (3/5), with accuracy findings the lexical gates cannot see.
- **Fix round** (one per video, by rule): the judge's finding was routed through an audited reset into the factory loop.
  - Flamingo: the hook stayed at 3; the judge says the question is generic and the ending circular.
  - Moon: the hook rose to 4, but message clarity is 3. "About 1.5 percent farther away" is no longer tied to
    "so slightly smaller", so viewers can conclude the opposite. The ending is also abrupt.
- These two were **not** re-made again. By the Phase 5 rule the final judgment is recorded, not optimised away. Their
  rejected deliverables are kept for inspection (`phase5-rejected-for-review.zip`).

## 3. Content memory and anti-repetition
- Topic rule calibrated on 12 known repeats and 15 new topics: all correct.
  - One deliberate edge: "Why eating fast is bad" is flagged against the brain-freeze title.
- The production database refused "Why do onions make you cry?" and "Why do flamingos stand on one leg?".
- History grew run by run: run 3 saw 7 earlier topics, including runs 1 and 2.
- The database now holds 8 runs and 8 videos with no duplicates after repeated packaging (ingest is idempotent).
- `memory/dump.json` carries them.

## 4. Batch and throughput
- Isolation is tested: in a 3-video run, one escalation leaves the other two untouched; two runs in one folder share
  only memory; a second process on a run is refused.
- Measured on 4 vCPU: 5–14 min of stage time per video, including retries. The 20–35 min elapsed per authoring round
  (hook, script, scenes, packages) dominates.
- **Estimate**: one agent produces 3–5 videos/day if each video needs 1–2 rounds (≈1–1.5 h per video). With a strict
  judge expect 2–3 rounds; parallel runs in one folder are safe.

## 5. Determinism
- Narration: byte-identical across 1/2/4 CPUs and empty caches.
- Seed replays compare every file of the publishing package:
  - **leap**: A (4 CPU, empty cache A) = B (2 CPU, empty cache B) = the original run, on every deliverable (final.mp4,
    captions, thumbnail, cover, crops, metadata, upload sheet).
  - **flamingo, Moon**: a 2-CPU replay with an empty cache equals the original on narration, video, captions,
    final.mp4 and every thumbnail. Both replays re-ran the same automatic fixes and were refused at PACKAGE by the
    stored judgment, as the originals were.
  - **brain freeze** (Phase 4 seed, final code): A (4 CPU) = B (2 CPU) on every deliverable. **Knuckles**: the same
    was verified after the determinism fixes, earlier in Phase 5.
- Brain-freeze seed on the final code against the alpha8 package zip: thumbnail, cover, crops and metadata are
  byte-identical. final.mp4 and the captions differ by design: alpha8's narration came from unseeded Kokoro randomness
  and cannot be reproduced; v3.0.0 replaces "identical to alpha8 because of the cache" with "identical everywhere".
- The only files that differ between replays are internal reports (provenance.json, provenance_result.json,
  result.json, qa_report.json, checksums.sha256), and only by run paths and timestamps.

## 6. Final gates
Full regression on the final code (`work/phase5/tools/full_regression.sh`, 4 vCPU): **all green**.

| suite | tests | result |
|---|---|---|
| fast suite (11 modules: identity, stage order, Phase 0, TTS cache, visual audit, reviewer, futile retry, Phase 2 script, Phase 3, Phase 3.5, factory review) | 78 | OK |
| test_phase2_hooks | 10 | OK |
| test_phase4 | 49 | OK |
| test_phase5 | 27 | OK |
| smoke_v2 | end to end | OK |
| bad videos A–D | 7 | OK |
| v1 regression (Ken Burns + karaoke) | 2 results | passed, passed |

The Phase 0–4 suites are unchanged and still pass. The baseline before any Phase 5 change was also green.

Media:
- An independent scan of every final deliverable (ffprobe tags, `strings`, full decode) found only standard container
  tags and no paths, tool names or provenance in the video or images. All decode without error.
- AI labels are set: TikTok AI-generated on, Instagram AI info on, YouTube altered/synthetic off (Phase 3.5 policy for
  non-realistic animation). The disclosure line is in every description.

## 7. Known limitations (documented, not fixed)
1. **The heuristic judges are generous.** They passed two videos and four packages the independent judge rejected. Use
   `ANTHROPIC_API_KEY` (QA `auto`) or `--review-backend subagent`, and a packet-only package judgment, in production.
   The package judge has no API backend; it is a fresh agent or a human.
2. **Writing quality is the bottleneck.** The judge rejected two of my three videos after one fix round, on wording
   (generic hook, circular ending, an unexplained fact). The factory routes these correctly but cannot author better
   lines than its agent.
3. **Claim checks are lexical.** Numbers are now whole-number exact. Paraphrased overstatements ("locked in place",
   "Yes") and dropped hedges ("about") need a reviewer. A false positive in the other direction was seen once
   ("argue about the exact cause" read as asserting a cause).
4. **The opening promise must differ across candidates** (diversity gate), while a judge prefers it to equal the spoken
   opening; P2–P4 lost hook-coherence points for this in two runs.
5. **Package judgments are matched by id.** Coverage is now enforced; the packet hash is optional, so a judgment without
   it is trusted to belong to the current packets.
6. **Internal reports in a package folder** (provenance.json, qa_report.json) carry absolute run paths. They are not
   publishable media; media are clean.
7. **Web research.** In this cloud environment WebFetch and outbound access to source hosts (PMC, Royal Society, Georgia
   Tech, Wikipedia) were blocked by the network policy. Dossiers rest on web-search results corroborated across domains,
   not on fetched papers.
8. Carried from earlier phases:
   - the ≈3:2 YouTube crop is advisory
   - no CTR/retention data yet
   - no text-on-text overlap gate
   - no futile-resubmission guard for VISUAL_PLAN
   - YouTube altered/synthetic logic unchanged
   - byte reproducibility is proven on one software stack (same packages, different CPU sets and caches), not across
     operating systems
   - authoring still needs an LLM agent (Claude Code headless or interactive)
9. Budgets: a reset re-opens the per-stage budgets. The per-video cap (8) and the events log still bound and record
   every attempt.

## 8. Freeze
v3.0.0 is the last development version. Only operation remains: making videos with the frozen factory, uploading by
hand, and logging analytics. Any further change is a new project decision by the owner.
