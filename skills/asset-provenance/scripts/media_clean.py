#!/usr/bin/env python3
"""media_clean — Phase 3.5 final-media metadata policy: clean publishable MP4/JPG files and audit them.

  media_clean.py clean --in final.mp4 --out clean.mp4          (or a .jpg)
  media_clean.py audit FILE [FILE ...]                         → JSON findings; exit 2 if any file is not clean

Policy (v3.0.1): a publishable file carries only what playback and handling technically need — MP4: the ftyp brands
(major_brand, minor_version, compatible_brands) and the mandatory per-track fields (mdhd language "und", the
sample-entry vendor field 0), with all times zeroed; no udta/meta/ilst/uuid/XMP box, empty track-handler names.
JPEG: SOI, the JFIF APP0 header, the coding segments (and an ICC profile if one exists — colour data); no EXIF, XMP,
IPTC, C2PA/JUMBF, comments or other APPn segments. Nothing internal (file-system paths, pipeline/run/checkpoint ids,
provenance notes, model or runtime names, encoder version strings, debug or test markers) and no embedded AI-label /
AI-disclosure metadata of any kind (XMP/IPTC DigitalSourceType, C2PA manifests, "AI-generated"/synthetic tags).

Cleaning never re-encodes: MP4 streams are copied (container metadata dropped, H.264 SEI user-data NAL units removed —
x264 writes its version and settings there), then descriptive boxes are neutralised in place at the same size (so no
sample offset moves); a JPEG keeps its compressed data byte for byte and only loses COM/APPn segments. Picture and
sound stay identical (MP4: stream MD5; JPEG: decoded pixels). Encoder strings inside the AAC
bitstream cannot be removed by copying — render_video encodes audio with +bitexact so new renders never contain them.

Disclosure is not done through the media file. The factory never embeds AI labels in media; it removes any it finds.
The owner sets each platform's AI-content label by hand at upload, from package/metadata.json and
PUBLISHING_PACKAGE.md (YouTube altered/synthetic, TikTok AI-generated, Instagram AI info). The PACKAGE gate
(PKG.DISCLOSURE) still blocks when those labels are missing there. Internal provenance stays in provenance.json and the
reports, outside the media.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import ffmpeg_bin  # noqa: E402

ALLOWED_FORMAT_TAGS = {"major_brand", "minor_version", "compatible_brands"}
ALLOWED_STREAM_TAGS = {"language": None, "vendor_id": {"[0][0][0][0]"}, "handler_name": {""}}   # v3.0.1: handler names empty
# printable strings (≥5 chars) that must never appear anywhere in a publishable file. Phase 5: a Windows path must look
# like one (drive, a name, a separator, a name; single or JSON-escaped backslashes) — the old 4-byte drive-letter
# pattern matched random bytes in the compressed video (~1 file in 7), and a deterministic encode can never clear that.
DENY = [r"/home/", r"/mnt/", r"/tmp/", r"/Users/", r"[A-Za-z]:\\{1,2}[\w .-]{3,}\\{1,2}[\w.-]{2,}", r"cf-provenance", r"provenance", r"checkpoint",
        r"v\d+\.\d+\.\d+-alpha", r"kokoro", r"onnx", r"Claude", r"anthropic", r"x264 - core", r"Lav[fc]\d", r"pipeline",
        r"debug", r"run-video", r"hook_id", r"factory", r"storyboard", r"manifest"]
DENY_RE = re.compile("|".join(DENY), re.IGNORECASE)     # also screens the authored public copy (PKG.PUBLIC_COPY_CLEAN)
# v3.0.1, media files only: embedded AI-label / AI-disclosure metadata (XMP, IPTC DigitalSourceType, C2PA, plain-text
# labels). Not applied to the public copy, where words like "synthetic" can be legitimate and disclosure is governed
# by PKG.DISCLOSURE.
AI_LABEL = [r"xmpmeta", r"x:xmptk", r"DigitalSourceType", r"trainedAlgorithmicMedia", r"compositeSynthetic",
            r"algorithmicMedia", r"c2pa\.[a-z]", r"contentauth", r"AI[- _]?generated", r"generated[- _]by[- _]AI",
            r"altered[- _]or[- _]synthetic", r"synthetic", r"ai_info", r"made with ai", r"text-to-speech"]
MEDIA_DENY_RE = re.compile("|".join(DENY + AI_LABEL), re.IGNORECASE)


def ffprobe() -> str:
    return str(Path(ffmpeg_bin()).with_name("ffprobe")) if Path(ffmpeg_bin()).with_name("ffprobe").exists() else "ffprobe"


def clean_mp4(src: Path, dst: Path) -> None:
    subprocess.run([ffmpeg_bin(), "-y", "-v", "error", "-i", str(src), "-map", "0", "-c", "copy", "-map_metadata", "-1",
                    "-map_chapters", "-1", "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
                    "-bsf:v", "filter_units=remove_types=6", "-movflags", "+faststart", str(dst)], check=True)
    strip_mp4_descriptive(Path(dst))


# boxes that only ever carry descriptive metadata (never needed to decode or play) and boxes whose payload is padding
META_BOXES = {b"udta", b"meta", b"uuid", b"XMP_", b"ilst"}
PAD_BOXES = {b"free", b"skip"}
CONTAINER_BOXES = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"dinf", b"edts", b"moof", b"traf", b"mvex"}


def mp4_boxes(data, off: int, end: int):
    """(offset, header size, box size, type) of the boxes in data[off:end]."""
    while off + 8 <= end:
        size, typ = struct.unpack(">I4s", data[off:off + 8])
        hdr = 8
        if size == 1:
            size, hdr = struct.unpack(">Q", data[off + 8:off + 16])[0], 16
        elif size == 0:
            size = end - off
        if size < hdr or off + size > end:
            raise ValueError(f"corrupt MP4 box {typ!r} at {off}")
        yield off, hdr, size, typ
        off += size


def strip_mp4_descriptive(path: Path) -> None:
    """v3.0.1: keep only what playback needs, in place and size-preserving (no sample offset moves): every
    udta/meta/ilst/uuid/XMP_ box becomes an all-zero `free` box, padding boxes are zeroed, and each media handler's
    name ("VideoHandler") is blanked — its 4-byte handler type, which players use, stays."""
    b = bytearray(Path(path).read_bytes())

    def walk(off: int, end: int, in_mdia: bool) -> None:
        for o, hdr, size, typ in list(mp4_boxes(b, off, end)):
            if typ in META_BOXES:
                b[o + 4:o + 8] = b"free"
                b[o + hdr:o + size] = bytes(size - hdr)
            elif typ in PAD_BOXES:
                b[o + hdr:o + size] = bytes(size - hdr)
            elif typ in CONTAINER_BOXES:
                walk(o + hdr, o + size, typ == b"mdia")
            elif typ == b"hdlr" and in_mdia:       # FullBox(4) pre_defined(4) handler_type(4) reserved(12) name
                b[o + hdr + 24:o + size] = bytes(max(0, size - hdr - 24))
    walk(0, len(b), False)
    Path(path).write_bytes(bytes(b))


def clean_jpg(src: Path, dst: Path) -> None:
    """Lossless: walk the JPEG segments and drop COM, APP1-APP15 (EXIF, XMP, IPTC, C2PA/JUMBF, encoder notes) and any
    APP0 that is not the JFIF header — except an APP2 ICC_PROFILE, which is colour data. The compressed image data is
    copied byte for byte."""
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
        jfif = marker == 0xE0 and seg[4:9] == b"JFIF\x00"
        if not (marker == 0xFE or (0xE0 <= marker <= 0xEF and not icc and not jfif)):
            out += seg
        i += 2 + seg_len
    Path(dst).write_bytes(bytes(out))


def clean(src: Path, dst: Path) -> None:
    (clean_mp4 if src.suffix.lower() in (".mp4", ".m4v", ".mov") else clean_jpg)(Path(src), Path(dst))


def blob_strings(data: bytes, n: int = 5) -> list[str]:
    return [m.group().decode("latin-1") for m in re.finditer(rb"[\x20-\x7e]{%d,}" % n, data)]


def strings(path: Path, n: int = 5) -> list[str]:
    """Every printable run in the whole file (kept for callers; audit() no longer scans compressed samples)."""
    return blob_strings(Path(path).read_bytes(), n)


# v3.0.2 — where the embedded-text scan looks. It used to scan every byte of the file, so 5 random printable bytes inside
# compressed picture data (e.g. "OnNX5" in an x264 keyframe) failed PKG.MEDIA_METADATA_CLEAN, and a deterministic encode
# could not clear it. Text a file can actually carry lives in: the MP4 box structure outside `mdat` (udta/meta/ilst/
# uuid/hdlr/stsd...), any bytes after the last box, the H.264 non-picture NAL units (SEI user data — where x264 writes
# its version — SPS/PPS/AUD), the AAC bitstream (encoder strings in fill elements: checked against encoder signatures
# only, since short words can occur by chance in compressed audio), the JPEG header segments before and between scans,
# and anything after the JPEG end-of-image marker. Whatever cannot be parsed is scanned whole, as before.
ENCODER_RE = re.compile(r"x264 - core|Lav[fc]\d+\.\d+|libfdk|FAAC|Nero AAC")    # case-sensitive signatures
VCL_NAL_TYPES = {1, 2, 3, 4, 5, 20, 21}             # H.264 coded-slice NAL units: compressed picture data


def _ffmpeg_out(cmd: list) -> bytes | None:
    p = subprocess.run([ffmpeg_bin(), "-v", "error"] + [str(c) for c in cmd], capture_output=True)
    return p.stdout if p.returncode == 0 else None


def mp4_regions(path: Path, data: bytes) -> list[tuple]:
    regions, meta, mdat, off = [], bytearray(), [], 0
    while off + 8 <= len(data):
        size, typ = struct.unpack(">I4s", data[off:off + 8])
        hdr = 8
        if size == 1 and off + 16 <= len(data):
            size, hdr = struct.unpack(">Q", data[off + 8:off + 16])[0], 16
        elif size == 0:
            size = len(data) - off
        if size < hdr or off + size > len(data):
            break                                  # not a box: the rest is scanned whole below
        if typ == b"mdat":
            meta += data[off:off + hdr]
            mdat.append(data[off + hdr:off + size])
        else:
            meta += data[off:off + size]
        off += size
    regions.append(("mp4 boxes", bytes(meta), MEDIA_DENY_RE))
    if off < len(data):
        regions.append(("bytes outside the mp4 boxes", data[off:], MEDIA_DENY_RE))
    if not mdat:
        return regions
    p = subprocess.run([ffprobe(), "-v", "error", "-show_entries", "stream=index,codec_type,codec_name", "-of", "json", str(path)],
                       capture_output=True, text=True)
    streams = json.loads(p.stdout or "{}").get("streams", []) if p.returncode == 0 else []
    parsed = bool(streams)
    for st in streams:
        i, kind, codec = st.get("index"), st.get("codec_type"), st.get("codec_name")
        if kind == "video" and codec == "h264":
            es = _ffmpeg_out(["-i", path, "-map", f"0:{i}", "-c", "copy", "-bsf:v", "h264_mp4toannexb", "-f", "h264", "-"])
            if es is None:
                parsed = False
                continue
            nals = [n for n in re.split(rb"\x00\x00\x01", es) if n and (n[0] & 0x1F) not in VCL_NAL_TYPES]
            regions.append((f"h264 stream {i}: SEI/SPS/PPS units", b"\n".join(nals), MEDIA_DENY_RE))
        elif kind == "audio":
            es = _ffmpeg_out(["-i", path, "-map", f"0:{i}", "-c", "copy", "-f", "data", "-"])
            if es is None:
                parsed = False
                continue
            regions.append((f"{codec} stream {i}: encoder signatures", es, ENCODER_RE))
        else:
            parsed = False                         # a stream this audit cannot split: scan its samples whole
    if not parsed:
        regions.append(("mdat (not parsed)", b"\n".join(mdat), MEDIA_DENY_RE))
    return regions


def jpeg_regions(data: bytes) -> list[tuple]:
    hdr, i, n = bytearray(data[:2]), 2, len(data)
    while i + 1 < n:
        if data[i] != 0xFF:
            return [("jpeg (unparsed)", data, MEDIA_DENY_RE)]
        m = data[i + 1]
        if m == 0xFF:                                # fill byte
            i += 1
            continue
        if m == 0xD9:                                # end of image: anything after it is not picture data
            return [("jpeg segments", bytes(hdr), MEDIA_DENY_RE)] + (
                [("bytes after the jpeg end marker", data[i + 2:], MEDIA_DENY_RE)] if data[i + 2:] else [])
        if 0xD0 <= m <= 0xD7 or m == 0x01:
            i += 2
            continue
        seg_len = int.from_bytes(data[i + 2:i + 4], "big")
        hdr += data[i:i + 2 + seg_len]
        i += 2 + seg_len
        if m == 0xDA:                                # entropy-coded data until the next real marker
            j = i
            while True:
                j = data.find(b"\xff", j)
                if j < 0 or j + 1 >= n:
                    return [("jpeg segments", bytes(hdr), MEDIA_DENY_RE)]
                k = data[j + 1]
                if k == 0x00 or 0xD0 <= k <= 0xD7 or k == 0xFF:
                    j += 1 if k == 0xFF else 2
                    continue
                break
            i = j
    return [("jpeg segments", bytes(hdr), MEDIA_DENY_RE)]


def text_regions(path: Path) -> list[tuple]:
    """(where, bytes, pattern) for every part of a publishable file that can carry text."""
    data = Path(path).read_bytes()
    if path.suffix.lower() in (".mp4", ".m4v", ".mov"):
        return mp4_regions(path, data)
    if data[:2] == b"\xff\xd8":
        return jpeg_regions(data)
    return [("whole file", data, MEDIA_DENY_RE)]


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
        data = path.read_bytes()

        def walk(off: int, end: int, in_mdia: bool) -> None:
            for o, hdr, size, typ in mp4_boxes(data, off, end):
                if typ in META_BOXES:
                    findings.append({"where": "mp4 box", "key": typ.decode("latin-1"), "value": f"{size} bytes at {o}"})
                elif typ in PAD_BOXES and any(data[o + hdr:o + size]):
                    findings.append({"where": "mp4 box", "key": typ.decode("latin-1"), "value": "padding box carries data"})
                elif typ in CONTAINER_BOXES:
                    walk(o + hdr, o + size, typ == b"mdia")
                elif typ == b"hdlr" and in_mdia and data[o + hdr + 24:o + size].strip(b"\x00"):
                    findings.append({"where": "mp4 box", "key": "hdlr name", "value": data[o + hdr + 24:o + size][:40].decode("latin-1")})
        try:
            walk(0, len(data), False)
        except ValueError:      # bytes that form no box (e.g. trailing data) are a decode question (PKG.FINAL_DECODES),
            pass                # not metadata; the byte scan below still covers every byte of the file
    else:
        from PIL import Image
        b = path.read_bytes()
        i = 2
        while i + 4 <= len(b) and b[i] == 0xFF and b[i + 1] != 0xDA:      # v3.0.1: segment-level check
            m, n = b[i + 1], int.from_bytes(b[i + 2:i + 4], "big")
            seg = b[i:i + 2 + n]
            if m == 0xFE or (0xE0 <= m <= 0xEF and not (m == 0xE0 and seg[4:9] == b"JFIF\x00")
                             and not (m == 0xE2 and seg[4:16] == b"ICC_PROFILE\x00")):
                findings.append({"where": "jpeg segment", "key": "COM" if m == 0xFE else f"APP{m - 0xE0}",
                                 "value": seg[4:20].decode("latin-1", "replace")})
            i += 2 + n
        im = Image.open(path)
        if im.getexif():
            findings.append({"where": "jpeg", "key": "EXIF", "value": f"{len(im.getexif())} tags"})
        for k in im.info:
            if k not in ("jfif", "jfif_version", "jfif_unit", "jfif_density", "dpi", "progressive", "progression",
                         "adobe", "adobe_transform"):
                findings.append({"where": "jpeg info", "key": k, "value": str(im.info[k])[:80]})
    for where, blob, rx in text_regions(path):     # v3.0.2: metadata/text regions only, never compressed samples
        for h in sorted({m.group() for s in blob_strings(blob) for m in rx.finditer(s)}):
            findings.append({"where": f"embedded text ({where})", "key": "denylisted string", "value": h})
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
