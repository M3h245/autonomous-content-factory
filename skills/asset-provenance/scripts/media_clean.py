#!/usr/bin/env python3
"""media_clean — Phase 3.5 final-media metadata policy: clean publishable MP4/JPG files and audit them.

  media_clean.py clean --in final.mp4 --out clean.mp4          (or a .jpg)
  media_clean.py audit FILE [FILE ...]                         → JSON findings; exit 2 if any file is not clean

Policy: a publishable file carries only the standard metadata players need — MP4: major_brand, minor_version,
compatible_brands; per stream language, handler_name (VideoHandler/SoundHandler), vendor_id. JPEG: no EXIF, XMP,
ICC-free comments or text chunks. Nothing internal: no file-system paths, pipeline/run/checkpoint ids, provenance
notes, model or runtime names, encoder version strings, debug or test markers.

Cleaning never re-encodes: MP4 streams are copied (container metadata dropped, H.264 SEI user-data NAL units removed —
x264 writes its version and settings there); a JPEG keeps its compressed data byte for byte and only loses COM/APPn
segments. Picture and sound stay identical (MP4: stream MD5; JPEG: decoded pixels). Encoder strings inside the AAC
bitstream cannot be removed by copying — render_video encodes audio with +bitexact so new renders never contain them.

This is media hygiene, not a way around disclosure: AI-content labels are set per platform at upload time from
package/metadata.json (YouTube altered/synthetic, TikTok AI-generated, Instagram AI info), and the PACKAGE gate
blocks if those labels are missing. Internal provenance stays in provenance.json / reports, outside the media.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import ffmpeg_bin  # noqa: E402

ALLOWED_FORMAT_TAGS = {"major_brand", "minor_version", "compatible_brands"}
ALLOWED_STREAM_TAGS = {"language": None, "handler_name": {"VideoHandler", "SoundHandler"}, "vendor_id": {"[0][0][0][0]"}}
# printable strings (≥5 chars) that must never appear anywhere in a publishable file
DENY = [r"/home/", r"/mnt/", r"/tmp/", r"/Users/", r"[A-Za-z]:\\\\", r"cf-provenance", r"provenance", r"checkpoint",
        r"v\d+\.\d+\.\d+-alpha", r"kokoro", r"onnx", r"Claude", r"anthropic", r"x264 - core", r"Lav[fc]\d", r"pipeline",
        r"debug", r"run-video", r"hook_id", r"factory", r"storyboard", r"manifest"]
DENY_RE = re.compile("|".join(DENY), re.IGNORECASE)


def ffprobe() -> str:
    return str(Path(ffmpeg_bin()).with_name("ffprobe")) if Path(ffmpeg_bin()).with_name("ffprobe").exists() else "ffprobe"


def clean_mp4(src: Path, dst: Path) -> None:
    subprocess.run([ffmpeg_bin(), "-y", "-v", "error", "-i", str(src), "-map", "0", "-c", "copy", "-map_metadata", "-1",
                    "-map_chapters", "-1", "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
                    "-bsf:v", "filter_units=remove_types=6", "-movflags", "+faststart", str(dst)], check=True)


def clean_jpg(src: Path, dst: Path) -> None:
    """Lossless: walk the JPEG segments and drop COM and APP1-APP15 (EXIF, XMP, encoder notes) — except an APP2
    ICC_PROFILE, which is colour data. The compressed image data is copied byte for byte."""
    b = Path(src).read_bytes()
    if b[:2] != b"\xff\xd8":
        raise ValueError(f"{src} is not a JPEG")
    out, i = bytearray(b[:2]), 2
    while i < len(b):
        if b[i] != 0xFF:
            raise ValueError("corrupt JPEG segment")
        marker = b[i + 1]
        if marker == 0xDA:                                   # start of scan: the rest is image data
            out += b[i:]
            break
        seg_len = int.from_bytes(b[i + 2:i + 4], "big")
        seg = b[i:i + 2 + seg_len]
        icc = marker == 0xE2 and seg[4:16] == b"ICC_PROFILE\x00"
        if not (marker == 0xFE or (0xE1 <= marker <= 0xEF and not icc)):
            out += seg
        i += 2 + seg_len
    Path(dst).write_bytes(bytes(out))


def clean(src: Path, dst: Path) -> None:
    (clean_mp4 if src.suffix.lower() in (".mp4", ".m4v", ".mov") else clean_jpg)(Path(src), Path(dst))


def strings(path: Path, n: int = 5) -> list[str]:
    data = Path(path).read_bytes()
    return [m.group().decode("latin-1") for m in re.finditer(rb"[\x20-\x7e]{%d,}" % n, data)]


def audit(path: Path) -> dict:
    path = Path(path)
    findings = []
    if path.suffix.lower() in (".mp4", ".m4v", ".mov"):
        p = subprocess.run([ffprobe(), "-v", "error", "-show_entries", "format_tags:stream_tags:stream=codec_type", "-of", "json",
                            str(path)], capture_output=True, text=True)
        info = json.loads(p.stdout or "{}")
        for k, v in (info.get("format", {}).get("tags") or {}).items():
            if k not in ALLOWED_FORMAT_TAGS:
                findings.append({"where": "format tag", "key": k, "value": str(v)[:80]})
        for st in info.get("streams", []):
            for k, v in (st.get("tags") or {}).items():
                allowed = ALLOWED_STREAM_TAGS.get(k, "missing")
                if allowed == "missing" or (allowed is not None and v not in allowed):
                    findings.append({"where": f"{st.get('codec_type')} stream tag", "key": k, "value": str(v)[:80]})
    else:
        from PIL import Image
        im = Image.open(path)
        if im.getexif():
            findings.append({"where": "jpeg", "key": "EXIF", "value": f"{len(im.getexif())} tags"})
        for k in im.info:
            if k not in ("jfif", "jfif_version", "jfif_unit", "jfif_density", "dpi", "progressive", "progression",
                         "adobe", "adobe_transform"):
                findings.append({"where": "jpeg info", "key": k, "value": str(im.info[k])[:80]})
    hits = sorted({m.group() for s in strings(path) for m in DENY_RE.finditer(s)})
    for h in hits:
        findings.append({"where": "embedded text", "key": "denylisted string", "value": h})
    return {"file": path.name, "clean": not findings, "findings": findings}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("clean"); c.add_argument("--in", dest="src", required=True); c.add_argument("--out", required=True)
    a_ = sub.add_parser("audit"); a_.add_argument("files", nargs="+")
    a = ap.parse_args()
    if a.cmd == "clean":
        clean(Path(a.src), Path(a.out))
        print(json.dumps(audit(Path(a.out))))
        return 0
    res = [audit(Path(f)) for f in a.files]
    print(json.dumps(res, indent=1))
    return 0 if all(r["clean"] for r in res) else 2


if __name__ == "__main__":
    raise SystemExit(main())
