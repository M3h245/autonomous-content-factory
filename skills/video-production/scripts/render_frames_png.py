#!/usr/bin/env python3
"""render_frames_png.py — render fixed frames of a fixed doodle timeline and save them as real PNG
files (via Skia's encoder), so an independent decoder (PIL) can compare them. This is the authoritative
correctness check for a rendering change.

  python render_frames_png.py --outdir DIR --mode old|new
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import skia

sys.path.insert(0, str(Path(__file__).resolve().parent))
import doodle_engine as DE  # noqa: E402

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920">
  <g data-in="draw" data-at="0">
    <circle cx="540" cy="700" r="220" fill="p0" stroke="ink" stroke-width="10"/>
    <text x="540" y="1180" font-family="marker" font-size="120" text-anchor="middle" fill="ink" data-in="write" data-at="w:1">THUNDER</text>
    <path d="M180,1400 L360,1500 L540,1380" fill="none" stroke="p1" stroke-width="14" data-in="draw" data-at="+0.5"/>
    <rect x="700" y="400" width="200" height="200" fill="p1" data-in="pop" data-at="+0.8" data-loop="wiggle"/>
  </g>
</svg>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--mode", choices=["old", "new", "oldsurf", "oldpaper"], default="new")
    a = ap.parse_args()

    if a.mode in ("old", "oldsurf"):
        DE._surface = lambda: skia.Surface.MakeRaster(
            skia.ImageInfo.Make(DE.W, DE.H, skia.kRGBA_8888_ColorType, skia.kPremul_AlphaType))
    if a.mode in ("old", "oldpaper"):
        DE.raster_image = lambda rgba, name="img": skia.Image.fromarray(
            rgba, colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kPremul_AlphaType)

    style = {"palette": ["#e8452c", "#3b82c4", "#2f9e44"], "paper": "plain"}
    sb = {"video_id": "correctness", "style": style,
          "shots": [{"id": "s1", "start": 0.0, "visual": {"kind": "doodle", "svg": SVG}, "camera": {"drift": "in"}},
                    {"id": "s2", "start": 2.2, "visual": {"kind": "doodle", "svg": SVG}, "camera": {"drift": "right"}}]}
    words = [{"w": "THUNDER", "start": 0.5, "end": 0.9}]
    tl = DE.build_timeline(sb, {"duration_s": 4.4, "words": words})
    tl.duration = 4.4

    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(range(0, 132, 5)):
        img = tl.frame(f / 30.0).makeImageSnapshot()
        img.save(str(out / f"frame_{i:03d}.png"), skia.kPNG)
    print(f"mode={a.mode} wrote {len(range(0, 132, 5))} frames to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
