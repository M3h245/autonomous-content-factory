"""Run each unittest file in its own subprocess with a timeout, so one slow or
hanging module cannot block the whole suite. Prints a compact table.

Usage: python tools/run_tests_isolated.py [--timeout N] [pattern]
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TIMEOUT = 300
pat = None
args = sys.argv[1:]
i = 0
while i < len(args):
    if args[i] == "--timeout":
        TIMEOUT = int(args[i + 1]); i += 2
    else:
        pat = args[i]; i += 1

files = sorted(REPO.glob("skills/*/tests/test_*.py"))
if pat:
    files = [f for f in files if pat in f.as_posix()]

env = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
import os
full_env = dict(os.environ)
full_env.update(env)

rows = []
for f in files:
    rel = f.relative_to(REPO).as_posix()
    t0 = time.time()
    try:
        r = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", str(f.parent), "-p", f.name, "-v"],
            cwd=str(REPO), capture_output=True, text=True, timeout=TIMEOUT, env=full_env,
            encoding="utf-8", errors="replace",
        )
        out = (r.stderr or "") + (r.stdout or "")
        tail = out.strip().splitlines()[-1] if out.strip() else ""
        status = "PASS" if r.returncode == 0 else "FAIL"
        rows.append((status, rel, round(time.time() - t0, 1), tail[:110]))
    except subprocess.TimeoutExpired:
        rows.append(("TIMEOUT", rel, TIMEOUT, "exceeded %ds" % TIMEOUT))
    print(f"{rows[-1][0]:<8} {rows[-1][2]:>7}s  {rel}")

print()
for st in ("FAIL", "TIMEOUT"):
    n = sum(1 for r in rows if r[0] == st)
    print(f"{st}: {n}")
ok = all(r[0] == "PASS" for r in rows)
print(f"PASS: {sum(1 for r in rows if r[0] == 'PASS')} / {len(rows)}")
for r in rows:
    if r[0] != "PASS":
        print(f"  {r[0]:<8} {r[1]}  ::  {r[3]}")
sys.exit(0 if ok else 1)
