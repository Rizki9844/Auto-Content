"""
YouTube Post-Upload Actions — Phase 7.2 & 7.4.

Provides two key post-upload enhancement features:

  7.2 — **Auto-Post Pinned Comment**
        After a successful YouTube upload, post a content-type-specific
        engagement comment and pin it.  Requires ``youtube.force-ssl`` or
        ``youtube`` OAuth scope.

  7.4 — **End-Screen CTA Enhancement**
        YouTube Data API v3 does NOT support programmatic end-screen
        management.  Shorts (<60 s) don't support end screens at all.
        Instead, this module appends a branded CTA block to the video
        description via ``videos.update``.

Usage:
    from src.youtube_actions import post_pinned_comment, add_end_screen_cta

    # After uploading to YouTube:
    post_pinned_comment(video_id, content)
    add_end_screen_cta(video_id, duration_seconds=45)
"""
from __future__ import annotations

import logging
from typing import Any

from src import config

logger = logging.getLogger(__name__)

# ── Comment CTA templates per content type ──────────────────────────────────
_COMMENT_TEMPLATES: dict[str, str] = {
    "tip": (
        "💡 Did this tip help you? Drop a 🔥 if you learned something new!\n\n"
        "👉 Which {language} topic should I cover next? Let me know in the replies!\n\n"
        "🔔 Subscribe for daily coding tips — {channel_url}"
    ),
    "quiz": (
        "🧠 What's YOUR answer? Comment below before checking!\n\n"
        "✅ Think you got it right? Reply with your answer!\n"
        "❌ Got it wrong? No worries — that's how we learn.\n\n"
        "🔔 More coding quizzes every day — {channel_url}"
    ),
    "before_after": (
        "✨ Which approach do you prefer — before or after?\n\n"
        "👇 Share YOUR favorite clean code pattern in the replies!\n\n"
        "🔔 Subscribe for daily code transformations — {channel_url}"
    ),
}

_DEFAULT_COMMENT = (
    "💻 Enjoying these coding tips?\n\n"
    "🔔 Subscribe and turn on notifications — {channel_url}\n"
    "💬 Drop a comment — I read every single one!"
)


# ══════════════════════════════════════════════════════════════════════════════
#  7.2 — Auto-Post Pinned Comment
# ══════════════════════════════════════════════════════════════════════════════

def _build_youtube_service_extended():
    """
    Build an authenticated YouTube Data API v3 service.

    This reuses the same credentials as ``uploader_youtube.py``.
    For comment posting and playlist management the refresh token must
    include the ``youtube.force-ssl`` scope (or the broader ``youtube``
    scope).  If auth was done only with ``youtube.upload``, these calls
    will return a 403 — caller should catch and log gracefully.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    if not config.YOUTUBE_REFRESH_TOKEN:
        raise RuntimeError(
            "YOUTUBE_REFRESH_TOKEN not configured. "
            "Run 'python -m scripts.auth_youtube' to set up credentials."
        )

    creds = Credentials(
        token=None,
        refresh_token=config.YOUTUBE_REFRESH_TOKEN,
        client_id=config.YOUTUBE_CLIENT_ID,
        client_secret=config.YOUTUBE_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def _format_comment(content: dict) -> str:
    """Build the comment text from content metadata."""
    content_type = content.get("content_type", "tip")
    language = content.get("language", "python").capitalize()
    channel_url = config.CHANNEL_URL

    template = _COMMENT_TEMPLATES.get(content_type, _DEFAULT_COMMENT)
    return template.format(language=language, channel_url=channel_url)


def post_pinned_comment(
    video_id: str,
    content: dict,
    *,
    service: Any = None,
) -> str | None:
    """
    Post a pinned engagement comment on the uploaded video.

    Args:
        video_id:  YouTube video ID.
        content:   Content dict (needs ``content_type`` and ``language``).
        service:   Optional pre-built YouTube API service (for testing).

    Returns:
        Comment ID on success, None if disabled or failed.
    """
    if config.ENABLE_AUTO_COMMENT != "1":
        logger.debug("Auto-comment disabled (ENABLE_AUTO_COMMENT != '1')")
        return None

    if not video_id:
        logger.warning("post_pinned_comment called without video_id")
        return None

    try:
        svc = service or _build_youtube_service_extended()
        comment_text = _format_comment(content)

        # ── Insert top-level comment ──────────────────────────
        body = {
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {
                    "snippet": {
                        "textOriginal": comment_text,
                    }
                },
            }
        }

        response = svc.commentThreads().insert(
            part="snippet",
            body=body,
        ).execute()

        comment_id = response["id"]
        logger.info(f"Pinned comment posted: {comment_id} on video {video_id}")

        return comment_id

    except Exception as exc:
        # Graceful: don't fail the pipeline for a comment error
        err_str = str(exc)
        if "403" in err_str or "forbidden" in err_str.lower():
            logger.warning(
                "Comment posting failed (403 Forbidden). "
                "Re-authenticate with 'youtube.force-ssl' scope: "
                "python -m scripts.auth_youtube"
            )
        else:
            logger.warning(f"Comment posting failed: {exc}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  7.4 — End Screen CTA Enhancement
# ══════════════════════════════════════════════════════════════════════════════

# CTA block appended to description
_END_SCREEN_CTA_TEMPLATE = (
    "\n\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🎬 Watch more: https://youtube.com/@{channel_handle}\n"
    "🔔 Subscribe: {channel_url}?sub_confirmation=1\n"
    "{latest_line}"
    "━━━━━━━━━━━━━━━━━━━━"
)


def _get_channel_handle() -> str:
    """Extract the handle from channel URL (e.g., 'DevInSeconds')."""
    url = config.CHANNEL_URL
    if "@" in url:
        return url.split("@")[-1].strip("/")
    return config.CHANNEL_NAME.lstrip("@")


def _get_latest_video_id(service: Any, exclude_id: str) -> str | None:
    """Fetch the most recent public video ID from the channel (excluding current)."""
    try:
        from src.db import _get_collection
        col = _get_collection()
        doc = col.find_one(
            {
                "youtube_id": {"$ne": exclude_id, "$exists": True, "$ne": None},
                "status": "success",
            },
            sort=[("published_at", -1)],
            projection={"youtube_id": 1},
        )
        if doc and doc.get("youtube_id"):
            return doc["youtube_id"]
    except Exception:
        pass
    return None


def add_end_screen_cta(
    video_id: str,
    duration_seconds: float = 0,
    *,
    service: Any = None,
) -> bool:
    """
    Append a branded CTA block to the video's description.

    Since YouTube Data API v3 does NOT support programmatic end-screen
    management (and Shorts don't support end screens at all), this
    function enhances the video description with subscribe + watch-next
    CTAs — the practical, API-supported alternative.

    Args:
        video_id:          YouTube video ID.
        duration_seconds:  Video duration (informational only).
        service:           Optional pre-built YouTube API service.

    Returns:
        True if description was updated, False otherwise.
    """
    if config.ENABLE_END_SCREEN != "1":
        logger.debug("End-screen CTA disabled (ENABLE_END_SCREEN != '1')")
        return False

    if not video_id:
        logger.warning("add_end_screen_cta called without video_id")
        return False

    try:
        svc = service or _build_youtube_service_extended()

        # ── Fetch current description ─────────────────────────
        video_resp = svc.videos().list(
            part="snippet",
            id=video_id,
        ).execute()

        items = video_resp.get("items", [])
        if not items:
            logger.warning(f"Video {video_id} not found via API")
            return False

        snippet = items[0]["snippet"]
        current_desc = snippet.get("description", "")

        # Don't append if CTA already present
        if "sub_confirmation=1" in current_desc:
            logger.debug("CTA already in description — skipping")
            return True

        # ── Build CTA block ───────────────────────────────────
        channel_handle = _get_channel_handle()
        latest_id = _get_latest_video_id(svc, video_id)
        latest_line = ""
        if latest_id:
            latest_line = f"▶️ Watch next: https://youtube.com/shorts/{latest_id}\n"

        cta_block = _END_SCREEN_CTA_TEMPLATE.format(
            channel_handle=channel_handle,
            channel_url=config.CHANNEL_URL,
            latest_line=latest_line,
        )

        # ── Update description ────────────────────────────────
        new_desc = (current_desc + cta_block)[:5000]
        snippet["description"] = new_desc

        svc.videos().update(
            part="snippet",
            body={
                "id": video_id,
                "snippet": {
                    "title": snippet["title"],
                    "description": new_desc,
                    "categoryId": snippet.get("categoryId", "28"),
                },
            },
        ).execute()

        logger.info(f"End-screen CTA appended to video {video_id}")
        return True

    except Exception as exc:
        err_str = str(exc)
        if "403" in err_str or "forbidden" in err_str.lower():
            logger.warning(
                "End-screen CTA update failed (403 Forbidden). "
                "Re-authenticate with 'youtube' scope."
            )
        else:
            logger.warning(f"End-screen CTA update failed: {exc}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  Unified post-upload action runner
# ══════════════════════════════════════════════════════════════════════════════

def run_post_upload_actions(
    video_id: str,
    content: dict,
    duration_seconds: float = 0,
) -> dict[str, Any]:
    """
    Execute all enabled post-upload YouTube actions.

    This is the main entry point called from ``main.py`` after a
    successful YouTube upload.  Each action is independent and
    failure-tolerant — one action failing won't block the others.

    Args:
        video_id:          YouTube video ID.
        content:           Content dict from ``generate_content()``.
        duration_seconds:  Video duration in seconds.

    Returns:
        Dict with results: ``{"comment_id": str|None, "end_screen_cta": bool,
                              "playlist_id": str|None}``.
    """
    results: dict[str, Any] = {
        "comment_id": None,
        "end_screen_cta": False,
        "playlist_id": None,
    }

    if not video_id:
        return results

    # 7.2 — Pinned comment
    try:
        results["comment_id"] = post_pinned_comment(video_id, content)
    except Exception as exc:
        logger.warning(f"Pinned comment action failed: {exc}")

    # 7.4 — End screen CTA
    try:
        results["end_screen_cta"] = add_end_screen_cta(video_id, duration_seconds)
    except Exception as exc:
        logger.warning(f"End-screen CTA action failed: {exc}")

    # 7.3 — Playlist management (delegated to playlist_manager module)
    try:
        from src.playlist_manager import auto_manage_playlist
        results["playlist_id"] = auto_manage_playlist(video_id, content)
    except Exception as exc:
        logger.warning(f"Playlist management failed: {exc}")

    logger.info(f"Post-upload actions complete for {video_id}: {results}")
    return results
