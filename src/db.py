"""
MongoDB Atlas history & analytics module.
Tracks all generated content to prevent topic repetition and store metadata.

Phase 3.3: Smarter deduplication — code similarity check + language frequency balancing.
Phase 3.4: Graceful degradation — upload retry queue.
"""
import logging
import re
from datetime import datetime, timezone

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from src import config

logger = logging.getLogger(__name__)

DB_NAME = "content_pipeline"
COLLECTION_NAME = "history"

# ── Module-level connection (reused across calls) ─────────────
_client = None
_collection = None


def _get_collection():
    """Get or create a MongoDB collection handle (lazy singleton)."""
    global _client, _collection
    if _collection is not None:
        return _collection

    if not config.MONGODB_URI:
        raise RuntimeError("MONGODB_URI is not configured")

    _client = MongoClient(
        config.MONGODB_URI,
        serverSelectionTimeoutMS=10_000,
        connectTimeoutMS=10_000,
        tls=True,                   # Force TLS encryption in transit
        retryWrites=True,           # Auto-retry on transient errors
        retryReads=True,
        appname="content-pipeline", # Identifies this app in MongoDB logs
    )
    # Verify connectivity
    _client.admin.command("ping")
    logger.info("Connected to MongoDB Atlas (TLS encrypted)")

    db = _client[DB_NAME]
    _collection = db[COLLECTION_NAME]

    # Ensure indexes
    _collection.create_index("created_at")
    _collection.create_index("status")
    _collection.create_index("language")

    return _collection


# ══════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════

def get_past_topics(limit: int = 50) -> list[dict]:
    """
    Retrieve the most recent successfully generated topics.
    Used by the LLM module to avoid repeating content.
    """
    try:
        col = _get_collection()
        docs = (
            col.find(
                {"status": "success"},
                {"topic": 1, "title": 1, "language": 1, "_id": 0},
            )
            .sort("created_at", -1)
            .limit(limit)
        )
        return list(docs)
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        logger.warning(f"MongoDB unreachable, returning empty history: {e}")
        return []


def save_record(data: dict) -> str | None:
    """
    Insert a new content record into MongoDB.
    Returns the inserted document ID as string, or None on failure.
    """
    try:
        col = _get_collection()
        record = {
            "topic": data.get("topic", ""),
            "title": data.get("title", ""),
            "script": data.get("script", ""),
            "code": data.get("code", ""),
            "language": data.get("language", ""),
            "hashtags": data.get("hashtags", []),
            "content_type": data.get("content_type", "tip"),
            "code_output": data.get("code_output"),
            "youtube_id": data.get("youtube_id"),
            "tiktok_id": data.get("tiktok_id"),
            "duration_seconds": data.get("duration_seconds", 0),
            "status": data.get("status", "success"),
            "error_message": data.get("error_message"),
            "metrics": data.get("metrics"),
            # Series fields (Phase 6.4)
            "series_id":   data.get("series_id"),
            "series_part": data.get("series_part"),
            # A/B testing & tone metadata (Phase 6.5 / 6.6 / 6.7)
            "prompt_variant": data.get("prompt_variant"),
            "narrator_tone":  data.get("narrator_tone"),
            "template_used":  data.get("template_used"),
            "created_at": datetime.now(timezone.utc),
            "published_at": data.get("published_at"),
        }
        result = col.insert_one(record)
        logger.info(f"Saved record to MongoDB: {result.inserted_id}")
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"Failed to save record to MongoDB: {e}")
        return None


def get_stats() -> dict:
    """Get basic pipeline statistics (for monitoring)."""
    try:
        col = _get_collection()
        total = col.count_documents({})
        success = col.count_documents({"status": "success"})
        failed = col.count_documents({"status": "failed"})

        # Language distribution
        pipeline = [
            {"$match": {"status": "success"}},
            {"$group": {"_id": "$language", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        lang_dist = {doc["_id"]: doc["count"] for doc in col.aggregate(pipeline)}

        return {
            "total": total,
            "success": success,
            "failed": failed,
            "languages": lang_dist,
        }
    except Exception as e:
        logger.warning(f"Failed to get stats: {e}")
        return {}


# ══════════════════════════════════════════════════════════════
#  SMARTER DEDUPLICATION  (Phase 3.3)
# ══════════════════════════════════════════════════════════════

def _normalize_code(code: str) -> str:
    """Normalize code for similarity comparison.
    Strips comments, collapses whitespace, lowercases.
    """
    # Remove single-line comments (# // --)
    code = re.sub(r"(#|//|--)\s*.*$", "", code, flags=re.MULTILINE)
    # Remove multi-line comments /* */
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    # Collapse whitespace
    code = re.sub(r"\s+", " ", code).strip().lower()
    return code


def check_code_similarity(new_code: str, limit: int = 20) -> dict:
    """
    Check if new code is too similar to recently generated content.

    Uses normalized token overlap (Jaccard similarity).

    Args:
        new_code: The new code snippet to check.
        limit: Number of recent records to compare against.

    Returns:
        Dict with:
          - is_duplicate (bool): True if too similar (>70%)
          - max_similarity (float): Highest similarity found (0.0–1.0)
          - similar_to (str): Title of the most similar content
    """
    new_normalized = _normalize_code(new_code)
    new_tokens = set(new_normalized.split())

    if not new_tokens:
        return {"is_duplicate": False, "max_similarity": 0.0, "similar_to": ""}

    max_sim = 0.0
    similar_title = ""

    try:
        col = _get_collection()
        docs = (
            col.find(
                {"status": "success", "code": {"$exists": True}},
                {"code": 1, "title": 1, "_id": 0},
            )
            .sort("created_at", -1)
            .limit(limit)
        )
        for doc in docs:
            existing_code = doc.get("code", "")
            if not existing_code:
                continue
            existing_tokens = set(_normalize_code(existing_code).split())
            if not existing_tokens:
                continue

            # Jaccard similarity
            intersection = new_tokens & existing_tokens
            union = new_tokens | existing_tokens
            similarity = len(intersection) / len(union) if union else 0

            if similarity > max_sim:
                max_sim = similarity
                similar_title = doc.get("title", "")

    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        logger.warning(f"MongoDB unreachable during similarity check: {e}")
        return {"is_duplicate": False, "max_similarity": 0.0, "similar_to": ""}

    is_dup = max_sim > 0.70
    if is_dup:
        logger.warning(
            f"Code similarity {max_sim:.0%} with '{similar_title}' — flagged as duplicate"
        )

    return {
        "is_duplicate": is_dup,
        "max_similarity": round(max_sim, 3),
        "similar_to": similar_title,
    }


def get_language_frequency(limit: int = 20) -> dict:
    """
    Get language frequency from recent successful videos.

    Returns:
        Dict with:
          - counts (dict[str, int]): language → count
          - overused (list[str]): languages used ≥5× in last N
          - suggested_avoid (list[str]): top 2 most frequent languages
          - recent_types (list[str]): recent content_type values (newest first)
    """
    counts: dict[str, int] = {}
    recent_types: list[str] = []

    try:
        col = _get_collection()
        docs = (
            col.find(
                {"status": "success"},
                {"language": 1, "content_type": 1, "_id": 0},
            )
            .sort("created_at", -1)
            .limit(limit)
        )
        for doc in docs:
            lang = doc.get("language", "unknown")
            counts[lang] = counts.get(lang, 0) + 1
            ct = doc.get("content_type", "tip")
            recent_types.append(ct)

    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        logger.warning(f"MongoDB unreachable during frequency check: {e}")

    overused = [lang for lang, c in counts.items() if c >= 5]
    sorted_langs = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    suggested_avoid = [lang for lang, _ in sorted_langs[:2]]

    return {
        "counts": counts,
        "overused": overused,
        "suggested_avoid": suggested_avoid,
        "recent_types": recent_types,
    }


# ══════════════════════════════════════════════════════════════
#  GRACEFUL DEGRADATION — Upload Retry Queue  (Phase 3.4)
# ══════════════════════════════════════════════════════════════

def save_pending_upload(video_path: str, record: dict) -> str | None:
    """
    Save a rendered-but-not-uploaded video for later retry.

    Sets status = 'rendered_not_uploaded' and stores the video path.
    """
    try:
        col = _get_collection()
        record["status"] = "rendered_not_uploaded"
        record["video_path"] = video_path
        record["retry_count"] = 0
        record["created_at"] = datetime.now(timezone.utc)

        result = col.insert_one(record)
        logger.info(f"Saved pending upload to retry queue: {result.inserted_id}")
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"Failed to save pending upload: {e}")
        return None


def get_pending_uploads(limit: int = 5) -> list[dict]:
    """
    Retrieve videos that were rendered but failed to upload.

    Returns list of records with status 'rendered_not_uploaded'
    and retry_count < 3.
    """
    try:
        col = _get_collection()
        docs = col.find(
            {
                "status": "rendered_not_uploaded",
                "retry_count": {"$lt": 3},
            },
        ).sort("created_at", 1).limit(limit)
        return list(docs)
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        logger.warning(f"MongoDB unreachable, no pending uploads: {e}")
        return []


def mark_upload_complete(doc_id, youtube_id: str) -> bool:
    """Mark a pending upload as successfully uploaded."""
    try:
        from bson import ObjectId
        col = _get_collection()
        col.update_one(
            {"_id": ObjectId(str(doc_id))},
            {
                "$set": {
                    "status": "success",
                    "youtube_id": youtube_id,
                    "published_at": datetime.now(timezone.utc),
                }
            },
        )
        logger.info(f"Marked {doc_id} as uploaded: {youtube_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to mark upload complete: {e}")
        return False


def increment_retry_count(doc_id) -> bool:
    """Increment the retry counter for a pending upload."""
    try:
        from bson import ObjectId
        col = _get_collection()
        col.update_one(
            {"_id": ObjectId(str(doc_id))},
            {"$inc": {"retry_count": 1}},
        )
        return True
    except Exception as e:
        logger.error(f"Failed to increment retry count: {e}")
        return False
