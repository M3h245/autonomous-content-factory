#!/usr/bin/env python3
"""review_packet — the data boundary between AUTHORING and REVIEW.

  review_packet.py build --final final.mp4 --timing timing.json --captions captions.ass --publish script.json
                         --out PACKET_DIR [--dossier dossier.json] [--measure qa_report=qa_report.json ...]
                         [--cover-at 0.7] [--min-s 20 --max-s 45]

The packet is the ONLY thing the independent reviewer may read. It contains finished artifacts and deterministic
measurements, never creative intent:
  media/final.mp4                    the video exactly as it will ship (hash-pinned)
  frames/first_frame.png, hook_strip.jpg (0-3.2 s), contact.jpg (16 evenly spaced), ending_strip.jpg (last 2.4 s),
  frames/cover.jpg                   built with the same command package_run uses for the shipped cover
  text/transcript.json               what is actually SAID (words + times from the voice timing; no beat roles)
  text/captions.ass                  the burned captions
  text/publish.json                  title, alternative titles, description, hashtags ONLY (from the script's publish block)
  evidence/claims.json               research dossier facts + sources (what the video may claim)
  measurements/*.json                deterministic results (technical QA, visual audit, mix report, subtitle gate)
  manifest.json                      sha256 of every file + the exclusion policy
Excluded by construction (the builder refuses them as inputs): storyboards, scene SVGs, hook candidates, beat
structure, idea/selection files, run state/events, review templates and any earlier review. The author's
self-review inside qa_report.json is stripped.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import ffmpeg_bin, media_duration, read_json, sha256_file, write_json  # noqa: E402

FORBIDDEN = [r"storyboard", r"\.svg$", r"hooks", r"^state\.json$", r"^review(_template)?\.json$", r"ideas", r"selection",
             r"run\.json$", r"judgment\.json$"]
BOUNDARY = ("The reviewer reads only the files listed in this manifest (hash-verified). It receives no storyboard, "
            "scene source, hook candidates, beat structure, author notes, run state or prior review.")


def forbidden(path: str) -> bool:
    name = Path(path).name.lower()
    return any(re.search(p, name) for p in FORBIDDEN)


def ff(*args) -> None:
    subprocess.run([ffmpeg_bin(), "-y", "-v", "error", *[str(a) for a in args]], check=True)


def strip(path: Path, every: float, t0: float, t1: float, out: Path, cols: int, width: int = 270) -> int:
    n = max(1, int(round((t1 - t0) / every)) + 1)
    ff("-ss", f"{max(0.0, t0):.3f}", "-t", f"{t1 - t0 + every:.3f}", "-i", path, "-vf",
       f"fps=1/{every},scale={width}:-2,tile={min(cols, n)}x{(n + cols - 1) // cols}", "-frames:v", "1", "-q:v", "3", out)
    return n


def cmd_build(a) -> int:
    inputs = {"final": a.final, "timing": a.timing, "captions": a.captions, "publish": a.publish, "dossier": a.dossier,
              **{k: v for k, v in (m.split("=", 1) for m in a.measure or [])}}
    bad = {k: v for k, v in inputs.items() if v and k != "publish" and forbidden(v)}
    if bad:
        raise SystemExit(f"BOUNDARY: refusing authoring artifacts as review input: {bad}")
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    for d in ("media", "frames", "text", "evidence", "measurements"):
        (out / d).mkdir(parents=True)
    final = out / "media" / "final.mp4"
    shutil.copy2(a.final, final)
    dur = media_duration(final)
    ff("-i", final, "-frames:v", "1", out / "frames" / "first_frame.png")
    ff("-ss", f"{a.cover_at}", "-i", final, "-frames:v", "1", "-q:v", "2", out / "frames" / "cover.jpg")
    strip(final, 0.4, 0.0, min(3.2, dur - 0.05), out / "frames" / "hook_strip.jpg", 9, 240)
    ff("-i", final, "-vf", f"fps=16/{dur:.3f},scale=270:-2,tile=4x4", "-frames:v", "1", "-q:v", "3", out / "frames" / "contact.jpg")
    strip(final, 0.4, max(0.0, dur - 2.4), dur - 0.05, out / "frames" / "ending_strip.jpg", 6, 240)
    tm = read_json(a.timing)
    write_json(out / "text" / "transcript.json", {
        "language": tm.get("language"), "duration_s": round(dur, 3),
        "text": " ".join(s["text"] for s in tm["sentences"]),
        "sentences": [{"text": s["text"], "start": s["start"], "end": s["end"]} for s in tm["sentences"]],
        "words": [{"w": w["w"], "start": w["start"], "end": w["end"]} for w in tm["words"]]})
    shutil.copy2(a.captions, out / "text" / "captions.ass")
    pub = (read_json(a.publish).get("publish") or {}) if a.publish else {}
    titles = pub.get("title_options") or []
    write_json(out / "text" / "publish.json", {"title": titles[0] if titles else "", "title_alternatives": titles[1:],
                                                "description": pub.get("description", ""), "hashtags": pub.get("hashtags", []),
                                                "target_duration_s": [a.min_s, a.max_s]})
    if a.dossier and Path(a.dossier).exists():
        d = read_json(a.dossier)
        write_json(out / "evidence" / "claims.json", {"facts": [{k: f[k] for k in ("id", "claim", "source_ids", "risk") if k in f}
                                                                for f in d.get("facts", [])],
                                                      "sources": [{k: s[k] for k in ("id", "title", "url", "publisher") if k in s}
                                                                  for s in d.get("sources", [])]})
    for name, path in (m.split("=", 1) for m in a.measure or []):
        if not Path(path).exists():
            continue
        data = read_json(path)
        if name == "cta_report":  # what the viewer gets (type, words, timing) + gate results; never the author's reasons
            c = data.get("cta") or {}
            write_json(out / "text" / "cta.json", {"present": bool(c.get("needed")), **({k: c.get(k) or "" for k in
                       ("type", "placement", "modality", "spoken", "on_screen")} if c.get("needed") else {}),
                       "window_s": data.get("window")})
            data = {"checks": data.get("checks", []), "metrics": {k: v for k, v in (data.get("metrics") or {}).items()
                                                                  if k not in ("decision_reason", "recommendation")}}
        if name == "qa_report":  # keep only automatic technical checks; drop any author self-review
            data = {"checks": [c for c in data.get("checks", []) if not c["id"].startswith("V.")],
                    "metrics": data.get("metrics", {})}
        write_json(out / "measurements" / f"{name}.json", data)
    files = sorted(p for p in out.rglob("*") if p.is_file())
    leaks = [str(p.relative_to(out)) for p in files if forbidden(str(p))]
    if leaks:
        raise SystemExit(f"BOUNDARY: authoring files ended up in the packet: {leaks}")
    manifest = {"packet_version": 1, "built_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat(),
                "boundary": BOUNDARY, "excluded_patterns": FORBIDDEN,
                "files": {str(p.relative_to(out)): {"sha256": sha256_file(p), "bytes": p.stat().st_size} for p in files},
                "source_hashes": {k: sha256_file(v) for k, v in inputs.items() if v and Path(v).is_file()}}
    write_json(out / "manifest.json", manifest)
    print(json.dumps({"packet": str(out), "files": len(files), "final_sha256": manifest["files"]["media/final.mp4"]["sha256"][:16]}))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--final", required=True); b.add_argument("--timing", required=True)
    b.add_argument("--captions", required=True); b.add_argument("--publish", help="script.json — only its publish block is read")
    b.add_argument("--dossier"); b.add_argument("--measure", action="append", help="name=path of a deterministic report")
    b.add_argument("--out", required=True); b.add_argument("--cover-at", type=float, default=0.7)
    b.add_argument("--min-s", type=float, default=15); b.add_argument("--max-s", type=float, default=60)
    a = ap.parse_args()
    return cmd_build(a)


if __name__ == "__main__":
    sys.exit(main())


def write_packet(out: Path, files: dict, note: str) -> dict:
    """Generic packet for candidate reviews (hooks, script variants): `files` maps packet-relative names to a source
    Path or to a JSON-serialisable object. Same boundary rules and manifest format as the video packet."""
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name, src in files.items():
        if forbidden(name) or (isinstance(src, (str, Path)) and forbidden(str(src))):
            raise SystemExit(f"BOUNDARY: refusing '{name}' in a review packet")
        dst = out / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(src, (str, Path)):
            shutil.copy2(src, dst)
        else:
            dst.write_text(json.dumps(src, indent=1), encoding="utf-8")
    files_ = sorted(p for p in out.rglob("*") if p.is_file())
    manifest = {"packet_version": 1, "kind": note, "boundary": BOUNDARY, "excluded_patterns": FORBIDDEN,
                "built_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat(),
                "files": {str(p.relative_to(out)): {"sha256": sha256_file(p), "bytes": p.stat().st_size} for p in files_}}
    write_json(out / "manifest.json", manifest)
    return manifest
