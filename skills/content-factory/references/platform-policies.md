# Platform targets and policies (checked 2026-10-03 — re-verify before relying on them; not legal advice)

## Technical targets used by the gates
1080×1920, 30 fps, H.264 High yuv420p, AAC 48 kHz stereo, faststart; integrated loudness −14 LUFS ±1.5, true peak ≤ −1 dBTP;
captions centred at 63 % height with 90 px side margins (clear of bottom UI and right-side buttons); hard ceiling 180 s.

## Monetization: YouTube "inauthentic content" (since 15 July 2025)
YouTube renamed "repetitious content" to "inauthentic content": mass-produced, templated, low-variation videos are
not eligible for the Partner Program, and reviewers look at the channel as a whole (theme, most-viewed, newest uploads,
metadata). Factory consequences: every idea carries a concrete value-add; batches must vary format and angle;
novelty is checked against history; templates (visual style, structure, voice) should rotate across batches.

## AI labels (realism test)
- YouTube: label realistic altered/synthetic depictions (and AI-generated music); an AI voiceover alone does not
  require the label; stylized/animated visuals do not.
- TikTok: label AI-generated or significantly edited realistic people, scenes, images or audio (the factory labels
  realistic synthetic voices conservatively).
- Instagram/Meta: "AI info" for photorealistic images or realistic-sounding synthetic audio.
- EU AI Act transparency duties (Art. 50) apply from 2 August 2026. The factory keeps the description disclosure line,
  and the platform labels in metadata.json for the owner to set at upload. Owner decision (v3.0.1): the media files
  carry **no** embedded AI-label or machine-readable AI marking (none had been embedded since Phase 3.5; v3.0.1
  makes that a tested guarantee). Whether Art. 50(2) machine-readable marking applies to this channel as a provider is
  the owner's call; if it does, the marking has to be added outside the factory.
