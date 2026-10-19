#!/usr/bin/env python3
"""ingest_youtube — link published YouTube Shorts to factory videos and load a metrics snapshot (dry run by default).

  ingest_youtube.py --db factory.db --videos snapshot.json|channel_videos.json --metrics yt_metrics_by_video.json
                    [--outputs <dir> ...] [--runs-dir <runs>] [--confirm confirmations.json] [--out report.json] [--apply]
  ingest_youtube.py --publications-only --db factory.db --videos snapshot.json [--outputs <dir> ...] [...] [--apply]

--publications-only links videos exactly as above but plans and writes publications only: --metrics is not read (and
is refused if given), no metrics row is planned, inserted, updated or deleted.

A YouTube video is written to `publications` (and its metrics loaded) only with one of two kinds of evidence:
  * owner_confirmed: the owner named the pair in --confirm ({"<youtube id>": {"run_id": ..., "video_id": ...}});
  * uploaded_file: the uploaded file is proven to be one factory output file, and that file is hash-linked to one run:
      - the video's fileDetails (from yt_sync.py pull) carry fileName and fileSize,
      - exactly one .mp4 under --outputs has that size (two files of the same size -> unresolved),
      - its file name equals the uploaded fileName (case-insensitive; any other name -> unresolved),
      - and its SHA-256 equals videos.final_sha256 of exactly one factory video, or its media fingerprint
        (ftyp + moov with chunk offsets made relative to mdat + mdat; C2PA uuid and free boxes ignored) equals that of
        <runs-dir>/<run>/package/<video>/final.mp4 whose SHA-256 equals videos.final_sha256 (outputs carry a C2PA box).
    fileSize alone is never enough. Any disagreement (owner confirmation, another YouTube id claiming the same file or
    factory video, or a probable title match pointing elsewhere) leaves the video unresolved.
A title + duration + date match is only "probable": it is listed in the report and never written. Videos without
fileDetails are reported as unresolved with the reason; nothing is guessed.

Legacy channel videos (legacy_channel.py: a fixed list of YouTube ids, owner decision) are never matched: no file,
owner-confirmation or title check is made for them, they are listed only under `legacy_channel` in the report with the
reason and the matching limitation, and any confirmation naming them is ignored. If the database already has a
publication for one of them the script stops with LEGACY_LINKED_IN_DB and writes nothing.

A publication is planned only when the input snapshot shows the video `public` with no `publishAt`; only then is its
`snippet.publishedAt` (as returned by the API at pull time) the time it became public. A linked video that is private,
unlisted, scheduled or of unknown privacy (e.g. a vidIQ export) is listed under `held_not_public` with its link
evidence and is not written (no publication, no metrics); re-run after it is public. Existing rows are never touched.

Writes are insert-only and idempotent: a row that already exists unchanged is skipped, a row that exists with
different values is reported as a conflict and never overwritten. --apply copies the database to
<db>.bak-<timestamp> first and writes in one transaction. Without --apply nothing is written to the database.
Metrics rows carry the snapshot's captured_at, so loading the same snapshot twice inserts nothing new.
perf stays NULL (the ANALYTICS stage computes it) and no weights are written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import struct
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import legacy_channel as L  # noqa: E402

DURATION_TOL_S = 1.5
URL = "https://www.youtube.com/shorts/{}"
C2PA_UUID = "d8fec3d61b0e483c92975828877ec481"
_CONTAINERS = {b"moov", b"trak", b"mdia", b"minf", b"stbl"}
LINKED = ("owner_confirmed", "uploaded_file")


def norm_title(t: str) -> str:
    t = (t or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = re.sub(r"#\w+", " ", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return re.sub(r"[\s.!?]+$", "", t)


def iso_seconds(d: str) -> float | None:
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", d or "")
    if not m or not any(m.groups()):
        return None
    h, mi, s = m.groups()
    return int(h or 0) * 3600 + int(mi or 0) * 60 + float(s or 0)


def load_json(p) -> dict:
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def factory_videos(con) -> list[dict]:
    q = ("SELECT v.run_id, v.video_id, v.title, v.duration_s, r.created_at, v.final_sha256 "
         "FROM videos v LEFT JOIN runs r ON r.run_id = v.run_id")
    return [dict(zip(["run_id", "video_id", "title", "duration_s", "run_created_at", "final_sha256"], r))
            for r in con.execute(q)]


def run_date(fv: dict) -> str:
    m = re.match(r"(\d{4}-\d{2}-\d{2})", fv["run_id"] or "")
    return (fv.get("run_created_at") or "")[:10] or (m.group(1) if m else "")


def normalize_videos(doc: dict) -> list[dict]:
    """Accept a vidIQ channel_videos.json (videoId, publishedAt, ...) or a yt_sync snapshot (video_id, published_at,
    file_details). file_details is taken only from the input; a missing one is reported as unavailable."""
    out = []
    for v in doc["videos"]:
        fd = v.get("file_details")
        if not isinstance(fd, dict):
            fd = {"status": "unavailable", "reason": "input has no file_details (run yt_sync.py pull for fileDetails)"}
        out.append({"videoId": v.get("videoId") or v.get("video_id"), "title": v.get("title") or "",
                    "publishedAt": v.get("publishedAt") or v.get("published_at"), "duration": v.get("duration", ""),
                    "videoType": v.get("videoType"), "file_details": fd,
                    "privacy": v.get("privacy"), "publish_at": v.get("publish_at")})
    return out


def legacy_entry(v: dict, confirmed: bool) -> dict:
    """Report-only record of a legacy channel video. No file, run or title check is attempted."""
    fd = v["file_details"]
    at, basis = L.public_time(v.get("privacy"), v.get("publishedAt"), v.get("publish_at"))
    limitation = ("fileDetails unavailable (" + str(fd.get("reason")) + "); no factory output file or run belongs to it"
                  if fd.get("status") != "available" else
                  "fileDetails available but never used: legacy videos are not matched to factory files")
    return {"youtube_id": v["videoId"], "youtube_title": v["title"], "scope": L.SCOPE, "privacy": v.get("privacy"),
            "snippet_published_at": v.get("publishedAt"), "public_at": at, "public_at_basis": basis,
            "not_matched_because": L.DECISION, "match_limitation": limitation,
            "owner_confirmation_ignored": confirmed}


def _boxes(d: bytes, i: int, end: int, out: list, path: tuple = ()) -> None:
    while i < end:
        if end - i < 8:
            raise ValueError("truncated box header")
        sz, t = struct.unpack(">I4s", d[i:i + 8]); h = 8
        if sz == 1:
            sz = struct.unpack(">Q", d[i + 8:i + 16])[0]; h = 16
        elif sz == 0:
            sz = end - i
        if sz < h or i + sz > end:
            raise ValueError(f"malformed box {t!r} at {i}")
        out.append((path + (t,), i, h, sz))
        if t in _CONTAINERS:
            _boxes(d, i + h, i + sz, out, path + (t,))
        i += sz


def media_fingerprint(data: bytes) -> str:
    """SHA-256 over ftyp/moov/mdat with stco/co64 offsets made relative to the mdat payload. A C2PA uuid box or a free
    box inserted at the top level does not change it; any change to the media bytes or sample tables does."""
    boxes: list = []
    _boxes(data, 0, len(data), boxes)
    top = [b for b in boxes if len(b[0]) == 1]
    mdat = [b for b in top if b[0][0] == b"mdat"]
    moov = [b for b in top if b[0][0] == b"moov"]
    if len(mdat) != 1 or len(moov) != 1:
        raise ValueError("need exactly one moov and one mdat")
    base = mdat[0][1] + mdat[0][2]
    _, oi, _, osz = moov[0]
    mv = bytearray(data[oi:oi + osz])
    for p, i, h, sz in boxes:
        if p[0] == b"moov" and p[-1] in (b"stco", b"co64"):
            n = struct.unpack(">I", data[i + h + 4:i + h + 8])[0]
            w = 4 if p[-1] == b"stco" else 8
            if 8 + n * w > sz - h:
                raise ValueError("chunk offset table overruns its box")
            for k in range(n):
                o = i + h + 8 + k * w
                v = int.from_bytes(data[o:o + w], "big") - base
                mv[o - oi:o - oi + w] = v.to_bytes(w, "big", signed=True)
    x = hashlib.sha256()
    for p, i, h, sz in top:
        t = p[0]
        if t == b"free" or (t == b"uuid" and data[i + h:i + h + 16].hex() == C2PA_UUID):
            continue
        x.update(t)
        x.update(bytes(mv) if t == b"moov" else data[i:i + sz])
    return x.hexdigest()


def sha256_file(p: Path) -> str:
    x = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            x.update(b)
    return x.hexdigest()


def index_outputs(dirs: list[str], runs_dir: str | None, fvs: list[dict]) -> tuple[list[dict], list[str]]:
    """Every .mp4 under --outputs with its size, name and the factory video it hash-links to (or why it does not)."""
    notes: list[str] = []
    by_sha: dict[str, list[dict]] = {}
    for fv in fvs:
        if fv.get("final_sha256"):
            by_sha.setdefault(fv["final_sha256"].lower(), []).append(fv)
    by_fp: dict[str, list[dict]] = {}
    if runs_dir:
        for fv in fvs:
            pk = Path(runs_dir) / fv["run_id"] / "package" / fv["video_id"] / "final.mp4"
            if not pk.is_file():
                continue
            if not fv.get("final_sha256") or sha256_file(pk) != fv["final_sha256"].lower():
                notes.append(f"{pk}: SHA-256 differs from videos.final_sha256; not used as a hash-chain anchor")
                continue
            try:
                by_fp.setdefault(media_fingerprint(pk.read_bytes()), []).append(fv)
            except ValueError as e:
                notes.append(f"{pk}: not parseable as MP4 ({e})")
    files = []
    for d in dirs:
        root = Path(d)
        if not root.is_dir():
            notes.append(f"--outputs {d} is not a folder")
            continue
        for p in sorted(root.rglob("*")):
            if not (p.is_file() and p.suffix.lower() == ".mp4"):
                continue
            rec = {"path": str(p), "name": p.name, "size": p.stat().st_size, "sha256": sha256_file(p), "chain": None}
            hits = by_sha.get(rec["sha256"], [])
            if len(hits) == 1:
                rec["chain"] = {"via": "sha256==videos.final_sha256", "run_id": hits[0]["run_id"],
                                "video_id": hits[0]["video_id"]}
            elif len(hits) > 1:
                rec["chain_problem"] = f"SHA-256 equals final_sha256 of {len(hits)} factory videos"
            else:
                try:
                    fp = media_fingerprint(p.read_bytes())
                    fh = by_fp.get(fp, [])
                    if len(fh) == 1:
                        rec["chain"] = {"via": "media_fingerprint==run package (package SHA-256 == videos.final_sha256)",
                                        "run_id": fh[0]["run_id"], "video_id": fh[0]["video_id"]}
                    else:
                        rec["chain_problem"] = ("media fingerprint matches no run package" if not fh else
                                                f"media fingerprint matches {len(fh)} run packages")
                        if not runs_dir:
                            rec["chain_problem"] += " (no --runs-dir given)"
                except ValueError as e:
                    rec["chain_problem"] = f"not parseable as MP4 ({e})"
            files.append(rec)
    return files, notes


def probable_match(v: dict, by_norm: dict) -> dict:
    """Title + duration + date. Report-only: never a reason to write anything."""
    dur = iso_seconds(v.get("duration", ""))
    cands = by_norm.get(norm_title(v["title"]), [])
    if len(cands) != 1:
        return {"reason": "no factory video with this title" if not cands else f"title matches {len(cands)} factory videos"}
    fv = cands[0]
    problems = []
    if dur is None or fv["duration_s"] is None or abs(dur - fv["duration_s"]) > DURATION_TOL_S:
        problems.append(f"duration {dur} s vs factory {fv['duration_s']} s")
    if run_date(fv) and (v.get("publishedAt") or "")[:10] < run_date(fv):
        problems.append(f"published {v.get('publishedAt')} before the run date {run_date(fv)}")
    out = {"run_id": fv["run_id"], "video_id": fv["video_id"], "factory_title": fv["title"]}
    if problems:
        return {**out, "reason": "; ".join(problems), "weak": True}
    exact = (v["title"] or "").strip() == (fv["title"] or "").strip()
    return {**out, "basis": f"title_{'exact' if exact else 'normalized'}+duration+date"}


def file_link(v: dict, files: list[dict]) -> dict:
    """The uploaded-file evidence for one video: {"link": ...} or {"reason": ...}."""
    fd = v["file_details"]
    if fd.get("status") != "available":
        return {"reason": "fileDetails unavailable: " + str(fd.get("reason"))}
    size, name = fd.get("file_size"), fd.get("file_name")
    if not isinstance(size, int) or isinstance(size, bool):
        return {"reason": "fileDetails has no integer fileSize"}
    if not name:
        return {"reason": "fileDetails has no fileName; fileSize alone is not enough"}
    same = [f for f in files if f["size"] == size]
    if not same:
        return {"reason": f"no output file of {size} bytes"}
    if len(same) > 1:
        return {"reason": f"{len(same)} output files have {size} bytes", "files": [f["path"] for f in same]}
    f = same[0]
    if Path(name.replace("\\", "/")).name.lower() != f["name"].lower():
        return {"reason": f"uploaded fileName {name!r} differs from the size-matched output {f['name']!r}",
                "files": [f["path"]]}
    if not f["chain"]:
        return {"reason": "size-matched output has no hash chain to a run: " + f.get("chain_problem", "unknown"),
                "files": [f["path"]]}
    return {"link": {**f["chain"], "file": f["path"], "file_size": size, "file_name": name, "file_sha256": f["sha256"]}}


def map_videos(yt: list[dict], fvs: list[dict], confirm: dict, files: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """-> (linked, probable, unresolved). Only `linked` (owner_confirmed / uploaded_file) is ever written."""
    by_norm: dict[str, list[dict]] = {}
    for fv in fvs:
        by_norm.setdefault(norm_title(fv["title"]), []).append(fv)
    keyset = {(f["run_id"], f["video_id"]): f for f in fvs}
    linked, probable, unresolved = [], [], []
    for v in yt:
        vid, dur = v["videoId"], iso_seconds(v.get("duration", ""))
        ev = {"youtube_id": vid, "youtube_title": v["title"], "published_at": v.get("publishedAt"), "youtube_duration_s": dur}
        if v.get("videoType") not in (None, "short"):
            unresolved.append({**ev, "reason": f"not a Short ({v.get('videoType')})"})
            continue
        prob = probable_match(v, by_norm)
        fl = file_link(v, files)
        c = confirm.get(vid)
        conf = keyset.get((c.get("run_id"), c.get("video_id"))) if c else None
        if c and not conf:
            unresolved.append({**ev, "reason": f"owner confirmation names an unknown factory video {c}"})
            continue
        cand = (conf["run_id"], conf["video_id"]) if conf else None
        mach = (fl["link"]["run_id"], fl["link"]["video_id"]) if "link" in fl else None
        if cand and mach and cand != mach:
            unresolved.append({**ev, "reason": f"owner confirmation {list(cand)} contradicts the uploaded-file link {list(mach)}",
                               "uploaded_file": fl["link"]})
            continue
        target = cand or mach
        if mach and not cand and "run_id" in prob and not prob.get("weak") and (prob["run_id"], prob["video_id"]) != mach:
            unresolved.append({**ev, "reason": f"uploaded-file link {list(mach)} contradicts the probable title match "
                               f"{[prob['run_id'], prob['video_id']]}", "uploaded_file": fl["link"]})
            continue
        if target:
            fv = keyset[target]
            linked.append({**ev, "run_id": fv["run_id"], "video_id": fv["video_id"], "factory_title": fv["title"],
                           "factory_duration_s": fv["duration_s"],
                           "evidence": "owner_confirmed" if cand else "uploaded_file",
                           **({"uploaded_file": fl["link"]} if mach else {"uploaded_file_check": fl.get("reason")})})
            continue
        if "basis" in prob:
            probable.append({**ev, "run_id": prob["run_id"], "video_id": prob["video_id"],
                             "factory_title": prob["factory_title"], "basis": prob["basis"],
                             "not_written_because": fl["reason"]})
        unresolved.append({**ev, "reason": fl["reason"], **({"files": fl["files"]} if "files" in fl else {}),
                           "probable": ({"run_id": prob["run_id"], "video_id": prob["video_id"], "basis": prob["basis"]}
                                        if "basis" in prob else
                                        {k: prob[k] for k in ("run_id", "video_id", "reason") if k in prob}),
                           "needs": "fileDetails that pass every uploaded-file check, or owner confirmation (--confirm)"})
    # one factory video or one output file may back only one YouTube id
    for key, label in ((lambda m: (m["run_id"], m["video_id"]), "factory video"),
                       (lambda m: m.get("uploaded_file", {}).get("file"), "output file")):
        claims: dict = {}
        for m in linked:
            k = key(m)
            if k:
                claims.setdefault(k, []).append(m["youtube_id"])
        dup = {k for k, ids in claims.items() if len(ids) > 1}
        for m in [m for m in linked if key(m) in dup]:
            linked.remove(m)
            unresolved.append({**m, "reason": f"{label} claimed by several YouTube ids {claims[key(m)]}"})
    return linked, probable, unresolved


def metric_rows(snap: dict, mapped: list[dict], held: frozenset = frozenset()) -> tuple[list[dict], list[dict]]:
    cols = snap["columns"]
    by_id = {r[cols.index("video")]: dict(zip(cols, r)) for r in snap["rows"]}
    end = snap["endDate"]
    rows, missing = [], []
    for m in mapped:
        r = by_id.get(m["youtube_id"])
        if not r:
            missing.append({"youtube_id": m["youtube_id"], "run_id": m["run_id"], "video_id": m["video_id"],
                            "reason": "no row in the snapshot (analytics lag or no views in the window)"})
            continue
        views = r.get("views") or 0
        inter = sum(r.get(k) or 0 for k in ("likes", "comments", "shares"))
        age = (date.fromisoformat(end) - date.fromisoformat(m["published_at"][:10])).days if m.get("published_at") else None
        raw = {**r, "window": {"start": snap["startDate"], "end": end, "note": snap.get("note")}, "source": snap["source"],
               "published_at": m.get("published_at"), "age_days_at_window_end": age,
               "engaged_view_rate": round(r["engagedViews"] / views, 4) if views and r.get("engagedViews") is not None else None}
        rows.append({"run_id": m["run_id"], "video_id": m["video_id"], "platform": "youtube", "captured_at": snap["captured_at"],
                     "views": float(views),
                     "retention": round(r["averageViewPercentage"] / 100, 4) if r.get("averageViewPercentage") is not None else None,
                     "engagement_rate": round(inter / views, 5) if views else None, "perf": None,
                     "raw_json": json.dumps(raw, sort_keys=True)})
    mapped_ids = {m["youtube_id"] for m in mapped}
    for yid in by_id:
        if yid not in mapped_ids:
            missing.append({"youtube_id": yid, **({"scope": L.SCOPE} if L.is_legacy(yid) else {}),
                            "reason": "legacy channel video, not a factory video (not inserted)" if L.is_legacy(yid)
                            else "linked factory video is not public yet: held (not inserted)" if yid in held
                            else "snapshot row has no mapped factory video (not inserted)"})
    return rows, missing


def plan(con, table: str, key: list[str], rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        cur = con.execute(f"SELECT * FROM {table} WHERE " + " AND ".join(f"{k}=?" for k in key), [row[k] for k in key])
        cols = [c[0] for c in cur.description]
        have = cur.fetchone()
        if have is None:
            out.append({"action": "insert", "row": row})
        else:
            have = dict(zip(cols, have))
            diff = {c: {"db": have.get(c), "new": row[c]} for c in row if have.get(c) != row[c]}
            out.append({"action": "conflict" if diff else "unchanged", "row": row, **({"diff": diff} if diff else {})})
    return out


def fail(code: str, **info) -> int:
    print(json.dumps({"error": code, **info}, ensure_ascii=True))
    return 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True); ap.add_argument("--videos", required=True)
    ap.add_argument("--metrics", help="metrics snapshot; required unless --publications-only")
    ap.add_argument("--publications-only", action="store_true",
                    help="plan/write publications only; metrics are neither read nor written")
    ap.add_argument("--confirm"); ap.add_argument("--out"); ap.add_argument("--apply", action="store_true")
    ap.add_argument("--outputs", action="append", default=[], help="folder with upload-ready .mp4 files (repeatable)")
    ap.add_argument("--runs-dir", help="factory runs folder, for the hash chain of outputs that carry a C2PA box")
    a = ap.parse_args()
    pub_only = a.publications_only
    if pub_only and a.metrics:
        return fail("METRICS_WITH_PUBLICATIONS_ONLY", detail="--publications-only never reads metrics; drop --metrics")
    if not pub_only and not a.metrics:
        return fail("METRICS_REQUIRED", detail="--metrics is required unless --publications-only is given")
    if not Path(a.db).is_file():
        return fail("DB_NOT_FOUND", db=a.db)
    inputs = {"videos": a.videos, "metrics": None if pub_only else a.metrics, "confirm": a.confirm}
    docs = {}
    for name, path in inputs.items():   # every input is read and validated before the database is opened
        if path is None:
            continue
        try:
            docs[name] = load_json(path)
        except FileNotFoundError:
            return fail("INPUT_NOT_FOUND", input=name, path=path)
        except (OSError, ValueError) as e:
            return fail("INPUT_INVALID", input=name, path=path, detail=str(e)[:200])
    if not isinstance(docs["videos"], dict) or not isinstance(docs["videos"].get("videos"), list):
        return fail("INPUT_INVALID", input="videos", path=a.videos, detail="expected an object with a 'videos' list")
    if not pub_only:
        need = ("columns", "rows", "startDate", "endDate", "captured_at", "source")
        if not isinstance(docs["metrics"], dict) or any(k not in docs["metrics"] for k in need):
            return fail("INPUT_INVALID", input="metrics", path=a.metrics, detail=f"expected keys {list(need)}")
    if "confirm" in docs and not isinstance(docs["confirm"], dict):
        return fail("INPUT_INVALID", input="confirm", path=a.confirm, detail="expected an object")
    try:
        con = sqlite3.connect(a.db)
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.DatabaseError as e:
        return fail("DB_INVALID", db=a.db, detail=str(e)[:200])
    if not {"videos", "runs", "publications", "metrics"} <= tables:
        return fail("DB_SCHEMA", tables=sorted(tables))
    yt, snap = docs["videos"], docs.get("metrics")
    fvs = factory_videos(con)
    yv = normalize_videos(yt)
    in_db = sorted({r[0] for r in con.execute("SELECT platform_video_id FROM publications WHERE platform='youtube'")
                    if L.is_legacy(r[0])})
    if in_db:
        return fail("LEGACY_LINKED_IN_DB", ids=in_db, detail="legacy channel videos must never have a factory "
                    "publication; fix the database first (nothing was written)")
    confirm_all = docs.get("confirm", {})
    legacy = [legacy_entry(v, v["videoId"] in confirm_all) for v in yv if L.is_legacy(v["videoId"])]
    confirm = {k: c for k, c in confirm_all.items() if not L.is_legacy(k)}
    files, file_notes = index_outputs(a.outputs, a.runs_dir, fvs)
    mapped, probable, unmapped = map_videos([v for v in yv if not L.is_legacy(v["videoId"])], fvs, confirm, files)
    assert all(m["evidence"] in LINKED for m in mapped)
    by_id = {v["videoId"]: v for v in yv}
    held = []
    for m in list(mapped):   # write a time only when the snapshot shows the video public and unscheduled
        v = by_id[m["youtube_id"]]
        at, basis = L.public_time(v.get("privacy"), v.get("publishedAt"), v.get("publish_at"))
        if at is None:
            mapped.remove(m)
            row = con.execute("SELECT published_at FROM publications WHERE platform='youtube' AND platform_video_id=?",
                              (m["youtube_id"],)).fetchone()
            held.append({**m, "privacy": v.get("privacy"), "publish_at": v.get("publish_at"),
                         "reason": basis,
                         "action": "not written (no publication, no metrics); re-run after the video is public",
                         "existing_db_row": None if row is None else {"published_at": row[0], "touched": False}})
        else:
            m["published_at_basis"] = basis
    pubs = [{"run_id": m["run_id"], "video_id": m["video_id"], "platform": "youtube", "url": URL.format(m["youtube_id"]),
             "platform_video_id": m["youtube_id"], "published_at": m["published_at"]} for m in mapped]
    mets, no_metrics = ([], []) if pub_only else metric_rows(snap, mapped, frozenset(h["youtube_id"] for h in held))
    pub_plan = plan(con, "publications", ["run_id", "video_id", "platform"], pubs)
    for p in pub_plan:   # one YouTube id must never point at two factory videos
        other = con.execute("SELECT run_id, video_id FROM publications WHERE platform='youtube' AND platform_video_id=? "
                            "AND NOT (run_id=? AND video_id=?)", (p["row"]["platform_video_id"], p["row"]["run_id"],
                                                                  p["row"]["video_id"])).fetchone()
        if other:
            p.update(action="conflict", diff={"platform_video_id": {"db_already_maps_to": list(other)}})
    met_plan = [] if pub_only else plan(con, "metrics", ["run_id", "video_id", "platform", "captured_at"], mets)
    count = lambda pl, k: sum(1 for p in pl if p["action"] == k)  # noqa: E731
    report = {"mode": "apply" if a.apply else "dry-run", "publications_only": pub_only, "db": str(Path(a.db).resolve()),
              "metrics_window": None if pub_only else {"start": snap["startDate"], "end": snap["endDate"],
                                                       "captured_at": snap["captured_at"], "note": snap.get("note")},
              "file_details": {"available": sum(1 for v in yv if v["file_details"].get("status") == "available"),
                               "videos": len(yv),
                               "capability": (yt.get("capabilities") or {}).get("file_details"),
                               "note": None if any(v["file_details"].get("status") == "available" for v in yv) else
                               "no video in --videos has fileDetails: uploaded-file links are impossible; only "
                               "owner confirmations can be written"},
              "output_files": files, "output_notes": file_notes,
              "mapped": mapped, "probable_not_written": probable, "unmapped": unmapped, "held_not_public": held,
              "legacy_channel": legacy,
              "no_metrics": no_metrics,
              "publications": pub_plan, "metrics": met_plan,
              "totals": {"youtube_videos": len(yv), "mapped": len(mapped), "probable_not_written": len(probable),
                         "unmapped": len(unmapped), "held_not_public": len(held), "legacy_channel": len(legacy),
                         "by_evidence": {k: sum(1 for m in mapped if m["evidence"] == k) for k in LINKED},
                         "publications": {k: count(pub_plan, k) for k in ("insert", "unchanged", "conflict")},
                         "metrics": "skipped (--publications-only)" if pub_only else
                         {k: count(met_plan, k) for k in ("insert", "unchanged", "conflict")}}}
    if a.apply and any(p["action"] == "insert" for p in pub_plan + met_plan):
        stamp, n = time.strftime("%Y%m%d-%H%M%S"), 0
        bak = Path(f"{a.db}.bak-{stamp}")
        while bak.exists():                      # never overwrite an earlier backup
            n += 1
            bak = Path(f"{a.db}.bak-{stamp}-{n}")
        con.close()
        shutil.copy2(a.db, bak)
        con = sqlite3.connect(a.db)
        with con:
            # met_plan is empty with --publications-only, so only publications can be inserted
            for table, pl in (("publications", pub_plan), ("metrics", met_plan)):
                for p in pl:
                    if p["action"] == "insert":
                        r = p["row"]
                        con.execute(f"INSERT INTO {table}({','.join(r)}) VALUES({','.join('?' * len(r))})", list(r.values()))
        report["backup"] = str(bak)
    text = json.dumps(report, indent=1, ensure_ascii=True)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps({"mode": report["mode"], "publications_only": pub_only, "totals": report["totals"], "report": a.out,
                      "backup": report.get("backup")}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
