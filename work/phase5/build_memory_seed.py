"""Build the factory's starting memory (memory/dump.json) from everything Phases 0-4 produced.

  python work/phase5/build_memory_seed.py --db OUT.db --brainfreeze-run RUN_DIR [--out memory/dump.json]

- knuckles (Phase 3.5 run, packaged in Phase 4): fixtures/phase4_package_run/<run> + the shipped metadata/provenance from
  checkpoints/v2.0.0-alpha8/phase4-package-knuckles.zip
- brain freeze (Phase 4): a replay of seeds/2026-10-07-why-ice-cream-gives-you-brain-fr (work/phase4/replay.py), packaged
- tickle (v1 regression fixture), finger wrinkles (Phases 0-2) and onions (Phase 3): their run folders are not in the
  repository, so their topic, title and hook are recorded from the phase reports (brief_json names the source)
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CFDB = REPO / "skills" / "content-database" / "scripts" / "cfdb.py"
sys.path.insert(0, str(CFDB.parent))
import cfdb  # noqa: E402

HISTORICAL = [  # (run_id, topic, created_at, title, hook, source)
    ("2026-10-04-why-you-cant-tickle-yourself", "Why you can't tickle yourself", "2026-10-04", "Why you can't tickle yourself",
     "Try to tickle yourself. Go on. Nothing, right?", "fixtures/v1_regression/audio/timing.json (v1 regression video)"),
    ("2026-10-05-why-fingers-wrinkle-in-water", "Why fingers wrinkle in water", "2026-10-05", "Why fingers wrinkle in water",
     "Pruney fingers? Not water. Nerves.", "PHASE_2_REPORT.md (Phase 0-2 wrinkle runs)"),
    ("2026-10-06-why-onions-make-you-cry", "Why onions make you cry", "2026-10-06", "Why onions make you cry",
     "", "PHASE_3_REPORT.md (Phase 3 onion run)"),
]


def sh(*cmd):
    p = subprocess.run([sys.executable, str(CFDB), *map(str, cmd)], capture_output=True, text=True)
    if p.returncode:
        raise SystemExit(p.stderr)
    return p.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True); ap.add_argument("--brainfreeze-run", required=True)
    ap.add_argument("--out", default=str(REPO / "memory" / "dump.json"))
    a = ap.parse_args()
    db = Path(a.db)
    db.unlink(missing_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="memseed_"))
    knuckles = tmp / "2026-10-07-why-your-knuckles-crack"
    shutil.copytree(REPO / "fixtures" / "phase4_package_run" / knuckles.name, knuckles)
    (knuckles / "package" / "v01").mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(REPO / "checkpoints" / "v2.0.0-alpha8" / "phase4-package-knuckles.zip") as z:
        for n in ("metadata.json", "provenance.json"):
            (knuckles / "package" / "v01" / n).write_bytes(z.read(f"v01/{n}"))
    print(sh("ingest-run", "--db", db, "--run", knuckles))
    print(sh("ingest-run", "--db", db, "--run", a.brainfreeze_run))
    con = cfdb.connect(str(db))
    for rid, topic, day, title, hook, src in HISTORICAL:
        cfdb.upsert(con, "runs", {"run_id": rid, "topic": topic, "created_at": day, "status": "packaged",
                                  "brief_json": json.dumps({"topic": topic, "source": src, "note": "historical, recorded in Phase 5"})})
        cfdb.upsert(con, "videos", {"video_id": "v01", "run_id": rid, "language": "en", "title": title, "hook": hook or None,
                                    "qa_status": "passed", "created_at": day})
    con.commit()
    con.close()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    print(sh("export", "--db", db, "--out", a.out))
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
