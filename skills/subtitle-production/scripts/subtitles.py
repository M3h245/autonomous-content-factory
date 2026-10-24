#!/usr/bin/env python3
"""subtitle-production — build word-synchronized captions and hard-burn them (SUBTITLES stage).

  subtitles.py run --timing timing.json --video video_nosubs.mp4 --out-dir DIR --result DIR/result.json
                   [--style auto|doodle|karaoke|word|clean] [--font auto|Anton|"Archivo Black"|"Permanent Marker"|Vazirmatn]
                   [--case auto|upper|keep]
                   [--max-words 3] [--y 0.63] [--overlays storyboard_timed.json] [--font-scale 1.0]

Writes captions.ass (burned), captions.srt + captions.vtt (platform upload), final.mp4.
Styles: doodle = hand-lettered ink (Permanent Marker) with a yellow marker swipe behind the spoken word and a slight
hand-placed tilt (v2 default for doodle storyboards; Latin scripts — RTL text falls back to karaoke);
karaoke = 1–3 word chunk with the spoken word highlighted; word = one word at a time;
clean = two-line sentence captions; auto = doodle when the timed storyboard has doodle scenes, else karaoke. Timing comes from timing.json, so captions are synchronized by construction.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import numpy as np
from fontTools.ttLib import TTFont
from PIL import ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import (X264_THREADS, StageResult, decode_errors, emit, exit_for, ff_filter_path, ffmpeg_bin, fix,  # noqa: E402
                       read_json, run, stage_main, validate_artifact)

W, H = 1080, 1920
SAFE_L, SAFE_R = 90, 90           # keep clear of edges; right-side UI buttons sit outside the centered caption band


def set_canvas(w: int, h: int) -> None:
    """v3.3: switch the ASS coordinate space to the brief's aspect (16:9 long-form = 1920x1080)."""
    global W, H
    W, H = int(w), int(h)

FONTS_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
FONT_FILES = {"Anton": "Anton-Regular.ttf", "Archivo Black": "ArchivoBlack-Regular.ttf", "Vazirmatn": "Vazirmatn-Bold.ttf",
              "Permanent Marker": "PermanentMarker-Regular.ttf"}
FONT_LICENSES = {"Permanent Marker": "Apache-2.0"}
RTL_LANGS = {"fa", "ar", "ur", "he", "ps"}
HIGHLIGHT = "&H0000E5FF&"         # #FFE500 (ASS is &HAABBGGRR)
STYLE_SIZES = {"karaoke": 92, "word": 124, "clean": 64, "doodle": 136}
INK = "&H001A1B1D&"               # #1D1B1A
MARKER = "&H003FD2FF&"            # #FFD23F highlighter


def ass_time(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def srt_time(t: float, sep: str = ",") -> str:
    ms = int(round(max(0.0, t) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}{sep}{ms % 1000:03d}"


def is_rtl_text(text: str) -> bool:
    return any(unicodedata.bidirectional(c) in ("R", "AL") for c in text)


def pick_font(lang: str, text: str, style: str = "karaoke") -> str:
    if lang in RTL_LANGS or is_rtl_text(text):
        return "Vazirmatn"
    return "Permanent Marker" if style == "doodle" else "Anton"


def esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def libass_em_ratio(font: str) -> float:
    """libass sizes a font so that (hhea ascent - descent) equals the ASS font size; PIL sizes the em square.
    Returns ASS size / effective em, used to measure doodle captions the way libass will actually draw them."""
    t = TTFont(str(FONTS_DIR / FONT_FILES[font]))
    return (t["hhea"].ascent - t["hhea"].descent) / t["head"].unitsPerEm


class Fitter:
    def __init__(self, font: str, size: float):
        self.f = ImageFont.truetype(str(FONTS_DIR / FONT_FILES[font]), max(1, int(round(size))))

    def width(self, text: str) -> float:
        return self.f.getlength(text)


WEAK_END = {"a", "an", "the", "of", "in", "on", "to", "and", "or", "but", "is", "are", "was", "your", "my", "its", "it's",
            "their", "our", "at", "for", "with", "from", "by", "as", "that", "this", "into", "than", "so", "if"}


def _norm(t: str) -> str:
    return re.sub(r"[^a-z']", "", t.lower().replace("’", "'"))


def chunk_words(words: list[dict], max_words: int, max_w: float, fitter: Fitter, disp) -> list[list[dict]]:
    chunks: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        if cur:
            prev = cur[-1]
            too_wide = fitter.width(" ".join(disp(x["w"]) for x in cur + [w])) > max_w
            # a comma break that would leave a chunk on screen < 0.25 s ("So," before the next word) is skipped:
            # the chunk would fail SUB.MIN_DISPLAY however many words are allowed (Phase 4 fix)
            comma_only = bool(re.search(r",$", prev["w"])) and w["start"] - cur[0]["start"] < 0.25
            brk = (len(cur) >= max_words or too_wide or (re.search(r"[.!?;:,…]$", prev["w"]) and not comma_only)
                   or w["start"] - prev["end"] > 0.35 or w["sentence"] != prev["sentence"])
            if brk:
                carry: list[dict] = []
                # v3.3.1: a word-count break never strands a function word at a chunk end
                # ("A metal spoon and a" / "Your skin is now the") — carry it into the next chunk
                soft = len(cur) >= max_words and not too_wide and not re.search(r"[.!?;:,…]$", prev["w"]) \
                    and w["start"] - prev["end"] <= 0.35 and w["sentence"] == prev["sentence"]
                while soft and len(cur) > 2 and _norm(cur[-1]["w"]) in WEAK_END:
                    carry.insert(0, cur.pop())
                chunks.append(cur)
                cur = carry
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def chunk_spans(chunks, duration: float) -> list[tuple[float, float]]:
    spans = []
    for i, c in enumerate(chunks):
        start = c[0]["start"]
        nxt = chunks[i + 1][0]["start"] if i + 1 < len(chunks) else duration
        end = min(nxt, max(c[-1]["end"] + 0.25, start + 0.35))
        spans.append((start, max(end, start + 0.05)))
    return spans


def build_ass(tm: dict, a, overlays: list[dict]) -> tuple[str, list, dict]:
    lang = tm["language"].split("-")[0].lower()
    words = tm["words"]
    all_text = " ".join(w["w"] for w in words)
    font = a.font if a.font != "auto" else pick_font(lang, all_text, a.style)
    rtl = lang in RTL_LANGS or is_rtl_text(all_text)
    upper = (a.case == "upper") or (a.case == "auto" and not rtl and font in ("Anton", "Archivo Black") and a.style != "doodle")
    # v3.3: keep the caption's visual size proportional across aspects (style sizes are authored for 1920-tall portrait)
    size = int(STYLE_SIZES[a.style] * a.font_scale * (H / 1920))
    disp = (lambda s: s.upper()) if upper else (lambda s: s)
    # v1 styles keep their original (conservative) measurement; doodle is calibrated to libass metrics + the 6 %
    # active-word scale and the ink outline
    fitter = Fitter(font, size / libass_em_ratio(font) * 1.08) if a.style == "doodle" else Fitter(font, size)
    max_w = W - SAFE_L - SAFE_R
    max_words = 1 if a.style == "word" else (8 if a.style == "clean" else a.max_words)
    chunks = chunk_words(words, max_words, max_w * (2 if a.style == "clean" else 1), fitter, disp)
    spans = chunk_spans(chunks, tm["duration_s"])
    y = int(H * a.y)
    # v3.3: keep side margins proportional across aspects (authored for 1080 wide)
    safe_l, safe_r = round(SAFE_L * W / 1080), round(SAFE_R * W / 1080)
    bold = -1 if font == "Vazirmatn" else 0
    enc = -1 if rtl else 1  # -1 = auto base direction; required for correct RTL order/joining in libass
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
            "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
            "MarginR, MarginV, Encoding\n"
            f"Style: Cap,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,{bold},0,0,0,100,100,1,0,1,"
            f"{max(4, size // 13)},{max(2, size // 30)},5,{safe_l},{safe_r},0,{enc}\n"
            f"Style: Clean,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,{bold},0,0,0,100,100,0,0,3,"
            f"14,0,2,{safe_l},{safe_r},{H - y},{enc}\n"
            f"Style: Doodle,{font},{size},{INK},{INK},&H00FFFFFF,&H64000000,0,0,0,0,100,100,1,0,1,"
            f"{max(5, size // 11)},{max(2, size // 34)},5,{safe_l},{safe_r},0,{enc}\n"
            f"Style: Marker,{font},{size},{MARKER},{MARKER},{MARKER},&HFF000000,0,0,0,0,100,100,1,0,1,"
            f"{max(10, size // 5)},0,5,{SAFE_L},{SAFE_R},0,{enc}\n"
            f"Style: Title,{font},{int(104 * a.font_scale * (H / 1920))},&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,{bold},0,0,0,100,100,1,0,1,"
            f"8,3,8,{SAFE_L},{SAFE_R},300,{enc}\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    ev = []
    pop = r"{\fscx88\fscy88\t(0,90,\fscx100\fscy100)}"
    for ci, (chunk, (cs, ce)) in enumerate(zip(chunks, spans)):
        texts = [esc(disp(w["w"])) for w in chunk]
        width = fitter.width(" ".join(texts))
        fs = rf"\fs{int(size * max_w / width)}" if width > max_w else ""  # a single over-long word
        pos = rf"{{\an5\pos({W // 2},{y}){fs}}}"
        if a.style == "clean":
            ev.append((cs, ce, f"Dialogue: 0,{ass_time(cs)},{ass_time(ce)},Clean,,0,0,0,,{' '.join(texts)}"))
            continue
        for j, w in enumerate(chunk):
            s = cs if j == 0 else w["start"]
            e = chunk[j + 1]["start"] if j + 1 < len(chunk) else ce
            if e <= s:
                continue
            if a.style == "doodle":
                ang = ((ci * 37) % 7 - 3) * 0.6
                rot = rf"\frz{ang + 3:.1f}\t(0,110,\frz{ang:.1f})" if j == 0 else rf"\frz{ang:.1f}"
                big, nrm = r"\fscx106\fscy106", r"\fscx100\fscy100"
                hide, show = r"\1a&HFF&\3a&HFF&", r"\1a&H10&\3a&H10&"
                ink = " ".join(rf"{{{big}}}{t}{{{nrm}}}" if k == j else t for k, t in enumerate(texts))
                mark = " ".join(rf"{{{show}{big}}}{t}{{{hide}{nrm}}}" if k == j else t for k, t in enumerate(texts))
                ev.append((s, e, f"Dialogue: 0,{ass_time(s)},{ass_time(e)},Marker,,0,0,0,,"
                                 rf"{{\an5\pos({W // 2 + 4},{y + 5}){fs}{rot}\blur1.5{hide}}}{mark}"))
                ev.append((s, e, f"Dialogue: 1,{ass_time(s)},{ass_time(e)},Doodle,,0,0,0,,"
                                 rf"{{\an5\pos({W // 2},{y}){fs}{rot}}}{ink}"))
                continue
            if a.style == "word":
                body = texts[j]
            else:
                body = " ".join(rf"{{\c{HIGHLIGHT}}}{t}{{\c&H00FFFFFF&}}" if k == j else t for k, t in enumerate(texts))
            ev.append((s, e, f"Dialogue: 1,{ass_time(s)},{ass_time(e)},Cap,,0,0,0,,{pos}{pop if j == 0 else ''}{body}"))
    for o in overlays:
        ev.append((o["start"], o["end"], f"Dialogue: 2,{ass_time(o['start'])},{ass_time(o['end'])},Title,,0,0,0,,"
                   rf"{{\fad(120,120)}}{esc(disp(o['text']))}"))
    ev.sort(key=lambda x: x[0])
    limit = max_w * (2 if a.style == "clean" else 1)
    too_wide = [i for i, c in enumerate(chunks)
                if len(c) > 1 and fitter.width(" ".join(disp(w["w"]) for w in c)) > limit]  # 1-word chunks are \\fs-scaled
    meta = {"font": font, "size": size, "rtl": rtl, "upper": upper, "chunks": len(chunks), "y": y,
            "too_wide": too_wide, "limit": limit}
    return head + "\n".join(e[2] for e in ev) + "\n", list(zip(chunks, spans)), meta


def build_srt_vtt(tm: dict, max_chars: int = 42) -> tuple[str, str]:
    cues, cur = [], []
    for w in tm["words"]:
        if cur and (len(" ".join(x["w"] for x in cur + [w])) > max_chars * 2 or w["sentence"] != cur[-1]["sentence"]):
            cues.append(cur); cur = []
        cur.append(w)
    if cur:
        cues.append(cur)
    srt, vtt = [], ["WEBVTT", ""]
    for i, c in enumerate(cues, 1):
        text, lines, line = " ".join(x["w"] for x in c), [], ""
        for tok in text.split():
            if line and len(line) + 1 + len(tok) > max_chars:
                lines.append(line); line = tok
            else:
                line = f"{line} {tok}".strip()
        lines.append(line)
        s, e = c[0]["start"], max(c[-1]["end"], c[0]["start"] + 0.8)
        srt += [str(i), f"{srt_time(s)} --> {srt_time(e)}", *lines, ""]
        vtt += [f"{srt_time(s, '.')} --> {srt_time(e, '.')}", *lines, ""]
    return "\n".join(srt), "\n".join(vtt)


def glyph_gaps(font: str, text: str) -> list[str]:
    cmap = TTFont(str(FONTS_DIR / FONT_FILES[font])).getBestCmap()
    return sorted({c for c in text if not c.isspace() and ord(c) not in cmap and unicodedata.category(c)[0] != "C"})


def caption_band_diff(a: Path, b: Path, t: float, y: int) -> int:
    """Pixels (quarter resolution) in the caption band that differ clearly between master and burned video at time t."""
    # v3.3.1: probe at quarter resolution of the CURRENT canvas; the fixed 270x480 grab squashed a 16:9 frame, so the
    # band row (y // 4) pointed at the middle of the picture and every long-form burn read as "nothing changed".
    qw, qh = W // 4, H // 4

    def grab(p: Path) -> np.ndarray:
        out = subprocess.run([ffmpeg_bin(), "-v", "error", "-ss", f"{t:.3f}", "-i", str(p), "-frames:v", "1",
                              "-vf", f"scale={qw}:{qh},format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
        return np.frombuffer(out, dtype=np.uint8).reshape(qh, qw).astype(float)
    band = slice(max(0, y // 4 - 40), min(qh, y // 4 + 40))
    return int((np.abs(grab(a)[band] - grab(b)[band]) > 40).sum())


@stage_main("SUBTITLES", "subtitle-production")
def cmd_run(a) -> int:
    tm = read_json(a.timing)
    out = Path(a.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    sr = StageResult("SUBTITLES", "subtitle-production", tm.get("video_id"), attempt=a.attempt)
    sr.input(a.timing, "voice_timing"); sr.input(a.video, "video_nosubs")
    errs = validate_artifact(tm, "voice_timing")
    if errs:
        sr.fail("SUB.TIMING_INVALID", "; ".join(errs[:5]), fix=fix("AUDIO", "resynthesize"), retryable=True)
        return exit_for(sr.finalize(a.result))
    overlays = []
    if a.overlays:
        for shot in read_json(a.overlays).get("shots", []):
            o = shot.get("overlay")
            if o and o.get("text") and shot["shot_id"].endswith(".1"):
                overlays.append({"start": shot["start"], "end": min(shot["end"], shot["start"] + o.get("max_s", 2.5)), "text": o["text"]})
    requested = a.style
    if a.style in ("auto", "doodle"):
        doodle_sb = False
        if a.overlays:
            doodle_sb = any((s.get("visual") or {}).get("kind") == "doodle" or (s.get("visual") or {}).get("used_kind") == "doodle"
                            for s in read_json(a.overlays).get("shots", []))
        rtl_text = tm["language"].split("-")[0].lower() in RTL_LANGS or is_rtl_text(" ".join(w["w"] for w in tm["words"]))
        a.style = "doodle" if (requested == "doodle" or doodle_sb) and not rtl_text else "karaoke"
    # v3.3: 16:9 long-form captions live at the frame's own ASS space and sit lower than a Short's (no Shorts
    # UI band to clear). `--y auto` picks the band per aspect; an explicit --y still wins.
    if a.aspect == "wide":
        set_canvas(1920, 1080)
        if a.y is None:
            a.y = 0.84      # v3.3.1: 0.86 sat under the YouTube player's control bar on hover
        if a.max_words is None:      # v3.3.1: 2-3-word flashes broke phrases on 8-minute videos ("ONE OF THE")
            a.max_words = 5
    else:
        set_canvas(1080, 1920)
        if a.y is None:
            a.y = 0.63
    if a.max_words is None:
        a.max_words = 3
    ass, chunks, meta = build_ass(tm, a, overlays)
    (out / "captions.ass").write_text(ass, encoding="utf-8")
    srt, vtt = build_srt_vtt(tm)
    (out / "captions.srt").write_text(srt, encoding="utf-8")
    (out / "captions.vtt").write_text(vtt, encoding="utf-8")
    final = out / "final.mp4"
    vf = f"ass=filename={ff_filter_path(out / 'captions.ass')}:fontsdir={ff_filter_path(FONTS_DIR)}:shaping=complex"
    run([ffmpeg_bin(), "-y", "-v", "error", "-i", a.video, "-vf", vf, "-c:v", "libx264", "-preset", a.preset, "-crf", str(a.crf), "-threads", X264_THREADS,
         "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", final])

    # ---------------- gate
    bad = decode_errors(final)
    sr.check("SUB.DECODE_OK", not bad, "blocking", "; ".join(bad) or "every packet of final.mp4 decodes", len(bad), 0,
             fix("SUBTITLES", "reburn"))
    words = tm["words"]
    flat = [w for c, _ in chunks for w in c]
    sr.check("SUB.COVERAGE", [w["w"] for w in flat] == [w["w"] for w in words], "blocking",
             f"{len(flat)}/{len(words)} words captioned in order", fix=fix("SUBTITLES", "rebuild"))
    spans = [s for _, s in chunks]
    overlaps = [i for i in range(len(spans) - 1) if spans[i][1] > spans[i + 1][0] + 1e-3]
    sr.check("SUB.NO_OVERLAP", not overlaps, "blocking", f"overlapping chunks at {overlaps[:5]}", fix=fix("SUBTITLES", "rebuild"))
    short = [i for i, (s, e) in enumerate(spans) if e - s < 0.25]
    sr.check("SUB.MIN_DISPLAY", not short, "major", f"chunks shorter than 0.25 s: {short[:8]}", len(short), 0,
             fix("SUBTITLES", "rebuild", max_words=a.max_words + 1))
    desync = [i for i, (c, (s, _)) in enumerate(chunks) if abs(c[0]["start"] - s) > 0.001]
    sr.check("SUB.SYNC", not desync, "blocking", "each caption appears exactly when its first word is spoken")
    sr.check("SUB.FITS_SAFE_AREA", not meta["too_wide"], "blocking",
             f"chunks wider than the {meta['limit']}px safe width: {meta['too_wide'][:8]}",
             fix=fix("SUBTITLES", "rebuild", font_scale=round(a.font_scale * 0.9, 2)))
    gaps = glyph_gaps(meta["font"], " ".join(w["w"] for w in words) + " ".join(o["text"] for o in overlays))
    sr.check("SUB.GLYPH_COVERAGE", not gaps, "blocking", f"font {meta['font']} lacks glyphs {gaps[:10]}", gaps, [],
             fix("SUBTITLES", "rebuild", font="Vazirmatn"))
    probe_t = [(s + e) / 2 for c, (s, e) in chunks[:: max(1, len(chunks) // 3)][:3]]
    diffs = [caption_band_diff(Path(a.video), final, t, meta["y"]) for t in probe_t]
    sr.check("SUB.BURNED_IN", min(diffs) >= 40, "blocking", f"changed caption-band pixels per probe {diffs}",
             diffs, ">=40 per probe", fix("SUBTITLES", "reburn"))
    sr.metric("chunks", meta["chunks"]); sr.metric("font", meta["font"]); sr.metric("rtl", meta["rtl"])
    sr.metric("style", a.style); sr.metric("style_requested", requested); sr.metric("overlays", len(overlays))
    for name, role, mt in [("captions.ass", "captions_ass", "text/x-ass"), ("captions.srt", "captions_srt", "application/x-subrip"),
                           ("captions.vtt", "captions_vtt", "text/vtt"), ("final.mp4", "final_video", "video/mp4")]:
        sr.output(out / name, role, mt)
    sr.provenance({"role": "font", "path": str(FONTS_DIR / FONT_FILES[meta["font"]]), "source": "Google Fonts (github.com/google/fonts)",
                   "license": FONT_LICENSES.get(meta["font"], "OFL-1.1"), "realistic": False})
    res = sr.finalize(a.result)
    emit(res)
    return exit_for(res)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--timing", required=True); r.add_argument("--video", required=True)
    r.add_argument("--out-dir", required=True); r.add_argument("--result", required=True)
    r.add_argument("--style", choices=["auto", "doodle", "karaoke", "word", "clean"], default="auto")
    r.add_argument("--font", default="auto", choices=["auto", *FONT_FILES])
    r.add_argument("--case", choices=["auto", "upper", "keep"], default="auto")
    r.add_argument("--max-words", type=int, default=None,
                   help="words per caption chunk (default: 3 on 9:16 Shorts, 5 on 16:9 long-form)")
    r.add_argument("--y", type=float, default=None, help="caption centre as a fraction of height (default: 0.63 portrait / 0.86 wide)")
    r.add_argument("--font-scale", type=float, default=1.0)
    r.add_argument("--aspect", default="vertical", choices=["vertical", "wide"],
                   help="ASS coordinate space: vertical = 1080x1920, wide (16:9 long-form) = 1920x1080")
    r.add_argument("--overlays", help="timed storyboard; shots with overlay.text become title cards")
    r.add_argument("--crf", type=int, default=19); r.add_argument("--preset", default="medium")
    r.add_argument("--attempt", type=int, default=1)
    a = ap.parse_args()
    return cmd_run(a)


if __name__ == "__main__":
    sys.exit(main())
