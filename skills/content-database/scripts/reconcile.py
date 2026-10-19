#!/usr/bin/env python3
"""reconcile — bring work done on another machine (a cloud worker) into the canonical Windows factory.db, safely.

  reconcile.py plan  --db CANONICAL.db (--run RUN_DIR ... | --dump cloud_dump.json) --out plan.json
  reconcile.py apply --db CANONICAL.db --plan plan.json [--report applied.json]

The canonical database is the single source of truth (docs/v3.1.0/ARCHITECTURE.md). Other machines never overwrite it:

  plan   opens CANONICAL read-only. Candidate rows come from cloud run folders (ingested with cfdb.py's own ingest logic
         into a throw-away database) or from a cloud dump.json. Each candidate row is compared with the canonical row
         that has the same primary key:
           insert     no canonical row with that key                       -> will be inserted
           identical  same key, same values (volatile columns ignored)     -> nothing to do
           conflict   same key, different values                           -> NEVER written; listed with the diff
         Identity is the full primary key: a generic video id such as `v01` is only ever matched together with its
         run_id. Run folders are validated first: every global stage passed, every video `packaged`, and every final.mp4 hashes to
         the final_sha256 the run recorded; a run that fails validation contributes no rows.
         Only factory production tables are reconciled (runs, ideas, videos, assets, stage_results). publications,
         metrics, weights and yt_* rows are reported but never planned: they are written only by their own evidence-
         checking tools (ingest_youtube.py, ingest_analytics.py, cfdb.py log-feedback).
  apply  re-plans against the current canonical file and refuses unless the result is identical to the plan file
         (nothing changed in between). It copies the database to <db>.bak-<timestamp>, inserts the planned rows in ONE
         transaction (plain INSERT, no REPLACE), re-reads every inserted row, compares the row counts with the plan and
         writes a reconciliation report. On any error nothing is written. Conflicts never block the inserts of other
         keys, but they are repeated in the report so the owner decides them by hand.
Exit: 0 ok (plan written / applied) · 2 invalid input, validation failure of every run, or the plan no longer matches.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFDB = HERE / "cfdb.py"
PK = {"runs": ("run_id",), "ideas": ("run_id", "idea_id"), "videos": ("run_id", "video_id"),
      "assets": ("run_id", "video_id", "role"), "stage_results": ("run_id", "video_id", "stage", "attempt")}
VOLATILE = {"videos": ("created_at",)}
DONE = {"passed", "passed_with_warnings", "skipped"}      # = factory.py DONE       # cfdb ingest-run stamps the ingest time; not a property of the video
NOT_PLANNED = ("publications", "metrics", "weights")


def fail(code: str, **info) -> int:
    print(json.dumps({"error": code, **info}, ensure_ascii=True))
    return 2


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def ro(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)


def rows_of(con, table: str) -> list[dict]:
    cur = con.execute(f"SELECT * FROM {table}")
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def validate_run(run: Path) -> list[str]:
    probs = []
    st = json.loads((run / "state.json").read_text(encoding="utf-8")) if (run / "state.json").is_file() else None
    if not st:
        return ["state.json missing"]
    bad_g = {k: v.get("status") for k, v in (st.get("global") or {}).items() if v.get("status") not in DONE}
    if bad_g:
        probs.append(f"global stages not passed: {bad_g}")
    bad_v = {k: v.get("status") for k, v in (st.get("videos") or {}).items() if v.get("status") != "packaged"}
    if bad_v or not st.get("videos"):
        probs.append(f"videos not packaged: {bad_v or 'none'}")
    for prov in sorted((run / "package").glob("*/provenance.json")):
        p = json.loads(prov.read_text(encoding="utf-8"))
        want = (p.get("final") or {}).get("sha256")
        mp4 = prov.parent / "final.mp4"
        if not want:
            probs.append(f"{prov.parent.name}: provenance has no final sha256")
        elif not mp4.is_file():
            probs.append(f"{prov.parent.name}: package/final.mp4 missing")
        elif sha_file(mp4) != want:
            probs.append(f"{prov.parent.name}: final.mp4 does not match its recorded sha256")
    if not list((run / "package").glob("*/provenance.json")):
        probs.append("no packaged video (package/*/provenance.json)")
    return probs


def candidates_from_runs(runs: list[Path], tmp: Path) -> tuple[dict, list[dict]]:
    db = tmp / "candidate.db"
    subprocess.run([sys.executable, str(CFDB), "init", "--db", str(db)], capture_output=True, text=True, check=True)
    report = []
    for run in runs:
        probs = validate_run(run)
        rid = (json.loads((run / "run.json").read_text(encoding="utf-8")).get("run_id") if (run / "run.json").is_file() else run.name)
        if probs:
            report.append({"run_dir": str(run), "run_id": rid, "valid": False, "problems": probs})
            continue
        p = subprocess.run([sys.executable, str(CFDB), "ingest-run", "--db", str(db), "--run", str(run)], capture_output=True, text=True)
        if p.returncode != 0:
            report.append({"run_dir": str(run), "run_id": rid, "valid": False, "problems": [f"ingest failed: {(p.stderr or p.stdout)[-300:]}"]})
            continue
        report.append({"run_dir": str(run), "run_id": rid, "valid": True, "problems": []})
    con = sqlite3.connect(db)
    out = {t: rows_of(con, t) for t in (*PK, *NOT_PLANNED)}
    con.close()
    return out, report


def candidates_from_dump(dump: Path) -> dict:
    d = json.loads(dump.read_text(encoding="utf-8"))
    t = d.get("tables") or {}
    return {k: list(t.get(k) or []) for k in (*PK, *NOT_PLANNED)} | {"_yt": sorted(k for k in t if k.startswith("yt_"))}


def plan_rows(canon: sqlite3.Connection, cand: dict) -> dict:
    out = {"insert": [], "identical": 0, "conflict": [], "by_table": {}}
    for t, key in PK.items():
        have = {tuple(r[k] for k in key): r for r in rows_of(canon, t)}
        vol = VOLATILE.get(t, ())
        ins = ide = con = 0
        for r in cand.get(t) or []:
            k = tuple(r.get(x) for x in key)
            cur = have.get(k)
            if cur is None:
                out["insert"].append({"table": t, "key": dict(zip(key, k)), "row": r}); ins += 1
                continue
            diff = {c: {"canonical": cur.get(c), "candidate": r.get(c)} for c in r if c not in vol and cur.get(c) != r.get(c)}
            if diff:
                out["conflict"].append({"table": t, "key": dict(zip(key, k)), "diff": diff}); con += 1
            else:
                out["identical"] += 1; ide += 1
        out["by_table"][t] = {"insert": ins, "identical": ide, "conflict": con}
    return out


def make_plan(db: Path, runs: list[Path], dump: Path | None) -> dict:
    canon = ro(db)
    with tempfile.TemporaryDirectory(prefix="reconcile_") as td:
        if dump:
            cand, runrep = candidates_from_dump(dump), []
        else:
            cand, runrep = candidates_from_runs(runs, Path(td))
    p = plan_rows(canon, cand)
    not_planned = {t: len(cand.get(t) or []) for t in NOT_PLANNED if cand.get(t)}
    canon.close()
    body = {"schema": "cf-reconcile-plan/1", "canonical_db": str(db.resolve()), "canonical_sha256": sha_file(db),
            "source": {"dump": str(dump.resolve()) if dump else None, "dump_sha256": sha_file(dump) if dump else None,
                       "runs": runrep},
            "totals": {"insert": len(p["insert"]), "identical": p["identical"], "conflict": len(p["conflict"]),
                       "by_table": p["by_table"]},
            "insert": p["insert"], "conflict": p["conflict"],
            "not_planned": {"rows": not_planned, "yt_tables": cand.get("_yt", []),
                            "why": "publications, metrics, weights and yt_* are written only by their evidence-checking tools"},
            "volatile_columns_ignored": VOLATILE}
    stable = [{**i, "row": {c: v for c, v in i["row"].items() if c not in VOLATILE.get(i["table"], ())}} for i in body["insert"]]
    body["plan_sha256"] = hashlib.sha256(json.dumps({"canonical_sha256": body["canonical_sha256"], "insert": stable,
                                                     "conflict": body["conflict"]}, sort_keys=True, default=str).encode()).hexdigest()
    return body


def cmd_plan(a) -> int:
    db = Path(a.db)
    if not db.is_file():
        return fail("DB_NOT_FOUND", db=a.db)
    if bool(a.dump) == bool(a.run):
        return fail("INPUT", detail="give either --dump or one or more --run")
    runs = [Path(r) for r in a.run or []]
    if any(not (r / "run.json").is_file() for r in runs):
        return fail("RUN_DIR_INVALID", runs=[str(r) for r in runs if not (r / "run.json").is_file()])
    plan = make_plan(db, runs, Path(a.dump) if a.dump else None)
    plan["created_at"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    Path(a.out).write_text(json.dumps(plan, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"plan": a.out, "totals": plan["totals"], "invalid_runs": [r["run_id"] for r in plan["source"]["runs"] if not r["valid"]],
                      "not_planned": plan["not_planned"]["rows"], "plan_sha256": plan["plan_sha256"]}, ensure_ascii=True))
    if runs and not any(r["valid"] for r in plan["source"]["runs"]):
        return 2
    return 0


def cmd_apply(a) -> int:
    db = Path(a.db)
    old = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    src = old["source"]
    runs = [Path(r["run_dir"]) for r in src["runs"]] if not src.get("dump") else []
    new = make_plan(db, runs, Path(src["dump"]) if src.get("dump") else None)
    if new["plan_sha256"] != old["plan_sha256"]:
        return fail("PLAN_STALE", detail="the canonical database or the source changed since the plan; plan again",
                    planned=old["plan_sha256"], now=new["plan_sha256"])
    if not new["insert"]:
        rep = {"applied": 0, "conflicts_not_applied": len(new["conflict"]), "backup": None}
        print(json.dumps(rep)); return 0
    stamp, n = dt.datetime.now().strftime("%Y%m%d-%H%M%S"), 0
    bak = Path(f"{db}.bak-{stamp}")
    while bak.exists():
        n += 1; bak = Path(f"{db}.bak-{stamp}-{n}")
    shutil.copy2(db, bak)
    before = {t: ro(db).execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in PK}
    con = sqlite3.connect(db, isolation_level=None)
    try:
        con.execute("BEGIN")
        for it in new["insert"]:
            r = it["row"]
            con.execute(f"INSERT INTO {it['table']}({','.join(r)}) VALUES({','.join('?' * len(r))})", list(r.values()))
        con.execute("COMMIT")
    except sqlite3.Error as e:
        con.execute("ROLLBACK"); con.close()
        return fail("APPLY_FAILED", detail=str(e)[:300], written=0, backup=str(bak))
    con.close()
    chk = ro(db)
    after = {t: chk.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in PK}
    missing = []
    for it in new["insert"]:
        key = PK[it["table"]]
        got = chk.execute(f"SELECT COUNT(*) FROM {it['table']} WHERE " + " AND ".join(f"{k}=?" for k in key),
                          [it["key"][k] for k in key]).fetchone()[0]
        if got != 1:
            missing.append(it["key"])
    chk.close()
    expect = {t: before[t] + new["totals"]["by_table"][t]["insert"] for t in PK}
    rep = {"schema": "cf-reconcile-report/1", "applied_at": dt.datetime.now(dt.timezone.utc).isoformat(), "db": str(db.resolve()),
           "backup": str(bak), "backup_sha256": sha_file(bak), "plan_sha256": new["plan_sha256"], "inserted": len(new["insert"]),
           "counts_before": before, "counts_after": after, "counts_expected": expect, "verified": after == expect and not missing,
           "missing_after_insert": missing, "conflicts_not_applied": new["conflict"],
           "rollback": f"close every factory process, then copy {bak} over {db}"}
    if a.report:
        Path(a.report).write_text(json.dumps(rep, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("inserted", "verified", "backup")} | {"conflicts_not_applied": len(new["conflict"])}))
    return 0 if rep["verified"] else 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan"); p.add_argument("--db", required=True); p.add_argument("--run", action="append")
    p.add_argument("--dump"); p.add_argument("--out", required=True)
    q = sub.add_parser("apply"); q.add_argument("--db", required=True); q.add_argument("--plan", required=True)
    q.add_argument("--report")
    a = ap.parse_args()
    return cmd_plan(a) if a.cmd == "plan" else cmd_apply(a)


if __name__ == "__main__":
    sys.exit(main())
