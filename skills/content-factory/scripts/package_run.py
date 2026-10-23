#!/usr/bin/env python3
"""content-factory PACKAGE stage — upload-ready deliverables per video plus a run-level bundle.

  package_run.py --run RUN --video v01 [--video v02 ...] [--zip] [--attempt N]

Per video (RUN/package/<vid>/): final.mp4 (standard metadata only; provenance stays in provenance.json), cover.jpg, captions.srt/.vtt,
metadata.json (YouTube/TikTok/Instagram fields + AI-label flags), provenance.json, CREDITS.txt, qa_report.json,
contact_sheet.jpg, result.json. Run level: run_summary.md, checksums.sha256 and optionally <run>_package.zip.
Nothing is published: uploading stays a human decision.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.append(str(Path(__file__).resolve().parents[2] / "asset-provenance" / "scripts"))   # media_clean
from cf_common import (StageResult, emit, ffmpeg_bin, fix, log, read_json, run as sh, sha256_file,  # noqa: E402
                       skill_script, stage_main, write_json)
from factory import PASSED, FileLock, vp  # noqa: E402

YT_TITLE, YT_DESC, SOCIAL_CAP = 100, 5000, 2200
NEED = ["final.mp4", "cover.jpg", "captions.srt", "captions.vtt", "metadata.json", "provenance.json", "CREDITS.txt", "qa_report.json"]
NEED_V4 = ["thumbnail.jpg", "thumbnail_crops.jpg", "publishing_package.json", "PUBLISHING_PACKAGE.md"]
# public copy never carries pipeline internals (candidate ids, strategies, reviewer notes, file names)
INTERNAL_TEXT = r"\b(candidate|strategy|reviewer|package_|rationale|heuristic)\b|\.json\b|\.svg\b"
COVER_STEPS = {
    "youtube": "Shorts custom thumbnail: YouTube Studio on desktop → this Short → Thumbnail → upload thumbnail.jpg (rolling out since "
               "2026-07-25, Partner Program channels first; shown at ≈3:2 outside the Shorts feed — subject and text sit in the "
               "centre). If the option is not available on this channel, choose the closest frame instead.",
    "tiktok": "Cover: desktop web upload → Edit cover → upload thumbnail.jpg (TikTok crops covers to 3:4; nothing important is outside "
              "the central square).",
    "instagram": "Reels cover: Edit cover → Add from camera roll → thumbnail.jpg (profile grid crops to the centre)."}
# v3.3: a 16:9 long-form upload is a normal watch-page video — the thumbnail is chosen in Studio directly, and no
# mobile 9:16 cover crops apply. It also gets an end screen and can enter Test & compare.
COVER_STEPS_WIDE = {
    "youtube": "Watch-page thumbnail: upload a 16:9 image (1280×720 recommended, ≥640 px wide, ≤2 MB) in YouTube Studio → "
               "Details → Thumbnail → upload. A 16:9 thumbnail is normal on a 16:9 video (the 4:5 replacement only happens "
               "on vertical videos).",
    "tiktok": "Not applicable: this is a 16:9 long-form upload for the YouTube watch page.",
    "instagram": "Not applicable: this is a 16:9 long-form upload for the YouTube watch page."}


STOP_WORDS = {"the", "a", "an", "of", "to", "in", "is", "are", "why", "how", "does", "do", "you", "your", "it", "and",
              "that", "this", "for", "on", "at", "with", "what", "when", "be", "can", "we", "i"}


def _tokens(text: str) -> set:
    """Content words of a title/promise: lowercased, punctuation stripped, stop-words dropped (v3.3 variation check)."""
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in STOP_WORDS and len(w) > 1}


def _jac(a: set, b: set) -> float:
    return len(a & b) / max(1, len(a | b))


def _shape(text: str) -> str:
    """The *template* of a title/promise: every word in order, but content words collapsed to their slot (v3.3).

    The inauthentic-content policy (support.google.com/youtube/answer/1311392) targets packaging that reads as "generic
    or unoriginal templates … interchangeable from video to video" — i.e. the same word-pattern reused, not merely a
    shared topic word. So the signature keeps function words verbatim (they carry the pattern) and replaces each content
    word with a bare slot marker, so two genuinely different titles that happen to share one word never collapse onto
    each other, while "What actually happens when you X the Y?" reused twice does."""
    out = []
    for w in re.findall(r"[a-z0-9']+", text.lower()):
        out.append(w if w in STOP_WORDS or len(w) <= 1 else "\u00a7")
    return " ".join(out)


def crops_preview(src: Path, dst: Path, aspect: str = "vertical") -> None:
    """How each platform crops the thumbnail: 9:16 | 4:5 | 3:4 | 1:1 | ≈3:2 band (vertical covers). For a 16:9
    long-form thumbnail there is no mobile cover crop — one band showing the full 16:9 frame is written instead."""
    from PIL import Image
    im = Image.open(src).convert("RGB")
    w, h = im.size
    ars = (16 / 9,) if aspect == "wide" else (9 / 16, 4 / 5, 3 / 4, 1.0, 3 / 2)
    strips = []
    for ar in ars:
        ch = min(h, round(w / ar))
        top = (h - ch) // 2
        c = im.crop((0, top, w, top + ch)).resize((round(480 * w / ch), 480), Image.LANCZOS)
        strips.append(c)
    out = Image.new("RGB", (sum(s.width for s in strips) + 16 * (len(strips) - 1), 480), (255, 255, 255))
    x = 0
    for s in strips:
        out.paste(s, (x, 0))
        x += s.width + 16
    out.save(dst, "JPEG", quality=88)


def run_packaging(run: Path, vid: str, p: dict, sr: StageResult) -> dict | None:
    """Phase 4: pick the strongest complete package. Returns the selection, or None when packaging is not in use
    (older runs: no candidates file and no `package_engine` in the brief → the Phase 3.5 package, unchanged)."""
    brief = read_json(run / "run.json") if (run / "run.json").exists() else {}
    cand = p["dir"] / "package" / "package_candidates.json"
    if not cand.exists():
        if brief.get("package_engine"):
            sr.check("PKG.CANDIDATES", False, "blocking", f"{cand.relative_to(run)} missing (≥3 complete package candidates)",
                     fix=fix("PACKAGE", "author_packages"))
            return {}
        return None
    pal = None
    sb = p["storyboard"]
    if sb.exists():
        pal = ",".join(read_json(sb).get("style", {}).get("palette", [])) or None
    brief = read_json(run / "run.json") if (run / "run.json").exists() else {}
    aspect = brief.get("aspect", "vertical")
    cmd = [sys.executable, str(Path(__file__).with_name("package_engine.py")), "select", "--candidates", cand, "--script", p["script"],
           "--timing", p["timing"], "--final", p["final"], "--dossier", run / "research" / "dossier.json",
           "--out-dir", p["dir"] / "package", "--aspect", aspect] + (["--palette", pal] if pal else [])
    judg = p["dir"] / "package" / "package_judgment.json"
    if judg.exists():
        cmd += ["--judgment", judg]
    backend = brief.get("review_backend", "auto")
    backend = "subagent" if backend == "human" else backend
    if backend not in ("auto", "heuristic", "subagent"):
        backend = "auto"
    if backend != "auto":
        cmd += ["--review-backend", backend]
    mem = (brief.get("memory") or {}).get("db")
    if mem and Path(mem).exists():
        cmd += ["--db", mem, "--runs-dir", run.parent]
    pr = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    selp = p["dir"] / "package" / "package_selection.json"
    sel = read_json(selp) if selp.exists() else {"status": "failed", "set_checks": [{"id": "PKG.ENGINE_ERROR", "evidence": pr.stderr[-300:]}],
                                                  "table": [], "selected": None}
    if sel.get("status") == "awaiting_judgment":
        req = (sel.get("review") or {}).get("request") or "review/package_review_request.md"
        sr.check("PKG.JUDGMENT", False, "blocking",
                 f"cover judgment awaited: give ONLY the packet folders to a fresh reviewer ({req}), write "
                 f"{judg.relative_to(run)} and re-run packaging", fix=fix("PACKAGE", "judge_package"))
        return {}
    probs = [f"{s['id']}: {s['evidence'][:160]}" for s in sel.get("set_checks", [])] + \
            [f"{r['id']}: {'; '.join(r['reasons'][:2])[:200]}" for r in sel.get("table", []) if not r["passed"]]
    sr.check("PKG.PACKAGING", sel.get("status") == "passed", "blocking",
             f"selected {sel['selected']['id']} ({sel['selected']['total']} pts) from {len(sel['table'])} candidates"
             if sel.get("selected") else "no package passed: " + " | ".join(probs[:6]),
             fix=fix("PACKAGE", "repackage", problems=probs[:8]))
    return sel if sel.get("status") == "passed" else {}



def package_video(run: Path, vid: str, attempt: int) -> dict:
    p, out = vp(run, vid), run / "package" / vid
    if out.exists():            # Phase 5: every file here is regenerated; a failed attempt must not leave the last
        shutil.rmtree(out)      # attempt's final.mp4 / PUBLISHING_PACKAGE.md looking ready to upload
    out.mkdir(parents=True, exist_ok=True)
    sr = StageResult("PACKAGE", "content-factory", vid, attempt=attempt)
    brief = read_json(run / "run.json") if (run / "run.json").exists() else {}
    aspect = brief.get("aspect", "vertical")
    qa = read_json(p["result"]["QA"]) if p["result"]["QA"].exists() else {"status": "missing"}
    sel = None
    if qa["status"] in PASSED:
        sel = run_packaging(run, vid, p, sr)
    if sel == {}:                                   # packaging in use but no package passed → stop here
        res = sr.finalize(out / "result.json")
        emit(res)
        return res
    if sr.check("PKG.QA_PASSED", qa["status"] in PASSED, "blocking", f"QA status is {qa['status']}", fix=fix("QA", "complete_review")):
        prov_res = out / "provenance_result.json"
        cmd = [sys.executable, str(skill_script("asset-provenance", "provenance.py")), "build", "--video-dir", p["dir"],
               "--final", p["final"], "--out-dir", out, "--result", prov_res, "--script", p["script"]]
        for flag, f in (("--dossier", run / "research" / "dossier.json"), ("--license-map", run / "licenses.json")):
            if f.exists():
                cmd += [flag, f]
        pp = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
        pr = read_json(prov_res) if prov_res.exists() else {"status": "missing", "errors": []}
        hard = [e for e in pr.get("errors", []) if e["severity"] != "minor"]
        if sr.check("PKG.PROVENANCE", pr["status"] in PASSED, "blocking",
                    "; ".join(e["message"][:140] for e in hard) or f"provenance {pr['status']} (exit {pp.returncode}): "
                    f"{(pp.stderr or pp.stdout)[-300:]}",
                    fix=(hard[0].get("fix_route") if hard else None) or fix("PACKAGE", "retry")):
            prov, script = read_json(out / "provenance.json"), read_json(p["script"])
            for src in (p["subs"] / "captions.srt", p["subs"] / "captions.vtt", p["qa"] / "contact_sheet.jpg", p["qa"] / "qa_report.json"):
                if src.exists():
                    shutil.copy2(src, out / src.name)
            if sel:                                 # Phase 4: the selected designed thumbnail is the cover everywhere
                s_ = sel["selected"]
                shutil.copy2(p["dir"] / "package" / s_["thumbnail_jpg"], out / "thumbnail.jpg")
                shutil.copy2(out / "thumbnail.jpg", out / "cover.jpg")
                crops_preview(out / "thumbnail.jpg", out / "thumbnail_crops.jpg", aspect)
            else:
                sh([ffmpeg_bin(), "-y", "-v", "error", "-ss", "0.7", "-i", out / "final.mp4", "-frames:v", "1", "-q:v", "2", out / "cover.jpg"])
            from media_clean import DENY_RE, audit as media_audit, clean as media_clean
            for img in (out / "cover.jpg", out / "contact_sheet.jpg", out / "thumbnail.jpg", out / "thumbnail_crops.jpg"):
                if img.exists():
                    tmp = img.with_suffix(".clean.jpg")
                    media_clean(img, tmp)
                    tmp.replace(img)
            pub, disc = dict(script["publish"]), prov["disclosure"]
            if sel:
                s_ = sel["selected"]
                body = "\n\n".join(x for x in [s_["opening_promise"], s_["description"]] if x)
                pub = {"title_options": [s_["title"]] + [r["title"] for r in sel["table"] if r["passed"] and r["id"] != s_["id"]],
                       "description": body, "hashtags": s_["hashtags"]}
            src_lines = [f"- {s['title']} ({s.get('publisher') or 'source'}): {s['url']}" for s in prov.get("sources", [])]
            tags = " ".join(pub["hashtags"])
            # v3.0.2: the same list, without "#" and comma-separated, for YouTube's tags field (owner request 2026-10-16)
            tags_plain = ", ".join(h.strip().lstrip("#") for h in pub["hashtags"] if h.strip().lstrip("#"))
            ccta = (sel["selected"].get("caption_cta") or "") if sel else ""
            # v3.0.2: no "Narration: AI text-to-speech (...). Visuals: ..." line in the description (owner request
            # 2026-10-16); disclosure is the platform AI labels in metadata.json, still enforced by PKG.DISCLOSURE
            desc = "\n\n".join(x for x in [pub["description"], ccta,
                                           "Sources:\n" + "\n".join(src_lines) if src_lines else "", tags] if x)
            caption = "\n\n".join(x for x in [pub["description"], ccta, tags] if x)
            meta = {"video_id": vid, "language": script["language"], "title": pub["title_options"][0],
                    "title_alternatives": pub["title_options"][1:],
                    "youtube": {"title": pub["title_options"][0], "description": desc,
                                "altered_or_synthetic": disc["youtube"]["altered_or_synthetic"]},
                    "tiktok": {"caption": caption, "ai_generated_label": disc["tiktok"]["ai_generated_label"]},
                    "instagram": {"caption": caption, "ai_info": disc["instagram"]["ai_info"]},
                    "hashtags": pub["hashtags"], "hashtags_copy_ready": tags_plain, "sources": prov.get("sources", []),
                    "human_must_set": ["YouTube audience setting (made for kids: yes/no)", "confirm AI-label toggles",
                                       "publish time / schedule"]}
            kind = brief.get("video_kind", "short")   # `brief` read at the top of package_video; `aspect` likewise
            if kind == "long":
                # v3.3 (D2): end screens are the official subscribe surface and exist on 16:9 long-form only — the
                # last 5–20 s must be left calm and free for them (support.google.com/youtube/answer/6388789).
                es = brief.get("end_screen") or {}
                meta["end_screen"] = {"zone_s": es.get("zone_s", [5, 20]), "element": "Subscribe",
                                      "instruction": "YouTube Studio → Editor → End screen: add an element in the last "
                                                     "5–20 s (Subscribe + one related video). The tail is left visually calm "
                                                     "for exactly this."}
                meta["human_must_set"].append("YouTube Studio → End screen: add Subscribe (+ related video) in the last 5–20 s")
                # v3.3: title/thumbnail A/B test is decided by WATCH TIME over ~2 weeks and needs a 16:9 watch page
                # (support.google.com/youtube/answer/16391400). Only the owner can start it.
                meta["ab_test"] = {"decision_metric": "watch time", "duration_days": 14,
                                   "variants": 3, "source": "support.google.com/youtube/answer/16391400",
                                   "instruction": "Studio → this video → Test & compare: test the 3 title variants below; "
                                                  "the winner is chosen by watch time, not CTR"}
                meta["human_must_set"].append("Optionally start Studio → Test & compare with the 3 title variants (decided by watch time)")
                meta["human_must_set"].insert(0, "upload a 16:9 (1920×1080) thumbnail as the custom thumbnail")
            elif sel:
                meta["human_must_set"].insert(0, "upload thumbnail.jpg (9:16) as the cover on each platform (see covers)")
            cta = script.get("cta") or {}
            if cta.get("needed"):
                meta["cta"] = {k: cta.get(k) for k in ("type", "placement", "modality", "spoken", "on_screen")}
            # v3.3: on a Short the related-video link is the official Shorts→long-form funnel (a clickable link below the
            # channel handle, support.google.com/youtube/answer/14075157). Offer it whenever the channel has a long-form
            # video to point at, not only for a part_2 — the funnel is how a Short earns its watch hours' worth of reach.
            if kind != "long" and (cta.get("type") == "part_2" or (run.parent / "longform_index.json").exists()):
                meta["human_must_set"].append("YouTube Studio → this Short → Related video: link the long-form video "
                                              "(advanced features; shown below the channel handle)")
            if sel:
                meta["thumbnail"] = "thumbnail.jpg"
                meta["thumbnail_text"] = sel["selected"]["thumbnail"]["text"]
                meta["opening_promise"] = sel["selected"].get("opening_promise", "")
                meta["covers"] = COVER_STEPS_WIDE if kind == "long" else COVER_STEPS
                if kind != "long":
                    meta["human_must_set"].insert(0, "upload thumbnail.jpg as the cover on each platform (see covers)")
                if ccta:
                    meta.setdefault("cta", {})["caption"] = ccta
            write_json(out / "metadata.json", meta)
            if sel:
                # authored copy only (disclosure is the platform labels, governed by PKG.DISCLOSURE)
                public = " ".join([meta["title"], pub["description"], ccta, " ".join(pub["hashtags"])] + meta["title_alternatives"])
                leaks = sorted({m_.group() for m_ in DENY_RE.finditer(public)} |
                               {m_.group() for m_ in re.finditer(INTERNAL_TEXT, public, re.I)})
                sr.check("PKG.PUBLIC_COPY_CLEAN", not leaks, "blocking", f"internal terms in public copy: {leaks}" if leaks else
                         "title/description/captions carry no internal or pipeline text", fix=fix("PACKAGE", "repackage"))
                # v3.3: the inauthentic-content policy (renamed from "repetitious" on 2025-07-15) refuses monetisation to
                # "generic or unoriginal templates … channels where content feels interchangeable from video to video"
                # (support.google.com/youtube/answer/1311392). A template factory is exactly the profile it targets, so
                # the package is compared against its siblings and the recent history: near-duplicate title shape,
                # thumbnail text or opening promise is treated as a monetisation risk, not a style choice.
                sib = [read_json(run / "package" / v2 / "publishing_package.json") for v2 in sorted((run / "package").iterdir())
                       if v2.is_dir() and v2.name != vid and (v2 / "publishing_package.json").exists()]
                hist = []                                  # past videos the channel already made (factory.db `videos`)
                dbp = brief.get("memory", {}).get("db")
                if dbp and Path(dbp).exists():
                    try:
                        import sqlite3
                        with sqlite3.connect(dbp) as con:
                            rows = con.execute(
                                "SELECT run_id, title, hook, final_sha256 FROM videos WHERE title IS NOT NULL").fetchall()
                    except Exception:                      # noqa: BLE001 — the check is advisory; never fail packaging on the DB
                        rows = []
                    own = brief.get("run_id") or run.name
                    own_sha = (prov.get("final") or {}).get("sha256")
                    own_title = meta["title"].strip().lower()
                    seen = set()
                    for rid, t, h, sha in rows:
                        # dedupe to distinct videos: the same title re-packaged inside one run is one video, not a
                        # fresh interchangeable one, so the run's own earlier ingest (same id, same final bytes, or the
                        # same title) must not judge itself. Re-publishing a video is caught by SELECTION's novelty rule,
                        # not here — this check is about *different* videos that read as one template.
                        key = (t, sha or h or "")
                        if rid != own and not (own_sha and sha == own_sha) and (t or "").strip().lower() != own_title \
                                and key not in seen:
                            seen.add(key)
                            hist.append({"title": t, "opening_promise": h})
                tt = _tokens(meta["title"])
                pt = _tokens(pub.get("description", "")[:120])
                ts = _shape(meta["title"])
                ps = _shape(pub.get("description", "")[:120])
                clashes = []
                for prev in hist[-30:] + sib:
                    if not isinstance(prev, dict):
                        continue
                    # a *template* clash: the same word-pattern reused, or near-identical wording. A shared topic word
                    # (e.g. both titles containing "time") is expected and is NOT a clash.
                    if prev.get("title") and (_shape(prev["title"]) == ts or _jac(tt, _tokens(prev["title"])) >= 0.85):
                        clashes.append(f"title shape repeats “{prev.get('title', '?')[:50]}”")
                    if prev.get("thumbnail_text") and (
                            _shape(prev["thumbnail_text"]) == _shape(meta.get("thumbnail_text", ""))
                            or _jac(_tokens(meta.get("thumbnail_text", "")), _tokens(prev["thumbnail_text"])) >= 0.85):
                        clashes.append("thumbnail text repeats an earlier video")
                    if prev.get("opening_promise") and (
                            _shape(prev["opening_promise"]) == ps or _jac(pt, _tokens(prev["opening_promise"])) >= 0.85):
                        clashes.append("opening promise repeats an earlier video")
                clashes = sorted(set(clashes))
                sr.check("PKG.PACKAGING_VARIATION", not clashes, "major",
                         f"packaging looks interchangeable with earlier videos (inauthentic-content risk): {clashes[:3]}"
                         if clashes else f"packaging differs from {len(hist[-30:]) + len(sib)} earlier videos",
                         fix=fix("PACKAGE", "vary_packaging", clashes=clashes[:3]))
                from PIL import Image
                try:
                    with Image.open(out / "thumbnail.jpg") as im_:
                        im_.load()
                        tsize = list(im_.size)
                except Exception as exc:  # noqa: BLE001
                    tsize = f"does not decode: {exc}"
                want = [1920, 1080] if aspect == "wide" else [1080, 1920]
                sr.check("PKG.THUMBNAIL_DECODES", tsize == want, "blocking", f"thumbnail.jpg {tsize} (needs {want})",
                         fix=fix("PACKAGE", "retry"))
                write_publishing_package(run, vid, out, meta, sel, prov, script)
            sr.check("PKG.TITLE_LENGTH", len(meta["title"]) <= YT_TITLE, "major", f"title {len(meta['title'])} chars",
                     fix=fix("SCRIPT", "retitle", max_chars=YT_TITLE))
            sr.check("PKG.YT_DESCRIPTION", len(desc) <= YT_DESC, "major", f"description {len(desc)} chars",
                     fix=fix("SCRIPT", "shorten_description"))
            sr.check("PKG.SOCIAL_CAPTION", len(caption) <= SOCIAL_CAP, "major", f"caption {len(caption)} chars",
                     fix=fix("SCRIPT", "shorten_description"))
            # Phase 3.5 media policy: publishable media carry no internal metadata; disclosure stays on the platform labels
            media = sorted(f for f in out.iterdir() if f.suffix.lower() in (".mp4", ".jpg", ".jpeg", ".png", ".m4v", ".mov"))
            audits = [media_audit(f) for f in media]
            dirty = [{"file": x["file"], "findings": x["findings"][:6]} for x in audits if not x["clean"]]
            write_json(out / "media_metadata_audit.json", {"policy": "standard metadata only (Phase 3.5)", "files": audits})
            sr.check("PKG.MEDIA_METADATA_CLEAN", not dirty, "blocking", f"internal/debug metadata in publishable media: {dirty}"
                     if dirty else f"{len(audits)} media files carry standard metadata only",
                     fix=fix("VIDEO", "rerender", reason="encoder/version strings inside streams") if any(
                         f["value"].lower().startswith("lav") for d in dirty for f in d["findings"]) else fix("PACKAGE", "retry"))
            dec = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(out / "final.mp4"), "-f", "null", "-"],
                                 capture_output=True, text=True).stderr.strip()
            sr.check("PKG.FINAL_DECODES", not dec, "blocking", dec[:200] or "cleaned deliverable decodes fully",
                     fix=fix("PACKAGE", "retry"))
            labels = [meta["youtube"].get("altered_or_synthetic"), meta["tiktok"].get("ai_generated_label"),
                      meta["instagram"].get("ai_info")]
            sr.check("PKG.DISCLOSURE", all(x is not None for x in labels), "blocking",
                     f"platform AI labels {labels} (set by hand at upload; no tool line in the description since v3.0.2)",
                     fix=fix("PACKAGE", "retry"))
            hist_p = run.parent / "cta_history.json"
            if not sr.failed and (cta.get("needed") or hist_p.exists()):   # remember only CTAs of videos that really ship
                with FileLock(run.parent / ".cta_history.lock", f"PACKAGE {run.name}/{vid}", wait_s=60):  # shared by runs
                    hist = read_json(hist_p) if hist_p.exists() else {"ctas": []}
                    # a video re-made after a reset replaces its own entry (Phase 5) instead of keeping the old CTA
                    kept = [h for h in hist["ctas"] if not (h["run"] == run.name and h["video_id"] == vid)]
                    if cta.get("needed"):
                        kept.append({"run": run.name, "video_id": vid, "type": cta.get("type"),
                                     "text": " ".join(x for x in (cta.get("spoken", ""), cta.get("on_screen", "")) if x)})
                    if kept != hist["ctas"]:
                        write_json(hist_p, {**hist, "ctas": kept})
            need = NEED + (NEED_V4 if sel else [])
            missing = [n for n in need if not (out / n).exists()]
            sr.check("PKG.FILES", not missing, "blocking", f"missing {missing}", fix=fix("PACKAGE", "retry"))
            sr.check("PKG.CHECKSUM", sha256_file(out / "final.mp4") == prov["final"]["sha256"], "blocking",
                     "deliverable matches the provenance hash", fix=fix("PACKAGE", "retry"))
            for n in need:
                if (out / n).exists():
                    sr.output(out / n, n)
    res = sr.finalize(out / "result.json")
    emit(res)
    return res


def write_publishing_package(run: Path, vid: str, out: Path, meta: dict, sel: dict, prov: dict, script: dict) -> None:
    """The one artifact the owner reads before uploading. Public copy is kept separate from internal references."""
    s_ = sel["selected"]
    rv = {k: v for k, v in s_["scores"].items()}
    rej = [{"id": r["id"], "title": r["title"], "thumbnail_text": r["thumbnail_text"], "total": r["total"], "reasons": r["reasons"]}
           for r in sel["rejected"]]
    pkg = {"video_id": vid, "public": {"title": meta["title"], "thumbnail": "thumbnail.jpg", "thumbnail_text": s_["thumbnail"]["text"],
                                       "youtube_description": meta["youtube"]["description"], "caption": meta["tiktok"]["caption"],
                                       "hashtags": meta["hashtags"], "hashtags_copy_ready": meta["hashtags_copy_ready"], "cta": {"in_video": meta.get("cta"), "caption": s_.get("caption_cta", "")},
                                       "ai_labels": {"youtube_altered_or_synthetic": meta["youtube"]["altered_or_synthetic"],
                                                     "tiktok_ai_generated": meta["tiktok"]["ai_generated_label"],
                                                     "instagram_ai_info": meta["instagram"]["ai_info"]}},
           "video": {"file": "final.mp4", "sha256": prov["final"]["sha256"]},
           "covers": COVER_STEPS, "human_must_set": meta["human_must_set"],
           "ab_test": meta.get("ab_test"), "end_screen": meta.get("end_screen"),
           "title_variants": meta.get("title_alternatives", []) if meta.get("ab_test") else [],
           "internal": {"selected_candidate": s_["id"], "strategy": s_["strategy"], "thumbnail_concept": s_["thumbnail"]["concept"],
                        "opening_promise": s_["opening_promise"], "review_scores": rv, "review_total": s_["total"],
                        "review_judges": sel["review"]["judges"], "claim_ids": s_["claim_ids"], "thumbnail_depicts": s_["thumbnail"]["depicts"],
                        "research": "research/dossier.json", "selection": f"videos/{vid}/package/package_selection.json",
                        "reviews": f"videos/{vid}/package/review/package_reviews.json", "rejected": rej}}
    write_json(out / "publishing_package.json", pkg)
    crop_label = ("16:9 frame" if meta.get("ab_test") else "9:16 · 4:5 · 3:4 · 1:1 · ≈3:2")
    L = [f"# Publishing package — {vid}", "", "Nothing is published automatically. Upload by hand; set the AI labels below.", "",
         "## Public copy", "", f"**Title:** {meta['title']}", "", f"**Thumbnail:** `thumbnail.jpg` (text: “{s_['thumbnail']['text']}”) — "
         f"crop preview in `thumbnail_crops.jpg` ({crop_label})", "", "**YouTube description:**", "", "```",
         meta["youtube"]["description"], "```", "", "**TikTok / Instagram caption:**", "", "```", meta["tiktok"]["caption"], "```", "",
         "**Hashtags (copy-ready):**", "", "```", meta["hashtags_copy_ready"], "```", "",
         f"**CTA:** in video — {(meta.get('cta') or {}).get('spoken') or 'none'}; caption — {s_.get('caption_cta') or 'none'}", "",
         f"**AI labels:** YouTube altered/synthetic = {meta['youtube']['altered_or_synthetic']}, TikTok AI-generated = "
         f"{meta['tiktok']['ai_generated_label']}, Instagram AI info = {meta['instagram']['ai_info']}", "",
         f"**Video:** `final.mp4` (sha256 {prov['final']['sha256'][:16]}…)", "", "## Covers", ""] + \
        [f"- **{k}:** {v}" for k, v in COVER_STEPS.items()] + ["", "## Before upload", ""] + [f"- {x}" for x in meta["human_must_set"]] + \
        (["", "## A/B test (long-form only)", "",
          f"Studio → this video → **Test & compare**. YouTube picks the winner by **{meta['ab_test']['decision_metric']}** "
          f"over ~{meta['ab_test']['duration_days']} days, not by click-through rate "
          f"({meta['ab_test']['source']}). Test up to 3 title variants:", ""] +
         [f"- {t}" for t in [meta["title"]] + meta.get("title_alternatives", [])[:2]] +
         ["", "or upload alternative 16:9 thumbnails (1280×720 recommended).", ""] if meta.get("ab_test") else []) + \
        ["", "## Why this package (internal)", "", f"Selected **{s_['id']}** ({s_['strategy']}), review total {s_['total']}/"
         f"{5 * len(rv)}: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in rv.items()), "",
         f"Opening promise (caption first line): {s_['opening_promise']}", f"Thumbnail concept: {s_['thumbnail']['concept']}",
         f"Claims rest on dossier facts {s_['claim_ids']}; thumbnail depicts {s_['thumbnail']['depicts']} (research/dossier.json).", "",
         "## Rejected alternatives", ""] + \
        [f"- **{r['id']}** “{r['title']}” / “{r['thumbnail_text']}” — " + "; ".join(r["reasons"][:3]) for r in rej]
    (out / "PUBLISHING_PACKAGE.md").write_text("\n".join(L) + "\n", encoding="utf-8")


@stage_main("PACKAGE", "content-factory")
def main_cmd(a) -> int:
    run = Path(a.run).resolve()
    results = [(vid, package_video(run, vid, a.attempt)) for vid in a.video]
    lines = [f"# Run summary — {run.name}", "", "| video | package | duration | title |", "|---|---|---|---|"]
    for vid, res in results:
        mp = run / "package" / vid / "metadata.json"
        title = read_json(mp)["title"] if mp.exists() else "—"
        qa = run / "package" / vid / "qa_report.json"
        dur = read_json(qa).get("metrics", {}).get("duration_s", "—") if qa.exists() else "—"
        lines.append(f"| {vid} | {res['status']} | {dur} s | {title} |")
    (run / "package" / "run_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    files = sorted(f for f in (run / "package").rglob("*") if f.is_file() and f.name != "checksums.sha256")
    (run / "package" / "checksums.sha256").write_text(
        "".join(f"{sha256_file(f)}  {f.relative_to(run / 'package').as_posix()}\n" for f in files), encoding="utf-8")
    ok = all(r["status"] in PASSED for _, r in results)
    zp = run / f"{run.name}_package.zip"
    if a.zip and ok:
        shutil.make_archive(str(zp.with_suffix("")), "zip", run / "package")
    elif a.zip:                 # Phase 5: never ship (or keep) a run zip while a video's package failed
        zp.unlink(missing_ok=True)
        log(f"no {zp.name}: package failed for {[v for v, r in results if r['status'] not in PASSED]}")
    return 0 if ok else 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True); ap.add_argument("--video", action="append", required=True)
    ap.add_argument("--zip", action="store_true"); ap.add_argument("--attempt", type=int, default=1)
    ap.add_argument("--result", help=argparse.SUPPRESS)
    return main_cmd(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
