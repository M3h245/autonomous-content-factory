---
name: asset-provenance
description: Tracks where every asset in a video came from and whether it may be used. Hashes voice, visuals, music and fonts, enforces a license allowlist and attribution, requires consent for voice clones, decides per-platform AI labels (YouTube altered or synthetic content, TikTok AI-generated, Instagram AI info), cites research sources, writes provenance.json and CREDITS.txt and embeds provenance metadata into the deliverable. Use for "can I use this image or music", "do I need to label this as AI", "credits for my video", or the content factory FINAL PACKAGE stage.
---

# Asset Provenance

**Stage:** FINAL PACKAGE (called by `package_run.py`) · **Error codes:** `PROV.*` · **Script:** `scripts/provenance.py build`

## Activation
Every packaged video; any licensing, credit or AI-disclosure question about factory output.

## Responsibilities
No asset ships without a known license, required credit and an explicit labeling decision.

## Inputs → outputs
| In | Out |
|---|---|
| `provenance` records inside every stage `result.json`, final render, dossier + script (sources), optional `licenses.json` | `package/<vid>/provenance.json`, `CREDITS.txt`, `final.mp4` with metadata (streams copied), `provenance_result.json` |

## Workflow
1. `provenance.py build --video-dir … --final … --out-dir … --result … --dossier … --script … [--license-map licenses.json]`
2. Allowlist: self-generated, OFL-1.1, CC0-1.0, Apache-2.0, MIT, Pexels License, Pixabay Content License, user-owned,
   CC-BY-4.0 (attribution required), commercial-licensed (needs `license_ref`). SD checkpoints need
   `licenses.json` `{"models": {"checkpoint_name": "license"}}` confirmed by a human.
3. Labels (policy verified 2026-10-03, re-verify — see `references/licenses-and-disclosure.md`): YouTube label for
   realistic synthetic visuals or AI music; TikTok/Instagram label for realistic synthetic visuals or voices
   (conservative); a plain description line always states AI narration and visual method.

## Final-media metadata policy (Phase 3.5; tightened in v3.0.1)
The deliverable is a clean copy (scripts/media_clean.py) that carries only what playback technically needs.
- MP4: the ftyp brands (major_brand, minor_version, compatible_brands) and the mandatory per-track fields (language
  `und`, the zero vendor field), all times zero. No udta/meta/ilst/uuid/XMP box (neutralised in place as all-zero
  `free` boxes), empty track-handler names, no H.264 SEI user data (x264 version string).
- JPEG: SOI, the JFIF APP0 header and the coding segments (an ICC profile is kept if one exists). No EXIF, XMP, IPTC,
  C2PA/JUMBF, COM or other APPn segment.
- **No embedded AI-label or AI-disclosure metadata** (XMP/IPTC DigitalSourceType, C2PA manifests, "AI-generated" or
  synthetic tags); the audit fails a file that carries any.
- Streams and pixels are not re-encoded (stream MD5 and decoded pixels unchanged). render_video encodes AAC with +bitexact so no
encoder string sits inside the audio. Provenance, model and run information stay in provenance.json and reports.
PACKAGE blocks on PKG.MEDIA_METADATA_CLEAN (audit of every publishable .mp4/.jpg/.png), PKG.FINAL_DECODES and
PKG.DISCLOSURE (platform AI labels present in metadata.json; since v3.0.2 no tool line is added to the YouTube description).
Disclosure is never carried by the media file: the owner sets each platform's AI label by hand at upload from
metadata.json / PUBLISHING_PACKAGE.md, and the package gate still requires those labels.

## Quality gate
PROV.ASSETS_RECORDED, LICENSES_KNOWN, ATTRIBUTION, CONSENT, HASH_VERIFIED (blocking) · MODEL_LICENSE (major, human).

## Failure recovery
Unknown license → replace the asset (VISUAL_PLAN) or record proof; missing credit → add attribution; never guess a license.

## Scripts · References
`scripts/provenance.py` · `references/licenses-and-disclosure.md`

## Dependencies · Interactions
ffmpeg (metadata remux), hashlib. Reads every stage's records; content-factory packaging consumes its outputs;
content-database stores asset hashes.
