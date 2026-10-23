"""Run every unittest module the v3.3 patch can affect. Reports per-file results and a summary.

Usage:  python tools/run_v33_tests.py [--quiet]
Not part of the product; a local convenience runner so the suite can be run without pytest.
"""
from __future__ import annotations

import importlib.util
import io
import sys
import time
import traceback
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Files whose modules the v3.3 patch touches (or that guard it). Explicit list keeps the run deterministic.
TARGETS = [
    "skills/content-factory/tests",
    "skills/content-analytics/tests",
    "skills/content-database/tests",
    "skills/hook-engineering/tests",
    "skills/video-production/tests",
    "skills/video-quality-assurance/tests",
    "skills/visual-storyboarding/tests",
    "skills/subtitle-production/tests",
    "skills/short-form-script/tests",
]


def load_module(path: Path):
    name = f"cf_v33_{path.parent.name}_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    quiet = "--quiet" in sys.argv
    files = []
    for t in TARGETS:
        d = REPO / t
        if d.is_dir():
            files += sorted(d.glob("test_*.py"))
    ok = fail = err = 0
    failed_names: list[str] = []
    for f in files:
        try:
            mod = load_module(f)
        except Exception:                     # noqa: BLE001 — an import error is itself a failure to report
            err += 1
            print(f"IMPORT-ERROR {f.relative_to(REPO)}")
            traceback.print_exc()
            continue
        suite = unittest.TestLoader().loadTestsFromModule(mod)
        buf = io.StringIO()
        t0 = time.time()
        with redirect_stdout(buf), redirect_stderr(buf):
            res = unittest.TextTestRunner(stream=buf, verbosity=2).run(suite)
        dt = time.time() - t0
        n_ok = res.testsRun - len(res.failures) - len(res.errors)
        ok += n_ok
        fail += len(res.failures)
        err += len(res.errors)
        for t, _ in res.failures + res.errors:
            failed_names.append(f"{f.relative_to(REPO)}::{t.id().split('.')[-1]}")
        status = "OK" if res.wasSuccessful() else "FAIL"
        print(f"{status:4} {f.relative_to(REPO)}  ({n_ok}/{res.testsRun} in {dt:.1f}s)")
        if not res.wasSuccessful() and not quiet:
            print(buf.getvalue()[-3000:])
    print(f"\nTOTAL ok={ok} fail={fail} err={err}  files={len(files)}")
    for n in failed_names:
        print(f"  FAILED {n}")
    return 0 if (fail == 0 and err == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
