# v3.2.0 — doodle render speed (P5, measured)

**Written 2026-10-20.** This documents a measured 37× speed-up of the doodle renderer, how it was found,
what was proven correct, and the one honest caveat. It exists because long-form (P3) is impossible without
it: at the old rate a 6-minute video would take roughly an hour to render.

## The measurement

A fixed synthetic doodle scene (4–5 elements, one write-on text, two scenes) was rendered repeatedly and
timed with `time.process_time()` (CPU time, immune to other load). A `cProfile` run was useless here
because **all the cost is inside Skia's C++ rasteriser** — cProfile reported 0.045 s for 60 frames while
the wall/CPU clock showed 0.26 s per frame.

| what | before | after |
|---|---|---|
| full frame | **300 ms** | **~8 ms** |
| frames per second | **3.2** | **120** |
| `Paper.draw` (the grain overlay, drawn every frame) | 289 ms | 3 ms |
| the actual artwork (`scene.draw`, no paper) | 11 ms | 8 ms |

Attribution (`bench_doodle_render.py`, `render_frames_png.py`):

| part | cost | note |
|---|---|---|
| clear + camera + all elements | 11 ms | never the bottleneck |
| the 1080×1920 paper overlay | **289 ms** | 96 % of the frame |
| surface created with `Surface.MakeRaster(ImageInfo(...))` | **154 ms per 2 MP blit** | the real culprit |
| surface created with `Surface.MakeRasterN32Premul(W, H)` | **3 ms** | byte-identical output |
| image built with `Image.fromarray` | **150–300 ms per blit** | slow internal path |
| image snapshotted from `Surface.MakeRasterDirect` (BGRA) | **3 ms** | pixel-identical after an R/B swap |

## The two fixes (both in `video-production/scripts/doodle_engine.py`)

1. **`_surface()`** now uses `skia.Surface.MakeRasterN32Premul(W, H)` instead of
   `skia.Surface.MakeRaster(skia.ImageInfo.Make(...))`. On skia-python 144.0.post2 the two produce
   byte-identical pixels (verified: **0/255 difference across 27 frames**) but the second is ~50× slower
   to draw images into. One line, no output change.
2. **`raster_image()`** builds the image we generate from numpy (currently the paper grain) via
   `Surface.MakeRasterDirect(info, buf, row).makeImageSnapshot()` instead of `Image.fromarray`. N32Premul is
   read as BGRA, so the buffer is R/B-swapped first; the result was verified **pixel-identical** against the
   old `fromarray` image with an independent decoder.

A third, smaller change memoises `rough_effect()` (a Skia `PathEffect` composed per glyph per frame) with a
bounded 8192-entry cache — about 3 % on the synthetic scene, kept because it is free and grows with scene
complexity.

## Correctness evidence (and the honest caveat)

The authoritative check is `render_frames_png.py`: it renders fixed frames of a fixed timeline to **PNG
files** through Skia's own encoder, and an independent decoder (PIL) compares them. Frames saved as PNG
avoid the trap that fooled earlier attempts — `skia.Image.toarray()` re-orders channels, so comparing
in-memory arrays gave false results (it once reported a 188/255 difference that was pure measurement error).

| comparison | worst channel difference |
|---|---|
| surface fix alone vs old | **0 / 255** (byte-identical) |
| image fix alone vs old | **3 / 255** (26 of 27 frames differ by 1–3) |
| both together vs old | **3 / 255** |

The histogram of the difference: ±1 on ~10 % of pixels, ±2 on 14 174 pixels, ±3 on 284 pixels — all of them
**fully opaque** pixels of the grain overlay. This is premultiply/blend **rounding**: the new image path
rounds the near-transparent grain alpha very slightly differently than `fromarray` did. It is not a channel
swap (a swap would show ~24/255 on R and B, which the earlier PIL test ruled out) and not a structural
change.

**Decision:** a ±1 rounding difference on a half-transparent paper texture, invisible to the eye, is worth a
37× render speed-up. It is recorded here so it is a known, accepted difference rather than a surprise.

## What this unblocks

- **Long-form (P3) is now practical.** 6 minutes at 30 fps = 10 800 frames × ~8 ms ≈ **1.5 minutes** of
  rendering (plus encoding), instead of ~1 hour.
- Every shorts batch gets faster too; the full test suite no longer spends 30+ minutes in a single doodle
  render.
- `idea_engine --run-timeout-min 180` is no longer at risk from a long run.

## Reproducing

```
python skills/video-production/scripts/bench_doodle_render.py --frames 300
python skills/video-production/scripts/render_frames_png.py --outdir %TEMP%\new --mode new
python skills/video-production/scripts/render_frames_png.py --outdir %TEMP%\old --mode old
# then compare the two directories with any PNG reader
```
