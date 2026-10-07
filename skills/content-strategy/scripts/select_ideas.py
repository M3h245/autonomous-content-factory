#!/usr/bin/env python3
"""content-strategy — IDEATION gate (validate the idea pool) and SELECTION (score, de-duplicate, diversify).

  select_ideas.py validate --ideas ideation/ideas.json --count N [--dossier research/dossier.json] --result ideation/result.json
  select_ideas.py select   --ideas ideation/ideas.json --count N --out selection/selection.json --result selection/result.json
                           [--caps capabilities.json] [--history history.json] [--trends research/trends.json] [--weights weights.json]

Selection = weighted rubric × learned weights + trend boost, hard filters (brand safety, feasibility with the
capabilities verified on this machine, novelty vs. past videos), then maximal-marginal-relevance so the batch is
varied in format and angle — the main defence against "mass-produced / repetitive" channel patterns.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import StageResult, emit, exit_for, fix, read_json, stage_main, validate_artifact, write_json  # noqa: E402

RUBRIC = {"audience_value": 0.25, "curiosity": 0.20, "originality": 0.20, "evidence_strength": 0.15,
          "visual_potential": 0.10, "brand_safety": 0.10}


def grams(t: str) -> Counter:
    t = re.sub(r"\s+", " ", re.sub(r"[^\w ]", "", t.lower())).strip()
    return Counter(t[i:i + 3] for i in range(max(0, len(t) - 2)))


def cos(a: Counter, b: Counter) -> float:
    num = sum(a[k] * b[k] for k in a.keys() & b.keys())
    den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return num / den if den else 0.0


def text(i: dict) -> str:
    return f"{i['title']} {i['angle']}"


@stage_main("IDEATION", "content-strategy")
def cmd_validate(a) -> int:
    d = read_json(a.ideas)
    sr = StageResult("IDEATION", "content-strategy", attempt=a.attempt)
    sr.input(a.ideas, "ideas")
    errs = validate_artifact(d, "ideas")
    if errs:
        sr.fail("IDEA.SCHEMA", "; ".join(errs[:6]), fix=fix("IDEATION", "repair_schema"), retryable=True)
        return exit_for(sr.finalize(a.result))
    ideas = d["ideas"]
    need = max(3, 2 * a.count)
    sr.check("IDEA.POOL_SIZE", len(ideas) >= need, "major", f"{len(ideas)} ideas; generate ≥ {need} (2× the requested count)",
             len(ideas), need, fix("IDEATION", "expand", n_more=need - len(ideas)))
    fmts = Counter(i["format"] for i in ideas)
    sr.check("IDEA.FORMAT_VARIETY", len(fmts) >= min(3, a.count + 1), "major", f"formats {dict(fmts)}",
             fix=fix("IDEATION", "diversify_formats"))
    if a.dossier:
        facts = {f["id"] for f in read_json(a.dossier)["facts"]}
        bad = [i["id"] for i in ideas if any(f not in facts for f in i["fact_ids"])]
        sr.check("IDEA.FACTS_RESOLVE", not bad, "blocking", f"ideas citing unknown fact ids: {bad}", fix=fix("IDEATION", "relink_facts"))
        thin = [i["id"] for i in ideas if i["format"] != "question" and len(i["fact_ids"]) < 1]
        sr.check("IDEA.EVIDENCE", not thin, "major", f"ideas without supporting facts: {thin}", fix=fix("IDEATION", "relink_facts"))
    g = [grams(text(i)) for i in ideas]
    dups = [(ideas[x]["id"], ideas[y]["id"]) for x in range(len(ideas)) for y in range(x + 1, len(ideas)) if cos(g[x], g[y]) > 0.8]
    sr.check("IDEA.DISTINCT", not dups, "major", f"near-duplicate ideas {dups[:4]}", fix=fix("IDEATION", "dedupe"))
    sr.metric("ideas", len(ideas)); sr.metric("formats", dict(fmts))
    res = sr.finalize(a.result)
    emit(res)
    return exit_for(res)


@stage_main("SELECTION", "content-strategy")
def cmd_select(a) -> int:
    ideas = read_json(a.ideas)["ideas"]
    sr = StageResult("SELECTION", "content-strategy", attempt=a.attempt)
    w = (read_json(a.weights).get("weights", {}) if a.weights else {})
    caps = read_json(a.caps)["capabilities"] if a.caps else {}
    avail = {k for k, v in caps.items() if v.get("available") in (True, "agent-tool")}
    hist = [grams(x["text"]) for x in read_json(a.history).get("items", [])] if a.history else []
    trends = read_json(a.trends)["signals"] if a.trends else []
    rows, rejected = [], []
    for i in ideas:
        sc = i["scores"]
        base = sum(RUBRIC[k] * (sc[k] - 1) / 4 for k in RUBRIC)
        mult = w.get(f"format:{i['format']}", 1.0) * w.get(f"pillar:{i.get('pillar')}", 1.0)
        tb = max((t["score"] for t in trends for term in i.get("trend_terms", []) if term.lower() in t["term"].lower()), default=0)
        final = base * mult + 0.1 * tb / 100
        novelty = 1 - max((cos(grams(text(i)), h) for h in hist), default=0.0)
        missing = [c for c in i.get("required_capabilities", []) if caps and c not in avail]
        why = ("brand safety below 3" if sc["brand_safety"] < 3 else f"needs unavailable capabilities {missing}" if missing
               else f"too similar to past content (novelty {novelty:.2f})" if novelty < 0.35 else None)
        (rejected if why else rows).append({"idea_id": i["id"], "reason": why} if why else
                                           {"idea": i, "final": final, "novelty": round(novelty, 3)})
    chosen = []
    while rows and len(chosen) < a.count:  # maximal marginal relevance: quality vs. similarity to already chosen
        def mmr(r):
            sim = max((cos(grams(text(r["idea"])), grams(text(c["idea"]))) + (0.15 if r["idea"]["format"] == c["idea"]["format"] else 0)
                       for c in chosen), default=0.0)
            return 0.75 * r["final"] - 0.25 * sim
        best = max(rows, key=mmr)
        chosen.append(best)
        rows.remove(best)
    rejected += [{"idea_id": r["idea"]["id"], "reason": "lower marginal score"} for r in rows]
    sel = {"selected": [{"rank": k + 1, "video_id": f"v{k + 1:02d}", "idea_id": c["idea"]["id"], "title": c["idea"]["title"],
                         "format": c["idea"]["format"], "final_score": round(c["final"], 4), "novelty": c["novelty"]}
                        for k, c in enumerate(chosen)], "rejected": rejected}
    write_json(a.out, sel)
    sr.check("SEL.COUNT", len(chosen) == a.count, "blocking", f"selected {len(chosen)}/{a.count}", len(chosen), a.count,
             fix("IDEATION", "expand", n_more=2 * (a.count - len(chosen))))
    fmts = {c["idea"]["format"] for c in chosen}
    sr.check("SEL.FORMAT_VARIETY", a.count < 3 or len(fmts) >= 2, "major", f"formats in batch {sorted(fmts)}",
             fix=fix("IDEATION", "diversify_formats"))
    sr.check("SEL.NOVELTY", all(c["novelty"] >= 0.5 for c in chosen), "minor", "some picks are close to past videos")
    sr.output(a.out, "selection", "application/json")
    sr.metric("selected", [c["idea"]["id"] for c in chosen]); sr.metric("rejected", len(rejected))
    res = sr.finalize(a.result)
    emit(res)
    return exit_for(res)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--ideas", required=True); v.add_argument("--count", type=int, required=True)
    v.add_argument("--dossier"); v.add_argument("--result", required=True); v.add_argument("--attempt", type=int, default=1)
    s = sub.add_parser("select")
    for k in ("--ideas", "--out", "--result"):
        s.add_argument(k, required=True)
    s.add_argument("--count", type=int, required=True)
    for k in ("--caps", "--history", "--trends", "--weights"):
        s.add_argument(k)
    s.add_argument("--attempt", type=int, default=1)
    a = ap.parse_args()
    return {"validate": cmd_validate, "select": cmd_select}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
