# Authoring doodle scenes (v2 default visual style)

The channel look: intentionally low-fi, hand-drawn doodles — stick figures, rough diagrams, handwritten labels, absurd
visual metaphors — animated with professional pacing. You write plain SVG plus `data-*` cues; the doodle engine
(video-production/scripts/doodle_engine.py) turns every stroke into a wobbly marker line that boils at 10 fps, offsets
marker fills, animates each element in on a narration word, runs the camera and sound effects. Never try to draw
"nicely": clean geometry is roughened automatically. Your job is the idea, the composition and the timing.

## Scene file
```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920">
  <path d="M80,1046 C400,1038 700,1052 1000,1043" data-in="none"/>                        <!-- ground line -->
  <g id="guy" data-lib="dude" data-pose="shrug" data-face="meh" transform="translate(540 1040) scale(1.8)" data-in="none"/>
  <g data-lib="brain" data-fill="p4" data-face="smug" transform="translate(800 420)" data-in="pop" data-at="w:brain" data-loop="wiggle"/>
  <text x="540" y="230" font-family="marker" font-size="104" data-in="write" data-at="w:spoiler">SPOILER!</text>
</svg>
```
Storyboard entry: `{"id": "s1", "beat_ids": ["b1"], "visual": {"kind": "doodle", "svg_path": "svg/s1.svg"},
"camera": {...}, "transition": {"type": "whip"}}` — `motion` is not needed for doodle scenes. One scene per beat.

## Layout (1080×1920)
- Drawing zone y 120–1050. Feet/ground at y≈1040. Caption band y 1060–1360 stays clear (the gate warns on labels there).
  Below 1360 is covered by platform UI — leave it as paper.
- Characters big: dude `scale(1.4–2.0)` (≈530–760 px tall). One focal subject per scene, 2–5 supporting elements.
- 2–3 marker colours per scene from the palette (`p0`…`p4`); everything else is ink. White fill (`fill="white"`) for
  speech bubbles, screens, heads.

## Animation cues
| attribute | values |
|---|---|
| `data-in` | `draw` (stroke reveal, default) · `pop` · `write` (text, letter by letter) · `slide-left/right/up/down` · `drop` (falls + bounces) · `grow` · `spin` · `fade` · `none` (simply there) |
| `data-at` | `w:robot` (when that word is spoken in THIS scene) · `w:2013` (spoken numbers match as words) · `w:robot#2` (2nd occurrence) · `w:3` (4th word, only if no spoken word is "3") · `1.2` (s) · `+0.2` (after previous) |
| `data-loop` | `wiggle` · `bob` · `float` · `pulse` · `shake` · `tremble` · `spin` (idle motion after the entrance) |
| `data-out` + `data-out-at` | `pop` · `fade` · `slide-*` — exits, e.g. swap a sad face for a happy one on a word |
| `data-dur`, `data-origin`, `data-sfx` | duration override · pivot `center/bottom/top/"x,y"` · `pop/scribble/whoosh/boing/ding/thump/none` |
| `data-fill-style="hatch"`, `data-sketch="2"` | hatched shading · double pencil stroke |

Rules the gates enforce:
- **Hook at t=0** (VIS.HOOK_AT_ZERO, VID.FIRST_FRAME): the first scene's subject is `data-in="none"` (or `data-at="0"`).
- **Never a blank page** (VID.EMPTY_FRAMES ≤ 0.5 s): every scene has something present at its first frame — a
  `none` element, or an entrance at `0` (entrances at 0 automatically start during the incoming transition).
- **Something new every ≤3.5 s** (VID.MOTION_GAP): entrances, exits, punch-ins or shakes. Aim for one per 1–1.5 s.
- **Cue words must be spoken in that scene** (VIS.CUE_WORDS). Use the word as written in the script, case-insensitive.
- ≥3 animated elements per scene (VIS.DOODLE_ACTORS).

## The opening scene (Phase 2)
When `brief_hint.opening_brief` exists, the first scene realises it: start from its `frame0_svg` (the selected hook's
frame 0), keep the subject ≥ `subject_size_target`, keep `on_screen_text` fully visible at t=0, add the
`visual_action`, punch only on `emphasis_words`, centred. VIS.OPENING (VISUAL_PLAN) and VID.FIRST_FRAME_SUBJECT,
VID.HOOK_TEXT_T0, VID.FIRST_EVENT (VIDEO) check this deterministically. `visual_mode` is "doodle" today; the
brief's fields are mode-neutral so a later visual router can pick another mode.

## What the VIDEO gate measures (deterministic visual audit)
After every actor and camera transform, at 10 fps: labels must stay fully in frame (a cropped label is major; a
cropped NEGATION — "NOT WATER" read as "WATER" — is blocking), settled elements must stay inside the canvas (a
punch-in may crop scenery, never text), lines that sit on a shape must not run past its edge, and text must be at
least 34 px on screen. Declare intent with `data-inside="#finger"` on details that must stay inside a shape
(violations are blocking). Keep labels ≥ 60 px from the frame edges when the scene has a punch-in.

## Layouts and variety (Phase 3 — measured from geometry, not from labels)
The VISUAL_PLAN gate classifies every scene from its settled geometry and enforces variety:
| layout | geometry | typical use |
|---|---|---|
| hero | one big subject (≥28 % height, ≥2× anything else) | the claim, the reveal |
| split | two comparable subjects spread ≥30 % of the width apart | before/after, normal vs damaged, myth vs fact |
| grid | ≥3 comparable subjects across the frame | lists, steps, three studies |
| panel | one wide block (≥65 % width, aspect ≥1.5) | cross-sections, diagrams, scoreboards |
| text_led | big text (≥6 % height) as large as the main shape | numbers, verdicts ("2 : 1") |
| character | the dude is the main subject | reactions, the viewer's stand-in |
| scatter | several small elements | use sparingly |
Rules: the same layout at most twice in a row (VIS.LAYOUT_REPEAT); the same main subject (same drawing, any size or
position) at most twice in a row and in at most half of the scenes — a final loop scene may call back to the opening
subject (VIS.SUBJECT_REPEAT); main subject ≥25 % of frame height in hero/split/character/scatter scenes
(VIS.SUBJECT_SIZE); no more than 4 of the 9 content-zone cells (y 96-1050) empty (VIS.DEAD_SPACE); scene 1 needs ≥2
visual events in its first 1.5 s (VIS.OPENING_DENSITY / VID.OPENING_DENSITY). VIDEO also requires an event at least
every 3 s with a median gap ≤1.8 s (VID.PACING_CADENCE), and a loop beat must return to the opening subject
(VID.LOOP_ENDING). To avoid repeating a subject, change the viewpoint: close-up of a detail, a diagram/cross-section,
a character reacting, a metaphor object, the number itself as the hero.

## Camera (per scene, in storyboard.json)
`"camera": {"drift": "in|out|left|right|up|down|none", "punch": [{"at": "w:spoiler", "focus": "#brain", "zoom": 1.14, "hold": 0.9}], "shake": ["w:boom"]}`
Punch on the 1–2 most important words of the scene; shake for impacts/surprises only. Vary drift between scenes.

## Transitions (scene.transition.type)
`whip` · `whip-up` · `paper` (new page slides over) · `pop` · `flash` · `fade` · `cut` · `auto` (seeded variety).
Use `cut` for fast punchlines, `whip` for "meanwhile/but", `paper` for a new topic, `flash` for a reveal. Don't repeat
the same transition three times in a row.

## Drawing quality floor (v3.3.1) — read before drawing anything
The channel's drawings must look *deliberately illustrated*, never like a toddler's sketch. Rules:
- **Use a library part whenever the subject has one** (`data-lib`, catalogue in `video-production/scripts/doodle_parts.py`):
  `leg`, `ear`, `head` (profile), `hand`, `eye`, `plane`, `thermometer`, `metal_block`, `wood_block`, `ice_cube`, `mug`,
  `pan`, `flame`, `weight`, `hose` (`data-state="kinked|straight"`), `molecule`, `spoon` (`data-fill` metal or wood), `bowl`
  (`data-fill` = water colour), `bench`, `slide`, `heat_sink`, `jacket`, `cup`, `water`, `rug`, `skin_layers`, `piggy_bank`,
  `finger`, `puddle`, `speaker`, `fan`, `railing`, `plastic_block`, plus the older props and the `dude`.
  Parts are centred on (0,0); place with `transform="translate(x y) scale(s)"`. Never redraw a body part from boxes.
- **A new subject the library lacks:** draw it with real anatomy/shape cues (a foot has a heel, arch and toes; a plane has
  a fuselage, wings, tail and windows), check it at full size, and add it to `doodle_parts.py` so the next video reuses it.
- **One clear subject per scene**, big (≥25 % of the frame height), nothing overlapping it by accident; labels never sit
  on top of the subject; no shape that can be misread (a plane that looks like an arrow piercing an ear).
- **Text `y` is the vertical centre** (the engine defaults to `dominant-baseline: middle`): a label inside a box
  uses the box's centre as its `y`, or the text sits on the box's bottom edge.
- **Long-form labels pop, they are not hand-written letter by letter:** a "write" entrance on a 16:9 label is often
  caught half-written ("concret", "su", "HIGHWAy") by any frame a viewer pauses on.
- **No "≈" in marker text:** Permanent Marker draws "≈" like a "1" ("COPPER ≈ 100×" reads "COPPER 1 100×"). Write
  "COPPER: 100× WOOD" or "ABOUT 100×".
- **Long-form (16:9): the subject being explained is on screen from the start of its scene.** Bind only labels,
  arrows and the second half of a comparison to narration words; a scene that shows a title and a stick figure
  pointing at nothing for 3 s reads as missing art. Comparisons ("air vs water", "three bowls") show both sides.
- **Scene titles are present from the scene's first frame** (`data-at="0"`): a title that writes itself in at the last
  word leaves the top of the frame empty for seconds.
- **Ending card:** the channel follow card says exactly `FOLLOW BRAIN ACADEMY` and must fit inside its card.
- The independent video review scores **drawing_quality** (judge-only, threshold 4): every drawn subject must be
  recognisable at a glance. Production runs use `--review-backend subagent` so a fresh agent looks at the frames.

## Component library (`data-lib`)
- `dude` — the channel mascot. `data-pose`: stand, wave, arms-up, point, point-left, shrug, think, hips, facepalm,
  run, tickle-self, reach, sit, fall. `data-face`: happy, sad, shock, meh, smug, angry, laugh, think, ko, nervous,
  wink, love. `data-acc`: glasses, tie, tuft, cap, coat (comma list). `data-fill` colours the shirt. Origin = feet.
- `bubble` (`data-text`, `data-w`, `data-h`, `data-tail` down|down-left|down-right, `data-size`), `thought`.
- `arrow` (`data-from="x,y" data-to="x,y" data-bend`; parent coordinates — no transform needed).
- `burst` (`data-r`, `data-n`), `star`, `sparkle`, `lines` (motion lines), `sweat`, `zz`, `spiral`, `question`, `exclaim`,
  `check`, `cross`.
- Props: `brain` (+`data-face`), `robot`, `bulb`, `clock`, `heart`, `coin`, `phone`, `feather`, `knob`, `cloud`, `sun`,
  `bomb`, `trophy`, `magnifier`. Draw anything else yourself with paths — absurd metaphors are the point.

## Comedy & clarity checklist
- One visual joke or metaphor per scene, tied to the line being spoken (the brain literally holds a SPOILER sign).
- Swap expressions on the punchline (`data-out` on the old dude + `pop` of the new one at the same word).
- Labels: ≤4 words, `font-family="hand"` 56–72 px for notes, `marker` 90–150 px for big words. No paragraphs.
- No real logos, brands, real people or known characters (V.SAFE_AND_ORIGINAL).
