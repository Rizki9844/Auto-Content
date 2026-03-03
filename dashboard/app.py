"""
Pipeline Dashboard — Phase 9.4.

A minimal Flask web app for monitoring the auto-content pipeline.
Reads data from MongoDB (same collections used by the pipeline).

Routes:
    /           — Overview: total videos, last run status, queue length
    /videos     — List of all videos with search & filter
    /analytics  — Charts: views trend, content type distribution
    /health     — System health: quota, stale queue, storage
    /api/stats  — JSON API for programmatic access

Usage:
    python -m dashboard.app                  # run on default port 5050
    DASHBOARD_PORT=8080 python -m dashboard.app

Deployment: Render / Railway / local.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path so we can import src.*
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from flask import Flask, jsonify, render_template

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("DASHBOARD_SECRET_KEY", "dev-secret-change-me")


def _get_db():
    """Get the MongoDB database connection (lazy)."""
    from src.db import _get_collection
    return _get_collection


def _safe_query(func, default=None):
    """Execute a DB query safely, returning default on failure."""
    try:
        return func()
    except Exception as e:
        logger.warning(f"Dashboard DB query failed: {e}")
        return default


# ══════════════════════════════════════════════════════════════
#  ROUTE: Overview
# ══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """Overview page with key stats."""
    get_col = _get_db()

    stats = _safe_query(lambda: _get_overview_stats(get_col), {})
    return render_template("index.html", stats=stats)


def _get_overview_stats(get_col) -> dict:
    """Gather overview statistics."""
    videos_col = get_col("videos")
    queue_col = get_col("pending_uploads")
    logs_col = get_col("pipeline_logs")

    total_videos = videos_col.count_documents({})
    total_queue = queue_col.count_documents({})

    # Last run
    last_log = logs_col.find_one(sort=[("timestamp", -1)])
    last_run = None
    last_outcome = "unknown"
    if last_log:
        last_run = last_log.get("timestamp")
        last_outcome = last_log.get("outcome", "unknown")

    # Videos this week
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    videos_this_week = videos_col.count_documents(
        {"created_at": {"$gte": week_ago}}
    )

    # Language distribution
    lang_pipeline = [
        {"$group": {"_id": "$language", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5},
    ]
    languages = {
        doc["_id"]: doc["count"]
        for doc in videos_col.aggregate(lang_pipeline)
        if doc["_id"]
    }

    return {
        "total_videos": total_videos,
        "queue_length": total_queue,
        "last_run": last_run,
        "last_outcome": last_outcome,
        "videos_this_week": videos_this_week,
        "languages": languages,
    }


# ══════════════════════════════════════════════════════════════
#  ROUTE: Videos List
# ══════════════════════════════════════════════════════════════

@app.route("/videos")
def videos():
    """List all videos with basic info."""
    from flask import request
    get_col = _get_db()

    page = int(request.args.get("page", 1))
    search = request.args.get("q", "").strip()
    per_page = 20

    query = {}
    if search:
        query["title"] = {"$regex": search, "$options": "i"}

    def _fetch():
        col = get_col("videos")
        total = col.count_documents(query)
        items = list(
            col.find(query, {"code": 0, "script": 0})
            .sort("created_at", -1)
            .skip((page - 1) * per_page)
            .limit(per_page)
        )
        return items, total

    items, total = _safe_query(_fetch, ([], 0))
    total_pages = max(1, (total + per_page - 1) // per_page)

    return render_template(
        "videos.html",
        videos=items,
        page=page,
        total_pages=total_pages,
        total=total,
        search=search,
    )


# ══════════════════════════════════════════════════════════════
#  ROUTE: Analytics
# ══════════════════════════════════════════════════════════════

@app.route("/analytics")
def analytics():
    """Analytics charts page."""
    get_col = _get_db()

    def _fetch_analytics():
        col = get_col("videos")

        # Content type distribution
        ct_pipeline = [
            {"$group": {"_id": "$content_type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        content_types = {
            doc["_id"] or "unknown": doc["count"]
            for doc in col.aggregate(ct_pipeline)
        }

        # Weekly video counts (last 8 weeks)
        eight_weeks_ago = datetime.now(timezone.utc) - timedelta(weeks=8)
        weekly_pipeline = [
            {"$match": {"created_at": {"$gte": eight_weeks_ago}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-W%U", "date": "$created_at"}},
                "count": {"$sum": 1},
            }},
            {"$sort": {"_id": 1}},
        ]
        weekly = {
            doc["_id"]: doc["count"]
            for doc in col.aggregate(weekly_pipeline)
        }

        # Language distribution
        lang_pipeline = [
            {"$group": {"_id": "$language", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        languages = {
            doc["_id"] or "unknown": doc["count"]
            for doc in col.aggregate(lang_pipeline)
        }

        return {
            "content_types": content_types,
            "weekly_counts": weekly,
            "languages": languages,
        }

    data = _safe_query(_fetch_analytics, {
        "content_types": {},
        "weekly_counts": {},
        "languages": {},
    })
    return render_template("analytics.html", data=data)


# ══════════════════════════════════════════════════════════════
#  ROUTE: Health
# ══════════════════════════════════════════════════════════════

@app.route("/health")
def health():
    """System health page."""
    health_data = _safe_query(_run_health_checks, {})
    return render_template("health.html", health=health_data)


def _run_health_checks() -> dict:
    """Run health checks and return results."""
    from src.health_monitor import run_all_checks
    return run_all_checks()


# ══════════════════════════════════════════════════════════════
#  API — JSON endpoint
# ══════════════════════════════════════════════════════════════

@app.route("/api/stats")
def api_stats():
    """JSON API for overview statistics."""
    get_col = _get_db()
    stats = _safe_query(lambda: _get_overview_stats(get_col), {})
    # Serialize datetime for JSON
    if stats.get("last_run"):
        stats["last_run"] = stats["last_run"].isoformat()
    return jsonify(stats)


# ══════════════════════════════════════════════════════════════
#  ENTRYPOINT
# ══════════════════════════════════════════════════════════════

def run_dashboard(port: int | None = None, debug: bool = False):
    """Start the Flask dashboard server."""
    from src import config
    port = port or config.DASHBOARD_PORT
    logger.info(f"Starting dashboard on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("DASHBOARD_PORT", "5050"))
    run_dashboard(port=port, debug=True)
