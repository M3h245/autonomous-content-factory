# H1 — statement vs question opening (prepared, not started)

**Question.** Does a declarative first line ("Flamingos aren't born pink.") keep more viewers than a direct question ("Why are flamingos pink?")?

**Design.** 6 matched topic pairs (12 new videos, 6 per arm). Within each pair one topic gets the statement and the other the question, decided by a recorded hash (`spec.json → assignment`), not by choice. Everything else is held constant: frame 0, length 20–25 s, voice, captions, the normal post-hook structure (no planned 3–9 s surprise — that is the beat3to9 experiment's variable), loop ending, no CTA. One pair per day, 18:00 and 23:00 Rome, with the arm in the 18:00 slot alternating.

**Measurement.** Each video at publish + 7 days. Primary: Studio "stayed to watch" if available for all 12, otherwise engaged views / views from the API for all 12 (never mixed). Guardrail: average view percentage. Data goes in through `ingest_youtube.py`; outcomes are filled in `spec.json` only from measured data.

**Decision.** Statement wins only if it is ahead in ≥ 5 of 6 pairs, the median paired gain is ≥ 5 points, and the guardrail drops by no more than 5 points (same rule reversed for the question). Anything else is inconclusive and the factory default stays. Six pairs give directional evidence, not certainty (5/6 wins: sign-test p ≈ 0.11; 6/6: p ≈ 0.016).

**Pilot (excluded from the decision).** The four finished unpublished videos (toast = question; ice, voice, cat = statement) are tracked for context only: their arms were not assigned in advance and the topics are not matched.

**Separation from EXP-2026W42-beat3to9-c.** Its spec, batch, slots, runs and gate state are untouched; H1 never uses `experiment.py` or that batch, and publishes only on days/slots that experiment does not use.

**Before production (needs approval).** RESEARCH gate on every planned statement; any reworded line is recorded in `spec.json` before the first render.
