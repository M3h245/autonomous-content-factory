#!/usr/bin/env python3
"""learning — turn ingested YouTube Analytics + the factory's own run files into findings that steer the next batch.

  learning.py attributes --db factory.db --runs-root DIR [--runs-root DIR ...] [--manifests GLOB ...] --out attributes.json
  learning.py kpis       --db factory.db --out kpis.json
  learning.py analyze    --db factory.db --attributes attributes.json --out-dir data/learning/<stamp>
                         [--experiments-dir experiments] [--publish-latest data/learning/latest.json]

Read-only on the database (opened with mode=ro). Inputs it relies on, all produced by existing tools:
  publications                 the verified run <-> YouTube links (ingest_youtube.py --publications-only)
  yt_snapshots / yt_videos /   immutable Analytics snapshots (ingest_analytics.py); every value carries a status and
  yt_observations              missing data is NULL, never 0
  run folders                  selected_hook.json, script.json, audio/timing.json, visual/storyboard.json,
                               package/package_selection.json, selection/selection.json, run.json (inspected, hashed)

attributes  one record per published factory video: hook wording/form/mechanism, spoken hook length, time to the first
            explanation beat, beat roles, scene count and density, duration, format, title form, CTA beat, loop ending,
            topic category (only when an idea-batch manifest assigned one), publish slot, and the learning summary the
            run was made with. Every field names its source file; nothing is inferred from metrics.
kpis        per video, at FIXED AGES on the Analytics calendar (day 1 = the publication day, Pacific time): views,
            engaged views and engaged share at D1/D3/D7 from the daily per-video rows of the newest snapshot that covers
            that age; plus lifetime-at-cutoff values (average view %, average view duration, retention at 3 s,
            subscribers gained) labelled with the age they were measured at. Maturity: none / early (1-2 days) /
            d3 (3-6) / d7 (≥7). A video without Analytics rows is `none` with NULL values, never zeros.
analyze     compares groups of videos per attribute level on the primary metric (engaged share at D3), with secondary
            metrics and a guardrail, shrinkage toward the channel mean, a deterministic bootstrap interval and a
            confidence label; writes learning_summary.json (cf-learning/1) and LEARNING_REPORT.md: findings with
            evidence and sample size, bounded directives for topic / hook / script consumers, the next experiment,
            and the outcome of earlier hypotheses. Correlation only; one video never makes a finding.
Exit: 0 ok · 2 invalid input / legacy video linked / schema problem.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import math
import random
import re
import sqlite3
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import legacy_channel as L  # noqa: E402
import learning_apply as LA  # noqa: E402

SCHEMA = LA.SCHEMA
VERSION = "1.0"
PRIMARY = "engaged_share_d3"
SECONDARY = ("views_d3", "avg_view_pct", "retention_3s")
GUARDRAIL = "avg_view_pct"
METRIC_LABEL = {"engaged_share_d3": "D3 engaged share", "views_d3": "D3 views", "avg_view_pct": "avg view % (lifetime)",
                "retention_3s": "retention at 3 s (lifetime)", "engaged_share_d1": "D1 engaged share", "views_d1": "D1 views"}
POLICY = {"primary_metric": PRIMARY, "secondary_metrics": list(SECONDARY), "guardrail": GUARDRAIL,
          "min_group_n": 3, "directive_rule": "n>=3 per side and the 80% interval excludes 0; guardrail not >5 pp worse",
          "shrinkage_k": 5, "bootstrap": {"resamples": 2000, "interval": 0.80, "seed": 20261018},
          "confidence": {"low": "interval overlaps 0, or a side has n<6", "medium": "interval excludes 0 and both sides n>=6",
                         "high": "medium, both sides n>=10 and the same sign in the previous summary"},
          "caps": {"low": 0.05, "medium": 0.10, "high": 0.15}, "effect_for_full_cap": {"engaged_share_d3": 0.05},
          "wording": "correlation only; groups differ in topic and timing, not just the attribute"}
DIRECTIVE_ATTRS = {"category": "topic", "format": "topic", "opening_form": "hook", "curiosity_mechanism": "hook"}
SCRIPT_ATTRS = ("duration_bucket", "first_value_bucket", "has_setup_beat", "scene_density_bucket")
COMPARE_ATTRS = ("opening_form", "curiosity_mechanism", "format", "category", "title_form", "duration_bucket",
                 "first_value_bucket", "has_setup_beat", "scene_density_bucket", "ends_with_loop", "publish_slot_utc")
EXPLAIN_ROLES = ("value", "payoff")


class Fail(Exception):
    def __init__(self, code, **info):
        super().__init__(code); self.info = {"error": code, **info}


# ----------------------------------------------------------------------------- helpers
def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def jload(p: Path):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def ro(db: str) -> sqlite3.Connection:
    p = Path(db)
    if not p.is_file():
        raise Fail("DB_NOT_FOUND", db=db)
    return sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)


def pacific_day(iso: str | None) -> str | None:
    if not iso:
        return None
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    try:
        from zoneinfo import ZoneInfo
        z = ZoneInfo("America/Los_Angeles")
    except Exception:  # noqa: BLE001  (no tz database: PDT, as ingest_analytics does)
        z = dt.timezone(dt.timedelta(hours=-7))
    return t.astimezone(z).date().isoformat()


def iso_dur(s: str | None) -> float | None:
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", s or "")
    if not m:
        return None
    h, mi, se = (float(x) if x else 0.0 for x in m.groups())
    return h * 3600 + mi * 60 + se


def publications(con) -> dict:
    """platform id -> (run_id, video_id, published_at); an id linked to two runs is dropped (never guessed)."""
    links: dict[str, set] = {}
    for vid, run, video, at in con.execute(
            "SELECT platform_video_id, run_id, video_id, published_at FROM publications WHERE platform='youtube'"):
        links.setdefault(vid, set()).add((run, video, at))
    legacy = sorted(v for v in links if L.is_legacy(v))
    if legacy:
        raise Fail("LEGACY_LINKED_IN_DB", ids=legacy, detail="legacy channel videos must never have a factory publication")
    return {v: next(iter(s)) for v, s in links.items() if len(s) == 1}


# ----------------------------------------------------------------------------- attributes
DUPLICATE_RUN_DIRS: list[dict] = []


def evidence_level(d: Path) -> int:
    """How complete a run folder is: packaged (3) > has a selected hook (2) > has a videos folder (1)."""
    if list(d.glob("package/*/provenance.json")):
        return 3
    if list(d.glob("videos/*/hook/selected_hook.json")):
        return 2
    return 1 if (d / "videos").is_dir() else 0


def find_run_dirs(roots: list[str]) -> dict[str, Path]:
    """run_id -> folder. The same run can exist twice (a stale PC copy and the finished cloud copy): the most complete
    folder wins and the duplicates are reported, never merged."""
    found: dict[str, list[Path]] = {}
    for r in roots:
        for rj in sorted(Path(r).rglob("run.json")):
            d = rj.parent
            if d.parent.name == "_superseded" or evidence_level(d) == 0:
                continue
            j = jload(rj) or {}
            found.setdefault(j.get("run_id") or d.name, []).append(d)
    out = {}
    for rid, ds in found.items():
        best = max(ds, key=lambda d: (evidence_level(d), -ds.index(d)))
        out[rid] = best
        if len(ds) > 1:
            DUPLICATE_RUN_DIRS.append({"run_id": rid, "used": str(best), "ignored": [str(d) for d in ds if d != best]})
    return out


def categories_from_manifests(patterns: list[str]) -> dict[str, dict]:
    """topic text (normalised) -> {category, manifest}: the category an idea batch's author assigned."""
    out = {}
    for pat in patterns or []:
        for m in sorted(glob.glob(pat)):
            d = jload(Path(m)) or {}
            for s in d.get("selected") or []:
                if s.get("category") and s.get("topic"):
                    out[norm(s["topic"])] = {"category": s["category"], "source": f"{m} (selected slot {s.get('slot')})"}
    return out


def norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def bucket(v, edges: tuple, names: tuple):
    if v is None:
        return None
    for e, n in zip(edges, names):
        if v < e:
            return n
    return names[-1]


def video_attributes(run_dir: Path, run_id: str, vid: str, cats: dict) -> dict:
    vd = run_dir / "videos" / vid
    src, a = {}, {"run_id": run_id, "video_id": vid}

    def J(rel):
        p = run_dir / rel
        d = jload(p)
        if d is not None:
            src[rel] = sha(p)[:16]
        return d
    run = J("run.json") or {}
    hook = J(f"videos/{vid}/hook/selected_hook.json") or {}
    script = J(f"videos/{vid}/script/script.json") or {}
    timing = J(f"videos/{vid}/audio/timing.json") or {}
    sb = J(f"videos/{vid}/visual/storyboard.json") or {}
    pkg = J(f"videos/{vid}/package/package_selection.json") or {}
    sel = J("selection/selection.json") or {}
    a["topic"] = run.get("topic")
    # v3.2.0: the long/short split for the learning loop. Prefer the brief's explicit video_kind; fall back to
    # the brief's max_s, then to the measured narration duration, so pre-v3.2 runs are classified too.
    _vk = run.get("video_kind")
    if not _vk:
        _ms = run.get("max_s")
        if _ms is None:
            _ms = (run.get("duration_s") or {}).get("max")
        _vk = ("long" if (_ms or 0) > 180 else "short") if _ms is not None else None
    a["video_kind"] = _vk
    spoken = hook.get("spoken_text")
    a["hook_text"] = spoken
    a["opening_form"] = LA.opening_form(spoken) if spoken else None
    a["curiosity_mechanism"] = (hook.get("curiosity_mechanism") or "").strip().lower() or None
    a["hook_words"] = len(re.findall(r"[A-Za-z0-9']+", spoken)) if spoken else None
    beats = script.get("beats") or []
    roles = [b.get("role") for b in beats]
    a["beat_roles"] = roles or None
    a["beats_n"] = len(beats) or None
    a["has_setup_beat"] = ("yes" if "setup" in roles else "no") if roles else None
    a["ends_with_loop"] = ("yes" if roles[-1] == "loop" else "no") if roles else None
    a["cta_beat"] = ("yes" if "cta" in roles else "no") if roles else None
    sents = timing.get("sentences") or []
    starts = {}
    for s in sents:
        starts.setdefault(s.get("beat_id"), s.get("start"))
    hook_end = max((s["end"] for s in sents if s.get("beat_id") == (beats[0]["id"] if beats else None)), default=None)
    a["hook_spoken_s"] = round(hook_end, 2) if hook_end is not None else None
    first_ex = next((b["id"] for b in beats if b.get("role") in EXPLAIN_ROLES), None)
    a["first_value_s"] = round(starts[first_ex], 2) if first_ex in starts and starts[first_ex] is not None else None
    a["first_value_bucket"] = bucket(a["first_value_s"], (4.0,), ("under_4s", "4s_or_later"))
    a["duration_s"] = round(timing["duration_s"], 2) if timing.get("duration_s") else None
    a["duration_bucket"] = bucket(a["duration_s"], (26.0,), ("under_26s", "26s_or_longer"))
    scenes = sb.get("scenes") or []
    a["scenes_n"] = len(scenes) or None
    a["scenes_per_10s"] = round(10 * len(scenes) / a["duration_s"], 2) if scenes and a["duration_s"] else None
    a["scene_density_bucket"] = bucket(a["scenes_per_10s"], (2.5,), ("under_2.5_per_10s", "2.5_per_10s_or_more"))
    chosen = pkg.get("selected") if isinstance(pkg.get("selected"), dict) else {}
    a["title"] = chosen.get("title")
    a["title_form"] = (LA.opening_form(a["title"]) if a["title"] else None)
    s0 = next((s for s in sel.get("selected") or [] if s.get("video_id") == vid), None)
    a["format"] = (s0 or {}).get("format")
    c = cats.get(norm(run.get("topic") or ""))
    a["category"] = c["category"] if c else None
    a["category_source"] = c["source"] if c else "unavailable: no idea-batch manifest assigned a category to this topic"
    ref = run.get("learning") or {}
    a["learning_ref"] = {k: ref.get(k) for k in ("summary_id", "sha256", "hypothesis_id")} if ref else None
    arm = next((m.groups() for c in run.get("constraints") or [] for m in [re.search(r"\b(H\d+[\w-]*)\s+arm=(\w+)", str(c))] if m), None)
    a["experiment_arm"] = {"experiment": arm[0], "arm": arm[1]} if arm else None
    a["sources"] = src
    a["missing"] = sorted(k for k in ("opening_form", "curiosity_mechanism", "first_value_s", "duration_s", "scenes_n",
                                      "title", "format", "category", "video_kind") if a.get(k) is None)
    return a


def cmd_attributes(a) -> dict:
    con = ro(a.db)
    pubs = publications(con)
    runs = find_run_dirs(a.runs_root)
    cats = categories_from_manifests(a.manifests)
    recs, gaps = [], []
    for pid, (run_id, vid, at) in sorted(pubs.items(), key=lambda x: x[1][2] or ""):
        d = runs.get(run_id)
        if not d:
            gaps.append({"platform_video_id": pid, "run_id": run_id, "reason": "run folder not found under --runs-root"})
            continue
        r = video_attributes(d, run_id, vid, cats)
        r.update(platform_video_id=pid, published_at=at, run_dir=str(d))
        h = dt.datetime.fromisoformat(at.replace("Z", "+00:00")).hour if at else None
        r["publish_slot_utc"] = f"{h:02d}h" if h is not None else None
        recs.append(r)
    doc = {"schema": "cf-creative-attributes/1", "generated_at": now_iso(), "rules": LA.RULES,
           "buckets": {"first_value_bucket": "first value/payoff beat starts before 4.0 s", "duration_bucket": "26 s",
                       "scene_density_bucket": "2.5 scenes per 10 s"},
           "videos": recs, "gaps": gaps, "duplicate_run_folders": DUPLICATE_RUN_DIRS,
           "coverage": {k: sum(1 for r in recs if r.get(k) is not None) for k in
                        ("opening_form", "curiosity_mechanism", "first_value_s", "duration_s", "scenes_n", "title", "format", "category")}}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"videos": len(recs), "gaps": len(gaps), "coverage": doc["coverage"], "out": a.out}


# ----------------------------------------------------------------------------- kpis
def snapshots(con) -> list[dict]:
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "yt_snapshots" not in tables:
        return []
    return [{"sha": s, "pulled_at": p, "cutoff": c} for s, p, c in
            con.execute("SELECT snapshot_sha256, pulled_at, analytics_cutoff_day FROM yt_snapshots ORDER BY pulled_at")]


def kpis_for(con, pid: str, published_at: str | None, snaps: list[dict], dur_hint=None) -> dict:
    pub_day = pacific_day(published_at)
    out = {"platform_video_id": pid, "publication_day_pt": pub_day}
    if not snaps:
        return {**out, "maturity": "none", "analytics_days": 0, "status": "no snapshot imported"}
    info = []
    for s in snaps:
        if not (s["cutoff"] and pub_day):
            continue
        days = (dt.date.fromisoformat(s["cutoff"]) - dt.date.fromisoformat(pub_day)).days + 1
        info.append((s, max(0, days)))
    latest_days = max((d for _, d in info), default=0)
    out["analytics_days"] = latest_days
    out["maturity"] = "none" if latest_days <= 0 else "early" if latest_days < 3 else "d3" if latest_days < 7 else "d7"
    for n in (1, 3, 7):
        cand = [s for s, d in info if d >= n]
        if not cand:
            out[f"views_d{n}"] = out[f"engaged_views_d{n}"] = out[f"engaged_share_d{n}"] = None
            out[f"status_d{n}"] = "immature"
            continue
        s = cand[-1]
        last = (dt.date.fromisoformat(pub_day) + dt.timedelta(days=n - 1)).isoformat()
        rows = {}
        for m, day, val, st in con.execute(
                "SELECT metric, dimension_value, value, status FROM yt_observations WHERE snapshot_sha256=? AND "
                "platform_video_id=? AND report='video_daily' AND dimension_value BETWEEN ? AND ?", (s["sha"], pid, pub_day, last)):
            rows.setdefault(m, {})[day] = (val, st)
        days = [(dt.date.fromisoformat(pub_day) + dt.timedelta(days=i)).isoformat() for i in range(n)]
        ok = all(rows.get(m, {}).get(d, (None, ""))[1] == "ok" for m in ("views", "engagedViews") for d in days)
        if not ok:
            out[f"views_d{n}"] = out[f"engaged_views_d{n}"] = out[f"engaged_share_d{n}"] = None
            out[f"status_d{n}"] = "incomplete: daily rows missing or not ok in snapshot " + s["sha"][:12]
            continue
        v = sum(rows["views"][d][0] for d in days)
        e = sum(rows["engagedViews"][d][0] for d in days)
        out[f"views_d{n}"], out[f"engaged_views_d{n}"] = v, e
        out[f"engaged_share_d{n}"] = round(e / v, 4) if v > 0 else None
        out[f"status_d{n}"] = "ok" if v > 0 else "no views in window"
        out[f"snapshot_d{n}"] = s["sha"][:12]
    # lifetime-at-cutoff values from the newest snapshot with an ok totals row
    out.update(avg_view_pct=None, avg_view_dur_s=None, subscribers_gained=None, views_total=None, retention_3s=None,
               lifetime_age_days=None, lifetime_status="no Analytics totals yet")
    for s, d in reversed(info):
        tot = {m: (v, st) for m, v, st in con.execute(
            "SELECT metric, value, status FROM yt_observations WHERE snapshot_sha256=? AND platform_video_id=? AND "
            "report='video_totals'", (s["sha"], pid))}
        if tot.get("views", (None, ""))[1] != "ok":
            continue
        g = lambda k: tot.get(k, (None, ""))[0] if tot.get(k, (None, ""))[1] == "ok" else None  # noqa: E731
        out.update(avg_view_pct=g("averageViewPercentage"), avg_view_dur_s=g("averageViewDuration"),
                   subscribers_gained=g("subscribersGained"), views_total=g("views"), lifetime_age_days=d,
                   lifetime_status=f"ok at {d} Analytics days (snapshot {s['sha'][:12]})")
        dur = dur_hint
        if dur is None:
            r = con.execute("SELECT duration FROM yt_videos WHERE snapshot_sha256=? AND platform_video_id=?", (s["sha"], pid)).fetchone()
            dur = iso_dur(r[0]) if r else None
        if dur:
            pts = [(float(x), v) for x, v, st in con.execute(
                "SELECT dimension_value, value, status FROM yt_observations WHERE snapshot_sha256=? AND platform_video_id=? "
                "AND report='video_retention' AND metric='audienceWatchRatio' AND status='ok'", (s["sha"], pid))]
            if pts:
                tgt = 3.0 / dur
                x, v = min(pts, key=lambda p: abs(p[0] - tgt))
                out["retention_3s"] = round(v, 4)
                out["retention_3s_point"] = x
        break
    pv = con.execute("SELECT value, snapshot_sha256 FROM yt_observations o JOIN yt_snapshots s USING(snapshot_sha256) "
                     "WHERE platform_video_id=? AND report='data_api_statistics' AND metric='public_views' AND status='ok' "
                     "ORDER BY s.pulled_at DESC LIMIT 1", (pid,)).fetchone()
    out["public_views_at_pull"] = pv[0] if pv else None
    return out


def all_kpis(con, attrs: dict | None = None) -> tuple[list[dict], list[dict]]:
    snaps = snapshots(con)
    pubs = publications(con)
    durs = {r["platform_video_id"]: r.get("duration_s") for r in (attrs or {}).get("videos", [])}
    rows = []
    for pid, (run_id, vid, at) in sorted(pubs.items(), key=lambda x: x[1][2] or ""):
        rows.append({"run_id": run_id, "video_id": vid, "published_at": at, **kpis_for(con, pid, at, snaps, durs.get(pid))})
    return rows, snaps


def cmd_kpis(a) -> dict:
    con = ro(a.db)
    rows, snaps = all_kpis(con)
    doc = {"schema": "cf-kpis/1", "generated_at": now_iso(), "snapshots": snaps, "videos": rows}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return {"videos": len(rows), "snapshots": len(snaps), "by_maturity": count(r["maturity"] for r in rows), "out": a.out}


def count(it) -> dict:
    d = {}
    for x in it:
        d[x] = d.get(x, 0) + 1
    return dict(sorted(d.items()))


# ----------------------------------------------------------------------------- analysis
def transform(metric: str, v):
    if v is None:
        return None
    return math.log(v + 1) if metric.startswith("views") else v


def boot_interval(xs: list[float], ys: list[float], seed: int, n: int, level: float) -> tuple[float, float]:
    rng = random.Random(seed)
    diffs = []
    for _ in range(n):
        a = [rng.choice(xs) for _ in xs]
        b = [rng.choice(ys) for _ in ys]
        diffs.append(statistics.fmean(a) - statistics.fmean(b))
    diffs.sort()
    lo, hi = diffs[int((1 - level) / 2 * n)], diffs[int((1 + level) / 2 * n) - 1]
    return lo, hi


def compare(videos: list[dict], attr: str, metric: str, prev: dict | None) -> list[dict]:
    pol = POLICY
    vals = [(v.get(attr), transform(metric, v.get(metric))) for v in videos]
    vals = [(lv, x) for lv, x in vals if lv is not None and x is not None]
    if len(vals) < 2:
        return []
    grand = statistics.fmean(x for _, x in vals)
    out = []
    for lvl in sorted({str(lv) for lv, _ in vals}):
        xs = [x for lv, x in vals if str(lv) == lvl]
        ys = [x for lv, x in vals if str(lv) != lvl]
        k = pol["shrinkage_k"]
        shrunk = (len(xs) * statistics.fmean(xs) + k * grand) / (len(xs) + k)
        row = {"attribute": attr, "level": lvl, "metric": metric, "n": len(xs), "n_rest": len(ys),
               "mean": round(statistics.fmean(xs), 4), "median": round(statistics.median(xs), 4),
               "mean_rest": round(statistics.fmean(ys), 4) if ys else None, "channel_mean": round(grand, 4),
               "effect_raw": round(statistics.fmean(xs) - statistics.fmean(ys), 4) if ys else None,
               "effect_shrunk": round(shrunk - grand, 4), "transform": "ln(views+1)" if metric.startswith("views") else "none"}
        if len(xs) < pol["min_group_n"] or len(ys) < pol["min_group_n"]:
            row.update(confidence="insufficient", interval=None,
                       note=f"n={len(xs)} vs {len(ys)}: below the minimum of {pol['min_group_n']} per side")
        else:
            seed = pol["bootstrap"]["seed"] + int(hashlib.sha256(f"{attr}|{lvl}|{metric}".encode()).hexdigest()[:6], 16)
            lo, hi = boot_interval(xs, ys, seed, pol["bootstrap"]["resamples"], pol["bootstrap"]["interval"])
            row["interval"] = [round(lo, 4), round(hi, 4)]
            excl = lo > 0 or hi < 0
            conf = "low"
            if excl and len(xs) >= 6 and len(ys) >= 6:
                conf = "medium"
                pe = ((prev or {}).get("effects") or {}).get(f"{attr}|{lvl}|{metric}")
                if len(xs) >= 10 and len(ys) >= 10 and pe is not None and (pe > 0) == (row["effect_raw"] > 0):
                    conf = "high"
            row["confidence"] = conf
        out.append(row)
    return out


def fmt_effect(metric: str, e) -> str:
    if e is None:
        return "n/a"
    if metric.startswith("views"):
        return f"{(math.exp(e) - 1) * 100:+.0f}% views"
    if metric in ("engaged_share_d3", "engaged_share_d1", "retention_3s"):
        return f"{e * 100:+.1f} pp"
    return f"{e:+.1f} pp"


def directive_entry(row: dict) -> dict | None:
    """A directive needs n>=3 per side AND an 80% interval that excludes 0: a level whose direction is not established
    gets no bonus or penalty (otherwise noise would act as a tie-breaker and pile every batch onto one level)."""
    if row["confidence"] == "insufficient" or row["effect_raw"] is None or not row.get("interval"):
        return None
    lo, hi = row["interval"]
    if lo <= 0 <= hi:
        return None
    cap = POLICY["caps"][row["confidence"]]
    full = POLICY["effect_for_full_cap"][PRIMARY]
    m = 1 + cap * max(-1.0, min(1.0, row["effect_shrunk"] / full))
    return {"multiplier": round(m, 4), "confidence": row["confidence"], "n": row["n"], "n_rest": row["n_rest"],
            "metric": PRIMARY, "effect_label": f"{fmt_effect(PRIMARY, row['effect_shrunk'])} shrunk vs channel mean",
            "interval": row["interval"]}


def find_experiment(exp_dir: str | None, attr: str) -> dict | None:
    if not exp_dir or not Path(exp_dir).is_dir():
        return None
    keys = {"opening_form": ("first spoken line", "opening", "first line")}.get(attr, ())
    for spec in sorted(Path(exp_dir).glob("*/spec.json")):
        s = jload(spec) or {}
        text = f"{s.get('variable', '')} {s.get('hypothesis', '')}".lower()
        if keys and any(k in text for k in keys):
            return {"experiment_id": s.get("experiment_id"), "spec": str(spec), "status": s.get("status"),
                    "arms": sorted((s.get("arms") or {}).keys())}
    return None


def registered(exp_dir: str | None) -> list[dict]:
    """Experiments the owner already designed (experiments/*/spec.json): listed so a new hypothesis never silently
    replaces a pre-registered one."""
    out = []
    for spec in sorted(Path(exp_dir).glob("*/spec.json")) if exp_dir and Path(exp_dir).is_dir() else []:
        s = jload(spec) or {}
        out.append({"experiment_id": s.get("experiment_id"), "status": s.get("status"), "variable": s.get("variable"),
                    "primary_metric": s.get("primary_metric"), "spec": str(spec)})
    return out


def cmd_analyze(a) -> dict:
    con = ro(a.db)
    attrs = jload(Path(a.attributes))
    if not attrs or attrs.get("schema") != "cf-creative-attributes/1":
        raise Fail("ATTRIBUTES_INVALID", path=a.attributes)
    kp, snaps = all_kpis(con, attrs)
    if not snaps:
        raise Fail("NO_SNAPSHOTS", detail="import a yt_sync snapshot with ingest_analytics.py --apply first")
    by = {r["platform_video_id"]: r for r in attrs["videos"]}
    videos = []
    for k in kp:
        at = by.get(k["platform_video_id"]) or {}
        videos.append({**{x: at.get(x) for x in ("topic", "title", "hook_text", "opening_form", "curiosity_mechanism", "format",
                                                  "category", "title_form", "duration_s", "duration_bucket", "first_value_s",
                                                  "first_value_bucket", "has_setup_beat", "scenes_per_10s",
                                                  "scene_density_bucket", "ends_with_loop", "cta_beat", "publish_slot_utc",
                                                  "learning_ref", "experiment_arm")}, **k, "attributes_found": bool(at)})
    prev = jload(Path(a.previous)) if a.previous else None
    prev_eff = {"effects": {f"{c['attribute']}|{c['level']}|{c['metric']}": c.get("effect_raw")
                            for c in (prev or {}).get("comparisons", [])}} if prev else None
    eligible = [v for v in videos if v.get(PRIMARY) is not None]
    comps = []
    for attr in COMPARE_ATTRS:
        for metric in (PRIMARY, *SECONDARY):
            pool = eligible if metric in (PRIMARY, "views_d3") else [v for v in videos if v.get(metric) is not None]
            comps += compare(pool, attr, metric, prev_eff)
    prim = [c for c in comps if c["metric"] == PRIMARY]
    guard = {(c["attribute"], c["level"]): c for c in comps if c["metric"] == GUARDRAIL}
    works, under, unclear = [], [], []
    for c in prim:
        if c["confidence"] == "insufficient":
            continue
        g = guard.get((c["attribute"], c["level"]))
        gnote = (f"; guardrail {METRIC_LABEL[GUARDRAIL]} {fmt_effect(GUARDRAIL, g['effect_raw'])} (n={g['n']} vs {g['n_rest']})"
                 if g and g.get("effect_raw") is not None else "")
        text = (f"{c['attribute']}={c['level']}: {METRIC_LABEL[PRIMARY]} {c['mean'] * 100:.1f}% vs {c['mean_rest'] * 100:.1f}% "
                f"for the rest (raw {fmt_effect(PRIMARY, c['effect_raw'])}, shrunk {fmt_effect(PRIMARY, c['effect_shrunk'])}; "
                f"n={c['n']} vs {c['n_rest']}; 80% interval {fmt_effect(PRIMARY, c['interval'][0])} … "
                f"{fmt_effect(PRIMARY, c['interval'][1])}){gnote}")
        item = {"attribute": c["attribute"], "level": c["level"], "confidence": c["confidence"], "evidence": text,
                "n": c["n"], "n_rest": c["n_rest"]}
        guard_bad = bool(g and g.get("effect_raw") is not None and g["effect_raw"] < -5 and c["effect_raw"] > 0)
        if c["interval"][0] > 0 and not guard_bad:
            works.append(item)
        elif c["interval"][1] < 0:
            under.append(item)
        else:
            item["direction"] = "higher" if c["effect_raw"] > 0 else "lower"
            item["why_unclear"] = ("the guardrail (avg view %) is more than 5 pp worse" if guard_bad
                                   else "the 80% interval includes no difference")
            unclear.append(item)
    # a two-level attribute yields two mirror-image rows; keep the side with the positive raw effect
    def dedupe(items):
        lv = {}
        for c in prim:
            lv.setdefault(c["attribute"], set()).add(c["level"])
        keep = []
        for it in items:
            if len(lv.get(it["attribute"], ())) == 2:
                mate = next((c for c in prim if c["attribute"] == it["attribute"] and c["level"] == it["level"]), None)
                if mate and mate["effect_raw"] is not None and mate["effect_raw"] < 0 and any(
                        x["attribute"] == it["attribute"] and x["level"] != it["level"] for x in works + under + unclear):
                    continue
            keep.append(it)
        return keep
    works, under, unclear = dedupe(works), dedupe(under), dedupe(unclear)
    # directives (bounded; none below n=3 per side)
    directives = {"topic": {"category": {}, "format": {}}, "hook": {"opening_form": {}, "curiosity_mechanism": {}},
                  "script": {}, "guidance": {"hook": [], "script": []}, "explore": []}
    for c in prim:
        grp = DIRECTIVE_ATTRS.get(c["attribute"])
        e = directive_entry(c)
        g = guard.get((c["attribute"], c["level"]))
        if e and e["multiplier"] > 1 and g and g.get("effect_raw") is not None and g["effect_raw"] < -5:
            directives["explore"].append(f"{c['attribute']}={c['level']}: higher {METRIC_LABEL[PRIMARY]} but the guardrail "
                                         f"{METRIC_LABEL[GUARDRAIL]} is {fmt_effect(GUARDRAIL, g['effect_raw'])} — no bonus")
            e = None
        if grp and e:
            directives[grp][c["attribute"]][c["level"]] = e
        elif c["attribute"] in SCRIPT_ATTRS and e:
            directives["script"].setdefault(c["attribute"], {})[c["level"]] = e
        if c["confidence"] == "insufficient" and c["attribute"] in (*DIRECTIVE_ATTRS, *SCRIPT_ATTRS):
            directives["explore"].append(f"{c['attribute']}={c['level']} (n={c['n']} vs {c['n_rest']}): comparison under-powered "
                                         "— keep it in rotation; no penalty or bonus")
        elif c["attribute"] in (*DIRECTIVE_ATTRS, *SCRIPT_ATTRS) and c.get("interval") and c["interval"][0] <= 0 <= c["interval"][1]:
            directives["explore"].append(f"{c['attribute']}={c['level']} (n={c['n']} vs {c['n_rest']}): direction not established "
                                         f"(80% interval {fmt_effect(PRIMARY, c['interval'][0])} … "
                                         f"{fmt_effect(PRIMARY, c['interval'][1])}) — no penalty or bonus")
    for attr in ("opening_form", "curiosity_mechanism"):
        ups = [(k, v) for k, v in directives["hook"][attr].items() if v["multiplier"] > 1]
        downs = [(k, v) for k, v in directives["hook"][attr].items() if v["multiplier"] < 1]
        for k, v in sorted(ups, key=lambda kv: -kv[1]["multiplier"]):
            directives["guidance"]["hook"].append(
                f"Evidence ({v['confidence']} confidence, n={v['n']}): {attr} '{k}' went with a higher {METRIC_LABEL[PRIMARY]} "
                f"({v['effect_label']}). Include at least one '{k}' candidate; the review still decides.")
        for k, v in sorted(downs, key=lambda kv: kv[1]["multiplier"]):
            directives["guidance"]["hook"].append(
                f"Evidence ({v['confidence']} confidence, n={v['n']}): {attr} '{k}' went with a lower {METRIC_LABEL[PRIMARY]} "
                f"({v['effect_label']}). Do not drop it; pair it with a stronger alternative.")
    for attr, levels in directives["script"].items():
        for k, v in sorted(levels.items(), key=lambda kv: -kv[1]["multiplier"]):
            directives["guidance"]["script"].append(
                f"Evidence ({v['confidence']} confidence, n={v['n']}): {attr} '{k}' went with "
                f"{'a higher' if v['multiplier'] > 1 else 'a lower'} {METRIC_LABEL[PRIMARY]} ({v['effect_label']}).")
    # next experiment: the largest shrunk effect that is not yet medium/high confidence, on a hook/script attribute
    cands = [c for c in prim if c["attribute"] in ("opening_form", "curiosity_mechanism", *SCRIPT_ATTRS)
             and c["confidence"] in ("low", "insufficient") and c["n"] >= 2]
    nx = None
    if cands:
        c = max(cands, key=lambda c: (abs(c["effect_shrunk"]), c["n"]))
        exp = find_experiment(a.experiments_dir, c["attribute"])
        hid = (exp or {}).get("experiment_id") or f"H-{c['attribute']}-{c['level']}"
        nx = {"hypothesis_id": hid, "attribute": c["attribute"],
              "arms": (exp or {}).get("arms") or [c["level"], f"not_{c['level']}"],
              "statement": f"Videos with {c['attribute']}={c['level']} get a {'higher' if c['effect_shrunk'] > 0 else 'lower'} "
                           f"{METRIC_LABEL[PRIMARY]} than comparable videos without it.",
              "current_evidence": f"shrunk {fmt_effect(PRIMARY, c['effect_shrunk'])}, n={c['n']} vs {c['n_rest']}, "
                                  f"confidence {c['confidence']}",
              "design": "paired topics, one arm each, same publish slots, measured at D3 and D7; decide only on the "
                        "pre-registered rule", "existing_spec": exp}
    # hypothesis tracking (videos made under an earlier summary / experiment arm)
    tracking = {}
    for v in videos:
        tags = []
        if v.get("learning_ref") and v["learning_ref"].get("hypothesis_id"):
            tags.append(("learning", v["learning_ref"]["hypothesis_id"], v["learning_ref"].get("summary_id")))
        if v.get("experiment_arm"):
            tags.append(("experiment", v["experiment_arm"]["experiment"], v["experiment_arm"]["arm"]))
        for kind, hid, sub in tags:
            t = tracking.setdefault(hid, {"hypothesis_id": hid, "kind": kind, "videos": []})
            t["videos"].append({"platform_video_id": v["platform_video_id"], "tag": sub, "maturity": v["maturity"],
                                PRIMARY: v.get(PRIMARY)})
    for t in tracking.values():
        vals = [x[PRIMARY] for x in t["videos"] if x[PRIMARY] is not None]
        rest = [v[PRIMARY] for v in eligible if v["platform_video_id"] not in {x["platform_video_id"] for x in t["videos"]}]
        t["n_measured"] = len(vals)
        t["status"] = ("waiting for D3 data" if not vals else
                       f"measured {len(vals)}: mean {statistics.fmean(vals) * 100:.1f}% vs {statistics.fmean(rest) * 100:.1f}% "
                       f"for the other videos (n={len(rest)}); not a decision until the pre-registered sample is complete"
                       if rest else f"measured {len(vals)}")
    mat = count(v["maturity"] for v in videos)
    conf_all = sorted({c["confidence"] for c in prim if c["confidence"] != "insufficient"})
    s_conf = "high" if "high" in conf_all else "medium" if "medium" in conf_all else "low" if conf_all else "insufficient"
    pol = {**POLICY, "summary_confidence": s_conf}
    cutoff = max(s["cutoff"] for s in snaps if s["cutoff"])
    core = {"schema": SCHEMA, "version": VERSION,
            "inputs": {"db": str(Path(a.db).resolve()), "db_sha256": sha(Path(a.db)), "snapshots": snaps,
                       "analytics_cutoff": cutoff, "attributes": str(Path(a.attributes).resolve()),
                       "attributes_sha256": sha(Path(a.attributes)), "previous_summary": (prev or {}).get("summary_id")},
            "policy": pol,
            "data_quality": {"published_factory_videos": len(videos), "by_maturity": mat,
                             "with_primary_metric": len(eligible),
                             "attribute_coverage": attrs.get("coverage"), "attribute_gaps": attrs.get("gaps"),
                             "legacy_channel_excluded": sorted(L.LEGACY_CHANNEL_VIDEOS),
                             "not_available_from_api": ["Stayed to watch (Studio only; engaged share is the API proxy)",
                                                        "Shown in feed (Studio only)"],
                             "known_limitations": [
                                 "Analytics days run midnight-to-midnight Pacific; day 1 is partial and its length depends "
                                 "on the publish slot (16:00Z = 09:00 PT, 21:00Z = 14:00 PT)",
                                 "average view % and retention are lifetime values at the snapshot cutoff, not age-matched",
                                 "groups differ in topic, publish day and slot as well as in the attribute compared",
                                 "category is known only where an idea-batch manifest assigned it"]},
            "videos": videos, "comparisons": comps,
            "findings": {"appears_to_work": works, "appears_to_underperform": under, "unclear": unclear},
            "directives": directives, "next_experiment": nx, "registered_experiments": registered(a.experiments_dir), "hypothesis_tracking": sorted(tracking.values(), key=lambda t: t["hypothesis_id"])}
    sid = "L-" + cutoff + "-" + hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()[:10]
    doc = {"summary_id": sid, "generated_at": now_iso(), **core}
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "learning_summary.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "LEARNING_REPORT.md").write_text(report_md(doc), encoding="utf-8")
    if a.publish_latest:
        lp = Path(a.publish_latest)
        lp.parent.mkdir(parents=True, exist_ok=True)
        lp.write_text((out / "learning_summary.json").read_text(encoding="utf-8"), encoding="utf-8")
    return {"summary_id": sid, "out": str(out), "videos": len(videos), "with_primary_metric": len(eligible), "by_maturity": mat,
            "findings": {k: len(v) for k, v in doc["findings"].items()},
            "directives": {g: {k: len(v) for k, v in d.items()} for g, d in directives.items() if isinstance(d, dict) and g != "guidance"},
            "summary_confidence": s_conf, "latest": a.publish_latest}


def report_md(d: dict) -> str:
    q, f, dr = d["data_quality"], d["findings"], d["directives"]
    L_ = [f"# Learning report — {d['summary_id']}", "",
          f"Analytics cutoff **{d['inputs']['analytics_cutoff']}** (Pacific) · {len(d['inputs']['snapshots'])} snapshot(s) · "
          f"generated {d['generated_at']} · overall confidence **{d['policy']['summary_confidence']}**", "",
          "Correlation, not causation: the groups below differ in topic, day and slot as well as in the attribute.", "",
          "## Evidence base", "",
          f"- Published factory videos: {q['published_factory_videos']} · maturity {q['by_maturity']} · "
          f"with the primary metric ({METRIC_LABEL[PRIMARY]}): {q['with_primary_metric']}",
          f"- Legacy channel videos excluded: {', '.join(q['legacy_channel_excluded'])}",
          f"- Attribute coverage: {q['attribute_coverage']}", ""]
    L_ += ["| video | published | maturity | D3 engaged share | D3 views | avg view % (age) | opening | mechanism |",
           "|---|---|---|---|---|---|---|---|"]
    for v in d["videos"]:
        es = f"{v[PRIMARY] * 100:.1f}%" if v.get(PRIMARY) is not None else "—"
        av = f"{v['avg_view_pct']:.1f} ({v['lifetime_age_days']}d)" if v.get("avg_view_pct") is not None else "—"
        L_.append(f"| {v['platform_video_id']} {(v.get('title') or v.get('topic') or '')[:38]} | {(v.get('published_at') or '')[:10]} | "
                  f"{v['maturity']} | {es} | {int(v['views_d3']) if v.get('views_d3') is not None else '—'} | {av} | "
                  f"{v.get('opening_form') or '—'} | {v.get('curiosity_mechanism') or '—'} |")
    for title, key in (("What appears to work", "appears_to_work"), ("What appears to underperform", "appears_to_underperform"),
                       ("Unclear", "unclear")):
        L_ += ["", f"## {title}", ""]
        L_ += [f"- [{x['confidence']}] {x['evidence']}" + (f" — unclear because {x['why_unclear']}" if x.get("why_unclear") else "")
               for x in f[key]] or ["- nothing at the current sample size"]
    L_ += ["", "## What changes in the next batch (bounded directives)", ""]
    any_d = False
    for g in ("topic", "hook", "script"):
        for attr, levels in dr[g].items():
            for lvl, e in levels.items():
                any_d = True
                L_.append(f"- {g}: {attr}={lvl} ×{e['multiplier']:.3f} ({e['confidence']}, n={e['n']} vs {e['n_rest']}; {e['effect_label']})")
    if not any_d:
        L_.append("- none: no attribute has ≥3 videos on each side with the primary metric")
    L_ += [f"- hook guidance: {x}" for x in dr["guidance"]["hook"]] + [f"- script guidance: {x}" for x in dr["guidance"]["script"]]
    L_ += ["", "Under-tested (kept in rotation, no penalty):", ""] + [f"- {x}" for x in dr["explore"]] or []
    nx = d.get("next_experiment")
    L_ += ["", "## Next hypothesis to test", ""]
    L_ += ([f"- **{nx['hypothesis_id']}** — {nx['statement']}", f"- current evidence: {nx['current_evidence']}",
            f"- arms: {nx['arms']} · design: {nx['design']}"] + ([f"- existing spec: {nx['existing_spec']['spec']} "
                                                                  f"({nx['existing_spec']['status']})"] if nx.get("existing_spec") else [])
           if nx else ["- none"])
    L_ += ["", "Experiments already designed by the owner (not replaced by the hypothesis above):", ""]
    L_ += [f"- {x['experiment_id']} — {x['status']} — {x['variable']}" for x in d.get("registered_experiments") or []] or ["- none"]
    L_ += ["", "## Earlier hypotheses", ""]
    L_ += [f"- {t['hypothesis_id']} ({t['kind']}): {len(t['videos'])} video(s); {t['status']}" for t in d["hypothesis_tracking"]] or \
        ["- no published video was made under a recorded hypothesis yet"]
    L_ += ["", "## Data limits", ""] + [f"- {x}" for x in q["known_limitations"] + q["not_available_from_api"]]
    return "\n".join(L_) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("attributes")
    s.add_argument("--db", required=True); s.add_argument("--runs-root", action="append", required=True)
    s.add_argument("--manifests", action="append", default=[]); s.add_argument("--out", required=True)
    s = sub.add_parser("kpis")
    s.add_argument("--db", required=True); s.add_argument("--out", required=True)
    s = sub.add_parser("analyze")
    s.add_argument("--db", required=True); s.add_argument("--attributes", required=True); s.add_argument("--out-dir", required=True)
    s.add_argument("--previous"); s.add_argument("--experiments-dir"); s.add_argument("--publish-latest")
    a = ap.parse_args()
    try:
        res = {"attributes": cmd_attributes, "kpis": cmd_kpis, "analyze": cmd_analyze}[a.cmd](a)
    except Fail as e:
        print(json.dumps(e.info, ensure_ascii=True))
        return 2
    print(json.dumps(res, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
