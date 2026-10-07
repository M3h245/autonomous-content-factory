#!/usr/bin/env python3
"""cta — Phase 3.5 CTA contract, policy and deterministic placement gates (shared by SCRIPT and VIDEO).

A script may carry one `cta` object (contract `script.cta`, optional):
  {"needed": false, "decision_reason": "…"}                                   — a deliberate no-CTA decision, or
  {"needed": true, "decision_reason": "…", "type": follow|subscribe|like|comment|save|share|part_2|question|profile,
   "placement": "after_payoff" | "integrated" | "on_screen_only", "modality": "spoken" | "on_screen" | "both",
   "beat_id": "<beat carrying it>", "spoken": "<exact sentence(s) inside that beat>", "on_screen": "<≤6 words>",
   "continuation": "<what part 2 answers>" (part_2 only)}
- after_payoff: its own beat (role "cta") after the payoff beat (and before a loop beat, if any)
- integrated: the CTA sentence lives inside a content beat after the payoff (e.g. the loop line asks the question)
- on_screen_only: no spoken words; an on-screen label during the given beat

`check(script, sentences, duration, ...)` runs on any timeline: the calibrated estimate at SCRIPT, the real TTS
timing at VIDEO. Every rule returns a check with id, severity and evidence; nothing here is a taste judgement.

Platform notes (verified 2026-10-07): YouTube end screens need videos ≥25 s and the end-screen help page does not
cover Shorts; Shorts link onward through a "related video" set in YouTube Studio (shown below the channel handle,
advanced feature access). So no end-screen zone is reserved; a part_2 / watch-next CTA adds a manual upload step.
"""
from __future__ import annotations

import json
import re

TYPES = {"follow", "subscribe", "like", "comment", "save", "share", "part_2", "question", "profile"}
PLACEMENTS = {"after_payoff", "integrated", "on_screen_only"}
MODALITIES = {"spoken", "on_screen", "both"}
GENERIC = ["smash that like", "like and subscribe", "don't forget to", "dont forget to", "hit the bell", "hit that bell",
           "see you in the next", "thanks for watching", "thank you for watching", "make sure to subscribe",
           "subscribe for more", "follow for more", "like for more"]
# words that mark a sentence as a CTA (used to find undeclared CTAs elsewhere in the script)
CTA_MARKERS = r"\b(subscribe|follow (me|us|for)|like (this|the) video|comment (below|down)|in the comments|tell me in|" \
              r"save (this|it) for|share (this|it) with|send (this|it) to|part 2|part two|link in (my )?(bio|profile))\b"
STOP = set("a an the and or but so of to in on at for with is are was were be it its this that you your we they i as by from "
           "do does did can will just me my more what which who".split())
LIMITS = {"hook_window_s": 3.2, "max_spoken_s": 2.8, "max_share_of_runtime": 0.12, "on_screen_min_s": 1.2,
          "on_screen_max_s": 3.5, "max_tail_after_cta_s": 1.2, "short_video_s": 20.0, "repeat_similarity": 0.6}


def words(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", t.lower()) if w not in STOP and len(w) > 2}


def jaccard(a: str, b: str) -> float:
    x, y = words(a), words(b)
    return len(x & y) / max(1, len(x | y))


def validate(cta: dict | None, script: dict) -> list[str]:
    if cta is None:
        return []
    errs = []
    if not isinstance(cta.get("needed"), bool):
        errs.append("cta.needed must be true/false")
    if not str(cta.get("decision_reason", "")).strip():
        errs.append("cta.decision_reason is required (why a CTA is or is not used)")
    if not cta.get("needed"):
        return errs
    if cta.get("type") not in TYPES:
        errs.append(f"cta.type must be one of {sorted(TYPES)}")
    if cta.get("placement") not in PLACEMENTS:
        errs.append(f"cta.placement must be one of {sorted(PLACEMENTS)}")
    if cta.get("modality") not in MODALITIES:
        errs.append(f"cta.modality must be one of {sorted(MODALITIES)}")
    beats = {b["id"]: b for b in script["beats"]}
    b = beats.get(cta.get("beat_id"))
    if not b:
        errs.append(f"cta.beat_id '{cta.get('beat_id')}' is not a beat")
    spoken_needed = cta.get("modality") in ("spoken", "both") and cta.get("placement") != "on_screen_only"
    if spoken_needed:
        if not str(cta.get("spoken", "")).strip():
            errs.append("a spoken CTA needs cta.spoken")
        elif b and norm(cta["spoken"]) not in norm(b["text"]):
            errs.append("cta.spoken must appear verbatim in its beat")
    if cta.get("placement") == "on_screen_only" and cta.get("modality") != "on_screen":
        errs.append("placement on_screen_only requires modality on_screen")
    if cta.get("modality") in ("on_screen", "both"):
        ost = str(cta.get("on_screen", "")).strip()
        if not ost or len(ost.split()) > 6:
            errs.append("cta.on_screen must be 1-6 words")
    if cta.get("placement") == "after_payoff" and b and b.get("role") != "cta":
        errs.append("placement after_payoff needs its own beat with role 'cta'")
    if cta.get("type") == "part_2" and not str(cta.get("continuation", "")).strip():
        errs.append("a part_2 CTA must say what part 2 answers (cta.continuation)")
    return errs


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]", " ", t.lower())).strip()


def cta_window(cta: dict, script: dict, sentences: list[dict]) -> tuple[float, float] | None:
    """[start, end] of the CTA on the timeline: its spoken sentence(s), or its beat for on-screen-only CTAs."""
    if not cta or not cta.get("needed"):
        return None
    beat_sents = [s for s in sentences if s["beat_id"] == cta.get("beat_id")]
    if not beat_sents:
        return None
    if cta.get("placement") == "on_screen_only" or cta.get("modality") == "on_screen":
        return beat_sents[0]["start"], beat_sents[-1]["end"]
    target = norm(cta.get("spoken", ""))
    hit = [s for s in beat_sents if norm(s["text"]) and norm(s["text"]) in target]
    hit = hit or beat_sents
    return hit[0]["start"], hit[-1]["end"]


def recommend(script: dict, duration_s: float) -> dict:
    """Deterministic policy envelope (the author still decides): what kinds of CTA this video can carry safely."""
    roles = [b.get("role") for b in script["beats"]]
    loop = "loop" in roles
    out = {"spoken_ok": duration_s >= LIMITS["short_video_s"], "loop_ending": loop,
           "placement_ok": ["integrated", "on_screen_only"] + ([] if duration_s < LIMITS["short_video_s"] else ["after_payoff"]),
           "notes": []}
    if loop:
        out["notes"].append("loop ending: the loop line must stay last — CTA goes before it or rides on it (integrated question / on-screen)")
    if not out["spoken_ok"]:
        out["notes"].append(f"under {LIMITS['short_video_s']:.0f} s: no spoken CTA beat; on-screen or integrated only")
    return out


def check(script: dict, sentences: list[dict], duration_s: float, *, labels: list[dict] | None = None,
          history: list[str] | None = None, topic: str = "", title: str = "", timeline: str = "estimate") -> dict:
    """Deterministic CTA gates on a timeline. Returns {"cta": …, "window": …, "checks": [...], "metrics": {...}}."""
    cta = script.get("cta")
    checks: list[dict] = []

    def c(cid, ok, sev, ev):
        checks.append({"id": cid, "passed": bool(ok), "severity": sev, "evidence": ev})

    errs = validate(cta, script)
    c("CTA.SCHEMA", not errs, "blocking", "; ".join(errs) or ("no CTA object" if cta is None else "valid"))
    beats = script["beats"]
    roles = {b["id"]: b.get("role") for b in beats}
    declared = cta.get("beat_id") if cta and cta.get("needed") else None
    undeclared = [b["id"] for b in beats if re.search(CTA_MARKERS, b["text"].lower()) and
                  not (declared == b["id"])]
    c("CTA.SINGLE", not undeclared, "major", f"CTA-like sentences outside the declared CTA: {undeclared}" if undeclared else
      "at most one CTA, declared")
    metrics = {"present": bool(cta and cta.get("needed")), "type": (cta or {}).get("type"), "timeline": timeline}
    if not cta or not cta.get("needed") or errs:
        if cta is not None and not cta.get("needed"):
            metrics["decision_reason"] = cta.get("decision_reason")
        return {"cta": cta, "window": None, "checks": checks, "metrics": metrics}
    win = cta_window(cta, script, sentences)
    start, end = win if win else (0.0, 0.0)
    metrics.update(start_s=round(start, 2), end_s=round(end, 2), duration_s=round(end - start, 2))
    order = [b["id"] for b in beats]
    payoff = [b["id"] for b in beats if b.get("role") == "payoff"]
    pay_end = max((s["end"] for s in sentences if s["beat_id"] in payoff), default=None)
    hook_end = max((s["end"] for s in sentences if roles.get(s["beat_id"]) == "hook"), default=0.0)
    # 1 never in the hook window
    c("CTA.NOT_IN_HOOK", roles.get(cta["beat_id"]) != "hook" and start >= max(LIMITS["hook_window_s"], hook_end), "blocking",
      f"CTA starts {start:.2f}s; hook ends {hook_end:.2f}s")
    # 2 never before or inside the payoff
    c("CTA.AFTER_PAYOFF", bool(payoff) and roles.get(cta["beat_id"]) != "payoff" and pay_end is not None and start >= pay_end - 0.01,
      "blocking", f"CTA starts {start:.2f}s; payoff ends {pay_end if pay_end is None else round(pay_end, 2)}s"
      + ("" if payoff else " (script has no payoff beat)"))
    # 3 duration
    spoken = cta.get("modality") in ("spoken", "both") and cta.get("placement") != "on_screen_only"
    if spoken:
        cap = min(LIMITS["max_spoken_s"], LIMITS["max_share_of_runtime"] * duration_s)
        c("CTA.DURATION", end - start <= cap, "major", f"spoken CTA {end - start:.2f}s (cap {cap:.2f}s = min 2.8 s, 12 % of runtime)")
        c("CTA.SHORT_VIDEO", duration_s >= LIMITS["short_video_s"] or cta.get("placement") == "integrated", "major",
          f"{duration_s:.1f}s video: a separate spoken CTA beat needs ≥{LIMITS['short_video_s']:.0f} s")
    else:
        d = end - start
        # an on-screen label riding on an integrated content beat may stay for that beat; a standalone one is capped
        cap = None if cta.get("placement") == "integrated" else LIMITS["on_screen_max_s"]
        c("CTA.DURATION", d >= LIMITS["on_screen_min_s"] and (cap is None or d <= cap), "major",
          f"on-screen CTA visible {d:.2f}s (needs ≥{LIMITS['on_screen_min_s']} s" + (f", ≤{cap} s)" if cap else ")"))
    # 4 ending: loop stays last; no dead tail; the video still ends well without the CTA
    loop_ids = [b for b in order if roles.get(b) == "loop"]
    if loop_ids:
        after_loop = order.index(cta["beat_id"]) > order.index(loop_ids[-1])
        ok = not after_loop or not spoken
        c("CTA.ENDING", ok, "blocking", "a spoken CTA after the loop line breaks the loop" if not ok else
          "loop line stays last" if cta["beat_id"] != loop_ids[-1] else "CTA rides on the loop line")
    else:
        tail = duration_s - end
        c("CTA.ENDING", tail <= LIMITS["max_tail_after_cta_s"] or order.index(cta["beat_id"]) < len(order) - 1, "blocking",
          f"{tail:.2f}s after the CTA (≤{LIMITS['max_tail_after_cta_s']} s when the CTA closes the video)")
    rest = [b for b in beats if not (cta.get("placement") == "after_payoff" and b["id"] == cta["beat_id"])]
    last = rest[-1] if rest else None
    remaining = norm(last["text"]).replace(norm(cta.get("spoken", "")), "").strip() if last else ""
    c("CTA.STANDALONE_ENDING", bool(last) and last.get("role") in ("payoff", "loop") and len(remaining.split()) >= 2, "blocking",
      f"without the CTA the video ends on beat {last['id'] if last else None} ({last.get('role') if last else None}): "
      f"'{remaining[:60]}'")
    # 5 relevance + not generic + not repeated
    text = " ".join(x for x in (cta.get("spoken", ""), cta.get("on_screen", "")) if x)
    generic = [g for g in GENERIC if g in text.lower()]
    body = " ".join(b["text"] for b in beats if b["id"] != cta["beat_id"]) + " " + topic + " " + title
    overlap = sorted(words(text) & words(body))
    c("CTA.RELEVANCE", bool(overlap) and not generic, "major",
      f"shares {overlap[:5]} with the video" + (f"; generic phrases {generic}" if generic else "") if overlap or generic
      else "no word in common with the video (generic outro)")
    sims = [(h, round(jaccard(text, h), 2)) for h in history or []]
    rep = [s for s in sims if s[1] >= LIMITS["repeat_similarity"]]
    c("CTA.NOT_REPEATED", not rep, "major", f"too close to earlier CTAs: {rep[:2]}" if rep else f"checked against {len(sims)} earlier CTAs")
    # 6 on-screen CTA must really be on screen during its window (VIDEO only — needs the visual audit labels)
    if labels is not None and cta.get("modality") in ("on_screen", "both"):
        want = norm(cta.get("on_screen", ""))
        seen = [lb for lb in labels if norm(lb["text"]) == want and start - 0.6 <= lb["at_s"] <= end + 0.3]
        c("CTA.ON_SCREEN_SHOWN", bool(seen), "major", f"label '{cta.get('on_screen')}' appears at "
          f"{[lb['at_s'] for lb in labels if norm(lb['text']) == want]} (window {start:.2f}-{end:.2f}s)")
    if cta.get("type") == "part_2":
        metrics["manual_upload_step"] = "set the YouTube Shorts 'related video' to part 2 in YouTube Studio (advanced features)"
    metrics["recommendation"] = recommend(script, duration_s)
    return {"cta": cta, "window": [round(start, 3), round(end, 3)], "checks": checks, "metrics": metrics}


def main() -> int:
    import argparse
    import sys
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--script", required=True); ap.add_argument("--timing", required=True)
    a = ap.parse_args()
    s, t = json.load(open(a.script, encoding="utf-8")), json.load(open(a.timing, encoding="utf-8"))
    print(json.dumps(check(s, t["sentences"], t["duration_s"], timeline="actual"), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
