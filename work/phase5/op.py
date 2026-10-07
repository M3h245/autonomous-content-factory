"""Operator step for Phase 5 fresh runs: every gate runs only through the factory loop (next → gate → record), so every
attempt is counted in the run's events (Phase 4 had uncounted gate runs while revising).

  python work/phase5/op.py step  RUN     # next; if do_stage: run its gate, then record; print a compact summary
  python work/phase5/op.py media RUN     # run the media chain for v01 (AUDIO → VIDEO → SUBTITLES → QA + review)
  python work/phase5/op.py peek  RUN     # what `next` would hand out (does not issue it)
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
F = REPO / "skills" / "content-factory" / "scripts" / "factory.py"
sys.path.insert(0, str(F.parent))


def summary(res_path: Path) -> dict:
    r = json.loads(res_path.read_text())
    return {"stage": r["stage"], "status": r["status"], "attempt": r.get("attempt"),
            "failed": [(e["code"], e["severity"], e["message"][:400]) for e in r["errors"]],
            "metrics": {k: v for k, v in r.get("metrics", {}).items() if k in ("selected", "scores", "duration_s", "candidates", "tiers")}}


def main():
    cmd, run = sys.argv[1], Path(sys.argv[2]).resolve()
    if cmd == "peek":
        import factory
        print(json.dumps(factory.next_action(run, factory.load(run)), indent=1)[:3000])
        return
    if cmd == "media":
        p = subprocess.run([sys.executable, str(F), "media", "--run", str(run), "--video", sys.argv[3] if len(sys.argv) > 3 else "v01"],
                           capture_output=True, text=True)
        print(p.stdout[-4000:])
        print("\n".join(l for l in p.stderr.splitlines() if l.startswith(("[", "{")))[-6000:])
        return
    nx = json.loads(subprocess.run([sys.executable, str(F), "next", "--run", str(run)], capture_output=True, text=True).stdout)
    if nx["action"] != "do_stage":
        print(json.dumps(nx, indent=1)[:3000])
        return
    g = subprocess.run(nx["gate"], capture_output=True, text=True)
    res = Path(nx["then"][-1])
    out = summary(res) if res.exists() else {"gate_exit": g.returncode, "stderr": g.stderr[-1500:]}
    rec = subprocess.run(nx["then"], capture_output=True, text=True)
    try:
        dec = json.loads(rec.stdout)
    except ValueError:
        dec = {"record_error": (rec.stdout + rec.stderr)[-1500:]}
    print(json.dumps({"stage": nx["stage"], "video": nx["video_id"], "attempt": nx["attempt"], "gate_exit": g.returncode,
                      "result": out, "decision": {k: dec.get(k) for k in ("action", "stage", "fix_action", "params", "because", "why",
                                                                          "errors", "record_error") if dec.get(k) is not None}},
                     indent=1, ensure_ascii=False)[:8000])


if __name__ == "__main__":
    main()
