"""Seed of a finished run = its brief + every authored input in its final form (the files work/phase4/replay.py copies
into a new run). Generated files (scores, renders, reports) are not seeds: the replay must regenerate them.

  python work/phase5/make_seed.py RUN seeds/<run>
"""
import json
import shutil
import sys
from pathlib import Path

run, dest = Path(sys.argv[1]), Path(sys.argv[2])
st = json.loads((run / "state.json").read_text())
FILES = ["research/dossier.json", "ideation/ideas.json", "videos/v01/hook/hooks.json", "videos/v01/script/script_variants.json",
         "videos/v01/visual/storyboard.json", "videos/v01/package/package_candidates.json", "videos/v01/package/package_judgment.json"]
if dest.exists():
    shutil.rmtree(dest)
for rel in FILES:
    if (run / rel).exists():
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(run / rel, dest / rel)
# only the SVGs the final inputs reference (earlier rounds may have left others behind)
hooks = json.loads((run / "videos/v01/hook/hooks.json").read_text())["candidates"]
sb = json.loads((run / "videos/v01/visual/storyboard.json").read_text())["scenes"]
pk = json.loads((run / "videos/v01/package/package_candidates.json").read_text())["candidates"]
for base, rels in (("videos/v01/hook", [c["first_frame_svg"] for c in hooks]),
                   ("videos/v01/visual", [s["visual"]["svg_path"] for s in sb if s["visual"].get("svg_path")]),
                   ("videos/v01/package", [c["thumbnail"]["svg"] for c in pk])):
    for rel in rels:
        (dest / base / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(run / base / rel, dest / base / rel)
b = st["brief"]
(dest / "run.json").write_text(json.dumps({"run_id": run.name, **{k: v for k, v in b.items() if k != "memory"}}, indent=2, ensure_ascii=False))
print(json.dumps({"seed": str(dest), "files": sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file())}, indent=0))
