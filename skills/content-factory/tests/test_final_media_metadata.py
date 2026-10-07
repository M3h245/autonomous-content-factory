"""v3.0.1 final-media metadata policy: publishable media carry only what playback needs — no factory, debug,
provenance, run or AI-label / AI-disclosure metadata. Platform disclosure happens at upload (metadata.json,
PKG.DISCLOSURE), never inside the file.

The inspection here is independent of media_clean's own audit: its own MP4 box walker, JPEG segment walker, a full
ffprobe dump and a byte scan with its own pattern list.

    python3 -m unittest content-factory.tests.test_final_media_metadata      (from skills/; ~1 min)
"""
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / "asset-provenance" / "scripts"))
import media_clean as MC  # noqa: E402

PY = sys.executable
FACT = ROOT / "content-factory" / "scripts" / "factory.py"
KNUCKLES = REPO / "fixtures" / "phase4_package_run" / "2026-10-07-why-your-knuckles-crack"

# what a publishable MP4 may contain: the ftyp brands, the boxes playback needs, empty padding
ALLOWED_BOXES = {"ftyp", "moov", "mvhd", "trak", "tkhd", "edts", "elst", "mdia", "mdhd", "hdlr", "minf", "vmhd", "smhd",
                 "dinf", "dref", "url ", "stbl", "stsd", "avc1", "avcC", "btrt", "pasp", "colr", "mp4a", "esds", "stts",
                 "stss", "ctts", "stsc", "stsz", "stco", "co64", "sgpd", "sbgp", "free", "mdat"}
ALLOWED_FORMAT_TAGS = {"major_brand", "minor_version", "compatible_brands"}
ALLOWED_STREAM_TAGS = {"language", "vendor_id"}
FORBIDDEN = re.compile(r"ai[- _]?generated|made with ai|synthetic|c2pa|contentauth|xmpmeta|xmptk|DigitalSourceType|"
                       r"trainedAlgorithmic|ai_info|text-to-speech|kokoro|onnx|claude|anthropic|provenance|run-video|"
                       r"checkpoint|factory|storyboard|/home/|/tmp/|x264 - core|Lavf|Lavc|VideoHandler|SoundHandler", re.I)
C2PA_UUID = bytes.fromhex("d8fec3d61b0e483c92975828877ec481")
XMP_UUID = bytes.fromhex("be7acfcb97a942e89c71999491e3afac")
XMP = (b'<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="factory"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
       b'<rdf:Description xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/" Iptc4xmpExt:DigitalSourceType='
       b'"http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"/></rdf:RDF></x:xmpmeta>')
C2PA = b'{"label": "c2pa.actions", "actions": [{"action": "c2pa.created", "digitalSourceType": "trainedAlgorithmicMedia"}]}'


# ----------------------------------------------------------------------------- independent inspection
def boxes(data: bytes, off: int = 0, end: int | None = None, path: str = ""):
    end = len(data) if end is None else end
    while off + 8 <= end:
        size, typ = struct.unpack(">I4s", data[off:off + 8])
        hdr = 8
        if size == 1:
            size, hdr = struct.unpack(">Q", data[off + 8:off + 16])[0], 16
        elif size == 0:
            size = end - off
        t = typ.decode("latin-1")
        yield path + "/" + t, t, data[off + hdr:off + size]
        child = {"moov": 0, "trak": 0, "mdia": 0, "minf": 0, "stbl": 0, "dinf": 0, "edts": 0, "udta": 0, "meta": 4,
                 "stsd": 8, "avc1": 78, "mp4a": 28}.get(t)
        if child is not None:
            yield from boxes(data, off + hdr + child, off + size, path + "/" + t)
        off += size


def inspect_mp4(path: Path) -> dict:
    data = path.read_bytes()
    bx = list(boxes(data))
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-show_chapters",
                                       "-show_programs", "-of", "json", str(path)], capture_output=True, text=True).stdout)
    times = {}
    for p, t, body in bx:
        if t in ("mvhd", "tkhd", "mdhd"):
            v = body[0]
            times[p] = (struct.unpack(">II", body[4:12]) if v == 0 else struct.unpack(">QQ", body[4:20]))
    return {"box_types": {t for _, t, _ in bx}, "hdlr_names": [body[24:] for p, t, body in bx if t == "hdlr"],
            "free_payload_nonzero": [p for p, t, body in bx if t in ("free", "skip") and any(body)],
            "times": times, "format_tags": set((probe.get("format", {}).get("tags") or {})),
            "stream_tags": [st.get("tags") or {} for st in probe.get("streams", [])],
            "chapters": probe.get("chapters", []), "programs": probe.get("programs", []),
            "forbidden_text": sorted({m.group() for s in re.findall(rb"[\x20-\x7e]{5,}", data)
                                      for m in FORBIDDEN.finditer(s.decode("latin-1"))})}


def jpeg_segments(path: Path) -> list[tuple[int, bytes]]:
    b, out, i = path.read_bytes(), [], 2
    while i + 4 <= len(b) and b[i] == 0xFF:
        m = b[i + 1]
        if m == 0xDA:
            out.append((m, b""))
            break
        n = int.from_bytes(b[i + 2:i + 4], "big")
        out.append((m, b[i + 4:i + 2 + n]))
        i += 2 + n
    return out


def jpeg_problems(path: Path) -> list[str]:
    probs = []
    for m, body in jpeg_segments(path):
        if m == 0xFE or (0xE0 <= m <= 0xEF and not (m == 0xE0 and body[:5] == b"JFIF\x00")
                         and not (m == 0xE2 and body[:12] == b"ICC_PROFILE\x00")):
            probs.append(f"segment {hex(m)} {body[:12]!r}")
    probs += [f"text {s}" for s in sorted({m.group() for s in re.findall(rb"[\x20-\x7e]{5,}", path.read_bytes())
                                           for m in FORBIDDEN.finditer(s.decode("latin-1"))})]
    return probs


def assert_playback_only(tc: unittest.TestCase, mp4: Path) -> dict:
    r = inspect_mp4(mp4)
    tc.assertLessEqual(r["box_types"], ALLOWED_BOXES, f"{mp4.name}: unexpected boxes {r['box_types'] - ALLOWED_BOXES}")
    tc.assertTrue(all(not n.strip(b"\x00") for n in r["hdlr_names"]), f"{mp4.name}: handler names {r['hdlr_names']}")
    tc.assertEqual(r["free_payload_nonzero"], [], mp4.name)
    tc.assertTrue(all(v == (0, 0) for v in r["times"].values()), f"{mp4.name}: times {r['times']}")
    tc.assertLessEqual(r["format_tags"], ALLOWED_FORMAT_TAGS, mp4.name)
    for t in r["stream_tags"]:
        tc.assertLessEqual(set(t), ALLOWED_STREAM_TAGS, f"{mp4.name}: stream tags {t}")
        tc.assertEqual(t.get("language", "und"), "und")
    tc.assertEqual((r["chapters"], r["programs"]), ([], []), mp4.name)
    tc.assertEqual(r["forbidden_text"], [], f"{mp4.name}: embedded text")
    return r


def stream_md5(f: Path, s: str) -> str:
    return subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-map", f"0:{s}", "-f", "md5", "-"],
                          capture_output=True, text=True).stdout


def mp4_box(typ: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), typ) + payload


def jpeg_seg(marker: int, payload: bytes) -> bytes:
    return bytes([0xFF, marker]) + (len(payload) + 2).to_bytes(2, "big") + payload


class DirtyInputs(unittest.TestCase):
    """Every kind of metadata the policy forbids, injected on purpose, is gone after cleaning — picture/sound intact."""
    @classmethod
    def setUpClass(cls):
        cls.d = Path(tempfile.mkdtemp(prefix="v301md_"))
        src = cls.d / "src.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=320x568:d=1:r=25", "-f", "lavfi",
                        "-i", "sine=f=300:d=1:sample_rate=48000", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                        "-flags:a", "+bitexact", "-shortest", "-movflags", "+use_metadata_tags",
                        "-metadata", "title=AI-generated explainer", "-metadata", "comment=Made with AI; provenance run-video v01",
                        "-metadata", "artist=Claude via the content factory", "-metadata", "ai_generated=true",
                        "-metadata", "creation_time=2026-10-07T12:00:00Z", "-metadata:s:v:0", "handler_name=Kokoro narration",
                        "-metadata:s:a:0", "handler_name=AI voice (text-to-speech)", "-metadata:s:a:0", "language=eng",
                        str(src)], check=True)
        # top-level XMP (IPTC DigitalSourceType) and C2PA manifest boxes, the way provenance tools embed them
        dirty = cls.d / "dirty.mp4"
        dirty.write_bytes(src.read_bytes() + mp4_box(b"uuid", XMP_UUID + XMP) + mp4_box(b"uuid", C2PA_UUID + C2PA))
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-frames:v", "1", "-q:v", "2", str(cls.d / "src.jpg")],
                       check=True)
        from PIL import Image
        im = Image.open(cls.d / "src.jpg")
        ex = Image.Exif()
        ex[0x010E] = "synthetic image, AI-generated by Claude"       # ImageDescription
        im.save(cls.d / "exif.jpg", exif=ex, quality=92)
        b = (cls.d / "exif.jpg").read_bytes()
        extra = (jpeg_seg(0xE1, b"http://ns.adobe.com/xap/1.0/\x00" + XMP) + jpeg_seg(0xEB, b"JP\x00\x00jumb" + C2PA)
                 + jpeg_seg(0xED, b"Photoshop 3.0\x008BIM DigitalSourceType trainedAlgorithmicMedia")
                 + jpeg_seg(0xE0, b"JFXX\x00\x10") + jpeg_seg(0xFE, b"AI generated, provenance run-video v01"))
        (cls.d / "dirty.jpg").write_bytes(b[:2] + extra + b[2:])
        MC.clean(dirty, cls.d / "clean.mp4")
        MC.clean(cls.d / "dirty.jpg", cls.d / "clean.jpg")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d, ignore_errors=True)

    def test_inputs_really_are_dirty(self):
        r = inspect_mp4(self.d / "dirty.mp4")
        for needle in ("AI-generated", "Made with AI", "trainedAlgorithmic", "c2pa", "xmpmeta", "provenance"):
            self.assertTrue(any(needle.lower() in t.lower() for t in r["forbidden_text"]), needle)
        self.assertIn("udta", r["box_types"])
        self.assertIn("uuid", r["box_types"])
        self.assertGreaterEqual(len(jpeg_problems(self.d / "dirty.jpg")), 6)
        self.assertFalse(MC.audit(self.d / "dirty.mp4")["clean"])
        self.assertFalse(MC.audit(self.d / "dirty.jpg")["clean"])

    def test_mp4_keeps_only_playback_metadata(self):
        assert_playback_only(self, self.d / "clean.mp4")
        self.assertTrue(MC.audit(self.d / "clean.mp4")["clean"], MC.audit(self.d / "clean.mp4"))   # and the factory agrees

    def test_mp4_picture_and_sound_unchanged(self):
        for s in ("v", "a"):
            self.assertEqual(stream_md5(self.d / "dirty.mp4", s), stream_md5(self.d / "clean.mp4", s), s)
        dec = subprocess.run(["ffmpeg", "-v", "error", "-i", str(self.d / "clean.mp4"), "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        self.assertEqual(dec.strip(), "")

    def test_jpeg_keeps_only_jfif_and_image_data(self):
        self.assertEqual(jpeg_problems(self.d / "clean.jpg"), [])
        self.assertTrue(MC.audit(self.d / "clean.jpg")["clean"], MC.audit(self.d / "clean.jpg"))
        from PIL import Image, ImageChops
        a, b = Image.open(self.d / "dirty.jpg").convert("RGB"), Image.open(self.d / "clean.jpg").convert("RGB")
        self.assertIsNone(ImageChops.difference(a, b).getbbox())


class PackagedDeliverables(unittest.TestCase):
    """The factory's own publishable files (PACKAGE on a finished fixture run) carry playback metadata only, while
    platform disclosure outside the media (metadata.json labels, the description line, PKG.DISCLOSURE) is unchanged."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="v301pkg_"))
        cls.rundir = cls.tmp / KNUCKLES.name
        shutil.copytree(KNUCKLES, cls.rundir)
        shutil.rmtree(cls.rundir / "package" / "v01", ignore_errors=True)
        cls.p = subprocess.run([PY, str(FACT), "package", "--run", str(cls.rundir)], capture_output=True, text=True)
        cls.pkg = cls.rundir / "package" / "v01"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_package_passed(self):
        self.assertEqual(self.p.returncode, 0, self.p.stdout[-1500:] + self.p.stderr[-1500:])
        res = json.loads((self.pkg / "result.json").read_text())
        self.assertEqual(res["status"], "passed")
        checks = {c["id"]: c["passed"] for c in res["gate"]["checks"]}
        self.assertTrue(checks["PKG.MEDIA_METADATA_CLEAN"])
        self.assertTrue(checks["PKG.DISCLOSURE"])              # compliance logic outside the media still enforced

    def test_final_mp4_keeps_only_playback_metadata(self):
        r = assert_playback_only(self, self.pkg / "final.mp4")
        self.assertIn("mdat", r["box_types"])

    def test_images_keep_only_jfif_and_image_data(self):
        for n in ("thumbnail.jpg", "cover.jpg", "thumbnail_crops.jpg", "contact_sheet.jpg"):
            if (self.pkg / n).exists():
                self.assertEqual(jpeg_problems(self.pkg / n), [], n)

    def test_disclosure_lives_outside_the_media(self):
        meta = json.loads((self.pkg / "metadata.json").read_text())
        labels = [meta["youtube"].get("altered_or_synthetic"), meta["tiktok"].get("ai_generated_label"),
                  meta["instagram"].get("ai_info")]
        self.assertTrue(all(x is not None for x in labels), labels)
        prov = json.loads((self.pkg / "provenance.json").read_text())
        self.assertIn(prov["disclosure"]["description_line"], meta["youtube"]["description"])
        self.assertIn("AI labels", (self.pkg / "PUBLISHING_PACKAGE.md").read_text())


if __name__ == "__main__":
    unittest.main()
