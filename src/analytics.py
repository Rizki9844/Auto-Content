"""
Analytics Dashboard — Phase 4.3.

Queries MongoDB ``history`` and ``scheduled`` collections and generates
a structured Markdown (or plain-text) performance report.

Report sections:
  1. Summary       — total, success rate, avg quality score
  2. Weekly trend  — videos published per week (last 8 weeks)
  3. Monthly trend — videos published per month (last 6 months)
  4. Language dist — bar chart (by character width)
  5. Content types — bar chart
  6. Latency trend — avg render / upload / total ms (last 20 runs)
  7. Queue status  — pending / done today / failed (from scheduler)

Usage:
    python -m src.main --analytics              # print to stdout
    python -m src.main --analytics --save       # write to output/report_YYYYMMDD.md
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Bar chart settings ─────────────────────────────────────────
_BAR_WIDTH = 30        # max bar length in characters
_BAR_CHAR  = "█"


# ══════════════════════════════════════════════════════════════
#  Internal helpers
# ══════════════════════════════════════════════════════════════

def _get_history_col():
    """Reuse the same MongoClient + collection as db.py."""
    from src.db import _get_collection
    return _get_collection()


def _bar(value: int | float, max_value: int | float, width: int = _BAR_WIDTH) -> str:
    """Return a text bar proportional to value/max_value."""
    if max_value <= 0:
        return ""
    filled = int(round(width * value / max_value))
    return _BAR_CHAR * filled


def _week_label(dt: datetime) -> str:
    """ISO week label: '2026-W09'."""
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _month_label(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


# ══════════════════════════════════════════════════════════════
#  Data queries
# ══════════════════════════════════════════════════════════════

def get_summary() -> dict[str, Any]:
    """
    High-level counts.

    Returns:
        total, success, failed, skipped, success_rate (0–100),
        avg_quality_score, avg_duration_seconds
    """
    try:
        col = _get_history_col()
        total   = col.count_documents({})
        success = col.count_documents({"status": "success"})
        failed  = col.count_documents({"status": "failed"})

        # Average quality score (only docs that have the field)
        pipeline_q = [
            {"$match": {"quality_score": {"$exists": True, "$gt": 0}}},
            {"$group": {"_id": None,
                        "avg_quality": {"$avg": "$quality_score"},
                        "avg_duration": {"$avg": "$duration_seconds"}}},
        ]
        agg = list(col.aggregate(pipeline_q))
        avg_quality  = round(agg[0]["avg_quality"],  1) if agg else 0.0
        avg_duration = round(agg[0]["avg_duration"], 1) if agg else 0.0

        return {
            "total":              total,
            "success":            success,
            "failed":             failed,
            "skipped":            total - success - failed,
            "success_rate":       round(success / total * 100, 1) if total else 0.0,
            "avg_quality_score":  avg_quality,
            "avg_duration_seconds": avg_duration,
        }
    except Exception as exc:
        logger.warning(f"get_summary error: {exc}")
        return {"total": 0, "success": 0, "failed": 0, "skipped": 0,
                "success_rate": 0.0, "avg_quality_score": 0.0, "avg_duration_seconds": 0.0}


def get_weekly_counts(weeks: int = 8) -> dict[str, int]:
    """
    Videos published per ISO week, newest first.

    Returns ordered dict ``{'2026-W09': 5, '2026-W08': 3, ...}``.
    """
    since = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    try:
        col = _get_history_col()
        docs = col.find(
            {"status": "success", "created_at": {"$gte": since}},
            {"created_at": 1, "_id": 0},
        )
        counts: dict[str, int] = defaultdict(int)
        for doc in docs:
            ts = doc.get("created_at")
            if ts:
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                counts[_week_label(ts)] += 1

        # Build ordered result (oldest → newest)
        all_weeks = [
            _week_label(datetime.now(timezone.utc) - timedelta(weeks=i))
            for i in range(weeks - 1, -1, -1)
        ]
        return {w: counts.get(w, 0) for w in all_weeks}
    except Exception as exc:
        logger.warning(f"get_weekly_counts error: {exc}")
        return {}


def get_monthly_counts(months: int = 6) -> dict[str, int]:
    """
    Videos published per calendar month, oldest → newest.

    Returns ``{'2025-10': 12, '2025-11': 18, ...}``.
    """
    now = datetime.now(timezone.utc)
    try:
        col = _get_history_col()
        pipeline = [
            {"$match": {"status": "success"}},
            {"$group": {
                "_id": {
                    "year":  {"$year": "$created_at"},
                    "month": {"$month": "$created_at"},
                },
                "count": {"$sum": 1},
            }},
            {"$sort": {"_id.year": 1, "_id.month": 1}},
        ]
        raw = {
            f"{d['_id']['year']}-{d['_id']['month']:02d}": d["count"]
            for d in col.aggregate(pipeline)
        }

        # Build ordered result for last N months
        result: dict[str, int] = {}
        for i in range(months - 1, -1, -1):
            # Go back i months
            mo = now.month - i
            yr = now.year
            while mo <= 0:
                mo += 12
                yr -= 1
            label = f"{yr}-{mo:02d}"
            result[label] = raw.get(label, 0)
        return result
    except Exception as exc:
        logger.warning(f"get_monthly_counts error: {exc}")
        return {}


def get_language_distribution() -> dict[str, int]:
    """Language → count for all successful videos, sorted descending."""
    try:
        col = _get_history_col()
        pipeline = [
            {"$match": {"status": "success", "language": {"$exists": True, "$ne": ""}}},
            {"$group": {"_id": "$language", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        return {doc["_id"]: doc["count"] for doc in col.aggregate(pipeline)}
    except Exception as exc:
        logger.warning(f"get_language_distribution error: {exc}")
        return {}


def get_content_type_distribution() -> dict[str, int]:
    """Content type → count for all successful videos, sorted descending."""
    try:
        col = _get_history_col()
        pipeline = [
            {"$match": {"status": "success", "content_type": {"$exists": True, "$ne": ""}}},
            {"$group": {"_id": "$content_type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        return {doc["_id"]: doc["count"] for doc in col.aggregate(pipeline)}
    except Exception as exc:
        logger.warning(f"get_content_type_distribution error: {exc}")
        return {}


def get_latency_trend(limit: int = 20) -> dict[str, float]:
    """
    Average pipeline latency metrics (ms) from the most recent ``limit``
    successful runs that have a ``metrics`` field.

    Returns ``{'gemini_ms': ..., 'tts_ms': ..., 'render_ms': ...,
                'upload_ms': ..., 'total_ms': ...}``.
    """
    try:
        col = _get_history_col()
        docs = list(
            col.find(
                {"status": "success", "metrics": {"$exists": True}},
                {"metrics": 1, "_id": 0},
            )
            .sort("created_at", -1)
            .limit(limit)
        )
        if not docs:
            return {}

        keys = {
            "gemini_ms":  "gemini_latency_ms",
            "tts_ms":     "tts_latency_ms",
            "render_ms":  "render_latency_ms",
            "upload_ms":  "upload_latency_ms",
            "total_ms":   "total_latency_ms",
        }
        sums: dict[str, float] = defaultdict(float)
        cnts: dict[str, int]   = defaultdict(int)

        for doc in docs:
            m = doc.get("metrics", {}) or {}
            for out_key, in_key in keys.items():
                val = m.get(in_key)
                if val is not None:
                    sums[out_key] += float(val)
                    cnts[out_key] += 1

        return {
            k: round(sums[k] / cnts[k], 0)
            for k in keys
            if cnts[k] > 0
        }
    except Exception as exc:
        logger.warning(f"get_latency_trend error: {exc}")
        return {}


def get_queue_status() -> dict[str, int]:
    """
    Current schedule queue status from the ``scheduled`` collection.
    Returns empty dict if scheduler not available.
    """
    try:
        from src.scheduler import get_schedule_summary
        return get_schedule_summary()
    except Exception as exc:
        logger.warning(f"get_queue_status error: {exc}")
        return {}


# ══════════════════════════════════════════════════════════════
#  Report generation
# ══════════════════════════════════════════════════════════════

def generate_report() -> str:
    """
    Build and return a full Markdown analytics report.
    All MongoDB calls are made here; each section degrades gracefully
    if data is unavailable.
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []

    def h1(text: str) -> None:
        lines.append(f"# {text}")

    def h2(text: str) -> None:
        lines.append(f"\n## {text}")

    def h3(text: str) -> None:
        lines.append(f"\n### {text}")

    def row(*cols: str) -> None:
        lines.append("| " + " | ".join(str(c) for c in cols) + " |")

    def sep(*widths: int) -> None:
        lines.append("| " + " | ".join(":---" if w else "---:" for w in widths) + " |")

    # ── Header ────────────────────────────────────────────────
    h1("📊 Auto-Content Pipeline — Analytics Report")
    lines.append(f"\n> Generated: **{now_str}**\n")

    # ── 1. Summary ────────────────────────────────────────────
    h2("1. Summary")
    s = get_summary()
    row("Metric", "Value")
    sep(1, 0)
    row("Total videos", s["total"])
    row("✅ Successful", s["success"])
    row("❌ Failed", s["failed"])
    row("Success rate", f"{s['success_rate']}%")
    row("Avg quality score", f"{s['avg_quality_score']}/100")
    row("Avg video duration", f"{s['avg_duration_seconds']}s")

    # ── 2. Weekly trend ───────────────────────────────────────
    h2("2. Weekly Output (last 8 weeks)")
    weekly = get_weekly_counts(8)
    if weekly:
        max_w = max(weekly.values()) if weekly.values() else 1
        row("Week", "Count", "Bar")
        sep(1, 0, 1)
        for week, cnt in weekly.items():
            row(week, cnt, f"`{_bar(cnt, max_w)}`" if cnt else "")
    else:
        lines.append("_No data_")

    # ── 3. Monthly trend ──────────────────────────────────────
    h2("3. Monthly Output (last 6 months)")
    monthly = get_monthly_counts(6)
    if monthly:
        max_m = max(monthly.values()) if monthly.values() else 1
        row("Month", "Count", "Bar")
        sep(1, 0, 1)
        for month, cnt in monthly.items():
            row(month, cnt, f"`{_bar(cnt, max_m)}`" if cnt else "")
    else:
        lines.append("_No data_")

    # ── 4. Language distribution ──────────────────────────────
    h2("4. Language Distribution")
    lang_dist = get_language_distribution()
    if lang_dist:
        max_l = max(lang_dist.values())
        total_vids = sum(lang_dist.values())
        row("Language", "Count", "%", "Bar")
        sep(1, 0, 0, 1)
        for lang, cnt in lang_dist.items():
            pct = round(cnt / total_vids * 100, 1) if total_vids else 0
            row(lang, cnt, f"{pct}%", f"`{_bar(cnt, max_l)}`")
    else:
        lines.append("_No data_")

    # ── 5. Content type distribution ──────────────────────────
    h2("5. Content Type Distribution")
    type_dist = get_content_type_distribution()
    if type_dist:
        max_t = max(type_dist.values())
        total_t = sum(type_dist.values())
        row("Type", "Count", "%", "Bar")
        sep(1, 0, 0, 1)
        for ctype, cnt in type_dist.items():
            pct = round(cnt / total_t * 100, 1) if total_t else 0
            row(ctype, cnt, f"{pct}%", f"`{_bar(cnt, max_t)}`")
    else:
        lines.append("_No data_")

    # ── 6. Pipeline latency ───────────────────────────────────
    h2("6. Average Pipeline Latency")
    latency = get_latency_trend(20)
    if latency:
        labels = {
            "gemini_ms":  "Gemini generation",
            "tts_ms":     "TTS (edge-tts)",
            "render_ms":  "Video render",
            "upload_ms":  "Upload",
            "total_ms":   "**Total**",
        }
        row("Step", "Avg (ms)", "Avg (s)")
        sep(1, 0, 0)
        for key, label in labels.items():
            if key in latency:
                ms = int(latency[key])
                row(label, f"{ms:,}", f"{ms/1000:.1f}")
    else:
        lines.append("_No latency data — `metrics` field may not be populated yet._")

    # ── 7. Schedule queue ─────────────────────────────────────
    h2("7. Schedule Queue")
    q = get_queue_status()
    if q:
        row("Status", "Count")
        sep(1, 0)
        row("Pending (due now)",   q.get("pending_due", 0))
        row("Pending (future)",    q.get("pending_future", 0))
        row("Done today",          q.get("done_today", 0))
        row("Failed (all time)",   q.get("failed_total", 0))
    else:
        lines.append("_Scheduler not available or no queued jobs._")

    lines.append("\n---")
    lines.append("_Report generated by Auto-Content Pipeline analytics module._")

    return "\n".join(lines)


def save_report(output_dir: Path | None = None) -> Path:
    """
    Write the Markdown report to disk.

    Args:
        output_dir: Directory to write into. Defaults to ``output/``.

    Returns:
        Path to the written file.
    """
    from src import config
    if output_dir is None:
        output_dir = config.OUTPUT_DIR

    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    path = output_dir / f"report_{date_str}.md"
    report = generate_report()
    path.write_text(report, encoding="utf-8")
    logger.info(f"Analytics report saved: {path}")
    return path
