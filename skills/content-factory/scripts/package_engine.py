#!/usr/bin/env python3
"""package_engine — Phase 4 packaging: choose the strongest complete package (title + thumbnail + opening promise +
description/caption + hashtags + CTA alignment) for ONE finished video.

  package_engine.py select --candidates videos/v01/package/package_candidates.json --script script.json
                           --timing timing.json --final final.mp4 --dossier dossier.json --out-dir videos/v01/package
                           [--palette "#ffd23f,#e8452c,..."] [--judgment judgment.json] [--policy review-policy.json]

Contract `package_candidates` (cf_common): ≥3 candidates, each with a strategy, a title, an opening promise (the first
caption line — the package's hook; the video's own spoken hook is fixed), a doodle thumbnail SVG (1080×1920) with its
2-4 word text and the dossier facts it depicts, description, hashtags, the fact ids its claims rest on, optional caption CTA.

Steps (all deterministic): render every thumbnail with the doodle engine → measure geometry, contrast at 168 px width,
dead space, clutter → title/claim/clickbait/payoff/CTA gates → set-level diversity (strategy, title, thumbnail text,
opening promise, perceptual thumbnail hash) → one review packet per candidate (finished copy + images + transcript +
evidence + measurements; never the strategy, concept, rationale or SVG) → `reviewer.py review-package` in its own
process → select the PASS candidate with the highest total review score.

Writes OUT/package_selection.json (selected + rejected-with-reasons), OUT/package_report.md, OUT/candidates/<id>/
(thumbnail.png/.jpg, thumbnail_168.png, checks.json), OUT/review/ (packets + package_reviews.json).
Exit 0 when a package is selected, 2 otherwise.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import ffmpeg_bin, read_json, skills_root, validate_artifact, write_json  # noqa: E402

ROOT = skills_root()
sys.path.append(str(ROOT / "video-production" / "scripts"))          # doodle_engine (thumbnail renderer)
sys.path.append(str(ROOT / "video-quality-assurance" / "scripts"))   # review_packet.write_packet, text utilities
POLICY = ROOT / "video-quality-assurance" / "references" / "review-policy.json"


def channel_covers(db: Path | None, runs_dir: Path | None, limit: int = 12) -> dict:
    """P6.2 context brief: the channel's own recent covers, kept OUTSIDE the review packet (P4.2). The judge may use
    them to answer "would this win a click next to what the channel already publishes"; the brief is hashed in the
    boundary log so the packet itself stays free of creative state. Best-effort: no database, no brief."""
    if not db or not Path(db).exists():
        return {"covers": []}
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
        rows = con.execute("SELECT run_id, video_id, COALESCE(title, '') FROM videos "
                           "ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        con.close()
    except Exception:
        return {"covers": []}
    covers = []
    for rid, vid, title in rows:
        thumb = ""
        if runs_dir:
            hits = sorted(Path(runs_dir).glob(f"{rid}/videos/{vid}/*/thumbnail.jpg"))
            thumb = str(hits[0].resolve()) if hits else ""
        covers.append({"video_id": vid, "title": title, "thumbnail": thumb})
    return {"covers": covers, "source": "content memory titles + local package covers", "db": str(db)}

CLICKBAIT = ["you won't believe", "you wont believe", "doctors hate", "shocking", "gone wrong", "insane", "mind-blowing",
             "mind blowing", "will blow your mind", "nobody tells you", "nobody is talking", "they don't want you to know",
             "this one trick", "one weird trick", "unbelievable", "crazy", "must see", "must-see", "guaranteed", "100%"]
ABSOLUTES = ["always", "every", "everyone", "everybody", "guaranteed", "proven", "proves", "prove", "definitely",
             "completely", "totally", "forever", "instantly", "cure", "cures", "miracle", "only way"]
RISK = ["cause", "causes", "caused", "causing", "damage", "damages", "harm", "harmful", "dangerous", "danger", "safe",
        "unsafe", "bad", "arthritis", "cancer", "kill", "kills", "ruin", "ruins", "destroy", "destroys", "injury", "link",
        "linked", "risk", "healthy", "unhealthy", "toxic", "poison", "disease"]
RELATIONAL = {"cause", "causes", "caused", "causing", "link", "linked", "risk"}   # a question may ask about a relation
ASSERT = RELATIONAL | {"damage", "damages", "harm", "harmful", "dangerous", "bad", "ruin", "ruins", "destroy", "destroys",
                      "kill", "kills", "unsafe", "toxic", "gives", "give", "leads", "lead"}   # words that turn a topic into a claim
NEG_RE = re.compile(r"n't\b|\b(no|not|never|without|nothing|myth|false)\b", re.I)
CTA_KINDS = {"comment": r"\b(comment|tell me|let me know|below|reply)\b", "follow": r"\bfollow\b", "subscribe": r"\bsubscrib",
             "like": r"\b(like this|hit like|leave a like)\b", "share": r"\b(share|send this)\b", "save": r"\bsave (this|it)\b",
             "part_2": r"\bpart ?(2|two)\b", "profile": r"\b(link in bio|my profile|my channel)\b"}
COMPATIBLE = {"comment": {"comment", "question"}, "question": {"comment", "question"}}


FUNC = {"what", "why", "how", "when", "where", "who", "which", "does", "doe", "did", "can", "will", "just", "really", "actually",
        "actual", "still", "here", "there", "then", "than", "about", "into", "inside", "out", "over", "one", "your", "yours", "you",
        "more", "less", "most", "least"}


def words_of(text: str) -> list[str]:
    from reviewer import words_of as w   # same stemming/normalisation the reviewer uses
    return w(text)


def topic_words(text: str) -> set[str]:
    """Content words that carry a topic (question words and fillers removed) — for 'is this about the video' checks."""
    return {x for x in words_of(text) if x not in FUNC}


def jac(a, b) -> float:
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 0.0


def phrase_hits(text: str, phrases: list[str]) -> list[str]:
    t = " " + re.sub(r"[^a-z0-9%' -]", " ", text.lower()) + " "
    return [p for p in phrases if re.search(r"(?<![a-z])" + re.escape(p) + r"(?![a-z])", t)]


# ----------------------------------------------------------------------------- claims (title, thumbnail, copy)
def claim_check(text: str, cited: list[dict], where: str) -> list[dict]:
    """Every number, absolute and health/causal term must be carried by a cited dossier fact, with the same polarity
    (a fact saying 'no link to arthritis' cannot support 'cracking causes arthritis'). Questions are not assertions
    for polarity, but their claim terms still need a cited fact."""
    out, ctext = [], " ".join(f["claim"] for f in cited).lower()
    cwords = set(words_of(ctext))
    for n in re.findall(r"\d+(?:[.,]\d+)?", text):
        # Phase 5: whole numbers only — a substring match let "2" pass on a fact that says "200"
        if not re.search(r"(?<![\d.,])" + re.escape(n) + r"(?![\d]|[.,]\d)", ctext):
            out.append({"id": "CLAIM.UNSUPPORTED_NUMBER", "severity": "blocking", "where": where,
                        "evidence": f"'{n}' in '{text}' is not in any cited fact"})
    for a in phrase_hits(text, ABSOLUTES):
        if not set(words_of(a)) <= cwords:
            out.append({"id": "CLAIM.UNSUPPORTED_ABSOLUTE", "severity": "blocking", "where": where,
                        "evidence": f"'{a}' in '{text}' — no cited fact says so"})
    question = text.strip().endswith("?")
    for r in phrase_hits(text, RISK):
        st = words_of(r)
        sup = [f for f in cited if all(any(fw == s or (len(s) >= 5 and fw.endswith(s)) for fw in words_of(f["claim"])) for s in st)]
        if not sup and question and r in RELATIONAL:
            continue                     # "Does X cause Y?" asks; the object (Y) still needs a cited fact
        if not sup:
            out.append({"id": "CLAIM.UNSUPPORTED", "severity": "blocking", "where": where,
                        "evidence": f"'{r}' in '{text}' — no cited fact mentions it"})
        elif not question and all(NEG_RE.search(f["claim"]) for f in sup) and not NEG_RE.search(text) and \
                set(re.findall(r"[a-z]+", text.lower())) & ASSERT:
            out.append({"id": "CLAIM.CONTRADICTS_EVIDENCE", "severity": "blocking", "where": where,
                        "evidence": f"'{text}' asserts '{r}' but the cited fact negates it: '{sup[0]['claim'][:90]}'"})
    return out


def clickbait_check(text: str, where: str, caps: bool = True, caps_max: int = 1) -> list[dict]:
    out = [{"id": "CLICKBAIT.PHRASE", "severity": "major", "where": where, "evidence": f"'{p}' in '{text}'"}
           for p in phrase_hits(text, CLICKBAIT)]
    if text.count("!") >= 2:
        out.append({"id": "CLICKBAIT.EXCLAMATION", "severity": "major", "where": where, "evidence": text})
    shout = [w for w in re.findall(r"[A-Za-z']+", text) if len(w) >= 4 and w.isupper()]
    if caps and len(shout) > caps_max:
        out.append({"id": "CLICKBAIT.CAPS", "severity": "major", "where": where, "evidence": f"shouting {shout}"})
    return out


def cta_kinds(text: str) -> set[str]:
    return {k for k, rx in CTA_KINDS.items() if re.search(rx, text.lower())}


# ----------------------------------------------------------------------------- thumbnail render + measurement
def render_thumb(svg_path: Path, palette: list[str], out: Path, pol: dict, canvas: list | None = None) -> dict:
    import doodle_engine as de
    import numpy as np
    import skia
    from PIL import Image
    if canvas:                       # v3.3: 16:9 long-form thumbnail renders at the run canvas (1920x1080)
        de.set_canvas(int(canvas[0]), int(canvas[1]))
    svg = svg_path.read_text(encoding="utf-8")
    sc = de.DoodleScene(svg, palette, [], 4.0, {"wobble": 2.6}, scene_id="thumb", camera={"drift": "none"})
    t = 3.95
    surf = skia.Surface.MakeRasterN32Premul(de.W, de.H)   # v3.2 speed fix: same pixels as MakeRaster(ImageInfo), ~50x faster
    sc.draw(surf.getCanvas(), t, de.Paper(), camera=False)
    png = out / "thumbnail.png"
    surf.makeImageSnapshot().save(str(png), skia.kPNG)
    im = Image.open(png).convert("RGB")
    im.save(out / "thumbnail.jpg", "JPEG", quality=92, optimize=True)
    cw = pol["thumb_check_width"]
    small = im.resize((cw, round(cw * im.height / im.width)), Image.LANCZOS)
    small.save(out / "thumbnail_168.png")
    # ---- geometry of the settled frame (no camera)
    cx0, cy0, cx1, cy1 = pol["core_safe"]
    core_area = (cx1 - cx0) * (cy1 - cy0)
    det = lambda T: abs(T.getScaleX() * T.getScaleY() - T.getSkewX() * T.getSkewY()) ** 0.5  # noqa: E731
    texts, shapes, unsettled = [], [], []
    for a, T, settled in sc._walk_matrices(t, skia.Matrix()):
        if not a.drawables or a is sc.root:
            continue
        if not settled:
            unsettled.append(a.id)
            continue
        r = skia.Rect.MakeEmpty()
        for d in a.drawables:
            if d.kind == "text":
                tb = skia.Rect.MakeEmpty()
                for gp, _x, _y, _ci in d.glyphs:
                    tb.join(T.mapRect(gp.computeTightBounds()))
                texts.append({"actor": a.id, "text": d.text, "size_px": round(d.font_size * det(T), 1),
                              "bbox": [round(tb.left()), round(tb.top()), round(tb.right()), round(tb.bottom())]})
            else:
                r.join(T.mapRect(d.bounds))
        if not r.isEmpty():
            shapes.append({"actor": a.id, "bbox": [r.left(), r.top(), r.right(), r.bottom()], "area": r.width() * r.height()})
    # top-level shapes only (drop shapes inside a larger one)
    tops = [s for s in shapes if not any(o is not s and o["area"] > s["area"] and o["bbox"][0] <= s["bbox"][0] + 2 and
                                         o["bbox"][1] <= s["bbox"][1] + 2 and o["bbox"][2] >= s["bbox"][2] - 2 and
                                         o["bbox"][3] >= s["bbox"][3] - 2 for o in shapes)]
    tops.sort(key=lambda s: -s["area"])
    main = tops[0] if tops else None

    def inter(b, box):
        return max(0.0, min(b[2], box[2]) - max(b[0], box[0])) * max(0.0, min(b[3], box[3]) - max(b[1], box[1]))
    core = pol["core_safe"]
    subj_h = (max(0.0, min(main["bbox"][3], cy1) - max(main["bbox"][1], cy0)) / (cy1 - cy0)) if main else 0.0
    subj_in = inter(main["bbox"], core) / max(main["area"], 1) if main else 0.0
    second = tops[1]["area"] / main["area"] if len(tops) > 1 and main else 0.0
    clutter = sum(1 for s in tops if s["area"] < 0.005 * core_area)
    # ---- pixels: background = most common border colour; ink share per 3x3 cell of the core square
    a_ = np.asarray(im).astype(np.int16)
    border = np.concatenate([a_[:8].reshape(-1, 3), a_[-8:].reshape(-1, 3), a_[:, :8].reshape(-1, 3), a_[:, -8:].reshape(-1, 3)])
    vals, counts = np.unique((border // 8).reshape(-1, 3), axis=0, return_counts=True)
    bg = vals[counts.argmax()] * 8 + 4
    ink = (np.abs(a_ - bg).sum(axis=2) > 60)
    cells = []
    for j in range(3):
        for i in range(3):
            x0 = cx0 + (cx1 - cx0) * i // 3; x1 = cx0 + (cx1 - cx0) * (i + 1) // 3
            y0 = cy0 + (cy1 - cy0) * j // 3; y1 = cy0 + (cy1 - cy0) * (j + 1) // 3
            cells.append(round(float(ink[y0:y1, x0:x1].mean()), 3))
    occupied = sum(c >= pol["cell_ink_min"] for c in cells)
    # ---- text contrast measured on the 168-px image (what a phone shelf shows)
    s_ = np.asarray(small).astype(np.float64) / 255.0
    lin = np.where(s_ <= 0.04045, s_ / 12.92, ((s_ + 0.055) / 1.055) ** 2.4)
    lum = lin @ np.array([0.2126, 0.7152, 0.0722])
    k = cw / im.width
    for tx in texts:
        x0, y0, x1, y1 = [int(round(v * k)) for v in tx["bbox"]]
        patch = lum[max(0, y0):max(y0 + 1, y1), max(0, x0):max(x0 + 1, x1)]
        lo, hi = (float(np.percentile(patch, 8)), float(np.percentile(patch, 92))) if patch.size else (0.0, 0.0)
        tx["contrast_168"] = round((hi + 0.05) / (lo + 0.05), 2)
        tx["height_168_px"] = round(tx["size_px"] * k, 1)
        tb_ = [tx["bbox"][0] - 24, tx["bbox"][1] - 24, tx["bbox"][2] + 24, tx["bbox"][3] + 24]   # breathing room
        tarea = max((tb_[2] - tb_[0]) * (tb_[3] - tb_[1]), 1)
        tx["overlap"] = round(min(1.0, sum(inter(s["bbox"], tb_) for s in shapes if s["actor"] != tx["actor"]) / tarea), 3)
        tx["inside_core"] = inter(tx["bbox"], core) >= 0.98 * max((tx["bbox"][2] - tx["bbox"][0]) * (tx["bbox"][3] - tx["bbox"][1]), 1)
        tx["inside_yt_band"] = inter(tx["bbox"], pol["yt_band"]) >= 0.98 * max((tx["bbox"][2] - tx["bbox"][0]) * (tx["bbox"][3] - tx["bbox"][1]), 1)
    g = np.asarray(small.convert("L").resize((9, 8), Image.LANCZOS)).astype(np.int16)
    dhash = "".join("1" if v else "0" for v in (g[:, 1:] > g[:, :-1]).flatten())
    return {"size": list(im.size), "texts": texts, "words": sum(len(t_["text"].split()) for t_ in texts),
            "text_words": " ".join(t_["text"] for t_ in texts), "unsettled": unsettled,
            "main_subject": main["actor"] if main else None, "main_bbox": [round(v) for v in main["bbox"]] if main else None,
            "subject_core_height": round(subj_h, 3), "subject_inside_core": round(subj_in, 3), "second_subject_ratio": round(second, 3),
            "shapes": len(tops), "clutter_small_shapes": clutter, "cell_ink": cells, "occupied_cells": occupied,
            "dead_cells": 9 - occupied, "dhash": dhash, "warnings": list(sc.warnings)}


def thumb_checks(c: dict, m: dict, pol: dict, cited: list[dict], ids: set, spoken: set) -> list[dict]:
    out, th = [], c["thumbnail"]

    def chk(cid, ok, sev, ev):
        if not ok:
            out.append({"id": cid, "severity": sev, "where": "thumbnail", "evidence": ev})
    W, H = pol["thumb_size"]
    chk("THUMB.SIZE", m["size"] == [W, H], "blocking", f"{m['size']} (needs {W}x{H})")
    chk("THUMB.SETTLED", not m["unsettled"], "major", f"elements still animating at capture: {m['unsettled']}")
    declared = th.get("text", "").strip()
    chk("THUMB.TEXT_MATCHES", [w.lower() for w in re.findall(r"[\w'?]+", declared)] ==
        [w.lower() for w in re.findall(r"[\w'?]+", m["text_words"])], "major",
        f"declared '{declared}' but the image says '{m['text_words']}'")
    chk("THUMB.WORDS", m["words"] <= pol["thumb_words_max"], "major", f"{m['words']} words (max {pol['thumb_words_max']})")
    small = [(t["text"], t["size_px"]) for t in m["texts"] if t["size_px"] < pol["thumb_text_min_px"]]
    chk("THUMB.TEXT_SIZE", not small, "major", f"text below {pol['thumb_text_min_px']} px (unreadable at "
        f"{pol['thumb_check_width']} px wide): {small}")
    if m["texts"]:
        chk("THUMB.HEADLINE_SIZE", max(t["size_px"] for t in m["texts"]) >= pol["thumb_headline_min_px"], "major",
            f"largest text {max(t['size_px'] for t in m['texts'])} px < {pol['thumb_headline_min_px']}")
    low = [(t["text"], t["contrast_168"]) for t in m["texts"] if t["contrast_168"] < pol["thumb_contrast_min"]]
    chk("THUMB.CONTRAST", not low, "major", f"contrast at {pol['thumb_check_width']} px below {pol['thumb_contrast_min']}: {low}")
    out_core = [t["text"] for t in m["texts"] if not t["inside_core"]]
    chk("THUMB.TEXT_CORE_SAFE", not out_core, "major", f"text outside the central square (cropped on 1:1/3:4 covers): {out_core}")
    chk("THUMB.SUBJECT", m["main_subject"] is not None and m["subject_core_height"] >= pol["subject_min_core_height"], "major",
        f"main subject {m['main_subject']} fills {m['subject_core_height']:.0%} of the core height (needs ≥{pol['subject_min_core_height']:.0%})")
    chk("THUMB.SUBJECT_CORE_SAFE", m["subject_inside_core"] >= pol["subject_inside_core_min"], "major",
        f"{m['subject_inside_core']:.0%} of the subject inside the central square")
    chk("THUMB.SINGLE_SUBJECT", m["second_subject_ratio"] <= pol["second_subject_max_ratio"], "major",
        f"second shape is {m['second_subject_ratio']:.0%} of the main subject — no single focal subject")
    over = [(t["text"], t["overlap"]) for t in m["texts"] if t["overlap"] > 0.03]
    chk("THUMB.TEXT_OVERLAP", not over, "major", f"text drawn over other shapes (share of text box covered): {over}")
    chk("THUMB.DEAD_SPACE", m["dead_cells"] <= pol["dead_cells_max"], "major", f"{m['dead_cells']}/9 empty cells in the core square")
    chk("THUMB.CLUTTER", m["clutter_small_shapes"] <= pol["clutter_max"], "major",
        f"{m['clutter_small_shapes']} tiny shapes (details lost at thumbnail size)")
    bad = [d for d in th.get("depicts", []) if d not in ids]
    chk("THUMB.DEPICTS_KNOWN", bool(th.get("depicts")) and not bad, "blocking",
        f"thumbnail depicts {th.get('depicts')} — unknown or none: {bad}")
    if declared:
        tw = set(words_of(declared))
        chk("THUMB.NOT_IN_VIDEO", len(tw & spoken) >= max(1, (len(tw) + 1) // 2), "major",
            f"thumbnail words {sorted(tw - spoken)} are never said in the video (promise the video does not keep)")
        out += [dict(x, where="thumbnail") for x in claim_check(declared, cited, "thumbnail")]
        out += clickbait_check(declared, "thumbnail", caps=False)
        if cta_kinds(declared):
            out.append({"id": "THUMB.CTA", "severity": "major", "where": "thumbnail", "evidence": f"call to action on the thumbnail: '{declared}'"})
    return out


# ----------------------------------------------------------------------------- per-candidate copy gates
def copy_checks(c: dict, pol: dict, cited: list[dict], ids: set, tr: dict, video_cta: dict) -> list[dict]:
    out = []

    def chk(cid, ok, sev, ev, where="title"):
        if not ok:
            out.append({"id": cid, "severity": sev, "where": where, "evidence": ev})
    title, promise, desc = c["title"].strip(), c["opening_promise"].strip(), c["description"].strip()
    bad_ids = [i for i in c["claim_ids"] if i not in ids]
    chk("CLAIM.UNKNOWN_FACT", not bad_ids, "blocking", f"claim_ids not in the dossier: {bad_ids}", "package")
    chk("TITLE.LENGTH", len(title) <= pol["title_max_chars"], "major", f"{len(title)} chars (mobile max {pol['title_max_chars']})")
    chk("TITLE.WORDS", len(title.split()) <= pol["title_max_words"], "major", f"{len(title.split())} words")
    chk("PROMISE.LENGTH", len(promise) <= pol["opening_promise_max_chars"], "major", f"{len(promise)} chars", "opening_promise")
    chk("DESC.LENGTH", len(desc) <= pol["description_max_chars"], "major", f"{len(desc)} chars", "description")
    lo, hi = pol["hashtags"]
    tags = c["hashtags"]
    chk("TAGS.FORMAT", lo <= len(tags) <= hi and all(re.fullmatch(r"#[A-Za-z0-9_]+", t) for t in tags) and
        len({t.lower() for t in tags}) == len(tags), "major", f"{tags}", "hashtags")
    tw = set(words_of(tr["text"]))
    chk("TAGS.RELEVANT", any(set(words_of(re.sub(r"([a-z])([A-Z])", r"\1 \2", t[1:]))) & tw or
                             any(x in t.lower() for x in tw if len(x) > 4) for t in tags), "major",
        f"no hashtag relates to what the video says: {tags}", "hashtags")
    for where, text in (("title", title), ("opening_promise", promise), ("description", desc)):
        out += claim_check(text, cited, where)
        out += clickbait_check(text, where, caps=(where == "title"), caps_max=pol["title_caps_words_max"])
    # promise/payoff: the title must be about what the video actually says; its key words must be paid off
    sents = tr["sentences"]
    k = max(1, round(len(sents) * 0.55))
    payoff = set(words_of(" ".join(s["text"] for s in sents[len(sents) - k:])))
    first = set(words_of(" ".join(s["text"] for s in sents[:2])))
    tt = topic_words(title)
    chk("TITLE.OFF_TOPIC", bool(tt & tw), "blocking", f"no title word is spoken in the video: '{title}'")
    chk("TITLE.PAYOFF", bool(tt & payoff), "major", f"title words {sorted(tt)} never come back in the payoff half")
    unsaid = sorted(tt - tw)
    chk("TITLE.NOT_IN_VIDEO", len(unsaid) <= 1 and not any(re.search(r"\d", w) or w in set(words_of("0 1 2 3 4 5 6 7 8 9 10 12 15 20 30 40 50 60 90 100")) for w in unsaid),
        "major", f"title promises {unsaid}, which the video never says")
    chk("PROMISE.MATCHES_HOOK", bool(set(words_of(promise)) & first), "major",
        f"opening promise shares nothing with the video's opening ('{sents[0]['text'] if sents else ''}')", "opening_promise")
    chk("DESC.ON_TOPIC", len(set(words_of(desc)) & tw) >= 3, "major", "description barely relates to the video", "description")
    # CTA alignment: public copy may only reinforce the video's own CTA, never ask for something else
    vt = video_cta.get("type") if video_cta.get("needed") else None
    allowed = COMPATIBLE.get(vt, {vt}) if vt else set()
    kinds = cta_kinds(" ".join([title, promise, desc, c.get("caption_cta", "")]))
    if c.get("caption_cta") and c["caption_cta"].strip().endswith("?"):
        kinds.add("comment")
    conflict = sorted(kinds - allowed) if vt else sorted(kinds - {"comment", "question"})
    chk("CTA.PKG_CONFLICT", not conflict, "major", f"copy asks for {conflict}; the video's CTA is {vt or 'none'}", "caption_cta")
    chk("CTA.PKG_SINGLE", len(kinds) <= 1, "major", f"{sorted(kinds)} — more than one ask", "caption_cta")
    return out


def diversity(cands: list[dict], meas: dict, pol: dict) -> tuple[list, dict]:
    pairs, issues = [], []
    for i, a in enumerate(cands):
        for b in cands[i + 1:]:
            ta = jac(words_of(a["title"]), words_of(b["title"]))
            tb = jac(words_of(a["thumbnail"]["text"]), words_of(b["thumbnail"]["text"])) if a["thumbnail"]["text"] and b["thumbnail"]["text"] else 0.0
            tp = jac(words_of(a["opening_promise"]), words_of(b["opening_promise"]))
            ha, hb = meas[a["id"]]["dhash"], meas[b["id"]]["dhash"]
            dh = sum(x != y for x, y in zip(ha, hb))
            p = {"a": a["id"], "b": b["id"], "title_jaccard": round(ta, 2), "thumb_text_jaccard": round(tb, 2),
                 "promise_jaccard": round(tp, 2), "thumb_dhash_distance": dh, "same_strategy": a["strategy"] == b["strategy"]}
            pairs.append(p)
            why = [x for x, bad in (("same strategy", p["same_strategy"]), (f"titles {ta:.2f} similar", ta > pol["title_jaccard_max"]),
                                    (f"thumbnail text {tb:.2f} similar", tb > pol["thumb_text_jaccard_max"]),
                                    (f"opening promises {tp:.2f} similar", tp > pol["promise_jaccard_max"]),
                                    (f"thumbnails look alike (dHash {dh})", dh < pol["thumb_dhash_min"])) if bad]
            if why:
                issues.append({"pair": [a["id"], b["id"]], "why": why})
    return issues, {"pairs": pairs, "strategies": sorted({c["strategy"] for c in cands})}


# ----------------------------------------------------------------------------- command
def _aspect_policy(pol: dict, aspect: str) -> dict:
    """v3.3: a 16:9 long-form thumbnail has its own size and safe area (the 9:16 core-square rule only protects
    vertical covers from mobile crops). Returns a shallow copy; the base policy is not mutated."""
    p = dict(pol)
    if aspect == "wide":
        p["thumb_size"] = pol.get("thumb_size_wide", [1920, 1080])
        p["core_safe"] = pol.get("core_safe_wide", [160, 60, 1760, 1020])
        p["yt_band"] = pol.get("yt_band_wide", p.get("yt_band"))
    return p


def cmd_select(a) -> int:
    from review_packet import write_packet
    pol_all = read_json(a.policy or POLICY)
    pol = pol_all["packaging"]
    aspect = getattr(a, "aspect", "vertical")
    pol = _aspect_policy(pol, aspect)
    canvas = [1920, 1080] if aspect == "wide" else [1080, 1920]
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cpath = Path(a.candidates)
    d = read_json(cpath)
    sel_path = out / "package_selection.json"
    errs = validate_artifact(d, "package_candidates")
    if errs:
        write_json(sel_path, {"status": "failed", "set_checks": [{"id": "PKG.SCHEMA", "severity": "blocking", "evidence": "; ".join(errs[:6])}],
                              "selected": None, "rejected": []})
        print(json.dumps({"status": "failed", "schema": errs[:6]}))
        return 2
    cands = d["candidates"]
    script, tm = read_json(a.script), read_json(a.timing)
    dossier = read_json(a.dossier) if a.dossier and Path(a.dossier).exists() else {"facts": [], "sources": []}
    facts = {f["id"]: f for f in dossier.get("facts", [])}
    ids = set(facts)
    tr = {"text": " ".join(s["text"] for s in tm["sentences"]), "duration_s": tm.get("duration_s"),
          "sentences": [{"text": s["text"], "start": s["start"], "end": s["end"]} for s in tm["sentences"]]}
    video_cta = script.get("cta") or {}
    on_screen = " ".join(b.get("on_screen", "") for b in script.get("beats", []))
    palette = [x.strip() for x in a.palette.split(",")] if a.palette else ["#ffd23f", "#e8452c", "#3b82c4", "#2f9e44", "#f783ac"]
    first = out / "review" / "video_first_frame.png"
    first.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg_bin(), "-y", "-v", "error", "-i", a.final, "-frames:v", "1", str(first)], check=True)
    meas, checks = {}, {}
    seen = set()
    for c in cands:
        if c["id"] in seen:
            raise SystemExit(f"duplicate candidate id {c['id']}")
        seen.add(c["id"])
        cdir = out / "candidates" / c["id"]
        cdir.mkdir(parents=True, exist_ok=True)
        cited = [facts[i] for i in c["claim_ids"] + c["thumbnail"].get("depicts", []) if i in facts]
        svg = (cpath.parent / c["thumbnail"]["svg"]).resolve()
        if not svg.exists():
            checks[c["id"]] = [{"id": "THUMB.MISSING", "severity": "blocking", "where": "thumbnail", "evidence": str(c["thumbnail"]["svg"])}]
            meas[c["id"]] = {"dhash": "0" * 64, "texts": [], "words": 0}
            continue
        meas[c["id"]] = render_thumb(svg, palette, cdir, pol, canvas)
        checks[c["id"]] = thumb_checks(c, meas[c["id"]], pol, cited, ids, set(words_of(tr["text"] + " " + on_screen))) + \
            copy_checks(c, pol, cited, ids, tr, video_cta)
        write_json(cdir / "checks.json", {"candidate": c["id"], "measurements": meas[c["id"]], "checks": checks[c["id"]]})
    div_issues, div = diversity(cands, meas, pol)
    viable = [c["id"] for c in cands if not any(x["severity"] in ("blocking", "major") for x in checks[c["id"]])]
    set_checks = []
    if len(cands) < pol["min_candidates"]:
        set_checks.append({"id": "PKG.CANDIDATES", "severity": "blocking", "evidence": f"{len(cands)} candidates (need {pol['min_candidates']})"})
    from itertools import combinations
    dup = {frozenset(i["pair"]) for i in div_issues}
    distinct = next((list(s) for n in range(len(viable), pol["min_candidates"] - 1, -1) for s in combinations(viable, n)
                     if not any(frozenset(pr) in dup for pr in combinations(s, 2))), None)
    div["distinct_viable_set"] = distinct
    div["near_duplicates"] = div_issues
    if not distinct:
        set_checks.append({"id": "PKG.DIVERSITY", "severity": "blocking",
                           "evidence": f"no {pol['min_candidates']} viable candidates are mutually distinct; near-duplicate pairs: {div_issues}"})
    for i in div_issues:
        for cid in i["pair"]:
            if distinct and cid not in distinct:
                checks[cid].append({"id": "PKG.NEAR_DUPLICATE", "severity": "major", "where": "package",
                                    "evidence": f"too close to {[x for x in i['pair'] if x != cid][0]}: {i['why']}"})
    if len(viable) < pol["min_viable"]:
        set_checks.append({"id": "PKG.VIABLE", "severity": "blocking",
                           "evidence": f"only {viable} pass every deterministic gate (need {pol['min_viable']} real alternatives)"})
    # ---- independent review: one packet per candidate, reviewer in its own process
    packets = []
    for c in cands:
        if c["id"] not in meas or "size" not in meas[c["id"]]:
            continue
        cdir, pk = out / "candidates" / c["id"], out / "review" / "packets" / c["id"]
        cited = sorted(set(c["claim_ids"]) | set(c["thumbnail"].get("depicts", [])))
        m = {k: v for k, v in meas[c["id"]].items() if k not in ("dhash", "warnings")}
        files = {"text/package.json": {"title": c["title"], "thumbnail_text": c["thumbnail"]["text"],
                                        "opening_promise": c["opening_promise"], "description": c["description"],
                                        "hashtags": c["hashtags"], "caption_cta": c.get("caption_cta", "")},
                 "frames/thumbnail.jpg": cdir / "thumbnail.jpg", "frames/thumbnail_168.png": cdir / "thumbnail_168.png",
                 "frames/video_first_frame.png": first,
                 "text/transcript.json": tr,
                 "text/cta.json": {"present": bool(video_cta.get("needed")), **({k: video_cta.get(k) or "" for k in
                                   ("type", "placement", "modality", "spoken", "on_screen")} if video_cta.get("needed") else {})},
                 "evidence/claims.json": {"facts": [{k: f[k] for k in ("id", "claim", "source_ids", "risk") if k in f}
                                                    for f in dossier.get("facts", [])], "package_claim_ids": cited},
                 "measurements/package_checks.json": {"checks": checks[c["id"]], "thumbnail": m}}
        man = write_packet(pk, files, "package_candidate")
        man["candidate_id"] = c["id"]
        write_json(pk / "manifest.json", man)
        packets.append(str(pk))
    rv = out / "review"
    cmd = [sys.executable, str(ROOT / "video-quality-assurance" / "scripts" / "reviewer.py"), "review-package", "--packets",
           *packets, "--out", str(rv)] + (["--policy", a.policy] if a.policy else []) + (["--judgment", a.judgment] if a.judgment else [])
    backend = getattr(a, "review_backend", "auto") or "auto"
    if backend != "auto":
        cmd += ["--backend", backend]
    ctx = Path(a.context) if getattr(a, "context", None) else None
    if ctx is None and getattr(a, "db", None):
        cov = channel_covers(Path(a.db), Path(a.runs_dir) if getattr(a, "runs_dir", None) else None)
        if cov["covers"]:
            ctx = out / "channel_covers.json"
            write_json(ctx, cov)
    if ctx is not None and ctx.exists():
        cmd += ["--context", str(ctx)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode == 3:                    # P6.2: the reviewer is waiting for an independent judgment
        req = rv / "package_review_request.md"
        set_checks.append({"id": "PKG.AWAITING_JUDGMENT", "severity": "blocking",
                           "evidence": f"awaiting an independent cover judgment: give ONLY the packet folders to a fresh "
                                       f"reviewer (request: {req.relative_to(out).as_posix()}), write "
                                       "package_judgment.json, then re-run"})
        res = {"version": 1, "status": "awaiting_judgment", "candidates_file": cpath.name, "set_checks": set_checks,
               "diversity": div, "viable": viable, "table": [], "selected": None, "rejected": [],
               "review": {"file": None, "judges": ["awaiting"], "request": req.relative_to(out).as_posix()}}
        write_json(sel_path, res)
        (out / "package_report.md").write_text(report_md(res), encoding="utf-8")
        print(json.dumps({"status": "awaiting_judgment", "request": str(req),
                          "judgment": str(out / "package_judgment.json")}))
        return 3
    if p.returncode != 0 or not (rv / "package_reviews.json").exists():
        set_checks.append({"id": "PKG.REVIEWER_ERROR", "severity": "blocking", "evidence": (p.stderr or p.stdout)[-400:]})
        reviews = {}
    else:
        reviews = {r["candidate"]: r for r in read_json(rv / "package_reviews.json")["results"]}
    rows = []
    for c in cands:
        det_fail = [x for x in checks[c["id"]] if x["severity"] in ("blocking", "major")]
        r = reviews.get(c["id"], {"verdict": "FAIL", "scores": {}, "failures": [{"id": "not reviewed"}]})
        total = sum(v["score"] for v in r["scores"].values())
        ok = not det_fail and r["verdict"] == "PASS"
        reasons = [f"{x['id']} ({x['where']}): {x['evidence']}" for x in det_fail] + \
                  [f"review {f['id']}: {f.get('score', '')}<{f.get('threshold', '')}" if "threshold" in f else f"review {f['id']}"
                   for f in r.get("failures", []) if not any(f["id"] == x["id"] for x in det_fail)]
        rows.append({"id": c["id"], "strategy": c["strategy"], "title": c["title"], "thumbnail_text": c["thumbnail"]["text"],
                     "passed": ok, "review_verdict": r["verdict"], "scores": {k: v["score"] for k, v in r["scores"].items()},
                     "total": total, "reasons": reasons})
    blocking_set = [s for s in set_checks if s["severity"] == "blocking"]
    winners = sorted([x for x in rows if x["passed"]], key=lambda x: (-x["total"], -x["scores"].get("accuracy", 0),
                                                                      -x["scores"].get("clickbait_risk", 0), len(x["title"]), x["id"]))
    sel = winners[0] if winners and not blocking_set else None
    by_id = {c["id"]: c for c in cands}
    rejected = []
    for x in rows:
        if sel and x["id"] == sel["id"]:
            continue
        weaker = [f"{k.replace('_', ' ')} {v} vs {sel['scores'].get(k)}" for k, v in x["scores"].items()
                  if sel and v < sel["scores"].get(k, 0)]
        why = x["reasons"] or ([f"lower total review score ({x['total']} vs {sel['total']})" + (f": {', '.join(weaker)}" if weaker else
                                " (tie broken by accuracy, clickbait safety, shorter title)")] if sel else ["no package selected"])
        rejected.append({**{k: x[k] for k in ("id", "strategy", "title", "thumbnail_text", "total", "scores")}, "reasons": why})
    res = {"version": 1, "status": "passed" if sel else "failed", "candidates_file": cpath.name, "set_checks": set_checks,
           "diversity": div, "viable": viable, "table": rows,
           "selected": ({**by_id[sel["id"]], "scores": sel["scores"], "total": sel["total"],
                         "thumbnail_jpg": str((out / "candidates" / sel["id"] / "thumbnail.jpg").relative_to(out)),
                         "thumbnail_measurements": {k: v for k, v in meas[sel["id"]].items() if k != "warnings"}} if sel else None),
           "rejected": rejected, "review": {"file": "review/package_reviews.json", "judges": sorted({r.get("judge", "heuristic") for r in reviews.values()})}}
    write_json(sel_path, res)
    (out / "package_report.md").write_text(report_md(res), encoding="utf-8")
    print(json.dumps({"status": res["status"], "selected": sel["id"] if sel else None,
                      "table": [{k: x[k] for k in ("id", "passed", "total")} for x in rows],
                      "set_checks": [s["id"] for s in set_checks]}))
    return 0 if sel else 2


def report_md(res: dict) -> str:
    L = ["# Package selection", "", f"Status: **{res['status']}**", ""]
    if res["selected"]:
        s = res["selected"]
        L += [f"Selected: **{s['id']}** ({s['strategy']}) — total {s['total']}", f"- Title: {s['title']}",
              f"- Thumbnail text: {s['thumbnail']['text'] or '(none)'} — {s['thumbnail']['concept']}",
              f"- Opening promise: {s['opening_promise']}", ""]
    dims = sorted({k for x in res["table"] for k in x["scores"]})
    L += ["| id | strategy | title | thumb | " + " | ".join(d.replace("_", " ") for d in dims) + " | total | pass |",
          "|" + "---|" * (len(dims) + 6)]
    for x in res["table"]:
        L.append(f"| {x['id']} | {x['strategy']} | {x['title']} | {x['thumbnail_text']} | " +
                 " | ".join(str(x["scores"].get(d, "")) for d in dims) + f" | {x['total']} | {'✓' if x['passed'] else '✗'} |")
    if res["set_checks"]:
        L += ["", "Set-level problems:"] + [f"- {s['id']}: {s['evidence']}" for s in res["set_checks"]]
    L += ["", "## Rejected"] + [f"- **{r['id']}** — {r['title']}: " + "; ".join(r["reasons"][:4]) for r in res["rejected"]]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    for k in ("candidates", "script", "timing", "final", "out_dir"):
        s.add_argument("--" + k.replace("_", "-"), required=True)
    s.add_argument("--dossier"); s.add_argument("--palette"); s.add_argument("--policy"); s.add_argument("--judgment")
    s.add_argument("--review-backend", default="auto", choices=["auto", "heuristic", "subagent"],
                   help="subagent (P6.2): the reviewer writes package_review_request.md and exits 3 until a fresh "
                        "agent/human writes package_judgment.json; auto/heuristic judge locally")
    s.add_argument("--context", help="context brief outside the packet (the channel's own covers)")
    s.add_argument("--db", help="content memory: build a channel-covers context brief from recent videos")
    s.add_argument("--runs-dir", help="runs directory (used with --db to locate existing covers)")
    s.add_argument("--aspect", default="vertical", choices=["vertical", "wide"],
                   help="vertical = 9:16 thumbnail 1080x1920; wide = 16:9 long-form thumbnail 1920x1080")
    a = ap.parse_args()
    return cmd_select(a)


if __name__ == "__main__":
    sys.exit(main())
