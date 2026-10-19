"""Tests for learning.py / learning_apply.py (v3.1.0): attributes, age-matched KPIs, missing data, idempotent snapshot
imports, API failures, legacy guard, comparisons, bounded directives and the guardrail.

Run:  python skills/content-analytics/tests/test_learning.py
Everything runs in a temporary folder with synthetic snapshots and a fresh database; no real data is touched.
"""
from __future__ import annotations

import datetime as dt
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
sys.path.insert(0, str(HERE.parents[1] / "content-database" / "scripts"))
import cfdb  # noqa: E402
import learning as LN  # noqa: E402
import learning_apply as LA  # noqa: E402

PY = sys.executable
LEARN = SCRIPTS / "learning.py"
INGEST = SCRIPTS / "ingest_analytics.py"
DAY0 = dt.date(2026, 10, 1)


def day(i: int) -> str:
    return (DAY0 + dt.timedelta(days=i)).isoformat()


def snapshot(videos: list[dict], cutoff: int, pulled: str, errors=()) -> dict:
    """videos: {id, pub (day index), daily: {day_index: (views, engaged)}, totals: dict|None, privacy}"""
    out = {"pulled_at": pulled, "since": day(0), "until": day(cutoff + 2), "channel": {"id": "UCx"}, "note": "test",
           "videos": [], "per_video": {}, "channel_traffic": [], "errors": list(errors), "capabilities": {}, "api_calls": 1,
           "channel_daily": [{"day": day(i), "views": 0, "engagedViews": 0, "subscribersGained": 0, "subscribersLost": 0}
                             for i in range(cutoff + 1)]}
    for v in videos:
        t = v.get("totals")
        out["videos"].append({"video_id": v["id"], "title": v["id"], "published_at": f"{day(v['pub'])}T18:00:00Z",
                              "duration": "PT25S", "privacy": v.get("privacy", "public"), "publish_at": None,
                              "public_views": 100, "public_likes": 1, "public_comments": 0,
                              **{k: (t or {}).get(k) for k in LN_TOTALS}})
        daily = [{"day": day(i), "views": v["daily"].get(i, (0, 0))[0], "engagedViews": v["daily"].get(i, (0, 0))[1],
                  "likes": 0, "subscribersGained": 0} for i in range(cutoff + 1)]
        out["per_video"][v["id"]] = {"daily": daily, "traffic": [],
                                     "retention": [{"elapsedVideoTimeRatio": round(x / 100, 2), "audienceWatchRatio": 1 - x / 200,
                                                    "relativeRetentionPerformance": 0.5} for x in range(1, 101)] if t else []}
    return out


LN_TOTALS = ("views", "engagedViews", "estimatedMinutesWatched", "averageViewDuration", "averageViewPercentage", "likes",
             "comments", "shares", "subscribersGained", "subscribersLost")


def totals(views, eng, pct) -> dict:
    return {"views": views, "engagedViews": eng, "estimatedMinutesWatched": 1, "averageViewDuration": 15,
            "averageViewPercentage": pct, "likes": 1, "comments": 0, "shares": 0, "subscribersGained": 0, "subscribersLost": 0}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="learn_"))
        self.db = self.tmp / "factory.db"
        cfdb.connect(self.db).close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def link(self, pid: str, run: str, pub_day: int):
        con = sqlite3.connect(self.db)
        with con:
            con.execute("INSERT INTO runs(run_id, topic, status) VALUES(?,?,?)", (run, run, "in_progress"))
            con.execute("INSERT INTO publications VALUES(?,?,?,?,?,?)",
                        (run, "v01", "youtube", f"https://youtube.com/shorts/{pid}", pid, f"{day(pub_day)}T18:00:00Z"))
        con.close()

    def ingest(self, snap: dict, name: str) -> dict:
        p = self.tmp / name
        p.write_text(json.dumps(snap), encoding="utf-8")
        r = subprocess.run([PY, str(INGEST), "--db", str(self.db), "--snapshot", str(p), "--apply"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def run_learn(self, *args) -> tuple[int, dict]:
        r = subprocess.run([PY, str(LEARN), *map(str, args)], capture_output=True, text=True)
        return r.returncode, json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {"stderr": r.stderr}

    def kpis(self) -> dict:
        code, res = self.run_learn("kpis", "--db", self.db, "--out", self.tmp / "kpis.json")
        self.assertEqual(code, 0, res)
        return {v["platform_video_id"]: v for v in json.loads((self.tmp / "kpis.json").read_text(encoding="utf-8"))["videos"]}


def four_videos():
    return [{"id": "A", "pub": 1, "daily": {i: (100, 40) for i in range(1, 12)}, "totals": totals(1100, 440, 60)},   # 10 days
            {"id": "B", "pub": 9, "daily": {9: (50, 10), 10: (30, 15), 11: (20, 5), 12: (10, 2)}, "totals": totals(110, 32, 55)},
            {"id": "C", "pub": 10, "daily": {10: (80, 20)}, "totals": totals(80, 20, 70)},                     # early
            {"id": "D", "pub": 12, "daily": {}, "totals": None}]                                             # after cutoff


class KPIs(Base):
    def setUp(self):
        super().setUp()
        for pid, d in (("A", 1), ("B", 9), ("C", 10), ("D", 12)):
            self.link(pid, f"run-{pid}", d)

    def test_maturity_age_matched_values_and_nulls_not_zeros(self):
        self.ingest(snapshot(four_videos() + [{"id": "KHutHAMv2_A", "pub": 0, "daily": {}, "totals": totals(5, 1, 30)}],
                             cutoff=10, pulled="2026-10-12T00:00:00+00:00"), "s1.json")
        k = self.kpis()
        self.assertEqual({p: k[p]["maturity"] for p in "ABCD"}, {"A": "d7", "B": "early", "C": "early", "D": "none"})
        self.assertEqual((k["A"]["views_d3"], k["A"]["engaged_views_d3"], k["A"]["engaged_share_d3"]), (300, 120, 0.4))
        self.assertEqual(k["A"]["views_d7"], 700)
        self.assertIsNone(k["B"]["views_d3"]); self.assertEqual(k["B"]["status_d3"], "immature")
        for f in ("views_d1", "engaged_share_d1", "avg_view_pct", "retention_3s", "views_total"):
            self.assertIsNone(k["D"][f], f)                       # published after the cutoff: NULL, never 0
        self.assertNotIn("KHutHAMv2_A", k)                        # legacy video: never in factory KPIs
        self.assertEqual(k["A"]["avg_view_pct"], 60.0)
        self.assertAlmostEqual(k["A"]["retention_3s"], 1 - 12 / 200, places=3)   # 3 s of 25 s = ratio 0.12

    def test_newer_snapshot_extends_age_and_duplicate_import_changes_nothing(self):
        self.ingest(snapshot(four_videos(), cutoff=10, pulled="2026-10-12T00:00:00+00:00"), "s1.json")
        first = self.kpis()
        again = self.ingest(snapshot(four_videos(), cutoff=10, pulled="2026-10-12T00:00:00+00:00"), "s1b.json")
        self.assertEqual(again["totals"]["action"], "unchanged (snapshot already imported)")
        self.assertEqual(self.kpis(), first)
        self.ingest(snapshot(four_videos(), cutoff=12, pulled="2026-10-14T00:00:00+00:00"), "s2.json")
        k = self.kpis()
        self.assertEqual(k["B"]["maturity"], "d3")
        self.assertEqual((k["B"]["views_d3"], k["B"]["engaged_views_d3"]), (100, 30))
        self.assertEqual(k["B"]["engaged_share_d3"], 0.3)

    def test_api_error_is_not_a_zero(self):
        snap = snapshot(four_videos(), cutoff=10, pulled="2026-10-12T00:00:00+00:00", errors=["A daily: quotaExceeded"])
        self.ingest(snap, "s1.json")
        k = self.kpis()
        self.assertIsNone(k["A"]["views_d3"])
        self.assertTrue(k["A"]["status_d3"].startswith("incomplete"))

    def test_legacy_publication_blocks_learning(self):
        self.link("QqI7w_BZaWE", "run-legacy", 0)
        code, res = self.run_learn("kpis", "--db", self.db, "--out", self.tmp / "k.json")
        self.assertEqual(code, 2)
        self.assertEqual(res["error"], "LEGACY_LINKED_IN_DB")


def attrs_doc(rows: list[dict]) -> dict:
    return {"schema": "cf-creative-attributes/1", "videos": rows, "gaps": [], "coverage": {}}


class Analysis(Base):
    """Eight mature videos: statement openers have a higher D3 engaged share than question openers."""
    def build(self, shares: dict, pcts: dict | None = None):
        vids = []
        for i, (pid, share) in enumerate(shares.items()):
            self.link(pid, f"run-{pid}", i)
            vids.append({"id": pid, "pub": i, "daily": {i + d: (100, round(100 * share)) for d in range(3)},
                         "totals": totals(300, round(300 * share), (pcts or {}).get(pid, 60))})
        self.ingest(snapshot(vids, cutoff=12, pulled="2026-10-14T00:00:00+00:00"), "s.json")

    def analyze(self, forms: dict, mech: dict | None = None) -> dict:
        rows = [{"platform_video_id": p, "opening_form": f, "curiosity_mechanism": (mech or {}).get(p, "m"), "format": "explainer",
                 "duration_s": 25.0} for p, f in forms.items()]
        (self.tmp / "attrs.json").write_text(json.dumps(attrs_doc(rows)), encoding="utf-8")
        code, res = self.run_learn("analyze", "--db", self.db, "--attributes", self.tmp / "attrs.json", "--out-dir", self.tmp / "L")
        self.assertEqual(code, 0, res)
        return json.loads((self.tmp / "L" / "learning_summary.json").read_text(encoding="utf-8"))

    def test_effect_found_bounded_and_explained(self):
        shares = {"s1": .50, "s2": .48, "s3": .52, "s4": .47, "q1": .30, "q2": .33, "q3": .28, "q4": .31}
        self.build(shares)
        s = self.analyze({k: "statement" if k[0] == "s" else "question" for k in shares})
        st = s["directives"]["hook"]["opening_form"]["statement"]
        qu = s["directives"]["hook"]["opening_form"]["question"]
        self.assertGreater(st["multiplier"], 1.0); self.assertLess(qu["multiplier"], 1.0)
        for e in (st, qu):                                     # n=4 per side -> low confidence -> cap 5 %
            self.assertEqual(e["confidence"], "low")
            self.assertLessEqual(abs(e["multiplier"] - 1), LN.POLICY["caps"]["low"] + 1e-9)
        self.assertTrue(any(f["attribute"] == "opening_form" for f in s["findings"]["appears_to_work"]))
        self.assertTrue(all("n=" in f["evidence"] for k in s["findings"] for f in s["findings"][k]))
        self.assertIn("Correlation", (self.tmp / "L" / "LEARNING_REPORT.md").read_text(encoding="utf-8"))
        self.assertIsNotNone(s["next_experiment"])

    def test_small_groups_make_no_directive(self):
        shares = {"s1": .50, "s2": .48, "q1": .30, "q2": .33, "q3": .28}
        self.build(shares)
        s = self.analyze({k: "statement" if k[0] == "s" else "question" for k in shares})
        self.assertEqual(s["directives"]["hook"]["opening_form"], {})          # n=2 vs 3: nothing changes
        self.assertTrue(any("opening_form=statement" in x for x in s["directives"]["explore"]))
        self.assertEqual(s["findings"]["appears_to_work"], [])

    def test_unestablished_direction_makes_no_directive(self):
        shares = {"s1": .40, "s2": .30, "s3": .45, "s4": .35, "q1": .38, "q2": .33, "q3": .42, "q4": .36}
        self.build(shares)
        s = self.analyze({k: "statement" if k[0] == "s" else "question" for k in shares})
        self.assertEqual(s["directives"]["hook"]["opening_form"], {})          # noise is never a tie-breaker
        self.assertTrue(any("direction not established" in x for x in s["directives"]["explore"]))

    def test_guardrail_blocks_a_bonus(self):
        shares = {"s1": .50, "s2": .48, "s3": .52, "s4": .47, "q1": .30, "q2": .33, "q3": .28, "q4": .31}
        self.build(shares, pcts={**{k: 40 for k in shares if k[0] == "s"}, **{k: 70 for k in shares if k[0] == "q"}})
        s = self.analyze({k: "statement" if k[0] == "s" else "question" for k in shares})
        self.assertNotIn("statement", s["directives"]["hook"]["opening_form"])
        self.assertTrue(any("guardrail" in x for x in s["directives"]["explore"]))

    def test_missing_attribute_never_imputed(self):
        shares = {"s1": .50, "s2": .48, "s3": .52, "q1": .30, "q2": .33, "q3": .28}
        self.build(shares)
        s = self.analyze({"s1": "statement", "s2": "statement", "s3": "statement", "q1": None, "q2": None, "q3": None})
        self.assertEqual(s["directives"]["hook"]["opening_form"], {})          # only one known level: nothing to compare


class Attributes(Base):
    def test_from_run_files_with_sources_and_explicit_gaps(self):
        run = self.tmp / "runs" / "run-A"
        v = run / "videos" / "v01"
        for d in ("hook", "script", "audio", "visual", "package"):
            (v / d).mkdir(parents=True)
        (run / "selection").mkdir()
        (run / "run.json").write_text(json.dumps({"run_id": "run-A", "topic": "Why is the sky blue?",
                                                  "constraints": ["H1-2026W43-opening-form arm=statement: first line"]}), encoding="utf-8")
        (v / "hook" / "selected_hook.json").write_text(json.dumps({"spoken_text": "Pinch your nose. Now hum.",
                                                                   "curiosity_mechanism": "Direct_Challenge"}), encoding="utf-8")
        (v / "script" / "script.json").write_text(json.dumps({"beats": [{"id": "b1", "role": "hook"}, {"id": "b2", "role": "setup"},
                                                                         {"id": "b3", "role": "value"}, {"id": "b4", "role": "loop"}]}), encoding="utf-8")
        (v / "audio" / "timing.json").write_text(json.dumps({"duration_s": 24.0, "sentences": [
            {"beat_id": "b1", "start": 0.1, "end": 1.9}, {"beat_id": "b2", "start": 2.1, "end": 3.0}, {"beat_id": "b3", "start": 3.4, "end": 9}]}), encoding="utf-8")
        (v / "visual" / "storyboard.json").write_text(json.dumps({"scenes": [{}] * 6}), encoding="utf-8")
        (v / "package" / "package_selection.json").write_text(json.dumps({"selected": {"title": "Why can't you hum?"}}), encoding="utf-8")
        (run / "selection" / "selection.json").write_text(json.dumps({"selected": [{"video_id": "v01", "format": "explainer"}]}), encoding="utf-8")
        self.link("YT1", "run-A", 3)
        man = self.tmp / "manifest.json"
        man.write_text(json.dumps({"selected": [{"slot": 1, "topic": "Why is the sky blue?", "category": "science"}]}), encoding="utf-8")
        code, res = self.run_learn("attributes", "--db", self.db, "--runs-root", self.tmp / "runs", "--manifests", man,
                                   "--out", self.tmp / "a.json")
        self.assertEqual(code, 0, res)
        a = json.loads((self.tmp / "a.json").read_text(encoding="utf-8"))["videos"][0]
        self.assertEqual((a["opening_form"], a["curiosity_mechanism"], a["hook_spoken_s"], a["first_value_s"]),
                         ("imperative", "direct_challenge", 1.9, 3.4))
        self.assertEqual((a["has_setup_beat"], a["ends_with_loop"], a["cta_beat"], a["scenes_n"], a["scenes_per_10s"]),
                         ("yes", "yes", "no", 6, 2.5))
        self.assertEqual((a["title_form"], a["format"], a["category"]), ("question", "explainer", "science"))
        self.assertEqual(a["experiment_arm"], {"experiment": "H1-2026W43-opening-form", "arm": "statement"})
        self.assertIn("videos/v01/hook/selected_hook.json", a["sources"])

    def test_duplicate_run_folder_most_complete_wins(self):
        stale = self.tmp / "pc" / "run-D"
        (stale / "videos").mkdir(parents=True)
        (stale / "run.json").write_text(json.dumps({"run_id": "run-D", "topic": "stale"}), encoding="utf-8")
        done = self.tmp / "cloud" / "run-D"
        (done / "videos" / "v01" / "hook").mkdir(parents=True); (done / "package" / "v01").mkdir(parents=True)
        (done / "run.json").write_text(json.dumps({"run_id": "run-D", "topic": "finished"}), encoding="utf-8")
        (done / "videos" / "v01" / "hook" / "selected_hook.json").write_text(json.dumps({"spoken_text": "Why?"}), encoding="utf-8")
        (done / "package" / "v01" / "provenance.json").write_text("{}", encoding="utf-8")
        self.link("YT9", "run-D", 3)
        code, res = self.run_learn("attributes", "--db", self.db, "--runs-root", self.tmp / "pc", "--runs-root", self.tmp / "cloud",
                                   "--out", self.tmp / "a.json")
        doc = json.loads((self.tmp / "a.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["videos"][0]["topic"], "finished")
        self.assertEqual(doc["duplicate_run_folders"][0]["ignored"], [str(stale)])

    def test_no_manifest_means_no_category(self):
        run = self.tmp / "runs" / "run-B"
        (run / "videos" / "v01").mkdir(parents=True)
        (run / "run.json").write_text(json.dumps({"run_id": "run-B", "topic": "x"}), encoding="utf-8")
        self.link("YT2", "run-B", 3)
        self.link("YT3", "run-missing", 4)
        code, res = self.run_learn("attributes", "--db", self.db, "--runs-root", self.tmp / "runs", "--out", self.tmp / "a.json")
        doc = json.loads((self.tmp / "a.json").read_text(encoding="utf-8"))
        a = doc["videos"][0]
        self.assertIsNone(a["category"]); self.assertTrue(a["category_source"].startswith("unavailable"))
        self.assertIn("opening_form", a["missing"])
        self.assertEqual([g["run_id"] for g in doc["gaps"]], ["run-missing"])


class Apply(unittest.TestCase):
    def test_opening_form_rule(self):
        for t, f in (("Why does ice crack?", "question"), ("Pinch your nose. Now hum.", "imperative"),
                     ("The ocean isn't blue because of the sky.", "statement"), ("Two lights. Only one twinkles?", "statement")):
            self.assertEqual(LA.opening_form(t), f, t)

    def test_bounds_hold_even_for_a_hostile_summary(self):
        s = {"summary_id": "L-x", "policy": {}, "directives": {"topic": {"category": {"space": {"multiplier": 9}}},
                                                                 "hook": {"opening_form": {"question": {"multiplier": -4}}}}}
        self.assertEqual(LA.topic_multiplier(s, "space")[0], 1 + LA.MAX_MULT_DEV)
        b, _ = LA.hook_bonus(s, "question", None)
        self.assertGreaterEqual(b, -LA.MAX_HOOK_BONUS)
        self.assertEqual(LA.topic_multiplier(s, "nature")[0], 1.0)
        self.assertEqual(LA.topic_multiplier(None, "space"), (1.0, []))

    def test_load_rejects_wrong_schema(self):
        d = Path(tempfile.mkdtemp())
        (d / "x.json").write_text(json.dumps({"schema": "other"}), encoding="utf-8")
        with self.assertRaises(LA.LearningError):
            LA.load(d / "x.json")
        shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main(verbosity=2)
