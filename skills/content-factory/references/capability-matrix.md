# Capability matrix (verified 2026-10-03 in the claude.ai sandbox; re-run `doctor.py` on every machine)

Sandbox facts: Ubuntu 24.04, 1 vCPU, 3.9 GB RAM, no GPU, Python 3.12, ffmpeg 6.1.1 (libass, FriBidi, HarfBuzz, x264),
tesseract (eng), rsvg-convert. Network allowlist: package registries and GitHub only — every media/platform API
tested (ElevenLabs, OpenAI, YouTube Data/Analytics, Pexels, Pixabay, Hugging Face, TikTok, Graph, Reddit, Google Trends)
returned `403 host_not_allowed`.

| Capability | Available now? | Tool | Skill | External service | Credential? | Autonomous? | Human action | Evidence |
|---|---|---|---|---|---|---|---|---|
| Web research with citations | Yes | web_search, web_fetch | content-research | — | No | Yes (chat) | — | searches + dossier gate passed |
| Quantitative trend data | No | vidIQ connector (directory) · YouTube Data API script · Google Trends CSV | trend-intelligence | vidIQ / YouTube Data API | Yes | After connecting | Connect or export CSV | registry search; egress 403 |
| Qualitative trend signals | Yes | web_search + trend_score.py | trend-intelligence | — | No | Yes | — | advisory gate run |
| Ideas, selection, hooks, scripts | Yes | Claude + gate scripts | strategy / hook / script | — | No | Yes | — | all gates passed in test run |
| Localization (gate) | Yes | Claude + ml_check.py | multilingual-content | — | No | Yes | — | script written; Italian TTS verified |
| Narration + exact word timing (en, it, es, fr, pt, hi, ja, zh) | Yes | kokoro-onnx 0.6.1 fp32 | voice-production | GitHub model download | No | Yes | — | 86/86 words timed, 1.25× real time |
| Persian/Arabic narration | No | ElevenLabs adapter (not live-tested) | voice-production | ElevenLabs | API key | On user's PC | Key + local run | egress 403 |
| Animated doodle scenes (v2 default) | Yes | skia-python + svgelements (doodle_engine.py) | visual-storyboarding → video-production | — | No | Yes | — | 7-scene, 30.8 s demo: all gates + vision review passed (2026-10-04) |
| Vector scene illustration (v1 stills) | Yes | rsvg-convert or cairosvg | visual-storyboarding | — | No | Yes | — | 6 scenes rendered, reviewed |
| Diffusion images | Not in sandbox | WebUI Forge adapter (not live-tested) | visual-storyboarding | user's local Forge | No | On user's PC | Start Forge with --api | localhost only |
| Stock photos | No | Pexels adapter (not live-tested) | visual-storyboarding | Pexels | API key | On user's PC | Free key | egress 403 |
| Generative AI video | No | — | (documented only) | paid video-gen APIs | Yes | No | Yes | not implemented |
| Assembly, motion, transitions, loudness | Yes | ffmpeg | video-production | — | No | Yes | — | −14.1 LUFS, −1.3 dBFS |
| Music bed + sound effects | Yes (procedural, seeded per video) | numpy (audio_design.py) | video-production | licensed library optional | No | Yes | License string for own tracks | 48 SFX placed, music ducked, −14.1 LUFS |
| Word-by-word burned captions (Latin) | Yes | libass (doodle: Permanent Marker + marker swipe; karaoke: Anton) | subtitle-production | — | No | Yes | — | burn-in proof + full decode + OCR 100 % |
| Persian/RTL burned captions | Yes | libass + Vazirmatn | subtitle-production | — | No | Yes | — | visual check after fix |
| Automatic QA + OCR (English) | Yes | ffmpeg, tesseract | video-quality-assurance | — | No | Yes | — | all checks passed |
| Vision review | Yes | image viewing | video-quality-assurance | — | No | Yes | — | contact sheet reviewed |
| Regeneration + escalation | Yes | factory.py | content-factory | — | No | Yes | Resolve escalations | 2 reruns → escalate → reset → pass |
| Provenance, licenses, AI-label decision | Yes | provenance.py | asset-provenance | — | No | Yes | Confirm model licenses; set toggles at upload | manifest + credits built |
| Final package | Yes | package_run.py | content-factory | — | No | Yes | — | zip + checksums |
| Content DB (session) | Yes | sqlite3 | content-database | — | No | Yes | — | ingest/similar/export ran |
| Cross-session memory | Partly | dump.json · Drive connector (small text) · Artifact db (not provisioned) | content-database | — | No | With re-upload | Re-upload dump.json | export/import ran |
| Analytics from CSV exports | Yes | pandas | content-analytics | — | No | Yes | Export + upload CSV | synthetic fixture run |
| Analytics via API/connector | No | Supermetrics connector (directory) · YouTube Analytics API | content-analytics | Supermetrics / Google | OAuth | After connecting | Connect | registry search |
| Publishing | No, by design | Chrome extension (0 browsers connected, ≤10 MB per upload) | — | YouTube / TikTok / Instagram | Login / OAuth | Never | Upload and approve each post | tool listing |
| Scheduled headless runs | Not in claude.ai | Claude Code `claude -p` (docs verified, not executed here) | automation-engineering | Anthropic API | Key or login | On user's machine | Install + schedule | official docs |
| Installing skills | Not by Claude | .skill files (Save skill) · install_skills.py | all | — | — | — | Click Save skill | skill-creator packager |
