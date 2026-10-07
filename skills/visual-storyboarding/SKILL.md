---
name: visual-storyboarding
description: Plans and renders the visuals for vertical short videos. Maps every script beat to a scene, writes animated hand-drawn doodle scenes (the v2 default: SVG with word-synced animation cues), original SVG illustrations or image prompts, picks camera moves and transitions, renders 9:16 assets through doodle, SVG, procedural, local Stable Diffusion WebUI Forge or Pexels backends with automatic fallbacks, and retimes scenes to the real narration. Use for "storyboard this script", "make visuals or b-roll for my short", "generate scene images", or the content factory VISUAL PLAN stage. Not for standalone thumbnails, posters or UI design, and not for editing finished video.
---

# Visual Storyboarding

**Stage:** VISUAL_PLAN (+ retime at the start of VIDEO) · **Error codes:** `VIS.*` · **Gate:** `scripts/storyboard_tool.py render`

## Activation
Every factory video after SCRIPT; whenever visuals for a short are needed.

## Responsibilities
Every second has a purposeful image; a visual change every ~2–4 s; nothing infringing; captions stay readable.

## Inputs → outputs
| In | Out |
|---|---|
| `script.json`, chosen hook `visual`, `capabilities.json`, style (palette, mood) | `visual/storyboard.json`, `visual/svg/*.svg`, `visual/assets/*.png` (2160×3840), `storyboard.rendered.json`, `result.json` |

## Workflow
1. One scene per beat (or per group of short beats); scenes must cover all beats in order (`beat_ids`).
2. Pick the backend per scene from what `capabilities.json` verified:
   - `doodle` (v2 default when the brief's `visual_style` is `doodle` and `visual.doodle` is available): write one
     doodle SVG per scene with `data-*` animation cues tied to narration words, a `camera` block and a transition —
     **read `references/doodle-scene-guide.md` first**. The whole video is then animated by video-production.
   - `svg` (v1 stills): write original flat-vector art — `references/svg-scene-guide.md`.
   - `sd_forge` (user's PC with Forge `--api`): prompts per `references/image-prompting.md`.
   - `stock` (Pexels key on the user's machine), `image` (user-supplied file with license), `procedural` (fallback).
   Give each scene `fallback: ["procedural"]` so a failed backend never blocks the run.
3. Motion: zoom_in, zoom_out, pan_left/right/up/down (strength 0.08–0.15); transitions: cut (default), fade,
   slideleft, slideup, wipeleft, circleopen, dissolve (0.2–0.35 s) — vary them, don't template them.
4. Optional `overlay: {"text": "…"}` on the first scene for a title card (rendered by subtitle-production).
5. Run `render`. Retiming to real audio happens automatically in the media chain (`retime`, max shot 3.6 s).

## Quality gate
VIS.SCHEMA, BEAT_COVERAGE, ASSETS_RENDERED, NOT_BLANK (blocking) · VISUAL_VARIETY (≥1 distinct visual per ~7 s,
major) · NO_BAKED_TEXT (minor; non-doodle scenes only).
Doodle scenes add: VIS.CUE_WORDS (every `w:` cue is spoken in its scene, major), VIS.DOODLE_ACTORS (≥3 animated
elements, major), VIS.HOOK_AT_ZERO (first scene shows its subject at t=0, major), VIS.DOODLE_LINT (unknown components,
labels in the caption band, parse problems — minor). `render` also writes a preview still per doodle scene.

## Phase 3 composition gates
The render step measures every doodle scene's settled geometry (doodle_engine `composition`): layout class, main
subject + a position/scale-invariant signature, subject height, dead space. Gates VIS.LAYOUT_REPEAT, VIS.SUBJECT_REPEAT,
VIS.SUBJECT_SIZE, VIS.DEAD_SPACE, VIS.OPENING_DENSITY — rules and the seven layouts in references/doodle-scene-guide.md.
Fix actions: vary_layouts, vary_subjects, enlarge_subject, fill_space, add_entrances.

## Failure recovery
Backend error → next fallback (recorded in provenance); blank/wrong image → rerender scene; QA freeze → retime with
shorter shots (automatic); QA mismatch → redesign the named scene.
Doodle fix actions (from VISUAL_PLAN or VIDEO gates, delivered as `fix_action` + `params`):
- `repair_cues` — change `w:` cues to words actually spoken in that scene (`params.scenes`).
- `add_entrances` — at `params.at_s` (absolute seconds) the page is blank or static: add a `none` element at the
  scene start and/or entrances on the next 2–3 words (`params.scenes` for VIS.DOODLE_ACTORS).
- `redesign_scene` — rebuild the named scene (`first` = hook: subject visible at t=0, bigger, a clear joke).
- `repair_scene` — fix the lint messages (unknown `data-lib`, labels in the caption band y 1060–1360, bad SVG).

## Scripts · References
`scripts/storyboard_tool.py render|retime` · `references/doodle-scene-guide.md` (v2) · `references/svg-scene-guide.md` ·
`references/image-prompting.md`. Retime never splits doodle scenes into sub-shots (the animation provides the change).

## Dependencies
Doodle: skia-python + svgelements (doodle engine in the sibling video-production skill). SVG stills: rsvg-convert or
cairosvg. Pillow, numpy. Optional: WebUI Forge API (`CF_FORGE_URL`), `PEXELS_API_KEY`.

## Interactions
Consumes short-form-script and hook-engineering; feeds video-production; provenance records go to asset-provenance.
