"""Legacy Brain Academy channel videos: published before the content factory existed (owner decision, 2026-10-17).

These YouTube ids are permanent, explicit exceptions. They are never linked to a factory output file, run or
publication — not by uploaded-file evidence, not by owner confirmation, not by title. They may appear in channel-wide
statistics, but never in factory KPIs, production cost or run attribution. Reports show them under the label
`legacy_channel` with the reason they are not matched. The list is fixed: it is not derived from dates or titles.
A copy of this set lives in content-database/scripts/cfdb.py (LEGACY_CHANNEL_VIDEOS); a test keeps both identical.
"""
from __future__ import annotations

SCOPE = "legacy_channel"
DECISION = "owner decision 2026-10-17: legacy channel video published before the content factory; never linked"
LEGACY_CHANNEL_VIDEOS = frozenset({"KHutHAMv2_A", "cFwkqgRnV9I", "QqI7w_BZaWE", "aRJAjjHVx9g"})


def is_legacy(youtube_id) -> bool:
    return youtube_id in LEGACY_CHANNEL_VIDEOS


def public_time(privacy, published_at, publish_at):
    """(time, basis). snippet.publishedAt is the moment the video became public only while it is public and not
    scheduled; otherwise the public time cannot be verified from the API and stays None."""
    if privacy == "public" and not publish_at and published_at:
        return published_at, "snippet.publishedAt of a public video"
    if privacy is None:
        return None, "unverifiable: privacy status not in the input"
    if privacy != "public":
        return None, f"unverifiable: video is {privacy}" + (f" (scheduled publishAt {publish_at})" if publish_at else "")
    return None, f"unverifiable: public video with publishAt {publish_at!r} or no publishedAt"
