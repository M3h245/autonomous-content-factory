"""Tests for reconcile.py (v3.1.0): cloud work reaches the canonical database insert-only, with validation, conflict
detection, idempotency, a backup and a stale-plan guard.

Run:  python skills/content-database/tests/test_reconcile.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import cfdb  # noqa: E402

PY = sys.executable
REC = SCRIPTS / "reconcile.py"


def make_run(root: Path, rid: str, topic: str, packaged=True, corrupt=False) -> Path:
    run = root / rid
    v = run / "videos" / "v01"
    (v / "script").mkdir(parents=True)
    (run / "selection").mkdir(); (run / "ideation").mkdir(); (run / "package" / "v01").mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"run_id": rid, "topic": topic, "created_at": "2026-10-17T10:00:00Z"}), encoding="utf-8")
    (run / "state.json").write_text(json.dumps({"run_id": rid, "status": "in_progress",
                                                "global": {"RESEARCH": {"status": "passed"}, "IDEATION": {"status": "passed"},
                                                           "SELECTION": {"status": "passed"}},
                                                "videos": {"v01": {"status": "packaged" if packaged else "in_progress"}}}), encoding="utf-8")
    (run / "ideation" / "ideas.json").write_text(json.dumps({"ideas": [{"id": "i1", "title": topic, "angle": "a", "format": "explainer"}]}), encoding="utf-8")
    (run / "selection" / "selection.json").write_text(json.dumps({"selected": [{"video_id": "v01", "idea_id": "i1", "final_score": 0.9}]}), encoding="utf-8")
    (v / "script" / "script.json").write_text(json.dumps({"language": "en", "beats": [{"text": f"Hook of {topic}"}],
                                                          "publish": {"title_options": [topic]}}), encoding="utf-8")
    mp4 = b"fake-mp4-" + rid.encode()
    (run / "package" / "v01" / "final.mp4").write_bytes(mp4 + (b"x" if corrupt else b""))
    (run / "package" / "v01" / "provenance.json").write_text(json.dumps(
        {"final": {"sha256": hashlib.sha256(mp4).hexdigest()}, "assets": [{"sha256": "aa", "role": "voice", "license": "x", "source": "y"}]}), encoding="utf-8")
    return run


class Reconcile(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="recon_"))
        self.db = self.tmp / "factory.db"
        con = cfdb.connect(self.db)
        with con:   # the canonical memory already holds an older run whose video id is also v01
            con.execute("INSERT INTO runs VALUES('old-run','Old topic','2026-10-08T00:00:00Z','{}','in_progress')")
            con.execute("INSERT INTO videos(video_id, run_id, title, final_sha256) VALUES('v01','old-run','Old','abc')")
        con.close()
        self.cloud = self.tmp / "cloud"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def rec(self, *args) -> tuple[int, dict]:
        p = subprocess.run([PY, str(REC), *map(str, args)], capture_output=True, text=True)
        return p.returncode, json.loads(p.stdout.strip().splitlines()[-1])

    def plan(self, runs, out="plan.json"):
        args = ["plan", "--db", self.db, "--out", self.tmp / out]
        for r in runs:
            args += ["--run", r]
        return self.rec(*args)

    def counts(self) -> dict:
        con = sqlite3.connect(self.db)
        c = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("runs", "videos", "ideas", "assets", "stage_results")}
        con.close()
        return c

    def test_insert_then_identical_and_generic_ids_never_joined_across_runs(self):
        r1, r2 = make_run(self.cloud, "new-run-1", "Topic one"), make_run(self.cloud, "new-run-2", "Topic two")
        code, res = self.plan([r1, r2])
        self.assertEqual(code, 0, res)
        self.assertEqual(res["totals"]["by_table"]["videos"], {"insert": 2, "identical": 0, "conflict": 0})
        before = self.db.read_bytes()
        self.assertEqual(self.db.read_bytes(), before)                      # plan writes nothing
        code, res = self.rec("apply", "--db", self.db, "--plan", self.tmp / "plan.json", "--report", self.tmp / "rep.json")
        self.assertEqual((code, res["verified"]), (0, True), res)
        self.assertTrue(Path(res["backup"]).read_bytes() == before)         # backup = the database before the write
        self.assertEqual(self.counts()["videos"], 3)
        con = sqlite3.connect(self.db)
        self.assertEqual(con.execute("SELECT title FROM videos WHERE run_id='old-run'").fetchone()[0], "Old")
        con.close()
        code, res = self.plan([r1, r2], "plan2.json")
        self.assertEqual(res["totals"]["insert"], 0)
        self.assertEqual(res["totals"]["conflict"], 0)
        code, res = self.rec("apply", "--db", self.db, "--plan", self.tmp / "plan2.json")
        self.assertEqual(res["applied"], 0)

    def test_conflict_is_reported_and_never_written(self):
        con = sqlite3.connect(self.db)
        with con:
            con.execute("INSERT INTO runs VALUES('new-run-1','A different topic','2026-10-17T10:00:00Z','{}','in_progress')")
        con.close()
        r1 = make_run(self.cloud, "new-run-1", "Topic one")
        code, res = self.plan([r1])
        self.assertEqual(res["totals"]["by_table"]["runs"]["conflict"], 1)
        plan = json.loads((self.tmp / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["conflict"][0]["diff"]["topic"], {"canonical": "A different topic", "candidate": "Topic one"})
        self.rec("apply", "--db", self.db, "--plan", self.tmp / "plan.json")
        con = sqlite3.connect(self.db)
        self.assertEqual(con.execute("SELECT topic FROM runs WHERE run_id='new-run-1'").fetchone()[0], "A different topic")
        self.assertEqual(con.execute("SELECT COUNT(*) FROM videos WHERE run_id='new-run-1'").fetchone()[0], 1)   # other keys go in
        con.close()

    def test_invalid_runs_contribute_nothing(self):
        bad = make_run(self.cloud, "bad-hash", "Bad", corrupt=True)
        unfinished = make_run(self.cloud, "unfinished", "Half", packaged=False)
        code, res = self.plan([bad, unfinished])
        self.assertEqual(code, 2)
        self.assertEqual(sorted(res["invalid_runs"]), ["bad-hash", "unfinished"])
        self.assertEqual(res["totals"]["insert"], 0)

    def test_stale_plan_is_refused(self):
        r1 = make_run(self.cloud, "new-run-1", "Topic one")
        self.plan([r1])
        con = sqlite3.connect(self.db)
        with con:
            con.execute("INSERT INTO runs VALUES('new-run-1','Changed meanwhile','x','{}','in_progress')")
        con.close()
        before = self.db.read_bytes()
        code, res = self.rec("apply", "--db", self.db, "--plan", self.tmp / "plan.json")
        self.assertEqual((code, res["error"]), (2, "PLAN_STALE"))
        self.assertEqual(self.db.read_bytes(), before)

    def test_dump_publications_and_analytics_are_not_planned(self):
        dump = {"tables": {"runs": [{"run_id": "d-run", "topic": "T", "created_at": "x", "brief_json": "{}", "status": "in_progress"}],
                           "publications": [{"run_id": "d-run", "video_id": "v01", "platform": "youtube", "url": "u",
                                             "platform_video_id": "YT", "published_at": "2026-10-17T16:00:00Z"}],
                           "yt_snapshots": [{"snapshot_sha256": "s"}]}}
        (self.tmp / "dump.json").write_text(json.dumps(dump), encoding="utf-8")
        code, res = self.rec("plan", "--db", self.db, "--dump", self.tmp / "dump.json", "--out", self.tmp / "p.json")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["totals"]["insert"], 1)
        self.assertEqual(res["not_planned"], {"publications": 1})
        self.rec("apply", "--db", self.db, "--plan", self.tmp / "p.json")
        con = sqlite3.connect(self.db)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM publications").fetchone()[0], 0)
        con.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
