"""
src/trending.py — Trending Topic Integration (Phase 6.1)

Fetches trending coding topics from two optional sources:
  - Google Trends via ``pytrends`` (optional install)
  - YouTube Data API v3 ``videos.list`` (Science & Technology, chart=mostPopular)

Never raises — returns an empty list on any failure so the main pipeline
is never blocked by an unavailable third-party API.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ── Coding-domain keyword filter ────────────────────────────────────────────
_CODING_KEYWORDS: frozenset[str] = frozenset(
    {
        "python", "javascript", "typescript", "rust", "golang", "go lang",
        "java", "c++", "csharp", "c#", "kotlin", "swift", "ruby", "php",
        "react", "vue", "angular", "svelte", "node", "django", "fastapi",
        "flask", "express", "nextjs", "next.js", "nuxtjs",
        "css", "html", "sql", "nosql", "mongodb", "postgres",
        "api", "rest", "graphql", "websocket",
        "bash", "shell", "linux", "terminal", "git", "github",
        "docker", "kubernetes", "k8s", "ci/cd", "devops",
        "aws", "azure", "gcp", "cloud",
        "ai", "llm", "machine learning", "ml", "deep learning", "neural",
        "algorithm", "data structure", "big o",
        "coding", "programming", "developer", "dev",
        "backend", "frontend", "fullstack", "full stack",
        "tailwind", "regex", "async", "lambda", "closure",
        "microservice", "serverless", "testing", "unit test",
        "vscode", "vim", "neovim", "ide",
        "tutorial", "tips", "tricks", "beginner",
    }
)

# Queries sent to Google Trends (kept short to avoid rate limits)
_TRENDS_QUERIES: list[str] = [
    "python tutorial",
    "javascript tips",
    "typescript tricks",
    "react hooks",
    "web development",
    "coding tips",
]


def _is_coding_relevant(text: str) -> bool:
    """
    Return True if *text* contains at least one coding-domain keyword.

    Uses word-level matching for single-word keywords to avoid false positives
    (e.g. 'ide' in 'video', 'tips' in 'cooking tips').
    Multi-word keywords (e.g. 'go lang', 'deep learning') use substring match.
    """
    normalized = text.lower()
    # Extract word tokens (alphanumeric, including '#' and '+' for c++/c#)
    tokens: set[str] = set(re.findall(r'[a-z][a-z0-9]*', normalized))
    # Also include joined forms e.g. 'nextjs', 'fullstack'
    for kw in _CODING_KEYWORDS:
        if " " in kw or "+" in kw or "#" in kw or "." in kw:
            # Multi-word or special-char keyword: substring match is fine
            if kw in normalized:
                return True
        else:
            # Single plain word: whole-word match only
            if kw in tokens:
                return True
    return False


def _clean_title(title: str) -> str:
    """Strip trailing attribution / channel suffixes from a video title."""
    cleaned = re.sub(r"\s*[\|\[\(].*", "", title).strip()
    # Also remove trailing dashes / colons
    cleaned = re.sub(r"[\s\-:]+$", "", cleaned).strip()
    return cleaned


# ── Source 1: Google Trends ─────────────────────────────────────────────────

def _get_google_trends(max_topics: int = 5) -> list[str]:
    """
    Return trending search queries related to coding from Google Trends.

    Uses pytrends (optional dependency).  Returns [] if not installed or if
    the request fails.
    """
    try:
        from pytrends.request import TrendReq  # type: ignore[import-untyped]  # lazy import — optional dep
    except ImportError:
        logger.debug("pytrends not installed — skipping Google Trends source")
        return []

    results: list[str] = []
    try:
        pytrends = TrendReq(hl="en-US", tz=0, timeout=(5, 15))
        for kw in _TRENDS_QUERIES:
            if len(results) >= max_topics:
                break
            try:
                pytrends.build_payload([kw], timeframe="now 7-d", geo="")
                related = pytrends.related_queries()
                df = related.get(kw, {}).get("top")
                if df is not None and not df.empty:
                    for q in df["query"].head(3).tolist():
                        if isinstance(q, str) and _is_coding_relevant(q):
                            results.append(q)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Google Trends query '{kw}' failed: {e}")
        logger.debug(f"Google Trends returned {len(results)} topics")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Google Trends session failed: {e}")

    return results[:max_topics]


# ── Source 2: YouTube Data API v3 ─────────────────────────────────────────

def _get_youtube_trending(api_key: str, max_topics: int = 5) -> list[str]:
    """
    Return titles of trending Science & Technology videos from YouTube.

    Filters for coding-relevant content using :func:`_is_coding_relevant`.
    Returns [] if ``api_key`` is empty or the request fails.
    """
    if not api_key:
        logger.debug("YOUTUBE_API_KEY not set — skipping YouTube Trending source")
        return []

    try:
        from googleapiclient.discovery import build  # already in requirements

        youtube = build("youtube", "v3", developerKey=api_key)
        response = (
            youtube.videos()
            .list(
                part="snippet",
                chart="mostPopular",
                videoCategoryId="28",  # Science & Technology
                maxResults=25,
                regionCode="US",
            )
            .execute()
        )

        topics: list[str] = []
        for item in response.get("items", []):
            title = item.get("snippet", {}).get("title", "")
            if _is_coding_relevant(title):
                cleaned = _clean_title(title)
                if cleaned and len(cleaned) > 5:
                    topics.append(cleaned)
            if len(topics) >= max_topics:
                break

        logger.debug(f"YouTube Trending returned {len(topics)} topics")
        return topics

    except Exception as e:  # noqa: BLE001
        logger.warning(f"YouTube Trending fetch failed: {e}")
        return []


# ── Public API ──────────────────────────────────────────────────────────────

def get_trending_topics(
    api_key: str = "",
    max_total: int = 8,
) -> list[str]:
    """
    Return a combined, deduplicated list of trending coding topic hints.

    Aggregates results from Google Trends and YouTube Trending.  Neither
    source is required — the function returns an empty list if both fail,
    so the main pipeline is never blocked.

    Args:
        api_key:   YouTube Data API v3 key (``YOUTUBE_API_KEY`` env var).
        max_total: Maximum number of topic hints to return.

    Returns:
        List of short topic hint strings, e.g.
        ``["python async await", "React Server Components tutorial"]``.
    """
    half = max(1, max_total // 2)
    google_topics = _get_google_trends(max_topics=half + 1)
    yt_topics = _get_youtube_trending(api_key=api_key, max_topics=half + 1)

    # Deduplicate preserving order (Google Trends first)
    seen: set[str] = set()
    unique: list[str] = []
    for topic in google_topics + yt_topics:
        key = topic.lower()
        if key not in seen:
            seen.add(key)
            unique.append(topic)

    logger.info(
        f"Trending topics fetched: {len(unique)} total "
        f"({len(google_topics)} Google, {len(yt_topics)} YouTube)"
    )
    return unique[:max_total]
