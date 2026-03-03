"""
SEO-Optimized Description Generator — Phase 7.1.

Builds a YouTube-optimized video description from content metadata.
Template follows YouTube SEO best practices:
  • Hook sentence in the first line (above the fold)
  • Bullet summary for viewer retention
  • Channel CTA with URL
  • Hashtags block (YouTube indexes first 3 for above-title display)
  • Estimated timestamps

Usage:
    from src.seo import generate_seo_description
    desc = generate_seo_description(content, duration_seconds=45)
"""
from __future__ import annotations

import logging
import re

from src import config

logger = logging.getLogger(__name__)

# ── Content-type specific hooks ─────────────────────────────────
_HOOK_PREFIX: dict[str, str] = {
    "tip":          "🔥 Quick coding tip",
    "quiz":         "🧠 Can you solve this coding quiz?",
    "before_after": "✨ See the before & after code transformation",
}

# ── CTA templates ───────────────────────────────────────────────
_CTA_LINES: list[str] = [
    "👨‍💻 More coding tips every day — Subscribe!",
    "🔔 Turn on notifications so you never miss a tip!",
    "💬 Drop a comment if you learned something new!",
]


def _extract_hook(script: str, max_len: int = 150) -> str:
    """Extract the first sentence from the script as a hook."""
    # Try splitting on sentence-ending punctuation
    sentences = re.split(r'(?<=[.!?])\s+', script.strip())
    if sentences:
        hook = sentences[0].strip()
        if len(hook) > max_len:
            hook = hook[:max_len].rsplit(" ", 1)[0] + "…"
        return hook
    return script[:max_len].strip()


def _build_bullets(content: dict) -> list[str]:
    """Generate 2–3 bullet points summarizing the content."""
    bullets: list[str] = []

    lang = content.get("language", "").capitalize()
    content_type = content.get("content_type", "tip")

    # Bullet 1: what language/topic
    if lang:
        bullets.append(f"Language: {lang}")

    # Bullet 2: what type of content
    type_labels = {
        "tip": "A quick, practical coding tip",
        "quiz": "An interactive coding quiz to test your skills",
        "before_after": "A before & after code transformation",
    }
    bullets.append(type_labels.get(content_type, "A coding insight"))

    # Bullet 3: code complexity
    code = content.get("code", "")
    line_count = code.count("\n") + 1 if code else 0
    if line_count > 0:
        bullets.append(f"Just {line_count} lines of clean code")

    return bullets


def _build_timestamps(duration_seconds: float, content_type: str) -> str:
    """Build estimated timestamps section."""
    if duration_seconds <= 0:
        return ""

    dur = int(duration_seconds)
    # Estimate sections based on typical video structure
    type_label = {
        "tip": "The Tip",
        "quiz": "The Quiz",
        "before_after": "Before & After",
    }.get(content_type, "The Content")

    lines = ["⏱ Timestamps:"]
    lines.append("0:00 Intro")

    # Code starts after ~3–5 seconds
    mid = min(5, dur // 3)
    lines.append(f"0:{mid:02d} {type_label}")

    # Outro in last 3 seconds
    if dur > 10:
        outro_s = max(dur - 3, mid + 1)
        m, s = divmod(outro_s, 60)
        lines.append(f"{m}:{s:02d} Subscribe reminder")

    return "\n".join(lines)


def generate_seo_description(
    content: dict,
    duration_seconds: float = 0,
    channel_url: str = "",
    extra_cta: str = "",
) -> str:
    """
    Build a full SEO-optimized YouTube description.

    Args:
        content:           Content dict from ``generate_content()``.
        duration_seconds:  Video duration for timestamp generation.
        channel_url:       Channel URL for CTA. Falls back to ``config.CHANNEL_URL``.
        extra_cta:         Optional extra CTA line (e.g., end-screen replacement).

    Returns:
        Formatted description string (max ~5000 chars for YouTube).
    """
    channel_url = channel_url or config.CHANNEL_URL
    script = content.get("script", "")
    hashtags = content.get("hashtags", [])
    content_type = content.get("content_type", "tip")
    language = content.get("language", "")

    # ── Hook line (above the fold — first 100 chars shown in search) ──
    hook_prefix = _HOOK_PREFIX.get(content_type, "💡 Coding tip")
    hook_sentence = _extract_hook(script)
    hook = f"{hook_prefix} — {hook_sentence}"

    # ── Bullet summary ─────────────────────────────────────────
    bullets = _build_bullets(content)
    bullets_block = "\n".join(f"• {b}" for b in bullets)

    # ── Channel CTA ────────────────────────────────────────────
    cta_lines = "\n".join(_CTA_LINES)

    # ── Hashtags (YouTube shows first 3 above title) ───────────
    hashtag_block = " ".join(hashtags[:15]) if hashtags else "#CodingTips #Shorts #Programming"

    # ── Timestamps ─────────────────────────────────────────────
    timestamps = _build_timestamps(duration_seconds, content_type)

    # ── SEO keywords (hidden, helps YouTube search ranking) ────
    seo_keywords = _build_seo_keywords(language, content_type)

    # ── Assemble ───────────────────────────────────────────────
    parts = [
        hook,
        "",
        "In this video:",
        bullets_block,
        "",
        f"👨‍💻 {channel_url}",
        cta_lines,
    ]

    if extra_cta:
        parts.extend(["", extra_cta])

    if timestamps:
        parts.extend(["", timestamps])

    parts.extend([
        "",
        "─" * 30,
        hashtag_block,
        "",
        seo_keywords,
    ])

    description = "\n".join(parts)

    # YouTube max 5000 chars
    if len(description) > 5000:
        description = description[:4997] + "..."

    logger.info(f"SEO description generated ({len(description)} chars)")
    return description


def _build_seo_keywords(language: str, content_type: str) -> str:
    """Build a hidden SEO keyword line for YouTube indexing."""
    keywords = [
        "coding tips", "programming", "developer",
        "learn to code", "software engineering",
        language.lower() if language else "python",
        f"{content_type} coding", "shorts",
        "coding tutorial", "dev tips",
    ]
    return " ".join(keywords)
