#!/usr/bin/env python3
"""yt_sync - read-only YouTube Data + Analytics pull for Brain Academy (standard library only).

  python tools/youtube_sync/yt_sync.py auth            one-time browser consent, stores a refresh token
  python tools/youtube_sync/yt_sync.py pull [--since 2026-10-01] [--out <repo>/data/analytics]
  python tools/youtube_sync/yt_sync.py status          shows whether a token exists (never prints it)

Secrets live outside the repository, in %USERPROFILE%/.brain-academy/ (override with YT_SYNC_HOME):
  client_secret.json  the OAuth "Desktop app" client downloaded from Google Cloud
  youtube_token.json  written by `auth`; contains the refresh token
Scopes are read-only (youtube.readonly, yt-analytics.readonly). Nothing is uploaded, edited or published.
Free: uses the YouTube Data API v3 and YouTube Analytics API quotas of your own Google Cloud project.
Not available from any API: Studio's "Stayed to watch" and "Shown in feed". engagedViews / views is the proxy.

Uploaded-file evidence (for linking a YouTube id to a factory output file): videos.list part=fileDetails is owner-only and
is filled only when processingDetails.fileDetailsAvailability is "available". Each video row gets
  file_details = {"status": "available", "file_name": ..., "file_size": <bytes>, "availability": ...}
  or {"status": "unavailable", "reason": ...}
Values are copied from the API response only; nothing is derived or guessed. If the API rejects the part, the pull
continues without it and snapshot["capabilities"]["file_details"] says why.
"""
from __future__ import annotations

import argparse, base64, csv, datetime as dt, hashlib, http.server, json, os, secrets, sys, threading
import urllib.error, urllib.parse, urllib.request, webbrowser
from pathlib import Path

# repo/data/analytics, wherever the command is run from (1.0 used a path relative to the current folder, so a pull run
# inside tools/youtube_sync wrote to tools/youtube_sync/data/analytics)
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "data" / "analytics"

HOME = Path(os.environ.get("YT_SYNC_HOME") or (Path.home() / ".brain-academy"))
CLIENT = HOME / "client_secret.json"
TOKEN = HOME / "youtube_token.json"
SCOPES = "https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/yt-analytics.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DATA = "https://www.googleapis.com/youtube/v3/"
ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
VIDEO_METRICS = ("views,engagedViews,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
                 "likes,comments,shares,subscribersGained,subscribersLost")


def die(msg: str, code: int = 2):
    print(json.dumps({"error": msg}, ensure_ascii=False)); sys.exit(code)


def load_client() -> dict:
    if not CLIENT.exists():
        die(f"missing {CLIENT} - download the OAuth Desktop client JSON from Google Cloud and save it there")
    c = json.loads(CLIENT.read_text(encoding="utf-8"))
    c = c.get("installed") or c.get("web") or {}
    if not c.get("client_id"):
        die("client_secret.json has no client_id (use an OAuth client of type 'Desktop app')")
    return c


def post_form(url: str, fields: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        die(f"token endpoint HTTP {e.code}: {json.loads(body).get('error_description', body[:200]) if body.startswith('{') else body[:200]}")


def cmd_auth(_a) -> int:
    c = load_client()
    HOME.mkdir(parents=True, exist_ok=True)
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    got: dict = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write("<h3>Brain Academy sync: authorization received. You can close this tab.</h3>".encode())
        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    redirect = f"http://127.0.0.1:{srv.server_address[1]}"
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": c["client_id"], "redirect_uri": redirect, "response_type": "code", "scope": SCOPES,
        "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})
    print("Opening the browser for Google consent. If it does not open, paste this URL into your browser:\n" + url)
    webbrowser.open(url)
    t = threading.Thread(target=srv.handle_request); t.start(); t.join(timeout=300); srv.server_close()
    if got.get("state") != state or "code" not in got:
        die(f"no authorization code received ({got.get('error', 'timeout or state mismatch')})")
    tok = post_form(TOKEN_URL, {"code": got["code"], "client_id": c["client_id"], "client_secret": c.get("client_secret", ""),
                                "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier})
    if "refresh_token" not in tok:
        die("Google returned no refresh token; remove the app's access at myaccount.google.com/permissions and run auth again")
    TOKEN.write_text(json.dumps({"refresh_token": tok["refresh_token"], "scope": tok.get("scope"),
                                 "created_at": dt.datetime.now(dt.timezone.utc).isoformat()}), encoding="utf-8")
    print(json.dumps({"ok": True, "token_file": str(TOKEN)}))
    return 0


def access_token() -> str:
    if not TOKEN.exists():
        die(f"no token at {TOKEN} - run: python tools/youtube_sync/yt_sync.py auth")
    c = load_client(); t = json.loads(TOKEN.read_text(encoding="utf-8"))
    r = post_form(TOKEN_URL, {"client_id": c["client_id"], "client_secret": c.get("client_secret", ""),
                              "refresh_token": t["refresh_token"], "grant_type": "refresh_token"})
    return r["access_token"]


class Api:
    def __init__(self):
        self.tok = access_token(); self.calls = 0

    def get(self, base: str, params: dict) -> dict:
        url = base + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.tok}"})
        self.calls += 1
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            try:
                msg = json.loads(body)["error"]["message"]
            except Exception:
                msg = body[:300]
            raise RuntimeError(f"HTTP {e.code} {base.rsplit('/', 1)[-1]}: {msg}")

    def report(self, **p) -> list[dict]:
        r = self.get(ANALYTICS, {"ids": "channel==MINE", **p})
        cols = [h["name"] for h in r.get("columnHeaders", [])]
        return [dict(zip(cols, row)) for row in r.get("rows", []) or []]


FILE_PARTS = "fileDetails,processingDetails"


def file_details_of(v: dict) -> dict:
    """fileDetails of one videos.list item, as returned by the API; never invented."""
    if "fileDetails" not in v and "processingDetails" not in v:
        return {"status": "unavailable", "reason": "fileDetails not requested or not returned"}
    avail = (v.get("processingDetails") or {}).get("fileDetailsAvailability")
    fd = v.get("fileDetails") or {}
    name, size = fd.get("fileName"), fd.get("fileSize")
    try:
        size = int(size) if size is not None else None   # unsigned long, serialised as a JSON string
    except (TypeError, ValueError):
        return {"status": "unavailable", "reason": f"fileSize is not an integer: {size!r}", "availability": avail}
    if avail != "available":
        return {"status": "unavailable", "reason": f"processingDetails.fileDetailsAvailability={avail!r}",
                "availability": avail}
    if size is None and not name:
        return {"status": "unavailable", "reason": "fileDetails has neither fileName nor fileSize", "availability": avail}
    return {"status": "available", "file_name": name, "file_size": size, "availability": avail}


def fetch_videos(api, ids: list[str]) -> tuple[list[dict], dict]:
    """videos.list with fileDetails; if the API refuses those parts, retry without them and say so."""
    base = "snippet,contentDetails,statistics,status"
    cap = {"requested": True, "error": None}
    items = []
    for i in range(0, len(ids), 50):
        chunk = ",".join(ids[i:i + 50])
        if cap["error"] is None:
            try:
                items += api.get(DATA + "videos", {"part": base + "," + FILE_PARTS, "id": chunk}).get("items", [])
                continue
            except RuntimeError as e:
                cap["error"] = str(e)[:300]
        items += api.get(DATA + "videos", {"part": base, "id": chunk}).get("items", [])
    return items, cap


def cmd_pull(a) -> int:
    api = Api()
    today = dt.date.today().isoformat()
    ch = api.get(DATA + "channels", {"part": "snippet,contentDetails,statistics", "mine": "true"})["items"][0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = [], None
    while True:
        p = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50}
        if page: p["pageToken"] = page
        r = api.get(DATA + "playlistItems", p)
        ids += [i["contentDetails"]["videoId"] for i in r.get("items", [])]
        page = r.get("nextPageToken")
        if not page: break
    videos = []
    items, file_cap = fetch_videos(api, ids)
    for v in items:
        videos.append({"video_id": v["id"], "title": v["snippet"]["title"], "published_at": v["snippet"]["publishedAt"],
                       "duration": v["contentDetails"]["duration"], "privacy": v["status"]["privacyStatus"],
                       "publish_at": v["status"].get("publishAt"),
                       "public_views": int(v["statistics"].get("viewCount", 0)),
                       "public_likes": int(v["statistics"].get("likeCount", 0)),
                       "public_comments": int(v["statistics"].get("commentCount", 0)),
                       "file_details": file_details_of(v)})
        if file_cap["error"] and "fileDetails" not in v and "processingDetails" not in v:
            videos[-1]["file_details"] = {"status": "unavailable",
                                          "reason": "videos.list refused fileDetails: " + file_cap["error"]}
    file_cap["available_for"] = sum(1 for v in videos if v["file_details"]["status"] == "available")
    file_cap["videos"] = len(videos)
    by_video = {r["video"]: r for r in api.report(startDate=a.since, endDate=today, metrics=VIDEO_METRICS,
                                                  dimensions="video", sort="-views", maxResults=200)}
    traffic = api.report(startDate=a.since, endDate=today, metrics="views,engagedViews,estimatedMinutesWatched",
                         dimensions="insightTrafficSourceType")
    daily_channel = api.report(startDate=a.since, endDate=today, metrics="views,engagedViews,subscribersGained,subscribersLost",
                               dimensions="day", sort="day")
    per_video, errors = {}, []
    for v in videos:
        if v["privacy"] != "public":
            continue
        vid = v["video_id"]; f = f"video=={vid}"; item = {}
        for key, kw in (("retention", dict(metrics="audienceWatchRatio,relativeRetentionPerformance", dimensions="elapsedVideoTimeRatio", maxResults=100)),
                        ("traffic", dict(metrics="views,engagedViews", dimensions="insightTrafficSourceType")),
                        ("daily", dict(metrics="views,engagedViews,likes,subscribersGained", dimensions="day", sort="day"))):
            try:
                item[key] = api.report(startDate=a.since, endDate=today, filters=f, **kw)
            except RuntimeError as e:
                item[key] = []; errors.append(f"{vid} {key}: {e}")
        per_video[vid] = item
    rows = []
    for v in videos:
        m = by_video.get(v["video_id"], {})
        ev, vw = m.get("engagedViews"), m.get("views")
        rows.append({**v, **{k: m.get(k) for k in VIDEO_METRICS.split(",")},
                     "engaged_share": round(ev / vw, 4) if ev is not None and vw else None})
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(a.out) / stamp; out.mkdir(parents=True, exist_ok=True)
    snap = {"pulled_at": dt.datetime.now(dt.timezone.utc).isoformat(), "since": a.since, "until": today,
            "channel": {"id": ch["id"], "title": ch["snippet"]["title"], "subscribers": ch["statistics"].get("subscriberCount"),
                        "views": ch["statistics"].get("viewCount"), "videos": ch["statistics"].get("videoCount")},
            "note": "Analytics rows lag 1-3 days; Stayed to watch / Shown in feed are Studio-only (engaged_share is the proxy).",
            "videos": rows, "channel_traffic": traffic, "channel_daily": daily_channel, "per_video": per_video,
            "capabilities": {"file_details": file_cap}, "errors": errors, "api_calls": api.calls}
    (out / "snapshot.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    (Path(a.out) / "latest.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    flat = [{**{k: v for k, v in r.items() if k != "file_details"}, "file_details_status": r["file_details"]["status"],
             "file_name": r["file_details"].get("file_name"), "file_size": r["file_details"].get("file_size")} for r in rows]
    with open(out / "videos.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(flat[0].keys()) if flat else ["video_id"]); w.writeheader(); w.writerows(flat)
    print(json.dumps({"ok": True, "out": str(out), "videos": len(rows), "with_analytics": len(by_video),
                      "file_details": {k: file_cap[k] for k in ("available_for", "videos", "error")},
                      "errors": len(errors), "api_calls": api.calls}))
    return 0


def cmd_status(_a) -> int:
    print(json.dumps({"home": str(HOME), "client_secret": CLIENT.exists(), "token": TOKEN.exists()}))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth"); sub.add_parser("status")
    p = sub.add_parser("pull"); p.add_argument("--since", default="2026-10-01"); p.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args()
    return {"auth": cmd_auth, "pull": cmd_pull, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
