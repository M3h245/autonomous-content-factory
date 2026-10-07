#!/usr/bin/env python3
"""hook-engineering — lint, score and choose the opening hook (HOOK gate).

  hook_lint.py --hooks videos/v01/hook/hooks.json --result videos/v01/hook/result.json [--wps 2.8] [--max-s 3.2] [--weights weights.json]

Hard rules (fail = not selectable): spoken hook ≤ max-s seconds at the language speaking rate, no throat-clearing
openers, no misleading clickbait. Soft rules lower the score. Writes hooks.scored.json with ranking and chosen_id.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import StageResult, emit, exit_for, fix, read_json, stage_main, validate_artifact, write_json  # noqa: E402

ARCHETYPES = {"contradiction", "curiosity_gap", "stakes", "specific_number", "myth_bust", "question", "pov",
              "challenge", "before_after", "story_open", "warning", "comparison"}
OPENERS = re.compile(r"^(hey|hi|hello|welcome|what'?s up|in this video|today (we|i)|so[, ]|let me|did you know|"
                     r"ciao|benvenut|oggi vi|in questo video)\b", re.I)
CLICKBAIT = ["you won't believe", "shocking", "doctors hate", "guaranteed", "100%", "nobody is talking", "insane",
             "mind-blowing", "!!!", "non ci crederai", "scioccante"]
CONTRAST = {"but", "actually", "isn't", "never", "wrong", "instead", "not", "why", "stop", "really", "myth", "should",
            "ma", "invece", "mai", "perché", "sbagliato"}
WPS = {"en": 2.8, "it": 2.7, "es": 2.9, "fr": 2.8, "pt": 2.7, "de": 2.4, "hi": 2.6, "fa": 2.4}


@stage_main("HOOK", "hook-engineering")
def main_cmd(a) -> int:
    d = read_json(a.hooks)
    sr = StageResult("HOOK", "hook-engineering", d.get("video_id"), attempt=a.attempt)
    sr.input(a.hooks, "hooks")
    errs = validate_artifact(d, "hooks")
    if errs:
        sr.fail("HOOK.SCHEMA", "; ".join(errs[:5]), fix=fix("HOOK", "repair_schema"), retryable=True)
        return exit_for(sr.finalize(a.result))
    wts = read_json(a.weights).get("weights", {}) if a.weights else {}
    wps = a.wps or WPS.get(d["language"].split("-")[0], 2.7)
    for c in d["candidates"]:
        words = c["spoken"].split()
        secs = len(words) / wps
        hard, soft = [], []
        if secs > a.max_s:
            hard.append(f"{secs:.1f}s spoken > {a.max_s}s")
        if OPENERS.search(c["spoken"].strip()):
            hard.append("throat-clearing opener")
        if any(x in c["spoken"].lower() or x in c.get("on_screen", "").lower() for x in CLICKBAIT):
            hard.append("misleading clickbait phrasing")
        if len(c.get("on_screen", "").split()) > 6 or len(c.get("on_screen", "")) > 34:
            soft.append("on-screen text too long (≤6 words / 34 chars)")
        if len(c["visual"]) < 12:
            soft.append("visual hook under-specified")
        if c["archetype"] not in ARCHETYPES:
            soft.append(f"unknown archetype {c['archetype']}")
        specific = bool(re.search(r"\d", c["spoken"])) or any(w[:1].isupper() for w in words[1:])
        contrast = bool(CONTRAST & {re.sub(r"[^\w']", "", w.lower()) for w in words})
        score = 50 + 15 * specific + 10 * contrast + max(0, 15 - 3 * max(0, len(words) - 6))
        score += 5 * (c.get("on_screen", "").lower().strip() not in ("", c["spoken"].lower().strip())) - 10 * len(soft)
        c["score"] = round(score * wts.get(f"hook_archetype:{c['archetype']}", 1.0), 1)
        c["est_s"], c["hard_issues"], c["soft_issues"], c["selectable"] = round(secs, 2), hard, soft, not hard
    ok = [c for c in d["candidates"] if c["selectable"]]
    pref = next((c for c in ok if c["id"] == d.get("chosen_id")), None)
    chosen = pref or max(ok, key=lambda c: c["score"], default=None)
    d["chosen_id"] = chosen["id"] if chosen else None
    d["candidates"].sort(key=lambda c: -c["score"])
    out = Path(a.hooks).with_name("hooks.scored.json")
    write_json(out, d)
    sr.check("HOOK.SELECTABLE", chosen is not None, "blocking", "no candidate passes the hard rules",
             fix=fix("HOOK", "regenerate", issues=sorted({i for c in d["candidates"] for i in c["hard_issues"]})))
    arche = {c["archetype"] for c in d["candidates"]}
    sr.check("HOOK.ARCHETYPE_VARIETY", len(arche) >= 3, "major", f"archetypes tried: {sorted(arche)}",
             fix=fix("HOOK", "diversify"))
    if chosen:
        sr.check("HOOK.STRENGTH", chosen["score"] >= 65, "minor", f"chosen hook score {chosen['score']}")
        sr.metric("chosen", {k: chosen[k] for k in ("id", "spoken", "archetype", "score", "est_s")})
    sr.output(out, "hooks_scored", "application/json")
    res = sr.finalize(a.result)
    emit(res)
    return exit_for(res)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hooks", required=True); ap.add_argument("--result", required=True)
    ap.add_argument("--wps", type=float); ap.add_argument("--max-s", type=float, default=3.2)
    ap.add_argument("--weights"); ap.add_argument("--attempt", type=int, default=1)
    return main_cmd(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
