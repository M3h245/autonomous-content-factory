#!/usr/bin/env python3
"""Replay a finished run's brief through the real factory state machine (reproducibility + cache check).

  replay_run.py --from RUN --runs-dir DIR [--out compare.json]

What is reused: only the AUTHORED inputs of the source run (dossier, ideas, hooks, script, storyboard + svg) — the
files Claude writes in do_stage. Everything else is executed again exactly as `factory.py next` prescribes: every
gate script, `factory.py media` (AUDIO/VIDEO/SUBTITLES/QA checks), PACKAGE. Caches (TTS) are used normally.
The QA vision review is reused ONLY when the new final.mp4 is byte-identical to the reviewed one; otherwise the replay
stops at `review` (a different picture needs a fresh look). Writes a comparison of artifact hashes, cache use and
per-stage wall time between the two runs.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import read_json, sha256_file, write_json  # noqa: E402

PY = sys.executable
F = str(Path(__file__).with_name("factory.py"))
AUTHORED = {  # stage -> files (relative to the run) the do_stage author writes
    "RESEARCH": ["research/dossier.json"], "IDEATION": ["ideation/ideas.json"], "SELECTION": [],
    "HOOK": ["videos/{v}/hook/hooks.json", "videos/{v}/hook/svg"],          # v2: candidates + frame-0 SVGs
    "SCRIPT": ["videos/{v}/script/script_variants.json", "videos/{v}/script/script.json"],
    "VISUAL_PLAN": ["videos/{v}/visual/storyboard.json", "videos/{v}/visual/svg"], "PACKAGE": [],
}
COMPARE = ["videos/{v}/audio/voice.wav", "videos/{v}/audio/timing.json", "videos/{v}/visual/storyboard.rendered.json",
           "videos/{v}/video/video_nosubs.mp4", "videos/{v}/subtitles/captions.ass", "videos/{v}/subtitles/final.mp4",
           "package/{v}/captions.srt", "package/{v}/cover.jpg", "package/{v}/metadata.json", "package/{v}/CREDITS.txt",
           "package/{v}/final.mp4"]


def sh(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True)


def copy_authored(src: Path, dst: Path, stage: str, vid: str | None) -> list[str]:
    done = []
    for rel in AUTHORED.get(stage, []):
        rel = rel.format(v=vid)
        s, d = src / rel, dst / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        if not s.exists():
            continue                      # v1 runs have no script_variants.json / hook svg
        if s.is_dir():
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)
        done.append(rel)
    return done


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="src", required=True)
    ap.add_argument("--runs-dir", required=True)
    ap.add_argument("--out")
    ap.add_argument("--continue", dest="continue_run", help="resume an existing replay run")
    ap.add_argument("--max-actions", type=int, help="stop after N actions (resume with --continue)")
    a = ap.parse_args()
    src = Path(a.src).resolve()
    b = read_json(src / "state.json")["brief"]
    init = [PY, F, "init", "--topic", b["topic"], "--count", b["count"], "--languages", ",".join(b["languages"]),
            "--min-s", b["min_s"], "--max-s", b["max_s"], "--music", b.get("music", "procedural"),
            "--caption-style", b.get("caption_style", "auto"), "--visual-style", b.get("visual_style", "doodle"),
            "--runs-dir", a.runs_dir]
    if b.get("voices"):
        init += ["--voices", ",".join(f"{k}={v}" for k, v in b["voices"].items())]
    if a.continue_run:
        run = Path(a.continue_run)
        state_file = run / "replay_log.json"
        log = json.loads(state_file.read_text()) if state_file.exists() else []
    else:
        run = Path(json.loads(sh(init).stdout)["run"])
        log = []
    t0 = time.time()
    actions = 0
    for _ in range(80):
        if a.max_actions and actions >= a.max_actions:
            (run / "replay_log.json").write_text(json.dumps(log, indent=1))
            print(json.dumps({"replay_run": str(run), "paused_after_actions": actions, "resume": f"--continue {run}"}))
            return 0
        actions += 1
        d = json.loads(sh([PY, F, "next", "--run", run]).stdout)
        act = d["action"]
        if act == "do_stage":
            copied = copy_authored(src, run, d["stage"], d.get("video_id"))
            g = sh(d["gate"])
            r = sh(d["then"])
            log.append({"step": "do_stage", "stage": d["stage"], "attempt": d["attempt"], "reused_inputs": copied,
                        "gate_exit": g.returncode, "decision": json.loads(r.stdout).get("action")})
        elif act == "run_media":
            m = sh(d["cmd"] + ["--steps", "1"])
            log.append({"step": "media", "out": m.stdout.strip().splitlines()[-1][:200] if m.stdout.strip() else m.returncode})
        elif act == "review" and not (src / "videos" / d["video_id"] / "qa" / "review.json").exists():
            # Phase 1+: the review is automatic and independent — let the factory's media chain run the reviewer
            m = sh([PY, F, "media", "--run", run, "--video", d["video_id"], "--steps", "1"])
            log.append({"step": "independent_review", "out": m.stdout.strip().splitlines()[-1][:200] if m.stdout.strip() else m.returncode})
        elif act == "review":
            vid = d["video_id"]
            new, old = run / "videos" / vid / "subtitles" / "final.mp4", src / "videos" / vid / "subtitles" / "final.mp4"
            same = sha256_file(new) == sha256_file(old)
            log.append({"step": "review", "final_identical_to_reviewed": same})
            if not same:
                log.append({"step": "stop", "why": "final.mp4 differs from the reviewed video: a fresh vision review is required"})
                break
            shutil.copy2(src / "videos" / vid / "qa" / "review.json", Path(d["write"]))
            sh(d["then"])
            r = sh(d["then_record"])
            log.append({"step": "review_recorded", "decision": json.loads(r.stdout).get("action")})
        elif act == "done":
            z = sh([PY, F, "package", "--run", run, "--zip"])
            log.append({"step": "package_zip", "exit": z.returncode})
            break
        else:
            log.append({"step": act, "detail": d})
            break
    (run / "replay_log.json").write_text(json.dumps(log, indent=1))
    total = round(time.time() - t0, 1)
    sh([PY, F, "report", "--run", run])
    vids = list(read_json(run / "state.json")["videos"])
    cmp_rows = []
    for vid in vids:
        for rel in COMPARE:
            rel = rel.format(v=vid)
            x, y = src / rel, run / rel
            hx = sha256_file(x) if x.exists() else None
            hy = sha256_file(y) if y.exists() else None
            cmp_rows.append({"artifact": rel, "identical": bool(hx and hx == hy), "source": (hx or "missing")[:16],
                             "replay": (hy or "missing")[:16]})
    out = {"source_run": str(src), "replay_run": str(run), "replay_wall_s": total, "steps": log, "artifacts": cmp_rows,
           "source_report": str(src / "report" / "report.json"), "replay_report": str(run / "report" / "report.json")}
    write_json(Path(a.out) if a.out else run / "report" / "replay_compare.json", out)
    print(json.dumps({"replay_run": str(run), "wall_s": total,
                      "identical": sum(r["identical"] for r in cmp_rows), "compared": len(cmp_rows)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
