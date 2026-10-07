---
name: multilingual-content
description: Localizes short-form video scripts into other languages by transcreation rather than word-for-word translation, preserving beat structure, claim ids, numbers and protected terms, keeping narration inside the duration window, and checking caption-font glyph coverage, right-to-left handling and voice availability for the target language. Use for "make Italian, Spanish or Persian versions", "translate this short", multi-language batches, or the content factory LOCALIZE stage. Not for translating websites or documents (searchfit-seo translation skills) or one-off sentence translations.
---

# Multilingual Content

**Stage:** LOCALIZE (language variants `v01-it`, `v01-fa` …) · **Error codes:** `LOC.*` · **Gate:** `scripts/ml_check.py`

## Activation
When the brief has more than one language (variants are created automatically at SELECTION) or the user asks for
another-language version of a short.

## Responsibilities
Same video, native-sounding narration: adapt idioms, units and examples; keep facts, numbers and beat ids identical
so the source visuals and claims still line up.

## Inputs → outputs
| In | Out |
|---|---|
| source `videos/<vid>/script/script.json`, optional `glossary.json` (`do_not_translate`) | `videos/<vid>-<lang>/script/script.json` (same schema, `language` set), `localize/result.json` |

## Workflow
1. Translate beat by beat; keep `id`, `role`, `claim_ids`; rewrite the hook for punch in the target language.
2. Keep numbers as digits; keep glossary terms; translate `publish` copy (titles ≤100 chars, local hashtags).
3. Check speaking length: Italian/Spanish run ~10–20 % longer — condense rather than speed up.
4. Run the gate. Variants reuse the source's rendered visuals; AUDIO/VIDEO/SUBTITLES/QA run per variant.

## Quality gate
LOC.SCHEMA, LANGUAGE_TAG, STRUCTURE, TRANSLATED, FONT_COVERAGE (blocking) · NUMBERS, GLOSSARY, DURATION,
VOICE_AVAILABLE (major). Local voices: en, it, es, fr, pt, hi, ja, zh (Kokoro). Persian/Arabic need ElevenLabs on
the user's machine; captions for them render with Vazirmatn and verified RTL shaping.

## Failure recovery
`condense` with `target_s`; numbers fixed beat by beat; no voice → keep the script, route AUDIO to
`switch_backend` (runs where the key lives) and tell the user.

## Scripts · References
`scripts/ml_check.py --source … --target … --caps … --result …` · `references/localization.md`

## Dependencies · Interactions
Font files from subtitle-production; voice list from voice-production; capabilities from content-factory.
