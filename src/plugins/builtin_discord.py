"""
Built-in plugin: Discord Webhook notifications.

Sends rich embeds to a Discord channel whenever the pipeline completes
or encounters an error.

Activate by setting:
    DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

WEBHOOK_URL: str = os.environ.get("DISCORD_WEBHOOK_URL", "")

# ── Color constants (decimal) ─────────────────────────────────
COLOR_SUCCESS = 0x28C840   # green
COLOR_ERROR = 0xFF5F57     # red
COLOR_INFO = 0x58A6FF      # blue


def _post(payload: dict) -> bool:
    """POST JSON to the Discord webhook URL.  Returns True on success."""
    if not WEBHOOK_URL:
        return False
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            WEBHOOK_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 204)
    except Exception:
        logger.exception("Discord webhook post failed")
        return False


# ── Handler: on_pipeline_complete ─────────────────────────────

def handle_pipeline_complete(event: dict[str, Any]) -> bool:
    """Send a success embed when the pipeline finishes."""
    if not WEBHOOK_URL:
        return False

    title = event.get("title", "Untitled")
    language = event.get("language", "")
    youtube_id = event.get("youtube_id")
    upload_results = event.get("upload_results", {})

    platforms = ", ".join(
        f"[{p}]({url})" if (url := upload_results.get(p)) else p
        for p in upload_results
    )

    fields = [
        {"name": "Language", "value": f"`{language}`", "inline": True},
        {"name": "Platforms", "value": platforms or "—", "inline": True},
    ]
    if youtube_id:
        yt_url = f"https://youtube.com/shorts/{youtube_id}"
        fields.append({"name": "YouTube", "value": yt_url, "inline": False})

    payload = {
        "embeds": [{
            "title": f"✅ {title}",
            "color": COLOR_SUCCESS,
            "fields": fields,
            "footer": {"text": "Auto-Content Pipeline"},
        }]
    }
    return _post(payload)


# ── Handler: on_error ─────────────────────────────────────────

def handle_error(event: dict[str, Any]) -> bool:
    """Send an error embed when the pipeline fails."""
    if not WEBHOOK_URL:
        return False

    error_msg = str(event.get("error", "Unknown error"))[:1000]
    error_class = event.get("error_class", "UNKNOWN")

    payload = {
        "embeds": [{
            "title": f"❌ Pipeline Error ({error_class})",
            "description": f"```\n{error_msg}\n```",
            "color": COLOR_ERROR,
            "footer": {"text": "Auto-Content Pipeline"},
        }]
    }
    return _post(payload)


# ── Register with the plugin system ──────────────────────────

def _register() -> None:
    """Wire handlers into the global registry."""
    from src.plugins import registry

    registry.register("on_pipeline_complete", handle_pipeline_complete)
    registry.register("on_error", handle_error)
    logger.debug("Discord webhook plugin registered")


# Auto-register on import (called by discover_builtin)
_register()
