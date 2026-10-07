"""cf_common — shared contract library for the Content Factory skills.

Canonical copy lives in content-factory/scripts/; every other skill ships an
identical copy so it can run on its own. Python 3.10+, standard library only.

Provides:
  * stage IDs and artifact schemas (the inter-skill contract)
  * StageResult: the envelope every stage writes (status, gate checks, errors, outputs, provenance)
  * a small JSON-schema validator (subset: type/required/properties/items/enum/min/max/length)
  * ffmpeg/ffprobe helpers that are safe on Linux and Windows paths
"""
from __future__ import annotations

import datetime as _dt
import functools
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

CONTRACT_VERSION = "cf/1.1"  # 1.1: doodle visuals, page transitions, optional motion

# Pipeline order. LOCALIZE runs only for language variants; ANALYTICS runs after publishing.
STAGES = ["RESEARCH", "IDEATION", "SELECTION", "HOOK", "SCRIPT", "LOCALIZE", "AUDIO",
          "VISUAL_PLAN", "VIDEO", "SUBTITLES", "QA", "REGENERATION", "PACKAGE", "ANALYTICS"]
GLOBAL_STAGES = ["RESEARCH", "IDEATION", "SELECTION"]
# AUDIO precedes VISUAL_PLAN (cf/1.1): doodle word cues are planned against the real narration timing, and a
# VISUAL_PLAN fix never invalidates the voice-over.
VIDEO_STAGES = ["HOOK", "SCRIPT", "LOCALIZE", "AUDIO", "VISUAL_PLAN", "VIDEO", "SUBTITLES", "QA", "PACKAGE"]
STAGE_OWNER = {
    "RESEARCH": "content-research", "IDEATION": "content-strategy", "SELECTION": "content-strategy",
    "HOOK": "hook-engineering", "SCRIPT": "short-form-script", "LOCALIZE": "multilingual-content",
    "VISUAL_PLAN": "visual-storyboarding", "AUDIO": "voice-production", "VIDEO": "video-production",
    "SUBTITLES": "subtitle-production", "QA": "video-quality-assurance", "REGENERATION": "content-factory",
    "PACKAGE": "content-factory", "ANALYTICS": "content-analytics",
}
SEVERITIES = ("blocking", "major", "minor")


# ----------------------------------------------------------------------------- basics
def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def log(*msg) -> None:
    print("[cf]", *msg, file=sys.stderr, flush=True)


def read_json(path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return str(path)


def sha256_file(path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def slug(text: str, maxlen: int = 48) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return (s or "x")[:maxlen]


def skills_root() -> Path:
    """Directory that holds the sibling factory skills (…/skills/<name>/scripts/this_file)."""
    env = os.environ.get("CF_SKILLS_ROOT")
    return Path(env) if env else Path(__file__).resolve().parents[2]


def skill_script(skill: str, script: str) -> Path:
    p = skills_root() / skill / "scripts" / script
    if not p.exists():
        raise FileNotFoundError(f"{skill}/scripts/{script} not found under {skills_root()} "
                                f"(install all factory skills side by side or set CF_SKILLS_ROOT)")
    return p


def cache_dir() -> Path:
    d = Path(os.environ.get("CF_CACHE", Path.home() / ".cache" / "content-factory"))
    d.mkdir(parents=True, exist_ok=True)
    return d


# ----------------------------------------------------------------------------- subprocess / ffmpeg
class CommandError(RuntimeError):
    def __init__(self, cmd, code, stderr):
        super().__init__(f"command failed ({code}): {' '.join(map(str, cmd))[:300]}\n{stderr[-1500:]}")
        self.cmd, self.code, self.stderr = cmd, code, stderr


def run(cmd, check: bool = True, timeout: int | None = None) -> subprocess.CompletedProcess:
    cmd = [str(c) for c in cmd]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        raise CommandError(cmd, p.returncode, p.stderr or p.stdout)
    return p


# Phase 5: libx264 picks its thread count from the CPU count and the bitstream changes with it, so a 2-core and a
# 4-core machine encoded different files from identical frames. Every encode uses this fixed count instead.
X264_THREADS = "4"


def ffmpeg_bin() -> str:
    return os.environ.get("CF_FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"


def decode_errors(path, limit: int = 5) -> list[str]:
    """Fully decode a media file and return ffmpeg's error lines (empty list = every packet decodes).

    A gate that only samples frames can pass a truncated or corrupted container; this cannot."""
    p = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(path), "-f", "null", "-"], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    lines = [ln for ln in (p.stderr or "").splitlines() if ln.strip()]
    if p.returncode != 0 and not lines:
        lines = [f"ffmpeg exited {p.returncode}"]
    return lines[:limit] + ([f"... {len(lines) - limit} more"] if len(lines) > limit else [])


def ffprobe_bin() -> str:
    return os.environ.get("CF_FFPROBE") or shutil.which("ffprobe") or "ffprobe"


def ffprobe(path) -> dict:
    p = run([ffprobe_bin(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    return json.loads(p.stdout)


def media_duration(path) -> float:
    return float(ffprobe(path)["format"]["duration"])


def ff_filter_path(path) -> str:
    """Escape a file path for use inside an ffmpeg filtergraph option (ass=, subtitles=, fontsdir=)."""
    p = str(Path(path).resolve()).replace("\\", "/")
    p = p.replace(":", r"\:").replace("'", r"\'")
    return f"'{p}'"


# ----------------------------------------------------------------------------- schema validator
def _type_ok(value, t) -> bool:
    if isinstance(t, list):
        return any(_type_ok(value, x) for x in t)
    return {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str), "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "null": value is None,
    }.get(t, True)


def validate(obj, schema, path: str = "$") -> list[str]:
    """Return a list of human-readable violations (empty list = valid)."""
    errs: list[str] = []
    t = schema.get("type")
    if t and not _type_ok(obj, t):
        return [f"{path}: expected {t}, got {type(obj).__name__}"]
    if "enum" in schema and obj not in schema["enum"]:
        errs.append(f"{path}: {obj!r} not in {schema['enum']}")
    if isinstance(obj, str):
        if len(obj) < schema.get("minLength", 0):
            errs.append(f"{path}: shorter than {schema['minLength']} chars")
        if "maxLength" in schema and len(obj) > schema["maxLength"]:
            errs.append(f"{path}: longer than {schema['maxLength']} chars")
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        if "minimum" in schema and obj < schema["minimum"]:
            errs.append(f"{path}: {obj} < {schema['minimum']}")
        if "maximum" in schema and obj > schema["maximum"]:
            errs.append(f"{path}: {obj} > {schema['maximum']}")
    if isinstance(obj, dict):
        for k in schema.get("required", []):
            if k not in obj:
                errs.append(f"{path}: missing required '{k}'")
        for k, sub in schema.get("properties", {}).items():
            if k in obj:
                errs += validate(obj[k], sub, f"{path}.{k}")
    if isinstance(obj, list):
        if len(obj) < schema.get("minItems", 0):
            errs.append(f"{path}: needs at least {schema['minItems']} items")
        if "maxItems" in schema and len(obj) > schema["maxItems"]:
            errs.append(f"{path}: more than {schema['maxItems']} items")
        if "items" in schema:
            for i, item in enumerate(obj):
                errs += validate(item, schema["items"], f"{path}[{i}]")
    return errs


S, N, I, B = {"type": "string"}, {"type": "number"}, {"type": "integer"}, {"type": "boolean"}
NES = {"type": "string", "minLength": 1}
NUM = {"type": "number"}
STRS = {"type": "array", "items": S}
SCORE5 = {"type": "number", "minimum": 1, "maximum": 5}
FIX_ROUTE = {"type": ["object", "null"], "required": ["stage", "action"],
             "properties": {"stage": {"type": "string", "enum": STAGES}, "action": NES, "params": {"type": "object"}}}

SCHEMAS: dict[str, dict] = {
    "brief": {"type": "object", "required": ["run_id", "topic", "count", "languages", "platforms"], "properties": {
        "run_id": NES, "topic": NES, "count": {"type": "integer", "minimum": 1, "maximum": 50},
        "languages": {"type": "array", "minItems": 1, "items": NES}, "platforms": {"type": "array", "minItems": 1, "items": NES},
        "duration_s": {"type": "object", "properties": {"min": N, "max": N, "target": N}},
        "audience": S, "tone": S, "style": S, "constraints": STRS}},
    "research_dossier": {"type": "object", "required": ["topic", "sources", "facts"], "properties": {
        "topic": NES,
        "sources": {"type": "array", "minItems": 1, "items": {"type": "object", "required": ["id", "url", "title"], "properties": {
            "id": NES, "url": NES, "title": NES, "publisher": S, "published": {"type": ["string", "null"]}, "accessed": S,
            "kind": {"type": "string", "enum": ["primary", "secondary", "reference", "news", "opinion", "social"]}}}},
        "facts": {"type": "array", "minItems": 1, "items": {"type": "object", "required": ["id", "claim", "source_ids", "risk"], "properties": {
            "id": NES, "claim": {"type": "string", "minLength": 10}, "source_ids": {"type": "array", "minItems": 1, "items": NES},
            "risk": {"type": "string", "enum": ["low", "medium", "high"]}, "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "quote": {"type": ["object", "null"], "properties": {"text": S, "source_id": S}}}}}}},
    "trend_report": {"type": "object", "required": ["signals"], "properties": {
        "signals": {"type": "array", "items": {"type": "object", "required": ["term", "score", "phase"], "properties": {
            "term": NES, "score": N, "phase": {"type": "string", "enum": ["emerging", "rising", "peaking", "evergreen", "declining", "unknown"]}}}}}},
    "ideas": {"type": "object", "required": ["ideas"], "properties": {
        "ideas": {"type": "array", "minItems": 1, "items": {"type": "object",
            "required": ["id", "title", "angle", "format", "value_add", "fact_ids", "scores"], "properties": {
            "id": NES, "title": NES, "angle": {"type": "string", "minLength": 10},
            "format": {"type": "string", "enum": ["explainer", "myth-bust", "listicle", "story", "how-to", "comparison", "question", "news"]},
            "pillar": S, "value_add": {"type": "string", "minLength": 30}, "fact_ids": STRS,
            "required_capabilities": STRS,
            "scores": {"type": "object", "required": ["audience_value", "curiosity", "originality", "evidence_strength", "visual_potential", "brand_safety"],
                       "properties": {k: SCORE5 for k in ["audience_value", "curiosity", "originality", "evidence_strength", "visual_potential", "brand_safety"]}}}}}}},
    "hooks": {"type": "object", "required": ["video_id", "language", "candidates"], "properties": {
        "video_id": NES, "language": NES,
        "candidates": {"type": "array", "minItems": 3, "items": {"type": "object", "required": ["id", "spoken", "on_screen", "visual", "archetype"], "properties": {
            "id": NES, "spoken": NES, "on_screen": S, "visual": NES, "archetype": NES}}}}},
    # cf/1.1 Phase 2: hook engine + script variants (the v1 "hooks" contract above stays for older runs)
    "hook_candidates": {"type": "object", "required": ["video_id", "language", "topic", "candidates"], "properties": {
        "video_id": NES, "language": NES, "topic": NES, "strategy_note": S,
        "candidates": {"type": "array", "minItems": 5, "items": {"type": "object", "required": [
            "hook_id", "spoken_text", "visual_concept", "on_screen_text", "curiosity_mechanism", "tension", "target_emotion",
            "first_frame_concept", "first_frame_subject", "first_frame_text", "visual_action", "payoff_connection",
            "why_it_should_work", "first_frame_svg"], "properties": {
            "hook_id": NES, "spoken_text": NES, "visual_concept": NES, "on_screen_text": S, "curiosity_mechanism": NES,
            "tension": NES, "target_emotion": NES, "estimated_duration": NUM, "first_frame_concept": NES,
            "first_frame_subject": NES, "first_frame_text": S, "visual_action": NES, "payoff_connection": NES,
            "why_it_should_work": NES, "first_frame_svg": NES, "fact_ids": STRS, "hook_exception": S}}}}},
    "script_variants": {"type": "object", "required": ["video_id", "language", "hook_id", "variants"], "properties": {
        "video_id": NES, "language": NES, "hook_id": NES,
        "variants": {"type": "array", "minItems": 2, "items": {"type": "object", "required": ["variant_id", "structure", "beats", "publish"],
                     "properties": {"variant_id": NES, "structure": NES, "beats": {"type": "array", "minItems": 3}, "publish": {"type": "object"}}}}}},
    "script": {"type": "object", "required": ["video_id", "language", "beats", "publish"], "properties": {
        "video_id": NES, "language": NES, "hook_id": S,
        "beats": {"type": "array", "minItems": 3, "items": {"type": "object", "required": ["id", "role", "text"], "properties": {
            "id": NES, "role": {"type": "string", "enum": ["hook", "setup", "value", "twist", "payoff", "cta", "loop"]},
            "text": NES, "on_screen": S, "claim_ids": STRS, "pause_before": NUM, "pause_after": NUM,
            "visual_intent": S, "emphasis": STRS}}},
        "publish": {"type": "object", "required": ["title_options", "description", "hashtags"], "properties": {
            "title_options": {"type": "array", "minItems": 1, "items": NES}, "description": S, "hashtags": STRS}},
        # Phase 3.5: one optional CTA decision (rules in short-form-script/scripts/cta.py)
        "cta": {"type": "object", "required": ["needed", "decision_reason"], "properties": {
            "needed": {"type": "boolean"}, "decision_reason": NES,
            "type": {"type": "string", "enum": ["follow", "subscribe", "like", "comment", "save", "share", "part_2", "question", "profile"]},
            "placement": {"type": "string", "enum": ["after_payoff", "integrated", "on_screen_only"]},
            "modality": {"type": "string", "enum": ["spoken", "on_screen", "both"]},
            "beat_id": S, "spoken": S, "on_screen": S, "continuation": S}}}},
    # Phase 4: packaging — ≥3 complete packages (title + thumbnail + opening promise + copy) for one finished video
    "package_candidates": {"type": "object", "required": ["video_id", "language", "candidates"], "properties": {
        "video_id": NES, "language": NES,
        "candidates": {"type": "array", "minItems": 3, "items": {"type": "object", "required": [
            "id", "strategy", "title", "opening_promise", "thumbnail", "description", "hashtags", "claim_ids"], "properties": {
            "id": NES, "strategy": {"type": "string", "enum": ["curiosity", "mechanism", "question", "challenge", "myth_bust",
                                                               "contrast", "utility", "story"]},
            "title": NES, "opening_promise": NES, "description": NES, "hashtags": {"type": "array", "minItems": 1, "items": NES},
            "claim_ids": STRS, "caption_cta": S, "rationale": S,
            "thumbnail": {"type": "object", "required": ["concept", "text", "svg", "depicts"], "properties": {
                "concept": NES, "text": S, "svg": NES, "depicts": STRS}}}}}}},
    "storyboard": {"type": "object", "required": ["video_id", "style", "scenes"], "properties": {
        "video_id": NES, "style": {"type": "object", "required": ["palette"], "properties": {"palette": {"type": "array", "minItems": 2, "items": S}}},
        "scenes": {"type": "array", "minItems": 2, "items": {"type": "object", "required": ["id", "beat_ids", "visual"], "properties": {
            "id": NES, "beat_ids": {"type": "array", "minItems": 1, "items": NES},
            "visual": {"type": "object", "required": ["kind"], "properties": {
                "kind": {"type": "string", "enum": ["doodle", "svg", "procedural", "image", "video", "sd_forge", "image_api", "stock"]}}},
            "motion": {"type": "object", "required": ["type"], "properties": {
                "type": {"type": "string", "enum": ["zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down", "static"]}}},
            "transition": {"type": "object", "properties": {"type": {"type": "string", "enum": ["cut", "fade", "slideleft", "slideup", "wipeleft", "circleopen", "dissolve", "whip", "whip-up", "paper", "pop", "flash", "auto"]}, "duration": N}}}}}}},
    "voice_timing": {"type": "object", "required": ["video_id", "language", "audio_path", "duration_s", "words", "sentences", "backend"], "properties": {
        "video_id": NES, "language": NES, "audio_path": NES, "duration_s": N, "backend": NES,
        "words": {"type": "array", "minItems": 1, "items": {"type": "object", "required": ["w", "start", "end", "sentence"], "properties": {"w": NES, "start": N, "end": N, "sentence": I}}},
        "sentences": {"type": "array", "minItems": 1, "items": {"type": "object", "required": ["i", "text", "start", "end"]}}}},
    "qa_report": {"type": "object", "required": ["video_id", "status", "checks"], "properties": {
        "video_id": NES, "status": {"type": "string", "enum": ["passed", "passed_with_warnings", "failed", "pending_review"]},
        "checks": {"type": "array", "items": {"type": "object", "required": ["id", "passed", "severity"]}}}},
    "provenance": {"type": "object", "required": ["video_id", "final", "assets", "disclosure"], "properties": {
        "assets": {"type": "array", "items": {"type": "object", "required": ["role", "sha256", "license", "source"]}}}},
    "stage_result": {"type": "object", "required": ["contract", "stage", "skill", "status", "attempt", "gate", "outputs", "errors"], "properties": {
        "stage": {"type": "string", "enum": STAGES},
        "status": {"type": "string", "enum": ["passed", "passed_with_warnings", "failed", "error", "pending_review"]},
        "errors": {"type": "array", "items": {"type": "object", "required": ["code", "severity", "message", "retryable"], "properties": {
            "severity": {"type": "string", "enum": list(SEVERITIES)}, "fix_route": FIX_ROUTE}}}}},
}


def validate_artifact(obj, kind: str) -> list[str]:
    return validate(obj, SCHEMAS[kind])


# ----------------------------------------------------------------------------- stage envelope
class StageResult:
    """Envelope written by every stage: `<stage dir>/result.json`.

    A failed check with severity blocking/major makes the stage `failed`; a failed minor check makes it
    `passed_with_warnings`. Every failed check becomes a structured error carrying a fix_route so the
    orchestrator can trigger correction instead of propagating bad output.
    """

    def __init__(self, stage: str, skill: str, video_id: str | None = None, run_id: str | None = None,
                 attempt: int = 1):
        assert stage in STAGES, stage
        self.d = {"contract": CONTRACT_VERSION, "stage": stage, "skill": skill, "run_id": run_id,
                  "video_id": video_id, "attempt": attempt, "status": "passed", "started_at": now_iso(),
                  "finished_at": None, "inputs": [], "outputs": [], "gate": {"checks": []},
                  "errors": [], "metrics": {}, "provenance": []}

    def input(self, path, role: str):
        p = Path(path)
        self.d["inputs"].append({"role": role, "path": str(p), "sha256": sha256_file(p) if p.is_file() else None})

    def output(self, path, role: str, media_type: str | None = None):
        p = Path(path)
        self.d["outputs"].append({"role": role, "path": str(p), "media_type": media_type,
                                  "sha256": sha256_file(p) if p.is_file() else None})

    def metric(self, key: str, value):
        self.d["metrics"][key] = value

    def provenance(self, record: dict):
        self.d["provenance"].append(record)

    def check(self, cid: str, passed: bool, severity: str = "blocking", message: str = "", value=None,
              threshold=None, fix: dict | None = None, retryable: bool = True) -> bool:
        assert severity in SEVERITIES
        passed = bool(passed)
        self.d["gate"]["checks"].append({"id": cid, "passed": passed, "severity": severity, "value": value,
                                         "threshold": threshold, "message": message})
        if not passed:
            self.d["errors"].append({"code": cid, "severity": severity, "message": message or cid,
                                     "evidence": {"value": value, "threshold": threshold},
                                     "retryable": retryable, "fix_route": fix})
        return passed

    def fail(self, code: str, message: str, fix: dict | None = None, retryable: bool = False):
        self.check(code, False, "blocking", message, fix=fix, retryable=retryable)

    @property
    def failed(self) -> bool:
        return any(e["severity"] in ("blocking", "major") for e in self.d["errors"])

    def finalize(self, path, status: str | None = None) -> dict:
        if status:
            self.d["status"] = status
        elif self.failed:
            self.d["status"] = "failed"
        elif self.d["errors"]:
            self.d["status"] = "passed_with_warnings"
        self.d["finished_at"] = now_iso()
        self.d["gate"]["passed"] = self.d["status"] in ("passed", "passed_with_warnings")
        write_json(path, self.d)
        return self.d


def fix(stage: str, action: str, **params) -> dict:
    return {"stage": stage, "action": action, "params": params}


def exit_for(result: dict) -> int:
    """0 = gate passed, 2 = gate failed (structured errors in result.json), 3 = waiting for review."""
    return {"passed": 0, "passed_with_warnings": 0, "pending_review": 3}.get(result["status"], 2)


def stage_main(stage: str, skill: str):
    """Decorator for CLI entry points: any crash becomes a structured INTERNAL error envelope."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(args):
            try:
                return fn(args)
            except Exception as exc:  # noqa: BLE001 — convert every crash into a contract error
                out = getattr(args, "result", None) or "result.json"
                sr = StageResult(stage, skill, getattr(args, "video_id", None))
                sr.fail("INTERNAL.EXCEPTION", f"{type(exc).__name__}: {exc}", retryable=True)
                sr.d["errors"][-1]["evidence"] = {"traceback": traceback.format_exc()[-2500:]}
                sr.finalize(out, status="error")
                log(f"{stage} crashed: {exc}")
                return 1
        return wrapper
    return deco


def emit(result: dict) -> None:
    """Print a compact summary (what the calling agent reads)."""
    summary = {"stage": result["stage"], "video_id": result.get("video_id"), "status": result["status"],
               "failed_checks": [{"id": e["code"], "severity": e["severity"], "message": e["message"][:200],
                                  "fix_route": e.get("fix_route")} for e in result["errors"]],
               "metrics": result.get("metrics", {})}
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    # `python cf_common.py export-schemas <dir>` writes every contract schema as JSON Schema files.
    if len(sys.argv) == 3 and sys.argv[1] == "export-schemas":
        out = Path(sys.argv[2])
        out.mkdir(parents=True, exist_ok=True)
        for name, sch in SCHEMAS.items():
            write_json(out / f"{name}.schema.json",
                       {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": f"cf.{name}", **sch})
        print(f"exported {len(SCHEMAS)} schemas to {out}")
    else:
        print("usage: cf_common.py export-schemas <dir>")
