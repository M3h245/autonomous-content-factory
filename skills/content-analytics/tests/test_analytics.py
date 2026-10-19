"""Tests for analytics.py analyze: attribution only through publication ids, legacy channel videos kept apart.

Run:  python skills/content-analytics/tests/test_analytics.py
Everything happens in a temporary folder with a fresh database; no real database or export is touched.
"""
from __future__ import annotations

import csv
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
SCRIPT = HERE.parent / "scripts" / "analytics.py"
sys.path.insert(0, str(HERE.parents[1] / "content-database" / "scripts"))
import cfdb  # noqa: E402

COLS = ["Content", "Video title", "Views", "Average percentage viewed (%)", "Likes", "Comments added", "Shares"]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="analytics_"))
        self.db = self.tmp / "factory.db"
        con = cfdb.connect(self.db)
        with con:
            for i, (run, title, fmt) in enumerate((("run-a", "Why is the ocean blue?", "myth"),
                                                    ("run-b", "Why is glass transparent?", "explainer"),
                                                    ("run-c", "Why do cats purr?", "explainer"))):
                con.execute("INSERT INTO runs(run_id, topic, created_at, status) VALUES(?,?,?,?)",
                            (run, title, f"2026-10-0{i + 1}T00:00:00Z", "done"))
                con.execute("INSERT INTO videos(video_id, run_id, title, format, duration_s) VALUES(?,?,?,?,?)",
                            ("v01", run, title, fmt, 30.0))
            for run, yid in (("run-a", "YT_A"), ("run-b", "YT_B")):        # run-c is not published
                con.execute("INSERT INTO publications VALUES(?,?,?,?,?,?)",
                            (run, "v01", "youtube", f"https://www.youtube.com/shorts/{yid}", yid, "2026-10-09T16:00:00Z"))
        con.close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def csv(self, rows, cols=COLS):
        p = self.tmp / "export.csv"
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(cols); w.writerows(rows)
        return p

    def analyze(self, rows, cols=COLS):
        out = self.tmp / "out"
        p = subprocess.run([sys.executable, "-B", str(SCRIPT), "analyze", "--csv", str(self.csv(rows, cols)),
                            "--platform", "youtube", "--db", str(self.db), "--out-dir", str(out),
                            "--result", str(out / "result.json")], capture_output=True, text=True, encoding="utf-8")
        res = json.loads((out / "result.json").read_text(encoding="utf-8"))
        fb = out / "feedback.json"
        return p.returncode, res, json.loads(fb.read_text(encoding="utf-8")) if fb.is_file() else None

    def sha(self):
        return hashlib.sha256(self.db.read_bytes()).hexdigest()


ROWS = [["YT_A", "Why is the ocean blue?", 1400, 60, 10, 1, 0],
        ["YT_B", "Why is glass transparent?", 1300, 55, 9, 0, 1],
        ["YT_X", "Why do cats purr?", 900, 70, 5, 0, 0],                # exact factory title, but no publication
        ["KHutHAMv2_A", "How to make pancake at home?", 23, 30, 0, 0, 0],
        ["QqI7w_BZaWE", "How to make a lot of money online?", 3, 20, 0, 0, 0]]


class Attribution(Base):
    def test_only_publication_ids_attribute_rows(self):
        _, res, fb = self.analyze(ROWS)
        self.assertEqual(sorted(v["run_id"] for v in fb["videos"]), ["run-a", "run-b"])     # never run-c by title
        self.assertEqual(fb["matched"], 2)

    def test_title_only_export_matches_nothing(self):
        rows = [r[1:] for r in ROWS]
        _, res, fb = self.analyze(rows, cols=COLS[1:])
        self.assertEqual(fb["matched"], 0)
        codes = {e["code"] for e in res["errors"]}
        self.assertIn("ANA.ID_COLUMN", codes); self.assertIn("ANA.MATCH_RATE", codes)

    def test_legacy_rows_are_channel_only(self):
        _, res, fb = self.analyze(ROWS)
        ch = fb["channel"]
        self.assertEqual((ch["rows"], ch["views"]), (5, 1400 + 1300 + 900 + 23 + 3))
        self.assertEqual(ch["by_scope"]["legacy_channel"], {"rows": 2, "views": 26})
        self.assertEqual(ch["by_scope"]["factory"], {"rows": 2, "views": 2700})
        self.assertEqual(ch["by_scope"]["unattributed"], {"rows": 1, "views": 900})
        self.assertEqual({x["platform_video_id"] for x in fb["legacy_channel"]}, {"KHutHAMv2_A", "QqI7w_BZaWE"})
        self.assertTrue(all("never linked" in x["reason"] for x in fb["legacy_channel"]))
        self.assertFalse({x["run_id"] for x in fb["videos"]} - {"run-a", "run-b"})
        rate = next(c for c in res["gate"]["checks"] if c["id"] == "ANA.MATCH_RATE")
        self.assertEqual(rate["value"], round(2 / 3, 2))                                 # legacy rows not in the denominator
        self.assertIn("2 legacy rows excluded", rate["message"])

    def test_factory_kpis_and_weights_ignore_legacy_rows(self):
        _, _, with_legacy = self.analyze(ROWS)
        _, _, without = self.analyze([r for r in ROWS if not r[0].startswith(("KHut", "QqI7"))])
        for k in ("global_perf", "videos", "feature_effects", "weights", "matched"):
            self.assertEqual(with_legacy[k], without[k], k)

    def test_legacy_publication_is_blocking(self):
        con = sqlite3.connect(self.db)
        with con:
            con.execute("INSERT INTO publications VALUES('run-c','v01','youtube','u','KHutHAMv2_A','2023-08-21T11:23:35Z')")
        con.close()
        h = self.sha()
        code, res, fb = self.analyze(ROWS)
        self.assertEqual(code, 2)
        self.assertEqual(res["errors"][0]["code"], "ANA.LEGACY_LINKED")
        self.assertIsNone(fb)
        self.assertEqual(self.sha(), h)


if __name__ == "__main__":
    unittest.main(verbosity=2)
