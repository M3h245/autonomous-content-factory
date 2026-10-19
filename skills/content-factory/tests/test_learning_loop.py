"""v3.1.0 feedback loop: a learning summary changes downstream decisions, boundedly and on the record.

  1. idea_engine: two summaries with opposite category evidence pick different topics from the same candidates;
     without a summary the ranking is the old one; the influence is written to ranking.json and the manifest.
  2. factory.py init --learning: the run records the summary, its guidance joins the constraints, format priors reach
     SELECTION's weights.json; a broken summary is refused; without --learning nothing changes.
  3. hook_engine select --learning: among candidates that PASSED the independent review, opposite evidence on the
     opening form selects different hooks; the choice without learning and the bonuses are recorded; a failing
     candidate never becomes selectable.

Run from skills/:  python -m unittest content-factory.tests.test_learning_loop
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "content-factory" / "scripts"))
sys.path.insert(0, str(ROOT / "content-analytics" / "scripts"))
import idea_engine as IE  # noqa: E402
import learning_apply as LA  # noqa: E402
import phase2_kit as K  # noqa: E402
import test_idea_engine as TI  # noqa: E402

PY = sys.executable
FACTORY = ROOT / "content-factory" / "scripts" / "factory.py"


def summary(sid: str, category=None, opening=None, fmt=None, conf="medium") -> dict:
    def e(m):
        return {"multiplier": m, "confidence": conf, "n": 8, "n_rest": 8, "metric": "engaged_share_d3", "effect_label": "test"}
    return {"schema": LA.SCHEMA, "summary_id": sid, "policy": {"summary_confidence": conf}, "inputs": {"analytics_cutoff": "2026-10-15"},
            "directives": {"topic": {"category": {k: e(v) for k, v in (category or {}).items()},
                                     "format": {k: e(v) for k, v in (fmt or {}).items()}},
                           "hook": {"opening_form": {k: e(v) for k, v in (opening or {}).items()}, "curiosity_mechanism": {}},
                           "script": {}, "guidance": {"hook": [f"{sid} hook guidance"], "script": [f"{sid} script guidance"]},
                           "explore": []},
            "next_experiment": {"hypothesis_id": f"H-{sid}", "attribute": "opening_form", "arms": ["statement", "question"]}}


def write(tmp: Path, s: dict) -> Path:
    p = tmp / f"{s['summary_id']}.json"
    p.write_text(json.dumps(s))
    return p


class TopicDecision(unittest.TestCase):
    def rows(self):
        base = {"angle": "a mechanism explained", "hook": None, "visual": None, "position": 0}
        return [dict(base, id="moon", topic="Why does the Moon look orange tonight?", category="space", position=1,
                     score={"total": 0.70}),
                dict(base, id="frog", topic="How do tree frogs stick to glass?", category="nature", position=2,
                     score={"total": 0.70})]

    def test_opposite_evidence_opposite_topic(self):
        space = summary("L-space", category={"space": 1.10, "nature": 0.95})
        nature = summary("L-nature", category={"nature": 1.10, "space": 0.95})
        picks = {}
        for s in (None, space, nature):
            rows = self.rows()
            for r in rows:
                r["score"] = IE.apply_learning(r["score"], r, s)
            winners, _ = IE.select(rows, 1)
            picks[s["summary_id"] if s else None] = winners[0]["id"]
            if s:
                self.assertIn("evidence", winners[0]["score"])
                self.assertEqual(winners[0]["score"]["evidence"]["summary_id"], s["summary_id"])
        self.assertEqual(picks["L-space"], "moon")
        self.assertEqual(picks["L-nature"], "frog")
        self.assertEqual(picks[None], "moon")              # tie -> file order, exactly the old rule

    def test_cli_records_influence_and_no_learning_is_unchanged(self):
        tmp = Path(tempfile.mkdtemp(prefix="ie_learn_"))
        try:
            db = TI.fresh_db(tmp)
            ideas = tmp / "ideas.json"
            ideas.write_text(json.dumps(TI.make_candidates()))
            env = TI.clean_env()
            out = {}
            for name, extra in (("plain", ["--no-learning"]),
                                ("nat", ["--learning", write(tmp, summary("L-nat", category={"nature": 1.15, "science": 0.85}))]),
                                ("sci", ["--learning", write(tmp, summary("L-sci", category={"science": 1.15, "nature": 0.85}))])):
                code, res, err = TI.engine("select", "--ideas-file", ideas, "--batches-dir", tmp / name, "--db", db, "--count", 3,
                                           "--allow-reused-input", *extra, cwd=tmp, env=env)
                self.assertEqual(code, 0, (res, err))
                b = Path(res["batch"])
                out[name] = {"manifest": json.loads((b / "manifest.json").read_text(encoding="utf-8")), "ranking": json.loads((b / "ranking.json").read_text(encoding="utf-8"))}
            self.assertNotIn("learning", out["plain"]["manifest"]["production"])
            self.assertNotIn("learning", out["plain"]["ranking"])
            cats = {k: [w["category"] for w in v["manifest"]["selected"]] for k, v in out.items()}
            self.assertNotEqual(cats["nat"], cats["sci"], cats)
            self.assertGreaterEqual(cats["nat"].count("nature"), cats["sci"].count("nature"))
            self.assertEqual(out["nat"]["manifest"]["production"]["learning"]["summary_id"], "L-nat")
            r0 = out["nat"]["ranking"]["ranked"][0]
            self.assertIn("base_total", r0); self.assertIn("evidence", r0)
            for k in ("nat", "sci"):                       # bounded: never more than ±15 % on any candidate
                for r in out[k]["ranking"]["ranked"]:
                    self.assertLessEqual(abs(r["total"] - r["base_total"]), LA.MAX_MULT_DEV * r["base_total"] + 1e-4)   # totals are rounded to 4 places
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class InitDecision(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="init_learn_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def init(self, *extra):
        p = subprocess.run([PY, str(FACTORY), "init", "--topic", "Why do tree frogs stick to glass?", "--count", "1",
                            "--runs-dir", str(self.tmp / "runs"), "--no-db", *map(str, extra)], capture_output=True, text=True)
        try:
            return p.returncode, json.loads(p.stdout)
        except ValueError:
            return p.returncode, {"raw": p.stdout + p.stderr}

    def test_run_records_summary_and_guidance(self):
        s = write(self.tmp, summary("L-init", fmt={"myth-bust": 1.1}))
        code, res = self.init("--learning", s)
        self.assertEqual(code, 0, res)
        run = Path(res["run"])
        brief = json.loads((run / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(brief["learning"]["summary_id"], "L-init")
        self.assertEqual(brief["learning"]["hypothesis_id"], "H-L-init")
        self.assertTrue(any("L-init hook guidance" in c for c in brief["constraints"]))
        self.assertTrue(any("L-init script guidance" in c for c in brief["constraints"]))
        self.assertEqual(json.loads((run / "learning.json").read_text(encoding="utf-8"))["summary_id"], "L-init")

    def test_no_learning_no_change_and_broken_file_refused(self):
        code, res = self.init()
        self.assertEqual(code, 0, res)
        brief = json.loads((Path(res["run"]) / "run.json").read_text(encoding="utf-8"))
        self.assertNotIn("learning", brief)
        self.assertFalse((Path(res["run"]) / "learning.json").exists())
        bad = self.tmp / "bad.json"
        bad.write_text(json.dumps({"schema": "nope"}))
        code, res = self.init("--learning", bad)
        self.assertEqual((code, res.get("error")), (2, "LEARNING_INVALID"))


class HookDecision(unittest.TestCase):
    """Two candidates with the same review total (statement vs question) plus three that fail the review."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="hook_learn_"))
        cls.cands = [K.cand("hs", "Wrinkly fingers are your nerves at work.", "x", mech="misconception_reversal"),
                     K.cand("hq", "Are wrinkly fingers your nerves at work?", "x", mech="question"),
                     K.cand("f1", "So, today we talk about fingers.", "x", mech="filler_a"),
                     K.cand("f2", "In this video, fingers and water.", "x", mech="filler_b"),
                     K.cand("f3", "Hello everyone, welcome back.", "x", mech="filler_c")]
        cls.res = {}
        for name, s in (("plain", None), ("stmt", summary("L-stmt", opening={"statement": 1.10, "question": 0.95})),
                        ("ques", summary("L-ques", opening={"question": 1.10, "statement": 0.95})),
                        ("fail", summary("L-fail", opening={"statement": 1.15}))):
            d = cls.tmp / name
            K.write_set(d, {"x": K.STRONG_SVG}, copy.deepcopy(cls.cands))
            cmd = [PY, str(K.HOOK_ENGINE), "select", "--hooks", d / "hooks.json", "--dossier", d / "dossier.json",
                   "--out-dir", d, "--result", d / "result.json"] + (["--learning", write(cls.tmp, s)] if s else [])
            subprocess.run(list(map(str, cmd)), capture_output=True, text=True)
            cls.res[name] = {"scored": json.loads((d / "hooks.scored.json").read_text(encoding="utf-8")),
                             "result": json.loads((d / "result.json").read_text(encoding="utf-8")),
                             "selected": json.loads((d / "selected_hook.json").read_text(encoding="utf-8")) if (d / "selected_hook.json").exists() else None}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_equal_review_totals_then_evidence_decides(self):
        tot = {c["hook_id"]: c.get("total") for c in self.res["plain"]["scored"]["candidates"]}
        self.assertEqual(tot["hs"], tot["hq"], tot)
        self.assertEqual(self.res["stmt"]["scored"]["selected"], "hs")
        self.assertEqual(self.res["ques"]["scored"]["selected"], "hq")

    def test_influence_recorded(self):
        plain = self.res["plain"]["scored"]["selected"]
        for name, sid in (("stmt", "L-stmt"), ("ques", "L-ques")):
            inf = self.res[name]["selected"]["learning_influence"]
            self.assertEqual(inf["summary_id"], sid)
            self.assertEqual(inf["without_learning"], plain)
            self.assertEqual(inf["changed_choice"], inf["selected"] != plain)
            self.assertLessEqual(max(abs(b) for b in inf["bonuses"].values()), LA.MAX_HOOK_BONUS)
            m = next(c for c in self.res[name]["result"]["gate"]["checks"] if c["id"] == "HOOK.LEARNING_COVERAGE")
            self.assertTrue(m["passed"])
        self.assertNotIn("learning_influence", self.res["plain"]["selected"])

    def test_failing_candidate_never_selected(self):
        sel = self.res["fail"]["scored"]["selected"]
        verdicts = {c["hook_id"]: (c.get("review") or {}).get("verdict") for c in self.res["fail"]["scored"]["candidates"]}
        self.assertEqual(verdicts[sel], "PASS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
