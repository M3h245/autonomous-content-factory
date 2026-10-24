#!/usr/bin/env python3
"""reviewer — independent review of a finished video from its REVIEW PACKET only (see review_packet.py).

  reviewer.py review --packet PACKET_DIR --out REVIEW_DIR [--backend auto|heuristic|anthropic|subagent]
                     [--judgment judgment.json] [--policy review-policy.json]

Independence: runs as its own process, imports no authoring module, opens files only through `Packet` (manifest
whitelist + sha256 verification), and logs every access to boundary_log.json. It never sees storyboards, scene
sources, hook candidates, beat structure, run state or earlier reviews.

Two layers:
  1. OBJECTIVE checks (deterministic, pass/fail): technical QA results, visual audit (off-canvas, cropped or
     meaning-changing text, overhangs, containment), first-frame blankness, title/cover format, timing coverage.
  2. RUBRIC scores 1-5 for 11 dimensions with anchors (1 unacceptable · 2 weak · 3 acceptable · 4 strong ·
     5 publish-ready). Every score lists its evidence; every score below 4 carries an explanation.
     judge "heuristic": measurable proxies, capped at 4 on taste-dependent dimensions (only an LLM/human judge may
     award 5 there). judge "anthropic": a fresh Messages-API context sees only packet content (needs
     ANTHROPIC_API_KEY). judge "subagent": writes review_request.md for a fresh Claude Code agent and merges its
     judgment.json. LLM scores replace heuristic scores on taste dimensions and are capped by the heuristic
     (min) on measurable ones.
Exit: 0 PASS · 2 FAIL · 3 awaiting judgment · 1 reviewer error. Writes review_report.json/.md + boundary_log.json.
"""
from __future__ import annotations

import argparse
import base64
import hashlib, json
import math
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import ffmpeg_bin, read_json, sha256_file, write_json  # noqa: E402
from review_packet import forbidden  # noqa: E402

AUTHOR_MODULES = ("doodle_engine", "doodle_lib", "storyboard_tool", "render_video", "factory", "hook_lint", "script_lint",
                  "package_engine", "package_run")
DIMS = ["hook_strength", "first_frame_clarity", "message_clarity", "visual_verbal_sync", "pacing_retention",
        "audio_balance", "subtitle_readability", "ending_quality", "title_coherence", "thumbnail_coherence",
        "drawing_quality", "overall_publishability"]
TASTE = {"hook_strength", "message_clarity", "pacing_retention", "ending_quality", "title_coherence",
         "thumbnail_coherence", "drawing_quality", "overall_publishability"}
# v3.3.1: drawing_quality is judge-only (a person or a fresh agent looking at the frames). The heuristic cannot see
# whether a foot looks like a foot, so without a judge the dimension is reported as not judged and gates nothing.
VIDEO_JUDGE_ONLY = {"drawing_quality"}
# Phase 3.5: CTA dimensions — scored only when the video carries a CTA (otherwise reported as not applicable)
CTA_DIMS = ["cta_quality", "cta_naturalness", "cta_relevance", "cta_retention_risk"]
CTA_VERB = {"follow": r"\bfollow", "subscribe": r"\bsubscrib", "like": r"\blike\b", "save": r"\bsave\b", "share": r"\b(share|send)\b",
            "part_2": r"\bpart (2|two)\b", "profile": r"\b(profile|bio)\b",
            "comment": r"\b(comment|tell (me|us)|which|what|have you|do you|would you)\b|\?", "question": r"\?"}
ASK_VERBS = r"\b(follow|subscribe|like|comment|save|share|send|tell)\b"
PUSHY = ["don't forget", "dont forget", "make sure", "smash", "hit the", "right now", "before you go", "do it now"]
ANCHORS = {1: "unacceptable", 2: "weak", 3: "acceptable", 4: "strong", 5: "publish-ready"}
DEFAULT_POLICY = Path(__file__).resolve().parents[1] / "references" / "review-policy.json"
STOP = set("a an the and or but so of to in on at for with is are was were be it its it's this that these those you your "
           "we our they their i my me as by from up out if then than not no do does did can will just".split())
CLICKBAIT = ["you won't believe", "shocking", "doctors hate", "guaranteed", "insane", "nobody is talking", "100%"]


class BoundaryError(RuntimeError):
    pass


# ----------------------------------------------------------------------------- packet access (the boundary)
class Packet:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        mf = self.root / "manifest.json"
        if not mf.exists():
            raise BoundaryError(f"no manifest in {self.root}")
        self.manifest = read_json(mf)
        # v3.3.1: the hash ignores `built_at` — rebuilding an identical packet (every PACKAGE re-run does) must not
        # turn a judgment of the very same files into JUDGMENT.STALE; any changed file still changes the hash
        canon = {k: v for k, v in self.manifest.items() if k != "built_at"}
        self.manifest_sha = hashlib.sha256(json.dumps(canon, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        self.read, self.refused = [], []
        leaks = [f for f in self.manifest["files"] if forbidden(f)]
        if leaks:
            raise BoundaryError(f"packet contains authoring artifacts: {leaks}")

    def has(self, name: str) -> bool:
        return name in self.manifest["files"]

    def path(self, name: str) -> Path:
        if name not in self.manifest["files"]:
            self.refused.append(name)
            raise BoundaryError(f"'{name}' is not in the review packet")
        p = (self.root / name).resolve()
        if self.root not in p.parents:
            self.refused.append(name)
            raise BoundaryError(f"'{name}' resolves outside the packet")
        h = sha256_file(p)
        if h != self.manifest["files"][name]["sha256"]:
            raise BoundaryError(f"'{name}' changed after the packet was built")
        if name not in [r["name"] for r in self.read]:
            self.read.append({"name": name, "sha256": h[:16]})
        return p

    def json(self, name: str, default=None):
        return read_json(self.path(name)) if self.has(name) else default

    def image(self, name: str) -> np.ndarray:
        return np.asarray(Image.open(self.path(name)).convert("RGB")).astype(np.int16)


# ----------------------------------------------------------------------------- measurements from the packet
def stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        # plural -s on short words too ("pops" ~ "pop", "cats" ~ "cat"); longer suffixes keep a 4-letter stem
        if w.endswith(suf) and len(w) - len(suf) >= (3 if suf == "s" else 4) and not w.endswith("ss"):
            w = w[: -len(suf)]
            break
    return w[:-1] if w.endswith("e") and len(w) > 4 else w


NUMWORDS = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven", "8": "eight",
            "9": "nine", "10": "ten", "12": "twelve", "15": "fifteen", "20": "twenty", "30": "thirty", "40": "forty", "50": "fifty",
            "60": "sixty", "90": "ninety", "100": "hundred"}
ABBREV = {"min": "minute", "mins": "minute", "sec": "second", "secs": "second", "hr": "hour", "hrs": "hour", "vs": "versus"}


def words_of(text: str) -> list[str]:
    """Content words, lightly stemmed (wrinkled ~ wrinkle), with small numbers and unit abbreviations normalised
    ("30 MIN" ~ "thirty minutes") so coherence checks compare meanings, not spellings."""
    out = []
    for w in re.findall(r"[a-z0-9']+", text.lower()):
        w = ABBREV.get(NUMWORDS.get(w, w), NUMWORDS.get(w, w))
        if w not in STOP and len(w) > 2:
            out.append(stem(w))
    return out


def coverage(img: np.ndarray) -> tuple[float, float]:
    """(share of non-paper pixels, share of dark ink pixels) against the frame's dominant background colour."""
    flat = img.reshape(-1, 3)
    bg = np.median(flat[:: max(1, len(flat) // 20000)], axis=0)
    diff = np.abs(img - bg).max(axis=2)
    gray = img.mean(axis=2)
    return float((diff > 40).mean()), float((gray < 110).mean())


def ocr_words(img_path: Path, box: tuple[float, float, float, float]) -> list[str]:
    try:
        im = Image.open(img_path).convert("L")
        w, h = im.size
        crop = im.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
        tmp = img_path.parent / ".ocr_tmp.png"
        crop.save(tmp)
        out = subprocess.run(["tesseract", str(tmp), "stdout", "--psm", "6"], capture_output=True, text=True).stdout
        tmp.unlink(missing_ok=True)
        return [w for w in re.findall(r"[A-Za-z]{3,}", out)]
    except (OSError, FileNotFoundError):
        return []


def ass_events(text: str) -> tuple[list[dict], dict]:
    styles, events = {}, []
    for line in text.splitlines():
        if line.startswith("Style:"):
            f = [x.strip() for x in line[6:].split(",")]
            styles[f[0]] = float(f[2])
        if line.startswith("Dialogue:"):
            f = line[9:].split(",", 9)
            if f[0].strip() != "1":
                continue
            t = lambda s: sum(float(x) * m for x, m in zip(s.split(":"), (3600, 60, 1)))  # noqa: E731
            raw = f[9]
            fs = re.search(r"\\fs(\d+)", raw)
            events.append({"start": t(f[1]), "end": t(f[2]), "style": f[3], "text": re.sub(r"\{[^}]*\}", "", raw),
                           "fs": float(fs.group(1)) if fs else None})
    return events, styles


def scene_changes(video: Path, thresh: float = 0.06) -> list[float]:
    """Engine-agnostic visual events: timestamps where the picture changes noticeably (cuts, transitions, pops)."""
    p = subprocess.run([ffmpeg_bin(), "-v", "info", "-i", str(video), "-an", "-vf",
                        f"scale=270:-2,select='gt(scene,{thresh})',showinfo", "-f", "null", "-"], capture_output=True, text=True)
    return [round(float(m), 3) for m in re.findall(r"pts_time:([0-9.]+)", p.stderr)]


def cover_format_ok(g: dict) -> bool:
    """v3.3.1: a Short's cover is 9:16 (>=720 wide); a 16:9 long-form video's thumbnail is 16:9 (>=1280 wide, YouTube's
    recommended thumbnail size). The 9:16 rule used to fail every long-form cover."""
    h, w = g["cover_shape"]
    if g.get("wide"):
        return w >= 1280 and abs(w / h - 16 / 9) <= 0.02
    return w >= 720 and abs(h / w - 16 / 9) <= 0.02


def cover_format_label(g: dict) -> str:
    return "16:9, ≥1280 wide" if g.get("wide") else "9:16, ≥720 wide"


def gather(pk: Packet) -> dict:
    tr = pk.json("text/transcript.json")
    pub = pk.json("text/publish.json", {})
    qa = pk.json("measurements/qa_report.json", {"checks": [], "metrics": {}})
    audit = pk.json("measurements/visual_audit.json")
    mix = pk.json("measurements/mix_report.json", {})
    subs = pk.json("measurements/subtitles_result.json", {})
    claims = pk.json("evidence/claims.json", {"facts": [], "sources": []})
    ff_img = pk.image("frames/first_frame.png")
    ff_cov, ff_ink = coverage(ff_img)
    cover_img = pk.image("frames/cover.jpg")
    cv_cov, _ = coverage(cover_img)
    events, styles = ass_events(pk.path("text/captions.ass").read_text(encoding="utf-8"))
    head = ocr_words(pk.path("frames/cover.jpg"), (0.04, 0.03, 0.96, 0.45))
    sents, words = tr["sentences"], tr["words"]
    cta_rep = pk.json("measurements/cta_report.json", {}) or {}
    # visual events: the engine's exact list for doodle videos, otherwise measured from the final video itself
    vis_events = audit["visual_events"] if audit else scene_changes(pk.path("media/final.mp4"))
    return {"visual_events": vis_events, "visual_events_source": "visual audit" if audit else "ffmpeg scene detection","tr": tr, "pub": pub, "qa": qa, "audit": audit, "mix": mix, "subs": subs, "claims": claims,
            "ff_cov": ff_cov, "ff_ink": ff_ink, "cover_shape": cover_img.shape[:2],
            "wide": ff_img.shape[1] > ff_img.shape[0], "cover_cov": cv_cov,   # v3.3.1 wide: 16:9 long-form → 16:9 cover
            "cover_headline": head, "cap_events": events, "cap_styles": styles, "sents": sents, "words": words,
            "duration": tr["duration_s"], "qa_failed": {c["id"]: c for c in qa.get("checks", []) if not c["passed"]},
            "qa_metrics": qa.get("metrics", {}), "cta_pub": pk.json("text/cta.json", {"present": False}) or {"present": False},
            "cta_checks": cta_rep.get("checks", [])}


# ----------------------------------------------------------------------------- objective layer
def objective(g: dict) -> list[dict]:
    out = []
    for cid, c in g["qa_failed"].items():
        if c["severity"] in ("blocking", "major"):
            out.append({"id": cid, "severity": c["severity"], "evidence": c.get("message") or cid, "source": "technical QA"})
    if g["audit"]:
        for i in g["audit"]["issues"]:
            if i["severity"] == "minor":
                continue
            d = i["detail"]
            ev = (f"'{d.get('text')}' shows as '{d.get('on_screen')}' (lost {d.get('lost_words')})" if "text" in d else
                  f"{i['actor']} over '{d.get('over') or d.get('container') or d.get('side')}' ({d.get('points_outside') or d.get('over_px')})")
            out.append({"id": f"AUDIT.{i['kind'].upper()}", "severity": i["severity"], "scene": i["scene"],
                        "at_s": i.get("first_s"), "evidence": f"{i['scene']} {ev}", "source": "visual audit"})
    for c_ in g.get("cta_checks", []):           # Phase 3.5: deterministic CTA placement gates (real timeline)
        if not c_["passed"] and c_["severity"] in ("blocking", "major"):
            out.append({"id": c_["id"], "severity": c_["severity"], "evidence": c_["evidence"], "source": "CTA gate"})
    hook = (g["audit"] or {}).get("hook") or {}
    blank = hook.get("elements_at_t0", 1) == 0 if hook else g["ff_cov"] < 0.02   # line art is a subject, not a blank page
    if blank:
        out.append({"id": "FIRST_FRAME.BLANK", "severity": "blocking",
                    "evidence": f"nothing on screen at t=0 ({hook.get('elements_at_t0', 0)} elements, {g['ff_cov']:.1%} non-paper pixels)"})
    t = g["pub"].get("title", "")
    if not t or len(t) > 100:
        out.append({"id": "TITLE.FORMAT", "severity": "blocking", "evidence": f"title length {len(t)} (1-100)"})
    h, w = g["cover_shape"]
    if not cover_format_ok(g):
        out.append({"id": "COVER.FORMAT", "severity": "major", "evidence": f"cover {w}x{h} (needs {cover_format_label(g)})"})
    if g["words"] and g["words"][-1]["end"] > g["duration"] + 0.05:
        out.append({"id": "TIMING.BEYOND_VIDEO", "severity": "blocking", "evidence": "speech ends after the video"})
    return out


# ----------------------------------------------------------------------------- rubric (heuristic judge)
def ratio_score(sig: list, cap: int) -> int:
    r = sum(1 for s in sig if s[1]) / max(len(sig), 1)
    return min(cap, 1 + math.floor((cap - 1) * r + 0.5))


def dim(score: int, sig: list, cap: int, note: str = "", critical: list | None = None) -> dict:
    """`critical` = [(condition, max_score, reason)]: a single severe defect caps the score however many other
    proxies pass (a 13-second static stretch cannot be 'acceptable' pacing)."""
    ev = [f"{'✓' if ok else '✗'} {name}: {detail}" for name, ok, detail in sig]
    miss = [f"{name} ({detail})" for name, ok, detail in sig if not ok]
    for cond, mx, why in critical or []:
        if cond and score > mx:
            score = mx
            miss.insert(0, f"CRITICAL {why}")
            ev.append(f"✗ critical: {why} (caps score at {mx})")
    expl = ""
    if score < 4:
        expl = ("Not met: " + "; ".join(miss)) if miss else note or "all proxies met but capped below strong"
    return {"score": int(score), "anchor": ANCHORS[int(score)], "evidence": ev, "explanation": expl,
            "judge": "heuristic", "cap": cap, **({"note": note} if note else {})}


def heuristic(g: dict) -> dict:
    tr, w, sents, a = g["tr"], g["words"], g["sents"], g["audit"] or {}
    hook = a.get("hook", {})
    onset = w[0]["start"] if w else 99
    first = sents[0] if sents else {"text": "", "start": 0, "end": 99}
    opening = " ".join(s["text"] for s in sents if s["start"] < 3.5) or first["text"]   # everything said in the hook window
    closing = " ".join(s["text"] for s in sents[-2:])
    tension = bool(re.search(r"n't\b|\b(not|never|no|but|actually|instead|wrong|myth|only|every|most)\b|\?|\d", opening.lower()))
    ev_times = g["visual_events"]
    labels = a.get("labels", [])
    out = {}
    # hook — strong (4) needs a visual hook in frame 0; 5 is reserved for an LLM/human judge
    sig = [("speech onset ≤0.35 s", onset <= 0.35, f"{onset:.2f}s"),
           ("first line ≤3.2 s", first["end"] - first["start"] <= 3.2, f"{first['end'] - first['start']:.2f}s '{first['text'][:40]}'"),
           ("tension device in the opening", tension, "negation/contrast/question/number" if tension else "none found"),
           ("≥2 visual events in first 1.5 s", hook.get("visual_events_first_1_5s", 0) >= 2, f"{hook.get('visual_events_first_1_5s', 0)}"),
           ("frame 0 shows ≥2 elements or on-screen text", hook.get("elements_at_t0", 0) >= 2 or hook.get("text_at_t0", False),
            f"{hook.get('elements_at_t0', '?')} element(s), text={hook.get('text_at_t0', '?')}"),
           ("on-screen text by 2.0 s", hook.get("first_text_s") is not None and hook["first_text_s"] <= 2.0,
            f"first label at {hook.get('first_text_s')}")]
    n = sum(1 for s in sig if s[1])
    sc = 4 if n == 6 else (4 if n == 5 and sig[4][1] else 3) if n >= 5 else 3 if n == 4 else 2 if n == 3 else 1
    out["hook_strength"] = dim(sc, sig, 4, "a strong hook needs a visual hook in frame 0, not only a spoken one")
    # first frame — subject extent: rendered bbox share for doodles (thin line art has little ink but is a real subject),
    # pixel coverage otherwise
    cov = max(g["ff_cov"], hook.get("subject_bbox_share_t0") or 0.0)
    edge0 = [i for i in a.get("issues", []) if i["scene"] == (a.get("scenes") or [{}])[0].get("scene") and i.get("first_s") is not None and i["first_s"] <= 0.3
             and i["severity"] != "minor"]
    sig = [("subject visible (≥6 % of frame)", cov >= 0.06, f"{cov:.1%}"), ("substantial subject (≥10 %)", cov >= 0.10, f"{cov:.1%}"),
           ("≥2 elements or text at t=0", hook.get("elements_at_t0", 0) >= 2 or hook.get("text_at_t0", False),
            f"{hook.get('elements_at_t0', '?')} element(s)"),
           ("nothing cropped at t=0", not edge0, f"{len(edge0)} issue(s)")]
    if hook.get("subject_height_ratio") is not None:   # doodle videos: the main subject should fill ≥35 % of the height
        sig.append(("main subject ≥35 % of frame height (or documented exception)",
                    hook["subject_height_ratio"] >= 0.35 or bool(hook.get("hook_exception")), f"{hook['subject_height_ratio']:.0%}"))
    nothing = hook.get("elements_at_t0", 1) == 0 if hook else cov < 0.02
    sc = 1 if nothing else 2 if cov < 0.06 else min(5, 3 + int(sig[1][1]) + int(sig[2][1])) - (0 if sig[3][1] else 1)
    if len(sig) > 4 and not sig[4][1]:
        sc = min(sc, 3)
    out["first_frame_clarity"] = dim(max(1, sc), sig, 5)
    # message clarity
    dur = max(g["duration"], 1e-6)
    wps = len(w) / dur
    lens = [len(s["text"].split()) for s in sents] or [0]
    facts = g["claims"].get("facts", [])
    strong_src = [s for s in g["claims"].get("sources", []) if re.search(r"\.(gov|edu)\b|doi\.org|nature\.com|science\.org|who\.int",
                                                                          s.get("url", ""))]
    callback = len(set(words_of(closing)) & (set(words_of(opening)) | set(words_of(g["pub"].get("title", ""))))) >= 2 if sents else False
    sig = [("speech rate 2.0-3.4 w/s", 2.0 <= wps <= 3.4, f"{wps:.2f}"), ("avg sentence ≤16 words", np.mean(lens) <= 16, f"{np.mean(lens):.1f}"),
           ("no sentence >24 words", max(lens) <= 24, f"max {max(lens)}"),
           ("claims backed by a dossier with a tier-1 source", len(facts) >= 3 and bool(strong_src), f"{len(facts)} facts, {len(strong_src)} tier-1"),
           ("ending returns to the core message", callback, "last line shares words with hook/title" if callback else "no callback")]
    out["message_clarity"] = dim(ratio_score(sig, 4), sig, 4, "truth of each claim needs an LLM/human check against evidence/claims.json",
                                [(max(lens) > 30, 2, f"a {max(lens)}-word sentence is hard to follow by ear")])
    # visual / verbal sync
    spoken = [(x["start"], re.sub(r"[^\w]", "", x["w"].lower())) for x in w]
    near = []
    for lb in labels:
        ws = [t for t in words_of(lb["text"])]
        if ws:
            hit = any(abs(t - lb["at_s"]) <= 2.5 and s in ws for t, s in spoken)
            near.append(hit)
    aligned = [any(abs(e - x["start"]) <= 0.3 for x in w) for e in ev_times] or [True]
    crops = [i for i in a.get("issues", []) if i["kind"] in ("meaning_cropped", "text_cropped", "text_offscreen")]
    sync_fail = {k for k in g["qa_failed"] if k in ("QA.HOOK_CAPTION", "QA.CAPTION_OVERLAP")} | \
                {c["id"] for c in g["subs"].get("gate", {}).get("checks", []) if not c["passed"] and c["id"] == "SUB.SYNC"}
    sig = [("labels spoken within ±2.5 s", (sum(near) / len(near) if near else 1) >= 0.7, f"{sum(near)}/{len(near)}"),
           ("visual events land on words (±0.3 s)", sum(aligned) / len(aligned) >= 0.6, f"{sum(aligned)}/{len(aligned)}"),
           ("no cropped or meaning-changed text", not crops, f"{[c['kind'] for c in crops]}" if crops else "none"),
           ("captions in sync", not sync_fail, f"{sorted(sync_fail)}" if sync_fail else "QA/SUB sync passed")]
    sc = ratio_score(sig, 5)
    if any(c["kind"] == "meaning_cropped" for c in crops):
        sc = min(sc, 2)
    out["visual_verbal_sync"] = dim(sc, sig, 5)
    # pacing
    tlist = sorted(set([0.0] + ev_times + [dur]))
    gap = max(b - c for c, b in zip(tlist, tlist[1:])) if len(tlist) > 1 else dur
    pauses = [w[k + 1]["start"] - w[k]["end"] for k in range(len(w) - 1)] or [0]
    lo, hi = g["pub"].get("target_duration_s", [15, 60])
    sig = [("no visual gap >3.0 s", gap <= 3.0, f"max {gap:.2f}s"), ("≥4 visual events per 10 s", len(ev_times) / dur * 10 >= 4,
            f"{len(ev_times) / dur * 10:.1f}"), ("duration in target window", lo - 0.5 <= dur <= hi + 0.5, f"{dur:.1f}s in {lo}-{hi}"),
           ("no speech pause >0.7 s", max(pauses) <= 0.7, f"max {max(pauses):.2f}s"), ("speech rate ≥2.2 w/s", wps >= 2.2, f"{wps:.2f}"),
           ("no frozen picture", "QA.NO_FREEZE" not in g["qa_failed"], "QA.NO_FREEZE")]
    out["pacing_retention"] = dim(ratio_score(sig, 4), sig, 4, critical=[
        (gap > 6.0, 2, f"the picture is static for {gap:.1f}s"), (gap > 4.5, 3, f"the picture is static for {gap:.1f}s")])
    # audio
    m, q = g["mix"], g["qa_metrics"]
    mu = m.get("music_under_voice_db")
    sig = [("loudness −14 ±1.5 LUFS", q.get("lufs") is not None and abs(q["lufs"] + 14) <= 1.5, f"{q.get('lufs')}"),
           ("true peak ≤ −1 dBTP", (q.get("true_peak_dbtp") if q.get("true_peak_dbtp") is not None else 0) <= -1.0, f"{q.get('true_peak_dbtp')}"),
           ("music 12-30 dB under voice", mu is not None and 12 <= mu <= 30, f"{mu}"),
           ("SFX ≤1.8 per s", (m.get("sfx_per_s") or 0) <= 1.8, f"{m.get('sfx_per_s')}"),
           ("SFX rarely competes with voice (≤25 %)", (m.get("sfx_near_voice_share") or 0) <= 0.25, f"{m.get('sfx_near_voice_share')}"),
           ("no dropouts / late speech", not {"QA.NO_DROPOUT", "QA.HOOK_AUDIO"} & set(g["qa_failed"]), "QA audio checks")]
    out["audio_balance"] = dim(ratio_score(sig, 4), sig, 4, "perceived voice quality is not measured; listen once per voice",
                              [(mu is not None and mu < 8, 1, f"music only {mu} dB under the voice"),
                               (mu is not None and mu < 12, 2, f"music only {mu} dB under the voice"),
                               (mu is not None and mu < 15, 3, f"music {mu} dB under the voice (aim ≥15)"),
                               (q.get("true_peak_dbtp") is not None and q["true_peak_dbtp"] > -0.5, 1, "clipping risk (true peak above −0.5 dBTP)")])
    # subtitles
    ev, st = g["cap_events"], g["cap_styles"]
    fs = [e["fs"] or st.get(e["style"], 0) for e in ev] or [0]
    chars = [len(e["text"]) for e in ev] or [0]
    disp = [e["end"] - e["start"] for e in ev] or [0]
    fits = not any(not c["passed"] and c["id"] == "SUB.FITS_SAFE_AREA" for c in g["subs"].get("gate", {}).get("checks", []))
    sig = [("OCR agreement ≥90 %", (q.get("ocr_rate") or 0) >= 0.9, f"{q.get('ocr_rate')}"),
           ("caption size ≥80 (ASS px @1920)", np.median(fs) >= 80, f"median {np.median(fs):.0f}"),
           ("short chunks (≤24 chars)", np.percentile(chars, 90) <= 24, f"p90 {np.percentile(chars, 90):.0f}"),
           ("each chunk shown ≥0.25 s", min(disp) >= 0.25, f"min {min(disp):.2f}s"),
           ("fits safe area / no overlap", fits and "QA.CAPTION_OVERLAP" not in g["qa_failed"], "SUB/QA gates")]
    out["subtitle_readability"] = dim(ratio_score(sig, 5), sig, 5, critical=[
        (np.median(fs) < 64, 2, f"captions too small (ASS size {np.median(fs):.0f})"),
        (np.median(fs) < 80, 3, f"captions small (ASS size {np.median(fs):.0f})")])
    # ending
    last_w = w[-1]["end"] if w else dur
    last_ev = max(ev_times) if ev_times else 0
    sig = [("visual event in the last 3 s", last_ev >= dur - 3.0, f"last at {last_ev:.1f}s of {dur:.1f}s"),
           ("hold after last word ≤1.2 s", dur - last_w <= 1.2, f"{dur - last_w:.2f}s"), ("not abrupt (tail ≥0.2 s)", dur - last_w >= 0.2, f"{dur - last_w:.2f}s"),
           ("loop / callback to the hook", callback, "shares words with hook/title" if callback else "no callback"),
           ("punchy last line (≤12 words)", (len(sents[-1]["text"].split()) if sents else 99) <= 12, f"{len(sents[-1]['text'].split()) if sents else '?'} words")]
    standalone = {c_["id"]: c_ for c_ in g.get("cta_checks", [])}.get("CTA.STANDALONE_ENDING")
    if g.get("cta_pub", {}).get("present") and standalone is not None:
        sig.append(("ending stands without the CTA", standalone["passed"], standalone["evidence"][:90]))
    out["ending_quality"] = dim(ratio_score(sig, 4), sig, 4, critical=[
        (dur - last_w > 2.5, 2, f"{dur - last_w:.1f}s of dead air after the last word"),
        (standalone is not None and not standalone["passed"], 2, "the ending only works with the CTA")])
    out.update(cta_scores(g.get("cta_pub", {}), g.get("cta_checks", []), tr["text"], dur, g["pub"].get("title", "")))
    # title
    t = g["pub"].get("title", "")
    tw = set(words_of(t))
    overlap = tw & set(words_of(tr["text"]))
    caps = sum(1 for c in t if c.isupper()) / max(1, sum(1 for c in t if c.isalpha()))
    sig = [("≤70 characters", 0 < len(t) <= 70, f"{len(t)}"), ("no clickbait phrases", not any(c in t.lower() for c in CLICKBAIT), "checked"),
           ("not shouting (≤40 % caps)", caps <= 0.4, f"{caps:.0%}"), ("≥2 title words are said in the video", len(overlap) >= 2, f"{sorted(overlap)[:5]}"),
           ("adds to the hook (not a verbatim copy)", t.strip().lower() != first["text"].strip().lower(), "differs" if t.strip().lower() != first["text"].strip().lower() else "same")]
    out["title_coherence"] = dim(ratio_score(sig, 4), sig, 4, "whether the title's promise is kept needs an LLM/human judge")
    # thumbnail / cover
    hd = g["cover_headline"]
    hw = set(words_of(" ".join(hd)))
    sig = [(cover_format_label(g), cover_format_ok(g), f"{g['cover_shape'][1]}x{g['cover_shape'][0]}"), ("subject fills ≥8 %", g["cover_cov"] >= 0.08, f"{g['cover_cov']:.1%}"),
           ("headline text in the upper area", len(hd) >= 1, f"{hd[:5]}" if hd else "none (frame grab with captions only)"),
           ("headline relates to title/video", bool(hw & (tw | set(words_of(tr["text"])))), f"{sorted(hw)[:5]}" if hw else "no headline")]
    out["thumbnail_coherence"] = dim(ratio_score(sig, 4), sig, 4, "a designed cover is a Phase 4 deliverable")
    return out


CHANNEL_CTA = {"spoken": "Follow for a daily mystery.", "on_screen": "FOLLOW BRAIN ACADEMY"}  # = cta.py


def _is_channel_cta(pub: dict) -> bool:
    n = lambda t: re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]", " ", (t or "").lower())).strip()  # noqa: E731
    return n(pub.get("spoken")) == n(CHANNEL_CTA["spoken"]) and n(pub.get("on_screen")) == n(CHANNEL_CTA["on_screen"])


def cta_scores(pub: dict, checks: list, transcript: str, duration: float, title: str = "") -> dict:
    """Heuristic CTA judgement (taste capped at 4); deterministic placement gates live in `objective` (CTA.*)."""
    if not pub or not pub.get("present"):
        return {}
    pub = {**pub, **{k: pub.get(k) or "" for k in ("type", "placement", "modality", "spoken", "on_screen")}}
    ck = {c_["id"]: c_["passed"] for c_ in checks}
    text = " ".join(x for x in (pub.get("spoken", ""), pub.get("on_screen", "")) if x)
    low = text.lower()
    t = pub.get("type", "")
    n_words = len(pub.get("spoken", "").split()) or len(pub.get("on_screen", "").split())
    asks = len(set(re.findall(ASK_VERBS, low)))
    generic = [x for x in ("like and subscribe", "smash", "hit the bell", "thanks for watching", "see you in the next",
                           "follow for more", "subscribe for more", "like for more") if x in low]
    body = transcript.lower().replace(pub.get("spoken", "").lower(), " ")
    overlap = sorted(set(words_of(text)) & set(words_of(body)))
    win = pub.get("window_s") or [0, 0]
    channel = _is_channel_cta(pub)
    if channel:  # the fixed brand line is about the channel, not this video; it is meant to repeat
        overlap = overlap or ["(channel line)"]
    out = {}
    sig = [("single ask (one action verb)", asks <= 1, f"{asks} ask verbs"), ("action matches the CTA type", bool(re.search(CTA_VERB.get(t, r"$^"), low)),
            f"type {t}"), ("short (≤12 words)", n_words <= 12, f"{n_words} words"), ("no stock outro phrase", not generic, f"{generic or 'none'}"),
           ("on-screen text ≤6 words", len(pub.get("on_screen", "").split()) <= 6, f"'{pub.get('on_screen', '')}'")]
    out["cta_quality"] = dim(ratio_score(sig, 4), sig, 4, critical=[(bool(generic), 2, f"stock outro {generic}"), (asks > 2, 2, "stacked asks")])
    pushy = [x for x in PUSHY if x in low]
    sig = [("integrated into the content or a question", pub.get("placement") == "integrated" or "?" in text, f"placement {pub.get('placement')}"),
           ("tied to the content words", len(overlap) >= 1, f"{overlap[:4]}"), ("no pushy phrasing", not pushy, f"{pushy or 'none'}"),
           ("brief when spoken (≤2.2 s; channel line ≤2.8 s)", (win[1] - win[0]) <= (2.8 if channel else 2.2) or pub.get("modality") == "on_screen", f"{win[1] - win[0]:.2f}s")]
    out["cta_naturalness"] = dim(ratio_score(sig, 4), sig, 4, critical=[(bool(pushy) and not overlap, 2, "pushy and generic")])
    subject = (sorted(set(words_of(text)) & set(words_of(title))) if title else overlap) or (["(channel line)"] if channel else [])
    sig = [("points at the video's subject (title words)", bool(subject), f"{subject[:4]}"),
           ("≥1 content word shared with the body", len(overlap) >= 1, f"{overlap[:3]}"), ("not a stock phrase", not generic, f"{generic or 'none'}")]
    out["cta_relevance"] = dim(ratio_score(sig, 4), sig, 4, critical=[(not overlap, 1, "nothing in the CTA refers to this video")])
    keys = ["CTA.NOT_IN_HOOK", "CTA.AFTER_PAYOFF", "CTA.DURATION", "CTA.ENDING", "CTA.STANDALONE_ENDING"]
    sig = [(k.replace("CTA.", "gate ").lower(), ck.get(k, False), "passed" if ck.get(k) else "failed/missing") for k in keys]
    sig.append(("CTA in the last quarter of the video", win[0] >= 0.75 * duration if duration else False, f"starts {win[0]:.1f}s of {duration:.1f}s"))
    out["cta_retention_risk"] = dim(ratio_score(sig, 5), sig, 5, "5 = no measurable risk to hook, payoff or ending", critical=[
        (not ck.get("CTA.AFTER_PAYOFF", True), 1, "CTA interrupts the payoff"), (not ck.get("CTA.NOT_IN_HOOK", True), 1, "CTA inside the hook"),
        (not ck.get("CTA.ENDING", True), 1, "CTA breaks the ending")])
    return out


def overall(scores: dict, objective_fails: list) -> dict:
    vals = [scores[d]["score"] for d in DIMS if d != "overall_publishability" and not scores[d].get("not_judged")]
    if any(o["severity"] == "blocking" for o in objective_fails):
        sc, why = 1, "objective blocking failure(s): " + ", ".join(o["id"] for o in objective_fails if o["severity"] == "blocking")
    elif objective_fails:
        sc, why = 2, "objective major failure(s): " + ", ".join(o["id"] for o in objective_fails)
    else:
        sc = min(math.floor(np.mean(vals) + 0.5), min(vals) + 1, 4)
        why = f"mean {np.mean(vals):.2f}, weakest {min(vals)} ({', '.join(d for d in DIMS[:-1] if scores[d]['score'] == min(vals) and not scores[d].get('not_judged'))})"
    return {"score": int(max(1, sc)), "anchor": ANCHORS[int(max(1, sc))], "evidence": [why], "judge": "heuristic", "cap": 4,
            "explanation": "" if sc >= 4 else why}


# ----------------------------------------------------------------------------- LLM judges (fresh context)
def rubric_text(g: dict) -> str:
    """v3.3.1: the reviewer is told the real format (a 16:9 long-form video was judged as a 'vertical short')."""
    fmt = ("16:9 long-form explainer (YouTube video over 8 minutes, chapters, thumbnail 16:9)" if g.get("wide")
           else "vertical short-form explainer")
    return RUBRIC_TEXT.replace("{FORMAT}", fmt)


RUBRIC_TEXT = ("Score each dimension 1-5 (1 unacceptable, 2 weak, 3 acceptable, 4 strong, 5 publish-ready) for a {FORMAT}. "
               "Dimensions: " + ", ".join(DIMS) + ". For EVERY dimension give concise visual/audio "
               "evidence from the packet; for every score below 4 give an explanation of what fails and what would fix it. "
               "Judge only what is in the packet. Return ONLY JSON: {\"<dimension>\": {\"score\": int, \"evidence\": str, "
               "\"explanation\": str}, ...}. If hook_strength is below 4, you may add \"fix_stage\": \"HOOK\" to it when the "
               "spoken hook line fails, or \"VISUAL_PLAN\" when only the opening picture fails. drawing_quality: would an adult "
               "viewer immediately recognise every drawn subject (a foot reads as a foot, a plane as a plane), with nothing "
               "that looks scribbled, childish, accidental, overlapping or misleading? 5 = every frame looks deliberately "
               "illustrated; 3 = mostly clear but at least one drawing is crude or ambiguous; 1 = drawings confuse the "
               "message. Name the frame and the drawing for any score below 4.")


def packet_text(pk: Packet, g: dict, obj: list) -> str:
    return json.dumps({"transcript": g["tr"]["text"], "duration_s": g["duration"], "publish": g["pub"],
                       "claims": g["claims"].get("facts", [])[:20], "objective_failures": obj,
                       "measurements": {"hook": (g["audit"] or {}).get("hook"), "mix": g["mix"], "qa": g["qa_metrics"]}}, indent=1)


def judge_anthropic(pk: Packet, g: dict, obj: list) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY")
    base = os.environ.get("CF_ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    if not key and "127.0.0.1" not in base and "localhost" not in base:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    content = []
    for name in ("frames/first_frame.png", "frames/hook_strip.jpg", "frames/contact.jpg", "frames/ending_strip.jpg", "frames/cover.jpg"):
        data = base64.b64encode(pk.path(name).read_bytes()).decode()
        content += [{"type": "text", "text": name}, {"type": "image", "source": {"type": "base64",
                    "media_type": "image/png" if name.endswith(".png") else "image/jpeg", "data": data}}]
    content.append({"type": "text", "text": packet_text(pk, g, obj)})
    body = {"model": os.environ.get("CF_REVIEW_MODEL", "claude-sonnet-4-5"), "max_tokens": 2500,
            "system": "You are an independent reviewer. You did not make this video. " + rubric_text(g),
            "messages": [{"role": "user", "content": content}]}
    req = urllib.request.Request(f"{base}/v1/messages", data=json.dumps(body).encode(), method="POST",
                                 headers={"x-api-key": key or "test", "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read())
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return json.loads(re.sub(r"^```(json)?|```$", "", text.strip()).strip())


def validate_judgment(j: dict) -> list[str]:
    errs = []
    for d in DIMS:
        v = j.get(d)
        if not isinstance(v, dict) or not isinstance(v.get("score"), int) or not 1 <= v["score"] <= 5:
            errs.append(f"{d}: missing or invalid score")
        elif not str(v.get("evidence", "")).strip():
            errs.append(f"{d}: no evidence")
        elif v["score"] < 4 and not str(v.get("explanation", "")).strip():
            errs.append(f"{d}: score {v['score']} without explanation")
        elif "fix_stage" in v and v["fix_stage"] not in JUDGE_ROUTES.get(d, {}):
            errs.append(f"{d}: fix_stage {v['fix_stage']!r} not one of {sorted(JUDGE_ROUTES.get(d, {}))}")
    return errs


def merge(heur: dict, j: dict, who: str) -> dict:
    out = {}
    for d in DIMS:
        h, l = heur[d], j[d]
        sc = l["score"] if d in TASTE else min(l["score"], h["score"] if h.get("cap", 5) == 5 else 5)
        out[d] = {"score": sc, "anchor": ANCHORS[sc], "evidence": [f"{who}: {l['evidence']}"] + h["evidence"],
                  "explanation": l.get("explanation", "") if sc < 4 else "", "judge": who, "heuristic_score": h["score"],
                  **({"fix_stage": l["fix_stage"]} if l.get("fix_stage") in JUDGE_ROUTES.get(d, {}) else {})}
    return out


# ----------------------------------------------------------------------------- policy + routes
ROUTES = {
    "hook_strength": ("VISUAL_PLAN", "redesign_scene", {"scene": "first"}),
    "first_frame_clarity": ("VISUAL_PLAN", "redesign_scene", {"scene": "first"}),
    "message_clarity": ("SCRIPT", "tighten", {}),
    "visual_verbal_sync": ("VISUAL_PLAN", "repair_cues", {}),
    "pacing_retention": ("VISUAL_PLAN", "add_entrances", {}),
    "audio_balance": ("VIDEO", "remix", {"music_gain_db": -22.0, "sfx_density": 0.7}),
    "subtitle_readability": ("SUBTITLES", "rebuild", {"font_scale": 1.15}),
    "ending_quality": ("SCRIPT", "revise_ending", {}),
    "title_coherence": ("SCRIPT", "revise_publish", {}),
    "thumbnail_coherence": ("VISUAL_PLAN", "redesign_scene", {"scene": "first", "for": "cover frame at 0.7 s"}),
    "drawing_quality": ("VISUAL_PLAN", "redraw_scene", {"hint": "use the anatomy/object library parts; one clear subject per scene"}),
    # P6.2: cover taste is a packaging problem, not a rendering problem — redesign the cover, don't re-render the video.
    "thumbnail_appeal": ("PACKAGE", "redesign_cover", {}),
}


# Phase 5: an LLM/human judge can say which stage its finding belongs to. Without this, a spoken-hook problem the
# heuristic did not mark (✗) was routed to a first-scene redesign that cannot change the words.
JUDGE_ROUTES = {"hook_strength": {"HOOK": ("HOOK", "regenerate", {}), "VISUAL_PLAN": ROUTES["hook_strength"]}}


def route_for(d: str, info: dict) -> dict:
    stage, action, params = ROUTES.get(d, ("VISUAL_PLAN", "redesign_scene", {}))
    if info.get("fix_stage") in JUDGE_ROUTES.get(d, {}):
        stage, action, params = JUDGE_ROUTES[d][info["fix_stage"]]
    elif d == "hook_strength":
        spoken_bad = [e for e in info["evidence"][:3] if e.startswith("✗")]
        if spoken_bad:
            stage, action = "HOOK", "regenerate"
    return {"stage": stage, "action": action, "params": {**params, "dimension": d, "evidence": info.get("explanation", "")[:300]}}


OBJECTIVE_ROUTES = {"FIRST_FRAME.BLANK": ("VISUAL_PLAN", "redesign_scene", {"scene": "first"}),
                    "TITLE.FORMAT": ("SCRIPT", "revise_publish", {}),
                    "COVER.FORMAT": ("VISUAL_PLAN", "redesign_scene", {"scene": "first"}),
                    "TIMING.BEYOND_VIDEO": ("VIDEO", "rerender", {}),
                    # P6.2: a package that ships unjudged (or judged against a stale packet/without a cover score) goes
                    # back to PACKAGE.
                    "JUDGMENT.MISSING": ("PACKAGE", "judge_package", {}),
                    "JUDGMENT.STALE": ("PACKAGE", "judge_package", {}),
                    "JUDGMENT.UNJUDGED_COVER": ("PACKAGE", "redesign_cover", {})}


def objective_route(o: dict) -> dict | None:
    if o["id"].startswith("AUDIT."):
        return {"stage": "VISUAL_PLAN", "action": "repair_scene", "params": {"issue": o}}
    if o["id"].startswith("CTA."):
        return {"stage": "SCRIPT", "action": "revise_cta", "params": {"check": o["id"], "evidence": o["evidence"]}}
    if o["id"] in OBJECTIVE_ROUTES:
        st, ac, pa = OBJECTIVE_ROUTES[o["id"]]
        return {"stage": st, "action": ac, "params": {**pa, "evidence": o["evidence"]}}
    return None      # technical QA failures keep the fix routes of the QA check envelope (see qa_video finalize)


def decide(scores: dict, obj: list, policy: dict) -> tuple[str, list]:
    fails = []
    for o in obj:
        if o["severity"] in ("blocking", "major"):
            route = objective_route(o)
            fails.append({"kind": "objective", "id": o["id"], "severity": o["severity"], "evidence": o["evidence"], "fix_route": route})
    for d in DIMS:
        if scores[d].get("not_judged"):
            continue
        s = scores[d]["score"]
        need = max(policy["thresholds"].get(d, 0), policy["min_any_dimension"])
        if s < need:
            fails.append({"kind": "quality", "id": d, "score": s, "threshold": need, "evidence": scores[d]["explanation"] or scores[d]["evidence"][:2],
                          "fix_route": route_for(d if d != "overall_publishability" else min([x for x in DIMS[:-1] if not scores[x].get("not_judged")], key=lambda x: scores[x]["score"]),
                                                 scores[d if d != "overall_publishability" else min([x for x in DIMS[:-1] if not scores[x].get("not_judged")], key=lambda x: scores[x]["score"])])})
    for d in CTA_DIMS:                 # only present when the video has a CTA
        if d in scores and scores[d]["score"] < policy.get("cta_thresholds", {}).get(d, 4):
            fails.append({"kind": "quality", "id": d, "score": scores[d]["score"], "threshold": policy.get("cta_thresholds", {}).get(d, 4),
                          "evidence": scores[d]["explanation"] or scores[d]["evidence"][:2],
                          "fix_route": {"stage": "SCRIPT", "action": "revise_cta", "params": {"dimension": d, "evidence": scores[d]["explanation"][:300]}}})
    return ("FAIL" if fails else "PASS"), fails


def md_report(rep: dict) -> str:
    L = [f"# Independent review — {rep['verdict']}", "", f"judge: {rep['judge']} · packet {rep['packet_manifest_sha256'][:12]} · "
         f"final.mp4 {rep['final_sha256'][:12]}", "", "| dimension | score | threshold | judge | why (if < 4) |", "|---|---|---|---|---|"]
    for d in DIMS:
        s = rep["scores"][d]
        L.append(f"| {d} | {s['score']} ({s['anchor']}) | {rep['thresholds'].get(d, rep['min_any_dimension'])} | {s['judge']} | {s['explanation'][:140]} |")
    cta_rows = [d for d in CTA_DIMS if d in rep["scores"]]
    if cta_rows:
        L += ["", "## CTA", "", "| dimension | score | threshold | why (if < 4) |", "|---|---|---|---|"]
        L += [f"| {d} | {rep['scores'][d]['score']} | {rep.get('cta_thresholds', {}).get(d, 4)} | {rep['scores'][d]['explanation'][:140]} |" for d in cta_rows]
    else:
        L += ["", "## CTA", "", f"- not applicable: {rep.get('cta_note', 'no CTA in this video')}"]
    L += ["", "## Objective checks", ""] + ([f"- **{o['severity']}** {o['id']}: {o['evidence']}" for o in rep["objective"]] or ["- none failed"])
    L += ["", "## Failures → repair routes", ""] + [f"- {f['id']} → {f['fix_route']['stage'] if f['fix_route'] else 'see check'}"
                                                   f"/{f['fix_route']['action'] if f['fix_route'] else ''}" for f in rep["failures"]]
    return "\n".join(L) + "\n"


def cmd_review(a) -> int:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    loaded = sorted(m for m in AUTHOR_MODULES if m in sys.modules)
    pk = Packet(Path(a.packet))
    policy = read_json(a.policy or DEFAULT_POLICY)
    g = gather(pk)
    obj = objective(g)
    heur = heuristic(g)
    heur["drawing_quality"] = {"score": 3, "anchor": ANCHORS[3], "judge": "heuristic", "cap": 3, "not_judged": True,
                               "evidence": ["not judged: only a person or a fresh agent looking at the frames can tell "
                                            "whether a drawing reads as what it is meant to be"],
                               "explanation": "not judged by the heuristic; it gates nothing until an LLM, human or "
                                              "subagent judge scores it"}
    heur["overall_publishability"] = overall(heur, obj)
    backend = a.backend
    if backend == "auto":
        backend = "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "heuristic"
    scores, judge = heur, "heuristic"
    if a.judgment or backend in ("anthropic", "subagent"):
        if a.judgment:
            j, judge = read_json(a.judgment), "external"
        elif backend == "subagent":
            jpath = out / "judgment.json"
            if not jpath.exists():
                (out / "review_request.md").write_text(
                    "# Independent review request\n\nYou are a fresh reviewer. Read ONLY the files in this packet:\n"
                    f"`{pk.root}` (see manifest.json). Do not open anything else.\n\n{rubric_text(g)}\n\nWrite the JSON to "
                    f"`{jpath}` and stop.\n\nObjective failures already found:\n```json\n{json.dumps(obj, indent=1)}\n```\n", encoding="utf-8")
                write_json(out / "boundary_log.json", boundary_log(pk, a, loaded, "subagent (awaiting)"))
                print(json.dumps({"verdict": "AWAITING_JUDGMENT", "request": str(out / "review_request.md")}))
                return 3
            j, judge = read_json(jpath), "subagent"
        else:
            j, judge = judge_anthropic(pk, g, obj), "anthropic"
        errs = validate_judgment(j)
        if errs:
            write_json(out / "boundary_log.json", boundary_log(pk, a, loaded, judge))
            print(json.dumps({"verdict": "ERROR", "judgment_errors": errs}))
            return 1
        scores = merge(heur, j, judge)
        scores.update({d: heur[d] for d in CTA_DIMS if d in heur})   # CTA dims stay heuristic unless judged separately
    verdict, fails = decide(scores, obj, policy)
    rep = {"verdict": verdict, "judge": judge, "packet": str(pk.root), "packet_manifest_sha256": pk.manifest_sha,
           "final_sha256": pk.manifest["files"]["media/final.mp4"]["sha256"], "thresholds": policy["thresholds"],
           "min_any_dimension": policy["min_any_dimension"], "objective": obj, "scores": scores, "failures": fails,
           "cta_thresholds": policy.get("cta_thresholds", {}),
           "cta_note": "no CTA in this video" if not g.get("cta_pub", {}).get("present") else "",
           "heuristic_scores": {d: heur[d]["score"] for d in DIMS} if judge != "heuristic" else None,
           "limits": [] if judge != "heuristic" else ["taste dimensions capped at 4 (heuristic judge); an LLM/human judge is needed for 5"]}
    write_json(out / "review_report.json", rep)
    (out / "review_report.md").write_text(md_report(rep), encoding="utf-8")
    write_json(out / "boundary_log.json", boundary_log(pk, a, loaded, judge))
    print(json.dumps({"verdict": verdict, "judge": judge, "scores": {d: scores[d]["score"] for d in DIMS},
                      "failures": [f["id"] for f in fails]}))
    return 0 if verdict == "PASS" else 2


def boundary_log(pk: Packet, a, loaded: list, judge: str) -> dict:
    return {"process": {"pid": os.getpid(), "ppid": os.getppid(), "argv": sys.argv}, "judge": judge,
            "packet_root": str(pk.root), "manifest_sha256": pk.manifest_sha, "files_read": pk.read, "refused": pk.refused,
            "authoring_modules_loaded": loaded + sorted(m for m in AUTHOR_MODULES if m in sys.modules and m not in loaded),
            "authoring_files_in_packet": [f for f in pk.manifest["files"] if forbidden(f)],
            "statement": "reviewer read only hash-verified packet files; no authoring module, state or reasoning available"}


# ============================================================================= Phase 2: hook + script candidates
GENERIC_OPENERS = ["in this video", "today we", "today i", "let's talk", "lets talk", "hey guys", "welcome back", "welcome to",
                   "we are going to", "we're going to talk", "i want to talk", "a little bit about"]
TENSION_RE = r"n't\b|\b(not|never|no|but|actually|instead|wrong|myth|only|every|most|why|what|how|still|until|secret)\b|\?|\d"


def _related(a: str, b: str) -> bool:
    neg = lambda t: bool(re.search(r"n't\b|\b(not|no|never)\b", t.lower()))  # noqa: E731
    return bool(set(words_of(a)) & set(words_of(b))) or (neg(a) and neg(b))


def score_hook_candidate(pk: Packet, pol: dict) -> dict:
    h, m = pk.json("text/hook.json"), pk.json("measurements/frame0.json")
    cl = pk.json("evidence/claims.json", {"facts": [], "promised_fact_ids": []})
    f0 = pol["frame0"]
    spoken, ost, dur, topic = h["spoken_text"], h.get("on_screen_text", ""), float(h["estimated_duration_s"]), h["topic"]
    ids = {f["id"] for f in cl.get("facts", [])}
    promised = cl.get("promised_fact_ids") or []
    texts = m.get("texts_t0", [])
    obj = []
    if m.get("elements_at_t0", 0) == 0:
        obj.append({"id": "FRAME0.BLANK", "severity": "blocking", "evidence": "nothing on screen at t=0"})
    for t in texts:
        if t["negation_hidden"]:
            obj.append({"id": "FRAME0.NEGATION_HIDDEN", "severity": "blocking", "evidence": f"'{t['text']}' reads '{t['on_screen']}'"})
        elif t["lost_words"]:
            obj.append({"id": "FRAME0.TEXT_CROPPED", "severity": "major", "evidence": f"'{t['text']}' loses {t['lost_words']}"})
        if not t["inside_safe"]:
            obj.append({"id": "FRAME0.TEXT_OUTSIDE_SAFE", "severity": "major", "evidence": f"'{t['text']}' bbox {t['bbox']}"})
        if t["size_px"] < f0["text_min_px"]:
            obj.append({"id": "FRAME0.TEXT_SMALL", "severity": "major", "evidence": f"'{t['text']}' {t['size_px']} px"})
    for v in m.get("safe_margin_violations_t0", []):
        obj.append({"id": "FRAME0.SAFE_MARGIN", "severity": "major", "evidence": f"{v['actor']} bbox {v['bbox']}"})
    exc = m.get("hook_exception")
    if m.get("subject_height_ratio", 0) < f0["subject_height_min"] and not exc:
        obj.append({"id": "FRAME0.SUBJECT_SMALL", "severity": "major",
                    "evidence": f"main subject {m.get('subject_height_ratio', 0):.0%} of frame height (needs ≥{f0['subject_height_min']:.0%} or a documented exception)"})
    ev0 = m.get("first_visual_event_s")
    if (ev0 is None or ev0 > f0["first_event_max_s"]) and not m.get("idle_motion_at_t0"):
        obj.append({"id": "FRAME0.NO_EARLY_EVENT", "severity": "major", "evidence": f"first visual event at {ev0}"})
    # v3.3: the hook window follows the format. Shorts keep the 3.2 s heuristic; long-form uses YouTube's own
    # 5-10 s creator guidance (docs/v3.3/RESEARCH-PACKAGING.md §2, youtube.com/creators/create/longform/).
    hook_max = f0["hook_max_s_long"] if h.get("video_kind") == "long" else f0["hook_max_s"]
    if dur > hook_max:
        obj.append({"id": "HOOK.TOO_LONG", "severity": "major",
                    "evidence": f"{dur:.2f}s spoken (calibrated estimate; limit {hook_max}s for {h.get('video_kind', 'short')})"})
    if not promised or not set(promised) <= ids:
        obj.append({"id": "HOOK.UNSUPPORTED_PROMISE", "severity": "blocking", "evidence": f"promised facts {promised} not all in the dossier"})
    generic = any(g in spoken.lower() for g in GENERIC_OPENERS)
    tension = bool(re.search(TENSION_RE, spoken.lower()))
    reinforce = bool(ost) and (_related(ost, spoken) or bool(re.search(r"\?|\bnot\b|\bno\b|\bvs\b", ost.lower())))
    visual0 = m.get("elements_at_t0", 0) >= 2 or m.get("text_at_t0", False)
    early = (ev0 is not None and ev0 <= f0["first_event_max_s"]) or bool(m.get("idle_motion_at_t0"))
    sig = [("spoken ≤3.2 s", dur <= 3.2, f"{dur:.2f}s"), ("tension device", tension, "found" if tension else "none"),
           ("short on-screen text (1-6 words)", 1 <= len(ost.split()) <= 6, f"'{ost}'"),
           ("on-screen text reinforces the spoken hook", reinforce, "related" if reinforce else "unrelated/none"),
           ("frame 0: ≥2 elements or text", visual0, f"{m.get('elements_at_t0')} elements, text={m.get('text_at_t0')}"),
           ("visual event ≤0.5 s", early, f"{ev0}"), ("promise backed by dossier facts", bool(promised) and set(promised) <= ids, f"{promised}")]
    n = sum(1 for x in sig if x[1])
    sc = 4 if n >= 6 and visual0 and early and reinforce else 3 if n >= 5 else 2 if n >= 3 else 1
    hook = dim(sc, sig, 4, "strong needs a visual frame 0, an immediate event and on-screen text that reinforces the line",
               [(generic, 2, "generic opener"), (dur > 4.0, 2, f"{dur:.1f}s before the hook lands")])
    shown_ok = all(not t["lost_words"] and t["inside_safe"] and t["size_px"] >= f0["text_min_px"] for t in texts)
    sig = [(f"subject ≥{f0['subject_height_min']:.0%} of frame height", m.get("subject_height_ratio", 0) >= f0["subject_height_min"] or bool(exc),
            f"{m.get('subject_height_ratio', 0):.0%}" + (f" (exception: {exc})" if exc else "")),
           ("≥2 elements at t=0", m.get("elements_at_t0", 0) >= 2, f"{m.get('elements_at_t0')}"),
           ("text fully visible, ≥60 px, inside safe area", bool(texts) and shown_ok, f"{[(t['text'], t['size_px']) for t in texts]}"),
           ("nothing outside safe margins", not m.get("safe_margin_violations_t0"), f"{len(m.get('safe_margin_violations_t0', []))}")]
    ff = dim(ratio_score(sig, 5), sig, 5, critical=[
        (m.get("elements_at_t0", 0) == 0, 1, "blank first frame"), (any(t["negation_hidden"] for t in texts), 1, "negation hidden at t=0"),
        (m.get("subject_height_ratio", 0) < 0.20 and not exc, 2, "tiny subject"), (any(t["lost_words"] for t in texts), 2, "cropped text")])
    sig = [("on-screen text relates to the spoken line", reinforce, f"'{ost}' vs '{spoken[:40]}'"),
           ("topic named immediately (spoken)", bool(set(words_of(spoken)) & set(words_of(topic))), f"topic '{topic}'"),
           ("frame text relates to topic or line", any(_related(t["text"], spoken + " " + topic) for t in texts), "checked"),
           ("negation consistent (spoken ↔ screen)", not re.search(r"n't\b|\bnot\b|\bno\b", spoken.lower()) or
            bool(re.search(r"\bnot\b|\bno\b|\?|✗|\bvs\b", " ".join(t["text"] for t in texts).lower())), "checked")]
    vv = dim(ratio_score(sig, 5), sig, 5, critical=[(any(t["negation_hidden"] for t in texts), 2, "on-screen negation hidden")])
    return {"objective": obj, "scores": {"hook_strength": hook, "first_frame_clarity": ff, "visual_verbal_sync": vv}}


def score_script_variant(pk: Packet, pol: dict) -> dict:
    tr, hk = pk.json("text/transcript.json"), pk.json("text/hook.json")
    pub, cl, chk = pk.json("text/publish.json", {}), pk.json("evidence/claims.json", {}), pk.json("measurements/script_checks.json", {})
    sents, words = tr["sentences"], tr["text"].split()
    dur = tr["estimated_duration_s"]
    lo, hi = pub.get("target_duration_s", [15, 60])
    lens = [len(s["text"].split()) for s in sents] or [0]
    # v3.3.1: words per second over the whole estimated runtime (pauses included), the same measure and band as the
    # final video review (2.0-3.4). Speech-only time with a 3.3 cap was tuned on am_michael; the default af_heart voice
    # speaks 3.3-3.5 w/s between pauses, so every correctly calibrated script failed clarity.
    wps = len(words) / max(float(dur), 1e-6)
    ids = {f["id"] for f in cl.get("facts", [])}
    used, promised = set(cl.get("script_fact_ids", [])), set(cl.get("promised_fact_ids", []))
    opening, closing = sents[0]["text"] if sents else "", " ".join(s["text"] for s in sents[-2:])
    callback = len(set(words_of(closing)) & (set(words_of(hk["spoken_text"])) | set(words_of(hk.get("on_screen_text", ""))))) >= 1
    obj = [{"id": c["id"], "severity": c["severity"], "evidence": c["evidence"]} for c in chk.get("checks", []) if not c["passed"]
           and c["severity"] in ("blocking", "major")]
    sig = [("speech rate 2.0-3.4 w/s (calibrated, pauses included)", 2.0 <= wps <= 3.4, f"{wps:.2f}"), ("avg sentence ≤16 words", np.mean(lens) <= 16, f"{np.mean(lens):.1f}"),
           ("no sentence >24 words", max(lens) <= 24, f"max {max(lens)}"), ("claims mapped to the dossier (≥3)", len(used) >= 3 and used <= ids,
            f"{sorted(used)}"), ("ending returns to the hook", callback, "callback" if callback else "none")]
    clar = dim(ratio_score(sig, 4), sig, 4, critical=[(max(lens) > 30, 2, f"{max(lens)}-word sentence")])
    expl = chk.get("explanation_start_s")
    sig = [("estimated duration in window", lo <= dur <= hi, f"{dur:.1f}s in {lo}-{hi}"),
           (f"explanation starts by {pol['frame0']['explanation_by_s']} s", expl is not None and expl <= pol["frame0"]["explanation_by_s"], f"{expl}"),
           ("varied rhythm (sentence-length spread ≥3 words)", float(np.std(lens)) >= 3, f"σ={np.std(lens):.1f}"),
           ("at least one punchy line (≤6 words)", min(lens) <= 6, f"min {min(lens)}"), ("no sentence >24 words", max(lens) <= 24, f"max {max(lens)}")]
    pace = dim(ratio_score(sig, 4), sig, 4, critical=[(dur > hi, 2, f"{dur:.1f}s > {hi}s")])
    mid = " ".join(s["text"] for s in sents[1:-1])
    addressed = bool(set(words_of(hk["spoken_text"]) + words_of(hk.get("on_screen_text", ""))) & set(words_of(mid)))
    title_spoken = len(set(words_of(pub.get("title", ""))) & set(words_of(tr["text"]))) >= 2
    sig = [("promised facts are delivered", bool(promised) and promised <= used, f"promised {sorted(promised)}, used {sorted(used)}"),
           ("the body addresses the hook's tension", addressed, "hook words reappear in the body" if addressed else "never addressed"),
           ("ending calls back to the hook", callback, "yes" if callback else "no"), ("title words are spoken", title_spoken, pub.get("title", "")),
           ("hook not repeated verbatim mid-script", not chk.get("hook_repeated_mid", False), "checked")]
    coh = dim(ratio_score(sig, 4), sig, 4, critical=[(bool(promised) and not promised <= used, 2, "hook promise not paid off")])
    # The hook itself (line + frame 0) was judged at the HOOK stage; here we check it is delivered intact and carry
    # that independent score — re-judging the line alone would contradict the frame-0 judgement.
    hr = (pk.json("measurements/hook_review.json", {}) or {}).get("scores", {})
    carried = int(hr.get("hook_strength") or 0)
    first_s = (sents[0]["end"] - sents[0]["start"]) if sents else 0
    sig = [("hook-stage score (line + frame 0)", carried >= 4, f"{carried or 'not reviewed'}"),
           ("opening is the selected hook", chk.get("hook_is_opening", False), "yes" if chk.get("hook_is_opening") else "no"),
           ("first line ≤3.2 s", first_s <= 3.2, f"{first_s:.2f}s"),
           ("no generic intro", not any(g in tr["text"].lower()[:200] for g in GENERIC_OPENERS), "checked")]
    base = min(carried, 4) if carried else ratio_score(sig, 4)
    hook = dim(base, sig, 4, "carries the independent hook-stage score", critical=[
        (not chk.get("hook_is_opening", False), 2, "the script does not open with the selected hook"),
        (first_s > 3.2, 3, f"opening line {first_s:.1f}s"), (any(g in tr["text"].lower()[:200] for g in GENERIC_OPENERS), 2, "generic intro")])
    scores = {"message_clarity": clar, "pacing_retention": pace, "payoff_coherence": coh, "hook_strength": hook}
    scores.update(cta_scores(pk.json("text/cta.json", {"present": False}) or {},
                             [c_ for c_ in chk.get("checks", []) if c_["id"].startswith("CTA.")], tr["text"], dur, pub.get("title", "")))
    return {"objective": obj, "scores": scores}


# ============================================================================= Phase 4: package candidates
PACKAGE_DIMS = ["title_strength", "curiosity", "accuracy", "thumbnail_readability", "complementarity", "hook_coherence",
                "promise_payoff", "clickbait_risk", "cta_coherence", "thumbnail_appeal"]
# P6.2: the cover's *taste* is not measurable geometrically. A cover can pass every metric above and still be dull.
# The heuristic returns a neutral 3 and says "not judged"; the external judge (fresh agent or human looking at the shelf
# size and the full size) is AUTHORITATIVE here and may raise as well as lower it. This is the one deliberate exception
# to the min-only merge, because a mechanical gate has no evidence to cap against.
JUDGE_ONLY = {"thumbnail_appeal"}
OPEN_LOOP = r"\?|\b(why|what|how|actually|really|isn't|not|vs|versus|myth|wrong|real|still|until|secret|inside)\b"
VAGUE = {"this", "thing", "things", "stuff", "video", "something", "everything"}
FUNC = {"what", "why", "how", "when", "where", "who", "which", "does", "doe", "did", "can", "will", "just", "really", "actually",
        "actual", "still", "here", "there", "then", "than", "about", "into", "inside", "out", "over", "one", "your", "yours", "you",
        "more", "less", "most", "least"}


def score_package(pk: Packet, pol: dict) -> dict:
    c, tr = pk.json("text/package.json"), pk.json("text/transcript.json")
    cl, mm = pk.json("evidence/claims.json", {}), pk.json("measurements/package_checks.json", {"checks": [], "thumbnail": {}})
    vc = pk.json("text/cta.json", {"present": False}) or {"present": False}
    pk.path("frames/thumbnail.jpg"); pk.path("frames/thumbnail_168.png")          # read: the images being judged
    pp = pol["packaging"]
    m, checks = mm["thumbnail"], mm["checks"]
    title, thumb, promise, desc = c["title"], c.get("thumbnail_text", ""), c["opening_promise"], c["description"]
    sents = tr["sentences"]
    T = set(words_of(tr["text"]))
    first = set(words_of(" ".join(s["text"] for s in sents[:2])))
    k = max(1, round(len(sents) * 0.55))
    payoff = set(words_of(" ".join(s["text"] for s in sents[len(sents) - k:])))
    answer = payoff - first
    W, TW, PW = (set(words_of(x)) - FUNC for x in (title, thumb, promise))
    cited = [f for f in cl.get("facts", []) if f["id"] in set(cl.get("package_claim_ids", []))]
    CW = set(words_of(" ".join(f["claim"] for f in cited)))
    ctext = " ".join(f["claim"] for f in cited).lower()
    obj = [{"id": x["id"], "severity": x["severity"], "evidence": f"{x.get('where', '')}: {x['evidence']}"} for x in checks
           if x["severity"] in ("blocking", "major")]
    claim_fail = [x for x in checks if x["id"].startswith("CLAIM.") or x["id"] == "TITLE.OFF_TOPIC"]
    bait = [p_ for p_ in CLICKBAIT + ["doctors hate", "gone wrong", "mind-blowing", "unbelievable", "this one trick", "crazy"]
            if p_ in " ".join([title, thumb, promise, desc]).lower()]
    raw = re.findall(r"[a-z']+", title.lower())
    # --- title strength
    sig = [("≤50 chars (mobile, no truncation)", len(title) <= 50, f"{len(title)}"), ("4-10 words", 4 <= len(raw) <= 10, f"{len(raw)}"),
           ("names the topic of the opening", bool(W & first), f"{sorted(W & first)}"),
           ("concrete: carries a fact word or a supported number", bool(W & CW), f"{sorted(W & CW)}"),
           ("no vague filler", not (set(raw) & VAGUE), f"{sorted(set(raw) & VAGUE)}"), ("no bait template", not bait, f"{bait}")]
    ts = dim(ratio_score(sig, 5), sig, 5, critical=[(len(title) > 60, 2, f"{len(title)}-char title truncates on mobile"),
                                                   (bool(bait), 2, "bait phrasing")])
    # --- curiosity (open loop that the video closes)
    loop = bool(re.search(OPEN_LOOP, title.lower()))
    keeps = title.strip().endswith("?") or not (W & answer)
    adds = bool(TW - W) or (not thumb and m.get("main_subject"))
    sig = [("open-loop device in the title", loop, "found" if loop else "none"),
           ("title leaves the answer for the video", keeps, f"answer words in title {sorted(W & answer)}"),
           ("thumbnail adds something the title does not say", bool(adds), f"{sorted(TW - W)}"),
           ("specific, not vague", bool(W & CW) or bool(re.search(r"\d", title)), "checked")]
    cu = dim(ratio_score(sig, 5), sig, 5, critical=[(bool(bait), 2, "curiosity built on bait")])
    # --- accuracy (independent re-check of numbers + deterministic claim gates)
    nums = [n for n in re.findall(r"\d+(?:[.,]\d+)?", " ".join([title, thumb, promise, desc])) if n not in ctext]
    sig = [("no unsupported/contradicted claim (deterministic gate)", not claim_fail, f"{[x['id'] for x in claim_fail]}"),
           ("every number is in a cited fact", not nums, f"unsupported {nums}"),
           ("claims rest on cited dossier facts", bool(cited), f"{[f['id'] for f in cited]}"),
           ("title words are spoken in the video", bool(W & T), f"{sorted(W & T)}")]
    ac = dim(ratio_score(sig, 5), sig, 5, critical=[(bool(claim_fail), 1, "unsupported or contradicted claim"),
                                                   (bool(nums), 1, f"number(s) {nums} not in the evidence")])
    # --- thumbnail readability at ~168 px
    texts = m.get("texts", [])
    big = max((t["size_px"] for t in texts), default=0)
    sig = [(f"headline ≥{pp['thumb_headline_min_px']} px", not texts or big >= pp["thumb_headline_min_px"], f"{big}"),
           (f"all text ≥{pp['thumb_text_min_px']} px", all(t["size_px"] >= pp["thumb_text_min_px"] for t in texts), f"{[t['size_px'] for t in texts]}"),
           (f"contrast at 168 px ≥{pp['thumb_contrast_min']}", all(t["contrast_168"] >= pp["thumb_contrast_min"] for t in texts),
            f"{[t['contrast_168'] for t in texts]}"),
           (f"≤{pp['thumb_words_max']} words", m.get("words", 0) <= pp["thumb_words_max"], f"{m.get('words')}"),
           (f"subject ≥{pp['subject_min_core_height']:.0%} of the core height", m.get("subject_core_height", 0) >= pp["subject_min_core_height"],
            f"{m.get('subject_core_height')}"),
           (f"≤{pp['dead_cells_max']} empty cells", m.get("dead_cells", 9) <= pp["dead_cells_max"], f"{m.get('dead_cells')}"),
           ("single focal subject", m.get("second_subject_ratio", 1) <= pp["second_subject_max_ratio"], f"{m.get('second_subject_ratio')}"),
           ("text inside the central square", all(t["inside_core"] for t in texts), "checked")]
    tr_ = dim(ratio_score(sig, 5), sig, 5, critical=[
        (any(t["size_px"] < pp["thumb_text_min_px"] for t in texts), 2, "text unreadable at thumbnail size"),
        (any(t["contrast_168"] < 3 for t in texts), 2, "text blends into the background"),
        (m.get("words", 0) > pp["thumb_words_max"], 2, f"{m.get('words')} words"),
        (m.get("subject_core_height", 0) < 0.25, 2, "subject too small")])
    # --- complementarity (title + thumbnail tell more together than either alone)
    rep = bool(thumb) and (TW <= W or thumb.lower().strip("?! .") in title.lower())
    sig = [("thumbnail text does not repeat the title", not rep and (len(TW & W) / max(len(TW | W), 1) <= 0.34), f"shared {sorted(TW & W)}"),
           ("thumbnail text is about the video", not TW or bool(TW & (T | CW)), f"{sorted(TW & (T | CW))}"),
           ("together they name ≥3 distinct video ideas", len((W | TW) & T) >= 3, f"{sorted((W | TW) & T)}"),
           ("thumbnail has a clear subject", bool(m.get("main_subject")), f"{m.get('main_subject')}")]
    co = dim(ratio_score(sig, 5), sig, 5, critical=[(rep, 2, "thumbnail repeats the title")])
    # --- hook / package coherence
    sig = [("opening promise matches the video's opening", bool(PW & first), f"{sorted(PW & first)}"),
           ("title matches the opening's topic", bool(W & first), f"{sorted(W & first)}"),
           ("thumbnail relates to the video", not TW or bool(TW & (T | CW)), "checked"),
           ("promise is one short line", len(promise) <= pp["opening_promise_max_chars"], f"{len(promise)} chars")]
    hc = dim(ratio_score(sig, 5), sig, 5, critical=[(not (PW & first) and not (W & first), 2, "package and opening are about different things")])
    # --- promise / payoff
    dw = set(words_of(desc))
    sig = [("title words are paid off in the second half", bool(W & payoff), f"{sorted(W & payoff)}"),
           ("thumbnail words appear in the video or evidence", not TW or len(TW & (T | CW)) >= max(1, len(TW) // 2), f"{sorted(TW & (T | CW))}"),
           ("a question title is answered", not title.strip().endswith("?") or bool(answer), "answered" if answer else "no answer"),
           ("description describes what is said", len(dw & T) >= 0.5 * max(len(dw), 1), f"{len(dw & T)}/{len(dw)} words")]
    # airtime: how much of the video is about what the title promises beyond the opening question
    focus = W - set(words_of(sents[0]["text"])) if sents else W
    dur_ = max(float(tr.get("duration_s") or (sents[-1]["end"] if sents else 1)), 1e-6)
    hit = set()
    for i, s in enumerate(sents):
        if focus & set(words_of(s["text"])):
            hit.add(i)
            if s["text"].strip().endswith("?") and i + 1 < len(sents):
                hit.add(i + 1)                 # a spoken question is answered by the next line
    air = 1.0 if not focus else sum(sents[i]["end"] - sents[i]["start"] for i in hit) / dur_
    # v3.3.1: a title that restates the run's own topic question ("Why does your foot fall asleep?") is about the whole
    # video, even when the narration words it differently ("a sleeping foot"); counting words alone called it a side note.
    topic_w = set(words_of(c.get("topic", ""))) - FUNC
    on_topic = bool(focus) and bool(topic_w) and focus <= topic_w
    if on_topic:
        air = 1.0
    sig.append(("the title's focus gets real airtime (≥20 %)", air >= 0.20,
                f"{sorted(focus)}: " + ("the run topic itself — the whole video answers it" if on_topic else f"{air:.0%} of the video")))
    pp_ = dim(ratio_score(sig, 5), sig, 5, critical=[(not (W & T), 1, "title is not about this video"),
                                                    (air < 0.10, 3, f"title focus {sorted(focus)} is a side note ({air:.0%})"),
                                                    (bool(claim_fail), 2, "promise rests on an unsupported claim")])
    # --- clickbait risk (5 = safe)
    caps = [w for w in re.findall(r"[A-Za-z']+", title) if len(w) >= 4 and w.isupper()]
    sig = [("no bait phrases", not bait, f"{bait}"), ("no shouting in the title", len(caps) <= 1, f"{caps}"),
           ("≤1 exclamation mark", " ".join([title, thumb, promise]).count("!") <= 1, "checked"),
           ("no unsupported absolutes/claims", not claim_fail, f"{[x['id'] for x in claim_fail]}"),
           ("title promise is delivered", bool(W & payoff), "checked")]
    cb = dim(ratio_score(sig, 5), sig, 5, critical=[(bool(bait), 2, "bait phrasing"), (bool(claim_fail), 1, "misleading claim")])
    # --- CTA coherence
    cta_fail = [x for x in checks if x["id"].startswith("CTA.PKG") or x["id"] == "THUMB.CTA"]
    ccta = c.get("caption_cta", "")
    rel = not ccta or not vc.get("present") or bool(set(words_of(ccta)) & set(words_of((vc.get("spoken") or "") + " " + (vc.get("on_screen") or "")) + list(T)))
    sig = [("copy asks only what the video asks", not cta_fail, f"{[x['id'] for x in cta_fail]}"),
           ("caption CTA echoes the video's CTA", rel, f"'{ccta}' vs '{vc.get('spoken', '')}'"),
           ("no CTA on the thumbnail", not any(x["id"] == "THUMB.CTA" for x in checks), "checked")]
    cc = dim(ratio_score(sig, 5), sig, 5, critical=[(bool(cta_fail), 2, "conflicting call to action")])
    # --- thumbnail appeal (P6.2, taste) ------------------------------------------
    # Everything above is measurable. This one is not: a cover can pass every geometric gate and still be dull.
    # The heuristic records only what it can see and returns a neutral 3 that says so. An agent (or human) looking at
    # the shelf-size and the full-size cover is authoritative for this dimension and may raise as well as lower it.
    sig = [("one clear focal subject", bool(m.get("main_subject")) and m.get("second_subject_ratio", 1) <= pp["second_subject_max_ratio"],
            f"subject {m.get('main_subject')}, second-subject ratio {m.get('second_subject_ratio')}"),
           ("cover text adds what the title does not say", not TW or bool(TW - W), f"{sorted(TW - W)}"),
           ("cover text is short (≤3 words)", m.get("words", 0) <= 3, f"{m.get('words')}"),
           ("the cover is not the title repeated", not rep, "repeats the title" if rep else "adds something")]
    ta = dim(3, sig, 5, "not judged: taste needs a judge looking at the cover at shelf size and full size; the "
                        "external judge's score for thumbnail_appeal is authoritative (it may raise or lower this)")
    if not m.get("main_subject") and not texts:
        ta = dim(2, sig, 5, "no depicted subject and no cover text: there is nothing here to win a click",
                 critical=[(True, 2, "the cover has neither a subject nor text")])
    return {"objective": obj, "scores": {"title_strength": ts, "curiosity": cu, "accuracy": ac, "thumbnail_readability": tr_,
                                         "complementarity": co, "hook_coherence": hc, "promise_payoff": pp_, "clickbait_risk": cb,
                                         "cta_coherence": cc, "thumbnail_appeal": ta}}


def merge_package_judgment(r: dict, j: dict | None, cid: str) -> dict:
    """An external judge (fresh agent or human who saw ONLY the packet) can lower a score, never raise it above the
    heuristic's evidence-backed ceiling: final = min(heuristic, judge). Both are kept in the record.

    Exception (P6.2): `thumbnail_appeal` is judge-only. The heuristic returns a neutral placeholder with no evidence to
    cap against, so the judge's score *replaces* it and can be higher as well as lower."""
    if not j:
        return r
    jc = (j.get("candidates") or {}).get(cid) or {}
    for d, v in (jc.get("scores") or {}).items():
        if d in r["scores"] and isinstance(v, (int, float)) and 1 <= v <= 5:
            h = r["scores"][d]
            h["heuristic_score"] = h["score"]
            h["judge_score"] = int(v)
            h["judge_note"] = (jc.get("notes") or {}).get(d, "")
            if d in JUDGE_ONLY:
                h["score"], h["anchor"], h["judge"] = int(v), ANCHORS[int(v)], "external"
                h["explanation"] = "" if int(v) >= 4 else f"external judge: {h['judge_note'] or 'cover appeal below strong'}"
            elif int(v) < h["score"]:
                h["score"], h["anchor"], h["judge"] = int(v), ANCHORS[int(v)], "external"
                h["explanation"] = f"external judge: {h['judge_note'] or 'lower score'}"
    return r

def _package_request_md(pkts: list, out: Path, context: dict | None) -> str:
    """The request an agent (or human) reads to judge cover taste. It names only packet files, so the judge still
    reads nothing the author wrote. The context brief (the channel's own covers) is separate and hashed."""
    L = ["# Independent cover review request", "",
         "You are a fresh reviewer. You did not make these covers and you have not seen the author's reasoning.",
         "For each candidate open ONLY its packet:", "", "1. `frames/thumbnail.jpg` — the cover at full size",
         "2. `frames/thumbnail_168.png` — the same cover exactly as it appears on a phone shelf",
         "3. `text/package.json` — title, cover text and opening promise", "",
         "Score `thumbnail_appeal` 1-5 for each candidate:", "",
         "| score | meaning |", "|---|---|",
         "| 5 | publish-ready: it would win a click next to the channel's current covers |",
         "| 4 | strong: one clear focal subject, an emotional or curiosity hook in the picture, and the cover text adds "
         "what the title does not say |",
         "| 3 | acceptable but forgettable |",
         "| 2 | weak: busy, vague, or the text repeats the title |",
         "| 1 | unacceptable |", "",
         "A cover can pass every geometric gate and still be dull — that is the only thing this dimension exists to catch.",
         "You may also score any other dimension, but your score can only LOWER the existing score (the exception is "
         "`thumbnail_appeal`, where your score is authoritative)."]
    if context and context.get("covers"):
        L += ["", "## Context brief (outside the packet)", "",
              "These are the channel's existing covers. Judge whether each candidate would win a click next to them. "
              "This brief is not part of the packet and its hash is recorded in the boundary log.", "",
              "| video | title | cover |", "|---|---|---|"]
        L += [f"| {c.get('video_id', '')} | {c.get('title', '')} | `{c.get('thumbnail', '')}` |" for c in context["covers"]]
    L += ["", "## Candidates", "", "| id | title | cover text | opening promise | packet |", "|---|---|---|---|---|"]
    L += [f"| {cid} | {t} | {tt} | {pr} | `{root}` |" for cid, root, t, tt, pr, _ in pkts]
    L += ["", "## Write this JSON, then stop", "", f"`{out / 'package_judgment.json'}`", "", "```json",
          json.dumps({"candidates": {_id: {"packet_manifest_sha256": sha, "scores": {"thumbnail_appeal": 4},
                                           "notes": {"thumbnail_appeal": "what makes this cover work or fail"}}
                                     for _id, _, _, _, _, sha in pkts}}, indent=1), "```", "",
          "`packet_manifest_sha256` must be copied exactly from the table below, so a judgment made for an older "
          "cover cannot be reused.", "", "| id | packet_manifest_sha256 |", "|---|---|"]
    L += [f"| {_id} | {sha} |" for _id, _, _, _, _, sha in pkts]
    return "\n".join(L) + "\n"


def cmd_candidates(a, kind: str) -> int:
    pol = read_json(a.policy or DEFAULT_POLICY)
    thr = dict(pol["hook_thresholds"]) if kind == "hook" else dict(pol["package_thresholds"]) if kind == "package" else \
        {**pol["script_thresholds"], **pol.get("cta_thresholds", {})}
    judg = read_json(a.judgment) if getattr(a, "judgment", None) else None
    loaded = sorted(m for m in AUTHOR_MODULES if m in sys.modules)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    backend = getattr(a, "backend", "auto") or "auto"
    if backend == "auto":
        backend = "heuristic"           # package judging stays local unless an agent is explicitly asked for
    context = read_json(a.context) if getattr(a, "context", None) else None
    if kind == "package" and backend == "subagent" and judg is None:
        rows, logs = [], []
        for pdir in a.packets:
            pk_ = Packet(Path(pdir))
            cid_ = pk_.manifest.get("candidate_id") or Path(pdir).name
            c_ = pk_.json("text/package.json")
            pk_.path("frames/thumbnail.jpg"); pk_.path("frames/thumbnail_168.png")
            rows.append((cid_, str(pk_.root.resolve()), c_["title"], c_.get("thumbnail_text", ""),
                         c_["opening_promise"], pk_.manifest_sha))
            logs.append(boundary_log(pk_, a, loaded, "subagent (awaiting)"))
        req = out / "package_review_request.md"
        req.write_text(_package_request_md(rows, out, context), encoding="utf-8")
        write_json(out / "boundary_log.json", {"judge": "subagent (awaiting)", "packets": logs,
                                               "context_sha256": sha256_file(Path(a.context)) if getattr(a, "context", None) else None,
                                               "statement": "awaiting an independent judgment; no heuristic scores were "
                                                            "shown to the judge"})
        print(json.dumps({"kind": kind, "verdict": "AWAITING_JUDGMENT", "request": str(req),
                          "judgment": str(out / "package_judgment.json")}))
        return 3
    results = []
    for pdir in a.packets:
        pk = Packet(Path(pdir))
        cid = pk.manifest.get("candidate_id") or Path(pdir).name
        r = score_hook_candidate(pk, pol) if kind == "hook" else score_package(pk, pol) if kind == "package" else \
            score_script_variant(pk, pol)
        cover = []
        if kind == "package" and judg is not None:
            # Phase 5: once an external judgment is in play it must cover what ships. A candidate it does not name
            # (e.g. a new id after a repackage) is not judged by heuristics alone, and an entry made for an earlier
            # packet (packet_manifest_sha256 differs) is not reused.
            jc = (judg.get("candidates") or {}).get(cid)
            if jc is None:
                cover.append({"id": "JUDGMENT.MISSING", "evidence": f"the external judgment does not cover {cid}: have the new "
                              "packet judged (packet-only) or remove package_judgment.json"})
            elif jc.get("packet_manifest_sha256") and jc["packet_manifest_sha256"] != pk.manifest_sha:
                cover.append({"id": "JUDGMENT.STALE", "evidence": f"judgment of {cid} was made for packet "
                              f"{jc['packet_manifest_sha256'][:12]}, current packet is {pk.manifest_sha[:12]}"})
            elif "thumbnail_appeal" not in (jc.get("scores") or {}):
                cover.append({"id": "JUDGMENT.UNJUDGED_COVER", "evidence": f"the external judgment of {cid} has no "
                              "thumbnail_appeal score: cover taste must be judged once a judgment is in play"})
        if kind == "package" and not cover:
            r = merge_package_judgment(r, judg, cid)
        cover = [{**c_, "fix_route": objective_route(c_)} for c_ in cover]
        fails = cover + [{**o, "fix_route": objective_route(o)} for o in r["objective"] if o["severity"] in ("blocking", "major")]
        low = [d for d, v in r["scores"].items() if v["score"] < pol.get("min_any_dimension", 3)
               and not (d in JUDGE_ONLY and judg is None)]
        fails += [{"id": d, "score": r["scores"][d]["score"], "threshold": pol.get("min_any_dimension", 3),
                   "evidence": "below min_any_dimension", "fix_route": route_for(d, r["scores"][d])}
                  for d in low if d not in thr] if kind == "package" else []
        fails += [{"id": d, "score": v["score"], "threshold": thr[d], "evidence": v["explanation"] or v["evidence"][:2],
                   "fix_route": route_for(d, v)}
                  for d, v in r["scores"].items() if v["score"] < thr[d] and not (d in JUDGE_ONLY and judg is None)]
        judge = "heuristic+external" if kind == "package" and judg else "heuristic"
        results.append({"candidate": cid, "verdict": "PASS" if not fails else "FAIL", "judge": judge,
                        "scores": r["scores"], "objective": r["objective"], "failures": fails,
                        "packet_manifest_sha256": pk.manifest_sha, "boundary": boundary_log(pk, a, loaded, "heuristic")})
    write_json(out / f"{kind}_reviews.json", {"kind": kind, "thresholds": thr, "results": results})
    print(json.dumps({"kind": kind, "results": [{"candidate": r["candidate"], "verdict": r["verdict"],
                                                 "scores": {d: v["score"] for d, v in r["scores"].items()},
                                                 "failures": [f["id"] for f in r["failures"]]} for r in results]}))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("review")
    r.add_argument("--packet", required=True); r.add_argument("--out", required=True)
    r.add_argument("--backend", default="auto", choices=["auto", "heuristic", "anthropic", "subagent"])
    r.add_argument("--judgment", help="merge an externally produced judgment (human or fresh agent)")
    r.add_argument("--policy")
    for k in ("review-hooks", "review-script", "review-package"):
        c = sub.add_parser(k)
        c.add_argument("--packets", nargs="+", required=True); c.add_argument("--out", required=True); c.add_argument("--policy")
        if k == "review-package":
            c.add_argument("--judgment", help="external judge scores (fresh agent/human, packet-only): {candidates: {id: {scores, notes}}}")
            c.add_argument("--backend", default="auto", choices=["auto", "heuristic", "subagent"],
                           help="subagent: write package_review_request.md and exit 3 (AWAITING_JUDGMENT) until the "
                                "judgment is written; P6.2")
            c.add_argument("--context", help="optional context brief outside the packet (the channel's own covers); hashed")
    a = ap.parse_args()
    try:
        if a.cmd in ("review-hooks", "review-script", "review-package"):
            return cmd_candidates(a, {"review-hooks": "hook", "review-script": "script", "review-package": "package"}[a.cmd])
        return cmd_review(a)
    except BoundaryError as exc:
        print(json.dumps({"verdict": "ERROR", "boundary_violation": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
