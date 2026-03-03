"""
MongoDB Archive & Cleanup — Phase 8.2

Maintenance utilities to keep MongoDB Atlas free-tier usage under control:
  - archive_old_records: move records > N days to 'archived_videos' collection
  - cleanup_failed_renders: remove old local video files
  - check_storage_usage: alert if approaching 512MB limit

Usage:
    python -m src.main --maintenance      # run all maintenance tasks
"""
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src import config

logger = logging.getLogger(__name__)


def archive_old_records(days: int | None = None) -> dict:
    """
    Move records older than ``days`` to the ``archived_videos`` collection.

    Strips large fields (code, script) from archived records to save space.
    Keeps only: title, language, content_type, created_at, yt_metrics,
    upload_result, youtube_id, quality_score.

    Args:
        days: Age threshold in days. Defaults to config.ARCHIVE_DAYS (90).

    Returns:
        Dict with 'archived' count, 'deleted' count, 'errors' count.
    """
    if days is None:
        days = config.ARCHIVE_DAYS

    result = {"archived": 0, "deleted": 0, "errors": 0}

    try:
        from src.db import _get_collection

        col = _get_collection()
        db = col.database

        # Get or create archive collection
        archive_col = db["archived_videos"]
        archive_col.create_index("created_at")

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        old_docs = list(col.find({"created_at": {"$lt": cutoff}}))
        if not old_docs:
            logger.info(f"No records older than {days} days to archive")
            return result

        logger.info(f"Archiving {len(old_docs)} records older than {days} days...")

        for doc in old_docs:
            try:
                # Build slim archived record
                archived = {
                    "_id": doc["_id"],
                    "title": doc.get("title", ""),
                    "language": doc.get("language", ""),
                    "content_type": doc.get("content_type", "tip"),
                    "created_at": doc.get("created_at"),
                    "published_at": doc.get("published_at"),
                    "youtube_id": doc.get("youtube_id"),
                    "upload_results": doc.get("upload_results"),
                    "quality_score": doc.get("quality_score"),
                    "yt_metrics": doc.get("yt_metrics"),
                    "status": doc.get("status"),
                    "duration_seconds": doc.get("duration_seconds"),
                    "archived_at": datetime.now(timezone.utc),
                }

                # Upsert into archive (idempotent)
                archive_col.replace_one(
                    {"_id": doc["_id"]},
                    archived,
                    upsert=True,
                )
                result["archived"] += 1

                # Delete from main collection
                col.delete_one({"_id": doc["_id"]})
                result["deleted"] += 1

            except Exception as e:
                logger.error(f"Failed to archive doc {doc.get('_id')}: {e}")
                result["errors"] += 1

        logger.info(
            f"Archive complete: {result['archived']} archived, "
            f"{result['deleted']} deleted, {result['errors']} errors"
        )

    except Exception as e:
        logger.error(f"Archive operation failed: {e}")

    return result


def cleanup_failed_renders(max_age_days: int = 7) -> dict:
    """
    Delete local video files in the output directory older than ``max_age_days``.

    Targets: .mp4, .mp3, .wav files in config.OUTPUT_DIR.

    Returns:
        Dict with 'deleted' count, 'freed_bytes', 'errors' count.
    """
    result = {"deleted": 0, "freed_bytes": 0, "errors": 0}

    try:
        output_dir = config.OUTPUT_DIR
        if not output_dir.exists():
            logger.info("Output directory doesn't exist — nothing to clean")
            return result

        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        cutoff_ts = cutoff.timestamp()

        extensions = {".mp4", ".mp3", ".wav", ".webm", ".png", ".jpg"}

        for fpath in output_dir.iterdir():
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() not in extensions:
                continue

            try:
                mtime = fpath.stat().st_mtime
                if mtime < cutoff_ts:
                    size = fpath.stat().st_size
                    fpath.unlink()
                    result["deleted"] += 1
                    result["freed_bytes"] += size
                    logger.debug(f"Deleted old file: {fpath.name} ({size / 1024:.1f} KB)")
            except Exception as e:
                logger.warning(f"Failed to delete {fpath.name}: {e}")
                result["errors"] += 1

        freed_mb = result["freed_bytes"] / (1024 * 1024)
        logger.info(
            f"Cleanup complete: {result['deleted']} files deleted, "
            f"{freed_mb:.1f} MB freed, {result['errors']} errors"
        )

    except Exception as e:
        logger.error(f"Cleanup operation failed: {e}")

    return result


def check_storage_usage() -> dict:
    """
    Check MongoDB Atlas database storage usage.

    If usage exceeds config.MONGO_STORAGE_ALERT_MB (default 400MB),
    send a Telegram alert.

    Returns:
        Dict with 'storage_mb', 'alert_sent', 'collections'.
    """
    result = {"storage_mb": 0.0, "alert_sent": False, "collections": {}}

    try:
        from src.db import _get_collection

        col = _get_collection()
        db = col.database

        stats = db.command("dbStats")
        data_size = stats.get("dataSize", 0)
        storage_size = stats.get("storageSize", 0)

        # Use the larger of the two
        size_bytes = max(data_size, storage_size)
        size_mb = size_bytes / (1024 * 1024)
        result["storage_mb"] = round(size_mb, 2)

        # Per-collection stats
        for col_name in db.list_collection_names():
            try:
                col_stats = db.command("collStats", col_name)
                col_size = col_stats.get("storageSize", 0) / (1024 * 1024)
                result["collections"][col_name] = round(col_size, 2)
            except Exception:
                pass

        logger.info(f"MongoDB storage: {size_mb:.1f} MB / {config.MONGO_STORAGE_ALERT_MB} MB limit")

        # Check if alert threshold exceeded
        if size_mb > config.MONGO_STORAGE_ALERT_MB:
            logger.warning(
                f"MongoDB storage alert! {size_mb:.1f} MB exceeds "
                f"{config.MONGO_STORAGE_ALERT_MB} MB threshold "
                f"(free tier limit: 512 MB)"
            )
            try:
                from src.notifier import send_notification
                send_notification(
                    status="failed",
                    title="Storage Alert",
                    error_message=(
                        f"MongoDB storage: {size_mb:.1f} MB / 512 MB (free tier). "
                        f"Threshold: {config.MONGO_STORAGE_ALERT_MB} MB. "
                        "Run --maintenance to archive old records."
                    ),
                    error_class="PERMANENT",
                )
                result["alert_sent"] = True
            except Exception as e:
                logger.warning(f"Failed to send storage alert: {e}")

    except Exception as e:
        logger.error(f"Storage check failed: {e}")

    return result


def cleanup_old_logs(days: int = 30) -> dict:
    """
    Phase 8.3 helper: Delete pipeline_logs older than ``days``.

    Returns:
        Dict with 'deleted' count.
    """
    result = {"deleted": 0}

    try:
        from src.db import _get_collection
        col = _get_collection()
        db = col.database

        logs_col = db["pipeline_logs"]
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        del_result = logs_col.delete_many({"timestamp": {"$lt": cutoff}})
        result["deleted"] = del_result.deleted_count
        logger.info(f"Deleted {result['deleted']} pipeline logs older than {days} days")

    except Exception as e:
        logger.error(f"Log cleanup failed: {e}")

    return result


def run_maintenance() -> dict:
    """
    Run all maintenance tasks:
      1. Archive old records (>90 days)
      2. Cleanup failed renders (>7 days)
      3. Check storage usage
      4. Cleanup old pipeline logs (>30 days)

    Returns:
        Combined report dict.
    """
    logger.info("=" * 55)
    logger.info("  Database Maintenance — Phase 8.2")
    logger.info("=" * 55)

    report = {}

    # 1. Archive
    logger.info("Step 1: Archiving old records...")
    report["archive"] = archive_old_records()

    # 2. Cleanup renders
    logger.info("Step 2: Cleaning up old render files...")
    report["cleanup_renders"] = cleanup_failed_renders()

    # 3. Storage check
    logger.info("Step 3: Checking MongoDB storage usage...")
    report["storage"] = check_storage_usage()

    # 4. Log rotation
    logger.info("Step 4: Rotating old pipeline logs...")
    report["log_rotation"] = cleanup_old_logs()

    logger.info("=" * 55)
    logger.info("  Maintenance complete")
    logger.info("=" * 55)
    return report
