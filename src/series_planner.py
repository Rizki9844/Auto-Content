"""
Series Planner — generates structured mini-series plans via LLM.

Phase 6.4: Smart Series Generator

Usage:
    from src.series_planner import plan_series
    plan = plan_series("Python Basics", episodes=5)
    # Returns list of dicts: [{episode, topic, language, content_type, hook}, ...]
"""
import json
import logging
import re
import time
from datetime import datetime, timezone

from google import genai
from google.genai import types

from src import config

logger = logging.getLogger(__name__)

# ── JSON schema for one series episode plan entry ─────────────
_EPISODE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    required=["episode", "topic", "language", "content_type"],
    properties={
        "episode":      types.Schema(type=types.Type.INTEGER),
        "topic":        types.Schema(type=types.Type.STRING),
        "language":     types.Schema(type=types.Type.STRING),
        "content_type": types.Schema(type=types.Type.STRING),
        "hook":         types.Schema(type=types.Type.STRING),
    },
)

_PLAN_SCHEMA = types.Schema(
    type=types.Type.ARRAY,
    items=_EPISODE_SCHEMA,
)

_PLAN_PROMPT_TEMPLATE = """\
You are creating a mini-series plan for YouTube Shorts coding content aimed at BEGINNER developers.

Series theme: "{theme}"
Number of episodes: {n}

Generate a list of exactly {n} episodes that:
- Build progressively from simple to slightly more advanced
- Cover different facets of the theme (avoid repeating the same concept)
- Alternate content types for variety (tip, quiz, before_after)
- Can mix 2-3 programming languages when the theme is language-agnostic
- Each episode should be self-contained but clearly part of the series

For each episode, provide:
  episode      — episode number (1-indexed)
  topic        — specific topic title (5-10 words max)
  language     — programming language: python, javascript, typescript, rust, go, etc.
  content_type — exactly one of: "tip", "quiz", "before_after"
  hook         — single compelling opening sentence the narrator will say (≤12 words)

Return a valid JSON array of exactly {n} objects. Return JSON only, no explanation, no markdown.
"""


def plan_series(theme: str, episodes: int) -> list[dict]:
    """
    Call Gemini to generate a structured plan for a mini-series.

    Args:
        theme:    Series theme string, e.g. "Python Basics for Beginners"
        episodes: Number of episodes to plan (1–20 recommended)

    Returns:
        List of episode dicts:
        [{"episode": 1, "topic": "...", "language": "python",
          "content_type": "tip", "hook": "..."}, ...]

    Raises:
        RuntimeError: If GEMINI_API_KEY is not set.
    """
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is required for plan_series()")

    episodes = max(1, min(episodes, 20))
    prompt = _PLAN_PROMPT_TEMPLATE.format(theme=theme, n=episodes)

    client = genai.Client(api_key=config.GEMINI_API_KEY)

    for attempt in range(1, 4):
        try:
            logger.info(
                f"Requesting series plan: theme={repr(theme)}, "
                f"episodes={episodes}, attempt={attempt}"
            )
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_PLAN_SCHEMA,
                    temperature=0.85,
                    top_p=0.95,
                ),
            )
            raw = (response.text or "[]").strip()
            plan = json.loads(raw)
            break
        except Exception as e:
            logger.warning(f"plan_series attempt {attempt} failed: {e}")
            if attempt < 3:
                time.sleep(2 ** attempt)
            else:
                raise

    if not isinstance(plan, list):
        plan = plan.get("items", []) if isinstance(plan, dict) else []

    # Normalise and fill gaps
    valid_types = {"tip", "quiz", "before_after"}
    result: list[dict] = []
    for i in range(1, episodes + 1):
        raw_ep = plan[i - 1] if i <= len(plan) else {}
        ct = raw_ep.get("content_type", "tip")
        if ct not in valid_types:
            ct = "tip"
        result.append({
            "episode":      int(raw_ep.get("episode", i)),
            "topic":        str(raw_ep.get("topic", f"{theme} — Part {i}")),
            "language":     str(raw_ep.get("language", "python")).lower(),
            "content_type": ct,
            "hook":         str(raw_ep.get("hook", "")),
        })

    logger.info(f"Series plan ready: {len(result)} episodes for '{theme}'")
    return result


def make_series_id(theme: str) -> str:
    """
    Generate a deterministic, URL-safe series identifier from a theme + date.

    Example: "Python Basics" → "python-basics-20260303"
    """
    slug = re.sub(r"[^a-z0-9]+", "-", theme.lower()).strip("-")
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{slug}-{date_str}"
