"""learning_apply — the read side of the learning summary (cf-learning/1), shared by every consumer.

Pure functions, standard library only. Consumers (idea_engine.py, factory.py init, hook_engine.py select) import this
module instead of re-implementing the rules, so every decision that uses evidence is explained the same way.

  load(path)                       -> summary dict, or raises LearningError (wrong schema, missing directives)
  resolve(explicit, repo, disabled) -> path of the summary a batch should use (explicit > $CF_LEARNING > repo latest)
  opening_form(text)               -> "question" | "imperative" | "statement"   (deterministic rule, see RULES)
  topic_multiplier(s, category)    -> (multiplier, [reasons])   bounded, 1.0 when there is no evidence
  format_weights(s)                -> {"format:<f>": multiplier}  for content-strategy select_ideas.py --weights
  hook_bonus(s, form, mechanism)   -> (bonus in review points, [reasons])   bounded ±MAX_HOOK_BONUS
  guidance(s)                      -> {"hook": [...], "script": [...]}  plain sentences for the run brief
  reference(s, path)               -> what a run records about the summary it was made with

A summary never forces a choice: multipliers are bounded by the summary's own caps (≤ ±15 %), levels without
evidence get exactly 1.0, and hook bonuses only re-rank candidates that already passed the independent review.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

SCHEMA = "cf-learning/1"
MAX_MULT_DEV = 0.15          # no directive may move a score by more than ±15 %, whatever the summary says
MAX_HOOK_BONUS = 1.5         # review points (a review total is 3 scores of 1–5); 1.5 < the gap between 4 and 5 on two scores
HOOK_BONUS_SCALE = 10.0      # bonus = 10 × (combined multiplier − 1): ±5 % → ±0.5 points (tie-break only)
IMPERATIVE = {"pinch", "look", "try", "watch", "imagine", "listen", "touch", "hold", "put", "drop", "close", "open", "stare",
              "cover", "press", "take", "picture", "guess", "spot", "notice", "count", "say", "hum", "blink", "tap", "wait"}
RULES = {"opening_form": "question if the first sentence ends with '?'; imperative if its first word is a command verb "
                         f"({', '.join(sorted(IMPERATIVE))}); otherwise statement"}


class LearningError(Exception):
    pass


def sha256_file(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(path) -> dict:
    p = Path(path)
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise LearningError(f"learning summary unreadable: {p}: {e}") from e
    if not isinstance(s, dict) or s.get("schema") != SCHEMA:
        raise LearningError(f"not a {SCHEMA} learning summary: {p}")
    for k in ("summary_id", "directives", "policy"):
        if k not in s:
            raise LearningError(f"learning summary {p} lacks '{k}'")
    s["_path"], s["_sha256"] = str(p.resolve()), sha256_file(p)
    return s


def resolve(explicit=None, repo=None, disabled=False):
    """The summary a new batch should read. Disabled → None. An explicit path must exist (error otherwise); the
    environment variable and the repo default are used only when present."""
    if disabled:
        return None
    if explicit:
        if not Path(explicit).is_file():
            raise LearningError(f"--learning {explicit}: file not found")
        return Path(explicit)
    env = os.environ.get("CF_LEARNING")
    if env:
        if not Path(env).is_file():
            raise LearningError(f"$CF_LEARNING={env}: file not found")
        return Path(env)
    if repo:
        p = Path(repo) / "data" / "learning" / "latest.json"
        if p.is_file():
            return p
    return None


def opening_form(text: str) -> str:
    first = re.split(r"(?<=[.!?])\s+", (text or "").strip(), maxsplit=1)[0]
    if first.rstrip().endswith("?"):
        return "question"
    w = re.findall(r"[A-Za-z']+", first)
    if w and w[0].lower() in IMPERATIVE:
        return "imperative"
    return "statement"


def _bounded(m) -> float:
    try:
        m = float(m)
    except (TypeError, ValueError):
        return 1.0
    return round(max(1 - MAX_MULT_DEV, min(1 + MAX_MULT_DEV, m)), 4)


def _prior(s: dict, group: str, attr: str, level) -> tuple[float, str | None]:
    d = ((s.get("directives") or {}).get(group) or {}).get(attr) or {}
    e = d.get(str(level)) if level is not None else None
    if not e:
        return 1.0, None
    m = _bounded(e.get("multiplier"))
    if m == 1.0:
        return 1.0, None
    return m, (f"{attr}={level}: ×{m:.3f} ({e.get('confidence')} confidence, n={e.get('n')}, "
               f"{e.get('metric')} {e.get('effect_label')}; {s['summary_id']})")


def topic_multiplier(s: dict | None, category) -> tuple[float, list[str]]:
    if not s:
        return 1.0, []
    m, why = _prior(s, "topic", "category", category)
    return m, [why] if why else [f"category={category}: no directive (×1.000; under-tested or no evidence)"]


def format_weights(s: dict | None) -> dict:
    if not s:
        return {}
    d = ((s.get("directives") or {}).get("topic") or {}).get("format") or {}
    return {f"format:{k}": _bounded(v.get("multiplier")) for k, v in d.items() if _bounded(v.get("multiplier")) != 1.0}


def hook_bonus(s: dict | None, form: str, mechanism: str | None) -> tuple[float, list[str]]:
    if not s:
        return 0.0, []
    m1, w1 = _prior(s, "hook", "opening_form", form)
    m2, w2 = _prior(s, "hook", "curiosity_mechanism", (mechanism or "").strip().lower() or None)
    b = max(-MAX_HOOK_BONUS, min(MAX_HOOK_BONUS, HOOK_BONUS_SCALE * (m1 * m2 - 1)))
    return round(b, 3), [w for w in (w1, w2) if w]


def guidance(s: dict | None) -> dict:
    if not s:
        return {"hook": [], "script": []}
    g = (s.get("directives") or {}).get("guidance") or {}
    return {"hook": list(g.get("hook") or []), "script": list(g.get("script") or [])}


def preferred_levels(s: dict | None, attr: str) -> list[str]:
    d = ((s or {}).get("directives") or {}).get("hook", {}).get(attr) or {}
    return sorted(k for k, v in d.items() if _bounded(v.get("multiplier")) > 1.0)


def tested_levels(s: dict | None, attr: str) -> list[str]:
    nx = (s or {}).get("next_experiment") or {}
    return list(nx.get("arms") or []) if nx.get("attribute") == attr else []


def reference(s: dict | None, path=None) -> dict | None:
    if not s:
        return None
    nx = s.get("next_experiment") or {}
    return {"summary_id": s["summary_id"], "sha256": s.get("_sha256") or (sha256_file(path) if path else None),
            "path": s.get("_path") or (str(path) if path else None), "analytics_cutoff": (s.get("inputs") or {}).get("analytics_cutoff"),
            "hypothesis_id": nx.get("hypothesis_id"), "confidence_note": (s.get("policy") or {}).get("summary_confidence")}
