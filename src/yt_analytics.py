"""
src/yt_analytics.py — YouTube Analytics Feedback Loop (Phase 6.2)

Fetches real performance metrics for recently uploaded videos using:
  - YouTube Data API v3  `videos.list(part=statistics)`  → views, likes
  - YouTube Analytics API v2  `reports.query`            → avd_s, ctr

Stores results in MongoDB under ``yt_metrics`` on each history record, and
exposes query helpers that feed back into content-generation decisions.

Required environment variables:
  ENABLE_YT_ANALYTICS  = "0" | "1"      (default "0", opt-in)
  YOUTUBE_CHANNEL_ID   = "UCxxxxxxxxxx" (needed for Analytics API AVD/CTR)
  YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
  (same OAuth credentials used for upload — no re-auth needed if the
   refresh token was issued with youtube.readonly + yt-analytics.readonly
   scopes; Data API statistics endpoint works with upload scope too)

yt_metrics document schema (stored under history record):
  {
    "views":      int,
    "likes":      int,
    "avd_s":      float,   # average view duration in seconds
    "ctr":        float,   # impressions click-through rate (0.0–1.0)
    "fetched_at": datetime
  }
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ── OAuth service builders ──────────────────────────────────────────────────

def _build_youtube_service():
    """
    Build an OAuth2-authenticated YouTube Data API v3 service.
    Reuses the same credential pattern as uploader_youtube.py.
    """
    from src import config
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    if not config.YOUTUBE_REFRESH_TOKEN:
        raise RuntimeError(
            "YOUTUBE_REFRESH_TOKEN not configured. "
            "Run 'python -m scripts.auth_youtube' to set up credentials."
        )

    creds = Credentials(
        token=None,
        refresh_token=config.YOUTUBE_REFRESH_TOKEN,
        client_id=config.YOUTUBE_CLIENT_ID,
        client_secret=config.YOUTUBE_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def _build_analytics_service():
    """
    Build an OAuth2-authenticated YouTube Analytics API v2 service.
    Requires the refresh token to include yt-analytics.readonly scope.
    Returns None and logs a warning if credentials are missing.
    """
    from src import config
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    if not config.YOUTUBE_REFRESH_TOKEN:
        logger.debug("YOUTUBE_REFRESH_TOKEN not set — Analytics API unavailable")
        return None

    creds = Credentials(
        token=None,
        refresh_token=config.YOUTUBE_REFRESH_TOKEN,
        client_id=config.YOUTUBE_CLIENT_ID,
        client_secret=config.YOUTUBE_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return build("youtubeAnalytics", "v2", credentials=creds)


# ── Core metric fetch ───────────────────────────────────────────────────────

def fetch_video_metrics(video_id: str, channel_id: str = "") -> dict[str, Any]:
    """
    Fetch performance metrics for a single YouTube video.

    Step 1 — YouTube Data API v3 (views + likes):
        Works with the existing upload OAuth token.

    Step 2 — YouTube Analytics API v2 (avd_s + ctr):
        Requires YOUTUBE_CHANNEL_ID and yt-analytics.readonly scope.
        Gracefully skipped if unavailable.

    Args:
        video_id:   YouTube video ID (e.g. "dQw4w9WgXcQ").
        channel_id: YouTube channel ID (needed for Analytics API).

    Returns:
        Dict with keys: views, likes, avd_s, ctr, fetched_at.
        Missing fields default to 0 / 0.0; function never raises.
    """
    metrics: dict[str, Any] = {
        "views":      0,
        "likes":      0,
        "avd_s":      0.0,
        "ctr":        0.0,
        "fetched_at": datetime.now(timezone.utc),
    }

    # ── Step 1: views + likes (Data API v3) ──────────────────
    try:
        yt = _build_youtube_service()
        resp = (
            yt.videos()
            .list(part="statistics", id=video_id)
            .execute()
        )
        items = resp.get("items", [])
        if items:
            stats = items[0].get("statistics", {})
            metrics["views"] = int(stats.get("viewCount", 0))
            metrics["likes"] = int(stats.get("likeCount", 0))
        logger.debug(
            f"Data API stats for {video_id}: "
            f"views={metrics['views']}, likes={metrics['likes']}"
        )
    except Exception as exc:
        logger.warning(f"Data API fetch failed for {video_id}: {exc}")

    # ── Step 2: avd_s + ctr (Analytics API v2) ───────────────
    if channel_id:
        try:
            analytics = _build_analytics_service()
            if analytics is None:
                raise RuntimeError("Analytics service unavailable")

            end_date   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            start_date = (
                datetime.now(timezone.utc) - timedelta(days=90)
            ).strftime("%Y-%m-%d")

            resp = (
                analytics.reports()
                .query(
                    ids=f"channel=={channel_id}",
                    startDate=start_date,
                    endDate=end_date,
                    metrics="views,averageViewDuration,annotationClickThroughRate",
                    dimensions="video",
                    filters=f"video=={video_id}",
                    maxResults=1,
                )
                .execute()
            )
            rows = resp.get("rows", [])
            if rows:
                row = rows[0]
                # column order: video, views, averageViewDuration, annotationCTR
                if len(row) >= 3:
                    metrics["avd_s"] = round(float(row[2]), 2)
                if len(row) >= 4:
                    metrics["ctr"]   = round(float(row[3]), 6)
            logger.debug(
                f"Analytics API for {video_id}: "
                f"avd_s={metrics['avd_s']:.1f}s, ctr={metrics['ctr']:.4f}"
            )
        except Exception as exc:
            logger.warning(
                f"Analytics API fetch failed for {video_id} "
                f"(avd_s/ctr will be 0): {exc}"
            )

    return metrics


# ── MongoDB persistence ─────────────────────────────────────────────────────

def store_video_metrics(doc_id: Any, metrics: dict[str, Any]) -> bool:
    """
    Upsert ``yt_metrics`` field on the MongoDB history record for ``doc_id``.

    Returns True if the record was found and updated, False otherwise.
    """
    try:
        from src.db import _get_collection
        col = _get_collection()
        result = col.update_one(
            {"_id": doc_id},
            {"$set": {"yt_metrics": metrics}},
        )
        updated = result.matched_count > 0
        if updated:
            logger.debug(f"yt_metrics stored for doc_id={doc_id}")
        else:
            logger.warning(f"No document found for doc_id={doc_id}")
        return updated
    except Exception as exc:
        logger.warning(f"store_video_metrics error (doc_id={doc_id}): {exc}")
        return False


# ── Batch refresh ───────────────────────────────────────────────────────────

def fetch_and_store_recent(
    limit: int = 20,
    channel_id: str = "",
    min_age_hours: int = 48,
) -> dict[str, int]:
    """
    Fetch and persist YouTube metrics for recently uploaded videos.

    Only processes records that:
      1. Have a non-null ``youtube_id``
      2. Were created at least ``min_age_hours`` ago (allows views to accumulate)
      3. Either have no ``yt_metrics`` yet, or the ``yt_metrics.fetched_at``
         timestamp is older than 24 h (avoids hammering the API on re-runs)

    Args:
        limit:         Max number of candidate records to process per call.
        channel_id:    YouTube channel ID for Analytics API (opt-in).
        min_age_hours: Minimum hours after upload before first fetch.

    Returns:
        Summary dict: {processed, updated, failed, skipped}
    """
    from src import config as cfg
    from src.db import _get_collection

    channel_id   = channel_id or cfg.YOUTUBE_CHANNEL_ID
    upload_cutoff = datetime.now(timezone.utc) - timedelta(hours=min_age_hours)
    stale_cutoff  = datetime.now(timezone.utc) - timedelta(hours=24)

    summary: dict[str, int] = {
        "processed": 0, "updated": 0, "failed": 0, "skipped": 0,
    }

    # ── Query: candidates that need metrics refresh ───────────
    try:
        col = _get_collection()
        query: dict[str, Any] = {
            "youtube_id": {"$exists": True, "$nin": [None, ""]},
            "status": "success",
            "created_at": {"$lte": upload_cutoff},
            "$or": [
                {"yt_metrics": {"$exists": False}},
                {"yt_metrics.fetched_at": {"$lt": stale_cutoff}},
            ],
        }
        docs = list(
            col.find(query, {"_id": 1, "youtube_id": 1, "created_at": 1})
            .sort("created_at", -1)
            .limit(limit)
        )
    except Exception as exc:
        logger.error(f"fetch_and_store_recent: DB query failed: {exc}")
        return summary

    logger.info(
        f"Metrics refresh: {len(docs)} candidate(s) found "
        f"(limit={limit}, min_age={min_age_hours}h)"
    )

    for doc in docs:
        summary["processed"] += 1
        vid = doc.get("youtube_id", "")
        if not vid:
            summary["skipped"] += 1
            continue

        try:
            metrics = fetch_video_metrics(vid, channel_id)
            if store_video_metrics(doc["_id"], metrics):
                summary["updated"] += 1
                logger.info(
                    f"  ✓ {vid} — views={metrics['views']}, "
                    f"likes={metrics['likes']}, avd_s={metrics['avd_s']:.1f}s"
                )
            else:
                summary["failed"] += 1
        except Exception as exc:
            summary["failed"] += 1
            logger.warning(f"  ✗ {vid}: {exc}")

    logger.info(
        f"Metrics refresh done — "
        f"updated={summary['updated']}, "
        f"failed={summary['failed']}, "
        f"skipped={summary['skipped']}"
    )
    return summary


# ── Analytics query helpers (used by llm.py + analytics.py) ────────────────

def get_best_content_type(
    min_views: int = 50,
    min_samples: int = 3,
) -> str | None:
    """
    Return the ``content_type`` with the highest average YouTube views.

    Requires at least ``min_samples`` records per type (statistical floor)
    and each record must have at least ``min_views`` (filters early outliers).

    Returns None when data is insufficient.
    """
    try:
        from src.db import _get_collection
        col = _get_collection()
        pipeline = [
            {"$match": {
                "yt_metrics.views": {"$gte": min_views},
                "content_type":     {"$exists": True, "$ne": ""},
            }},
            {"$group": {
                "_id":       "$content_type",
                "avg_views": {"$avg": "$yt_metrics.views"},
                "count":     {"$sum": 1},
            }},
            {"$match": {"count": {"$gte": min_samples}}},
            {"$sort": {"avg_views": -1}},
            {"$limit": 1},
        ]
        results = list(col.aggregate(pipeline))
        if results:
            winner = results[0]["_id"]
            avg    = round(results[0]["avg_views"])
            logger.debug(f"Best content_type: '{winner}' (avg {avg} views)")
            return winner
    except Exception as exc:
        logger.warning(f"get_best_content_type failed: {exc}")
    return None


def get_best_language(
    min_views: int = 50,
    min_samples: int = 3,
) -> str | None:
    """
    Return the programming language with the highest average YouTube views.

    Same threshold logic as :func:`get_best_content_type`.
    Returns None when data is insufficient.
    """
    try:
        from src.db import _get_collection
        col = _get_collection()
        pipeline = [
            {"$match": {
                "yt_metrics.views": {"$gte": min_views},
                "language":         {"$exists": True, "$ne": ""},
            }},
            {"$group": {
                "_id":       "$language",
                "avg_views": {"$avg": "$yt_metrics.views"},
                "count":     {"$sum": 1},
            }},
            {"$match": {"count": {"$gte": min_samples}}},
            {"$sort": {"avg_views": -1}},
            {"$limit": 1},
        ]
        results = list(col.aggregate(pipeline))
        if results:
            winner = results[0]["_id"]
            avg    = round(results[0]["avg_views"])
            logger.debug(f"Best language: '{winner}' (avg {avg} views)")
            return winner
    except Exception as exc:
        logger.warning(f"get_best_language failed: {exc}")
    return None


# ── Upload Time Optimization (Phase 7.5) ───────────────────────────────────

def get_best_upload_times(
    top_n: int = 3,
    min_samples: int = 3,
    min_views: int = 0,
) -> list[tuple[int, int]]:
    """
    Determine the best upload times based on historical view performance.

    Queries MongoDB for videos with ``yt_metrics`` and groups them by the
    UTC hour of their ``published_at`` timestamp.  Returns the top-N hours
    (by average views) as ``(hour, 0)`` tuples compatible with
    ``scheduler.PEAK_SLOTS_UTC``.

    Args:
        top_n:       Number of slots to return (default 3).
        min_samples: Minimum videos in an hour bucket to be considered.
        min_views:   Minimum view count threshold per video.

    Returns:
        List of ``(hour, minute)`` tuples sorted by highest avg views.
        Empty list if there isn't enough data.
    """
    try:
        from src.db import _get_collection
        col = _get_collection()

        pipeline = [
            {"$match": {
                "yt_metrics.views": {"$exists": True, "$gte": min_views},
                "published_at":     {"$exists": True},
            }},
            {"$project": {
                "hour":  {"$hour": "$published_at"},
                "views": "$yt_metrics.views",
            }},
            {"$group": {
                "_id":       "$hour",
                "avg_views": {"$avg": "$views"},
                "count":     {"$sum": 1},
            }},
            {"$match": {"count": {"$gte": min_samples}}},
            {"$sort": {"avg_views": -1}},
            {"$limit": top_n},
        ]
        results = list(col.aggregate(pipeline))
        if results:
            slots = [(int(r["_id"]), 0) for r in results]
            logger.info(
                f"Best upload times (top {top_n}): "
                + ", ".join(f"{h:02d}:{m:02d} UTC" for h, m in slots)
            )
            return slots

    except Exception as exc:
        logger.warning(f"get_best_upload_times failed: {exc}")

    return []


# ── Report data (used by analytics.py) ─────────────────────────────────────

def get_yt_metrics_summary() -> dict[str, Any]:
    """
    Return aggregated YouTube performance data for the analytics report.

    Returns:
        Dict with keys: total_with_metrics, avg_views, avg_likes, avg_avd_s,
        best_content_type, best_language, top_videos (list of up to 5 dicts).
        Returns safe empty defaults on any failure.
    """
    empty: dict[str, Any] = {
        "total_with_metrics": 0,
        "avg_views":         0.0,
        "avg_likes":         0.0,
        "avg_avd_s":         0.0,
        "best_content_type": None,
        "best_language":     None,
        "top_videos":        [],
    }
    try:
        from src.db import _get_collection
        col = _get_collection()

        # ── Aggregate averages ────────────────────────────────
        agg = list(col.aggregate([
            {"$match": {"yt_metrics": {"$exists": True}}},
            {"$group": {
                "_id":       None,
                "count":     {"$sum": 1},
                "avg_views": {"$avg": "$yt_metrics.views"},
                "avg_likes": {"$avg": "$yt_metrics.likes"},
                "avg_avd_s": {"$avg": "$yt_metrics.avd_s"},
            }},
        ]))
        if not agg:
            return empty

        summary: dict[str, Any] = {
            "total_with_metrics": agg[0]["count"],
            "avg_views":         round(agg[0]["avg_views"], 1),
            "avg_likes":         round(agg[0]["avg_likes"], 1),
            "avg_avd_s":         round(agg[0]["avg_avd_s"], 1),
            "best_content_type": get_best_content_type(),
            "best_language":     get_best_language(),
            "top_videos":        [],
        }

        # ── Top 5 videos by view count ────────────────────────
        top_docs = list(
            col.find(
                {"yt_metrics.views": {"$gt": 0}},
                {
                    "title": 1, "language": 1, "content_type": 1,
                    "yt_metrics": 1, "youtube_id": 1, "_id": 0,
                },
            )
            .sort("yt_metrics.views", -1)
            .limit(5)
        )
        summary["top_videos"] = [
            {
                "title":        doc.get("title", "?"),
                "language":     doc.get("language", "?"),
                "content_type": doc.get("content_type", "?"),
                "views":        doc.get("yt_metrics", {}).get("views", 0),
                "likes":        doc.get("yt_metrics", {}).get("likes", 0),
                "avd_s":        doc.get("yt_metrics", {}).get("avd_s", 0.0),
                "url": (
                    f"https://youtube.com/shorts/{doc['youtube_id']}"
                    if doc.get("youtube_id") else ""
                ),
            }
            for doc in top_docs
        ]
        return summary

    except Exception as exc:
        logger.warning(f"get_yt_metrics_summary failed: {exc}")
        return empty
