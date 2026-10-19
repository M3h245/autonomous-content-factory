"""Tests for ingest_analytics.py (official yt_sync snapshot -> per-video observations).

Run:  python skills/content-analytics/tests/test_ingest_analytics.py
Everything runs in a temporary folder with a fresh database; no real database or snapshot is touched.
"""
from __future__ import annotations

import copy
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
sys.path.insert(0, str(HERE.parents[1] / "content-database" / "scripts"))
import cfdb  # noqa: E402

SCRIPT = SCRIPTS / "ingest_analytics.py"
LINKED, UNRES, PRIV, LATE, ERR = "YT_LINKED", "YT_UNRES", "YT_PRIV", "YT_LATE", "YT_ERR"


def video(vid, published, privacy="public", **m):
    return {"video_id": vid, "title": "T " + vid, "published_at": published, "duration": "PT30S", "privacy": privacy,
            "public_views": m.pop("public_views", 10), "public_likes": 1, "public_comments": 0, **m}


def snapshot(pulled="2026-10-16T22:27:12+00:00", until="2026-10-17"):
    days = [{"day": f"2026-10-{d:02d}", "views": 0, "engagedViews": 0, "subscribersGained": 0, "subscribersLost": 0}
            for d in range(1, 15)]                       # cutoff 2026-10-14
    return {"pulled_at": pulled, "since": "2026-10-01", "until": until, "channel": {"id": "UC_TEST"},
            "videos": [video(LINKED, "2026-10-09T16:00:00Z", views=951, engagedViews=302, averageViewPercentage=45.96,
                             likes=15, comments=0, shares=0, averageViewDuration=17),
                       video(UNRES, "2026-10-12T16:00:00Z", views=100, engagedViews=0, likes=0),   # real zeros
                       video(PRIV, "2026-10-16T14:18:00Z", privacy="private", public_views=0),
                       video(LATE, "2026-10-15T16:00:00Z"),
                       video(ERR, "2026-10-10T16:00:00Z", views=5)],
            "channel_daily": days, "channel_traffic": [],
            "per_video": {
                LINKED: {"daily": [{"day": "2026-10-09", "views": 400, "engagedViews": 100, "likes": 3, "subscribersGained": 0},
                                   {"day": "2026-10-10", "views": 0, "engagedViews": 0, "likes": 0, "subscribersGained": 0}],
                         "retention": [{"elapsedVideoTimeRatio": 0.01, "audienceWatchRatio": 1.24, "relativeRetentionPerformance": 0.53}],
                         "traffic": [{"insightTrafficSourceType": "SHORTS", "views": 900, "engagedViews": 290}]},
                UNRES: {"daily": [{"day": "2026-10-12", "views": 100, "engagedViews": 0, "likes": 0, "subscribersGained": 0}],
                        "retention": [], "traffic": []},
                LATE: {"daily": [], "retention": [], "traffic": []},
                ERR: {"daily": [{"day": "2026-10-10", "views": 5, "engagedViews": 1, "likes": 0, "subscribersGained": 0}],
                      "retention": [], "traffic": []}},
            "capabilities": {"file_details": {"requested": True, "error": None}},
            "errors": [f"{ERR} retention: HTTP 403 reports: forbidden"], "api_calls": 9}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ingest_an_"))
        self.db = self.tmp / "factory.db"
        con = cfdb.connect(self.db)
        with con:
            con.execute("INSERT INTO runs(run_id, topic, created_at, status) VALUES('run-a','a','2026-10-08T00:00:00Z','done')")
            con.execute("INSERT INTO videos(video_id, run_id, title, final_sha256) VALUES('v01','run-a','A','abc')")
            con.execute("INSERT INTO publications VALUES('run-a','v01','youtube','https://www.youtube.com/shorts/YT_LINKED',"
                        "'YT_LINKED','2026-10-09T16:00:00Z')")
            con.execute("INSERT INTO metrics VALUES('run-a','v01','youtube','2026-10-01T00:00:00Z',1,0.5,0.1,0.4,'{}')")
            con.execute("INSERT INTO weights VALUES('format:x', 1.1, 3, '2026-10-01')")
        con.close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, doc):
        p = self.tmp / name
        p.write_text(json.dumps(doc), encoding="utf-8")
        return p

    def run_ingest(self, snap, apply=False, name="snapshot.json", expect=0):
        sp = snap if isinstance(snap, Path) else self.write(name, snap)
        cmd = [sys.executable, str(SCRIPT), "--db", str(self.db), "--snapshot", str(sp), "--out", str(self.tmp / "rep.json")]
        p = subprocess.run(cmd + (["--apply"] if apply else []), capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(p.returncode, expect, p.stdout + p.stderr)
        out = json.loads(p.stdout)
        rep = json.loads((self.tmp / "rep.json").read_text(encoding="utf-8")) if expect == 0 else None
        return out, rep, p

    def q(self, sql, *args):
        con = sqlite3.connect(self.db)
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    def protected(self):
        return [self.q(f"SELECT * FROM {t} ORDER BY 1,2,3") for t in ("publications", "metrics", "weights", "runs", "videos")]

    def sha(self):
        return hashlib.sha256(self.db.read_bytes()).hexdigest()


class Collection(Base):
    def test_every_video_is_considered_not_only_linked_ones(self):
        _, rep, _ = self.run_ingest(snapshot())
        self.assertEqual({v["platform_video_id"] for v in rep["videos"]}, {LINKED, UNRES, PRIV, LATE, ERR})
        self.assertEqual((rep["totals"]["videos"], rep["totals"]["linked"], rep["totals"]["unresolved"]), (5, 1, 4))

    def test_linked_video_keeps_its_verified_association(self):
        self.run_ingest(snapshot(), apply=True)
        self.assertEqual(self.q("SELECT run_id, video_id, learning_eligible FROM yt_videos WHERE platform_video_id=?", LINKED),
                         [("run-a", "v01", 1)])

    def test_unresolved_videos_have_no_fabricated_link(self):
        self.run_ingest(snapshot(), apply=True)
        rows = self.q("SELECT platform_video_id, run_id, video_id, learning_eligible, link_evidence FROM yt_videos "
                      "WHERE platform_video_id != ?", LINKED)
        self.assertEqual(len(rows), 4)
        for vid, run, video_id, elig, ev in rows:
            self.assertIsNone(run); self.assertIsNone(video_id); self.assertEqual(elig, 0)
            self.assertIn("unresolved", ev)
        self.assertGreater(self.q("SELECT count(*) FROM yt_observations WHERE platform_video_id=? AND status='ok'", UNRES)[0][0], 0)

    def test_missing_is_never_zero_and_real_zero_stays_zero(self):
        self.run_ingest(snapshot(), apply=True)
        v = dict(self.q("SELECT metric, value FROM yt_observations WHERE platform_video_id=? AND report='video_totals' "
                        "AND status='ok'", UNRES))
        self.assertEqual(v["engagedViews"], 0.0)                          # API said 0
        rows = self.q("SELECT metric, value, status FROM yt_observations WHERE platform_video_id=? AND report='video_totals' "
                      "AND metric='averageViewPercentage'", UNRES)
        self.assertEqual(rows, [("averageViewPercentage", None, "missing")])
        self.assertEqual(self.q("SELECT count(*) FROM yt_observations WHERE status != 'ok' AND value IS NOT NULL")[0][0], 0)
        self.assertEqual(set(r[0] for r in self.q("SELECT status FROM yt_observations WHERE platform_video_id=? "
                                                  "AND report='video_totals'", PRIV)), {"not_yet_processed"})
        self.assertEqual(set(r[0] for r in self.q("SELECT status FROM yt_observations WHERE platform_video_id=? "
                                                  "AND report LIKE 'video\\_%' ESCAPE '\\' AND report != 'video_totals'", PRIV)),
                         {"not_requested"})
        self.assertEqual(set(r[0] for r in self.q("SELECT status FROM yt_observations WHERE platform_video_id=? "
                                                  "AND report='video_retention'", UNRES)), {"unavailable"})

    def test_days_before_publication_are_not_results(self):
        snap = snapshot()
        snap["per_video"][LINKED]["daily"].insert(0, {"day": "2026-10-08", "views": 0, "engagedViews": 0, "likes": 0,
                                                      "subscribersGained": 0})
        self.run_ingest(snap, apply=True)
        rows = self.q("SELECT dimension_value, value, status FROM yt_observations WHERE platform_video_id=? "
                      "AND report='video_daily' AND metric='views' ORDER BY dimension_value", LINKED)
        self.assertEqual(rows, [("2026-10-08", None, "not_applicable"), ("2026-10-09", 400.0, "ok"), ("2026-10-10", 0.0, "ok")])

    def test_lifetime_and_windowed_metrics_cannot_be_confused(self):
        self.run_ingest(snapshot(), apply=True)
        life = self.q("SELECT DISTINCT report, window_kind, window_start FROM yt_observations WHERE metric LIKE 'public_%'")
        self.assertEqual(life, [("data_api_statistics", "lifetime_at_pull", "")])
        win = self.q("SELECT DISTINCT window_kind, window_start, window_end FROM yt_observations WHERE report='video_totals'")
        self.assertEqual(win, [("date_range", "2026-10-01", "2026-10-17")])
        self.assertEqual(self.q("SELECT count(*) FROM yt_observations WHERE metric='views' AND report='data_api_statistics'")[0][0], 0)
        self.assertEqual(self.q("SELECT analytics_cutoff_day, requested_start, requested_end FROM yt_snapshots"),
                         [("2026-10-14", "2026-10-01", "2026-10-17")])
        self.assertEqual(self.q("SELECT DISTINCT window_kind FROM yt_observations WHERE report='video_daily' AND status='ok'"),
                         [("day",)])

    def test_reimport_is_idempotent(self):
        snap = snapshot()
        self.run_ingest(snap, apply=True)
        n, h = self.q("SELECT count(*) FROM yt_observations")[0][0], self.sha()
        out, rep, _ = self.run_ingest(snap, apply=True)
        self.assertEqual(rep["totals"]["action"], "unchanged (snapshot already imported)")
        self.assertIsNone(out["backup"]); self.assertEqual(self.sha(), h)
        self.assertEqual(self.q("SELECT count(*) FROM yt_observations")[0][0], n)

    def test_different_windows_are_separate_history(self):
        a = snapshot()
        b = snapshot(pulled="2026-10-18T09:00:00+00:00", until="2026-10-18")
        b["videos"][0]["views"] = 1200
        self.run_ingest(a, apply=True, name="a.json")
        self.run_ingest(b, apply=True, name="b.json")
        rows = self.q("SELECT window_end, value FROM yt_observations WHERE platform_video_id=? AND report='video_totals' "
                      "AND metric='views' ORDER BY window_end", LINKED)
        self.assertEqual(rows, [("2026-10-17", 951.0), ("2026-10-18", 1200.0)])
        self.assertEqual(self.q("SELECT count(*) FROM yt_snapshots")[0][0], 2)

    def test_publications_metrics_weights_never_touched(self):
        before = self.protected()
        self.run_ingest(snapshot(), apply=True)
        self.assertEqual(self.protected(), before)
        src = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("import ingest_youtube", src)
        for t in ("publications", "metrics", "weights"):
            self.assertNotRegex(src, rf"(?i)(INSERT|UPDATE|DELETE|REPLACE)[^\n]*\b{t}\b")

    def test_dry_run_writes_nothing(self):
        h = self.sha()
        out, rep, _ = self.run_ingest(snapshot())
        self.assertEqual((out["mode"], rep["totals"]["action"]), ("dry-run", "insert"))
        self.assertEqual(self.sha(), h)
        self.assertEqual(self.q("SELECT name FROM sqlite_master WHERE name LIKE 'yt_%'"), [])
        self.assertEqual(list(self.tmp.glob("factory.db.bak-*")), [])

    def test_api_errors_are_recorded_not_fabricated(self):
        _, rep, _ = self.run_ingest(snapshot(), apply=True)
        rows = self.q("SELECT metric, value, status, reason FROM yt_observations WHERE platform_video_id=? "
                      "AND report='video_retention'", ERR)
        self.assertEqual({r[2] for r in rows}, {"error"}); self.assertTrue(all(r[1] is None for r in rows))
        self.assertIn("HTTP 403", rows[0][3])
        self.assertEqual(rep["api_errors_in_snapshot"], [f"{ERR} retention: HTTP 403 reports: forbidden"])


class LegacyChannel(Base):
    """The four legacy channel ids: channel-wide data only, labelled legacy_channel, never linked or learned from."""
    LEG = "aRJAjjHVx9g"

    def snap(self):
        s = snapshot()
        s["videos"].append(video(self.LEG, "2023-09-05T14:50:49Z", views=3))
        return s

    def test_legacy_video_is_labelled_and_never_linked(self):
        _, rep, _ = self.run_ingest(self.snap(), apply=True)
        v = next(x for x in rep["videos"] if x["platform_video_id"] == self.LEG)
        self.assertEqual((v["scope"], v["run_id"], v["video_id"], v["learning_eligible"]), ("legacy_channel", None, None, 0))
        self.assertIn("never linked", v["scope_reason"])
        t = rep["totals"]
        self.assertEqual((t["videos"], t["linked"], t["unresolved"], t["legacy_channel"]), (6, 1, 4, 1))
        self.assertEqual(self.q("SELECT run_id, video_id, learning_eligible FROM yt_videos WHERE platform_video_id=?", self.LEG),
                         [(None, None, 0)])
        self.assertEqual({x["scope"] for x in rep["videos"] if x["platform_video_id"] != self.LEG}, {"factory", "unlinked"})

    def test_publication_row_for_a_legacy_video_is_refused(self):
        con = sqlite3.connect(self.db)
        with con:
            con.execute("INSERT INTO publications VALUES('run-a','v02','youtube','u',?,'2023-09-05T14:50:49Z')", (self.LEG,))
        con.close()
        h = self.sha()
        out, _, _ = self.run_ingest(self.snap(), apply=True, expect=2)
        self.assertEqual((out["error"], out["ids"]), ("LEGACY_LINKED_IN_DB", [self.LEG]))
        self.assertEqual(self.sha(), h)
        self.assertEqual(list(self.tmp.glob("factory.db.bak-*")), [])


class AtomicApply(Base):
    def test_failed_apply_leaves_no_tables_and_no_rows(self):
        snap = snapshot()
        snap["per_video"][LINKED]["traffic"].append(dict(snap["per_video"][LINKED]["traffic"][0]))  # duplicate key
        before = self.protected()
        out, _, _ = self.run_ingest(snap, apply=True, expect=2)
        self.assertEqual((out["error"], out["written"]), ("APPLY_FAILED", 0))
        self.assertTrue(Path(out["backup"]).is_file())                      # the pre-write backup exists
        self.assertEqual(self.q("SELECT name FROM sqlite_master WHERE name LIKE 'yt_%'"), [])   # no empty tables
        self.assertEqual(self.protected(), before)


class Refusals(Base):
    def test_vidiq_export_is_refused(self):
        vidiq = {"source": "YouTube Analytics API via vidIQ vidiq_channel_analytics (dimensions=video)",
                 "captured_at": "2026-10-16T11:02:00+00:00", "startDate": "2026-10-09", "endDate": "2026-10-16",
                 "columns": ["video", "views"], "rows": [["YT_LINKED", 1121]]}
        h = self.sha()
        out, _, _ = self.run_ingest(vidiq, apply=True, expect=2)
        self.assertEqual(out["error"], "NOT_A_YT_SYNC_SNAPSHOT")
        self.assertEqual(self.sha(), h); self.assertEqual(list(self.tmp.glob("factory.db.bak-*")), [])
        disguised = snapshot(); disguised["source"] = vidiq["source"]       # yt_sync-shaped, but labelled vidIQ
        out, _, _ = self.run_ingest(disguised, apply=True, name="disguised.json", expect=2)
        self.assertEqual(out["error"], "NOT_A_YT_SYNC_SNAPSHOT")
        self.assertEqual(self.sha(), h)

    def test_secrets_are_refused_and_never_echoed(self):
        token = "ya29.a0SECRETSECRETSECRET123"
        snap = snapshot(); snap["errors"] = [f"{ERR} daily: bad header Authorization: Bearer {token}"]
        h = self.sha()
        out, _, p = self.run_ingest(snap, apply=True, expect=2)
        self.assertEqual(out["error"], "SECRET_IN_INPUT")
        self.assertNotIn(token, p.stdout + p.stderr)
        self.assertEqual(self.sha(), h)
        snap2 = snapshot(); snap2["note"] = json.dumps({"refresh_token": "1//0abcdefSECRET"})
        out, _, p = self.run_ingest(snap2, apply=True, expect=2)
        self.assertNotIn("1//0abcdefSECRET", p.stdout + p.stderr)

    def test_reports_never_contain_token_text(self):
        _, rep, p = self.run_ingest(snapshot(), apply=True)
        blob = json.dumps(rep) + p.stdout + p.stderr
        for pat in ("ya29.", "refresh_token", "client_secret", "access_token"):
            self.assertNotIn(pat, blob)

    def test_bad_inputs_fail_safely(self):
        h = self.sha()
        bad = self.tmp / "bad.json"; bad.write_text("{nope", encoding="utf-8")
        dup = snapshot(); dup["videos"].append(copy.deepcopy(dup["videos"][0]))
        cases = [(bad, "INPUT_INVALID"), (self.tmp / "missing.json", "INPUT_NOT_FOUND"),
                 (self.write("x.json", {"videos": []}), "NOT_A_YT_SYNC_SNAPSHOT"),
                 (self.write("dup.json", dup), "NOT_A_YT_SYNC_SNAPSHOT")]
        for path, code in cases:
            with self.subTest(code=code):
                out, _, _ = self.run_ingest(path, apply=True, expect=2)
                self.assertEqual(out["error"], code)
        self.assertEqual(self.sha(), h)
        p = subprocess.run([sys.executable, str(SCRIPT), "--db", str(self.tmp / "none.db"), "--snapshot",
                            str(self.write("s.json", snapshot()))], capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)["error"]), (2, "DB_NOT_FOUND"))

    def test_youtube_id_on_two_runs_is_not_linked(self):
        con = sqlite3.connect(self.db)
        with con:
            con.execute("INSERT INTO publications VALUES('run-b','v01','youtube','u','YT_UNRES','2026-10-12T00:00:00Z')")
            con.execute("INSERT INTO publications VALUES('run-c','v01','youtube','u','YT_UNRES','2026-10-12T00:00:00Z')")
        con.close()
        _, rep, _ = self.run_ingest(snapshot())
        self.assertEqual(rep["ambiguous_publications_not_linked"], [UNRES])
        v = next(x for x in rep["videos"] if x["platform_video_id"] == UNRES)
        self.assertEqual((v["run_id"], v["learning_eligible"]), (None, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
