"""
MongoDB Atlas history & analytics module.
Tracks all generated content to prevent topic repetition and store metadata.
"""
import logging
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
    )
    # Verify connectivity
    _client.admin.command("ping")
    logger.info("Connected to MongoDB Atlas")

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
            "youtube_id": data.get("youtube_id"),
            "tiktok_id": data.get("tiktok_id"),
            "duration_seconds": data.get("duration_seconds", 0),
            "status": data.get("status", "success"),
            "error_message": data.get("error_message"),
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
