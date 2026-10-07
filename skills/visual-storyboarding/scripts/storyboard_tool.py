#!/usr/bin/env python3
"""visual-storyboarding — turn a storyboard.json into rendered 9:16 visuals and keep it in sync with audio.

  storyboard_tool.py render   --storyboard sb.json --script script.json --out-dir DIR --result DIR/result.json
  storyboard_tool.py retime   --storyboard DIR/storyboard.rendered.json --timing timing.json --out sb_timed.json
                              [--max-shot 3.6]

`render` is the VISUAL_PLAN stage (renders + gate). `retime` runs at the start of VIDEO: scene cuts are placed
on real sentence onsets from timing.json and long scenes are split into sub-shots with varied motion.

Visual backends (scene.visual.kind):
  doodle      (v2 default) Claude-authored doodle SVG with data-* animation cues, animated by the video-production
              doodle engine; here it is linted and a preview still is rendered (references/doodle-scene-guide.md)
  svg         Claude-authored vector scene (viewBox 0 0 1080 1920) → PNG via rsvg-convert (or cairosvg)
  procedural  seeded gradient/bokeh background from the style palette (no text)
  image       a user/previous asset at visual.path (cropped/upscaled to 9:16)
  sd_forge    local Stable Diffusion WebUI Forge API (txt2img) — runs where Forge runs (CF_FORGE_URL)
  stock       Pexels photo search (PEXELS_API_KEY) — license + photographer recorded for provenance
Every scene may list `fallback` kinds; the first that succeeds is used and recorded.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import (StageResult, emit, exit_for, fix, log, read_json, run, stage_main,  # noqa: E402
                       validate_artifact, write_json)

W, H = 1080, 1920
RW, RH = 2160, 3840  # rendered at 2x for zoom/pan headroom
MOTIONS = ["zoom_in", "pan_left", "zoom_out", "pan_up", "pan_right", "pan_down"]
FRAMING = os.environ.get("CF_SD_FRAMING", "wide shot, full body, environment visible")
NEGATIVE = ("text, watermark, logo, signature, letters, extreme close-up, cropped, blurry, lowres, deformed, "
            "extra fingers, bad anatomy")


# ----------------------------------------------------------------------------- image utils
def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def fit_9x16(img: Image.Image) -> Image.Image:
    img = img.convert("RGB")
    scale = max(RW / img.width, RH / img.height)
    img = img.resize((math.ceil(img.width * scale), math.ceil(img.height * scale)), Image.LANCZOS)
    x, y = (img.width - RW) // 2, (img.height - RH) // 2
    return img.crop((x, y, x + RW, y + RH))


def procedural(palette: list[str], seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    w, h = RW // 4, RH // 4
    c1, c2 = (np.array(hex_rgb(c), float) for c in rng.choice(palette, 2, replace=False))
    yy = np.linspace(0, 1, h)[:, None, None]
    img = c1 * (1 - yy) + c2 * yy
    img = np.repeat(img, w, axis=1)
    xs, ys = np.meshgrid(np.arange(w), np.arange(h))
    for _ in range(9):  # soft bokeh blobs
        cx, cy, r = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(w * 0.08, w * 0.35)
        col = np.array(hex_rgb(rng.choice(palette)), float)
        a = np.exp(-(((xs - cx) ** 2 + (ys - cy) ** 2) / (2 * r * r)))[..., None] * rng.uniform(0.15, 0.45)
        img = img * (1 - a) + col * a
    vign = 1 - 0.35 * (((xs / w - 0.5) ** 2 + (ys / h - 0.5) ** 2) * 2.2)[..., None]
    img = np.clip(img * vign + rng.normal(0, 2.0, img.shape), 0, 255).astype(np.uint8)
    return Image.fromarray(img).resize((RW, RH), Image.BICUBIC).filter(ImageFilter.GaussianBlur(6))


def render_svg(svg_text: str, out_png: Path) -> None:
    if not re.search(r'viewBox="0 0 1080 1920"', svg_text):
        raise ValueError('SVG must declare viewBox="0 0 1080 1920"')
    src = out_png.with_suffix(".svg")
    src.write_text(svg_text, encoding="utf-8")
    if shutil.which("rsvg-convert"):
        run(["rsvg-convert", "-w", RW, "-h", RH, "-o", out_png, src])
    else:
        import cairosvg  # optional fallback
        cairosvg.svg2png(bytestring=svg_text.encode(), write_to=str(out_png), output_width=RW, output_height=RH)


def http_json(url: str, payload: dict | None = None, headers: dict | None = None, timeout: int = 300) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# ----------------------------------------------------------------------------- backends
def backend_svg(scene, style, out: Path, _seed):
    spec = scene["visual"].get("svg") or Path(scene["visual"]["svg_path"]).read_text(encoding="utf-8")
    render_svg(spec, out)
    has_text = "<text" in spec
    return {"source": "generated", "license": "self-generated", "generator": {"tool": "svg (Claude-authored)",
            "renderer": "rsvg-convert" if shutil.which("rsvg-convert") else "cairosvg"}, "contains_text": has_text,
            "realistic": False}


def _doodle_engine():
    here = Path(__file__).resolve()
    for cand in (here.parents[2] / "video-production" / "scripts", here.parent):
        if (cand / "doodle_engine.py").exists():
            sys.path.insert(0, str(cand))
            break
    import doodle_engine  # noqa: PLC0415
    return doodle_engine


def scene_words(scene: dict, beats: dict[str, str], wps: float = 2.8) -> list[dict]:
    """Approximate word timings for a scene from its beat text (real timings arrive with the AUDIO stage)."""
    toks = [t for bid in scene.get("beat_ids", []) for t in beats.get(bid, "").split()]
    return [{"w": t, "start": i / wps, "end": (i + 1) / wps} for i, t in enumerate(toks)]


def scene_words_timed(scene: dict, timing: dict) -> list[dict]:
    """Real narration words of a scene (from AUDIO's timing.json), re-based to the scene's first word."""
    sent_ids = {r["i"] for r in timing["sentences"] if r["beat_id"] in set(scene.get("beat_ids", []))}
    ws = [w for w in timing["words"] if w["sentence"] in sent_ids]
    if not ws:
        return []
    t0 = max(0.0, ws[0]["start"] - 0.08)
    return [{"w": w["w"], "start": round(w["start"] - t0, 3), "end": round(w["end"] - t0, 3)} for w in ws]


def doodle_cue_problems(svg: str, words: list[dict]) -> list[str]:
    import re as _re
    spoken = {_re.sub(r"[^\w]", "", w["w"].lower()) for w in words}
    probs = []
    for cue in _re.findall(r'data-(?:at|out-at)="w:([^"#]+)', svg) + _re.findall(r'"at":\s*"w:([^"#]+)', svg):
        k = _re.sub(r"[^\w]", "", cue.lower())
        if k in spoken:  # spoken words (numbers included, e.g. w:2013) match first
            continue
        if k.lstrip("-").isdigit():
            if abs(int(k)) >= len(words):
                probs.append(f"w:{cue} beyond the scene's {len(words)} words")
        elif not any(w == k or w.startswith(k) for w in spoken):
            probs.append(f"w:{cue} is not spoken in this scene")
    return probs


def backend_doodle(scene, style, out: Path, _seed):
    de = _doodle_engine()
    spec = scene["visual"].get("svg") or Path(scene["visual"]["svg_path"]).read_text(encoding="utf-8")
    words = scene.get("_words", [])
    dur = (words[-1]["end"] + 0.6) if words else 4.0
    sc = de.DoodleScene(spec, style.get("palette"), words, dur, style, scene_id=scene["id"], camera=scene.get("camera"),
                        bg=scene.get("bg"))
    de.render_still(sc, out, scale=2, paper=de.Paper(style.get("paper", "plain")))
    scene["visual"]["lint"] = [w for w in sc.warnings if "not spoken" not in w] + doodle_cue_problems(
        spec + json.dumps(scene.get("camera", {})), words)
    scene["visual"]["actors"] = sum(1 for a in sc.root.walk()) - 1
    scene["visual"]["frame0"] = sc.hook_stats()
    scene["visual"]["composition"] = sc.composition()
    return {"source": "generated", "license": "self-generated", "generator": {"tool": "doodle engine (Claude-authored SVG)",
            "renderer": "skia-python"}, "contains_text": "<text" in spec or "data-text" in spec, "realistic": False}


def runs(seq: list) -> list[tuple]:
    """[(value, start index, length)] of consecutive equal values."""
    out, i = [], 0
    while i < len(seq):
        j = i
        while j + 1 < len(seq) and seq[j + 1] == seq[i]:
            j += 1
        out.append((seq[i], i, j - i + 1))
        i = j + 1
    return out


def comp_gates(sr, scenes: list, roles: dict) -> None:
    """Phase 3 composition gates on the settled geometry of every doodle scene."""
    comp = [(s["id"], s["visual"].get("composition")) for s in scenes if s["visual"].get("composition")]
    if not comp:
        return
    ids = [c[0] for c in comp]
    lay = [c[1]["layout"] for c in comp]
    bad = [(v, ids[i:i + n]) for v, i, n in runs(lay) if n > 2]
    sr.check("VIS.LAYOUT_REPEAT", not bad, "major", f"layouts {dict(zip(ids, lay))}; repeated >2 in a row: {bad}",
             fix=fix("VISUAL_PLAN", "vary_layouts", scenes=[x for _, g in bad for x in g[2:]], layouts=lay))
    sig = [c[1]["main_signature"] for c in comp]
    last_loop = bool(scenes) and any(roles.get(b) == "loop" for b in scenes[-1].get("beat_ids", []))
    counted = sig[:-1] if last_loop and len(sig) > 2 else sig   # a closing loop may call back to the opening subject
    top = max(set(counted), key=counted.count) if counted else None
    share = counted.count(top) / max(1, len(counted)) if top else 0
    rep = [(v, ids[i:i + n]) for v, i, n in runs(sig) if n > 2 and v]
    sr.check("VIS.SUBJECT_REPEAT", not rep and share <= 0.5, "major",
             f"main subject per scene {dict(zip(ids, [c[1]['main_subject'] for c in comp]))}; same subject {share:.0%} of "
             f"{'non-loop ' if last_loop else ''}scenes; >2 in a row: {rep}",
             round(share, 2), 0.5, fix("VISUAL_PLAN", "vary_subjects", repeated_signature=top,
                                       scenes=[ids[i] for i, x in enumerate(sig) if x == top][1:]))
    small = [(i_, c["main_height_ratio"]) for i_, c in comp if c["layout"] in ("hero", "split", "character", "scatter")
             and c["main_height_ratio"] < 0.25]
    sr.check("VIS.SUBJECT_SIZE", not [x for x in small if x[1] < 0.18], "major" if [x for x in small if x[1] < 0.18] else "minor",
             f"main subject smaller than 25 % of frame height: {small}", fix=fix("VISUAL_PLAN", "enlarge_subject", scenes=[x[0] for x in small]))
    dead = [(i_, c["empty_cells"]) for i_, c in comp if c["empty_cells"] >= 5]
    sr.check("VIS.DEAD_SPACE", not dead, "major", f"content zone mostly empty (≥5 of 9 cells): {dead}",
             fix=fix("VISUAL_PLAN", "fill_space", scenes=[x[0] for x in dead]))
    f0 = scenes[0]["visual"].get("frame0") or {}
    n15 = f0.get("visual_events_first_1_5s", 0)
    sr.check("VIS.OPENING_DENSITY", n15 >= 2, "major", f"{n15} visual event(s) in the first 1.5 s (needs ≥2 to carry the hook)",
             n15, 2, fix=fix("VISUAL_PLAN", "add_entrances", scene="first", window_s=1.5))
    sr.metric("composition", {i_: {k: c[k] for k in ("layout", "main_subject", "main_height_ratio", "empty_cells")} for i_, c in comp})


def backend_procedural(scene, style, out: Path, seed):
    procedural(style["palette"], seed).save(out)
    return {"source": "generated", "license": "self-generated", "generator": {"tool": "procedural-bokeh", "seed": seed},
            "realistic": False}


def backend_image(scene, style, out: Path, _seed):
    src = Path(scene["visual"]["path"])
    fit_9x16(Image.open(src)).save(out)
    v = scene["visual"]
    return {"source": v.get("source", "user-provided"), "license": v.get("license", "unknown"),
            "attribution": v.get("attribution"), "origin_path": str(src), "realistic": v.get("realistic", True)}


def backend_sd_forge(scene, style, out: Path, seed):
    url = os.environ.get("CF_FORGE_URL", "http://127.0.0.1:7860").rstrip("/")
    v = scene["visual"]
    prompt = ", ".join(x for x in [style.get("sd_style", ""), v["prompt"], FRAMING] if x)
    payload = {"prompt": prompt, "negative_prompt": v.get("negative", NEGATIVE), "seed": v.get("seed", seed),
               "width": v.get("width", 576), "height": v.get("height", 1024), "steps": v.get("steps", 24),
               "cfg_scale": v.get("cfg", 6), "sampler_name": v.get("sampler", "DPM++ 2M"),
               "scheduler": v.get("scheduler", "Karras"), "batch_size": 1}
    res = http_json(f"{url}/sdapi/v1/txt2img", payload)
    raw = out.with_suffix(".raw.png")
    raw.write_bytes(base64.b64decode(res["images"][0].split(",", 1)[-1]))
    fit_9x16(Image.open(raw)).save(out)
    try:
        model = http_json(f"{url}/sdapi/v1/options", timeout=10).get("sd_model_checkpoint")
    except Exception:  # noqa: BLE001
        model = "unknown"
    return {"source": "generated", "license": "check model license", "generator": {
        "tool": "sd-webui-forge", "model": model, "prompt": prompt, "negative": payload["negative_prompt"],
        "seed": payload["seed"], "steps": payload["steps"], "cfg": payload["cfg_scale"], "size": [payload["width"], payload["height"]]},
        "realistic": v.get("realistic", False)}


def backend_stock(scene, style, out: Path, _seed):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        raise RuntimeError("PEXELS_API_KEY not set")
    base = os.environ.get("CF_PEXELS_BASE", "https://api.pexels.com")
    q = urllib.parse.urlencode({"query": scene["visual"]["query"], "orientation": "portrait", "per_page": 5})
    res = http_json(f"{base}/v1/search?{q}", headers={"Authorization": key}, timeout=30)
    if not res.get("photos"):
        raise RuntimeError(f"no Pexels results for {scene['visual']['query']!r}")
    ph = res["photos"][scene["visual"].get("pick", 0) % len(res["photos"])]
    raw = out.with_suffix(".raw.jpg")
    with urllib.request.urlopen(urllib.request.Request(ph["src"]["original"], headers={"Authorization": key}), timeout=60) as r:
        raw.write_bytes(r.read())
    fit_9x16(Image.open(raw)).save(out)
    return {"source": "stock:pexels", "license": "Pexels License", "source_url": ph["url"],
            "attribution": f"Photo by {ph['photographer']} on Pexels", "realistic": True}


BACKENDS = {"doodle": backend_doodle, "svg": backend_svg, "procedural": backend_procedural, "image": backend_image,
            "sd_forge": backend_sd_forge, "stock": backend_stock}


# ----------------------------------------------------------------------------- render (VISUAL_PLAN stage)
@stage_main("VISUAL_PLAN", "visual-storyboarding")
def cmd_render(a) -> int:
    sb, script = read_json(a.storyboard), read_json(a.script)
    out = Path(a.out_dir).resolve()
    (out / "assets").mkdir(parents=True, exist_ok=True)
    sr = StageResult("VISUAL_PLAN", "visual-storyboarding", sb.get("video_id"), attempt=a.attempt)
    sr.input(a.storyboard, "storyboard"); sr.input(a.script, "script")
    errs = validate_artifact(sb, "storyboard")
    if errs:
        sr.fail("VIS.SCHEMA", "; ".join(errs[:6]), fix=fix("VISUAL_PLAN", "repair_schema"), retryable=True)
        return exit_for(sr.finalize(a.result))
    style, base = sb["style"], Path(a.storyboard).resolve().parent
    for scene in sb["scenes"]:  # relative asset paths are relative to the storyboard file
        for key in ("svg_path", "path"):
            if scene["visual"].get(key) and not Path(scene["visual"][key]).is_absolute():
                scene["visual"][key] = str(base / scene["visual"][key])
    beat_text = {b["id"]: b["text"] for b in script["beats"]}
    timing = read_json(a.timing) if getattr(a, "timing", None) and Path(a.timing).exists() else None
    if timing:
        sr.input(a.timing, "voice_timing")
    for scene in sb["scenes"]:
        scene["_words"] = scene_words_timed(scene, timing) if timing else scene_words(scene, beat_text)
    sr.metric("cue_timing", "narration" if timing else "estimated")
    for n, scene in enumerate(sb["scenes"]):
        kinds = [scene["visual"]["kind"]] + scene["visual"].get("fallback", []) + (["procedural"] if a.auto_fallback else [])
        png = out / "assets" / f"{scene['id']}.png"
        for kind in dict.fromkeys(kinds):
            try:
                prov = BACKENDS[kind](scene, style, png, a.seed + n)
                scene["visual"]["path"], scene["visual"]["used_kind"] = str(png), kind
                prov.update({"role": f"visual:{scene['id']}", "path": str(png)})
                sr.provenance(prov)
                break
            except Exception as exc:  # noqa: BLE001 — try the next backend, record why
                log(f"scene {scene['id']}: backend {kind} failed: {exc}")
                scene["visual"].setdefault("errors", []).append(f"{kind}: {exc}"[:300])
    for scene in sb["scenes"]:
        scene.pop("_words", None)
    rendered = out / "storyboard.rendered.json"
    write_json(rendered, sb)

    beats = [b["id"] for b in script["beats"]]
    covered = [bid for s in sb["scenes"] for bid in s["beat_ids"]]
    sr.check("VIS.BEAT_COVERAGE", covered == beats, "blocking",
             f"scenes must cover every beat once, in order (scenes={covered}, script={beats})",
             fix=fix("VISUAL_PLAN", "remap_beats"))
    missing = [s["id"] for s in sb["scenes"] if "path" not in s["visual"]]
    sr.check("VIS.ASSETS_RENDERED", not missing, "blocking", f"unrendered scenes: {missing}", missing, [],
             fix("VISUAL_PLAN", "rerender", scenes=missing, add_fallback="procedural"))
    blank, used = [], {}
    for s in sb["scenes"]:
        if "path" in s["visual"]:
            arr = np.asarray(Image.open(s["visual"]["path"]).convert("L").resize((270, 480)), dtype=float)
            if arr.std() < 4.0:
                blank.append(s["id"])
            used[s["visual"]["used_kind"]] = used.get(s["visual"]["used_kind"], 0) + 1
    sr.check("VIS.NOT_BLANK", not blank, "blocking", f"near-uniform images: {blank}", blank, [],
             fix("VISUAL_PLAN", "rerender", scenes=blank))
    words = sum(len(b["text"].split()) for b in script["beats"])
    need = max(2, math.ceil(words / 2.8 / 7.0))  # ≥ one distinct visual per ~7 s of narration
    distinct = len({s["visual"].get("path") for s in sb["scenes"]})
    sr.check("VIS.VISUAL_VARIETY", distinct >= need, "major", f"{distinct} distinct visuals, need ≥ {need}",
             distinct, need, fix("VISUAL_PLAN", "add_scenes", min_scenes=need))
    texty = [s["id"] for s in sb["scenes"] if s["visual"].get("kind") != "doodle" and "<text" in (s["visual"].get("svg") or "")]
    sr.check("VIS.NO_BAKED_TEXT", not texty, "minor", f"SVG scenes containing <text> (clash with captions): {texty}")
    doodles = [s for s in sb["scenes"] if s["visual"].get("used_kind") == "doodle"]
    if doodles:
        cue_bad = {s["id"]: [w for w in s["visual"].get("lint", []) if w.startswith("w:")] for s in doodles}
        cue_bad = {k: v for k, v in cue_bad.items() if v}
        sr.check("VIS.CUE_WORDS", not cue_bad, "major", f"word cues that never get spoken: {cue_bad}", len(cue_bad), 0,
                 fix("VISUAL_PLAN", "repair_cues", scenes=list(cue_bad)))
        lint = {s["id"]: [w for w in s["visual"].get("lint", []) if not w.startswith("w:")] for s in doodles}
        lint = {k: v for k, v in lint.items() if v}
        sr.check("VIS.DOODLE_LINT", not lint, "minor", f"doodle scene warnings: {lint}", len(lint), 0,
                 fix("VISUAL_PLAN", "repair_scene", scenes=list(lint)))
        thin = [s["id"] for s in doodles if s["visual"].get("actors", 0) < 3]
        sr.check("VIS.DOODLE_ACTORS", not thin, "major", f"scenes with fewer than 3 animated elements: {thin}",
                 thin, [], fix("VISUAL_PLAN", "add_entrances", scenes=thin))
        comp_gates(sr, sb["scenes"], {b["id"]: b.get("role") for b in script["beats"]})
        f0 = sb["scenes"][0]["visual"].get("frame0") or {}
        ob = read_json(a.opening)["opening_beat"] if getattr(a, "opening", None) and Path(a.opening).exists() else None
        if ob:
            need = (ob.get("subject_size_target") or {}).get("min_height_ratio", 0.35)
            exc = ob.get("hook_exception") or f0.get("hook_exception")
            shown = " ".join(t["on_screen"] for t in f0.get("texts_t0", []))
            want = [w for w in re.findall(r"[A-Za-z0-9']+", (ob.get("on_screen_text") or "").upper())]
            probs = []
            if f0.get("subject_height_ratio", 0) < need and not exc:
                probs.append(f"subject {f0.get('subject_height_ratio', 0):.0%} of frame height < {need:.0%}")
            got = set(re.findall(r"[A-Za-z0-9']+", shown.upper()))      # same tokenisation on both sides ("GAS?" == "GAS")
            if want and not all(w in got for w in want):
                probs.append(f"on-screen hook text '{ob.get('on_screen_text')}' not fully visible at t=0 (shows '{shown}')")
            if f0.get("elements_at_t0", 0) < 2:
                probs.append(f"{f0.get('elements_at_t0', 0)} element(s) at t=0")
            ev = f0.get("first_visual_event_s")
            if (ev is None or ev > 0.5) and not f0.get("idle_motion_at_t0"):
                probs.append(f"first visual event at {ev}")
            if any(t.get("negation_hidden") or t.get("lost_words") or not t.get("inside_safe") for t in f0.get("texts_t0", [])):
                probs.append("frame-0 text cropped / outside the safe area")
            sr.check("VIS.OPENING", not probs, "major", "; ".join(probs) or "frame 0 honours the opening brief",
                     fix=fix("VISUAL_PLAN", "redesign_scene", scene="first", brief=ob, problems=probs))
        v0 = sb["scenes"][0]["visual"]
        first = v0.get("svg") or (Path(v0["svg_path"]).read_text(encoding="utf-8") if v0.get("svg_path") else "")
        sr.check("VIS.HOOK_AT_ZERO", 'data-in="none"' in first or 'data-at="0"' in first, "major",
                 "the first scene must show its hook subject at t=0 (data-in=\"none\" or data-at=\"0\")",
                 fix=fix("VISUAL_PLAN", "redesign_scene", scene="first"))
    sr.metric("scenes", len(sb["scenes"])); sr.metric("backends_used", used)
    sr.output(rendered, "storyboard_rendered", "application/json")
    res = sr.finalize(a.result)
    emit(res)
    return exit_for(res)


# ----------------------------------------------------------------------------- retime (start of VIDEO)
def cmd_retime(a) -> int:
    sb, tm = read_json(a.storyboard), read_json(a.timing)
    first_start: dict[str, float] = {}
    for srow in tm["sentences"]:
        first_start.setdefault(srow["beat_id"], srow["start"])
    duration = tm["duration_s"]
    starts = []
    for i, sc in enumerate(sb["scenes"]):
        if i == 0:
            starts.append(0.0)
        else:
            t = first_start.get(sc["beat_ids"][0])
            if t is None:
                raise SystemExit(f"beat {sc['beat_ids'][0]} has no audio; re-run AUDIO")
            starts.append(max(starts[-1] + 0.4, t - 0.08))  # cut just before the line lands
    shots = []
    words = tm["words"]
    for i, sc in enumerate(sb["scenes"]):
        s0, s1 = starts[i], starts[i + 1] if i + 1 < len(starts) else duration
        animated = sc["visual"].get("kind") == "doodle" or sc["visual"].get("used_kind") == "doodle"
        n = 1 if animated else max(1, math.ceil((s1 - s0) / a.max_shot))
        cuts = [s0]
        for k in range(1, n):  # split on the word boundary nearest to an even division
            target = s0 + (s1 - s0) * k / n
            cand = [w["start"] for w in words if cuts[-1] + 0.8 < w["start"] < s1 - 0.8]
            cuts.append(min(cand, key=lambda x: abs(x - target)) if cand else target)
        cuts.append(s1)
        base = (sc.get("motion") or {}).get("type", "zoom_in")
        for k in range(len(cuts) - 1):
            shot = json.loads(json.dumps(sc))
            shot["shot_id"] = f"{sc['id']}.{k + 1}"
            shot["start"], shot["end"] = round(cuts[k], 3), round(cuts[k + 1], 3)
            if k:
                shot["motion"] = {"type": MOTIONS[(MOTIONS.index(base) + k) % len(MOTIONS)] if base in MOTIONS else MOTIONS[k % 6],
                                  "strength": (sc.get("motion") or {}).get("strength", 0.12)}
                shot["transition"] = {"type": "cut", "duration": 0}
            shots.append(shot)
    sb["shots"] = shots
    sb["duration_s"] = duration
    write_json(a.out, sb)
    lens = [s["end"] - s["start"] for s in shots]
    print(json.dumps({"shots": len(shots), "min_shot_s": round(min(lens), 2), "max_shot_s": round(max(lens), 2),
                      "duration_s": duration, "out": a.out}))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--storyboard", required=True); r.add_argument("--script", required=True)
    r.add_argument("--out-dir", required=True); r.add_argument("--result", required=True)
    r.add_argument("--seed", type=int, default=1234); r.add_argument("--attempt", type=int, default=1)
    r.add_argument("--auto-fallback", action="store_true", help="append 'procedural' as last-resort fallback")
    r.add_argument("--timing", help="AUDIO timing.json: plan word cues against the real narration (factory passes it)")
    r.add_argument("--opening", help="HOOK opening_brief.json: the first scene must realise this frame 0")
    t = sub.add_parser("retime")
    t.add_argument("--storyboard", required=True); t.add_argument("--timing", required=True)
    t.add_argument("--out", required=True); t.add_argument("--max-shot", type=float, default=3.6)
    a = ap.parse_args()
    return {"render": cmd_render, "retime": cmd_retime}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
