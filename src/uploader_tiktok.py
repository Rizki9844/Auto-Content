"""
TikTok video upload module.

Uses the TikTok Content Posting API (v2) — requires a registered app on
TikTok for Developers with ``video.upload`` scope and a valid access token.

Setup:
    1. Register at https://developers.tiktok.com/
    2. Create an app with "Content Posting API" permission
    3. Obtain an OAuth access token (server-to-server or user flow)
    4. Set environment variables:
       - TIKTOK_ACCESS_TOKEN

Docs: https://developers.tiktok.com/doc/content-posting-api-get-started/
"""
from __future__ import annotations

import json
import logging
import os
import time

import requests

from src import config
from src.uploader_base import UploaderBase, UploadResult, register_uploader

logger = logging.getLogger(__name__)

_BASE_URL = "https://open.tiktokapis.com/v2"
_UPLOAD_TIMEOUT = 300  # seconds
_MAX_RETRIES = 3
_RETRY_DELAY = 5


def _get_token() -> str:
    return config.TIKTOK_ACCESS_TOKEN


def _init_upload(token: str, file_size: int) -> dict:
    """
    Step 1 — Request a file upload URL from TikTok.
    Returns ``{"upload_url": "...", "publish_id": "..."}``
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    body = {
        "post_info": {
            "title": "",  # set later
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_duet": False,
            "disable_stitch": False,
            "disable_comment": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": file_size,  # single chunk for shorts (< 50 MB)
            "total_chunk_count": 1,
        },
    }

    resp = requests.post(
        f"{_BASE_URL}/post/publish/inbox/video/init/",
        headers=headers,
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("error", {}).get("code") != "ok":
        raise RuntimeError(f"TikTok init failed: {json.dumps(data.get('error', {}))}")

    return {
        "upload_url": data["data"]["upload_url"],
        "publish_id": data["data"]["publish_id"],
    }


def _upload_video_chunk(upload_url: str, video_path: str, file_size: int) -> None:
    """Step 2 — Upload the video binary to the pre-signed URL."""
    headers = {
        "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
        "Content-Type": "video/mp4",
    }
    with open(video_path, "rb") as f:
        resp = requests.put(
            upload_url,
            headers=headers,
            data=f,
            timeout=_UPLOAD_TIMEOUT,
        )
    resp.raise_for_status()


def _check_publish_status(token: str, publish_id: str) -> dict:
    """Step 3 — Poll publish status until complete or failed."""
    headers = {"Authorization": f"Bearer {token}"}
    params = {"publish_id": publish_id}

    for attempt in range(1, 13):  # poll up to ~60 seconds
        resp = requests.get(
            f"{_BASE_URL}/post/publish/status/fetch/",
            headers=headers,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        status = data.get("status", "PROCESSING_DOWNLOAD")

        if status == "PUBLISH_COMPLETE":
            return {"video_id": data.get("publicaly_available_post_id", [""])[0]}
        if status.startswith("FAILED"):
            raise RuntimeError(f"TikTok publish failed: {data.get('fail_reason', 'unknown')}")

        time.sleep(5)

    raise RuntimeError("TikTok publish timed out after 60 seconds")


def upload_to_tiktok(
    video_path: str,
    title: str,
    description: str,
    tags: list[str] | None = None,
) -> str | None:
    """
    Upload a video to TikTok using the Content Posting API.

    Returns the TikTok video ID on success, None if skipped.
    """
    token = _get_token()
    if not token:
        logger.warning("TikTok access token not configured — skipping upload")
        return None

    file_size = os.path.getsize(video_path)
    logger.info(f"Uploading to TikTok: '{title}' ({file_size / 1024:.0f} KB)")

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            init_data = _init_upload(token, file_size)
            _upload_video_chunk(init_data["upload_url"], video_path, file_size)
            result = _check_publish_status(token, init_data["publish_id"])
            video_id = result.get("video_id", "")
            logger.info(f"TikTok upload complete: {video_id}")
            return video_id
        except Exception as exc:
            if attempt == _MAX_RETRIES:
                raise
            delay = _RETRY_DELAY * (2 ** (attempt - 1))
            logger.warning(
                f"TikTok upload error (attempt {attempt}/{_MAX_RETRIES}): {exc} "
                f"— retrying in {delay}s"
            )
            time.sleep(delay)

    return None


# ──────────────────────────────────────────────────────────────
#  Adapter class for unified uploader interface
# ──────────────────────────────────────────────────────────────
@register_uploader
class TikTokUploader(UploaderBase):
    """TikTok uploader using the Content Posting API v2."""

    @property
    def name(self) -> str:
        return "tiktok"

    def is_configured(self) -> bool:
        return bool(config.TIKTOK_ACCESS_TOKEN)

    def upload(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: list[str] | None = None,
    ) -> UploadResult:
        try:
            video_id = upload_to_tiktok(
                video_path=video_path,
                title=title,
                description=description,
                tags=tags,
            )
            if video_id:
                return UploadResult(
                    platform="tiktok",
                    success=True,
                    video_id=video_id,
                    url=f"https://www.tiktok.com/@/video/{video_id}",
                )
            return UploadResult(
                platform="tiktok",
                success=False,
                error="Upload returned None (token missing or skipped)",
            )
        except Exception as exc:
            return UploadResult(
                platform="tiktok",
                success=False,
                error=str(exc)[:500],
            )
