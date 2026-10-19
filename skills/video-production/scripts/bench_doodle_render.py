#!/usr/bin/env python3
"""bench_doodle_render.py — measure doodle frame rendering throughput (v3.2.0 speed work).

Renders a synthetic doodle scene N frames, with the rough_effect cache on and off, and reports
frames/second. Pure measurement — it writes nothing outside the temp dir.

  python bench_doodle_render.py [--frames 90] [--scene path/to/scene.svg]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import doodle_engine as DE  # noqa: E402

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920">
  <g data-in="draw" data-at="0">
    <circle cx="540" cy="700" r="220" fill="p0" stroke="ink" stroke-width="10"/>
    <path d="M320,700 Q540,980 760,700" fill="none" stroke="ink" stroke-width="10"/>
    <text x="540" y="1180" font-family="marker" font-size="120" text-anchor="middle" fill="ink" data-in="write" data-at="w:1">WHY DOES THUNDER ROAR?</text>
    <path d="M180,1400 L360,1500 L540,1380 L720,1520 L900,1400" fill="none" stroke="p1" stroke-width="14" data-in="draw" data-at="+0.5"/>
  </g>
</svg>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=90)
    ap.add_argument("--scene", default=None)
    ap.add_argument("--no-cache", action="store_true", help="disable the rough_effect cache to compare")
    a = ap.parse_args()

    svg = Path(a.scene).read_text(encoding="utf-8") if a.scene else SVG
    dur = 6.0
    words = [{"w": w, "start": 0.4 + 0.35 * i, "end": 0.7 + 0.35 * i} for i, w in enumerate("WHY DOES THUNDER ROAR".split())]
    style = {"palette": ["#e8452c", "#3b82c4", "#2f9e44"], "paper": "plain"}
    sb = {"video_id": "bench", "style": style,
          "shots": [{"id": "s1", "start": 0.0, "visual": {"kind": "doodle", "svg": svg}, "camera": {"drift": "in"}}]}
    tl = DE.build_timeline(sb, {"duration_s": dur, "words": words})
    tl.duration = dur

    if a.no_cache:
        DE._PE_CACHE_MAX = 0          # every lookup misses → measures the uncached path

    n = a.frames
    t0, c0 = time.perf_counter(), time.process_time()
    for f in range(n):
        tl.frame((f / n) * dur)
    dt, cdt = time.perf_counter() - t0, time.process_time() - c0
    print(json.dumps({"frames": n, "wall_s": round(dt, 2), "cpu_s": round(cdt, 2),
                      "wall_fps": round(n / dt, 1), "cpu_fps": round(n / cdt, 1) if cdt else None,
                      "cache": not a.no_cache, "pe_cache_entries": len(DE._PE_CACHE)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
