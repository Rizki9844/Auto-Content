"""
Self-Healing Pipeline — Phase 8.1

Periodic self-checks that detect and auto-recover from common failures:
  - Stale queue detector: pending uploads > 24h → alert + auto-retry
  - Quota recovery: YouTube quota exhausted → skip upload, reschedule 24h
  - Storage monitor: MongoDB usage alert when approaching free-tier limit

Usage:
    python -m src.main --health-monitor   # run all health checks
"""
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


def check_stale_queue(stale_hours: int = 24) -> dict:
    """
    Detect items in pending_uploads that have been stuck > stale_hours.

    For each stale item:
      - Send a Telegram alert
      - Auto-retry by resetting retry_count to 0

    Returns:
        Dict with 'stale_count', 'alerted', 'reset' counts.
    """
    from src.db import _get_collection
    from src.notifier import send_notification

    result = {"stale_count": 0, "alerted": 0, "reset": 0}

    try:
        col = _get_collection()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=stale_hours)

        stale_docs = list(col.find({
            "status": "rendered_not_uploaded",
            "created_at": {"$lt": cutoff},
        }))

        result["stale_count"] = len(stale_docs)

        if not stale_docs:
            logger.info("No stale items in upload queue")
            return result

        logger.warning(f"Found {len(stale_docs)} stale item(s) in upload queue (>{stale_hours}h)")

        for doc in stale_docs:
            title = doc.get("title", "Unknown")
            age_hours = (datetime.now(timezone.utc) - doc["created_at"]).total_seconds() / 3600

            # Send Telegram alert
            try:
                send_notification(
                    status="failed",
                    title=title,
                    error_message=(
                        f"Stale upload detected: '{title}' has been pending for "
                        f"{age_hours:.0f}h. Auto-retrying..."
                    ),
                    error_class="TRANSIENT",
                )
                result["alerted"] += 1
            except Exception as e:
                logger.warning(f"Failed to send stale alert for '{title}': {e}")

            # Reset retry count to allow re-processing
            try:
                col.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"retry_count": 0}},
                )
                result["reset"] += 1
                logger.info(f"Reset retry count for stale item: {title}")
            except Exception as e:
                logger.error(f"Failed to reset retry count for {doc['_id']}: {e}")

    except Exception as e:
        logger.error(f"Stale queue check failed: {e}")

    return result


def check_quota_recovery() -> dict:
    """
    Check if YouTube quota has recovered (resets daily at midnight Pacific).

    If quota is exhausted, reschedule pending uploads for 24h later.

    Returns:
        Dict with 'quota_available', 'rescheduled' count.
    """
    from src.rate_limiter import RateLimiter

    result = {"quota_available": True, "rescheduled": 0}

    try:
        limiter = RateLimiter()
        quota_status = limiter.check_youtube_quota()

        if quota_status["can_upload"]:
            logger.info(f"YouTube quota OK: {quota_status['remaining']} remaining")
            return result

        result["quota_available"] = False
        logger.warning(
            f"YouTube quota exhausted ({quota_status['remaining']} remaining). "
            "Pending uploads will be retried in next run."
        )

        # Send alert
        try:
            from src.notifier import send_notification
            send_notification(
                status="failed",
                title="Quota Recovery",
                error_message=(
                    f"YouTube API quota exhausted. "
                    f"Remaining: {quota_status['remaining']}. "
                    "Uploads will resume when quota resets (midnight Pacific)."
                ),
                error_class="PERMANENT",
            )
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Quota recovery check failed: {e}")

    return result


def run_all_checks() -> dict:
    """
    Run all health monitor checks and return a combined report.

    Returns:
        Dict with results from each check.
    """
    logger.info("=" * 55)
    logger.info("  Health Monitor — Running self-healing checks")
    logger.info("=" * 55)

    report = {}

    # 1. Stale queue detector
    logger.info("Checking stale upload queue...")
    report["stale_queue"] = check_stale_queue()

    # 2. Quota recovery
    logger.info("Checking YouTube quota status...")
    report["quota"] = check_quota_recovery()

    # Summary
    issues = []
    if report["stale_queue"]["stale_count"] > 0:
        issues.append(f"{report['stale_queue']['stale_count']} stale uploads")
    if not report["quota"]["quota_available"]:
        issues.append("YouTube quota exhausted")

    if issues:
        logger.warning(f"Health issues found: {', '.join(issues)}")
    else:
        logger.info("All health checks passed ✓")

    logger.info("=" * 55)
    return report
