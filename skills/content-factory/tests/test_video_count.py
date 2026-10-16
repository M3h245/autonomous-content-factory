"""How many videos are made: the default is 2, `--count N` overrides it, anything but a whole number 1-50 is refused.

Covers both entry points that decide the number of videos — `factory.py init --count` (videos per run) and
`idea_engine.py select|run --count` (topics = runs = videos per batch) — and the run_factory templates' defaults.
Nothing here produces a video: `init` only creates the run folder, `select` stops at the manifest.

    cd skills && python -m unittest content-factory.tests.test_video_count        (~1 min)
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (ROOT / "content-factory" / "scripts", ROOT / "content-database" / "scripts", HERE):
    sys.path.insert(0, str(p))
import factory as F  # noqa: E402
import idea_engine as IE  # noqa: E402
import test_idea_engine as IET  # noqa: E402   helpers only: fresh candidates, a seeded memory, the engine runner

PY = sys.executable
FACT = ROOT / "content-factory" / "scripts" / "factory.py"
TEMPLATES = ROOT / "automation-engineering" / "assets" / "templates"
INVALID = ["0", "-1", "abc", "2.5", "", " ", "+3", "1e1", "51", "99999999999999999999"]


def candidates() -> dict:
    """The idea engine tests' fresh candidates only: unlike test_idea_engine.make_candidates this does not depend on
    which ideas memory/dump.json still holds."""
    return {"version": "1.0", "candidates": [{"id": i, "topic": t, "angle": a, "hook": h, "visual": v, "category": c,
                                              "source_hint": s, "notes": None} for i, t, a, h, v, c, s in IET.FRESH]}


def init(runs: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, str(FACT), "init", "--topic", "count check", "--no-db", "--runs-dir", str(runs), *extra],
                          capture_output=True, text=True, env=IET.clean_env())


class CountRule(unittest.TestCase):
    def test_default_is_two_everywhere(self):
        self.assertEqual(F.DEFAULT_VIDEO_COUNT, 2)
        self.assertEqual(IE.DEFAULT_COUNT, F.DEFAULT_VIDEO_COUNT)        # one default, defined once
        self.assertEqual(F.MAX_VIDEO_COUNT, 50)
        self.assertFalse(hasattr(IE, "WINNERS"))                         # the old fixed 5 is gone

    def test_valid_values(self):
        for text, n in (("1", 1), ("2", 2), ("4", 4), ("50", 50), (" 4 ", 4), ("04", 4)):
            self.assertEqual(F.video_count(text), n, text)

    def test_invalid_values_name_the_rule(self):
        for text in INVALID:
            with self.assertRaises(argparse.ArgumentTypeError, msg=repr(text)) as cm:
                F.video_count(text)
            self.assertIn("positive whole number from 1 to 50", str(cm.exception))


class FactoryInit(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cf_count_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def brief(self, p: subprocess.CompletedProcess) -> dict:
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])
        return json.loads((Path(json.loads(p.stdout)["run"]) / "state.json").read_text(encoding="utf-8"))["brief"]

    def test_default_makes_two_videos(self):
        self.assertEqual(self.brief(init(self.tmp / "runs"))["count"], 2)

    def test_count_four(self):
        self.assertEqual(self.brief(init(self.tmp / "runs", "--count", "4"))["count"], 4)

    def test_invalid_count_is_refused_before_anything_is_written(self):
        runs = self.tmp / "runs"
        for text in INVALID:
            for args in (["--count", text], [f"--count={text}"]):
                p = init(runs, *args)
                self.assertEqual(p.returncode, 2, (args, p.stdout, p.stderr))
                self.assertRegex(p.stderr, r"argument --count: invalid count .*positive whole number from 1 to 50", args)
                self.assertFalse(runs.exists(), args)                  # no run folder was created


class IdeaEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="ie_count_"))
        cls.db = IET.fresh_db(cls.tmp)
        cls.ideas = cls.tmp / "ideas.json"
        cls.ideas.write_text(json.dumps(candidates(), indent=1), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def select(self, name: str, *extra):
        return IET.engine("select", "--ideas-file", self.ideas, "--batches-dir", self.tmp / name, "--db", self.db, *extra,
                          cwd=self.tmp)

    def winners(self, out) -> tuple[list, list]:
        batch = Path(out["batch"])
        sel = json.loads((batch / "selected.json").read_text(encoding="utf-8"))["winners"]
        man = json.loads((batch / "manifest.json").read_text(encoding="utf-8"))["selected"]
        return sel, [s["slot"] for s in man]

    def test_default_selects_two(self):
        rc, out, err = self.select("b-default")
        self.assertEqual(rc, 0, f"{out}\n{err[-2000:]}")
        sel, slots = self.winners(out)
        self.assertEqual((len(sel), slots, len(out["selected"])), (2, [1, 2], 2))

    def test_count_four_selects_four(self):
        rc, out, err = self.select("b-four", "--count", "4")
        self.assertEqual(rc, 0, f"{out}\n{err[-2000:]}")
        sel, slots = self.winners(out)
        self.assertEqual((len(sel), slots), (4, [1, 2, 3, 4]))
        names = {w["id"] for w in sel}
        self.assertEqual(len(names), 4)                                     # four different candidates

    def test_more_than_the_usable_candidates_fails_clearly(self):
        rc, out, _ = self.select("b-fifty", "--count", "50")
        self.assertEqual((rc, out["error"], out["need"]), (2, "TOO_FEW_CANDIDATES", 50))
        self.assertFalse((Path(out["batch"]) / "manifest.json").exists())

    def test_invalid_count_is_refused_before_anything_is_written(self):
        for cmd in ("select", "run"):
            for text in INVALID:
                d = self.tmp / f"b-bad-{cmd}"
                rc, out, err = IET.engine(cmd, "--ideas-file", self.ideas, "--batches-dir", d, "--db", self.db,
                                          f"--count={text}", "--produce", "none", cwd=self.tmp) if cmd == "run" else \
                    IET.engine(cmd, "--ideas-file", self.ideas, "--batches-dir", d, "--db", self.db, f"--count={text}",
                               cwd=self.tmp)
                self.assertEqual(rc, 2, (cmd, text, out, err[-500:]))
                self.assertRegex(err, r"argument --count: invalid count .*positive whole number from 1 to 50", (cmd, text))
                self.assertFalse(d.exists(), (cmd, text))                   # no batch folder was created


class Templates(unittest.TestCase):
    """The unattended templates are checked as text only: running them would start a real Claude Code session."""

    def test_powershell_default_and_check(self):
        s = (TEMPLATES / "run_factory.ps1").read_text(encoding="utf-8")
        self.assertRegex(s, r'\[string\]\$Count = "2"')
        self.assertIn("'^[0-9]{1,3}$'", s)
        self.assertIn("-gt 50", s)
        self.assertIn("exit 2", s)

    def test_shell_default_count_option_and_check(self):
        s = (TEMPLATES / "run_factory.sh").read_text(encoding="utf-8")
        self.assertIn('COUNT="${1:-2}"', s)
        self.assertIn('"${1:-}" = "--count"', s)
        self.assertIn("^[0-9]{1,3}$", s)
        self.assertNotRegex(s, r"\$\{2:-5\}")

    def test_github_workflow_default(self):
        s = (TEMPLATES / "content-factory.yml").read_text(encoding="utf-8")
        self.assertIn('default: "2"', s)
        self.assertIn("inputs.count || '2'", s)
        self.assertIsNone(re.search(r"inputs\.count \|\| '[3-9]'", s))


if __name__ == "__main__":
    unittest.main()
