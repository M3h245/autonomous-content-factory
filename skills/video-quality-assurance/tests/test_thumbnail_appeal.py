"""P6.2 (v3.3) — thumbnail taste is judged, not measured.

A cover can pass every geometric gate and still be dull, so the package review carries one judge-only dimension,
`thumbnail_appeal`. These tests pin the three behaviours the design depends on:

* the heuristic never fails a package on taste (it returns a neutral 3 and says "not judged") — heuristic-only runs
  keep working exactly as before;
* an external judge is AUTHORITATIVE for that dimension (it may raise as well as lower), while every other dimension
  keeps the min(heuristic, judge) rule;
* `--backend subagent` writes the request a fresh reviewer reads (shelf size + full size + title/promise) and exits 3
  until `package_judgment.json` exists, and a low taste score routes back to PACKAGE / redesign_cover.

    cd skills && python -m unittest video-quality-assurance.tests.test_thumbnail_appeal
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
REVIEWER = REPO / "skills" / "video-quality-assurance" / "scripts" / "reviewer.py"
ENGINE = REPO / "skills" / "content-factory" / "scripts" / "package_engine.py"
FIXTURE = REPO / "fixtures" / "phase4_package_run"
PY = sys.executable


def read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def write_json(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, indent=1), encoding="utf-8")


class ThumbnailAppeal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="p62_"))
        src = next(FIXTURE.iterdir())
        shutil.copytree(src, cls.tmp / src.name)
        cls.rundir = cls.tmp / src.name
        pkg = cls.rundir / "videos" / "v01" / "package"
        cls.out = cls.tmp / "out"
        r = subprocess.run([PY, str(ENGINE), "select",
                            "--candidates", pkg / "package_candidates.json",
                            "--script", cls.rundir / "videos/v01/script/script.json",
                            "--timing", cls.rundir / "videos/v01/audio/timing.json",
                            "--final", cls.rundir / "videos/v01/subtitles/final.mp4",
                            "--dossier", cls.rundir / "research/dossier.json",
                            "--out-dir", cls.out], capture_output=True, text=True)
        if not (cls.out / "review" / "packets" / "P1").exists():
            raise AssertionError(f"package_engine failed: {(r.stderr or r.stdout)[-800:]}")
        cls.packets = sorted(str(x) for x in (cls.out / "review" / "packets").iterdir())
        cls.sha = {Path(p).name: hashlib.sha256((Path(p) / "manifest.json").read_bytes()).hexdigest() for p in cls.packets}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def judge(self, scores: dict, out: Path) -> dict:
        j = self.tmp / f"{out.name}.json"
        write_json(j, {"candidates": {cid: {"packet_manifest_sha256": self.sha[cid], "scores": s,
                                            "notes": {k: "test note" for k in s}} for cid, s in scores.items()}})
        r = subprocess.run([PY, str(REVIEWER), "review-package", "--packets", *self.packets,
                            "--out", str(out), "--judgment", str(j)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, (r.stderr or r.stdout)[-800:])
        return {x["candidate"]: x for x in read_json(out / "package_reviews.json")["results"]}

    def test_heuristic_reports_taste_as_not_judged_and_does_not_fail_on_it(self):
        """Heuristic-only packaging (the default) still selects a package: taste is reported, not gated."""
        sel = read_json(self.out / "package_selection.json")
        self.assertEqual(sel["status"], "passed", sel.get("set_checks"))
        rev = {x["candidate"]: x for x in read_json(self.out / "review" / "package_reviews.json")["results"]}
        for cid, x in rev.items():
            self.assertIn("thumbnail_appeal", x["scores"])
            self.assertEqual(x["scores"]["thumbnail_appeal"]["score"], 3)
            self.assertIn("not judged", x["scores"]["thumbnail_appeal"].get("note", ""))
            self.assertNotIn("thumbnail_appeal", [f["id"] for f in x["failures"]], f"{cid} failed on an unjudged taste dim")

    def test_judge_is_authoritative_for_taste_only(self):
        """P1 is raised by the judge (3 → 5); P2 is lowered (3 → 2) and every other dimension keeps min()."""
        rev = self.judge({"P1": {"thumbnail_appeal": 5}, "P2": {"thumbnail_appeal": 2, "curiosity": 5}}, self.tmp / "rv1")
        p1 = rev["P1"]["scores"]["thumbnail_appeal"]
        self.assertEqual((p1["score"], p1["judge_score"], p1["heuristic_score"], p1["judge"]), (5, 5, 3, "external"))
        self.assertEqual(rev["P1"]["verdict"], "PASS")
        p2 = rev["P2"]["scores"]["thumbnail_appeal"]
        self.assertEqual((p2["score"], p2["judge"], p2["heuristic_score"]), (2, "external", 3))
        self.assertEqual(rev["P2"]["verdict"], "FAIL")
        # a non-taste dimension can only be lowered by the judge
        self.assertLessEqual(rev["P2"]["scores"]["curiosity"]["score"],
                             rev["P2"]["scores"]["curiosity"]["heuristic_score"])

    def test_low_taste_routes_back_to_package_redesign_cover(self):
        rev = self.judge({cid: {"thumbnail_appeal": 2} for cid in self.sha}, self.tmp / "rv2")
        for cid, x in rev.items():
            f = next(f for f in x["failures"] if f["id"] == "thumbnail_appeal")
            self.assertEqual(f["fix_route"]["stage"], "PACKAGE")
            self.assertEqual(f["fix_route"]["action"], "redesign_cover")
            self.assertEqual(f["fix_route"]["params"]["dimension"], "thumbnail_appeal")

    def test_unjudged_cover_in_a_judgment_is_blocking(self):
        """Once a judgment is in play it must cover taste; otherwise the cover would ship unjudged."""
        rev = self.judge({"P1": {"curiosity": 5}}, self.tmp / "rv3")
        ids = [f["id"] for f in rev["P1"]["failures"]]
        self.assertIn("JUDGMENT.UNJUDGED_COVER", ids)
        f = next(f for f in rev["P1"]["failures"] if f["id"] == "JUDGMENT.UNJUDGED_COVER")
        self.assertEqual((f["fix_route"]["stage"], f["fix_route"]["action"]), ("PACKAGE", "redesign_cover"))

    def test_subagent_backend_awaits_a_fresh_reviewer(self):
        out = self.tmp / "rv4"
        r = subprocess.run([PY, str(REVIEWER), "review-package", "--packets", *self.packets,
                            "--out", str(out), "--backend", "subagent"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 3, (r.stderr or r.stdout)[-800:])
        self.assertEqual(json.loads(r.stdout.splitlines()[-1])["verdict"], "AWAITING_JUDGMENT")
        req = (out / "package_review_request.md").read_text(encoding="utf-8")
        for needle in ("frames/thumbnail.jpg", "frames/thumbnail_168.png", "thumbnail_appeal",
                       "package_judgment.json", "P1", self.sha["P1"]):
            self.assertIn(needle, req)
        self.assertFalse((out / "package_reviews.json").exists(), "a review must not be written before the judgment")
        log = read_json(out / "boundary_log.json")
        self.assertEqual(log["judge"], "subagent (awaiting)")
        # the heuristic's scores are not leaked to the judge
        self.assertNotIn("heuristic", req.lower())

    def test_package_engine_surfaces_the_await(self):
        """package_engine select --review-backend subagent returns 3 and marks the selection awaiting_judgment."""
        tmp = Path(tempfile.mkdtemp(prefix="p62eng_"))
        try:
            pkg = self.rundir / "videos" / "v01" / "package"
            r = subprocess.run([PY, str(ENGINE), "select",
                                "--candidates", pkg / "package_candidates.json",
                                "--script", self.rundir / "videos/v01/script/script.json",
                                "--timing", self.rundir / "videos/v01/audio/timing.json",
                                "--final", self.rundir / "videos/v01/subtitles/final.mp4",
                                "--dossier", self.rundir / "research/dossier.json",
                                "--out-dir", tmp / "out", "--review-backend", "subagent"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 3, (r.stderr or r.stdout)[-800:])
            sel = read_json(tmp / "out" / "package_selection.json")
            self.assertEqual(sel["status"], "awaiting_judgment")
            self.assertIsNone(sel["selected"])
            self.assertIn("PKG.AWAITING_JUDGMENT", [s["id"] for s in sel["set_checks"]])
            self.assertTrue((tmp / "out" / "review" / "package_review_request.md").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
