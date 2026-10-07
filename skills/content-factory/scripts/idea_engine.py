#!/usr/bin/env python3
"""idea_engine — the batch layer above the V3.0.1 production engine (no LLM API needed).

  idea_engine.py validate --ideas-file input/ideas.json
  idea_engine.py select   [--ideas-file input/ideas.json] [--batches-dir batches] [--db factory.db]
  idea_engine.py run      [--ideas-file input/ideas.json] [--batches-dir …] [--db …] [--output-dir D:\\shorts]
                          [--produce claude|none] [--driver-cmd "CMD … {run} …"] [--run-timeout-min 180]
  idea_engine.py produce  --batch batches/<batch-id> [--output-dir …] [--produce …] [--driver-cmd …]

~50 topic candidates written elsewhere (by hand, or by asking ChatGPT/Claude for the JSON format in
references/idea-engine.md) → validation → content-memory filter (the factory's own database and rules) → offline
research screen → deterministic, explainable scoring → diversity selection of exactly 5 → batch manifest → 5 isolated
V3.0.1 runs (`factory.py init`, one topic each) → production of each run by the existing unattended driver
(`claude -p /content-factory …`, the same as automation-engineering's run_factory templates) → each verified
publishing package copied to the output directory → report.

V3.0.1 stays the single source of truth for research, hooks, scripts, voice, visuals, audio, captions, QA, review,
packaging, media metadata, platform disclosure and memory ingest. Nothing here changes how a video is made.

Exit: 0 done · 2 invalid input, fewer than 5 usable candidates, or a production run that did not deliver (report) ·
3 environment not ready (no memory, no driver) — runs prepared so far are kept for `produce`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parents[1]
for _p in (HERE, SKILLS / "content-database" / "scripts", SKILLS / "content-strategy" / "scripts",
           SKILLS / "content-research" / "scripts", SKILLS / "hook-engineering" / "scripts"):
    sys.path.insert(0, str(_p))
import cfdb  # noqa: E402   content memory: topic_repeats (init's rule), corpus (SELECTION's novelty corpus)
import factory  # noqa: E402   V3.0.1 state machine: load, next_action, FileLock, PASSED
from cf_common import now_iso, read_json, write_json  # noqa: E402
from dossier_tool import domain as src_domain, tier as src_tier  # noqa: E402   source tiers of the RESEARCH gate
from hook_engine import jaccard as hook_jaccard  # noqa: E402   the HOOK gate's past-hook similarity
from hook_lint import CLICKBAIT, CONTRAST, OPENERS, WPS  # noqa: E402   hook hard/soft rules
from select_ideas import cos, grams  # noqa: E402   SELECTION's similarity

ENGINE_VERSION = "1.0"
FILE_VERSION = "1.0"
WINNERS = 5
NOVELTY_MIN = 0.35          # content-strategy SELECTION: an idea closer than this to past content is rejected
HOOK_REPEAT = 0.6           # hook engine: a hook this close to a used one is never selected again
QUALITY_FLOOR = 0.40        # below this total a candidate is not worth a production run (a bare topic scores ≈0.45)
EXPECTED = (30, 80)         # "about 50": outside this range the report warns (no candidate is dropped for it)
MAX_CANDIDATES = 500
ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
FIELDS = {"id", "topic", "angle", "hook", "visual", "category", "source_hint", "notes"}
CATEGORIES = {"curiosity", "science", "everyday", "psychology", "technology", "nature", "human_body", "space", "history",
              "engineering", "strange_facts", "counterintuitive", "discoveries", "common_questions", "visual_phenomena"}
WEIGHTS = {"novelty": 0.15, "curiosity": 0.15, "hook_potential": 0.15, "visual_potential": 0.12, "clarity": 0.10,
           "short_form_fit": 0.10, "payoff": 0.10, "factual_confidence": 0.08, "research_quality": 0.05}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

# ---- lexicons for the offline screen and the scoring (deterministic; documented in references/idea-engine.md)
VISUAL = set("""animal bird fish cat dog flamingo octopus shark whale bee ant insect spider snake frog plant tree flower leaf
seed fruit root body brain heart eye ear nose tongue skin bone muscle blood finger hand foot tooth teeth hair stomach lung
cell water ice fire flame light shadow colour color rainbow cloud rain snow wind lightning thunder storm wave ocean sea
river lake volcano earthquake mountain sand rock stone crystal magnet battery engine wheel gear bridge plane wing rocket
satellite planet moon sun star comet galaxy orbit telescope clock mirror glass bubble balloon coffee tea bread egg salt
sugar onion lemon milk honey candle smoke steam metal gold iron rust paper sound echo bell string spring""".split())
ABSTRACT = set("""economy economics inflation policy politics philosophy meaning ethics morality consciousness law laws society
culture ideology theory justice value values rights government""".split())
RISK_HIGH = set("""cure cures treat treatment dose dosage medicine medication drug drugs disease cancer diabetes vaccine
diet supplement weight-loss invest investing investment stock stocks crypto bitcoin loan tax taxes legal lawsuit illegal
suicide poison overdose surgery pregnancy""".split())
EXAGGERATION = re.compile(r"\b(always|never fails|everyone|nobody|100%|proven|guaranteed|miracle|cures?|secret (they|that)|"
                          r"will change your life|the only|forever)\b", re.I)
LISTY = re.compile(r"\b(top \d+|\d+ (facts|things|reasons|ways)|everything (about|you)|history of|complete guide|explained in full)\b",
                   re.I)
MECHANISM = re.compile(r"\b(because|reason|turns out|actually|the trick|secret|mechanism|causes?|thanks to|which means|"
                       r"so that|works by|happens when)\b", re.I)
EXPLAINS = re.compile(r"\b(because|so|which|reason|means|causes?|thanks to|turns out|by|when)\b", re.I)
SURPRISE = re.compile(r"\b(actually|turns out|surprising|secret|myth|wrong|despite|even|weird|strange|backwards)\b", re.I)
RELATABLE = re.compile(r"\b(you|your|we|our|everyday|every day|people|home|kitchen)\b", re.I)
QUESTION = re.compile(r"^(why|how|what|can|does|do|is|are|where|when|which|who)\b", re.I)


class BatchRefused(Exception):
    """A batch that must not be produced (edited manifest, wrong folder, changed input): exit 2 with the reason."""
    def __init__(self, why: str, error: str = "STALE_MANIFEST", **info):
        super().__init__(why)
        self.payload = {"error": error, "why": why, **info}


class IdeaFileError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def canonical(o) -> str:
    return json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# ----------------------------------------------------------------------------- input
def parse_ideas(raw: bytes) -> tuple[dict, list[dict], list[str]]:
    """→ (document, candidates [each with 'valid' and 'problems'], file warnings). File-level problems (not JSON,
    no candidates list, wrong version, duplicate ids, too many candidates) raise IdeaFileError with every problem
    found. A candidate-level problem (missing or empty topic, wrong types) marks only that candidate invalid — it is
    kept and reported, never silently dropped."""
    problems = []
    text = raw.decode("utf-8-sig", errors="strict") if raw else ""

    def no_dup_keys(pairs):
        keys = [k for k, _ in pairs]
        dup = sorted({k for k in keys if keys.count(k) > 1})
        if dup:
            raise ValueError(f"duplicate key(s) {dup} in one object")
        return dict(pairs)
    try:
        doc = json.loads(text, object_pairs_hook=no_dup_keys)
    except json.JSONDecodeError as e:
        raise IdeaFileError([f"not valid JSON: {e.msg} at line {e.lineno}, column {e.colno}"]) from None
    except ValueError as e:
        raise IdeaFileError([f"not valid JSON: {e}"]) from None
    if not isinstance(doc, dict):
        raise IdeaFileError(["the file must be a JSON object with \"version\" and \"candidates\""])
    if doc.get("version") != FILE_VERSION:
        problems.append(f"\"version\" must be \"{FILE_VERSION}\" (found {doc.get('version')!r})")
    cands = doc.get("candidates")
    if not isinstance(cands, list) or not cands:
        problems.append("\"candidates\" must be a non-empty list")
        raise IdeaFileError(problems)
    if len(cands) > MAX_CANDIDATES:
        problems.append(f"{len(cands)} candidates (more than {MAX_CANDIDATES}); split the file")
    ids = [c.get("id") if isinstance(c, dict) else None for c in cands]
    dup = sorted({i for i in ids if isinstance(i, str) and ids.count(i) > 1})
    if dup:
        problems.append(f"duplicate candidate id(s): {dup}")
    bad_ids = [f"#{n + 1}" for n, i in enumerate(ids) if not (isinstance(i, str) and ID_RE.match(i))]
    if bad_ids:
        problems.append(f"candidate(s) {bad_ids[:10]} need an \"id\" of 1-64 letters, digits, '.', '_' or '-'")
    if problems:
        raise IdeaFileError(problems)
    out = []
    for n, c in enumerate(cands):
        p = []
        if not isinstance(c, dict):
            out.append({"id": f"#{n + 1}", "position": n + 1, "valid": False, "problems": ["not a JSON object"]})
            continue
        topic = c.get("topic")
        if not isinstance(topic, str) or not topic.strip():
            p.append("missing or empty \"topic\"")
        elif len(topic.strip()) > 200:
            p.append("\"topic\" longer than 200 characters")
        for k, lim in (("angle", 400), ("hook", 200), ("visual", 300), ("category", 40), ("notes", 400)):
            v = c.get(k)
            if v is not None and not isinstance(v, str):
                p.append(f"\"{k}\" must be a string or null")
            elif isinstance(v, str) and len(v) > lim:
                p.append(f"\"{k}\" longer than {lim} characters")
        sh = c.get("source_hint")
        if sh is not None and not (isinstance(sh, str) or (isinstance(sh, list) and all(isinstance(x, str) for x in sh))):
            p.append("\"source_hint\" must be null, a string or a list of strings")
        unknown = sorted(set(c) - FIELDS)
        norm = {k: (c.get(k).strip() if isinstance(c.get(k), str) else c.get(k)) for k in FIELDS if k in c}
        norm["source_hint"] = ([norm["source_hint"]] if isinstance(norm.get("source_hint"), str) else norm.get("source_hint")) or []
        norm["source_hint"] = [s.strip() for s in norm["source_hint"] if isinstance(s, str) and s.strip()]
        out.append({**norm, "position": n + 1, "valid": not p, "problems": p,
                    "warnings": [f"unknown field(s) {unknown} ignored"] if unknown else []})
    warns = []
    if not EXPECTED[0] <= len(cands) <= EXPECTED[1]:
        warns.append(f"{len(cands)} candidates supplied; about 50 work best (the engine still processes all of them)")
    return doc, out, warns


# ----------------------------------------------------------------------------- memory (the factory's own database)
def resolve_db(arg: str | None) -> Path:
    """Same resolution as `factory.py init` and the run_factory templates: --db, else $CF_DB, else
    $CF_RUNS_DIR/factory.db, else ~/content-factory/runs/factory.db — one memory for every way the factory runs."""
    if arg:
        return Path(arg).resolve()
    if os.environ.get("CF_DB"):
        return Path(os.environ["CF_DB"]).resolve()
    runs = os.environ.get("CF_RUNS_DIR") or str(Path.home() / "content-factory" / "runs")
    return (Path(runs) / "factory.db").resolve()


def ensure_memory(db: Path, allow_empty: bool) -> dict:
    """Never filter against a silently empty memory: an absent database is seeded from ./memory/dump.json (the
    templates' rule); with neither, stop unless --allow-empty-memory."""
    if db.exists():
        return {"db": str(db), "seeded_from": None}
    seed = Path("memory/dump.json")
    if seed.exists():
        db.parent.mkdir(parents=True, exist_ok=True)
        p = subprocess.run([sys.executable, str(SKILLS / "content-database" / "scripts" / "cfdb.py"), "import", "--db", str(db),
                            "--in", str(seed)], capture_output=True, text=True)
        if p.returncode != 0:
            raise SystemExit(json.dumps({"error": "MEMORY_FAILED", "db": str(db), "stderr": (p.stderr or p.stdout)[-400:]}))
        return {"db": str(db), "seeded_from": str(seed.resolve())}
    if not allow_empty:
        raise EnvironmentError(f"no content memory at {db} and no memory/dump.json to seed it — without memory the engine "
                               "cannot refuse repeated topics. Point --db (or CF_DB) at the factory database, or pass "
                               "--allow-empty-memory for a deliberately fresh channel")
    db.parent.mkdir(parents=True, exist_ok=True)
    return {"db": str(db), "seeded_from": None, "empty": True}


def memory_check(c: dict, con, items: list[dict], gitems: list) -> dict:
    """Existing memory semantics, unchanged: topic/title repeat (init's TOPIC_REPEATED rule) and novelty below 0.35
    against every remembered title, hook, idea and topic (SELECTION's rule) reject; a hook hint that repeats a used
    hook (the hook engine's rule) is flagged — V3.0.1 writes and selects its own hooks."""
    repeats, checked = cfdb.topic_repeats(con, c["topic"])
    g = grams(f"{c['topic']} {c.get('angle') or ''}")
    sims = sorted(((cos(g, gi), it) for gi, it in zip(gitems, items)), key=lambda x: (-x[0], x[1]["kind"], x[1]["text"]))
    novelty = round(1 - (sims[0][0] if sims else 0.0), 3)
    nearest = [{"kind": it["kind"], "text": it["text"], "similarity": round(s, 3)} for s, it in sims[:3]]
    past_hooks = [it["text"] for it in items if it["kind"] == "hook"]
    hook_rep = max(((hook_jaccard(c["hook"], h), h) for h in past_hooks), default=(0.0, None)) if c.get("hook") else (0.0, None)
    reason = (f"repeats earlier {repeats[0]['kind'].replace('_', ' ')} “{repeats[0]['text']}”" if repeats else
              f"too close to earlier content (novelty {novelty:.2f} < {NOVELTY_MIN}): “{nearest[0]['text']}”" if novelty < NOVELTY_MIN
              else None)
    return {"verdict": "rejected" if reason else "passed", "reason": reason, "topic_repeats": repeats[:3],
            "compared_with": checked, "novelty": novelty, "nearest": nearest,
            "hook_repeats_past": bool(hook_rep[0] >= HOOK_REPEAT), "hook_similarity": round(hook_rep[0], 3),
            "hook_nearest": hook_rep[1]}


# ----------------------------------------------------------------------------- research (offline screen, explicit)
def research_offline(c: dict) -> dict:
    """No web research happens here: without an LLM agent the factory has no research backend. This screen grades only
    what is in the file. Facts are researched and gated by V3.0.1's RESEARCH stage for each selected topic."""
    text = " ".join(x for x in (c["topic"], c.get("angle"), c.get("hook")) if x)
    words = set(re.findall(r"[a-z][a-z-]*", text.lower()))
    high = sorted(words & RISK_HIGH)
    medium = bool(re.search(r"\d", text)) or bool(re.search(r"\b(percent|record|fastest|largest|first|ranking)\b", text, re.I))
    hints = []
    for s in c.get("source_hint") or []:
        if re.match(r"^https?://", s):
            hints.append({"hint": s, "domain": src_domain(s), "tier": src_tier(s), "verified": False})
        else:
            hints.append({"hint": s, "domain": None, "tier": None, "verified": False})
    return {"mode": "offline", "web_research": "not performed",
            "why": "the Idea Engine runs without an LLM or web agent; V3.0.1's RESEARCH stage researches and gates each "
                   "selected topic (tier-1 or two independent sources for high-risk claims)",
            "risk": "high" if high else "medium" if medium else "low", "risk_terms": high,
            "exaggeration": sorted({m.group().lower() for m in EXAGGERATION.finditer(text)}),
            "clickbait": sorted({x for x in CLICKBAIT if x in text.lower()}), "source_hints": hints}


# ----------------------------------------------------------------------------- scoring
def clip(x: float) -> float:
    return round(max(0.0, min(1.0, x)), 3)


def score(c: dict, mem: dict, res: dict) -> dict:
    """Each component is 0..1 with the reasons that produced it; the total is the weighted sum (WEIGHTS)."""
    topic, angle, hook, visual = c["topic"], c.get("angle") or "", c.get("hook") or "", c.get("visual") or ""
    allt = f"{topic} {angle} {hook}"
    comp, why = {}, {}

    def put(k, v, reasons):
        comp[k], why[k] = clip(v), reasons
    # novelty (the memory penalty): rescaled above SELECTION's rejection threshold
    put("novelty", (mem["novelty"] - NOVELTY_MIN) / (1 - NOVELTY_MIN),
        [f"novelty {mem['novelty']:.2f} vs memory" + (f" (nearest: “{mem['nearest'][0]['text']}”)" if mem["nearest"] else "")])
    r, v = [], 0.0
    if topic.rstrip().endswith("?") or QUESTION.match(topic):
        v += 0.35; r.append("posed as a question")
    if CONTRAST & {w.strip("?,.!").lower() for w in allt.split()}:
        v += 0.25; r.append("contrast/tension word")
    if re.search(r"\d", f"{topic} {hook}") or any(w[:1].isupper() for w in topic.split()[1:]):
        v += 0.15; r.append("specific (number or name)")
    if RELATABLE.search(allt):
        v += 0.15; r.append("relatable to the viewer")
    if SURPRISE.search(allt):
        v += 0.10; r.append("surprise marker")
    put("curiosity", v, r or ["no question, contrast or surprise"])
    r = []
    if not hook:
        v = 0.3; r.append("no hook hint (V3.0.1 writes its own hooks)")
    else:
        secs = len(hook.split()) / WPS["en"]
        v = 0.35 if secs <= 3.2 else 0.15 if secs <= 4.0 else 0.0
        r.append(f"hook ≈{secs:.1f}s spoken" + (" (≤3.2 s)" if secs <= 3.2 else " (long)"))
        if OPENERS.search(hook):
            v -= 0.4; r.append("throat-clearing opener")
        if CONTRAST & {w.strip("?,.!").lower() for w in hook.split()}:
            v += 0.2; r.append("contrast")
        if re.search(r"\d", hook) or any(w[:1].isupper() for w in hook.split()[1:]):
            v += 0.15; r.append("specific")
        if hook.rstrip().endswith("?") or SURPRISE.search(hook):
            v += 0.15; r.append("tension")
        if any(x in hook.lower() for x in CLICKBAIT):
            v = 0.0; r.append("clickbait phrasing (not usable)")
        if mem["hook_repeats_past"]:
            v -= 0.5; r.append(f"repeats a used hook “{mem['hook_nearest']}” (V3.0.1 never reuses it)")
    put("hook_potential", v, r)
    words = set(re.findall(r"[a-z]+", f"{topic} {angle} {visual}".lower()))
    conc = sorted({w for w in words if w in VISUAL or (w.endswith("s") and w[:-1] in VISUAL)})
    abst = sorted(words & ABSTRACT)
    v = (0.4 if len(visual) >= 12 else 0.0) + min(0.6, 0.2 * len(conc)) - 0.2 * len(abst)
    put("visual_potential", v, ([f"visual idea supplied"] if len(visual) >= 12 else ["no visual idea"]) +
        ([f"concrete: {', '.join(conc[:4])}"] if conc else ["nothing concrete to draw"]) +
        ([f"abstract: {', '.join(abst)}"] if abst else []))
    nt, na = len(topic.split()), len(angle.split())
    v = (0.4 if 3 <= nt <= 14 else 0.15) + (0.3 if topic.count("?") <= 1 and " and why " not in topic.lower() else 0.0) + \
        (0.3 if 6 <= na <= 45 else 0.0)
    put("clarity", v, [f"topic {nt} words", "single question" if topic.count("?") <= 1 else "several questions",
                       f"angle {na} words" if angle else "no angle"])
    v = (0.2 if LISTY.search(allt) else 0.6) + (0.3 if MECHANISM.search(angle) else 0.0) + (0.1 if na <= 45 else 0.0)
    put("short_form_fit", v, (["list/overview format (hard to pay off in 30 s)"] if LISTY.search(allt) else ["single subject"]) +
        (["one clear mechanism"] if MECHANISM.search(angle) else ["no mechanism named"]))
    shared = set(cfdb.topic_stems(topic)) & set(cfdb.topic_stems(angle))
    v = (0.4 if shared else 0.0) + (0.4 if EXPLAINS.search(angle) else 0.0) + (0.2 if angle and not angle.rstrip().endswith("?") else 0.0)
    put("payoff", v, [("angle picks up the topic's words" if shared else "angle shares no word with the topic"),
                      ("gives an explanation" if EXPLAINS.search(angle) else "no explanation in the angle")])
    v = 1.0 - {"high": 0.5, "medium": 0.2, "low": 0.0}[res["risk"]] - min(0.6, 0.2 * len(res["exaggeration"]))
    put("factual_confidence", v, [f"{res['risk']} risk" + (f" ({', '.join(res['risk_terms'])})" if res["risk_terms"] else "")] +
        ([f"exaggeration: {', '.join(res['exaggeration'])}"] if res["exaggeration"] else []))
    tiers = [h["tier"] for h in res["source_hints"] if h["tier"]]
    best = min(tiers) if tiers else None
    put("research_quality", {1: 1.0, 2: 0.8, 3: 0.45, 4: 0.15, None: 0.35}[best],
        [f"best source hint tier {best} (unverified)" if best else "no source hint (unknown, not penalised to zero)"])
    total = round(sum(WEIGHTS[k] * comp[k] for k in WEIGHTS), 4)
    return {"components": comp, "reasons": why, "total": total}


# ----------------------------------------------------------------------------- dedupe + diversity selection
def same_subject(a: str, b: str) -> dict | None:
    """init's repetition rule applied between two candidates (trigram cosine ≥ 0.6, ≥2 shared stems, or containment)."""
    sa, sb = cfdb.topic_stems(a), cfdb.topic_stems(b)
    shared = sorted({x for x in sa for y in sb if cfdb.stems_match(x, y)})
    c = cfdb.cosine(cfdb.grams(a), cfdb.grams(b))
    if c >= cfdb.TOPIC_COSINE or len(shared) >= 2 or (shared and len(shared) in (len(sa), len(sb))):
        return {"cosine": round(c, 3), "shared": shared}
    return None


def similarity(a: dict, b: dict) -> float:
    parts = [cos(grams(f"{a['topic']} {a.get('angle') or ''}"), grams(f"{b['topic']} {b.get('angle') or ''}"))]
    if a.get("hook") and b.get("hook"):
        parts.append(cos(grams(a["hook"]), grams(b["hook"])))
    if a.get("visual") and b.get("visual"):
        parts.append(cos(grams(a["visual"]), grams(b["visual"])))
    sa, sb = set(cfdb.topic_stems(a["topic"])), set(cfdb.topic_stems(b["topic"]))
    parts.append(len(sa & sb) / max(1, len(sa | sb)))
    return round(max(parts) + (0.15 if a.get("category") and a.get("category") == b.get("category") else 0.0), 3)


def select(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Maximal marginal relevance, the same shape as SELECTION (0.75 · quality − 0.25 · similarity to the picks, +0.15
    for the same category): five strong candidates that differ in subject, angle, hook and visual. A candidate on the
    same subject as a pick is never picked. Ties break on the candidate's position in the file."""
    pool = sorted(rows, key=lambda r: (-r["score"]["total"], r["position"]))
    chosen, notes = [], {}
    while pool and len(chosen) < WINNERS:
        def mmr(r):
            sims = [(similarity(r, c), c["id"]) for c in chosen]
            s = max(sims, default=(0.0, None))
            return 0.75 * r["score"]["total"] - 0.25 * s[0], s
        best, best_key = None, None
        for r in pool:
            if any(same_subject(r["topic"], c["topic"]) for c in chosen):
                continue
            m, s = mmr(r)
            key = (round(m, 6), -r["position"])
            if best is None or key > best_key:
                best, best_key, best_s = r, key, s
        if best is None:
            break
        best["selection"] = {"pick": len(chosen) + 1, "marginal_score": round(best_key[0], 4),
                             "most_similar_pick": best_s[1], "similarity_to_it": best_s[0]}
        chosen.append(best)
        pool.remove(best)
    for r in pool:
        clash = next((c["id"] for c in chosen if same_subject(r["topic"], c["topic"])), None)
        notes[r["id"]] = f"same subject as winner {clash}" if clash else "lower marginal score than the five winners"
    return chosen, [{"id": r["id"], "reason": notes[r["id"]]} for r in pool]


# ----------------------------------------------------------------------------- the selection pipeline
def build_selection(cands: list[dict], con, warnings: list[str]) -> dict:
    items = cfdb.corpus(con)
    gitems = [grams(it["text"]) for it in items]
    filtered, research, ranked, rejected = [], [], [], []
    for c in cands:
        if not c["valid"]:
            rejected.append({"id": c["id"], "stage": "validation", "reason": "; ".join(c["problems"])})
            continue
        mem = memory_check(c, con, items, gitems)
        filtered.append({"id": c["id"], "topic": c["topic"], **mem})
        if mem["verdict"] == "rejected":
            rejected.append({"id": c["id"], "stage": "memory", "reason": mem["reason"]})
            continue
        res = research_offline(c)
        research.append({"id": c["id"], "topic": c["topic"], **res})
        if any(x in f"{c['topic']} {c.get('angle') or ''}".lower() for x in CLICKBAIT):
            rejected.append({"id": c["id"], "stage": "quality", "reason": f"misleading clickbait phrasing {res['clickbait']}"})
            continue
        ranked.append({**c, "memory": mem, "research": res, "score": score(c, mem, res)})
    ranked.sort(key=lambda r: (-r["score"]["total"], r["position"]))
    kept = []
    for r in ranked:                              # near-duplicates inside the file: keep the better-scored phrasing
        dup = next((k for k in kept if same_subject(r["topic"], k["topic"])), None)
        if dup:
            rejected.append({"id": r["id"], "stage": "duplicate", "reason": f"same subject as {dup['id']} (kept, higher score)"})
        elif r["score"]["total"] < QUALITY_FLOOR:
            rejected.append({"id": r["id"], "stage": "quality", "reason": f"total {r['score']['total']:.2f} below the floor {QUALITY_FLOOR}"})
        else:
            kept.append(r)
    winners, not_selected = select(kept)
    for i, r in enumerate(ranked):
        r["rank"] = i + 1
    return {"filtered": filtered, "research": research, "ranked": ranked, "eligible": [r["id"] for r in kept],
            "winners": winners, "not_selected": not_selected, "rejected": rejected, "warnings": warnings,
            "memory_items": len(items), "history_sha256": sha256_bytes(canonical(items).encode())}


def public(r: dict) -> dict:
    return {k: r.get(k) for k in ("id", "position", "topic", "angle", "hook", "visual", "category", "source_hint")}


def manifest_core(m: dict) -> dict:
    return {k: m[k] for k in ("schema", "batch_id", "created_at", "engine", "factory_version", "ideas_file", "memory",
                              "selected", "production")}


def write_analysis(batch: Path, doc: dict, cands: list[dict], sel: dict) -> None:
    write_json(batch / "candidates.json", {"version": doc.get("version"), "generated_at": doc.get("generated_at"),
                                           "count": len(cands), "candidates": cands})
    write_json(batch / "filtered.json", {"rule": {"topic_repeat": "factory init (TOPIC_REPEATED)", "novelty_min": NOVELTY_MIN,
                                                  "hook_repeat": HOOK_REPEAT}, "candidates": sel["filtered"]})
    write_json(batch / "research.json", {"mode": "offline", "candidates": sel["research"]})
    write_json(batch / "ranking.json", {"weights": WEIGHTS, "quality_floor": QUALITY_FLOOR,
                                        "ranked": [{"rank": r["rank"], **public(r), "total": r["score"]["total"],
                                                    "components": r["score"]["components"], "reasons": r["score"]["reasons"],
                                                    "eligible": r["id"] in sel["eligible"]} for r in sel["ranked"]]})
    write_json(batch / "selected.json", {"winners": [{**public(r), "rank": r["rank"], "total": r["score"]["total"],
                                                      "selection": r["selection"], "why": top_reasons(r)} for r in sel["winners"]],
                                         "not_selected": sel["not_selected"]})


def write_manifest(batch: Path, raw: bytes, sel: dict, mem_info: dict, args) -> dict:
    fv = (SKILLS / "content-factory" / "VERSION").read_text().strip()
    m = {"schema": "cf-idea-batch/1", "batch_id": batch.name, "created_at": now_iso(), "engine": f"idea_engine {ENGINE_VERSION}",
         "factory_version": fv, "ideas_file": {"path": str(Path(args.ideas_file).resolve()), "sha256": sha256_bytes(raw),
                                               "archived_as": "input.json"},
         "memory": {"db": mem_info["db"], "items": sel["memory_items"], "history_sha256": sel["history_sha256"]},
         "selected": [{"slot": i + 1, **public(r), "total": r["score"]["total"]} for i, r in enumerate(sel["winners"])],
         "production": {"runs_dir": str(batch / "runs"), "init": init_defaults(args)}}
    m["manifest_sha256"] = sha256_bytes(canonical(manifest_core(m)).encode())
    write_json(batch / "manifest.json", m)
    return m


def top_reasons(r: dict) -> list[str]:
    comp = r["score"]["components"]
    best = sorted(comp, key=lambda k: (-WEIGHTS[k] * comp[k], k))[:3]
    return [f"{k.replace('_', ' ')} {comp[k]:.2f}: {'; '.join(r['score']['reasons'][k])}" for k in best]


def init_defaults(args) -> dict:
    return {"count": 1, "languages": args.languages, "min_s": args.min_s, "max_s": args.max_s}


# ----------------------------------------------------------------------------- handoff to V3.0.1
def prepare_runs(batch: Path, m: dict, db: str) -> list[dict]:
    """One isolated V3.0.1 run per winner, created through the production engine's own entry point. `init` re-checks
    the topic against memory and the machine's capabilities; a refusal is recorded for that slot only."""
    runs_dir = batch / "runs"
    runs_dir.mkdir(exist_ok=True)
    slots = read_json(batch / "slots.json") if (batch / "slots.json").exists() else {"slots": []}
    have = {s["slot"]: s for s in slots["slots"]}
    ini = m["production"]["init"]
    for w in m["selected"]:
        if w["slot"] in have and have[w["slot"]].get("run_dir"):
            continue
        cmd = [sys.executable, str(HERE / "factory.py"), "init", "--topic", w["topic"], "--count", str(ini["count"]),
               "--languages", ini["languages"], "--min-s", str(ini["min_s"]), "--max-s", str(ini["max_s"]),
               "--runs-dir", str(runs_dir), "--db", db]
        for label, k in (("Angle (from the idea batch)", "angle"), ("Hook idea (optional; the hook engine decides)", "hook"),
                         ("Visual idea (optional)", "visual")):
            if w.get(k):
                cmd += ["--constraint", f"{label}: {w[k]}"]
        p = subprocess.run(cmd, capture_output=True, text=True)
        try:
            out = json.loads(p.stdout)
        except ValueError:
            out = {"error": "INIT_FAILED", "stderr": (p.stderr or p.stdout)[-400:]}
        entry = {"slot": w["slot"], "candidate_id": w["id"], "topic": w["topic"], "init_exit": p.returncode,
                 "run_dir": out.get("run") if p.returncode == 0 else None, "init_error": None if p.returncode == 0 else out}
        have[w["slot"]] = entry
        write_json(batch / "slots.json", {"batch_id": m["batch_id"], "slots": [have[k] for k in sorted(have)]})
    return [have[k] for k in sorted(have)]


def verify_batch(batch: Path) -> dict:
    """Refuse a manifest that was edited, belongs to another folder, or no longer matches its archived input."""
    try:
        m = read_json(batch / "manifest.json")
    except (OSError, ValueError) as e:
        raise BatchRefused(f"manifest.json unreadable: {e}", batch=str(batch)) from None
    if sha256_bytes(canonical(manifest_core(m)).encode()) != m.get("manifest_sha256"):
        raise BatchRefused("manifest.json was changed after selection", batch=str(batch))
    if m["batch_id"] != batch.name:
        raise BatchRefused(f"manifest is for batch {m['batch_id']}, folder is {batch.name}", batch=str(batch))
    inp = batch / "input.json"
    if not inp.exists() or sha256_bytes(inp.read_bytes()) != m["ideas_file"]["sha256"]:
        raise BatchRefused("input.json does not match the manifest's ideas file", batch=str(batch))
    return m


def run_state(run: Path, slot: dict, m: dict) -> dict:
    """What V3.0.1 itself says about the run — the only evidence used. A run counts as delivered only when every video is
    packaged, its PACKAGE stage passed, and the package envelope is the one `record` stored (same sha256)."""
    if not (run / "state.json").exists():
        return {"status": "missing", "reasons": [f"run folder {run} (or its state.json) is missing"]}
    if run.resolve().parent != Path(m["production"]["runs_dir"]).resolve():
        return {"status": "foreign", "reasons": [f"{run} is not a run of this batch"]}
    st = factory.load(run)
    if st["brief"]["topic"] != slot["topic"]:
        return {"status": "foreign", "reasons": [f"run topic “{st['brief']['topic']}” is not slot topic “{slot['topic']}”"]}
    if st["brief"]["created_at"] < m["created_at"]:
        return {"status": "foreign", "reasons": ["run is older than this batch"]}
    if not st["videos"]:
        nx = factory.next_action(run, st)
        why = [f"run escalated at {nx['events'][-1].get('stage') if nx.get('events') else '?'}"] if nx.get("action") == "escalated" \
            else [f"no video yet; next V3.0.1 action: {nx.get('action')} {nx.get('stage') or ''}".strip()]
        return {"status": "not_packaged", "reasons": why}
    reasons = []
    for vid, v in st["videos"].items():
        pk = v["stages"]["PACKAGE"]
        rp = factory.vp(run, vid)["result"]["PACKAGE"]
        if v["status"] == "packaged" and pk["status"] in factory.PASSED and rp.exists():
            if hashlib.sha256(rp.read_bytes()).hexdigest() != pk.get("result_sha256"):
                reasons.append(f"{vid}: package result differs from the one V3.0.1 recorded (stale)")
            continue
        open_ = [f"{k}={x['status']}" for k, x in v["stages"].items() if x["status"] not in ("passed", "passed_with_warnings", "skipped")]
        reasons.append(f"{vid}: status {v['status']}; " + ", ".join(open_)[:240])
        for k, x in v["stages"].items():           # the failing gate's own error codes (escalation evidence)
            if x["status"] == "failed" and x.get("result") and Path(x["result"]).exists():
                errs = read_json(Path(x["result"])).get("errors", [])
                reasons += [f"{vid} {k}: {e.get('code')}: {(e.get('message') or '')[:160]}" for e in errs[:3]]
    if reasons:
        nx = factory.next_action(run, st)
        if nx.get("action") not in ("done", "escalated"):
            reasons.append(f"next V3.0.1 action: {nx.get('action')} {nx.get('stage') or ''}".strip())
        return {"status": "not_packaged", "reasons": reasons}
    zp = run / f"{run.name}_package.zip"
    return {"status": "packaged", "package_dir": str(run / "package"), "zip": str(zp) if zp.exists() else None, "reasons": []}


def checksums_ok(pkg: Path) -> list[str]:
    cs = pkg / "checksums.sha256"
    if not cs.exists():
        return ["checksums.sha256 missing"]
    bad = []
    for line in cs.read_text().splitlines():
        h, _, rel = line.partition("  ")
        f = pkg / rel
        if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest() != h:
            bad.append(rel)
    return [f"checksum mismatch: {bad[:5]}"] if bad else []


def deliver(run: Path, state: dict, out_root: Path, slot: dict, batch_id: str) -> dict:
    dest = out_root / batch_id / f"{slot['slot']:02d}-{run.name}"
    src = Path(state["package_dir"])
    if dest.exists():                        # never overwrite: identical → already delivered; different → refuse
        same = not checksums_ok(dest / "package") and (dest / "package" / "checksums.sha256").read_bytes() == \
            (src / "checksums.sha256").read_bytes()
        return {"delivered": same, "path": str(dest), "note": "already delivered" if same else
                "output folder exists with different content; not overwritten"}
    probs = checksums_ok(src)
    if probs:
        return {"delivered": False, "path": None, "note": "; ".join(probs)}
    dest.mkdir(parents=True)
    shutil.copytree(src, dest / "package")
    if state.get("zip"):
        shutil.copy2(state["zip"], dest / Path(state["zip"]).name)
    probs = checksums_ok(dest / "package")
    return {"delivered": not probs, "path": str(dest), "note": "; ".join(probs) or "copied and verified"}


def driver_argv(args, run: Path, batch: Path, slot: dict) -> list[str]:
    if args.driver_cmd:
        parts = shlex.split(args.driver_cmd, posix=os.name != "nt")
        parts = [p[1:-1] if os.name == "nt" and len(p) > 1 and p[0] == p[-1] == '"' else p for p in parts]
        return [p.format(run=str(run), batch=str(batch), topic=slot["topic"], slot=slot["slot"]) for p in parts]
    prompt = (f"/content-factory Continue the existing factory run at {run} — do not start a new run. It was prepared by the "
              f"idea batch {batch.name} for the topic “{slot['topic']}” (angle and hook idea are in its run.json "
              "constraints). Unattended run: never publish or upload anything; drive it with factory.py next/record/media "
              f"until it is packaged, then run `factory.py package --run {run} --zip`, stop, and report escalations.")
    # the same flags as automation-engineering/assets/templates/run_factory.sh, plus access to the batch folder
    return ["claude", "-p", prompt, "--permission-mode", "acceptEdits", "--permission-prompts", "none",
            "--allowedTools", "Bash,Read,Write,Edit,WebSearch,WebFetch", "--output-format", "json", "--add-dir", str(batch)]


def preflight(args) -> str | None:
    if args.produce == "none" or args.driver_cmd:
        return None
    if not shutil.which("claude"):
        return ("the production driver needs Claude Code (`claude` on PATH) — the same unattended interface V3.0.1 uses "
                "(automation-engineering). Install it and log in (a Claude subscription login is enough; no API key needed), "
                "or pass --produce none and produce the prepared runs later with `idea_engine.py produce --batch …`")
    if not any(p.exists() for p in (Path(".claude/skills/content-factory/SKILL.md"),
                                    Path.home() / ".claude" / "skills" / "content-factory" / "SKILL.md")):
        return ("Claude Code would not find the content-factory skill: run from the project folder where "
                "install_skills.py installed .claude/skills/ (or install them into ~/.claude/skills)")
    return None


def produce(batch: Path, args) -> dict:
    m = verify_batch(batch)
    db = m["memory"]["db"]
    if not Path(db).exists():                 # init would start an empty memory and stop refusing repeated topics
        raise BatchRefused(f"the content memory this batch was selected against is gone: {db}", error="MEMORY_MISSING",
                           hint="restore the database (or memory/dump.json → cfdb.py import) and run produce again")
    with factory.FileLock(batch / ".lock", "idea_engine produce"):
        slots = prepare_runs(batch, m, db)
        if args.produce == "none":
            return {"slots": [{**s, "status": "prepared" if s["run_dir"] else "init_failed"} for s in slots], "production": "not run"}
        why = preflight(args)
        if why:
            return {"slots": [{**s, "status": "prepared" if s["run_dir"] else "init_failed"} for s in slots],
                    "production": "not run", "environment_error": why}
        out_root = Path(args.output_dir).resolve() if args.output_dir else None
        (batch / "logs").mkdir(exist_ok=True)
        env = {**os.environ, "CF_DB": db, "CF_RUNS_DIR": str(batch / "runs")}
        results = []
        for s in slots:
            r = dict(s)
            if not s["run_dir"]:
                e = s["init_error"] or {}
                r.update(status="init_failed", reasons=[f"factory init refused: {e.get('error')}"] +
                         [f"{x.get('kind')} “{x.get('text')}”" for x in e.get("repeats", [])[:2]] +
                         [f"missing {x.get('capability')}: {str(x.get('fix'))[:160]}" for x in e.get("missing", [])[:3]] +
                         ([str(e.get("stderr"))[-200:]] if e.get("stderr") else []))
                results.append(r)
                continue
            run = Path(s["run_dir"])
            before = run_state(run, s, m)
            if before["status"] in ("foreign", "missing"):
                r.update(status="refused", reasons=before["reasons"])
                results.append(r)
                continue
            if before["status"] != "packaged":
                n = 1
                while (batch / "logs" / f"{s['slot']:02d}-{run.name}.{n}.log").exists():   # every attempt's log is kept
                    n += 1
                log = batch / "logs" / f"{s['slot']:02d}-{run.name}.{n}.log"
                argv = driver_argv(args, run, batch, s)
                try:
                    p = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=args.run_timeout_min * 60)
                    rc, outp, errp, note = p.returncode, p.stdout, p.stderr, (f"driver exit {p.returncode}" if p.returncode else None)
                except subprocess.TimeoutExpired as e:
                    outp = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
                    rc, errp, note = None, "", f"driver timed out after {args.run_timeout_min} min"
                except OSError as e:
                    rc, outp, errp, note = None, "", "", f"driver could not start: {e}"
                log.write_text(f"$ {' '.join(argv[:2])} …\nexit: {rc}\n{note or ''}\n--- stdout\n{outp}\n--- stderr\n{errp}\n",
                               encoding="utf-8")
                r.update(driver_exit=rc, log=str(log))
            else:
                note = None
                r.update(driver_exit=None, note="already packaged; driver not run again")
            after = run_state(run, s, m)
            r["status"], r["reasons"] = after["status"], ([note] if note else []) + list(after["reasons"])
            if after["status"] == "packaged":
                if out_root:
                    d = deliver(run, after, out_root, s, m["batch_id"])
                    r.update(output=d["path"], output_note=d["note"])
                    if not d["delivered"]:
                        r["status"], r["reasons"] = "delivery_failed", [d["note"]]
                else:
                    r.update(output=after["package_dir"], output_note="no --output-dir/CF_OUTPUT_DIR: package left in the run")
            results.append(r)
        return {"slots": results, "production": "attempted", "output_dir": str(out_root) if out_root else None, "db": db}


# ----------------------------------------------------------------------------- report
def write_report(batch: Path, stage: str, sel: dict | None, prod: dict | None, extra: dict) -> dict:
    m = read_json(batch / "manifest.json") if (batch / "manifest.json").exists() else None
    cands = read_json(batch / "candidates.json")["candidates"] if (batch / "candidates.json").exists() else []
    ranking = read_json(batch / "ranking.json")["ranked"] if (batch / "ranking.json").exists() else []
    selected = read_json(batch / "selected.json") if (batch / "selected.json").exists() else {"winners": [], "not_selected": []}
    rejected = sel["rejected"] if sel else (read_json(batch / "report.json").get("rejected", []) if (batch / "report.json").exists() else [])
    slots = (prod or {}).get("slots", [])
    rep = {"batch_id": batch.name, "stage": stage, "written_at": now_iso(), "supplied": len(cands),
           "invalid": [r for r in rejected if r["stage"] == "validation"],
           "rejected_by_memory": [r for r in rejected if r["stage"] == "memory"],
           "rejected_quality": [r for r in rejected if r["stage"] in ("quality", "duplicate")],
           "rejected": rejected, "top": [{k: r[k] for k in ("rank", "id", "topic", "total", "eligible")} for r in ranking[:15]],
           "winners": selected["winners"], "not_selected": selected["not_selected"][:20],
           "production": prod.get("production") if prod else "not started",
           "runs": slots, "succeeded": [s for s in slots if s.get("status") == "packaged"],
           "failed": [s for s in slots if s.get("status") not in ("packaged", "prepared")],
           "memory_export": (prod or {}).get("memory_export"),
           "manifest": str(batch / "manifest.json") if m else None, **extra}
    write_json(batch / "report.json", rep)
    L = [f"# Idea batch {batch.name}", "", f"Stage reached: **{stage}** · supplied {len(cands)} candidates · "
         f"invalid {len(rep['invalid'])} · rejected by memory {len(rep['rejected_by_memory'])} · rejected for quality/duplicates "
         f"{len(rep['rejected_quality'])} · eligible {len([r for r in ranking if r['eligible']])}", ""]
    for w in rep.get("warnings", []):
        L.append(f"> warning: {w}")
    if rep.get("error"):
        L += [f"> **{rep['error']}**", ""]
    L += ["", "## Winners", "", "| slot | id | topic | total | why |", "|---|---|---|---|---|"]
    L += [f"| {i + 1} | {w['id']} | {w['topic']} | {w['total']:.2f} | {' · '.join(w['why'])} |" for i, w in enumerate(rep["winners"])]
    L += ["", "## Production", "", f"{rep['production']}" + (f" — output: {prod.get('output_dir')}" if prod and prod.get("output_dir") else ""), "",
          "| slot | topic | status | run | output / reason |", "|---|---|---|---|---|"]
    L += [f"| {s['slot']} | {s['topic']} | {s.get('status')} | {s.get('run_dir') or '—'} | "
          f"{s.get('output') or '; '.join(s.get('reasons', []))[:200] or '—'} |" for s in slots]
    if prod and prod.get("environment_error"):
        L += ["", f"> environment: {prod['environment_error']}"]
    L += ["", "## Top candidates", "", "| rank | id | topic | total | eligible |", "|---|---|---|---|---|"]
    L += [f"| {r['rank']} | {r['id']} | {r['topic']} | {r['total']:.2f} | {r['eligible']} |" for r in rep["top"]]
    L += ["", "## Rejected", ""] + [f"- {r['id']} ({r['stage']}): {r['reason']}" for r in rejected] + \
         ["", "## Not selected (eligible)", ""] + [f"- {n['id']}: {n['reason']}" for n in rep["not_selected"]]
    L += ["", "Research: offline screen only (no web research without an agent); V3.0.1's RESEARCH stage researches and "
          "gates each selected topic. Details: candidates.json · filtered.json · research.json · ranking.json · selected.json · "
          "manifest.json · slots.json · logs/."]
    (batch / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return rep


# ----------------------------------------------------------------------------- commands
def load_env() -> None:
    """The run_factory templates source ./.env; do the same for CF_* paths (never printed, never overriding)."""
    f = Path(".env")
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        k, sep, v = line.strip().partition("=")
        if sep and k and not k.startswith("#") and v.strip() and k.strip() not in os.environ:
            os.environ[k.strip()] = v.strip().strip('"').strip("'")


def new_batch(batches: Path, raw: bytes) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    base = f"{stamp}-{sha256_bytes(raw)[:8]}"
    b, k = batches / base, 1
    while b.exists():                     # never reuse a batch folder
        k += 1
        b = batches / f"{base}-{k}"
    b.mkdir(parents=True)
    return b


def earlier_use(batches: Path, digest: str) -> list[str]:
    hits = []
    for mf in sorted(batches.glob("*/manifest.json")):
        try:
            if read_json(mf)["ideas_file"]["sha256"] == digest:
                hits.append(mf.parent.name)
        except (OSError, ValueError, KeyError):
            continue
    return hits


def cmd_validate(a) -> int:
    raw = Path(a.ideas_file).read_bytes()
    try:
        _, cands, warns = parse_ideas(raw)
    except IdeaFileError as e:
        print(json.dumps({"valid": False, "errors": e.problems}, indent=1, ensure_ascii=False))
        return 2
    bad = [{"id": c["id"], "problems": c["problems"]} for c in cands if not c["valid"]]
    print(json.dumps({"valid": True, "candidates": len(cands), "usable": len(cands) - len(bad), "invalid": bad,
                      "warnings": warns}, indent=1, ensure_ascii=False))
    return 0


def cmd_select(a, produce_after: bool) -> int:
    path = Path(a.ideas_file)
    if not path.exists():
        print(json.dumps({"error": "IDEAS_FILE_MISSING", "path": str(path.resolve()),
                          "hint": "save the ~50-candidate JSON there (references/idea-engine.md)"}))
        return 2
    raw = path.read_bytes()
    try:
        doc, cands, warns = parse_ideas(raw)
    except IdeaFileError as e:
        print(json.dumps({"error": "INVALID_IDEAS_FILE", "file": str(path.resolve()), "problems": e.problems}, indent=1, ensure_ascii=False))
        return 2
    batches = Path(a.batches_dir).resolve()
    batches.mkdir(parents=True, exist_ok=True)
    used = earlier_use(batches, sha256_bytes(raw))
    if used and not a.allow_reused_input:
        print(json.dumps({"error": "IDEAS_FILE_ALREADY_USED", "batches": used,
                          "hint": "save a fresh ideas file, or pass --allow-reused-input to run it again on purpose"}))
        return 2
    db = resolve_db(a.db)
    try:
        mem_info = ensure_memory(db, a.allow_empty_memory)
    except EnvironmentError as e:
        print(json.dumps({"error": "NO_MEMORY", "why": str(e)}))
        return 3
    batch = new_batch(batches, raw)
    (batch / "input.json").write_bytes(raw)
    con = cfdb.connect(str(db))
    sel = build_selection(cands, con, warns)
    con.close()
    if mem_info.get("seeded_from"):
        sel["warnings"].append(f"memory was empty; seeded from {mem_info['seeded_from']}")
    if mem_info.get("empty"):
        sel["warnings"].append("memory is empty (--allow-empty-memory): no earlier topics could be refused")
    extra = {"memory": mem_info, "warnings": sel["warnings"]}
    write_analysis(batch, doc, cands, sel)
    if len(sel["winners"]) < WINNERS:
        err = (f"only {len(sel['winners'])} usable, mutually different candidates (need {WINNERS}); nothing was produced — "
               "add more fresh ideas to the file")
        rep = write_report(batch, "selection_failed", sel, None, {**extra, "error": err})
        print(json.dumps({"error": "TOO_FEW_CANDIDATES", "batch": str(batch), "usable": len(sel["winners"]), "need": WINNERS,
                          "rejected": len(rep["rejected"]), "report": str(batch / "report.md")}, indent=1))
        return 2
    m = write_manifest(batch, raw, sel, mem_info, a)
    write_report(batch, "selected", sel, None, extra)
    if not produce_after:
        print(json.dumps({"batch": str(batch), "selected": [(w["slot"], w["topic"]) for w in m["selected"]],
                          "manifest": str(batch / "manifest.json"), "report": str(batch / "report.md")}, indent=1, ensure_ascii=False))
        return 0
    return finish_production(batch, a, sel, extra)


def finish_production(batch: Path, a, sel: dict | None, extra: dict) -> int:
    try:
        prod = produce(batch, a)
    except BatchRefused as e:
        print(json.dumps(e.payload, indent=1, ensure_ascii=False))
        return 2
    if prod["production"] == "attempted" and Path("memory").is_dir():   # the run_factory templates' rule: persist what was made
        x = subprocess.run([sys.executable, str(SKILLS / "content-database" / "scripts" / "cfdb.py"), "export", "--db",
                            prod["db"], "--out", str(Path("memory") / "dump.json")], capture_output=True, text=True)
        prod["memory_export"] = str(Path("memory/dump.json").resolve()) if x.returncode == 0 else f"failed: {x.stderr[-200:]}"
    if prod["production"] == "not run":
        stage = "prepared" if all(s.get("status") == "prepared" for s in prod["slots"]) else "prepared_incomplete"
    else:
        stage = "delivered" if all(s.get("status") == "packaged" for s in prod["slots"]) else "production_incomplete"
    rep = write_report(batch, stage, sel, prod, {**extra, **({"environment_error": prod["environment_error"]}
                                                           if prod.get("environment_error") else {})})
    print(json.dumps({"batch": str(batch), "stage": stage, "succeeded": [s["slot"] for s in rep["succeeded"]],
                      "failed": [{"slot": s["slot"], "status": s.get("status"), "reasons": s.get("reasons", [])[:2]} for s in rep["failed"]],
                      "output_dir": prod.get("output_dir"), "report": str(batch / "report.md"),
                      **({"memory_export": prod["memory_export"]} if prod.get("memory_export") else {}),
                      **({"environment_error": prod["environment_error"]} if prod.get("environment_error") else {})}, indent=1, ensure_ascii=False))
    if prod.get("environment_error"):
        return 3
    return 0 if stage in ("delivered", "prepared") else 2


def cmd_produce(a) -> int:
    batch = Path(a.batch).resolve()
    if not (batch / "manifest.json").exists():
        print(json.dumps({"error": "NO_MANIFEST", "batch": str(batch)}))
        return 2
    prev = read_json(batch / "report.json") if (batch / "report.json").exists() else {}
    return finish_production(batch, a, None, {"memory": prev.get("memory"), "warnings": prev.get("warnings", [])})


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="check an ideas file and print every problem")
    v.add_argument("--ideas-file", default="input/ideas.json")
    for name in ("select", "run"):
        s = sub.add_parser(name, help="select 5 topics (select) or select and produce them (run)")
        s.add_argument("--ideas-file", default="input/ideas.json")
        s.add_argument("--batches-dir", default=os.environ.get("CF_BATCHES_DIR", "batches"))
        s.add_argument("--db", help="content memory (default: $CF_DB, else $CF_RUNS_DIR/factory.db, as factory.py init)")
        s.add_argument("--allow-empty-memory", action="store_true", help="run with an empty memory on purpose")
        s.add_argument("--allow-reused-input", action="store_true", help="accept an ideas file an earlier batch already used")
        s.add_argument("--languages", default="en"); s.add_argument("--min-s", type=float, default=20)
        s.add_argument("--max-s", type=float, default=45)
    for name in ("run", "produce"):
        s = sub.choices[name] if name in sub.choices else sub.add_parser(name, help="(re)produce the runs of a batch")
        if name == "produce":
            s.add_argument("--batch", required=True)
        s.add_argument("--output-dir", default=os.environ.get("CF_OUTPUT_DIR"), help="where verified packages are copied (HDD)")
        s.add_argument("--produce", choices=["claude", "none"], default="claude",
                       help="claude = the existing unattended driver (claude -p /content-factory); none = prepare runs only")
        s.add_argument("--driver-cmd", help="custom production command per run; placeholders {run} {batch} {topic} {slot}")
        s.add_argument("--run-timeout-min", type=int, default=180)
    a = ap.parse_args()
    if a.cmd == "validate":
        return cmd_validate(a)
    if a.cmd == "select":
        return cmd_select(a, produce_after=False)
    if a.cmd == "run":
        return cmd_select(a, produce_after=True)
    return cmd_produce(a)


if __name__ == "__main__":
    sys.exit(main())
