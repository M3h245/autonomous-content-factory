"""Offline tests for yt_sync.py fileDetails handling (no network, no OAuth files are read).

Run:  python tools/youtube_sync/test_yt_sync.py
The fake API below returns canned responses shaped like the YouTube Data API v3 documentation; it proves only how
yt_sync handles such responses. Whether Google returns fileDetails for this channel is known only after a real pull.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yt_sync as Y  # noqa: E402


def item(vid, fd=None, avail="available"):
    v = {"id": vid, "snippet": {"title": "T " + vid, "publishedAt": "2026-10-14T12:00:00Z"},
         "contentDetails": {"duration": "PT31S"}, "status": {"privacyStatus": "public"},
         "statistics": {"viewCount": "10", "likeCount": "1", "commentCount": "0"}}
    if avail is not None:
        v["processingDetails"] = {"processingStatus": "succeeded", "fileDetailsAvailability": avail}
    if fd is not None:
        v["fileDetails"] = fd
    return v


class FakeApi:
    def __init__(self, items, refuse_file_parts=False):
        self.items, self.refuse, self.calls, self.parts = items, refuse_file_parts, 0, []

    def get(self, base, params):
        self.calls += 1
        if base.endswith("channels"):
            return {"items": [{"id": "UC_TEST", "snippet": {"title": "Test"}, "statistics": {},
                               "contentDetails": {"relatedPlaylists": {"uploads": "UU_TEST"}}}]}
        if base.endswith("playlistItems"):
            return {"items": [{"contentDetails": {"videoId": v["id"]}} for v in self.items]}
        if base.endswith("videos"):
            self.parts.append(params["part"])
            wanted = set(params["id"].split(","))
            if "fileDetails" in params["part"]:
                if self.refuse:
                    raise RuntimeError("HTTP 403 videos: The request is not properly authorized to access fileDetails")
                return {"items": [v for v in self.items if v["id"] in wanted]}
            strip = lambda v: {k: x for k, x in v.items() if k not in ("fileDetails", "processingDetails")}  # noqa: E731
            return {"items": [strip(v) for v in self.items if v["id"] in wanted]}
        raise AssertionError(base)

    def report(self, **p):
        return []


class FileDetailsOf(unittest.TestCase):
    def test_available(self):
        fd = Y.file_details_of(item("a", {"fileName": "final.mp4", "fileSize": "11617208"}))
        self.assertEqual(fd, {"status": "available", "file_name": "final.mp4", "file_size": 11617208,
                              "availability": "available"})

    def test_part_not_returned(self):
        fd = Y.file_details_of(item("a", avail=None))
        self.assertEqual(fd["status"], "unavailable")
        self.assertNotIn("file_size", fd)

    def test_not_yet_available(self):
        fd = Y.file_details_of(item("a", {"fileName": "final.mp4", "fileSize": "1"}, avail="inProgress"))
        self.assertEqual(fd["status"], "unavailable")
        self.assertIn("inProgress", fd["reason"])
        self.assertNotIn("file_size", fd)

    def test_available_but_empty(self):
        self.assertEqual(Y.file_details_of(item("a", {}))["status"], "unavailable")

    def test_non_integer_size_is_not_used(self):
        fd = Y.file_details_of(item("a", {"fileName": "final.mp4", "fileSize": "12MB"}))
        self.assertEqual(fd["status"], "unavailable")
        self.assertNotIn("file_size", fd)


class Pull(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="yt_sync_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def pull(self, api):
        orig = Y.Api
        Y.Api = lambda: api
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = Y.cmd_pull(argparse.Namespace(since="2026-10-01", out=str(self.tmp)))
        finally:
            Y.Api = orig
        self.assertEqual(rc, 0)
        return json.loads(buf.getvalue()), json.loads((self.tmp / "latest.json").read_text(encoding="utf-8"))

    def test_with_file_details(self):
        api = FakeApi([item("a", {"fileName": "final.mp4", "fileSize": "100"}), item("b", avail="processing")])
        out, snap = self.pull(api)
        self.assertIn("fileDetails", api.parts[0]); self.assertIn("processingDetails", api.parts[0])
        fds = {v["video_id"]: v["file_details"] for v in snap["videos"]}
        self.assertEqual(fds["a"]["file_size"], 100)
        self.assertEqual(fds["b"]["status"], "unavailable")
        self.assertEqual(snap["capabilities"]["file_details"]["available_for"], 1)
        self.assertIsNone(snap["capabilities"]["file_details"]["error"])
        self.assertEqual(out["file_details"], {"available_for": 1, "videos": 2, "error": None})
        with open(next(self.tmp.glob("*/videos.csv")), encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual({r["video_id"]: r["file_size"] for r in rows}, {"a": "100", "b": ""})

    def test_without_file_details(self):
        api = FakeApi([item("a", {"fileName": "final.mp4", "fileSize": "100"})], refuse_file_parts=True)
        out, snap = self.pull(api)
        self.assertEqual(len(api.parts), 2)                     # refused, then retried without the parts
        self.assertNotIn("fileDetails", api.parts[1])
        fd = snap["videos"][0]["file_details"]
        self.assertEqual(fd["status"], "unavailable"); self.assertIn("HTTP 403", fd["reason"])
        self.assertNotIn("file_size", fd)
        self.assertEqual(snap["capabilities"]["file_details"]["available_for"], 0)
        self.assertIn("HTTP 403", out["file_details"]["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
