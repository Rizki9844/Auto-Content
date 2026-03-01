"""
YouTube Shorts upload module.
Authenticates via OAuth2 refresh token and uploads video using YouTube Data API v3.
"""
import logging

from src import config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_API_SERVICE = "youtube"
YOUTUBE_API_VERSION = "v3"


def _build_youtube_service():
    """
    Build an authenticated YouTube API service using refresh token.
    The refresh token is exchanged for a short-lived access token automatically.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    if not config.YOUTUBE_REFRESH_TOKEN:
        raise RuntimeError(
            "YOUTUBE_REFRESH_TOKEN not configured. "
            "Run 'python -m scripts.auth_youtube' locally first."
        )

    creds = Credentials(
        token=None,  # Will be refreshed automatically
        refresh_token=config.YOUTUBE_REFRESH_TOKEN,
        client_id=config.YOUTUBE_CLIENT_ID,
        client_secret=config.YOUTUBE_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )

    # Force token refresh
    creds.refresh(Request())
    logger.info("YouTube OAuth token refreshed successfully")

    return build(YOUTUBE_API_SERVICE, YOUTUBE_API_VERSION, credentials=creds)


def upload_to_youtube(
    video_path: str,
    title: str,
    description: str,
    tags: list[str] | None = None,
    category_id: str = "28",  # Science & Technology
    privacy: str = "public",
) -> str | None:
    """
    Upload a video to YouTube as a Short.

    Args:
        video_path: Path to the MP4 file.
        title: Video title (max 100 chars, should include #Shorts).
        description: Video description (max 5000 chars).
        tags: List of hashtag strings.
        category_id: YouTube category ID ("28" = Science & Technology).
        privacy: "public", "private", or "unlisted".

    Returns:
        YouTube video ID on success, None if upload is skipped.
    """
    from googleapiclient.http import MediaFileUpload

    # ── Pre-flight checks ─────────────────────────────────────
    if not config.YOUTUBE_CLIENT_ID or not config.YOUTUBE_REFRESH_TOKEN:
        logger.warning("YouTube credentials not configured — skipping upload")
        return None

    # ── Build authenticated service ───────────────────────────
    service = _build_youtube_service()

    # ── Prepare metadata ──────────────────────────────────────
    # Ensure #Shorts in title for reliable Shorts classification
    safe_title = title[:100]
    if "#Shorts" not in safe_title and "#shorts" not in safe_title:
        if len(safe_title) + 8 <= 100:
            safe_title += " #Shorts"

    body = {
        "snippet": {
            "title": safe_title,
            "description": description[:5000],
            "tags": (tags or [])[:30],      # YouTube max 30 tags
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    # ── Upload with resumable chunked transfer ────────────────
    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 5,  # 5 MB chunks
    )

    request = service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    logger.info(f"Uploading to YouTube: '{safe_title}'")

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            logger.info(f"Upload progress: {pct}%")

    video_id = response.get("id", "unknown")
    logger.info(f"Upload complete! https://youtube.com/shorts/{video_id}")

    return video_id
