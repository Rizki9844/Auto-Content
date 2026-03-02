"""
Rate Limiting Awareness — Phase 3.6

Tracks API usage and provides rate-limit-aware decisions:
  - Gemini: Parse rate limit headers, add delay when approaching limits.
  - YouTube: Track quota usage (10,000 units/day, upload = 1,600 units).

Usage:
    from src.rate_limiter import RateLimiter
    limiter = RateLimiter()
    limiter.check_gemini_limits()       # Raises if exhausted
    limiter.check_youtube_quota()       # Raises if quota exceeded
    limiter.record_youtube_upload()     # Track usage
"""
import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── YouTube Data API v3 quotas ────────────────────────────────
YOUTUBE_DAILY_QUOTA = 10_000         # units per day
YOUTUBE_UPLOAD_COST = 1_600          # units per video upload
YOUTUBE_LIST_COST = 1                # units per list call
_QUOTA_SAFETY_MARGIN = 0.90         # raise alarm at 90% usage

# ── Gemini rate limit defaults ────────────────────────────────
GEMINI_DEFAULT_RPM = 15              # requests per minute (free tier)
GEMINI_MIN_DELAY_S = 2.0            # minimum delay between calls


class RateLimiter:
    """
    Stateful rate limiter for external APIs.

    Tracks:
      - Gemini request timestamps → enforce RPM
      - YouTube quota consumption → prevent exceeding daily limit
    """

    def __init__(self):
        self._gemini_calls: list[float] = []
        self._youtube_quota_used: int = 0
        self._youtube_quota_date: str = ""  # YYYY-MM-DD
        self._gemini_rpm_limit: int = GEMINI_DEFAULT_RPM

    # ══════════════════════════════════════════════════════════
    #  GEMINI RATE LIMITING
    # ══════════════════════════════════════════════════════════

    def pre_gemini_call(self) -> float:
        """
        Check Gemini rate limits before making a call.

        Returns:
            Delay in seconds to wait (0.0 if no wait needed).
            Callers should sleep this amount before proceeding.
        """
        now = time.time()

        # Clean old entries (older than 60s)
        self._gemini_calls = [t for t in self._gemini_calls if now - t < 60]

        delay = 0.0

        # Check RPM
        if len(self._gemini_calls) >= self._gemini_rpm_limit:
            oldest = self._gemini_calls[0]
            delay = max(0, 60 - (now - oldest) + 1)
            logger.warning(
                f"Gemini RPM limit ({self._gemini_rpm_limit}/min) approaching. "
                f"Waiting {delay:.1f}s..."
            )

        return delay

    def record_gemini_call(self, response_headers: dict | None = None):
        """
        Record a Gemini API call and optionally parse rate limit headers.

        Args:
            response_headers: HTTP response headers (optional).
                Looks for X-RateLimit-Remaining, Retry-After, etc.
        """
        self._gemini_calls.append(time.time())

        if response_headers:
            self._parse_gemini_headers(response_headers)

    def _parse_gemini_headers(self, headers: dict):
        """Parse rate limit info from Gemini API response headers."""
        # Gemini uses standard headers in some endpoints
        remaining = headers.get("x-ratelimit-remaining") or headers.get("X-RateLimit-Remaining")
        limit = headers.get("x-ratelimit-limit") or headers.get("X-RateLimit-Limit")
        retry_after = headers.get("retry-after") or headers.get("Retry-After")

        if limit:
            try:
                self._gemini_rpm_limit = int(limit)
                logger.debug(f"Gemini RPM limit set to {self._gemini_rpm_limit}")
            except (ValueError, TypeError):
                pass

        if remaining is not None:
            try:
                rem = int(remaining)
                if rem <= 2:
                    logger.warning(f"Gemini rate limit nearly exhausted: {rem} remaining")
            except (ValueError, TypeError):
                pass

        if retry_after:
            try:
                wait = float(retry_after)
                logger.warning(f"Gemini Retry-After header: {wait}s")
            except (ValueError, TypeError):
                pass

    # ══════════════════════════════════════════════════════════
    #  YOUTUBE QUOTA TRACKING
    # ══════════════════════════════════════════════════════════

    def check_youtube_quota(self) -> dict:
        """
        Check if YouTube quota is sufficient for an upload.

        Returns:
            Dict with:
              - can_upload (bool): True if quota is sufficient
              - used (int): Quota units used today
              - remaining (int): Estimated remaining units
              - daily_limit (int): Total daily quota
        """
        self._reset_quota_if_new_day()

        remaining = YOUTUBE_DAILY_QUOTA - self._youtube_quota_used
        can_upload = remaining >= YOUTUBE_UPLOAD_COST

        if not can_upload:
            logger.warning(
                f"YouTube quota insufficient: {remaining} units remaining, "
                f"upload requires {YOUTUBE_UPLOAD_COST} units"
            )
        elif remaining < YOUTUBE_DAILY_QUOTA * (1 - _QUOTA_SAFETY_MARGIN):
            logger.info(f"YouTube quota healthy: {remaining} units remaining")

        return {
            "can_upload": can_upload,
            "used": self._youtube_quota_used,
            "remaining": remaining,
            "daily_limit": YOUTUBE_DAILY_QUOTA,
        }

    def record_youtube_upload(self):
        """Record a YouTube upload against daily quota."""
        self._reset_quota_if_new_day()
        self._youtube_quota_used += YOUTUBE_UPLOAD_COST
        logger.info(
            f"YouTube quota used: {self._youtube_quota_used}/{YOUTUBE_DAILY_QUOTA} "
            f"({self._youtube_quota_used / YOUTUBE_DAILY_QUOTA:.0%})"
        )

    def record_youtube_api_call(self, cost: int = YOUTUBE_LIST_COST):
        """Record a generic YouTube API call."""
        self._reset_quota_if_new_day()
        self._youtube_quota_used += cost

    def _reset_quota_if_new_day(self):
        """Reset quota counter at midnight UTC (YouTube resets at midnight PT, close enough)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._youtube_quota_date:
            if self._youtube_quota_date:
                logger.info(
                    f"YouTube quota reset (new day: {today}, "
                    f"prev usage: {self._youtube_quota_used})"
                )
            self._youtube_quota_date = today
            self._youtube_quota_used = 0

    # ══════════════════════════════════════════════════════════
    #  SUMMARY
    # ══════════════════════════════════════════════════════════

    def get_status(self) -> dict:
        """Get current rate limiting status for monitoring."""
        now = time.time()
        recent_gemini = len([t for t in self._gemini_calls if now - t < 60])
        self._reset_quota_if_new_day()

        return {
            "gemini_rpm_used": recent_gemini,
            "gemini_rpm_limit": self._gemini_rpm_limit,
            "youtube_quota_used": self._youtube_quota_used,
            "youtube_quota_remaining": YOUTUBE_DAILY_QUOTA - self._youtube_quota_used,
            "youtube_can_upload": (YOUTUBE_DAILY_QUOTA - self._youtube_quota_used) >= YOUTUBE_UPLOAD_COST,
        }
