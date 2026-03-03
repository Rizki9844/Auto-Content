"""
Multi-channel YouTube support — Phase 9.3.

Allows uploading the same (or different) content to multiple YouTube channels.
Channels are configured via YOUTUBE_CHANNELS env var as a JSON list:

    YOUTUBE_CHANNELS='[
        {"name":"en","client_id":"...","client_secret":"...","refresh_token":"..."},
        {"name":"id","client_id":"...","client_secret":"...","refresh_token":"..."}
    ]'

If YOUTUBE_CHANNELS is empty, falls back to the single-channel config
(YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN).

Usage:
    from src.multi_channel import get_channels, upload_to_all_channels
    channels = get_channels()
    results = upload_to_all_channels(video_path, title, description, tags)
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

from src import config

logger = logging.getLogger(__name__)


@dataclass
class ChannelConfig:
    """Configuration for a single YouTube channel."""
    name: str
    client_id: str
    client_secret: str
    refresh_token: str
    channel_name: str = ""  # display name for branding

    @property
    def is_valid(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)


@dataclass
class ChannelUploadResult:
    """Result of uploading to a single channel."""
    channel_name: str
    success: bool
    video_id: str = ""
    url: str = ""
    error: str = ""


def get_channels() -> list[ChannelConfig]:
    """
    Parse YOUTUBE_CHANNELS JSON config into a list of ChannelConfig objects.

    If YOUTUBE_CHANNELS is empty/unset, returns a single-channel config from
    the legacy YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN.

    Returns:
        List of ChannelConfig objects (may be empty if nothing is configured).
    """
    raw = config.YOUTUBE_CHANNELS.strip()

    if raw:
        try:
            channels_data = json.loads(raw)
            if not isinstance(channels_data, list):
                logger.error("YOUTUBE_CHANNELS must be a JSON array")
                return []
            channels = []
            for ch in channels_data:
                channels.append(ChannelConfig(
                    name=ch.get("name", "unnamed"),
                    client_id=ch.get("client_id", ""),
                    client_secret=ch.get("client_secret", ""),
                    refresh_token=ch.get("refresh_token", ""),
                    channel_name=ch.get("channel_name", ""),
                ))
            return [c for c in channels if c.is_valid]
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse YOUTUBE_CHANNELS JSON: {e}")
            return []

    # Fallback: single channel from legacy config
    if config.YOUTUBE_CLIENT_ID and config.YOUTUBE_REFRESH_TOKEN:
        return [ChannelConfig(
            name="default",
            client_id=config.YOUTUBE_CLIENT_ID,
            client_secret=config.YOUTUBE_CLIENT_SECRET,
            refresh_token=config.YOUTUBE_REFRESH_TOKEN,
            channel_name=config.CHANNEL_NAME,
        )]

    return []


def _build_service_for_channel(channel: ChannelConfig):
    """Build an authenticated YouTube API service for a specific channel."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=channel.refresh_token,
        client_id=channel.client_id,
        client_secret=channel.client_secret,
        token_uri="https://oauth2.googleapis.com/token",
    )

    for attempt in range(1, 4):
        try:
            creds.refresh(Request())
            logger.info(f"YouTube token refreshed for channel '{channel.name}'")
            break
        except Exception as e:
            if attempt == 3:
                raise
            logger.warning(
                f"Token refresh failed for '{channel.name}' "
                f"(attempt {attempt}/3): {e}"
            )
            time.sleep(2 * attempt)

    return build("youtube", "v3", credentials=creds)


def upload_to_channel(
    channel: ChannelConfig,
    video_path: str,
    title: str,
    description: str,
    tags: list[str] | None = None,
    category_id: str = "28",
    privacy: str = "public",
) -> ChannelUploadResult:
    """
    Upload a video to a specific YouTube channel.

    Returns:
        ChannelUploadResult with success/failure details.
    """
    try:
        from googleapiclient.http import MediaFileUpload

        service = _build_service_for_channel(channel)

        safe_title = title[:100]
        if "#Shorts" not in safe_title and "#shorts" not in safe_title:
            if len(safe_title) + 8 <= 100:
                safe_title += " #Shorts"

        body = {
            "snippet": {
                "title": safe_title,
                "description": description[:5000],
                "tags": (tags or [])[:30],
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024 * 5,
        )

        request = service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        logger.info(f"Uploading to channel '{channel.name}': '{safe_title}'")

        response = None
        retries = 0
        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    pct = int(status.progress() * 100)
                    logger.info(f"  [{channel.name}] Upload progress: {pct}%")
            except Exception as e:
                retries += 1
                if retries > 3:
                    raise RuntimeError(
                        f"Upload to '{channel.name}' failed after 3 retries: {e}"
                    ) from e
                delay = 5 * (2 ** (retries - 1))
                logger.warning(f"  [{channel.name}] Retry {retries}/3: {e}")
                time.sleep(delay)

        video_id = response.get("id", "unknown")
        url = f"https://youtube.com/shorts/{video_id}"
        logger.info(f"  [{channel.name}] Upload complete: {url}")

        return ChannelUploadResult(
            channel_name=channel.name,
            success=True,
            video_id=video_id,
            url=url,
        )

    except Exception as exc:
        logger.error(f"Upload to channel '{channel.name}' failed: {exc}")
        return ChannelUploadResult(
            channel_name=channel.name,
            success=False,
            error=str(exc)[:500],
        )


def upload_to_all_channels(
    video_path: str,
    title: str,
    description: str,
    tags: list[str] | None = None,
    channels: list[ChannelConfig] | None = None,
) -> list[ChannelUploadResult]:
    """
    Upload a video to all configured YouTube channels.

    Args:
        video_path:  Path to the MP4 file.
        title:       Video title.
        description: Video description.
        tags:        Optional list of tags.
        channels:    Explicit channel list. If None, uses get_channels().

    Returns:
        List of ChannelUploadResult objects, one per channel.
    """
    if channels is None:
        channels = get_channels()

    if not channels:
        logger.warning("No YouTube channels configured — skipping multi-channel upload")
        return []

    results = []
    for ch in channels:
        result = upload_to_channel(ch, video_path, title, description, tags)
        results.append(result)

    successful = sum(1 for r in results if r.success)
    logger.info(f"Multi-channel upload complete: {successful}/{len(results)} succeeded")

    return results
