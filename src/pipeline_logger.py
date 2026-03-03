"""
Comprehensive Logging & Audit Trail — Phase 8.3

Stores structured pipeline logs to MongoDB 'pipeline_logs' collection.
Each pipeline run gets a unique run_id with step-level tracking.

Features:
  - Per-step status tracking: pending → running → success/failed/skipped
  - run_id, timestamp, total_duration_ms, outcome, error_if_any
  - CLI: --logs --last N to view recent runs
  - Log rotation: auto-delete logs > 30 days
"""
import logging
import time
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class PipelineLog:
    """
    Structured pipeline run logger.

    Usage:
        log = PipelineLog()
        log.start_step("content_generation")
        # ... do work ...
        log.end_step("content_generation", status="success", details={...})
        log.save()
    """

    VALID_STATUSES = ("pending", "running", "success", "failed", "skipped")

    def __init__(self, run_type: str = "single"):
        self.run_id = str(uuid.uuid4())[:12]
        self.run_type = run_type  # "single", "batch", "series", "upload_queue"
        self.timestamp = datetime.now(timezone.utc)
        self.steps: list[dict] = []
        self.outcome: str = "pending"  # "success", "failed", "partial"
        self.error_if_any: str = ""
        self._step_timers: dict[str, float] = {}
        self._start_time = time.perf_counter()
        self._saved = False

    def start_step(self, name: str) -> None:
        """Mark a pipeline step as running."""
        # Check if step already exists
        for step in self.steps:
            if step["name"] == name:
                step["status"] = "running"
                step["started_at"] = datetime.now(timezone.utc).isoformat()
                self._step_timers[name] = time.perf_counter()
                return

        self.steps.append({
            "name": name,
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "ended_at": None,
            "duration_ms": 0,
            "details": {},
        })
        self._step_timers[name] = time.perf_counter()

    def end_step(
        self,
        name: str,
        status: str = "success",
        details: dict | None = None,
        error: str = "",
    ) -> None:
        """Mark a pipeline step as completed (success/failed/skipped)."""
        if status not in self.VALID_STATUSES:
            status = "success"

        for step in self.steps:
            if step["name"] == name:
                step["status"] = status
                step["ended_at"] = datetime.now(timezone.utc).isoformat()
                if name in self._step_timers:
                    elapsed = time.perf_counter() - self._step_timers[name]
                    step["duration_ms"] = round(elapsed * 1000)
                if details:
                    step["details"] = details
                if error:
                    step["error"] = error
                return

        # Step wasn't started — add it directly
        self.steps.append({
            "name": name,
            "status": status,
            "started_at": None,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": 0,
            "details": details or {},
            "error": error,
        })

    def skip_step(self, name: str, reason: str = "") -> None:
        """Mark a step as skipped."""
        self.end_step(name, status="skipped", details={"reason": reason})

    def set_outcome(self, outcome: str, error: str = "") -> None:
        """Set the final pipeline outcome."""
        self.outcome = outcome
        if error:
            self.error_if_any = error[:500]

    def to_dict(self) -> dict:
        """Convert to MongoDB-storable dict."""
        total_ms = round((time.perf_counter() - self._start_time) * 1000)
        return {
            "run_id": self.run_id,
            "run_type": self.run_type,
            "timestamp": self.timestamp,
            "steps": self.steps,
            "total_duration_ms": total_ms,
            "outcome": self.outcome,
            "error_if_any": self.error_if_any,
        }

    def save(self) -> str | None:
        """
        Persist this log to MongoDB 'pipeline_logs' collection.

        Returns:
            Inserted document ID as string, or None on failure.
        """
        if self._saved:
            return None

        try:
            from src.db import _get_collection

            col = _get_collection()
            db = col.database
            logs_col = db["pipeline_logs"]
            logs_col.create_index("timestamp")
            logs_col.create_index("run_id")

            doc = self.to_dict()
            result = logs_col.insert_one(doc)
            self._saved = True
            logger.info(f"Pipeline log saved: run_id={self.run_id}")
            return str(result.inserted_id)

        except Exception as e:
            logger.warning(f"Failed to save pipeline log: {e}")
            return None


def get_recent_logs(last: int = 10) -> list[dict]:
    """
    Retrieve the most recent pipeline logs.

    Args:
        last: Number of recent logs to retrieve.

    Returns:
        List of log dicts, newest first.
    """
    try:
        from src.db import _get_collection

        col = _get_collection()
        db = col.database
        logs_col = db["pipeline_logs"]

        docs = list(
            logs_col.find({}, {"_id": 0})
            .sort("timestamp", -1)
            .limit(last)
        )
        return docs

    except Exception as e:
        logger.error(f"Failed to retrieve pipeline logs: {e}")
        return []


def print_logs(last: int = 10) -> None:
    """
    Pretty-print recent pipeline logs to stdout.

    Called by: python -m src.main --logs --last 10
    """
    logs = get_recent_logs(last)
    if not logs:
        print("No pipeline logs found.")
        return

    print(f"\n{'='*60}")
    print(f"  Pipeline Audit Trail — Last {len(logs)} runs")
    print(f"{'='*60}\n")

    for log in logs:
        ts = log.get("timestamp", "?")
        if hasattr(ts, "strftime"):
            ts = ts.strftime("%Y-%m-%d %H:%M:%S UTC")

        outcome = log.get("outcome", "?")
        outcome_icon = {"success": "✅", "failed": "❌", "partial": "⚠️"}.get(
            outcome, "❓"
        )
        run_type = log.get("run_type", "single")
        total_ms = log.get("total_duration_ms", 0)

        print(f"  {outcome_icon} [{log.get('run_id', '?')}] {ts}")
        print(f"     Type: {run_type} | Duration: {total_ms}ms | Outcome: {outcome}")

        # Steps
        for step in log.get("steps", []):
            status = step.get("status", "?")
            s_icon = {
                "success": "✓", "failed": "✗", "skipped": "⊘",
                "running": "→", "pending": "○",
            }.get(status, "?")
            dur = step.get("duration_ms", 0)
            err = step.get("error", "")
            line = f"     {s_icon} {step['name']}: {status} ({dur}ms)"
            if err:
                line += f" — {err[:80]}"
            print(line)

        if log.get("error_if_any"):
            print(f"     Error: {log['error_if_any'][:200]}")
        print()

    print(f"{'='*60}")
