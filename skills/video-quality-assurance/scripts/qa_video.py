#!/usr/bin/env python3
"""video-quality-assurance — independent QA of the finished, caption-burned video (QA stage).

  qa_video.py check    --video final.mp4 --timing timing.json --captions captions.ass --out-dir DIR
                       --result DIR/result.json [--nosubs video_nosubs.mp4] [--min-s 15 --max-s 60]
                       [--lufs -14] [--ocr auto|on|off]
  qa_video.py finalize --out-dir DIR --review DIR/review.json --result DIR/result.json

`check` runs deterministic probes on the delivered file. If they pass it renders contact_sheet.jpg and
hook.jpg and writes review_template.json; status `pending_review` (exit 3) means the agent must LOOK at the
images and write review.json. `finalize` merges that vision review into the gate. Every failed check
carries a fix_route so the orchestrator regenerates the responsible stage instead of shipping bad output.
"""
from __future__ import annotations

import argparse
import difflib
import re
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import (StageResult, decode_errors, emit, exit_for, ffmpeg_bin, ffprobe, fix, read_json,  # noqa: E402
                       run, stage_main, write_json)

W, H, PLATFORM_MAX_S = 1080, 1920, 180.0
# v3.3: the expected container spec depends on the brief's aspect. 9:16 shorts are 1080x1920; 16:9 long-form is
# 1920x1080 (docs/v3.3/RESEARCH-PACKAGING.md §1.2). --aspect switches the pair QA compares against.

def set_canvas(w: int, h: int) -> None:
    global W, H
    W, H = int(w), int(h)
TESS_LANG = {"en": "eng", "it": "ita", "es": "spa", "fr": "fra", "pt": "por", "de": "deu", "fa": "fas", "ar": "ara"}
REVIEW_ITEMS = [
    ("V.CAPTIONS_READABLE", "Are captions legible against every background in the contact sheet?", "blocking",
     fix("SUBTITLES", "rebuild", font_scale=1.1)),
    ("V.NO_COLLISION", "Do captions avoid covering the key subject or any baked-in text?", "major",
     fix("SUBTITLES", "rebuild", y=0.70)),
    ("V.HOOK_FRAME", "Is the first frame (hook.jpg) striking and clearly about the topic?", "major",
     fix("VISUAL_PLAN", "redesign_scene", scene="first")),
    ("V.VISUALS_MATCH", "Does each visual match what the narration says at that moment?", "major",
     fix("VISUAL_PLAN", "redesign_scene")),
    ("V.NO_ARTIFACTS", "No broken renders, distorted shapes, garbled text, watermarks or glitches?", "blocking",
     fix("VISUAL_PLAN", "rerender")),
    ("V.SAFE_AND_ORIGINAL", "Nothing misleading, unsafe, or infringing (no real logos, characters, people)?", "blocking",
     fix("VISUAL_PLAN", "redesign_scene")),
    ("V.CLAIMS_SUPPORTED", "Every factual statement in the captions is backed by the research dossier?", "blocking",
     fix("SCRIPT", "revise_claims")),
]


def ass_events(path: Path) -> list[dict]:
    ev = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("Dialogue:"):
            parts = line[len("Dialogue:"):].split(",", 9)
            def t(s):
                h, m, rest = s.strip().split(":")
                return int(h) * 3600 + int(m) * 60 + float(rest)
            ev.append({"layer": int(parts[0]), "start": t(parts[1]), "end": t(parts[2]), "style": parts[3],
                       "raw": parts[9], "text": re.sub(r"\{[^}]*\}", "", parts[9]).strip(), "pop": "\\t(" in parts[9]})
    return ev


def moov_first(path: Path) -> bool:
    with open(path, "rb") as f:
        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                return False
            size, typ = int.from_bytes(hdr[:4], "big"), hdr[4:8]
            hl = 8
            if size == 1:
                size, hl = int.from_bytes(f.read(8), "big"), 16
            if typ == b"moov":
                return True
            if typ == b"mdat" or size == 0:
                return False
            f.seek(size - hl, 1)


def gray_frame(video: Path, t: float, crop: str | None = None) -> np.ndarray:
    vf = (f"crop={crop}," if crop else "") + "format=gray"
    w, h = (int(crop.split(":")[0]), int(crop.split(":")[1])) if crop else (W, H)
    out = subprocess.run([ffmpeg_bin(), "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-vf", vf,
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(out, dtype=np.uint8).reshape(h, w).astype(float)


def ocr_event(video: Path, nosubs: Path | None, ev: dict, y: int, lang: str) -> float:
    """OCR one caption event; polarity-aware (light captions with dark outline, or dark ink on a light edge)."""
    t = ev["start"] + 0.6 * (ev["end"] - ev["start"])
    crop = f"{W}:260:0:{max(0, y - 130)}"
    fin = gray_frame(video, t, crop)
    base = gray_frame(nosubs, t, crop) if nosubs else None
    changed = (np.abs(fin - base) > 40) if base is not None else np.ones_like(fin, bool)
    masks = [changed & (fin > 150) if base is not None else fin > 190,   # light text
             changed & (fin < 100)]                                        # dark ink text
    norm = lambda s: re.sub(r"[^A-Z0-9]", "", s.upper())  # noqa: E731
    best = 0.0
    for mask in masks:
        if mask.sum() < 50:
            continue
        img = Image.fromarray(np.where(mask, 0, 255).astype(np.uint8))
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.png"
            img.save(p)
            txt = run(["tesseract", p, "stdout", "--psm", "7", "-l", lang], check=False).stdout
        best = max(best, difflib.SequenceMatcher(None, norm(txt), norm(ev["text"])).ratio())
        if best >= 0.6:
            break
    return best


@stage_main("QA", "video-quality-assurance")
def cmd_check(a) -> int:
    out = Path(a.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    tm = read_json(a.timing)
    video = Path(a.video)
    if a.aspect == "wide":
        set_canvas(1920, 1080)
    sr = StageResult("QA", "video-quality-assurance", tm.get("video_id"), attempt=a.attempt)
    sr.input(video, "final_video"); sr.input(a.timing, "voice_timing"); sr.input(a.captions, "captions_ass")
    info = ffprobe(video)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    au = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    fps = float(Fraction(v.get("r_frame_rate", "0/1")))
    dur = float(info["format"]["duration"])
    spec_ok = ((v["width"], v["height"], v["codec_name"], v["pix_fmt"]) == (W, H, "h264", "yuv420p")
               and abs(fps - 30) < 0.01 and au is not None and au["codec_name"] == "aac"
               and int(au["sample_rate"]) == 48000 and int(au.get("channels", 0)) == 2)
    sr.check("QA.CONTAINER_SPEC", spec_ok, "blocking",
             f"{v['width']}x{v['height']} {v['codec_name']}/{v.get('profile')} {v['pix_fmt']} {fps:.2f}fps "
             f"audio={au and au['codec_name']}/{au and au['sample_rate']}", fix=fix("VIDEO", "rerender"))
    bad = decode_errors(video)
    sr.check("QA.DECODE_OK", not bad, "blocking", "; ".join(bad) or "every packet decodes", len(bad), 0,
             fix("SUBTITLES", "reburn"))
    sr.check("QA.FASTSTART", moov_first(video), "minor", "moov atom before mdat (fast start)")
    platform_max = max(PLATFORM_MAX_S, float(a.max_s))   # a long-form brief (max_s up to 480) governs; shorts keep the 180 s default
    sr.check("QA.PLATFORM_MAX", dur <= platform_max, "blocking", f"{dur:.1f}s ≤ {platform_max:g}s",
             round(dur, 2), platform_max, fix("SCRIPT", "shorten", target_s=a.max_s))
    in_range = a.min_s <= dur <= a.max_s
    sr.check("QA.DURATION_TARGET", in_range, "major", f"{dur:.1f}s within [{a.min_s}, {a.max_s}]", round(dur, 2),
             [a.min_s, a.max_s], fix("SCRIPT", "shorten" if dur > a.max_s else "lengthen", target_s=a.max_s if dur > a.max_s else a.min_s))
    sr.check("QA.AV_DURATION", abs(dur - tm["duration_s"]) <= 0.15, "blocking",
             f"video {dur:.2f}s vs narration {tm['duration_s']:.2f}s", fix=fix("VIDEO", "rerender"))

    vlog = run([ffmpeg_bin(), "-hide_banner", "-nostats", "-i", video, "-an", "-vf",
                "blackdetect=d=0.2:pix_th=0.08,freezedetect=n=0.002:d=3", "-f", "null", "-"]).stderr
    alog = run([ffmpeg_bin(), "-hide_banner", "-nostats", "-i", video, "-vn", "-af",
                "silencedetect=noise=-45dB:d=0.5,ebur128=peak=true", "-f", "null", "-"]).stderr
    blacks = [float(x) for x in re.findall(r"black_duration:([\d.]+)", vlog)]
    freezes = [float(x) for x in re.findall(r"freeze_duration: ([\d.]+)", vlog)]
    sil_s = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", alog)]
    sil_e = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", alog)]
    i_lufs = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", alog)[-1])
    tpk = float(re.findall(r"Peak:\s+(-?[\d.inf]+) dBFS", alog)[-1])
    onset = sil_e[0] if sil_s and sil_s[0] <= 0.05 and sil_e else 0.0
    internal = [(s, e) for s, e in zip(sil_s, sil_e + [dur]) if s > 0.3 and e < dur - 0.6]
    sr.check("QA.NO_BLACK", not blacks, "major", f"black segments {blacks}", blacks, [], fix("VIDEO", "rerender"))
    sr.check("QA.NO_FREEZE", not freezes, "major", f"frozen segments ≥3s {freezes}", freezes, [],
             fix("VISUAL_PLAN", "retime", max_shot=2.8))
    sr.check("QA.NO_DROPOUT", not internal, "major", f"internal silences {internal}", internal, [],
             fix("AUDIO", "resynthesize"))
    sr.check("QA.LOUDNESS", a.lufs - 1.5 <= i_lufs <= a.lufs + 1.5, "major", f"{i_lufs} LUFS", i_lufs,
             [a.lufs - 1.5, a.lufs + 1.5], fix("VIDEO", "remix", lufs=a.lufs))
    sr.check("QA.TRUE_PEAK", tpk <= -1.0, "major", f"true peak {tpk} dBTP", tpk, -1.0, fix("VIDEO", "remix", lufs=a.lufs - 1))
    sr.check("QA.HOOK_AUDIO", onset <= 0.4, "major", f"speech starts at {onset:.2f}s", round(onset, 2), 0.4,
             fix("AUDIO", "resynthesize", lead_s=0.05))

    ev = ass_events(Path(a.captions))
    cap = sorted([e for e in ev if e["layer"] == 1], key=lambda e: e["start"])
    sr.check("QA.CAPTIONS_PRESENT", bool(cap) and cap[-1]["end"] <= dur + 0.05, "blocking",
             f"{len(cap)} caption events", fix=fix("SUBTITLES", "rebuild"))
    if cap:
        sr.check("QA.HOOK_CAPTION", cap[0]["start"] <= 0.6, "major", f"first caption at {cap[0]['start']:.2f}s",
                 cap[0]["start"], 0.6, fix("SUBTITLES", "rebuild"))
        ov = [i for i in range(len(cap) - 1) if cap[i]["end"] > cap[i + 1]["start"] + 0.005]
        sr.check("QA.CAPTION_OVERLAP", not ov, "blocking", f"overlapping caption events {ov[:5]}",
                 fix=fix("SUBTITLES", "rebuild"))
    pos = re.search(r"\\pos\(\d+,(\d+)\)", cap[0]["raw"]) if cap else None
    y = int(pos.group(1)) if pos else int(H * 0.63)
    nosubs = Path(a.nosubs) if a.nosubs else None
    if nosubs and cap:
        mids = [(e["start"] + e["end"]) / 2 for e in cap[:: max(1, len(cap) // 3)][:3]]
        band = slice(max(0, y - 120), y + 120)
        diffs = [int((np.abs(gray_frame(video, t)[band] - gray_frame(nosubs, t)[band]) > 40).sum()) for t in mids]
        sr.check("QA.BURNED_IN", min(diffs) >= 400, "blocking", f"changed caption-band pixels per probe {diffs}",
                 diffs, ">=400", fix=fix("SUBTITLES", "reburn"))
    lang = TESS_LANG.get(tm["language"].split("-")[0].lower())
    have = run(["tesseract", "--list-langs"], check=False).stdout.split() if shutil.which("tesseract") else []
    if a.ocr != "off" and lang in have and cap:
        firsts = [e for e in cap if e["pop"] and e["end"] - e["start"] >= 0.25]
        sample = firsts[:: max(1, len(firsts) // 6)][:6]
        scores = [ocr_event(video, nosubs, e, y, lang) for e in sample]
        rate = sum(s >= 0.6 for s in scores) / max(1, len(scores))
        sr.check("QA.OCR_MATCH", rate >= 0.6, "major", f"OCR agreement {rate:.0%} on {len(scores)} samples",
                 [round(s, 2) for s in scores], ">=60% of samples ≥0.6", fix("SUBTITLES", "rebuild", font_scale=1.1))
        sr.metric("ocr_rate", round(rate, 2))
    else:
        sr.check("QA.OCR_MATCH", a.ocr != "on", "minor", f"OCR skipped (tesseract language for {tm['language']} unavailable)")

    sheet, hook = out / "contact_sheet.jpg", out / "hook.jpg"
    run([ffmpeg_bin(), "-y", "-v", "error", "-i", video, "-vf", f"fps={15 / dur:.5f},scale=216:384,tile=5x3",
         "-frames:v", "1", "-q:v", "3", sheet])
    run([ffmpeg_bin(), "-y", "-v", "error", "-ss", "0.7", "-i", video, "-frames:v", "1", "-vf", "scale=540:960", "-q:v", "3", hook])
    for k, val in {"duration_s": round(dur, 2), "lufs": i_lufs, "true_peak_dbtp": tpk, "speech_onset_s": round(onset, 2),
                   "caption_events": len(cap)}.items():
        sr.metric(k, val)
    sr.output(sheet, "contact_sheet", "image/jpeg"); sr.output(hook, "hook_frame", "image/jpeg")
    template = {"video_id": tm.get("video_id"), "images": [str(sheet), str(hook)],
                "instructions": "View both images. For each item set passed true/false and a short note. "
                                "Save as review.json next to this file, then run `qa_video.py finalize`.",
                "items": [{"id": i, "question": q, "severity": s, "fix_route": f} for i, q, s, f in REVIEW_ITEMS]}
    write_json(out / "review_template.json", template)
    status = None if sr.failed else "pending_review"
    res = sr.finalize(a.result, status=status)
    write_json(out / "qa_report.json", {"video_id": tm.get("video_id"), "status": res["status"],
                                        "checks": res["gate"]["checks"], "metrics": res["metrics"],
                                        "images": {"contact_sheet": str(sheet), "hook": str(hook)}})
    emit(res)
    return exit_for(res)


def finalize_independent(a, out: Path, rep: dict, prev: dict) -> int:
    """QA verdict = technical checks + the independent reviewer's report (objective checks + rubric scores)."""
    rv = read_json(a.independent)
    sr = StageResult("QA", "video-quality-assurance", rep["video_id"], attempt=prev.get("attempt", 1))
    sr.d["inputs"], sr.d["outputs"], sr.d["metrics"] = prev["inputs"], prev["outputs"], prev["metrics"]
    routes = {e["code"]: e.get("fix_route") for e in prev.get("errors", [])}   # fix routes of the QA check stage
    for c in rep["checks"]:
        if c["id"].startswith(("V.", "REV.")):
            continue                      # never carry an earlier (self-)review forward
        if c["passed"]:
            sr.d["gate"]["checks"].append(c)
        else:
            sr.check(c["id"], False, c["severity"], c["message"], c.get("value"), c.get("threshold"), routes.get(c["id"]))
    failing = {f["id"]: f for f in rv["failures"]}
    for d, v in rv["scores"].items():
        thr = max(rv["thresholds"].get(d, 0), rv["min_any_dimension"])
        f = failing.get(d)
        sr.check(f"REV.{d.upper()}", f is None, "major",
                 f"{v['score']}/5 {v['anchor']} (needs ≥{thr}; judge {v['judge']})" + (f" — {v['explanation']}" if v["explanation"] else ""),
                 v["score"], thr, f["fix_route"] if f else None)
    for f in rv["failures"]:
        if f["kind"] == "objective" and not f["id"].startswith("QA."):
            sr.check(f"REV.{f['id']}", False, f["severity"], str(f["evidence"]), fix=f.get("fix_route"))
    sr.metric("independent_review", {"verdict": rv["verdict"], "judge": rv["judge"], "report": str(Path(a.independent)),
                                     "packet_manifest_sha256": rv["packet_manifest_sha256"], "final_sha256": rv["final_sha256"],
                                     "scores": {d: v["score"] for d, v in rv["scores"].items()}})
    sr.output(Path(a.independent), "independent_review", "application/json")
    res = sr.finalize(a.result)
    rep.pop("review", None)
    rep.update({"status": res["status"], "checks": res["gate"]["checks"],
                "independent_review": {"verdict": rv["verdict"], "judge": rv["judge"], "report": str(Path(a.independent))}})
    write_json(out / "qa_report.json", rep)
    emit(res)
    return exit_for(res)


@stage_main("QA", "video-quality-assurance")
def cmd_finalize(a) -> int:
    out = Path(a.out_dir).resolve()
    rep = read_json(out / "qa_report.json")
    prev = read_json(a.result)
    if getattr(a, "independent", None):
        return finalize_independent(a, out, rep, prev)
    tpl, rev = read_json(out / "review_template.json"), read_json(a.review)
    sr = StageResult("QA", "video-quality-assurance", rep["video_id"], attempt=prev.get("attempt", 1))
    sr.d["inputs"], sr.d["outputs"], sr.d["metrics"] = prev["inputs"], prev["outputs"], prev["metrics"]
    for c in rep["checks"]:
        if c["passed"]:
            sr.d["gate"]["checks"].append(c)
        else:  # auto failures (minor ones) carry forward
            sr.check(c["id"], False, c["severity"], c["message"], c.get("value"), c.get("threshold"))
    answers = {i["id"]: i for i in rev.get("items", [])}
    for item in tpl["items"]:
        ans = answers.get(item["id"])
        if ans is None:
            sr.check(item["id"], False, "blocking", f"review item not answered: {item['question']}",
                     fix=fix("QA", "complete_review"))
        else:
            sr.check(item["id"], bool(ans.get("passed")), item["severity"], ans.get("note", item["question"]),
                     fix=item["fix_route"])
    sr.metric("reviewer", rev.get("reviewer", "unknown"))
    res = sr.finalize(a.result)
    rep.update({"status": res["status"], "checks": res["gate"]["checks"], "review": rev})
    write_json(out / "qa_report.json", rep)
    emit(res)
    return exit_for(res)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--video", required=True); c.add_argument("--timing", required=True)
    c.add_argument("--captions", required=True); c.add_argument("--out-dir", required=True)
    c.add_argument("--result", required=True); c.add_argument("--nosubs")
    c.add_argument("--min-s", type=float, default=15); c.add_argument("--max-s", type=float, default=60)
    c.add_argument("--lufs", type=float, default=-14.0); c.add_argument("--ocr", choices=["auto", "on", "off"], default="auto")
    c.add_argument("--aspect", default="vertical", choices=["vertical", "wide"],
                   help="expected container spec: vertical = 1080x1920 (short), wide = 1920x1080 (16:9 long-form)")
    c.add_argument("--attempt", type=int, default=1)
    f = sub.add_parser("finalize")
    f.add_argument("--out-dir", required=True); f.add_argument("--result", required=True)
    g = f.add_mutually_exclusive_group(required=True)
    g.add_argument("--independent", help="review_report.json from reviewer.py (Phase 1 independent review)")
    g.add_argument("--review", help="legacy review.json filled from review_template.json")
    a = ap.parse_args()
    return {"check": cmd_check, "finalize": cmd_finalize}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
