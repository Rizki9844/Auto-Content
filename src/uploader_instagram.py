"""
Instagram Reels upload module.

Uses the Instagram Graph API via a Facebook Page linked to an
Instagram Professional (Business / Creator) account.

Setup:
    1. Create a Facebook App at https://developers.facebook.com/
    2. Link an Instagram Professional account to a Facebook Page
    3. Generate a long-lived Page Access Token with:
       - ``instagram_basic``
       - ``instagram_content_publish``
       - ``pages_read_engagement``
    4. Set environment variables:
       - INSTAGRAM_ACCESS_TOKEN  (long-lived page token)
       - INSTAGRAM_ACCOUNT_ID   (IG Business account ID)

Docs: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing
"""
from __future__ import annotations

import logging
import os
import time

import requests

from src import config
from src.uploader_base import UploaderBase, UploadResult, register_uploader

logger = logging.getLogger(__name__)

_GRAPH_API = "https://graph.facebook.com/v21.0"
_MAX_RETRIES = 3
_RETRY_DELAY = 5
_PUBLISH_POLL_INTERVAL = 5
_PUBLISH_POLL_MAX = 24  # 24 × 5 s ≈ 2 min


def _get_token() -> str:
    return config.INSTAGRAM_ACCESS_TOKEN


def _get_account_id() -> str:
    return config.INSTAGRAM_ACCOUNT_ID


def _create_reel_container(
    account_id: str,
    token: str,
    video_url: str,
    caption: str,
) -> str:
    """
    Step 1 — Create a media container for a Reel.

    The video must be accessible via a public URL.  For local files
    you need a temporary hosting step (e.g. upload to a public bucket
    first).  This function assumes ``video_url`` is already public.
    """
    resp = requests.post(
        f"{_GRAPH_API}/{account_id}/media",
        params={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    container_id = data.get("id")
    if not container_id:
        raise RuntimeError(f"Instagram container creation failed: {data}")

    return container_id


def _wait_for_container(account_id: str, token: str, container_id: str) -> None:
    """Step 2 — Wait for the container to finish processing."""
    for _ in range(_PUBLISH_POLL_MAX):
        resp = requests.get(
            f"{_GRAPH_API}/{container_id}",
            params={
                "fields": "status_code",
                "access_token": token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        status = resp.json().get("status_code", "IN_PROGRESS")

        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError("Instagram container processing failed")

        time.sleep(_PUBLISH_POLL_INTERVAL)

    raise RuntimeError("Instagram container processing timed out")


def _publish_container(account_id: str, token: str, container_id: str) -> str:
    """Step 3 — Publish the processed container as a Reel."""
    resp = requests.post(
        f"{_GRAPH_API}/{account_id}/media_publish",
        params={
            "creation_id": container_id,
            "access_token": token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    media_id = data.get("id", "")
    if not media_id:
        raise RuntimeError(f"Instagram publish failed: {data}")
    return media_id


def upload_to_instagram(
    video_path: str,
    title: str,
    description: str,
    tags: list[str] | None = None,
    video_url: str = "",
) -> str | None:
    """
    Upload a Reel to Instagram via the Graph API.

    ``video_url`` must be a publicly accessible URL of the video.
    If not provided, the upload is skipped (local file hosting
    is the caller's responsibility).

    Returns the Instagram media ID on success, None if skipped.
    """
    token = _get_token()
    account_id = _get_account_id()

    if not token or not account_id:
        logger.warning("Instagram credentials not configured — skipping upload")
        return None

    if not video_url:
        logger.warning(
            "Instagram requires a public video URL. "
            "Local file upload not yet supported — skipping."
        )
        return None

    # Build caption: title + description + hashtags
    hashtag_str = " ".join(tags or [])
    caption = f"{title}\n\n{description}\n\n{hashtag_str}".strip()
    if len(caption) > 2200:
        caption = caption[:2197] + "..."

    file_size = os.path.getsize(video_path) if os.path.exists(video_path) else 0
    logger.info(
        f"Uploading to Instagram Reels: '{title}' "
        f"({file_size / 1024:.0f} KB)"
    )

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            container_id = _create_reel_container(
                account_id, token, video_url, caption,
            )
            _wait_for_container(account_id, token, container_id)
            media_id = _publish_container(account_id, token, container_id)
            logger.info(f"Instagram upload complete: {media_id}")
            return media_id
        except Exception as exc:
            if attempt == _MAX_RETRIES:
                raise
            delay = _RETRY_DELAY * (2 ** (attempt - 1))
            logger.warning(
                f"Instagram upload error (attempt {attempt}/{_MAX_RETRIES}): {exc} "
                f"— retrying in {delay}s"
            )
            time.sleep(delay)

    return None


# ──────────────────────────────────────────────────────────────
#  Adapter class for unified uploader interface
# ──────────────────────────────────────────────────────────────
@register_uploader
class InstagramUploader(UploaderBase):
    """Instagram Reels uploader via Facebook Graph API."""

    @property
    def name(self) -> str:
        return "instagram"

    def is_configured(self) -> bool:
        return bool(config.INSTAGRAM_ACCESS_TOKEN and config.INSTAGRAM_ACCOUNT_ID)

    def upload(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: list[str] | None = None,
    ) -> UploadResult:
        try:
            media_id = upload_to_instagram(
                video_path=video_path,
                title=title,
                description=description,
                tags=tags,
                # TODO: Implement local→public URL hosting (e.g. S3, GCS)
                video_url="",
            )
            if media_id:
                return UploadResult(
                    platform="instagram",
                    success=True,
                    video_id=media_id,
                    url=f"https://www.instagram.com/reel/{media_id}/",
                )
            return UploadResult(
                platform="instagram",
                success=False,
                error="Upload returned None (credentials missing or skipped)",
            )
        except Exception as exc:
            return UploadResult(
                platform="instagram",
                success=False,
                error=str(exc)[:500],
            )
