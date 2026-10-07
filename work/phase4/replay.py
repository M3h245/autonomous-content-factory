"""Same-brief replay: new run, same brief + same authored inputs, every stage gated by the factory; compare outputs."""
import json, shutil, subprocess, sys, hashlib
from pathlib import Path
CF = Path(__file__).resolve().parents[2] / "skills" / "content-factory" / "scripts" / "factory.py"
src = Path(sys.argv[1]); runs = Path(sys.argv[2])
b = json.loads((src / "run.json").read_text())
runs.mkdir(parents=True, exist_ok=True)
if (src.parent / "cta_history.json").exists():
    # same history the original run saw before it shipped (original run appended itself afterwards)
    h = json.loads((src.parent / "cta_history.json").read_text())
    h["ctas"] = [c for c in h["ctas"] if c["run"] != src.name]
    (runs / "cta_history.json").write_text(json.dumps(h))
out = subprocess.run([sys.executable, CF, "init", "--topic", b["topic"], "--count", str(b["count"]), "--languages", ",".join(b["languages"]),
                      "--platforms", ",".join(b["platforms"]), "--min-s", str(b["min_s"]), "--max-s", str(b["max_s"]), "--runs-dir", str(runs),
                      "--audience", b.get("audience") or "", "--tone", b.get("tone") or ""], capture_output=True, text=True).stdout
run = Path(json.loads(out)["run"])
AUTH = {"RESEARCH": ["research/dossier.json"], "IDEATION": ["ideation/ideas.json"], "SELECTION": [],
        "HOOK": ["videos/v01/hook/hooks.json", "videos/v01/hook/svg"], "SCRIPT": ["videos/v01/script/script_variants.json"],
        "VISUAL_PLAN": ["videos/v01/visual/storyboard.json", "videos/v01/visual/svg"],
        "PACKAGE": ["videos/v01/package/package_candidates.json", "videos/v01/package/svg", "videos/v01/package/package_judgment.json"]}
log = []
for _ in range(40):
    nx = json.loads(subprocess.run([sys.executable, CF, "next", "--run", str(run)], capture_output=True, text=True).stdout)
    if nx["action"] == "done":
        break
    if nx["action"] == "run_media":
        p = subprocess.run([sys.executable, CF, "media", "--run", str(run), "--video", "v01"], capture_output=True, text=True)
        log.append(("media", p.stdout.strip()[-200:]))
        continue
    if nx["action"] != "do_stage":
        log.append(("stop", nx)); break
    for rel in AUTH.get(nx["stage"], []):
        s, d = src / rel, run / rel
        if s.is_dir():
            shutil.copytree(s, d, dirs_exist_ok=True)
        elif s.exists():
            d.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(s, d)
    subprocess.run(nx["gate"], capture_output=True, text=True)
    r = json.loads(subprocess.run(nx["then"], capture_output=True, text=True).stdout)
    log.append((nx["stage"], r["action"]))
print(json.dumps({"run": str(run), "log": log}, indent=0, default=str))
