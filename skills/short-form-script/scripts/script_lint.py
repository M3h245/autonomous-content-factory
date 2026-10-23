#!/usr/bin/env python3
"""short-form-script — lint a beat-structured short-form script (SCRIPT gate).

  script_lint.py --script videos/v01/script/script.json --result videos/v01/script/result.json
                 [--dossier research/dossier.json] [--hooks videos/v01/hook/hooks.scored.json] [--min-s 20 --max-s 45]

Checks structure (hook first, payoff/loop ending), estimated spoken duration, claim traceability to the research
dossier, speakability, banned filler, and publish-copy limits. Duration is re-verified on real audio at AUDIO.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import StageResult, emit, exit_for, fix, read_json, stage_main, validate_artifact  # noqa: E402

WPS = {"en": 3.0, "it": 2.8, "es": 3.0, "fr": 2.9, "pt": 2.8, "de": 2.5, "hi": 2.7, "fa": 2.5, "ar": 2.4}
CPS = {"ja": 7.0, "zh": 4.5}
BANNED = ["in this video", "smash that like", "link in bio", "don't forget to subscribe", "hey guys", "without further ado"]
FACTUAL = {"setup", "value", "twist", "payoff"}


def est_seconds(text: str, lang: str) -> float:
    lang = lang.split("-")[0]
    if lang in CPS:
        return len(re.sub(r"\s", "", text)) / CPS[lang]
    return len(text.split()) / WPS.get(lang, 2.8)


@stage_main("SCRIPT", "short-form-script")
def main_cmd(a) -> int:
    s = read_json(a.script)
    sr = StageResult("SCRIPT", "short-form-script", s.get("video_id"), attempt=a.attempt)
    sr.input(a.script, "script")
    errs = validate_artifact(s, "script")
    if errs:
        sr.fail("SCRIPT.SCHEMA", "; ".join(errs[:5]), fix=fix("SCRIPT", "repair_schema"), retryable=True)
        return exit_for(sr.finalize(a.result))
    beats, lang = s["beats"], s["language"]
    sr.check("SCRIPT.HOOK_FIRST", beats[0]["role"] == "hook", "blocking", "first beat must be the hook",
             fix=fix("SCRIPT", "restructure"))
    if a.hooks and Path(a.hooks).exists():
        h = read_json(a.hooks)
        chosen = next((c for c in h["candidates"] if c["id"] == h.get("chosen_id")), None)
        norm = lambda t: re.sub(r"[^\w ]", "", t.lower()).strip()  # noqa: E731
        sr.check("SCRIPT.HOOK_MATCH", chosen is None or norm(chosen["spoken"]) == norm(beats[0]["text"]), "major",
                 "opening line must be the chosen hook verbatim", fix=fix("SCRIPT", "use_chosen_hook"))
    total = sum(est_seconds(b["text"], lang) for b in beats) + 0.2 * (len(beats) - 1)
    sr.check("SCRIPT.DURATION", a.min_s <= total <= a.max_s, "major", f"≈{total:.1f}s spoken", round(total, 1),
             [a.min_s, a.max_s], fix("SCRIPT", "shorten" if total > a.max_s else "lengthen",
                                     target_s=a.max_s * 0.9 if total > a.max_s else a.min_s * 1.1))
    unlinked = [b["id"] for b in beats if b["role"] in FACTUAL and not b.get("claim_ids") and not b.get("opinion")]
    sr.check("SCRIPT.CLAIMS_LINKED", not unlinked, "major", f"factual beats without claim_ids: {unlinked}",
             fix=fix("SCRIPT", "link_claims", beats=unlinked))
    if a.dossier:
        facts = {f["id"] for f in read_json(a.dossier)["facts"]}
        bad = sorted({c for b in beats for c in b.get("claim_ids", []) if c not in facts})
        sr.check("SCRIPT.CLAIMS_EXIST", not bad, "blocking", f"claim ids not in dossier: {bad}", fix=fix("SCRIPT", "link_claims"))
    long_s = [x for b in beats for x in re.split(r"(?<=[.!?])\s+", b["text"]) if len(x.split()) > 24]
    sr.check("SCRIPT.SPEAKABLE", not long_s, "minor", f"sentences over 24 words: {[x[:40] for x in long_s]}")
    full = " ".join(b["text"] for b in beats).lower()
    hits = [p for p in BANNED if p in full]
    sr.check("SCRIPT.NO_FILLER", not hits, "major", f"filler phrases {hits}", fix=fix("SCRIPT", "remove_filler", phrases=hits))
    sr.check("SCRIPT.ENDING", beats[-1]["role"] in ("payoff", "cta", "loop"), "minor", "end on payoff, CTA or loop")
    titles = s["publish"]["title_options"]
    sr.check("SCRIPT.TITLE_LENGTH", all(len(t) <= 100 for t in titles), "major", "titles ≤ 100 characters",
             fix=fix("SCRIPT", "retitle", max_chars=100))
    tags = s["publish"]["hashtags"]
    # v3.3: cap kept far below YouTube's own limit — "more than 60 hashtags, we'll ignore each hashtag"; over-tagging
    # "may result in the removal of your video … from search" (support.google.com/youtube/answer/6390658). Only the
    # first ~3 description hashtags are shown next to the title, so relevance, not count, is the goal.
    sr.check("SCRIPT.HASHTAGS", 1 <= len(tags) <= 8 and all(t.startswith("#") for t in tags), "minor",
             f"{len(tags)} hashtags (relevant only; YouTube shows ~3, ignores all past 60 and can remove over-tagged videos)")
    sr.check("SCRIPT.NO_HASH_IN_TITLE", not any("#" in t for t in titles), "major",
             "no # in the title (hashtags belong in the description; a title hashtag is not promoted)",
             fix=fix("SCRIPT", "retitle", max_chars=100))
    sr.check("SCRIPT.ON_SCREEN", all(len(b.get("on_screen", "")) <= 34 for b in beats), "minor", "on-screen text ≤ 34 chars")
    sr.metric("est_duration_s", round(total, 1)); sr.metric("beats", len(beats))
    sr.metric("words", sum(len(b["text"].split()) for b in beats))
    res = sr.finalize(a.result)
    emit(res)
    return exit_for(res)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--script", required=True); ap.add_argument("--result", required=True)
    ap.add_argument("--dossier"); ap.add_argument("--hooks")
    ap.add_argument("--min-s", type=float, default=20); ap.add_argument("--max-s", type=float, default=45)
    ap.add_argument("--attempt", type=int, default=1)
    return main_cmd(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
