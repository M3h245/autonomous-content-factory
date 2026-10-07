#!/usr/bin/env python3
"""content-research — validate and score a research dossier (RESEARCH gate).

  dossier_tool.py validate --dossier research/dossier.json --result research/result.json [--min-facts 5]

Tiers sources by domain (1 = government/intergovernmental/peer-reviewed, 2 = established newsroom or reference,
3 = other, 4 = social/UGC), then enforces evidence rules: every fact cited; medium-risk facts need a tier ≤2 source;
high-risk facts need a tier-1 source or two independent domains; quotes ≤15 words and ≤1 per source.
Writes dossier.scored.json (tiers added).
"""
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import StageResult, emit, exit_for, fix, read_json, stage_main, validate_artifact, write_json  # noqa: E402

TIER1 = ("who.int", "un.org", "europa.eu", "oecd.org", "worldbank.org", "imf.org", "ipcc.ch", "esa.int", "cern.ch",
         "nature.com", "science.org", "thelancet.com", "nejm.org", "bmj.com", "cell.com", "doi.org", "pnas.org", "plos.org")
TIER2 = ("reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "nytimes.com", "theguardian.com", "economist.com", "ft.com",
         "wsj.com", "nationalgeographic.com", "scientificamerican.com", "newscientist.com", "britannica.com", "bigthink.com",
         "smithsonianmag.com", "arxiv.org", "pubmed.ncbi.nlm.nih.gov", "ansa.it", "corriere.it", "lemonde.fr", "elpais.com")
TIER4 = ("reddit.com", "x.com", "twitter.com", "tiktok.com", "facebook.com", "instagram.com", "quora.com", "youtube.com",
         "medium.com", "pinterest.com", "threads.net")


def domain(url: str) -> str:
    d = urlparse(url).netloc.lower().split(":")[0]
    return d[4:] if d.startswith("www.") else d


def tier(url: str) -> int:
    d = domain(url)
    match = lambda lst: any(d == x or d.endswith("." + x) for x in lst)  # noqa: E731
    if d.endswith((".gov", ".mil", ".edu")) or ".gov." in d or ".edu." in d or match(TIER1):
        return 1
    if match(TIER2):
        return 2
    return 4 if match(TIER4) else 3


@stage_main("RESEARCH", "content-research")
def cmd_validate(a) -> int:
    d = read_json(a.dossier)
    sr = StageResult("RESEARCH", "content-research", attempt=a.attempt)
    sr.input(a.dossier, "dossier")
    errs = validate_artifact(d, "research_dossier")
    if errs:
        sr.fail("RES.SCHEMA", "; ".join(errs[:6]), fix=fix("RESEARCH", "repair_schema"), retryable=True)
        return exit_for(sr.finalize(a.result))
    src = {s["id"]: s for s in d["sources"]}
    for s in d["sources"]:
        s["tier"], s["domain"] = tier(s["url"]), domain(s["url"])
    dangling = sorted({sid for f in d["facts"] for sid in f["source_ids"] if sid not in src})
    sr.check("RES.CITATIONS_RESOLVE", not dangling, "blocking", f"facts cite unknown sources {dangling}",
             fix=fix("RESEARCH", "fix_citations"))
    weak_high, weak_med, long_q, quotes = [], [], [], {}
    for f in d["facts"]:
        cited = [src[s] for s in f["source_ids"] if s in src]
        best = min((s["tier"] for s in cited), default=9)
        if f["risk"] == "high" and not (best == 1 or len({s["domain"] for s in cited}) >= 2):
            weak_high.append(f["id"])
        if f["risk"] == "medium" and best > 2:
            weak_med.append(f["id"])
        q = f.get("quote") or {}
        if q.get("text"):
            if len(q["text"].split()) > 15:
                long_q.append(f["id"])
            quotes[q.get("source_id")] = quotes.get(q.get("source_id"), 0) + 1
    sr.check("RES.HIGH_RISK_CORROBORATED", not weak_high, "blocking",
             f"high-risk facts need a tier-1 source or 2 independent domains: {weak_high}", fix=fix("RESEARCH", "corroborate", facts=weak_high))
    sr.check("RES.MEDIUM_RISK_SOURCED", not weak_med, "major", f"medium-risk facts lack a tier ≤2 source: {weak_med}",
             fix=fix("RESEARCH", "corroborate", facts=weak_med))
    sr.check("RES.QUOTE_LENGTH", not long_q, "blocking", f"quotes over 15 words (paraphrase instead): {long_q}",
             fix=fix("RESEARCH", "paraphrase", facts=long_q))
    multi = [k for k, n in quotes.items() if n > 1]
    sr.check("RES.ONE_QUOTE_PER_SOURCE", not multi, "major", f"sources quoted more than once: {multi}", fix=fix("RESEARCH", "paraphrase"))
    claims = [f["claim"].lower() for f in d["facts"]]
    dups = [(d["facts"][i]["id"], d["facts"][j]["id"]) for i in range(len(claims)) for j in range(i + 1, len(claims))
            if difflib.SequenceMatcher(None, claims[i], claims[j]).ratio() > 0.9]
    sr.check("RES.NO_DUPLICATES", not dups, "minor", f"near-duplicate facts {dups[:4]}")
    sr.check("RES.ENOUGH_FACTS", len(d["facts"]) >= a.min_facts, "major", f"{len(d['facts'])} facts (need ≥ {a.min_facts})",
             len(d["facts"]), a.min_facts, fix("RESEARCH", "expand", min_facts=a.min_facts))
    social = sum(1 for s in d["sources"] if s["tier"] == 4) / len(d["sources"])
    sr.check("RES.SOURCE_QUALITY", social <= 0.5, "major", f"{social:.0%} of sources are social/UGC", round(social, 2), 0.5,
             fix("RESEARCH", "replace_sources"))
    out = Path(a.dossier).with_name("dossier.scored.json")
    write_json(out, d)
    sr.output(out, "dossier_scored", "application/json")
    sr.metric("facts", len(d["facts"])); sr.metric("sources", len(d["sources"]))
    sr.metric("tiers", {t: sum(1 for s in d["sources"] if s["tier"] == t) for t in (1, 2, 3, 4)})
    res = sr.finalize(a.result)
    emit(res)
    return exit_for(res)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--dossier", required=True); v.add_argument("--result", required=True)
    v.add_argument("--min-facts", type=int, default=5); v.add_argument("--attempt", type=int, default=1)
    return cmd_validate(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
