> v2: for the channel's hand-drawn style use `doodle-scene-guide.md` (kind `doodle`). This guide covers v1 still `svg` scenes.

# Authoring SVG scenes (the free, always-available visual backend)
- Root: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920">` (add xmlns:xlink when using `<use>`).
- Original flat-vector art only: no text, no logos, no recognisable characters or real people.
- Fill the whole canvas (background rect/gradient first). Rendered at 2160×3840 so zoom/pan stays sharp.
- Caption band ≈ y 1050–1370: avoid tiny high-contrast detail there; big shapes behind captions are fine.
- Layers: background gradient → mid shapes → focal subject (upper half, y 300–1000) → foreground silhouette.
- 3–5 colours from the style palette; radial gradients for glow; rounded caps/joins; stroke widths ≥ 8 px.
- One clear idea per scene, readable as a thumbnail. Vary composition between consecutive scenes.
- Motion pairing: zoom_in for reveals, pan for journeys/sequences, zoom_out for conclusions.
