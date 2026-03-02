"""
Content scheduling module — Phase 4.2.

Manages a MongoDB ``scheduled`` collection that acts as a publish queue.

Usage flow:
  1.  ``python -m src.main --batch 3``
        → generates 3 videos, assigns future peak-time slots, saves to queue.

  2.  ``python -m src.main --upload-queue``
        → picks up due jobs, uploads via all configured uploaders, marks done.

Peak slots (UTC) mirror the generate.yml cron schedule and target
the US audience:
  - 13:00 UTC  →  8 AM EST  /  5 AM PST  — morning commute
  - 18:00 UTC  →  1 PM EST  / 10 AM PST  — lunch break
  - 00:00 UTC  →  7 PM EST  /  4 PM PST  — prime time (evening)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ASCENDING

logger = logging.getLogger(__name__)

# ── MongoDB collection name ────────────────────────────────────
SCHEDULED_COLLECTION = "scheduled"

# ── Peak publish slots (UTC hour, minute) ─────────────────────
# Must match generate.yml cron schedule for coherent timing.
PEAK_SLOTS_UTC: list[tuple[int, int]] = [
    (13, 0),   # 8 AM EST — morning
    (18, 0),   # 1 PM EST — lunch
    (0, 0),    # 7 PM EST — prime time
]

# ── Job status constants ───────────────────────────────────────
STATUS_PENDING   = "pending"
STATUS_UPLOADING = "uploading"
STATUS_DONE      = "done"
STATUS_FAILED    = "failed"

# Lazily-resolved collection handle
_sched_col = None


# ──────────────────────────────────────────────────────────────
#  Internal helpers
# ──────────────────────────────────────────────────────────────

def _get_sched_collection():
    """Return (and cache) the ``scheduled`` MongoDB collection."""
    global _sched_col
    if _sched_col is not None:
        return _sched_col

    from src.db import _get_collection  # reuse same MongoClient
    col_handle = _get_collection()      # ensures client is alive
    db = col_handle.database
    _sched_col = db[SCHEDULED_COLLECTION]

    # Indexes
    _sched_col.create_index([("publish_at", ASCENDING)])
    _sched_col.create_index([("status", ASCENDING)])
    logger.debug("Scheduler collection ready")
    return _sched_col


def _slot_datetime(dt: datetime, hour: int, minute: int) -> datetime:
    """Return a UTC datetime for the given hour:minute on the same date as dt."""
    return dt.replace(hour=hour, minute=minute, second=0, microsecond=0,
                      tzinfo=timezone.utc)


def next_available_slots(n: int, after: datetime | None = None) -> list[datetime]:
    """
    Return the next ``n`` unique peak-time slots that are in the future
    *and* not yet occupied by a pending/uploading job.

    Args:
        n:     Number of slots to reserve.
        after: Start searching after this datetime (default: now).

    Returns:
        List of UTC aware datetimes, sorted ascending.
    """
    if n <= 0:
        return []

    col = _get_sched_collection()
    now = after or datetime.now(timezone.utc)

    # Fetch all occupied slots from the queue
    occupied: set[datetime] = set()
    for doc in col.find(
        {"status": {"$in": [STATUS_PENDING, STATUS_UPLOADING]}},
        {"publish_at": 1},
    ):
        ts = doc.get("publish_at")
        if ts:
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            occupied.add(ts)

    slots: list[datetime] = []
    cursor = now
    max_iterations = 365 * len(PEAK_SLOTS_UTC)  # safety upper-bound

    for _ in range(max_iterations):
        for hour, minute in PEAK_SLOTS_UTC:
            candidate = _slot_datetime(cursor, hour, minute)
            if candidate <= now:
                candidate += timedelta(days=1)

            if candidate not in occupied and candidate not in slots:
                slots.append(candidate)
                if len(slots) == n:
                    slots.sort()
                    return slots
        cursor += timedelta(days=1)

    slots.sort()
    return slots


# ──────────────────────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────────────────────

def add_to_schedule(
    content: dict[str, Any],
    video_path: str,
    audio_path: str,
    publish_at: datetime,
    quality_score: float = 0.0,
) -> str:
    """
    Add a rendered video to the publish queue.

    Args:
        content:       Content dict from ``generate_content()``.
        video_path:    Absolute path to the rendered MP4 file.
        audio_path:    Absolute path to the TTS audio file.
        publish_at:    UTC datetime when this should be uploaded.
        quality_score: Quality score from Phase 3.1.

    Returns:
        Inserted document ID (str).
    """
    col = _get_sched_collection()
    doc = {
        "status": STATUS_PENDING,
        "publish_at": publish_at,
        "created_at": datetime.now(timezone.utc),
        "title": content.get("title", ""),
        "script": content.get("script", ""),
        "language": content.get("language", ""),
        "hashtags": content.get("hashtags", []),
        "content_type": content.get("content_type", "tip"),
        "code": content.get("code", ""),
        "video_path": video_path,
        "audio_path": audio_path,
        "quality_score": quality_score,
        "retry_count": 0,
        "upload_results": {},
    }
    result = col.insert_one(doc)
    inserted_id = str(result.inserted_id)
    logger.info(
        f"Scheduled '{doc['title']}' for "
        f"{publish_at.strftime('%Y-%m-%d %H:%M UTC')}"
        f" (id={inserted_id})"
    )
    return inserted_id


def get_due_jobs(limit: int = 5) -> list[dict[str, Any]]:
    """
    Return up to ``limit`` due jobs (``publish_at <= now``, status == pending).

    Results are ordered by ``publish_at`` ascending (oldest first).
    """
    col = _get_sched_collection()
    now = datetime.now(timezone.utc)
    docs = list(
        col.find(
            {
                "status": STATUS_PENDING,
                "publish_at": {"$lte": now},
            },
            sort=[("publish_at", ASCENDING)],
            limit=limit,
        )
    )
    return docs


def get_pending_count() -> int:
    """Return number of pending (not yet due) jobs in the queue."""
    col = _get_sched_collection()
    now = datetime.now(timezone.utc)
    return col.count_documents({
        "status": STATUS_PENDING,
        "publish_at": {"$gt": now},
    })


def mark_job_done(job_id: Any, upload_results: dict[str, str | None]) -> None:
    """Mark a scheduled job as successfully uploaded."""
    from bson import ObjectId
    col = _get_sched_collection()
    col.update_one(
        {"_id": ObjectId(str(job_id)) if not hasattr(job_id, "generation_time") else job_id},
        {
            "$set": {
                "status": STATUS_DONE,
                "upload_results": upload_results,
                "completed_at": datetime.now(timezone.utc),
            }
        },
    )
    logger.info(f"Job {job_id} marked done: {upload_results}")


def mark_job_failed(job_id: Any, error: str, increment_retry: bool = True) -> None:
    """Mark a scheduled job as failed (optionally increment retry count)."""
    from bson import ObjectId
    col = _get_sched_collection()
    update: dict[str, Any] = {
        "$set": {
            "status": STATUS_FAILED,
            "last_error": str(error)[:500],
            "failed_at": datetime.now(timezone.utc),
        }
    }
    if increment_retry:
        update["$inc"] = {"retry_count": 1}
    col.update_one(
        {"_id": ObjectId(str(job_id)) if not hasattr(job_id, "generation_time") else job_id},
        update,
    )
    logger.warning(f"Job {job_id} marked failed: {error[:200]}")


def get_schedule_summary() -> dict[str, Any]:
    """
    Return a summary of the current queue state for logging/monitoring.

    Returns dict with keys: pending_due, pending_future, done_today, failed_total.
    """
    col = _get_sched_collection()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    return {
        "pending_due": col.count_documents({
            "status": STATUS_PENDING,
            "publish_at": {"$lte": now},
        }),
        "pending_future": col.count_documents({
            "status": STATUS_PENDING,
            "publish_at": {"$gt": now},
        }),
        "done_today": col.count_documents({
            "status": STATUS_DONE,
            "completed_at": {"$gte": today_start},
        }),
        "failed_total": col.count_documents({"status": STATUS_FAILED}),
    }
