"""cfdb.py export/import with the YouTube Analytics tables (yt_*) of content-analytics/ingest_analytics.py.

Run:  python skills/content-database/tests/test_cfdb_export_import.py
Temporary databases and dumps only; the real factory.db and memory/dump.json are never touched.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parents[1]
CFDB = SKILLS / "content-database" / "scripts" / "cfdb.py"
INGEST = SKILLS / "content-analytics" / "scripts" / "ingest_analytics.py"
sys.path.insert(0, str(CFDB.parent))
sys.path.insert(0, str(SKILLS / "content-analytics" / "tests"))
import cfdb  # noqa: E402
from test_ingest_analytics import snapshot  # noqa: E402   (the importer's own fixture)

CORE, YT = cfdb.TABLES, cfdb.YT_TABLES


def run(*args):
    p = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, encoding="utf-8")
    return p.returncode, json.loads(p.stdout) if p.stdout.strip() else None, p.stderr


def rows(db: Path, table: str) -> list:
    con = sqlite3.connect(db)
    try:
        return sorted(con.execute(f"SELECT * FROM {table}").fetchall(), key=repr)
    finally:
        con.close()


def tables(db: Path) -> set:
    con = sqlite3.connect(db)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cfdb_dump_"))
        self.src = self.tmp / "src.db"
        con = cfdb.connect(self.src)
        with con:
            con.execute("INSERT INTO runs(run_id, topic, created_at, status) VALUES('run-a','a','2026-10-08T00:00:00Z','done')")
            con.execute("INSERT INTO videos(video_id, run_id, title, final_sha256) VALUES('v01','run-a','A','abc')")
            con.execute("INSERT INTO publications VALUES('run-a','v01','youtube','https://www.youtube.com/shorts/YT_LINKED',"
                        "'YT_LINKED','2026-10-09T16:00:00Z')")
        con.close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def with_analytics(self, db: Path, name="snap.json", **kw) -> None:
        sp = self.tmp / name
        sp.write_text(json.dumps(snapshot(**kw)), encoding="utf-8")
        code, out, err = run(INGEST, "--db", db, "--snapshot", sp, "--apply")
        self.assertEqual(code, 0, err)

    def export(self, db: Path, name="dump.json") -> Path:
        out = self.tmp / name
        code, res, err = run(CFDB, "export", "--db", db, "--out", out)
        self.assertEqual(code, 0, err)
        return out


class ExportImport(Base):
    def test_export_includes_yt_tables_when_present(self):
        self.with_analytics(self.src)
        d = json.loads(self.export(self.src).read_text(encoding="utf-8"))
        self.assertEqual(list(d["tables"]), CORE + YT)
        for t in YT:
            self.assertGreater(len(d["tables"][t]), 0, t)

    def test_export_without_yt_tables_is_unchanged(self):
        d = json.loads(self.export(self.src).read_text(encoding="utf-8"))
        self.assertEqual(list(d["tables"]), CORE)
        self.assertNotIn("yt_snapshots", tables(self.src))                 # export never creates them

    def test_round_trip_preserves_all_tables(self):
        self.with_analytics(self.src)
        dump = self.export(self.src)
        dst = self.tmp / "dst.db"
        code, res, err = run(CFDB, "import", "--db", dst, "--in", dump)
        self.assertEqual(code, 0, err)
        for t in CORE + YT:
            self.assertEqual(rows(dst, t), rows(self.src, t), t)
        self.assertEqual(res["yt_observations"]["inserted"], len(rows(self.src, "yt_observations")))

    def test_yt_schema_is_created_and_matches_the_importer(self):
        self.with_analytics(self.src)
        dump = self.export(self.src)
        dst = self.tmp / "dst.db"
        self.assertEqual(run(CFDB, "import", "--db", dst, "--in", dump)[0], 0)
        norm = lambda d: {r[0]: re.sub(r"\s+", " ", r[1]) for r in sqlite3.connect(d).execute(   # noqa: E731
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name LIKE 'yt_%'")}
        self.assertEqual(norm(dst), norm(self.src))
        txt = INGEST.read_text(encoding="utf-8")
        schema = re.search(r'SCHEMA = """(.*?)"""', txt, re.S).group(1)
        self.assertEqual(re.sub(r"\s+", " ", schema).strip(), re.sub(r"\s+", " ", cfdb.YT_SCHEMA).strip())

    def test_old_dump_still_imports(self):
        old = {"exported_at": "2026-10-09T22:31:31+00:00", "tables": {t: [] for t in CORE}}
        old["tables"]["runs"] = [{"run_id": "run-z", "topic": "z", "created_at": "2026-10-01", "brief_json": None, "status": "done"}]
        p = self.tmp / "old.json"; p.write_text(json.dumps(old), encoding="utf-8")
        dst = self.tmp / "dst.db"
        code, res, err = run(CFDB, "import", "--db", dst, "--in", p)
        self.assertEqual(code, 0, err)
        self.assertEqual(res, {t: len(old["tables"][t]) for t in CORE})       # same output shape as before
        self.assertEqual(rows(dst, "runs"), [("run-z", "z", "2026-10-01", None, "done")])
        self.assertFalse(tables(dst) & set(YT))

    def test_old_dump_keeps_existing_analytics(self):
        self.with_analytics(self.src)
        before = {t: rows(self.src, t) for t in YT}
        old = {"tables": {t: [] for t in CORE}}
        p = self.tmp / "old.json"; p.write_text(json.dumps(old), encoding="utf-8")
        self.assertEqual(run(CFDB, "import", "--db", self.src, "--in", p)[0], 0)
        self.assertEqual({t: rows(self.src, t) for t in YT}, before)

    def test_reimport_is_idempotent_for_yt(self):
        self.with_analytics(self.src)
        dump = self.export(self.src)
        h = {t: rows(self.src, t) for t in YT}
        code, res, err = run(CFDB, "import", "--db", self.src, "--in", dump)
        self.assertEqual(code, 0, err)
        self.assertEqual(res["yt_observations"]["inserted"], 0)
        self.assertEqual(res["yt_observations"]["unchanged"], len(h["yt_observations"]))
        self.assertEqual({t: rows(self.src, t) for t in YT}, h)

    def test_new_snapshot_history_is_added_not_replaced(self):
        self.with_analytics(self.src)
        other = self.tmp / "other.db"; cfdb.connect(other).close()
        self.with_analytics(other, name="b.json", pulled="2026-10-18T09:00:00+00:00", until="2026-10-18")
        self.assertEqual(run(CFDB, "import", "--db", self.src, "--in", self.export(other, "b.json.dump"))[0], 0)
        self.assertEqual(len(rows(self.src, "yt_snapshots")), 2)


class FailsSafely(Base):
    def check_untouched(self, db, dump, before_sha, code="IMPORT_FAILED"):
        c, res, err = run(CFDB, "import", "--db", db, "--in", dump)
        self.assertEqual(c, 2, err)
        self.assertEqual(res["error"], code)
        self.assertEqual(sha(db), before_sha)

    def test_malformed_yt_rows_write_nothing(self):
        self.with_analytics(self.src)
        d = json.loads(self.export(self.src).read_text(encoding="utf-8"))
        d["tables"]["runs"].append({"run_id": "run-new", "topic": "n", "created_at": "x", "brief_json": None, "status": "done"})
        d["tables"]["yt_observations"].append({"snapshot_sha256": "s", "platform_video_id": "v"})   # NOT NULL columns missing
        p = self.tmp / "bad.json"; p.write_text(json.dumps(d), encoding="utf-8")
        dst = self.tmp / "dst.db"; cfdb.connect(dst).close()
        self.check_untouched(dst, p, sha(dst))
        self.assertFalse(tables(dst) & set(YT))                                # no empty yt_* tables left behind
        self.assertEqual(rows(dst, "runs"), [])                               # no partial core rows either

    def test_conflicting_yt_row_aborts_without_overwriting(self):
        self.with_analytics(self.src)
        d = json.loads(self.export(self.src).read_text(encoding="utf-8"))
        d["tables"]["yt_observations"][0]["value"] = 999999.0
        d["tables"]["yt_observations"] = [d["tables"]["yt_observations"][0]]
        p = self.tmp / "conflict.json"; p.write_text(json.dumps(d), encoding="utf-8")
        self.check_untouched(self.src, p, sha(self.src))

    def test_unknown_table_or_bad_shape_is_refused(self):
        for doc in ({"tables": {"evil": []}}, {"tables": []}, {"nope": 1}, {"tables": {"runs": {}}}):
            with self.subTest(doc=doc):
                p = self.tmp / "u.json"; p.write_text(json.dumps(doc), encoding="utf-8")
                self.check_untouched(self.src, p, sha(self.src), code="DUMP_INVALID")


if __name__ == "__main__":
    unittest.main(verbosity=2)
