#!/usr/bin/env python3
"""doodle_engine — hand-drawn, word-synchronised scene animation for the content factory (v2 video engine).

A doodle scene is ordinary SVG (viewBox 0 0 1080 1920) plus `data-*` animation attributes. The engine:
  * re-draws every stroke as a wobbly marker line that "boils" at 10 fps (Skia discrete+corner path effects),
  * offsets marker fills slightly from the ink outline (coloured-outside-the-lines look),
  * animates each element in on a cue — seconds, or the moment a narration WORD is spoken (`data-at="w:robot"`),
  * runs a per-scene camera (slow drift, punch-ins and shakes on cue words) and page transitions between scenes,
  * renders frames straight into ffmpeg and returns an event list (pops, scribbles, whooshes) for sound design.

Animation attributes (any element or <g>):
  data-in     draw | pop | write | slide-left|right|up|down | drop | grow | spin | fade | none   (default draw)
  data-at     1.2 (s from scene start) | w:3 (4th word of the scene) | w:robot | w:robot#2 | +0.3 (after previous)
  data-dur    entrance duration in s (defaults per animation)
  data-loop   wiggle | bob | pulse | shake | spin | float | tremble        (idle motion after the entrance)
  data-out    pop | fade | slide-left|right|up|down ; data-out-at = cue  (exit)
  data-origin center | bottom | top | "x,y"                              (pivot for pop/grow/spin/wiggle)
  data-sfx    pop | scribble | whoosh | boing | ding | thump | none     (override the automatic sound)
  data-lib    a component from doodle_lib (dude, bubble, arrow, robot, brain, …) expanded in place
  data-fill-style hatch                                                   (hatched marker shading)
  data-sketch 2                                                           (double pencil stroke)
Colours: hex, a few names, or p0…p5 (= style.palette[i]). Text: <text font-family="hand|marker" font-size="72">.

CLI (for testing):
  doodle_engine.py still --svg scene.svg --out still.png [--t 3] [--scale 1]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import skia
from svgelements import (Arc, Circle, Close, CubicBezier, Ellipse, Line, Matrix, Move, Path as SPath, Polygon,
                         Polyline, QuadraticBezier, Rect, SimpleLine)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import doodle_lib  # noqa: E402
from cf_common import X264_THREADS  # noqa: E402

W, H = 1080, 1920
FPS = 30
BOIL_FPS = 10
INK = "#1d1b1a"
PAPER = "#fbf7ee"
FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
FONT_FILES = {"hand": "PatrickHand-Regular.ttf", "marker": "PermanentMarker-Regular.ttf", "rtl": "Vazirmatn-Bold.ttf"}
NAMED = {"white": "#ffffff", "black": INK, "ink": INK, "red": "#e8452c", "yellow": "#ffd23f", "blue": "#3b82c4",
         "green": "#2f9e44", "orange": "#f08c00", "pink": "#f783ac", "purple": "#7048e8", "gray": "#9a9a9a",
         "grey": "#9a9a9a", "paper": PAPER, "sky": "#7cc6f2"}
SHAPES = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
ANIMS_IN = {"draw", "pop", "write", "slide-left", "slide-right", "slide-up", "slide-down", "drop", "grow", "spin", "fade", "none"}
LOOPS = {"wiggle", "bob", "pulse", "shake", "spin", "float", "tremble"}
DEFAULT_DUR = {"pop": 0.38, "slide-left": 0.45, "slide-right": 0.45, "slide-up": 0.45, "slide-down": 0.45, "drop": 0.6,
               "grow": 0.42, "spin": 0.5, "fade": 0.3, "none": 0.0}
WORD_LEAD = 0.06       # visuals land a hair before the word
CAPTION_BAND = (1060, 1360)
_FONT_CACHE: dict = {}
_TF_CACHE: dict = {}


# ----------------------------------------------------------------------------- small helpers
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def ease_in_out(u):
    return u * u * (3 - 2 * u)


def ease_out_cubic(u):
    return 1 - (1 - u) ** 3


def ease_in_cubic(u):
    return u ** 3


def back_out(u, s=1.9):
    u -= 1
    return u * u * ((s + 1) * u + s) + 1


def back_in(u, s=1.7):
    return u * u * ((s + 1) * u - s)


def bounce_out(u):
    n, d = 7.5625, 2.75
    if u < 1 / d:
        return n * u * u
    if u < 2 / d:
        u -= 1.5 / d
        return n * u * u + 0.75
    if u < 2.5 / d:
        u -= 2.25 / d
        return n * u * u + 0.9375
    u -= 2.625 / d
    return n * u * u + 0.984375


def h32(*parts) -> int:
    return int(hashlib.blake2s("|".join(map(str, parts)).encode(), digest_size=4).hexdigest(), 16)


def color4(spec: str | None, palette: list[str], alpha: float = 1.0):
    if spec is None:
        return None
    s = spec.strip().lower()
    if s in ("none", "transparent", ""):
        return None
    m = re.fullmatch(r"p(\d)", s)
    if m and palette:
        s = palette[int(m.group(1)) % len(palette)].lower()
    s = NAMED.get(s, s)
    if s.startswith("#") and len(s) == 4:
        s = "#" + "".join(ch * 2 for ch in s[1:])
    if not re.fullmatch(r"#[0-9a-f]{6}", s):
        m = re.fullmatch(r"rgba?\(([^)]*)\)", s)
        if not m:
            return skia.Color4f(0.11, 0.11, 0.1, alpha)
        v = [float(x) for x in m.group(1).split(",")]
        return skia.Color4f(v[0] / 255, v[1] / 255, v[2] / 255, (v[3] if len(v) > 3 else 1) * alpha)
    r, g, b = (int(s[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return skia.Color4f(r, g, b, alpha)


def is_rtl(text: str) -> bool:
    return any(unicodedata.bidirectional(c) in ("R", "AL") for c in text)


def norm_word(s: str) -> str:
    return re.sub(r"[^\w]", "", s.lower(), flags=re.UNICODE)


def sk_matrix(m: Matrix) -> skia.Matrix:
    return skia.Matrix.MakeAll(m.a, m.c, m.e, m.b, m.d, m.f, 0, 0, 1)


def rough_effect(seed: int, dev: float, seg: float = 13.0, corner: float = 9.0, trim: float | None = None):
    pe = skia.PathEffect.MakeCompose(skia.CornerPathEffect.Make(corner), skia.DiscretePathEffect.Make(seg, dev, seed & 0x7FFFFFFF))
    if trim is not None and trim < 0.999:
        t = skia.TrimPathEffect.Make(0, max(0.0005, trim))
        if t is not None:
            pe = skia.PathEffect.MakeCompose(pe, t)
    return pe


def typeface(key: str):
    if key not in _TF_CACHE:
        _TF_CACHE[key] = skia.Typeface.MakeFromFile(str(FONT_DIR / FONT_FILES[key]))
    return _TF_CACHE[key]



NEGATIONS = {"not", "no", "never", "dont", "isnt", "arent", "cant", "wont", "without", "nothing", "none", "nor",
             "neither", "doesnt", "didnt", "wasnt", "werent", "shouldnt", "couldnt", "nobody", "nowhere", "aint"}


def visible_words(text: str, vis: list[tuple[int, bool]]) -> tuple[str, list[str]]:
    """Words fully on screen vs words that lost at least one glyph (glyph i ↔ character index ci of `text`)."""
    ok = {ci: v for ci, v in vis}
    shown, lost, pos = [], [], 0
    for m in re.finditer(r"\S+", text):
        chars = [ok[i] for i in range(m.start(), m.end()) if i in ok]
        (shown if chars and all(chars) else lost).append(m.group())
        pos = m.end()
    return " ".join(shown), lost


def sample_path(path: skia.Path, step: float) -> list[tuple[float, float]]:
    pts = []
    meas = skia.PathMeasure(path, False)
    while True:
        L = meas.getLength()
        dist = 0.0
        while dist <= L:
            p, _t = meas.getPosTan(dist)
            pts.append((p.x(), p.y()))
            dist += step
        if not meas.nextContour():
            break
    return pts

# ----------------------------------------------------------------------------- scene model
class Drawable:
    """One ink shape (path) or one text run, already in scene coordinates."""

    def __init__(self):
        self.kind = "path"
        self.path: skia.Path | None = None
        self.fill_path: skia.Path | None = None
        self.stroke = None
        self.fill = None
        self.sw = 8.0
        self.opacity = 1.0
        self.hatch = False
        self.sketch = 1
        self.seed = 0
        self.length = 0.0
        self.glyphs: list[tuple[skia.Path, float, float, int]] = []   # (path, cx, cy, char index in text)
        self.text = ""
        self.font_size = 0.0
        self.inside = None          # id of the actor this drawable must stay inside (data-inside)
        self.rtl = False
        self.bounds = skia.Rect.MakeEmpty()


class Actor:
    def __init__(self, el_id: str, attrs: dict, order: int):
        self.id = el_id
        self.attrs = attrs
        self.order = order
        self.anim = attrs.get("data-in", "draw")
        if self.anim not in ANIMS_IN:
            self.anim = "draw"
        self.loop = attrs.get("data-loop") if attrs.get("data-loop") in LOOPS else None
        self.out = attrs.get("data-out")
        self.at = 0.0
        self.dur = 0.0
        self.out_at = None
        self.out_dur = 0.3
        self.drawables: list[Drawable] = []
        self.children: list[Actor] = []
        self.bounds = skia.Rect.MakeEmpty()
        self.pivot = (W / 2, H / 2)
        self.total_len = 0.0
        self.sfx = attrs.get("data-sfx")
        self.lib = attrs.get("data-lib")

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


class DoodleScene:
    """Parse one doodle SVG and render it at any local time."""

    def __init__(self, svg_text: str, palette: list[str] | None = None, words: list[dict] | None = None,
                 duration: float = 4.0, style: dict | None = None, scene_id: str = "s", camera: dict | None = None,
                 bg: str | None = None):
        self.palette = palette or ["#ffd23f", "#e8452c", "#3b82c4", "#2f9e44"]
        self.words = words or []
        self.duration = duration
        self.style = style or {}
        self.scene_id = scene_id
        self.warnings: list[str] = []
        self.wobble = float(self.style.get("wobble", 2.6))
        self.bg = color4(bg or self.style.get("paper_color", PAPER), self.palette)
        self.root = Actor("root", {"data-in": "none"}, 0)
        self._order = 0
        self._parse(svg_text)
        self._resolve_timing()
        self.camera = self._build_camera(camera or {})

    # ------------------------------------------------------------------ parsing
    def _parse(self, svg_text: str) -> None:
        svg_text = re.sub(r'\sxmlns(:\w+)?="[^"]*"', "", svg_text, count=0)
        root = ET.fromstring(svg_text)
        self.hook_exception = root.get("data-hook-exception")
        vb = root.get("viewBox", "0 0 1080 1920").split()
        if [float(v) for v in vb] != [0, 0, 1080, 1920]:
            self.warnings.append(f"viewBox {vb} is not 0 0 1080 1920; scaling assumed 1:1")
        base_style = {"stroke": None, "fill": None, "stroke-width": "8", "opacity": "1", "font-size": "64",
                      "font-family": "hand", "text-anchor": "middle", "dominant-baseline": "middle"}
        for child in list(root):
            self._walk(child, Matrix(), base_style, self.root, top=True)
        self._finish_actor(self.root)

    @staticmethod
    def _style_of(el, parent: dict) -> dict:
        st = dict(parent)
        for k in ("stroke", "fill", "stroke-width", "opacity", "font-size", "font-family", "text-anchor",
                  "dominant-baseline", "data-fill-style", "data-sketch", "data-outline", "data-inside"):
            if el.get(k) is not None:
                st[k] = el.get(k)
        for decl in (el.get("style") or "").split(";"):
            if ":" in decl:
                k, v = (x.strip() for x in decl.split(":", 1))
                st[k] = v
        if el.get("opacity") is not None:
            st["opacity"] = str(float(parent.get("opacity", 1)) * float(el.get("opacity")))
        return st

    def _walk(self, el, mtx: Matrix, pstyle: dict, actor: Actor, top: bool = False) -> None:
        tag = el.tag.split("}")[-1]
        if tag in ("defs", "title", "desc", "metadata", "style", "clipPath", "mask", "linearGradient", "radialGradient"):
            return
        attrs = dict(el.attrib)
        if attrs.get("data-lib"):
            name = attrs["data-lib"]
            try:
                inner = doodle_lib.expand(name, attrs)
            except KeyError:
                self.warnings.append(f"unknown data-lib '{name}'")
                inner = ""
            frag = ET.fromstring(f"<g>{inner}</g>")
            el = ET.Element("g", attrs)
            el.extend(list(frag))
            tag = "g"
        local = Matrix(el.get("transform")) if el.get("transform") else Matrix()
        m = local * mtx
        style = self._style_of(el, pstyle)
        anim_keys = ("data-in", "data-at", "data-loop", "data-out", "data-dur")
        if top or any(k in attrs for k in anim_keys):
            self._order += 1
            child = Actor(attrs.get("id") or f"{tag}{self._order}", attrs, self._order)
            if attrs.get("data-lib") == "dude" and "data-origin" not in attrs:
                child.attrs["data-origin"] = "bottom"
            actor.children.append(child)
            actor = child
        if tag in ("g", "a", "svg", "switch"):
            for c in list(el):
                self._walk(c, m, style, actor)
            return
        if tag == "text":
            d = self._text_drawable(el, m, style)
            if d:
                actor.drawables.append(d)
            return
        if tag in SHAPES:
            d = self._shape_drawable(el, tag, m, style)
            if d:
                actor.drawables.append(d)

    def _shape_drawable(self, el, tag: str, m: Matrix, st: dict) -> Drawable | None:
        g = lambda k, dflt=0.0: float(el.get(k, dflt))  # noqa: E731
        try:
            if tag == "path":
                shape = SPath(el.get("d", ""))
            elif tag == "rect":
                shape = SPath(Rect(g("x"), g("y"), g("width"), g("height"), el.get("rx"), el.get("ry")))
            elif tag == "circle":
                shape = SPath(Circle(g("cx"), g("cy"), g("r")))
            elif tag == "ellipse":
                shape = SPath(Ellipse(g("cx"), g("cy"), g("rx"), g("ry")))
            elif tag == "line":
                shape = SPath(SimpleLine(g("x1"), g("y1"), g("x2"), g("y2")))
            elif tag == "polyline":
                shape = SPath(Polyline(el.get("points", "")))
            else:
                shape = SPath(Polygon(el.get("points", "")))
        except Exception as exc:  # noqa: BLE001
            self.warnings.append(f"bad <{tag}>: {exc}")
            return None
        shape *= m
        shape.reify()
        path = skia.Path()
        closed_any = False
        for seg in shape:
            if isinstance(seg, Move):
                path.moveTo(seg.end.x, seg.end.y)
            elif isinstance(seg, Close):
                path.close()
                closed_any = True
            elif isinstance(seg, Line):
                path.lineTo(seg.end.x, seg.end.y)
            elif isinstance(seg, CubicBezier):
                path.cubicTo(seg.control1.x, seg.control1.y, seg.control2.x, seg.control2.y, seg.end.x, seg.end.y)
            elif isinstance(seg, QuadraticBezier):
                path.quadTo(seg.control.x, seg.control.y, seg.end.x, seg.end.y)
            elif isinstance(seg, Arc):
                for c in seg.as_cubic_curves():
                    path.cubicTo(c.control1.x, c.control1.y, c.control2.x, c.control2.y, c.end.x, c.end.y)
        if path.countPoints() < 2:
            return None
        d = Drawable()
        d.path = path
        d.opacity = float(st.get("opacity", 1))
        scale = math.sqrt(abs(m.a * m.d - m.b * m.c)) or 1.0
        fill = st.get("fill")
        stroke = st.get("stroke")
        d.fill = color4(fill, self.palette) if fill not in (None, "none") else None
        if tag in ("line", "polyline") or (tag == "path" and not closed_any and fill is None):
            d.fill = None
        if stroke is None:
            stroke = "none" if st.get("data-outline") == "none" else INK
        d.stroke = color4(stroke, self.palette)
        d.sw = clamp(float(re.sub(r"[^\d.]", "", st.get("stroke-width", "8")) or 8) * scale, 2.0, 40.0)
        d.hatch = st.get("data-fill-style") == "hatch"
        d.sketch = int(st.get("data-sketch", self.style.get("sketch", 1)))
        d.seed = h32(self.scene_id, self._order, path.countPoints(), round(path.getBounds().left(), 1))
        meas = skia.PathMeasure(path, False)
        total = 0.0
        while True:
            total += meas.getLength()
            if not meas.nextContour():
                break
        d.length = max(total, 1.0)
        d.bounds = path.computeTightBounds()
        d.inside = (st.get("data-inside") or "").lstrip("#") or None
        return d

    def _text_drawable(self, el, m: Matrix, st: dict) -> Drawable | None:
        text = "".join(el.itertext()).strip()
        if not text:
            return None
        rtl = is_rtl(text)
        key = "rtl" if rtl else ("marker" if "marker" in st.get("font-family", "") else "hand")
        size = float(re.sub(r"[^\d.]", "", st.get("font-size", "64")) or 64)
        visual = text
        if rtl:
            try:
                import arabic_reshaper
                from bidi.algorithm import get_display
                visual = get_display(arabic_reshaper.reshape(text))
            except Exception:  # noqa: BLE001
                self.warnings.append("arabic-reshaper/python-bidi missing: RTL label rendered unshaped")
        font = skia.Font(typeface(key), size)
        glyphs = font.textToGlyphs(visual)
        widths = font.getWidths(glyphs)
        total = float(sum(widths))
        x, y = float(el.get("x", 540)), float(el.get("y", 960))
        anchor = st.get("text-anchor", "middle")
        x0 = x - total / 2 if anchor == "middle" else (x - total if anchor == "end" else x)
        met = font.getMetrics()
        base = y - (met.fAscent + met.fDescent) / 2 if st.get("dominant-baseline", "middle") in ("middle", "central") else y
        sm = sk_matrix(m)
        d = Drawable()
        d.kind = "text"
        d.rtl = rtl
        d.fill = color4(st.get("fill") if st.get("fill") not in (None, "none") else INK, self.palette)
        d.stroke = None
        d.opacity = float(st.get("opacity", 1))
        cx = x0
        bounds = skia.Rect.MakeEmpty()
        for ci, (gid, wdt) in enumerate(zip(glyphs, widths)):
            p = font.getPath(gid)
            if p is not None and p.countPoints():
                p.offset(cx, base)
                p.transform(sm)
                b = p.computeTightBounds()
                d.glyphs.append((p, b.centerX(), b.centerY(), ci))
                bounds.join(b)
            cx += wdt
        if d.rtl:
            d.glyphs.reverse()  # write right-to-left
        d.bounds = bounds
        d.length = 46.0 * max(1, len(d.glyphs))
        d.text = visual
        d.font_size = size * math.sqrt(abs(m.a * m.d - m.b * m.c))
        d.seed = h32(self.scene_id, "t", text)
        if bounds.top() < CAPTION_BAND[1] and bounds.bottom() > CAPTION_BAND[0]:
            self.warnings.append(f"label '{text[:24]}' overlaps the caption band y{CAPTION_BAND}")
        return d

    def _finish_actor(self, actor: Actor) -> None:
        b = skia.Rect.MakeEmpty()
        for d in actor.drawables:
            b.join(d.bounds)
        for c in actor.children:
            self._finish_actor(c)
            b.join(c.bounds)
        actor.bounds = b
        actor.total_len = sum(d.length for d in actor.drawables)
        org = actor.attrs.get("data-origin", "center")
        if "," in org:
            px, py = (float(v) for v in org.split(","))
        elif org == "bottom":
            px, py = b.centerX(), b.bottom()
        elif org == "top":
            px, py = b.centerX(), b.top()
        else:
            px, py = b.centerX(), b.centerY()
        actor.pivot = (px, py) if not b.isEmpty() else (W / 2, H / 2)

    # ------------------------------------------------------------------ timing
    def cue(self, spec, prev: float, default: float) -> float:
        if spec is None or str(spec).strip() == "":
            return default
        s = str(spec).strip()
        try:
            if s.startswith("+"):
                return prev + float(s[1:])
            if s.startswith("w:"):
                key, occ = s[2:], 1
                if "#" in key:
                    key, o = key.split("#", 1)
                    occ = int(o)
                k = norm_word(key)
                spoken = [w for w in self.words if norm_word(w["w"]) == k]
                if re.fullmatch(r"-?\d+", key) and not spoken:   # a number nobody says = word index (w:3 = 4th word)
                    return max(0.0, self.words[int(key)]["start"] - WORD_LEAD)
                hits = [w for w in self.words if norm_word(w["w"]) == k] or \
                       [w for w in self.words if norm_word(w["w"]).startswith(k)]
                if len(hits) >= occ:
                    return max(0.0, hits[occ - 1]["start"] - WORD_LEAD)
                raise LookupError(f"word '{key}' not spoken in this scene")
            return float(s)
        except (ValueError, IndexError, LookupError) as exc:
            self.warnings.append(f"cue {s!r}: {exc}; using {default:.2f}s")
            return default

    def _resolve_timing(self) -> None:
        prev = 0.0
        for i, a in enumerate(self.root.children):
            # an element that is simply "there" (data-in=none, no cue) is on screen from the first frame
            static = a.anim == "none" and "data-at" not in a.attrs
            prev_keep = prev
            t = self._time_actor(a, prev, default=0.0 if (i == 0 or static) else prev + 0.3)
            prev = prev_keep if static else t
            for j, c in enumerate(a.walk()):
                if c is a:
                    continue
                if "data-at" not in c.attrs:
                    # a nested element that is simply there (data-in=none) appears with its parent, not staggered
                    c.at = a.at if c.anim == "none" else a.at + 0.12 * j
                else:
                    c.at = self.cue(c.attrs["data-at"], a.at, a.at)
                c.dur = self._dur(c)
                self._time_out(c)

    def _time_actor(self, a: Actor, prev: float, default: float) -> float:
        a.at = self.cue(a.attrs.get("data-at"), prev, default)
        a.dur = self._dur(a)
        self._time_out(a)
        return a.at

    def _time_out(self, a: Actor) -> None:
        if a.out and a.attrs.get("data-out-at"):
            a.out_at = self.cue(a.attrs["data-out-at"], a.at, a.at + a.dur + 1.0)
            a.out_dur = float(a.attrs.get("data-out-dur", 0.3))

    def _dur(self, a: Actor) -> float:
        if a.attrs.get("data-dur"):
            return max(0.0, float(a.attrs["data-dur"]))
        if a.anim == "draw":
            return clamp(a.total_len / 1500 + 0.25, 0.3, 1.3) if a.total_len else 0.3
        if a.anim == "write":
            n = sum(len(d.glyphs) for d in a.drawables) or 6
            return clamp(n * 0.05, 0.3, 1.2)
        return DEFAULT_DUR.get(a.anim, 0.35)

    def events(self, offset: float = 0.0) -> list[dict]:
        out = []
        for a in self.root.walk():
            if a is self.root or a.anim == "none" and not a.sfx:
                continue
            kind = a.sfx or {"draw": "scribble", "write": "scribble", "pop": "pop", "grow": "pop", "spin": "whoosh",
                             "drop": "boing", "fade": None, "slide-left": "whoosh", "slide-right": "whoosh",
                             "slide-up": "whoosh", "slide-down": "whoosh"}.get(a.anim)
            if kind and kind != "none" and a.at < self.duration:
                out.append({"t": round(offset + a.at, 3), "kind": kind, "dur": round(max(a.dur, 0.08), 3), "id": a.id})
            if a.out and a.out_at is not None and a.out_at < self.duration:
                out.append({"t": round(offset + a.out_at, 3), "kind": "pop" if a.out == "pop" else "whoosh", "dur": 0.2, "id": a.id})
        for p in self.camera["punch"]:
            out.append({"t": round(offset + p["at"], 3), "kind": "thump", "dur": 0.2, "id": "camera"})
        for s in self.camera["shake"]:
            out.append({"t": round(offset + s, 3), "kind": "thump", "dur": 0.25, "id": "camera"})
        return out

    def visual_event_times(self) -> list[float]:
        ts = [a.at for a in self.root.walk() if a is not self.root and (a.anim != "none" or a.at > 0)]
        ts += [p["at"] for p in self.camera["punch"]] + self.camera["shake"]
        ts += [a.out_at for a in self.root.walk() if a.out_at is not None]
        return sorted(t for t in ts if 0 <= t <= self.duration)

    # ------------------------------------------------------------------ camera
    def _build_camera(self, cam: dict) -> dict:
        drift = cam.get("drift", "in")
        punches = []
        for p in cam.get("punch", []) or []:
            p = {"at": p} if isinstance(p, (str, int, float)) else dict(p)
            at = self.cue(p.get("at"), 0, 0)
            focus = p.get("focus")
            if isinstance(focus, str) and focus.startswith("#"):
                act = next((a for a in self.root.walk() if a.id == focus[1:]), None)
                focus = (act.bounds.centerX(), act.bounds.centerY()) if act and not act.bounds.isEmpty() else None
                if focus is None:
                    self.warnings.append(f"camera focus {p.get('focus')} not found")
            punches.append({"at": at, "zoom": float(p.get("zoom", 1.14)), "hold": float(p.get("hold", 0.9)),
                            "focus": tuple(focus) if focus else (W / 2, 860)})
        shakes = [self.cue(s, 0, 0) for s in cam.get("shake", []) or []]
        return {"drift": drift, "punch": punches, "shake": shakes, "amount": float(cam.get("amount", 0.05))}

    def punch_level(self, t: float) -> float:
        """0..1: how far into a camera punch-in the shot is at local time t (punch-ins crop on purpose)."""
        lvl = 0.0
        for p in self.camera["punch"]:
            dt = t - p["at"]
            if 0 <= dt < 0.09 + p["hold"] + 0.4:
                lvl = max(lvl, 1.0 if dt <= 0.09 + p["hold"] else 1 - (dt - 0.09 - p["hold"]) / 0.4)
        return lvl

    def camera_matrix(self, t: float) -> skia.Matrix:
        c = self.camera
        u = clamp(t / max(self.duration, 0.1))
        e = ease_in_out(u)
        amt = c["amount"]
        z, tx, ty = 1.0, 0.0, 0.0
        if c["drift"] == "in":
            z = 1 + amt * e
        elif c["drift"] == "out":
            z = 1 + amt * (1 - e)
        elif c["drift"] in ("left", "right", "up", "down"):
            z = 1 + amt * 0.8
            sgn = -1 if c["drift"] in ("left", "up") else 1
            tx = sgn * (e - 0.5) * 50 if c["drift"] in ("left", "right") else 0
            ty = sgn * (e - 0.5) * 70 if c["drift"] in ("up", "down") else 0
        m = skia.Matrix()
        m.preTranslate(W / 2 + tx, 900 + ty)
        m.preScale(z, z)
        m.preTranslate(-W / 2, -900)
        for p in c["punch"]:
            dt = t - p["at"]
            if dt < 0:
                continue
            if dt < 0.09:
                k = ease_out_cubic(dt / 0.09)
            elif dt < 0.09 + p["hold"]:
                k = 1.0
            else:
                k = 1 - ease_in_out(clamp((dt - 0.09 - p["hold"]) / 0.4))
            if k <= 0:
                continue
            zz = 1 + (p["zoom"] - 1) * k
            fx, fy = p["focus"]
            # move the focus point toward the screen centre while zooming in
            cx, cy = W / 2 + (fx - W / 2) * (1 - 0.6 * k), 860 + (fy - 860) * (1 - 0.6 * k)
            pm = skia.Matrix()
            pm.preTranslate(cx, cy)
            pm.preScale(zz, zz)
            pm.preTranslate(-fx, -fy)
            m = skia.Matrix.Concat(m, pm)
        for s in c["shake"]:
            dt = t - s
            if 0 <= dt < 0.35:
                amp = 16 * (1 - dt / 0.35)
                q = int(dt * 30)
                m.postTranslate(amp * math.sin(q * 2.7 + 1), amp * math.cos(q * 3.1))
        return m

    # ------------------------------------------------------------------ drawing
    def _actor_matrix(self, a: Actor, t: float):
        """Return (visible, matrix, alpha, reveal) for actor a at local time t."""
        if a is self.root:
            return True, None, 1.0, 1.0
        if t < a.at - 1e-6:
            return False, None, 0.0, 0.0
        u = clamp((t - a.at) / a.dur) if a.dur > 0 else 1.0
        px, py = a.pivot
        m = skia.Matrix()
        alpha, reveal = 1.0, 1.0
        kind = a.anim
        if kind == "draw":
            reveal = ease_in_out(u)
        elif kind == "write":
            reveal = u
        elif kind == "pop":
            s = max(0.001, back_out(u))
            m.preTranslate(px, py); m.preScale(s, s); m.preTranslate(-px, -py)
        elif kind == "grow":
            s = max(0.001, back_out(u, 1.4))
            m.preTranslate(px, py); m.preScale(1, s); m.preTranslate(-px, -py)
        elif kind == "spin":
            s = max(0.001, ease_out_cubic(u))
            m.preTranslate(px, py); m.preRotate(-200 * (1 - s)); m.preScale(s, s); m.preTranslate(-px, -py)
        elif kind.startswith("slide-"):
            k = 1 - back_out(u, 1.2)
            dx = {"slide-left": 1150, "slide-right": -1150}.get(kind, 0)
            dy = {"slide-up": 1500, "slide-down": -1500}.get(kind, 0)
            m.preTranslate(dx * k, dy * k)
        elif kind == "drop":
            m.preTranslate(0, -1400 * (1 - bounce_out(u)))
        elif kind == "fade":
            alpha = u
        if a.loop and u >= 1.0:
            lt = t - a.at - a.dur
            q = math.floor(lt * BOIL_FPS) / BOIL_FPS
            if a.loop == "wiggle":
                m.preTranslate(px, py); m.preRotate(4 * math.sin(2 * math.pi * 1.4 * q)); m.preTranslate(-px, -py)
            elif a.loop == "bob":
                m.preTranslate(0, 10 * math.sin(2 * math.pi * 1.1 * lt))
            elif a.loop == "float":
                m.preTranslate(0, 12 * math.sin(2 * math.pi * 0.7 * lt))
                m.preTranslate(px, py); m.preRotate(2 * math.sin(2 * math.pi * 0.5 * lt)); m.preTranslate(-px, -py)
            elif a.loop == "pulse":
                s = 1 + 0.05 * math.sin(2 * math.pi * 1.6 * lt)
                m.preTranslate(px, py); m.preScale(s, s); m.preTranslate(-px, -py)
            elif a.loop == "shake":
                k = int(lt * BOIL_FPS)
                m.preTranslate(6 * math.sin(k * 2.3), 4 * math.cos(k * 1.7))
            elif a.loop == "tremble":
                k = int(lt * 30)
                m.preTranslate(3 * math.sin(k * 2.3), 2 * math.cos(k * 1.9))
            elif a.loop == "spin":
                m.preTranslate(px, py); m.preRotate(120 * lt); m.preTranslate(-px, -py)
        if a.out_at is not None and t >= a.out_at:
            v = clamp((t - a.out_at) / max(a.out_dur, 0.01))
            if v >= 1:
                return False, None, 0.0, 0.0
            if a.out == "pop":
                s = max(0.001, 1 - back_in(v))
                m.preTranslate(px, py); m.preScale(s, s); m.preTranslate(-px, -py)
            elif a.out == "fade":
                alpha *= 1 - v
            elif a.out and a.out.startswith("slide-"):
                k = ease_in_cubic(v)
                m.preTranslate({"slide-left": -1150, "slide-right": 1150}.get(a.out, 0) * k,
                               {"slide-up": -1500, "slide-down": 1500}.get(a.out, 0) * k)
        return True, m, alpha, reveal

    def _paint_drawable(self, canvas, d: Drawable, reveal: float, boil: int, alpha: float, write: bool = False) -> None:
        a = alpha * d.opacity
        if a <= 0.003 or reveal <= 0.0005:
            return
        seed = d.seed + boil * 7919
        if d.kind == "text":
            n = len(d.glyphs)
            shown = n if reveal >= 1 else reveal * n
            paint = skia.Paint(AntiAlias=True, Color4f=d.fill, Style=skia.Paint.kStrokeAndFill_Style, StrokeWidth=1.2,
                               StrokeJoin=skia.Paint.kRound_Join)
            paint.setAlphaf(a * d.fill.fA)
            for k, (gp, cx, cy, _ci) in enumerate(d.glyphs):
                if k >= math.ceil(shown):
                    break
                part = clamp(shown - k) if write else 1.0
                rs = h32(seed, k)
                canvas.save()
                jitter = 1.0 if boil >= 0 else 0
                canvas.translate(((rs % 7) - 3) * 0.35 * jitter, (((rs >> 3) % 7) - 3) * 0.35 * jitter)
                canvas.translate(cx, cy)
                canvas.rotate((((rs >> 6) % 9) - 4) * 0.45)
                sc = 0.55 + 0.45 * back_out(part) if part < 1 else 1.0
                canvas.scale(sc, sc)
                canvas.translate(-cx, -cy)
                paint.setPathEffect(rough_effect(seed + k, 0.9, seg=7, corner=4))
                canvas.drawPath(gp, paint)
                canvas.restore()
            return
        if d.fill is not None and d.fill_path is None:
            d.fill_path = skia.Path(d.path)
            d.fill_path.setFillType(skia.PathFillType.kWinding)
        if d.fill is not None:
            fa = clamp((reveal - 0.45) / 0.45) if reveal < 1 else 1.0
            if fa > 0:
                ox, oy = ((d.seed % 9) - 4) * 1.1, (((d.seed >> 4) % 9) - 4) * 1.1
                canvas.save()
                canvas.translate(ox, oy)
                if d.hatch:
                    canvas.save()
                    canvas.clipPath(d.fill_path, skia.ClipOp.kIntersect, True)
                    tint = skia.Paint(AntiAlias=True, Color4f=d.fill)
                    tint.setAlphaf(a * fa * 0.30)
                    canvas.drawPath(d.fill_path, tint)
                    hp = skia.Paint(AntiAlias=True, Color4f=d.fill, Style=skia.Paint.kStroke_Style, StrokeWidth=5,
                                    StrokeCap=skia.Paint.kRound_Cap, PathEffect=rough_effect(seed + 3, 1.6))
                    hp.setAlphaf(a * fa)
                    b = d.bounds
                    hatch = skia.Path()
                    span = b.width() + b.height()
                    x = b.left() - b.height()
                    while x < b.right():
                        hatch.moveTo(x, b.bottom()); hatch.lineTo(x + b.height(), b.top())
                        x += 17
                    _ = span
                    canvas.drawPath(hatch, hp)
                    canvas.restore()
                else:
                    fp = skia.Paint(AntiAlias=True, Color4f=d.fill, PathEffect=rough_effect(seed + 1, self.wobble * 0.8))
                    fp.setAlphaf(a * fa * d.fill.fA)
                    canvas.drawPath(d.fill_path, fp)
                canvas.restore()
        if d.stroke is not None:
            for k in range(max(1, d.sketch)):
                sp = skia.Paint(AntiAlias=True, Color4f=d.stroke, Style=skia.Paint.kStroke_Style,
                                StrokeWidth=d.sw if k == 0 else d.sw * 0.55, StrokeCap=skia.Paint.kRound_Cap,
                                StrokeJoin=skia.Paint.kRound_Join,
                                PathEffect=rough_effect(seed + 17 * k, self.wobble * (1 + 0.4 * k), trim=reveal))
                sp.setAlphaf(a * d.stroke.fA * (1 if k == 0 else 0.55))
                canvas.drawPath(d.path, sp)

    def _draw_actor(self, canvas, a: Actor, t: float, boil: int, alpha: float) -> None:
        vis, m, al, reveal = self._actor_matrix(a, t)
        if not vis:
            return
        canvas.save()
        if m is not None:
            canvas.concat(m)
        alpha *= al
        if a.anim in ("draw", "write") and reveal < 1 and a.total_len > 0:
            budget = reveal * a.total_len
            for d in a.drawables:
                local = clamp(budget / d.length)
                self._paint_drawable(canvas, d, local, boil, alpha, write=True)
                budget -= d.length
                if budget <= 0:
                    break
        else:
            for d in a.drawables:
                self._paint_drawable(canvas, d, 1.0, boil, alpha)
        for c in a.children:
            self._draw_actor(canvas, c, t, boil, alpha)
        canvas.restore()

    def draw(self, canvas, t: float, paper: "Paper | None" = None, camera: bool = True, boil_offset: int = 0) -> None:
        canvas.clear(self.bg if self.bg is not None else color4(PAPER, []))
        if paper is not None:
            paper.draw(canvas)
        boil = int(math.floor(t * BOIL_FPS)) + boil_offset
        canvas.save()
        if camera:
            canvas.concat(self.camera_matrix(t))
        self._draw_actor(canvas, self.root, t, boil, 1.0)
        canvas.restore()


    # ------------------------------------------------------------------ geometry audit (deterministic review input)
    def _walk_matrices(self, t: float, cam: skia.Matrix) -> list:
        """[(actor, total matrix incl. camera, settled)] for actors visible at local time t."""
        out = []

        def rec(a: Actor, M: skia.Matrix, parent_settled: bool) -> None:
            vis, m, al, _rev = self._actor_matrix(a, t)
            if not vis:
                return
            T = M if m is None else skia.Matrix.Concat(M, m)
            moving = a.anim not in ("none", "draw", "write", "fade") and t < a.at + a.dur
            exiting = a.out_at is not None and t >= a.out_at
            settled = parent_settled and not moving and not exiting and al >= 0.5
            if a is not self.root:
                out.append((a, T, settled))
            for c in a.children:
                rec(c, T, settled)

        rec(self.root, cam, True)
        return out

    def audit_frame(self, t: float, cam: skia.Matrix, margin: float = 12.0) -> list[dict]:
        """Where every settled element really is on screen at local time t (after actor + camera transforms)."""
        finds = []
        for a, T, settled in self._walk_matrices(t, cam):
            if not settled:
                continue
            det = abs(T.getScaleX() * T.getScaleY() - T.getSkewX() * T.getSkewY()) ** 0.5
            for d in a.drawables:
                if d.kind == "text":
                    vis = []
                    for gp, _cx, _cy, ci in d.glyphs:
                        r = T.mapRect(gp.computeTightBounds())
                        vis.append((ci, r.left() >= -2 and r.top() >= -2 and r.right() <= W + 2 and r.bottom() <= H + 2))
                    shown, lost = visible_words(d.text, vis)
                    finds.append({"kind": "text", "actor": a.id, "text": d.text, "size_px": round(d.font_size * det, 1), "glyphs": len(vis),
                                  "visible": sum(v for _, v in vis), "shown": shown, "lost": lost})
                else:
                    r = T.mapRect(d.bounds)
                    pad = d.sw * det / 2 if d.stroke is not None else 0.0
                    l, tp, rt, bt = r.left() - pad, r.top() - pad, r.right() + pad, r.bottom() + pad
                    over = max(-l, rt - W, -tp, bt - H, 0.0)
                    if over > margin:
                        w_, h_ = max(rt - l, 1.0), max(bt - tp, 1.0)
                        iw = max(0.0, min(rt, W) - max(l, 0)); ih = max(0.0, min(bt, H) - max(tp, 0))
                        frac = 1 - (iw * ih) / (w_ * h_)
                        if frac > 0.03:
                            side = max((("left", -l), ("right", rt - W), ("top", -tp), ("bottom", bt - H)), key=lambda x: x[1])[0]
                            finds.append({"kind": "off_canvas", "actor": a.id, "over_px": round(over, 1),
                                          "outside_share": round(frac, 3), "side": side})
        return finds

    def audit_geometry(self, t: float | None = None) -> list[dict]:
        """Stroke-only lines that run over the edge of a filled shape they mostly sit inside (e.g. wrinkle lines
        poking out of a finger), and violations of explicit data-inside containment. Camera-independent."""
        t = self.still_time() if t is None else t
        items = self._walk_matrices(t, skia.Matrix())
        fills, strokes, ancestry = [], [], {}
        for a, T, _settled in items:
            for c in a.walk():
                ancestry.setdefault(c.id, set()).add(a.id)
            for d in a.drawables:
                if d.kind != "path":
                    continue
                gp = skia.Path(d.path)
                gp.transform(T)
                if d.fill is not None:
                    fills.append((a.id, gp))
                elif d.stroke is not None:
                    strokes.append((a.id, gp, d))
        out = []
        for aid, sp, d in strokes:
            pts = sample_path(sp, 6.0)
            if len(pts) < 4:
                continue
            targets = [(fid, fp) for fid, fp in fills if not d.inside or d.inside in ancestry.get(fid, {fid}) or fid == d.inside]
            for fid, fp in targets:
                inside = [fp.contains(x, y) for x, y in pts]
                frac = sum(inside) / len(pts)
                b = fp.computeTightBounds()
                cx, cy = b.centerX(), b.centerY()
                far = 0
                for (x, y), ins in zip(pts, inside):
                    if not ins:
                        dx, dy = cx - x, cy - y
                        n = max((dx * dx + dy * dy) ** 0.5, 1e-6)
                        if not fp.contains(x + 6 * dx / n, y + 6 * dy / n):
                            far += 1
                if d.inside and fid == d.inside or d.inside and d.inside in ancestry.get(fid, set()):
                    if far >= 1:
                        out.append({"kind": "containment", "actor": aid, "container": d.inside, "points_outside": far,
                                    "inside_share": round(frac, 3)})
                    break
                if not d.inside and 0.75 <= frac < 1.0 and far >= 2 and fid != aid:
                    out.append({"kind": "overhang", "actor": aid, "over": fid, "points_outside": far,
                                "inside_share": round(frac, 3)})
        return out

    def hook_stats(self) -> dict:
        """What the very first frame shows (after the t=0 camera) and how fast the opening moves — deterministic
        inputs for the visual-hook gates and the reviewer. Safe area: 5 % side margins, 5 % top, bottom ≥ 5 %."""
        safe = (0.05 * W, 0.05 * H, 0.95 * W, 0.95 * H)
        items = [(a, T) for a, T, settled in self._walk_matrices(0.0, self.camera_matrix(0.0)) if settled and a.drawables]
        area, has_text, elements, subj, texts, margin = 0.0, False, 0, None, [], []
        det = lambda T: abs(T.getScaleX() * T.getScaleY() - T.getSkewX() * T.getSkewY()) ** 0.5  # noqa: E731
        for a, T in items:
            r = skia.Rect.MakeEmpty()
            for d in a.drawables:
                r.join(T.mapRect(d.bounds))
                if d.kind == "text":
                    has_text = True
                    gl = [(ci, T.mapRect(gp.computeTightBounds())) for gp, _cx, _cy, ci in d.glyphs]
                    vis = [(ci, g.left() >= -2 and g.top() >= -2 and g.right() <= W + 2 and g.bottom() <= H + 2) for ci, g in gl]
                    shown, lost = visible_words(d.text, vis)
                    tb = skia.Rect.MakeEmpty()
                    for _ci, g in gl:
                        tb.join(g)
                    texts.append({"actor": a.id, "text": d.text, "on_screen": shown, "lost_words": lost,
                                  "size_px": round(d.font_size * det(T), 1), "bbox": [round(tb.left()), round(tb.top()), round(tb.right()), round(tb.bottom())],
                                  "inside_safe": tb.left() >= safe[0] and tb.top() >= safe[1] and tb.right() <= safe[2] and tb.bottom() <= safe[3],
                                  "negation_hidden": any(norm_word(w) in NEGATIONS for w in lost)})
            iw = max(0.0, min(r.right(), W) - max(r.left(), 0)); ih = max(0.0, min(r.bottom(), H) - max(r.top(), 0))
            is_text = all(d.kind == "text" for d in a.drawables)
            if iw * ih > 0.002 * W * H or any(d.kind == "text" for d in a.drawables):
                elements += 1
            area += iw * ih
            if not is_text and (subj is None or iw * ih > subj[1]):
                subj = (a.id, iw * ih, ih / H, [round(r.left()), round(r.top()), round(r.right()), round(r.bottom())])
            if not is_text and iw * ih > 0.01 * W * H and (r.left() < safe[0] - 1 or r.right() > safe[2] + 1 or r.top() < safe[1] - 1):
                margin.append({"actor": a.id, "bbox": [round(r.left()), round(r.top()), round(r.right()), round(r.bottom())]})
        ents = sorted(a.at for a in self.root.walk() if a is not self.root and a.anim != "none")
        punches = sorted(p["at"] for p in self.camera["punch"])
        loops0 = any(a.loop for a, _T in items)
        first_ev = min(ents[:1] + punches[:1]) if (ents or punches) else None
        return {"elements_at_t0": elements, "text_at_t0": has_text, "subject_bbox_share_t0": round(min(area / (W * H), 1.0), 4),
                "subject": subj[0] if subj else None, "subject_height_ratio": round(subj[2], 3) if subj else 0.0,
                "subject_bbox": subj[3] if subj else None, "texts_t0": texts, "safe_margin_violations_t0": margin,
                "first_visual_event_s": round(first_ev, 3) if first_ev is not None else None, "idle_motion_at_t0": loops0,
                "hook_exception": self.hook_exception,
                "visual_events_first_1_5s": sum(1 for x in ents if x <= 1.5) + sum(1 for p in punches if p <= 1.5),
                "first_text_s": min((a.at for a in self.root.walk() if a is not self.root and any(d.kind == "text" for d in a.drawables)),
                                    default=None)}


    # ------------------------------------------------------------------ composition (Phase 3)
    def composition(self, t: float | None = None) -> dict:
        """Settled-state composition: main subject (+ a position/scale-invariant signature), subject height, dead space
        in the content zone (3×3 grid above the caption band) and a layout class computed from geometry."""
        t = self.still_time() if t is None else t
        zone = (0.05 * W, 0.05 * H, 0.95 * W, 1050.0)
        els = []
        for a, T, _settled in self._walk_matrices(t, skia.Matrix()):
            if not a.drawables or a is self.root:
                continue
            r = skia.Rect.MakeEmpty()
            for d in a.drawables:
                r.join(T.mapRect(d.bounds))
            is_text = all(d.kind == "text" for d in a.drawables)
            area = max(0.0, r.width()) * max(0.0, r.height())
            if area < 0.004 * W * H and not is_text:
                continue
            sig = a.lib or "geo:" + hashlib.blake2s(json.dumps(sorted(
                (d.kind, d.path.countVerbs() if d.path is not None else len(d.glyphs),
                 round(4 * min(4.0, d.bounds.width() / max(d.bounds.height(), 1))) / 4) for d in a.drawables)).encode(), digest_size=5).hexdigest()
            els.append({"actor": a.id, "text": is_text, "lib": a.lib, "sig": sig, "bbox": [r.left(), r.top(), r.right(), r.bottom()],
                        "area": area, "h": r.height() / H, "w": r.width() / W,
                        "cx": r.centerX() / W, "cy": r.centerY() / H})
        # keep only top-level groups: drop elements fully contained in a larger element of the same scene
        tops = [e for e in els if not any(o is not e and o["area"] > e["area"] and o["bbox"][0] <= e["bbox"][0] + 2 and
                                          o["bbox"][1] <= e["bbox"][1] + 2 and o["bbox"][2] >= e["bbox"][2] - 2 and
                                          o["bbox"][3] >= e["bbox"][3] - 2 for o in els)]
        shapes = sorted([e for e in tops if not e["text"]], key=lambda e: -e["area"])
        texts = [e for e in tops if e["text"]]
        main = shapes[0] if shapes else None
        cells = 0
        for i in range(3):
            for j in range(3):
                cx0 = zone[0] + (zone[2] - zone[0]) * i / 3; cx1 = zone[0] + (zone[2] - zone[0]) * (i + 1) / 3
                cy0 = zone[1] + (zone[3] - zone[1]) * j / 3; cy1 = zone[1] + (zone[3] - zone[1]) * (j + 1) / 3
                occ = sum(max(0.0, min(e["bbox"][2], cx1) - max(e["bbox"][0], cx0)) * max(0.0, min(e["bbox"][3], cy1) - max(e["bbox"][1], cy0))
                          for e in tops)
                cells += occ >= 0.12 * (cx1 - cx0) * (cy1 - cy0)
        layout = "scatter"
        if main and main["w"] >= 0.65 and main["w"] * W / max(main["h"] * H, 1) >= 1.5:
            layout = "panel"
        elif texts and max(t_["area"] for t_ in texts) >= 0.6 * (main["area"] if main else 1) and max(t_["h"] for t_ in texts) >= 0.06:
            layout = "text_led"
        elif len(shapes) >= 2 and shapes[1]["area"] >= 0.4 * shapes[0]["area"] and \
                max(e["cx"] for e in shapes if e["area"] >= 0.4 * shapes[0]["area"]) - \
                min(e["cx"] for e in shapes if e["area"] >= 0.4 * shapes[0]["area"]) >= 0.3:
            # several comparable subjects spread across the frame: 2 → split, ≥3 → grid
            layout = "grid" if len(shapes) >= 3 and shapes[2]["area"] >= 0.4 * shapes[0]["area"] else "split"
        elif main and main["lib"] == "dude":
            layout = "character"
        elif main and main["h"] >= 0.28 and (len(shapes) < 2 or main["area"] >= 2 * shapes[1]["area"]):
            layout = "hero"
        elif main and main["h"] < 0.28 and len(shapes) >= 2:
            layout = "scatter"
        return {"layout": layout, "main_subject": main["actor"] if main else None, "main_signature": main["sig"] if main else None,
                "main_height_ratio": round(main["h"], 3) if main else 0.0, "occupied_cells": cells, "empty_cells": 9 - cells,
                "elements": len(tops), "texts": len(texts),
                "layout_slots": [[round(e["cx"], 2), round(e["cy"], 2), round(e["h"], 2)] for e in shapes[:4]]}

    def still_time(self) -> float:
        """A moment when the most actors are on screen (for previews and gates)."""
        best, best_t = -1, self.duration * 0.85
        for k in range(1, 13):
            t = self.duration * k / 12
            n = sum(1 for a in self.root.walk() if a is not self.root and self._actor_matrix(a, t)[0])
            if n > best:
                best, best_t = n, t
        return best_t


# ----------------------------------------------------------------------------- paper
class Paper:
    """Static paper grain overlay (drawn above the background colour, below the ink)."""

    def __init__(self, kind: str = "plain", seed: int = 3):
        rng = np.random.default_rng(seed)
        small = rng.normal(0, 1, (H // 4, W // 4)).astype(np.float32)
        k = np.ones(5, np.float32) / 5
        small = np.apply_along_axis(lambda r: np.convolve(r, k, "same"), 1, small)
        small = np.apply_along_axis(lambda c: np.convolve(c, k, "same"), 0, small)
        blot = np.kron(small, np.ones((4, 4), np.float32))
        fine = rng.normal(0, 1, (H, W)).astype(np.float32)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        vign = ((xx / W - 0.5) ** 2 + (yy / H - 0.5) ** 2) * 1.6
        dark = np.clip(0.035 * fine + 0.05 * blot + 0.10 * vign, 0, 0.35)
        rgba = np.zeros((H, W, 4), np.uint8)
        rgba[..., 0:3] = np.array([92, 72, 40], np.uint8)
        rgba[..., 3] = (np.clip(dark, 0, 1) * 255).astype(np.uint8)
        if kind in ("grid", "dots", "lined"):
            line = np.zeros((H, W), bool)
            if kind == "grid":
                line[::60, :] = True
                line[:, ::60] = True
            elif kind == "lined":
                line[::72, :] = True
            else:
                line[::60, ::60] = True
                line[1::60, ::60] = True
                line[::60, 1::60] = True
            rgba[line, 0:3] = (120, 160, 205)
            rgba[line, 3] = np.maximum(rgba[line, 3], 46)
        # premultiply for skia
        a = rgba[..., 3:4].astype(np.float32) / 255
        rgba[..., 0:3] = (rgba[..., 0:3] * a).astype(np.uint8)
        self.image = skia.Image.fromarray(rgba, colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kPremul_AlphaType)

    def draw(self, canvas) -> None:
        canvas.drawImage(self.image, 0, 0)


# ----------------------------------------------------------------------------- image scenes (non-doodle shots)
class ImageScene:
    """A raster still inside a doodle video (photo, SD render): gentle drift, taped-on-paper look."""

    def __init__(self, path: str, duration: float, motion: dict | None = None, bg: str | None = None):
        self.img = skia.Image.open(path)
        self.duration = duration
        self.motion = (motion or {}).get("type", "zoom_in")
        self.strength = float((motion or {}).get("strength", 0.1))
        self.warnings: list[str] = []
        self.bg = color4(bg or PAPER, [])

    def events(self, offset: float = 0.0) -> list[dict]:
        return []

    def visual_event_times(self) -> list[float]:
        return [0.0]

    def draw(self, canvas, t: float, paper=None, camera: bool = True, boil_offset: int = 0) -> None:
        canvas.clear(self.bg)
        u = ease_in_out(clamp(t / max(self.duration, 0.1)))
        s = self.strength
        z = {"zoom_in": 1 + s * u, "zoom_out": 1 + s * (1 - u)}.get(self.motion, 1 + s)
        dx = {"pan_left": (0.5 - u) * 80, "pan_right": (u - 0.5) * 80}.get(self.motion, 0)
        dy = {"pan_up": (0.5 - u) * 120, "pan_down": (u - 0.5) * 120}.get(self.motion, 0)
        sc = max(W / self.img.width(), H / self.img.height()) * z
        w, h = self.img.width() * sc, self.img.height() * sc
        canvas.drawImageRect(self.img, skia.Rect.MakeXYWH((W - w) / 2 + dx, (H - h) / 2 + dy, w, h),
                             skia.SamplingOptions(skia.FilterMode.kLinear))

    def still_time(self) -> float:
        return self.duration / 2


# ----------------------------------------------------------------------------- compositor
TRANSITIONS = {"cut": 0.0, "whip": 0.28, "whip-up": 0.28, "paper": 0.36, "pop": 0.26, "flash": 0.22, "fade": 0.3}
AUTO_TRANSITIONS = ["whip", "cut", "paper", "pop", "cut", "whip-up", "cut", "flash"]


def _surface():
    return skia.Surface.MakeRaster(skia.ImageInfo.Make(W, H, skia.kRGBA_8888_ColorType, skia.kPremul_AlphaType))


class Timeline:
    """Shots (scenes with absolute start/end) + transitions → frames."""

    def __init__(self, shots: list[dict], scenes: list, duration: float, paper: Paper, seed: int = 1):
        self.shots, self.scenes, self.duration, self.paper = shots, scenes, duration, paper
        self.trans = []
        for i, sh in enumerate(shots):
            if i == 0:
                self.trans.append(("cut", 0.0))
                continue
            kind = (sh.get("transition") or {}).get("type") or "auto"
            legacy = {"fade": "fade", "dissolve": "fade", "slideleft": "whip", "slideup": "whip-up", "wipeleft": "whip",
                      "circleopen": "pop"}
            kind = legacy.get(kind, kind)
            if kind not in TRANSITIONS:
                kind = AUTO_TRANSITIONS[(i + seed) % len(AUTO_TRANSITIONS)]
            dur = float((sh.get("transition") or {}).get("duration") or TRANSITIONS[kind]) if kind != "cut" else 0.0
            if kind != "cut":
                dur = clamp(dur, 0.12, 0.5)
            self.trans.append((kind, dur))
        # Entrances cued at the very start of an incoming scene begin when its transition begins, so the new page
        # arrives with its first drawing already happening instead of sliding in blank. Word cues are untouched.
        for i, sc in enumerate(scenes):
            kind, dur = self.trans[i]
            if i and kind != "cut" and isinstance(sc, DoodleScene):
                for a in sc.root.walk():
                    if a is not sc.root and a.anim != "none" and a.at < 0.05:
                        a.at -= dur / 2
        self.sa, self.sb = _surface(), _surface()
        self.out = _surface()

    def events(self) -> list[dict]:
        ev = []
        for i, (sh, sc) in enumerate(zip(self.shots, self.scenes)):
            ev += sc.events(sh["start"])
            kind, dur = self.trans[i]
            if i and kind != "cut":
                ev.append({"t": round(sh["start"] - dur / 2, 3), "kind": "page" if kind == "paper" else "whoosh",
                           "dur": dur, "id": f"transition:{kind}"})
        return sorted(ev, key=lambda e: e["t"])

    def visual_events(self) -> list[float]:
        ts = []
        for sh, sc in zip(self.shots, self.scenes):
            ts += [sh["start"] + x for x in sc.visual_event_times()]
            ts.append(sh["start"])
        return sorted(ts)


    def audit(self, fps: float = 10.0) -> dict:
        """Deterministic visual audit of the whole video: off-canvas elements, cropped / meaning-changing text,
        small text, overhangs, containment, hook stats. Transition windows are skipped (pages move on purpose)."""
        agg: dict = {}
        geometry, scenes_meta, labels = [], [], []
        for i, (sh, sc) in enumerate(zip(self.shots, self.scenes)):
            if not isinstance(sc, DoodleScene):
                continue
            s0 = sh["start"]
            s1 = self.shots[i + 1]["start"] if i + 1 < len(self.shots) else self.duration
            lo = s0 + self.trans[i][1] / 2 + 0.02
            hi = s1 - (self.trans[i + 1][1] / 2 if i + 1 < len(self.shots) else 0.0) - 0.02
            sid = sh.get("id", f"s{i + 1}")
            n = 0
            t = lo
            while t < hi:
                for f in sc.audit_frame(t - s0, sc.camera_matrix(t - s0)):
                    if f["kind"] == "text":
                        if f["visible"] == f["glyphs"] and f["size_px"] >= 34:
                            continue
                        if f["visible"] == f["glyphs"]:
                            kind = "text_small"
                        elif f["visible"] == 0:
                            kind = "text_offscreen"
                        else:
                            kind = "meaning_cropped" if any(norm_word(w) in NEGATIONS for w in f["lost"]) else "text_cropped"
                    else:
                        kind = "off_canvas_punch" if sc.punch_level(t - s0) > 0.1 else f["kind"]
                    key = (sid, f["actor"], kind)
                    r = agg.setdefault(key, {"scene": sid, "actor": f["actor"], "kind": kind, "first_s": round(t, 2),
                                             "last_s": round(t, 2), "frames": 0, "detail": {}})
                    r["last_s"] = round(t, 2)
                    r["frames"] += 1
                    if f["kind"] == "text":
                        r["detail"] = {"text": f["text"], "on_screen": f["shown"], "lost_words": f["lost"],
                                       "min_size_px": min(f["size_px"], r["detail"].get("min_size_px", 1e9))}
                    else:
                        r["detail"] = {"over_px": max(f["over_px"], r["detail"].get("over_px", 0)), "side": f["side"]}
                n += 1
                t += 1.0 / fps
            merged: dict = {}
            for g in sc.audit_geometry():
                k = (g["actor"], g["kind"], g.get("over") or g.get("container"))
                if k in merged:
                    merged[k]["points_outside"] += g["points_outside"]
                    merged[k]["paths"] += 1
                else:
                    merged[k] = {"scene": sid, **g, "paths": 1}
            geometry.extend(merged.values())
            scenes_meta.append({"scene": sid, "start": round(s0, 2), "end": round(s1, 2), "frames_checked": n})
            for act in sc.root.walk():
                for d in act.drawables:
                    if d.kind == "text" and d.text.strip():
                        labels.append({"scene": sid, "actor": act.id, "text": d.text, "at_s": round(s0 + max(act.at, 0.0), 3)})
        issues = [r for r in agg.values() if r["frames"] >= 2] + \
                 [{"scene": g["scene"], "actor": g["actor"], "kind": g["kind"], "frames": None, "detail": g} for g in geometry]
        sev = {"meaning_cropped": "blocking", "containment": "blocking", "text_cropped": "major", "text_offscreen": "major",
               "off_canvas": "major", "off_canvas_punch": "minor", "overhang": "major", "text_small": "minor"}
        for r in issues:
            r["severity"] = sev[r["kind"]]
            if r["kind"] == "text_small" and r["detail"].get("min_size_px", 99) < 26:
                r["severity"] = "major"
        hook = self.scenes[0].hook_stats() if isinstance(self.scenes[0], DoodleScene) else {}
        composition = [{"scene": sh.get("id", f"s{i + 1}"), **sc.composition()} for i, (sh, sc) in enumerate(zip(self.shots, self.scenes))
                       if isinstance(sc, DoodleScene)]
        return {"version": 1, "fps": fps, "canvas": [W, H], "scenes": scenes_meta, "issues": issues, "hook": hook, "labels": labels,
                "composition": composition,
                "visual_events": [round(x, 3) for x in self.visual_events()]}

    def _scene_at(self, t: float) -> int:
        idx = 0
        for i, sh in enumerate(self.shots):
            if t >= sh["start"] - 1e-6:
                idx = i
        return idx

    def frame(self, t: float):
        i = self._scene_at(t)
        nxt = i + 1 if i + 1 < len(self.shots) else None
        if nxt is not None:
            kind, dur = self.trans[nxt]
            b = self.shots[nxt]["start"]
            if kind != "cut" and t >= b - dur / 2:
                return self._transition(i, nxt, kind, dur, t, b)
        kind, dur = self.trans[i]
        b = self.shots[i]["start"]
        if i and kind != "cut" and t < b + dur / 2:
            return self._transition(i - 1, i, kind, dur, t, b)
        self.scenes[i].draw(self.out.getCanvas(), t - self.shots[i]["start"], self.paper)
        return self.out

    def _transition(self, ia: int, ib: int, kind: str, dur: float, t: float, b: float):
        q = clamp((t - (b - dur / 2)) / dur)
        self.scenes[ia].draw(self.sa.getCanvas(), t - self.shots[ia]["start"], self.paper)
        self.scenes[ib].draw(self.sb.getCanvas(), t - self.shots[ib]["start"], self.paper, boil_offset=0)
        A, B = self.sa.makeImageSnapshot(), self.sb.makeImageSnapshot()
        c = self.out.getCanvas()
        c.clear(skia.ColorWHITE)
        if kind in ("whip", "whip-up"):
            e = ease_in_out(q)
            vel = 6 * q * (1 - q)  # bell-shaped speed → motion blur
            blur = skia.Paint(ImageFilter=skia.ImageFilters.Blur(60 * vel if kind == "whip" else 0.01,
                                                                 0.01 if kind == "whip" else 80 * vel, skia.TileMode.kClamp))
            if kind == "whip":
                c.drawImage(A, -e * W, 0, paint=blur)
                c.drawImage(B, (1 - e) * W, 0, paint=blur)
            else:
                c.drawImage(A, 0, -e * H, paint=blur)
                c.drawImage(B, 0, (1 - e) * H, paint=blur)
        elif kind == "paper":
            e = ease_out_cubic(q)
            dim = skia.Paint()
            cf = skia.ColorFilters.Blend(skia.Color4f(0, 0, 0, 0.18 * e).toColor(), skia.BlendMode.kSrcATop)
            if cf is not None:   # Phase 5: skia returns None for a fully transparent dim (the transition's first frame) → crash
                dim.setColorFilter(cf)
            c.drawImage(A, 0, -60 * e, paint=dim)
            y = (1 - e) * H
            sh = skia.Paint(Color=skia.Color(0, 0, 0, 70), ImageFilter=skia.ImageFilters.Blur(18, 18))
            c.drawRect(skia.Rect.MakeXYWH(0, y - 6, W, H), sh)
            c.drawImage(B, 0, y)
        elif kind == "pop":
            if q < 0.5:
                e = ease_in_cubic(q / 0.5)
                c.save(); c.translate(W / 2, H / 2); c.scale(1 + 0.18 * e, 1 + 0.18 * e); c.translate(-W / 2, -H / 2)
                p = skia.Paint(); p.setAlphaf(1 - 0.6 * e)
                c.drawImage(A, 0, 0, paint=p); c.restore()
            else:
                e = back_out((q - 0.5) / 0.5, 1.4)
                s = 0.86 + 0.14 * e
                c.save(); c.translate(W / 2, H / 2); c.scale(s, s); c.translate(-W / 2, -H / 2)
                c.drawImage(B, 0, 0); c.restore()
        elif kind == "flash":
            c.drawImage(A if q < 0.5 else B, 0, 0)
            p = skia.Paint(Color=skia.ColorWHITE)
            p.setAlphaf(1 - abs(q - 0.5) * 2)
            c.drawRect(skia.Rect.MakeWH(W, H), p)
        else:  # fade
            c.drawImage(A, 0, 0)
            p = skia.Paint()
            p.setAlphaf(ease_in_out(q))
            c.drawImage(B, 0, 0, paint=p)
        return self.out


def build_timeline(sb: dict, timing: dict, base_dir: Path | None = None) -> Timeline:
    """sb = retimed storyboard (with `shots`); timing = voice timing.json."""
    style = sb.get("style", {})
    palette = style.get("palette") or []
    paper = Paper(style.get("paper", "plain"), seed=h32(sb.get("video_id", "v")) % 1000)
    shots = sb["shots"]
    duration = float(timing["duration_s"])
    scenes = []
    for i, sh in enumerate(shots):
        s0 = sh["start"]
        s1 = shots[i + 1]["start"] if i + 1 < len(shots) else duration
        words = [{"w": w["w"], "start": w["start"] - s0, "end": w["end"] - s0} for w in timing["words"]
                 if s0 - 0.05 <= w["start"] < s1 - 0.02]
        v = sh["visual"]
        if v.get("kind") == "doodle" or v.get("used_kind") == "doodle":
            svg = v.get("svg") or Path(v["svg_path"] if Path(v["svg_path"]).is_absolute() else (base_dir or Path(".")) / v["svg_path"]).read_text(encoding="utf-8")
            sc = DoodleScene(svg, palette, words, s1 - s0, style, scene_id=f"{sb.get('video_id', 'v')}:{sh.get('id', i)}",
                             camera=sh.get("camera") or {"drift": ["in", "out", "left", "in", "right", "out"][i % 6]},
                             bg=sh.get("bg"))
        else:
            sc = ImageScene(v["path"], s1 - s0, sh.get("motion"), sh.get("bg"))
        scenes.append(sc)
    return Timeline(shots, scenes, duration, paper, seed=h32(sb.get("video_id", "v")) % 7)


def render_video(tl: Timeline, out: Path, fps: int = FPS, crf: int = 17, preset: str = "veryfast", ffmpeg: str = "ffmpeg") -> int:
    n = round(tl.duration * fps)
    cmd = [ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
           "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-threads", X264_THREADS, "-pix_fmt", "yuv420p", "-r", str(fps), str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for f in range(n):
            surf = tl.frame(f / fps)
            proc.stdin.write(surf.makeImageSnapshot().tobytes())
    finally:
        proc.stdin.close()
        rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg exited {rc} while encoding doodle frames")
    return n


def render_still(scene, out_png: Path, t: float | None = None, scale: int = 2, paper: Paper | None = None) -> None:
    surf = skia.Surface.MakeRaster(skia.ImageInfo.Make(W * scale, H * scale, skia.kRGBA_8888_ColorType, skia.kPremul_AlphaType))
    c = surf.getCanvas()
    c.scale(scale, scale)
    scene.draw(c, scene.still_time() if t is None else t, paper or Paper(), camera=False)
    surf.makeImageSnapshot().save(str(out_png), skia.kPNG)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("still")
    s.add_argument("--svg", required=True); s.add_argument("--out", required=True)
    s.add_argument("--t", type=float); s.add_argument("--scale", type=int, default=1)
    s.add_argument("--duration", type=float, default=4.0); s.add_argument("--paper", default="plain")
    a = ap.parse_args()
    sc = DoodleScene(Path(a.svg).read_text(encoding="utf-8"), duration=a.duration)
    render_still(sc, Path(a.out), a.t, a.scale, Paper(a.paper))
    print(json.dumps({"out": a.out, "warnings": sc.warnings}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
