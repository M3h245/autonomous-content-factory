"""Tests for ingest_youtube.py: uploaded-file evidence, probable matches that are never written, idempotent re-runs.

Run:  python skills/content-analytics/tests/test_ingest_youtube.py
Everything happens in a temporary folder with a fresh database; no real database, run or output folder is touched.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
SKILLS = HERE.parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SKILLS / "content-database" / "scripts"))
import cfdb  # noqa: E402
import ingest_youtube as I  # noqa: E402

C2PA = bytes.fromhex(I.C2PA_UUID)


def box(t: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + t + payload


def make_mp4(media: bytes, c2pa: bytes | None = None, chunks: int = 3) -> bytes:
    """A minimal ISO-BMFF file: ftyp [uuid C2PA] moov(trak/mdia/minf/stbl/stco) free mdat, with absolute chunk offsets."""
    ftyp = box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2")
    pre = ftyp + (box(b"uuid", C2PA + c2pa) if c2pa is not None else b"")
    step = max(1, len(media) // chunks)

    def moov_for(base: int) -> bytes:
        stco = box(b"stco", b"\x00\x00\x00\x00" + struct.pack(">I", chunks)
                   + b"".join(struct.pack(">I", base + k * step) for k in range(chunks)))
        return box(b"moov", box(b"mvhd", b"\x00" * 20) + box(b"trak", box(b"mdia", box(b"minf", box(b"stbl", stco)))))

    moov_len = len(moov_for(0))
    base = len(pre) + moov_len + 8 + 8          # + free + mdat header
    return pre + moov_for(base) + box(b"free", b"") + box(b"mdat", media)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


RUN_A, RUN_B, RUN_C = "2026-10-14-alpha-run", "2026-10-14-bravo-run", "2026-10-16-charlie-run"
SNAP = {"source": "test", "captured_at": "2026-10-16T11:02:00Z", "startDate": "2026-10-09", "endDate": "2026-10-16",
        "note": "fixture", "columns": ["video", "views", "engagedViews", "averageViewPercentage", "likes", "comments", "shares"],
        "rows": [["YT_A", 1000, 600, 55.0, 10, 2, 1], ["YT_B", 500, 250, 41.0, 3, 0, 0], ["YT_C", 800, 400, 60.0, 5, 1, 0]]}


def yt_video(vid, title, published, duration="PT30S", fd=None, shape="sync", privacy="public", publish_at=None):
    if shape == "vidiq":
        return {"videoId": vid, "title": title, "publishedAt": published, "duration": duration, "videoType": "short"}
    v = {"video_id": vid, "title": title, "published_at": published, "duration": duration, "privacy": privacy,
         "publish_at": publish_at}
    if fd is not None:
        v["file_details"] = fd
    return v


def fd_ok(size, name="final.mp4"):
    return {"status": "available", "file_name": name, "file_size": size, "availability": "available"}


class Fixture:
    """runs/<run>/package/v01/final.mp4 (hashes in the DB), outputs/<n>/final.mp4 (the package plus a C2PA box)."""

    def __init__(self, root: Path):
        self.root = root
        self.runs = root / "runs"; self.outputs = root / "outputs"; self.db = root / "factory.db"
        self.pkg, self.out = {}, {}
        con = cfdb.connect(self.db)
        for i, (run, title) in enumerate(((RUN_A, "Alpha title"), (RUN_B, "Bravo title"), (RUN_C, "Charlie title"))):
            pkg = make_mp4(bytes([65 + i]) * (3000 + 7 * i))
            p = self.runs / run / "package" / "v01" / "final.mp4"; p.parent.mkdir(parents=True); p.write_bytes(pkg)
            self.pkg[run] = pkg
            con.execute("INSERT INTO runs(run_id, topic, created_at, status) VALUES(?,?,?,?)",
                        (run, title, run[:10] + "T10:00:00Z", "done"))
            con.execute("INSERT INTO videos(video_id, run_id, title, duration_s, final_sha256) VALUES(?,?,?,?,?)",
                        ("v01", run, title, 30.0, sha(pkg)))
        con.commit(); con.close()

    def add_output(self, folder: str, run: str, c2pa: bytes | None = b"manifest", name: str = "final.mp4") -> Path:
        data = self.pkg[run] if c2pa is None else self._with_c2pa(run, c2pa)
        p = self.outputs / folder / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
        return p

    def _with_c2pa(self, run: str, c2pa: bytes) -> bytes:
        i = list(self.pkg).index(run)
        return make_mp4(bytes([65 + i]) * (3000 + 7 * i), c2pa=c2pa)

    def write(self, name: str, doc) -> Path:
        p = self.root / name; p.write_text(json.dumps(doc), encoding="utf-8"); return p

    def ingest(self, videos: dict, confirm: dict | None = None, apply: bool = False, runs_dir: bool = True,
               outputs: bool = True, publications_only: bool = False) -> tuple[dict, dict]:
        cmd = [sys.executable, str(SCRIPTS / "ingest_youtube.py"), "--db", str(self.db),
               "--videos", str(self.write("videos.json", videos)), "--out", str(self.root / "report.json")]
        cmd += ["--publications-only"] if publications_only else ["--metrics", str(self.write("metrics.json", SNAP))]
        if outputs:
            cmd += ["--outputs", str(self.outputs)]
        if runs_dir:
            cmd += ["--runs-dir", str(self.runs)]
        if confirm is not None:
            cmd += ["--confirm", str(self.write("confirm.json", confirm))]
        if apply:
            cmd.append("--apply")
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if p.returncode != 0:
            raise AssertionError(p.stderr or p.stdout)
        return json.loads(p.stdout), json.loads((self.root / "report.json").read_text(encoding="utf-8"))

    def raw(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPTS / "ingest_youtube.py"), *args],
                              capture_output=True, text=True, encoding="utf-8")

    def rows(self, table: str) -> list[tuple]:
        con = sqlite3.connect(self.db)
        try:
            return sorted(con.execute(f"SELECT * FROM {table}").fetchall(), key=repr)
        finally:
            con.close()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ingest_yt_"))
        self.fx = Fixture(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def size(self, folder):
        return (self.fx.outputs / folder / "final.mp4").stat().st_size


class MediaFingerprint(unittest.TestCase):
    def test_c2pa_box_does_not_change_the_fingerprint(self):
        plain, signed = make_mp4(b"x" * 999), make_mp4(b"x" * 999, c2pa=b"m" * 5000)
        self.assertNotEqual(sha(plain), sha(signed))
        self.assertEqual(I.media_fingerprint(plain), I.media_fingerprint(signed))

    def test_other_media_changes_the_fingerprint(self):
        self.assertNotEqual(I.media_fingerprint(make_mp4(b"x" * 999)), I.media_fingerprint(make_mp4(b"y" * 999)))

    def test_unknown_uuid_box_changes_the_fingerprint(self):
        a = make_mp4(b"x" * 999)
        other = bytearray(make_mp4(b"x" * 999, c2pa=b"m"))
        u = other.index(C2PA)
        other[u:u + 16] = b"\x11" * 16          # same layout, but not the C2PA uuid
        self.assertNotEqual(I.media_fingerprint(a), I.media_fingerprint(bytes(other)))

    def test_garbage_is_rejected(self):
        with self.assertRaises(ValueError):
            I.media_fingerprint(b"\x00\x00\x00\x10ftypisom\x00\x00")


class FileDetailsInput(Base):
    def test_snapshot_without_file_details_writes_nothing_and_says_why(self):
        self.fx.add_output("01_alpha", RUN_A)
        vids = {"videos": [yt_video("YT_A", "Alpha title", "2026-10-14T12:00:00Z")]}   # yt_sync shape, no file_details
        summary, rep = self.fx.ingest(vids, apply=True)
        self.assertEqual(rep["totals"]["mapped"], 0)
        self.assertEqual(rep["totals"]["probable_not_written"], 1)
        self.assertIn("no video in --videos has fileDetails", rep["file_details"]["note"])
        self.assertIn("fileDetails unavailable", rep["unmapped"][0]["reason"])
        self.assertEqual(self.fx.rows("publications"), []); self.assertEqual(self.fx.rows("metrics"), [])
        self.assertIsNone(summary["backup"])

    def test_vidiq_shape_is_accepted_and_has_no_file_evidence(self):
        vids = {"videos": [yt_video("YT_A", "Alpha title", "2026-10-14T12:00:00Z", shape="vidiq")]}
        _, rep = self.fx.ingest(vids)
        self.assertEqual(rep["file_details"]["available"], 0)
        self.assertEqual(rep["probable_not_written"][0]["run_id"], RUN_A)

    def test_unavailable_file_details_from_the_api(self):
        self.fx.add_output("01_alpha", RUN_A)
        fd = {"status": "unavailable", "reason": "processingDetails.fileDetailsAvailability='processing'"}
        _, rep = self.fx.ingest({"videos": [yt_video("YT_A", "Alpha title", "2026-10-14T12:00:00Z", fd=fd)]}, apply=True)
        self.assertEqual(rep["totals"]["mapped"], 0)
        self.assertIn("processing", rep["unmapped"][0]["reason"])
        self.assertEqual(self.fx.rows("publications"), [])


class Linking(Base):
    def test_definitive_link_through_c2pa_output_and_run_package(self):
        self.fx.add_output("01_alpha", RUN_A); self.fx.add_output("02_bravo", RUN_B)
        vids = {"videos": [yt_video("YT_A", "A different public title", "2026-10-14T12:00:00Z", fd=fd_ok(self.size("01_alpha")))]}
        _, rep = self.fx.ingest(vids, apply=True)
        self.assertEqual(rep["totals"]["by_evidence"], {"owner_confirmed": 0, "uploaded_file": 1})
        m = rep["mapped"][0]
        self.assertEqual((m["run_id"], m["video_id"], m["evidence"]), (RUN_A, "v01", "uploaded_file"))
        self.assertTrue(m["uploaded_file"]["via"].startswith("media_fingerprint"))
        pubs = self.fx.rows("publications")
        self.assertEqual([(p[0], p[1], p[2], p[4]) for p in pubs], [(RUN_A, "v01", "youtube", "YT_A")])
        self.assertEqual(len(self.fx.rows("metrics")), 1)

    def test_definitive_link_by_exact_sha256_needs_no_runs_dir(self):
        self.fx.add_output("01_alpha", RUN_A, c2pa=None)          # byte-identical to the package
        vids = {"videos": [yt_video("YT_A", "Alpha title", "2026-10-14T12:00:00Z", fd=fd_ok(self.size("01_alpha")))]}
        _, rep = self.fx.ingest(vids, runs_dir=False)
        self.assertEqual(rep["mapped"][0]["uploaded_file"]["via"], "sha256==videos.final_sha256")

    def test_c2pa_output_without_runs_dir_has_no_chain(self):
        self.fx.add_output("01_alpha", RUN_A)
        vids = {"videos": [yt_video("YT_A", "Alpha title", "2026-10-14T12:00:00Z", fd=fd_ok(self.size("01_alpha")))]}
        _, rep = self.fx.ingest(vids, runs_dir=False)
        self.assertEqual(rep["totals"]["mapped"], 0)
        self.assertIn("no hash chain", rep["unmapped"][0]["reason"])
        self.assertEqual(rep["probable_not_written"][0]["run_id"], RUN_A)

    def test_probable_link_is_reported_but_never_written(self):
        vids = {"videos": [yt_video("YT_B", "Bravo title!", "2026-10-15T12:00:00Z", fd=fd_ok(123456))]}
        _, rep = self.fx.ingest(vids, apply=True)
        self.assertEqual(rep["totals"]["mapped"], 0)
        self.assertEqual(rep["probable_not_written"][0]["basis"], "title_normalized+duration+date")
        self.assertEqual(rep["publications"], []); self.assertEqual(self.fx.rows("publications"), [])

    def test_unresolved_video(self):
        vids = {"videos": [yt_video("YT_Z", "Nothing like any factory title", "2026-10-15T12:00:00Z")]}
        _, rep = self.fx.ingest(vids)
        self.assertEqual((rep["totals"]["mapped"], rep["totals"]["probable_not_written"], rep["totals"]["unmapped"]), (0, 0, 1))
        self.assertEqual(rep["unmapped"][0]["probable"]["reason"], "no factory video with this title")

    def test_duplicate_file_sizes_leave_the_video_unresolved(self):
        a = self.fx.add_output("01_alpha", RUN_A)
        dup = self.fx.outputs / "99_copy" / "final.mp4"; dup.parent.mkdir(); dup.write_bytes(b"\x00" * a.stat().st_size)
        vids = {"videos": [yt_video("YT_A", "Alpha title", "2026-10-14T12:00:00Z", fd=fd_ok(a.stat().st_size))]}
        _, rep = self.fx.ingest(vids, apply=True)
        self.assertEqual(rep["totals"]["mapped"], 0)
        self.assertIn("2 output files have", rep["unmapped"][0]["reason"])
        self.assertEqual(self.fx.rows("publications"), [])

    def test_file_size_alone_is_not_enough(self):
        a = self.fx.add_output("01_alpha", RUN_A)
        for fd, why in ((fd_ok(a.stat().st_size, name=""), "no fileName"),
                        (fd_ok(a.stat().st_size, name="leidenfrost_v2.mp4"), "differs from the size-matched output")):
            _, rep = self.fx.ingest({"videos": [yt_video("YT_A", "Alpha title", "2026-10-14T12:00:00Z", fd=fd)]})
            self.assertEqual(rep["totals"]["mapped"], 0, why)
            self.assertIn(why, rep["unmapped"][0]["reason"])

    def test_windows_style_uploaded_name_is_compared_by_basename(self):
        a = self.fx.add_output("01_alpha", RUN_A)
        fd = fd_ok(a.stat().st_size, name=r"C:\Users\x\outputs\01_alpha\FINAL.mp4")
        _, rep = self.fx.ingest({"videos": [yt_video("YT_A", "Alpha title", "2026-10-14T12:00:00Z", fd=fd)]})
        self.assertEqual(rep["totals"]["mapped"], 1)

    def test_size_match_to_a_file_that_belongs_to_no_run(self):
        p = self.fx.outputs / "07_other" / "final.mp4"; p.parent.mkdir(parents=True); p.write_bytes(make_mp4(b"q" * 4000))
        vids = {"videos": [yt_video("YT_A", "Alpha title", "2026-10-14T12:00:00Z", fd=fd_ok(p.stat().st_size))]}
        _, rep = self.fx.ingest(vids)
        self.assertEqual(rep["totals"]["mapped"], 0)
        self.assertIn("matches no run package", rep["unmapped"][0]["reason"])

    def test_two_youtube_ids_claiming_one_file_are_both_unresolved(self):
        a = self.fx.add_output("01_alpha", RUN_A)
        vids = {"videos": [yt_video("YT_A", "x", "2026-10-14T12:00:00Z", fd=fd_ok(a.stat().st_size)),
                           yt_video("YT_A2", "y", "2026-10-14T13:00:00Z", fd=fd_ok(a.stat().st_size))]}
        _, rep = self.fx.ingest(vids, apply=True)
        self.assertEqual(rep["totals"]["mapped"], 0)
        self.assertTrue(all("claimed by several YouTube ids" in u["reason"] for u in rep["unmapped"]))
        self.assertEqual(self.fx.rows("publications"), [])

    def test_file_link_contradicting_a_clean_title_match_is_unresolved(self):
        b = self.fx.add_output("02_bravo", RUN_B)
        vids = {"videos": [yt_video("YT_A", "Alpha title", "2026-10-14T12:00:00Z", fd=fd_ok(b.stat().st_size))]}
        _, rep = self.fx.ingest(vids)
        self.assertEqual(rep["totals"]["mapped"], 0)
        self.assertIn("contradicts the probable title match", rep["unmapped"][0]["reason"])


class OwnerConfirmed(Base):
    def test_owner_confirmation_is_its_own_evidence(self):
        vids = {"videos": [yt_video("YT_C", "Whatever", "2026-10-16T12:00:00Z")]}
        _, rep = self.fx.ingest(vids, confirm={"YT_C": {"run_id": RUN_C, "video_id": "v01"}}, apply=True)
        self.assertEqual(rep["mapped"][0]["evidence"], "owner_confirmed")
        self.assertIn("fileDetails unavailable", rep["mapped"][0]["uploaded_file_check"])
        self.assertEqual(rep["totals"]["by_evidence"], {"owner_confirmed": 1, "uploaded_file": 0})
        self.assertEqual(len(self.fx.rows("publications")), 1)

    def test_owner_confirmation_agreeing_with_the_file_keeps_both_proofs(self):
        a = self.fx.add_output("01_alpha", RUN_A)
        vids = {"videos": [yt_video("YT_A", "Alpha title", "2026-10-14T12:00:00Z", fd=fd_ok(a.stat().st_size))]}
        _, rep = self.fx.ingest(vids, confirm={"YT_A": {"run_id": RUN_A, "video_id": "v01"}})
        self.assertEqual(rep["mapped"][0]["evidence"], "owner_confirmed")
        self.assertEqual(rep["mapped"][0]["uploaded_file"]["run_id"], RUN_A)

    def test_owner_confirmation_contradicting_the_file_is_unresolved(self):
        a = self.fx.add_output("01_alpha", RUN_A)
        vids = {"videos": [yt_video("YT_A", "Alpha title", "2026-10-14T12:00:00Z", fd=fd_ok(a.stat().st_size))]}
        _, rep = self.fx.ingest(vids, confirm={"YT_A": {"run_id": RUN_B, "video_id": "v01"}}, apply=True)
        self.assertEqual(rep["totals"]["mapped"], 0)
        self.assertIn("contradicts the uploaded-file link", rep["unmapped"][0]["reason"])
        self.assertEqual(self.fx.rows("publications"), [])


class Idempotent(Base):
    def test_rerun_inserts_nothing_and_changes_nothing(self):
        self.fx.add_output("01_alpha", RUN_A); self.fx.add_output("03_charlie", RUN_C)
        vids = {"videos": [
            yt_video("YT_A", "Alpha title", "2026-10-14T12:00:00Z", fd=fd_ok(self.size("01_alpha"))),     # definitive
            yt_video("YT_B", "Bravo title", "2026-10-15T12:00:00Z"),                                       # probable
            yt_video("YT_C", "Charlie", "2026-10-16T12:00:00Z"),                                           # owner
            yt_video("YT_Z", "Unknown", "2026-10-16T12:00:00Z")]}                                          # unresolved
        confirm = {"YT_C": {"run_id": RUN_C, "video_id": "v01"}}
        s1, r1 = self.fx.ingest(vids, confirm=confirm, apply=True)
        self.assertEqual(r1["totals"]["publications"], {"insert": 2, "unchanged": 0, "conflict": 0})
        self.assertEqual(r1["totals"]["metrics"], {"insert": 2, "unchanged": 0, "conflict": 0})
        self.assertIsNotNone(s1["backup"]); self.assertTrue(Path(s1["backup"]).is_file())
        db_after_first = (self.fx.rows("publications"), self.fx.rows("metrics"))
        db_hash = sha(self.fx.db.read_bytes())
        s2, r2 = self.fx.ingest(vids, confirm=confirm, apply=True)
        self.assertEqual(r2["totals"]["publications"], {"insert": 0, "unchanged": 2, "conflict": 0})
        self.assertEqual(r2["totals"]["metrics"], {"insert": 0, "unchanged": 2, "conflict": 0})
        self.assertIsNone(s2["backup"])
        self.assertEqual((self.fx.rows("publications"), self.fx.rows("metrics")), db_after_first)
        self.assertEqual(sha(self.fx.db.read_bytes()), db_hash)
        self.assertEqual({p[4] for p in self.fx.rows("publications")}, {"YT_A", "YT_C"})   # never YT_B (probable)

    def test_dry_run_never_writes(self):
        self.fx.add_output("01_alpha", RUN_A)
        h = sha(self.fx.db.read_bytes())
        vids = {"videos": [yt_video("YT_A", "Alpha title", "2026-10-14T12:00:00Z", fd=fd_ok(self.size("01_alpha")))]}
        s, rep = self.fx.ingest(vids)
        self.assertEqual((s["mode"], rep["totals"]["publications"]["insert"]), ("dry-run", 1))
        self.assertEqual(sha(self.fx.db.read_bytes()), h)
        self.assertEqual(list(self.tmp.glob("factory.db.bak-*")), [])


class PublicationsOnly(Base):
    """--publications-only: same linking, publications planned/written, metrics never touched."""

    def videos(self):
        self.fx.add_output("01_alpha", RUN_A); self.fx.add_output("03_charlie", RUN_C)
        return {"videos": [
            yt_video("YT_A", "Alpha title", "2026-10-14T12:00:00Z", fd=fd_ok(self.size("01_alpha"))),     # definitive
            yt_video("YT_C", "Charlie title", "2026-10-16T12:00:00Z", fd=fd_ok(self.size("03_charlie"))), # definitive
            yt_video("YT_B", "Bravo title", "2026-10-15T12:00:00Z"),                                       # probable
            yt_video("YT_Z", "Unknown", "2026-10-16T12:00:00Z")]}                                          # unresolved

    def seed_metric(self):
        """A pre-existing metrics row that must survive untouched."""
        con = sqlite3.connect(self.fx.db)
        with con:
            con.execute("INSERT INTO metrics VALUES(?,?,?,?,?,?,?,?,?)",
                        (RUN_A, "v01", "youtube", "2026-10-01T00:00:00Z", 5.0, 0.5, 0.1, 0.42, '{"seed": true}'))
        con.close()

    def test_dry_run_plans_exactly_the_expected_publications_and_no_metrics(self):
        h = sha(self.fx.db.read_bytes())
        s, rep = self.fx.ingest(self.videos(), publications_only=True)
        self.assertEqual((s["mode"], s["publications_only"]), ("dry-run", True))
        self.assertEqual(sorted((p["action"], p["row"]["platform_video_id"], p["row"]["run_id"]) for p in rep["publications"]),
                         [("insert", "YT_A", RUN_A), ("insert", "YT_C", RUN_C)])
        self.assertEqual(rep["metrics"], []); self.assertIsNone(rep["metrics_window"]); self.assertEqual(rep["no_metrics"], [])
        self.assertEqual(rep["totals"]["metrics"], "skipped (--publications-only)")
        self.assertEqual(rep["totals"]["probable_not_written"], 1)
        self.assertEqual(sha(self.fx.db.read_bytes()), h)
        self.assertEqual(list(self.tmp.glob("factory.db.bak-*")), [])

    def test_apply_inserts_publications_and_leaves_metrics_untouched(self):
        self.seed_metric()
        before = self.fx.rows("metrics")
        s, rep = self.fx.ingest(self.videos(), publications_only=True, apply=True)
        pubs = self.fx.rows("publications")
        self.assertEqual([(p[0], p[1], p[2], p[3], p[4], p[5]) for p in pubs], [
            (RUN_A, "v01", "youtube", "https://www.youtube.com/shorts/YT_A", "YT_A", "2026-10-14T12:00:00Z"),
            (RUN_C, "v01", "youtube", "https://www.youtube.com/shorts/YT_C", "YT_C", "2026-10-16T12:00:00Z")])
        self.assertEqual(self.fx.rows("metrics"), before)                 # zero inserts or modifications
        self.assertTrue(Path(s["backup"]).is_file())
        self.assertNotIn("YT_B", {p[4] for p in pubs})                     # probable never written

    def test_rerun_is_idempotent(self):
        vids = self.videos()
        self.fx.ingest(vids, publications_only=True, apply=True)
        h = sha(self.fx.db.read_bytes())
        s, rep = self.fx.ingest(vids, publications_only=True, apply=True)
        self.assertEqual(rep["totals"]["publications"], {"insert": 0, "unchanged": 2, "conflict": 0})
        self.assertIsNone(s["backup"])
        self.assertEqual(sha(self.fx.db.read_bytes()), h)
        self.assertEqual(self.fx.rows("metrics"), [])

    def test_existing_conflicts_are_reported_not_overwritten(self):
        con = sqlite3.connect(self.fx.db)
        with con:   # same factory video, different YouTube id; and YT_C already mapped to another factory video
            con.execute("INSERT INTO publications VALUES(?,?,?,?,?,?)",
                        (RUN_A, "v01", "youtube", "https://www.youtube.com/shorts/OLD", "OLD", "2026-10-01T00:00:00Z"))
            con.execute("INSERT INTO publications VALUES(?,?,?,?,?,?)",
                        (RUN_B, "v01", "youtube", "https://www.youtube.com/shorts/YT_C", "YT_C", "2026-10-02T00:00:00Z"))
        con.close()
        before = self.fx.rows("publications")
        s, rep = self.fx.ingest(self.videos(), publications_only=True, apply=True)
        acts = {p["row"]["platform_video_id"]: p for p in rep["publications"]}
        self.assertEqual(acts["YT_A"]["action"], "conflict")
        self.assertEqual(acts["YT_A"]["diff"]["platform_video_id"], {"db": "OLD", "new": "YT_A"})
        self.assertEqual(acts["YT_C"]["action"], "conflict")
        self.assertEqual(acts["YT_C"]["diff"]["platform_video_id"]["db_already_maps_to"], [RUN_B, "v01"])
        self.assertEqual(rep["totals"]["publications"], {"insert": 0, "unchanged": 0, "conflict": 2})
        self.assertIsNone(s["backup"])
        self.assertEqual(self.fx.rows("publications"), before)

    def test_default_mode_is_unchanged(self):
        vids = self.videos()
        s, rep = self.fx.ingest(vids, apply=False)
        self.assertFalse(s["publications_only"])
        self.assertEqual(rep["totals"]["publications"], {"insert": 2, "unchanged": 0, "conflict": 0})
        self.assertEqual(rep["totals"]["metrics"], {"insert": 2, "unchanged": 0, "conflict": 0})   # SNAP has YT_A and YT_C
        self.assertEqual(rep["metrics_window"]["captured_at"], SNAP["captured_at"])
        self.assertEqual(self.fx.rows("publications"), []); self.assertEqual(self.fx.rows("metrics"), [])


class LegacyChannel(Base):
    """The four legacy channel ids are never matched, even with a matching file or an owner confirmation."""
    LEG = ("KHutHAMv2_A", "cFwkqgRnV9I", "QqI7w_BZaWE", "aRJAjjHVx9g")

    def legacy(self, vid, fd=None, privacy="public", publish_at=None, published="2023-08-21T11:23:35Z"):
        v = yt_video(vid, "How to make pancake at home?", published, duration="PT3M38S",
                     fd=fd or {"status": "unavailable", "reason": "processingDetails.fileDetailsAvailability=inProgress"})
        v.update(privacy=privacy, publish_at=publish_at)
        return v

    def test_list_is_fixed(self):
        self.assertEqual(sorted(I.L.LEGACY_CHANNEL_VIDEOS), sorted(self.LEG))

    def test_legacy_videos_are_reported_apart_and_never_written(self):
        a = self.fx.add_output("01_alpha", RUN_A)
        vids = {"videos": [yt_video("YT_A", "Alpha title", "2026-10-14T12:00:00Z", fd=fd_ok(a.stat().st_size)),
                           self.legacy("KHutHAMv2_A"),
                           self.legacy("aRJAjjHVx9g", fd=fd_ok(a.stat().st_size))]}   # even a perfect file match
        confirm = {"cFwkqgRnV9I": {"run_id": RUN_B, "video_id": "v01"}, "aRJAjjHVx9g": {"run_id": RUN_C, "video_id": "v01"}}
        vids["videos"].append(self.legacy("cFwkqgRnV9I"))
        _, rep = self.fx.ingest(vids, confirm=confirm, apply=True, publications_only=True)
        t = rep["totals"]
        self.assertEqual((t["youtube_videos"], t["mapped"], t["unmapped"], t["legacy_channel"]), (4, 1, 0, 3))
        self.assertEqual({m["youtube_id"] for m in rep["mapped"]}, {"YT_A"})
        leg = {x["youtube_id"]: x for x in rep["legacy_channel"]}
        self.assertEqual(set(leg), {"KHutHAMv2_A", "aRJAjjHVx9g", "cFwkqgRnV9I"})
        self.assertTrue(all(x["scope"] == "legacy_channel" and "never linked" in x["not_matched_because"] for x in leg.values()))
        self.assertIn("fileDetails unavailable", leg["KHutHAMv2_A"]["match_limitation"])
        self.assertIn("never used", leg["aRJAjjHVx9g"]["match_limitation"])
        self.assertEqual((leg["cFwkqgRnV9I"]["owner_confirmation_ignored"], leg["KHutHAMv2_A"]["owner_confirmation_ignored"]),
                         (True, False))
        self.assertEqual(leg["KHutHAMv2_A"]["public_at"], "2023-08-21T11:23:35Z")
        self.assertNotIn("run_id", leg["KHutHAMv2_A"])
        self.assertEqual([p[4] for p in self.fx.rows("publications")], ["YT_A"])

    def test_public_time_is_not_guessed(self):
        vids = {"videos": [self.legacy("QqI7w_BZaWE", privacy="private", publish_at="2026-12-01T10:00:00Z"),
                           self.legacy("KHutHAMv2_A", privacy=None)]}
        _, rep = self.fx.ingest(vids, publications_only=True)
        leg = {x["youtube_id"]: x for x in rep["legacy_channel"]}
        self.assertIsNone(leg["QqI7w_BZaWE"]["public_at"]); self.assertIn("unverifiable", leg["QqI7w_BZaWE"]["public_at_basis"])
        self.assertIsNone(leg["KHutHAMv2_A"]["public_at"]); self.assertIn("privacy status", leg["KHutHAMv2_A"]["public_at_basis"])

    def test_legacy_metric_rows_are_labelled_not_inserted(self):
        snap = dict(SNAP, rows=SNAP["rows"] + [["KHutHAMv2_A", 23, 5, 30.0, 0, 0, 0]])
        vids = {"videos": [self.legacy("KHutHAMv2_A")]}
        cmd = [sys.executable, str(SCRIPTS / "ingest_youtube.py"), "--db", str(self.fx.db), "--videos",
               str(self.fx.write("v.json", vids)), "--metrics", str(self.fx.write("m.json", snap)),
               "--out", str(self.tmp / "r.json"), "--apply"]
        self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
        rep = json.loads((self.tmp / "r.json").read_text(encoding="utf-8"))
        miss = next(x for x in rep["no_metrics"] if x["youtube_id"] == "KHutHAMv2_A")
        self.assertEqual(miss["scope"], "legacy_channel")
        self.assertEqual(self.fx.rows("metrics"), [])

    def test_existing_legacy_publication_stops_everything(self):
        con = sqlite3.connect(self.fx.db)
        with con:
            con.execute("INSERT INTO publications VALUES(?,?,?,?,?,?)",
                        (RUN_B, "v01", "youtube", "https://www.youtube.com/shorts/QqI7w_BZaWE", "QqI7w_BZaWE", "x"))
        con.close()
        h = sha(self.fx.db.read_bytes())
        p = self.fx.raw("--publications-only", "--db", str(self.fx.db), "--videos",
                        str(self.fx.write("v.json", {"videos": [self.legacy("QqI7w_BZaWE")]})), "--apply")
        self.assertEqual(p.returncode, 2)
        self.assertEqual(json.loads(p.stdout)["error"], "LEGACY_LINKED_IN_DB")
        self.assertEqual(sha(self.fx.db.read_bytes()), h)
        self.assertEqual(list(self.tmp.glob("factory.db.bak-*")), [])


class HeldNotPublic(Base):
    """Only a verified public time is written: private/scheduled/unknown-privacy videos are held, never stored."""

    def vids(self):
        a = self.fx.add_output("01_alpha", RUN_A); b = self.fx.add_output("02_bravo", RUN_B)
        c = self.fx.add_output("03_charlie", RUN_C)
        return {"videos": [
            yt_video("YT_A", "Alpha title", "2026-10-14T16:00:14Z", fd=fd_ok(a.stat().st_size)),               # public
            yt_video("YT_B", "Bravo title", "2026-10-16T14:18:24Z", fd=fd_ok(b.stat().st_size),
                     privacy="private", publish_at="2026-10-17T16:00:00Z"),                                     # scheduled
            yt_video("YT_C", "Charlie title", "2026-10-16T14:23:23Z", fd=fd_ok(c.stat().st_size), privacy=None)]}

    def test_scheduled_and_unknown_privacy_are_held(self):
        _, rep = self.fx.ingest(self.vids(), publications_only=True, apply=True)
        t = rep["totals"]
        self.assertEqual((t["mapped"], t["held_not_public"], t["publications"]["insert"]), (1, 2, 1))
        held = {h["youtube_id"]: h for h in rep["held_not_public"]}
        self.assertIn("scheduled publishAt 2026-10-17T16:00:00Z", held["YT_B"]["reason"])
        self.assertIn("privacy status not in the input", held["YT_C"]["reason"])
        self.assertEqual(held["YT_B"]["run_id"], RUN_B)                      # link evidence kept in the report
        self.assertEqual([(p[4], p[5]) for p in self.fx.rows("publications")], [("YT_A", "2026-10-14T16:00:14Z")])
        self.assertEqual(rep["mapped"][0]["published_at_basis"], "snippet.publishedAt of a public video")

    def test_upload_time_is_never_stored_and_metrics_are_held_too(self):
        snap = dict(SNAP, rows=SNAP["rows"])                                   # SNAP has rows for YT_A, YT_B, YT_C
        cmd = [sys.executable, str(SCRIPTS / "ingest_youtube.py"), "--db", str(self.fx.db), "--videos",
               str(self.fx.write("v.json", self.vids())), "--metrics", str(self.fx.write("m.json", snap)),
               "--outputs", str(self.fx.outputs), "--runs-dir", str(self.fx.runs), "--out", str(self.tmp / "r.json"), "--apply"]
        self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
        rep = json.loads((self.tmp / "r.json").read_text(encoding="utf-8"))
        self.assertEqual({r[0] for r in self.fx.rows("metrics")}, {RUN_A})
        self.assertNotIn("2026-10-16T14:18:24Z", {p[5] for p in self.fx.rows("publications")})
        reasons = {x["youtube_id"]: x["reason"] for x in rep["no_metrics"]}
        self.assertIn("held", reasons["YT_B"]); self.assertIn("held", reasons["YT_C"])

    def test_after_it_goes_public_the_real_time_is_written(self):
        v = self.vids()
        self.fx.ingest(v, publications_only=True, apply=True)
        v["videos"][1].update(privacy="public", publish_at=None, published_at="2026-10-17T16:00:03Z")
        _, rep = self.fx.ingest(v, publications_only=True, apply=True)
        self.assertEqual(rep["totals"]["publications"], {"insert": 1, "unchanged": 1, "conflict": 0})
        self.assertIn(("YT_B", "2026-10-17T16:00:03Z"), [(p[4], p[5]) for p in self.fx.rows("publications")])

    def test_existing_row_of_a_held_video_is_reported_and_untouched(self):
        con = sqlite3.connect(self.fx.db)
        with con:
            con.execute("INSERT INTO publications VALUES(?,?,?,?,?,?)",
                        (RUN_B, "v01", "youtube", "https://www.youtube.com/shorts/YT_B", "YT_B", "2026-10-16T14:18:24Z"))
        con.close()
        before = self.fx.rows("publications")
        _, rep = self.fx.ingest(self.vids(), publications_only=True, apply=True)
        h = next(x for x in rep["held_not_public"] if x["youtube_id"] == "YT_B")
        self.assertEqual(h["existing_db_row"], {"published_at": "2026-10-16T14:18:24Z", "touched": False})
        self.assertIn(before[0], self.fx.rows("publications"))


class FailsSafely(Base):
    def check(self, args, code):
        h = sha(self.fx.db.read_bytes())
        p = self.fx.raw(*args)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertEqual(json.loads(p.stdout)["error"], code)
        self.assertEqual(sha(self.fx.db.read_bytes()), h)
        self.assertEqual(list(self.tmp.glob("factory.db.bak-*")), [])

    def test_bad_inputs(self):
        vids = str(self.fx.write("videos.json", {"videos": [yt_video("YT_A", "Alpha title", "2026-10-14T12:00:00Z")]}))
        mets = str(self.fx.write("metrics.json", SNAP))
        bad = self.tmp / "bad.json"; bad.write_text("{not json", encoding="utf-8")
        db = str(self.fx.db)
        cases = [
            (["--db", db, "--videos", vids, "--apply"], "METRICS_REQUIRED"),
            (["--db", db, "--videos", vids, "--metrics", mets, "--publications-only", "--apply"], "METRICS_WITH_PUBLICATIONS_ONLY"),
            (["--db", str(self.tmp / "nope.db"), "--videos", vids, "--publications-only", "--apply"], "DB_NOT_FOUND"),
            (["--db", db, "--videos", str(self.tmp / "missing.json"), "--publications-only", "--apply"], "INPUT_NOT_FOUND"),
            (["--db", db, "--videos", str(bad), "--publications-only", "--apply"], "INPUT_INVALID"),
            (["--db", db, "--videos", str(self.fx.write("v2.json", {"items": []})), "--publications-only", "--apply"],
             "INPUT_INVALID"),
            (["--db", db, "--videos", vids, "--metrics", str(bad), "--apply"], "INPUT_INVALID"),
            (["--db", db, "--videos", vids, "--metrics", str(self.fx.write("m2.json", {"rows": []})), "--apply"],
             "INPUT_INVALID"),
            (["--db", db, "--videos", vids, "--publications-only", "--confirm", str(bad), "--apply"], "INPUT_INVALID"),
        ]
        for args, code in cases:
            with self.subTest(code=code, args=args[2:]):
                self.check(args, code)

    def test_non_database_file(self):
        junk = self.tmp / "junk.db"; junk.write_bytes(b"this is not sqlite" * 100)
        vids = str(self.fx.write("videos.json", {"videos": []}))
        p = self.fx.raw("--db", str(junk), "--videos", vids, "--publications-only", "--apply")
        self.assertEqual((p.returncode, json.loads(p.stdout)["error"]), (2, "DB_INVALID"))
        self.assertEqual(junk.read_bytes(), b"this is not sqlite" * 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
