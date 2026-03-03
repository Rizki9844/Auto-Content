"""
YouTube Playlist & Series Management — Phase 7.3.

Auto-organizes uploaded videos into language-based and series-based
YouTube playlists.  Playlist IDs are cached in MongoDB to avoid
redundant API calls.

Requires ``youtube`` or ``youtube.force-ssl`` OAuth scope.

Usage:
    from src.playlist_manager import auto_manage_playlist

    # After upload, pass video_id and content dict:
    playlist_id = auto_manage_playlist(video_id, content)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src import config

logger = logging.getLogger(__name__)

# ── MongoDB cache collection name ───────────────────────────────────────────
PLAYLIST_CACHE_COLLECTION = "playlist_cache"

# ── Playlist title templates ────────────────────────────────────────────────
_LANGUAGE_PLAYLIST_TITLE = "{language} Tips & Tricks — {channel}"
_SERIES_PLAYLIST_TITLE   = "{series_theme} — {channel}"

# ── Playlist description templates ──────────────────────────────────────────
_LANGUAGE_PLAYLIST_DESC = (
    "A curated collection of {language} coding tips, quizzes, and transformations.\n"
    "Subscribe for daily content: {channel_url}"
)
_SERIES_PLAYLIST_DESC = (
    "{series_theme}\n"
    "Part of the auto-generated coding series by {channel}.\n"
    "Subscribe: {channel_url}"
)


# ══════════════════════════════════════════════════════════════════════════════
#  MongoDB cache helpers
# ══════════════════════════════════════════════════════════════════════════════

_cache_col = None


def _get_cache_collection():
    """Return the playlist_cache MongoDB collection (lazy singleton)."""
    global _cache_col
    if _cache_col is not None:
        return _cache_col

    from src.db import _get_collection
    col_handle = _get_collection()
    db = col_handle.database
    _cache_col = db[PLAYLIST_CACHE_COLLECTION]
    _cache_col.create_index("title", unique=True)
    logger.debug("Playlist cache collection ready")
    return _cache_col


def _get_cached_playlist_id(title: str) -> str | None:
    """Look up a playlist ID from the MongoDB cache."""
    try:
        col = _get_cache_collection()
        doc = col.find_one({"title": title})
        if doc:
            return doc.get("playlist_id")
    except Exception as exc:
        logger.debug(f"Playlist cache lookup failed: {exc}")
    return None


def _cache_playlist_id(title: str, playlist_id: str) -> None:
    """Store a playlist ID in the MongoDB cache."""
    try:
        col = _get_cache_collection()
        col.update_one(
            {"title": title},
            {
                "$set": {
                    "playlist_id": playlist_id,
                    "updated_at": datetime.now(timezone.utc),
                },
                "$setOnInsert": {
                    "created_at": datetime.now(timezone.utc),
                },
            },
            upsert=True,
        )
        logger.debug(f"Cached playlist '{title}' → {playlist_id}")
    except Exception as exc:
        logger.debug(f"Playlist cache write failed: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
#  YouTube API helpers
# ══════════════════════════════════════════════════════════════════════════════

def _build_youtube_service():
    """Build authenticated YouTube Data API v3 service."""
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


def get_or_create_playlist(
    title: str,
    description: str = "",
    *,
    service: Any = None,
) -> str | None:
    """
    Find an existing playlist by title, or create a new one.

    Uses a local MongoDB cache to avoid repeated API calls.

    Args:
        title:       Playlist title (exact match).
        description: Description for new playlists.
        service:     Optional pre-built YouTube API service.

    Returns:
        YouTube playlist ID, or None on failure.
    """
    # ── Check cache first ─────────────────────────────────────
    cached = _get_cached_playlist_id(title)
    if cached:
        logger.debug(f"Playlist '{title}' found in cache: {cached}")
        return cached

    try:
        svc = service or _build_youtube_service()

        # ── Search existing playlists ─────────────────────────
        page_token = None
        while True:
            resp = svc.playlists().list(
                part="snippet",
                mine=True,
                maxResults=50,
                pageToken=page_token,
            ).execute()

            for item in resp.get("items", []):
                if item["snippet"]["title"] == title:
                    pid = item["id"]
                    _cache_playlist_id(title, pid)
                    logger.info(f"Found existing playlist '{title}': {pid}")
                    return pid

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        # ── Create new playlist ───────────────────────────────
        create_resp = svc.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": title[:150],
                    "description": (description or f"Auto-managed playlist by {config.CHANNEL_NAME}")[:5000],
                },
                "status": {
                    "privacyStatus": "public",
                },
            },
        ).execute()

        pid = create_resp["id"]
        _cache_playlist_id(title, pid)
        logger.info(f"Created new playlist '{title}': {pid}")
        return pid

    except Exception as exc:
        err_str = str(exc)
        if "403" in err_str or "forbidden" in err_str.lower():
            logger.warning(
                "Playlist management failed (403 Forbidden). "
                "Re-authenticate with 'youtube' scope: "
                "python -m scripts.auth_youtube"
            )
        else:
            logger.warning(f"get_or_create_playlist failed: {exc}")
        return None


def add_to_playlist(
    video_id: str,
    playlist_id: str,
    *,
    service: Any = None,
) -> bool:
    """
    Add a video to a YouTube playlist.

    Args:
        video_id:    YouTube video ID.
        playlist_id: YouTube playlist ID.
        service:     Optional pre-built YouTube API service.

    Returns:
        True if added successfully, False otherwise.
    """
    try:
        svc = service or _build_youtube_service()

        svc.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": video_id,
                    },
                },
            },
        ).execute()

        logger.info(f"Added video {video_id} to playlist {playlist_id}")
        return True

    except Exception as exc:
        err_str = str(exc)
        if "409" in err_str or "Conflict" in err_str:
            logger.debug(f"Video {video_id} already in playlist {playlist_id}")
            return True  # Duplicate is fine
        logger.warning(f"add_to_playlist failed: {exc}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  High-level auto-management
# ══════════════════════════════════════════════════════════════════════════════

def auto_manage_playlist(
    video_id: str,
    content: dict,
    *,
    service: Any = None,
) -> str | None:
    """
    Automatically organize a video into the appropriate playlists.

    Creates/finds playlists based on:
      1. **Language playlist** — e.g., "Python Tips & Tricks — @DevInSeconds"
      2. **Series playlist** — if content belongs to a series (Phase 6.4)

    Args:
        video_id: YouTube video ID.
        content:  Content dict from ``generate_content()``.
        service:  Optional pre-built YouTube API service.

    Returns:
        Primary playlist ID (language-based) on success, None if disabled/failed.
    """
    if config.ENABLE_PLAYLISTS != "1":
        logger.debug("Playlist management disabled (ENABLE_PLAYLISTS != '1')")
        return None

    if not video_id:
        logger.warning("auto_manage_playlist called without video_id")
        return None

    language = content.get("language", "python").capitalize()
    channel = config.CHANNEL_NAME
    channel_url = config.CHANNEL_URL

    svc = service  # Will be built lazily inside get_or_create_playlist

    # ── 1. Language-based playlist ────────────────────────────
    lang_title = _LANGUAGE_PLAYLIST_TITLE.format(
        language=language,
        channel=channel,
    )
    lang_desc = _LANGUAGE_PLAYLIST_DESC.format(
        language=language,
        channel_url=channel_url,
    )

    primary_pid = get_or_create_playlist(lang_title, lang_desc, service=svc)
    if primary_pid:
        add_to_playlist(video_id, primary_pid, service=svc)
    else:
        logger.warning(f"Could not create/find language playlist: {lang_title}")

    # ── 2. Series-based playlist (Phase 6.4 integration) ─────
    series_theme = content.get("series_theme") or content.get("series_id")
    if series_theme:
        series_title = _SERIES_PLAYLIST_TITLE.format(
            series_theme=series_theme,
            channel=channel,
        )
        series_desc = _SERIES_PLAYLIST_DESC.format(
            series_theme=series_theme,
            channel=channel,
            channel_url=channel_url,
        )
        series_pid = get_or_create_playlist(series_title, series_desc, service=svc)
        if series_pid:
            add_to_playlist(video_id, series_pid, service=svc)
            logger.info(f"Video added to series playlist: {series_title}")

    return primary_pid
