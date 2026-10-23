"""One-off: build the small shipped memory snapshot (P5.1) from the live dump.

The live export `memory/dump.json` is a working file and is now git-ignored. What ships is
`memory/snapshot.json`: every run, idea, video, asset and publication the channel has made, without the bulky
YouTube analytics rows (`yt_*`) and per-stage bookkeeping, which are rebuilt from the live database.
"""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
live = json.loads((root / "memory" / "dump.json").read_text(encoding="utf-8"))
keep = {k: v for k, v in live["tables"].items() if not k.startswith("yt_") and k != "stage_results"}
out = {"exported_at": live.get("exported_at"), "kind": "shipped snapshot (P5.1)",
       "note": "Working memory lives in the factory database (see memory/README.md); this is the small seed that ships.",
       "tables": keep}
p = root / "memory" / "snapshot.json"
p.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"{p} {p.stat().st_size / 1024:.0f} KB, tables: {', '.join(f'{k}={len(v)}' for k, v in keep.items())}")
