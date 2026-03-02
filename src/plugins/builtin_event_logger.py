"""
Built-in plugin: JSON Event Logger.

Appends every pipeline event as a JSON-lines entry to
``output/plugin_events.jsonl``.  Useful for debugging, auditing, and
building custom dashboards from the raw event stream.

Always active (no env-var gate) — the file is tiny and append-only.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

EVENTS_FILE: Path = Path(__file__).resolve().parent.parent.parent / "output" / "plugin_events.jsonl"


def _write_event(event_name: str, event: dict[str, Any]) -> bool:
    """Append one JSON line to the events file."""
    try:
        EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_name,
            **event,
        }
        with EVENTS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception:
        logger.exception("Event logger: failed to write %s", event_name)
        return False


# ── Handlers ──────────────────────────────────────────────────

def on_content_generated(event: dict[str, Any]) -> bool:
    return _write_event("on_content_generated", event)


def on_video_rendered(event: dict[str, Any]) -> bool:
    return _write_event("on_video_rendered", event)


def on_uploaded(event: dict[str, Any]) -> bool:
    return _write_event("on_uploaded", event)


def on_pipeline_complete(event: dict[str, Any]) -> bool:
    return _write_event("on_pipeline_complete", event)


def on_error(event: dict[str, Any]) -> bool:
    return _write_event("on_error", event)


# ── Register with the plugin system ──────────────────────────

def _register() -> None:
    from src.plugins import registry

    registry.register("on_content_generated", on_content_generated)
    registry.register("on_video_rendered", on_video_rendered)
    registry.register("on_uploaded", on_uploaded)
    registry.register("on_pipeline_complete", on_pipeline_complete)
    registry.register("on_error", on_error)
    logger.debug("Event logger plugin registered")


_register()
