"""Tests for `cfdb.py publish`: explicit run, real public time, insert-only, legacy channel videos refused.

Run:  python skills/content-database/tests/test_cfdb_publish.py
Everything happens in a temporary folder with a fresh database; no real database is touched.
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
CFDB = SCRIPTS / "cfdb.py"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE.parents[1] / "content-analytics" / "scripts"))
import cfdb  # noqa: E402
import legacy_channel  # noqa: E402

OK = ["--run-id", "run-old", "--video", "v01", "--platform", "youtube", "--url", "https://www.youtube.com/shorts/YT_1",
      "--platform-id", "YT_1", "--published-at", "2026-10-14T16:00:14Z"]


class Publish(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cfdb_pub_"))
        self.db = self.tmp / "factory.db"
        con = cfdb.connect(self.db)
        with con:   # two runs share video_id v01; the newer one must never be picked implicitly
            con.execute("INSERT INTO videos(video_id, run_id, title, created_at) VALUES('v01','run-old','Old','2026-10-14T00:00:00Z')")
            con.execute("INSERT INTO videos(video_id, run_id, title, created_at) VALUES('v01','run-new','New','2026-10-16T00:00:00Z')")
        con.close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def pub(self, args):
        p = subprocess.run([sys.executable, "-B", str(CFDB), "publish", "--db", str(self.db), *args],
                           capture_output=True, text=True, encoding="utf-8")
        return p.returncode, json.loads(p.stdout)

    def rows(self):
        con = sqlite3.connect(self.db)
        try:
            return con.execute("SELECT * FROM publications ORDER BY 1").fetchall()
        finally:
            con.close()

    def sha(self):
        return hashlib.sha256(self.db.read_bytes()).hexdigest()

    def args(self, **kw):
        a = list(OK)
        for k, v in kw.items():
            flag = "--" + k.replace("_", "-")
            i = a.index(flag)
            if v is None:
                del a[i:i + 2]
            else:
                a[i + 1] = v
        return a

    def test_insert_uses_the_named_run_and_the_given_time(self):
        code, out = self.pub(OK)
        self.assertEqual((code, out["action"]), (0, "insert"))
        self.assertEqual(self.rows(), [("run-old", "v01", "youtube", "https://www.youtube.com/shorts/YT_1", "YT_1",
                                        "2026-10-14T16:00:14Z")])

    def test_every_argument_is_required(self):
        for k in ("run_id", "published_at", "platform_id", "url"):
            code, out = self.pub(self.args(**{k: None}))
            self.assertEqual((code, out["error"]), (2, "PUBLISH_ARGS_REQUIRED"), k)
            self.assertIn("--" + k.replace("_", "-"), out["missing"])
        self.assertEqual(self.rows(), [])

    def test_bad_times_are_refused(self):
        for t in ("now", "2026-10-14", "2026-10-14T16:00:14", "2026-10-14 16:00:14Z", "2026-13-40T16:00:14Z"):
            code, out = self.pub(self.args(published_at=t))
            self.assertEqual((code, out["error"]), (2, "PUBLISHED_AT_INVALID"), t)
        self.assertEqual(self.rows(), [])

    def test_unknown_run_or_video_is_refused(self):
        code, out = self.pub(self.args(run_id="run-missing"))
        self.assertEqual((code, out["error"]), (2, "UNKNOWN_VIDEO"))
        self.assertEqual(self.rows(), [])

    def test_rerun_is_unchanged(self):
        self.pub(OK)
        h = self.sha()
        code, out = self.pub(OK)
        self.assertEqual((code, out["action"]), (0, "unchanged"))
        self.assertEqual(self.sha(), h)

    def test_different_values_are_a_conflict_never_an_overwrite(self):
        self.pub(OK)
        before, h = self.rows(), self.sha()
        code, out = self.pub(self.args(published_at="2026-10-17T09:00:00Z"))
        self.assertEqual((code, out["error"]), (3, "CONFLICT"))
        self.assertEqual(out["diff"]["published_at"], {"db": "2026-10-14T16:00:14Z", "new": "2026-10-17T09:00:00Z"})
        self.assertEqual((self.rows(), self.sha()), (before, h))

    def test_platform_id_on_another_video_is_a_conflict(self):
        self.pub(OK)
        code, out = self.pub(self.args(run_id="run-new"))
        self.assertEqual((code, out["error"], out["db_already_maps_to"]), (3, "CONFLICT", ["run-old", "v01"]))
        self.assertEqual(len(self.rows()), 1)

    def test_legacy_channel_videos_are_refused(self):
        for vid in sorted(cfdb.LEGACY_CHANNEL_VIDEOS):
            code, out = self.pub(self.args(platform_id=vid))
            self.assertEqual((code, out["error"]), (2, "LEGACY_CHANNEL_VIDEO"), vid)
        self.assertEqual(self.rows(), [])

    def test_legacy_list_matches_content_analytics(self):
        self.assertEqual(cfdb.LEGACY_CHANNEL_VIDEOS, legacy_channel.LEGACY_CHANNEL_VIDEOS)
        self.assertEqual(len(cfdb.LEGACY_CHANNEL_VIDEOS), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
