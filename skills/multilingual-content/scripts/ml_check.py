#!/usr/bin/env python3
"""multilingual-content — verify a localized script against its source (LOCALIZE gate).

  ml_check.py --source videos/v01/script/script.json --target videos/v01-it/script/script.json
              --result videos/v01-it/localize/result.json [--glossary glossary.json] [--caps capabilities.json]
              [--min-s 20 --max-s 45]

Structure and claim ids must match beat-for-beat; numbers and protected terms must survive; the localized
narration must still fit the duration window at that language's speaking rate; the caption font must cover every
glyph (RTL scripts switch to Vazirmatn); a voice must exist for the language on this machine.
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import StageResult, emit, exit_for, fix, read_json, skills_root, stage_main, validate_artifact  # noqa: E402

WPS = {"en": 3.0, "it": 2.8, "es": 3.0, "fr": 2.9, "pt": 2.8, "de": 2.5, "hi": 2.7, "fa": 2.5, "ar": 2.4}
KOKORO = {"en", "it", "es", "fr", "pt", "hi", "ja", "zh"}
RTL = {"fa", "ar", "ur", "he", "ps"}


def nums(t: str) -> Counter:
    return Counter(re.findall(r"\d+(?:[.,]\d+)?", t))


@stage_main("LOCALIZE", "multilingual-content")
def main_cmd(a) -> int:
    src, tgt = read_json(a.source), read_json(a.target)
    sr = StageResult("LOCALIZE", "multilingual-content", tgt.get("video_id"), attempt=a.attempt)
    sr.input(a.source, "source_script"); sr.input(a.target, "target_script")
    errs = validate_artifact(tgt, "script")
    if errs:
        sr.fail("LOC.SCHEMA", "; ".join(errs[:5]), fix=fix("LOCALIZE", "repair_schema"), retryable=True)
        return exit_for(sr.finalize(a.result))
    lang = tgt["language"].split("-")[0].lower()
    sr.check("LOC.LANGUAGE_TAG", lang != src["language"].split("-")[0].lower(), "blocking", f"target language {lang}",
             fix=fix("LOCALIZE", "set_language"))
    shape = lambda s: [(b["id"], b["role"], tuple(sorted(b.get("claim_ids", [])))) for b in s["beats"]]  # noqa: E731
    sr.check("LOC.STRUCTURE", shape(src) == shape(tgt), "blocking", "beat ids, roles and claim ids must match the source",
             fix=fix("LOCALIZE", "realign_beats"))
    same = [b["id"] for b, c in zip(src["beats"], tgt["beats"]) if b["text"].strip() == c["text"].strip()]
    sr.check("LOC.TRANSLATED", not same, "blocking", f"untranslated beats {same}", fix=fix("LOCALIZE", "translate", beats=same))
    lost = [b["id"] for b, c in zip(src["beats"], tgt["beats"]) if nums(b["text"]) != nums(c["text"])]
    sr.check("LOC.NUMBERS", not lost, "major", f"numbers changed in beats {lost}", fix=fix("LOCALIZE", "fix_numbers", beats=lost))
    if a.glossary:
        keep = [t for t in read_json(a.glossary).get("do_not_translate", [])
                if any(t in b["text"] for b in src["beats"]) and not any(t in c["text"] for c in tgt["beats"])]
        sr.check("LOC.GLOSSARY", not keep, "major", f"protected terms missing: {keep}", fix=fix("LOCALIZE", "apply_glossary", terms=keep))
    text = " ".join(b["text"] for b in tgt["beats"])
    est = len(text.split()) / WPS.get(lang, 2.8) + 0.2 * (len(tgt["beats"]) - 1)
    sr.check("LOC.DURATION", a.min_s <= est <= a.max_s, "major", f"≈{est:.1f}s in {lang}", round(est, 1), [a.min_s, a.max_s],
             fix("LOCALIZE", "condense" if est > a.max_s else "expand", target_s=a.max_s * 0.9))
    rtl = lang in RTL or any(unicodedata.bidirectional(c) in ("R", "AL") for c in text)
    font_file = skills_root() / "subtitle-production" / "assets" / "fonts" / ("Vazirmatn-Bold.ttf" if rtl else "Anton-Regular.ttf")
    if font_file.exists():
        from fontTools.ttLib import TTFont
        cmap = TTFont(str(font_file)).getBestCmap()
        gaps = sorted({c for c in text if not c.isspace() and ord(c) not in cmap and unicodedata.category(c)[0] != "C"})
        sr.check("LOC.FONT_COVERAGE", not gaps, "blocking", f"{font_file.name} lacks {gaps[:12]}",
                 fix=fix("SUBTITLES", "rebuild", font="Vazirmatn"))
    caps = read_json(a.caps)["capabilities"] if a.caps else {}
    voice_ok = lang in KOKORO or caps.get("tts.elevenlabs", {}).get("available") is True
    sr.check("LOC.VOICE_AVAILABLE", voice_ok, "major",
             f"no local voice for '{lang}'" + ("" if voice_ok else "; needs ElevenLabs (run on your machine with a key)"),
             fix=fix("AUDIO", "switch_backend", backend="elevenlabs"), retryable=False)
    sr.metric("language", lang); sr.metric("rtl", rtl); sr.metric("est_duration_s", round(est, 1))
    res = sr.finalize(a.result)
    emit(res)
    return exit_for(res)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True); ap.add_argument("--target", required=True); ap.add_argument("--result", required=True)
    ap.add_argument("--glossary"); ap.add_argument("--caps")
    ap.add_argument("--min-s", type=float, default=20); ap.add_argument("--max-s", type=float, default=45)
    ap.add_argument("--attempt", type=int, default=1)
    return main_cmd(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
