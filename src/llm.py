"""
LLM content generation module using Google Gemini Pro.
Generates structured JSON with title, narration script, code snippet, and hashtags.
"""
import json
import re
import time
import logging

from google import genai
from google.genai import types

from src import config
from src.db import get_past_topics

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
#  SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """You are an expert coding educator who creates viral short-form video content for YouTube Shorts. Your goal is to generate a unique, practical, educational coding tip that makes developers think "I didn't know that!"

STRICT RULES:
1. The code snippet MUST be concise (3–15 lines max), syntactically correct, and demonstrate ONE clear concept.
2. The narration script MUST be exactly 40–60 words. Start with a hook question or surprising statement. Be conversational, energetic, educational.
3. The title MUST be catchy, max 80 characters, and end with " #Shorts".
4. Generate exactly 5–8 relevant hashtags (with # prefix).
5. The code MUST use proper indentation (spaces, not tabs).
6. VARY the programming language and category across generations.

CATEGORIES TO ROTATE BETWEEN:
- Python tricks & one-liners
- JavaScript modern features (ES6+)
- CSS tricks & animations
- TypeScript type magic
- React hooks & patterns
- SQL query tricks
- HTML5 hidden features
- Git power commands
- API design patterns
- Algorithm tricks & data structures
- Node.js tips
- Tailwind CSS shortcuts

Return valid JSON with this exact schema:
{
  "title": "catchy title ending with #Shorts",
  "script": "40-60 word narration script",
  "code": "the code snippet with proper formatting",
  "language": "python|javascript|typescript|css|html|sql|bash|go|rust|java",
  "hashtags": ["#CodingTips", "#Programming", ...]
}"""

MAX_RETRIES = 3
RETRY_DELAY = 10  # seconds


def _repair_json(raw: str) -> dict:
    """
    Attempt to parse JSON, with fallback repair for common LLM issues:
    - Code blocks wrapped in ```json ... ```
    - Unterminated strings (truncated output)
    - Unescaped newlines inside string values
    """
    # Step 1: Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()

    # Step 2: Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Step 3: Fix unescaped newlines inside JSON string values
    # Replace literal newlines that are inside strings with \\n
    fixed = ""
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            fixed += ch
            escape_next = False
            continue
        if ch == '\\':
            fixed += ch
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            fixed += ch
            continue
        if in_string and ch == '\n':
            fixed += '\\n'
            continue
        if in_string and ch == '\t':
            fixed += '\\t'
            continue
        fixed += ch

    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Step 4: Try to extract individual fields with regex as last resort
    try:
        title = re.search(r'"title"\s*:\s*"([^"]*)"', text)
        script = re.search(r'"script"\s*:\s*"([^"]*)"', text)
        lang = re.search(r'"language"\s*:\s*"([^"]*)"', text)
        hashtags = re.search(r'"hashtags"\s*:\s*\[(.*?)\]', text, re.DOTALL)

        # Code field is trickiest — grab everything between "code": " and the next key
        code_match = re.search(
            r'"code"\s*:\s*"(.*?)"\s*,\s*"(?:language|hashtags|title|script)"',
            text, re.DOTALL
        )

        if title and script and code_match and lang:
            tags = []
            if hashtags:
                tags = re.findall(r'"(#[^"]+)"', hashtags.group(1))

            return {
                "title": title.group(1),
                "script": script.group(1),
                "code": code_match.group(1).replace('\\n', '\n').replace('\\t', '\t'),
                "language": lang.group(1),
                "hashtags": tags or ["#CodingTips", "#Programming", "#Shorts"],
            }
    except Exception:
        pass

    # Nothing worked — raise original error
    raise json.JSONDecodeError("Could not repair JSON from LLM response", text, 0)


def generate_content() -> dict:
    """
    Generate a unique coding tip using Gemini Pro.
    Returns a dict with keys: title, script, code, language, hashtags.
    Raises RuntimeError after MAX_RETRIES failed attempts.
    """
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    client = genai.Client(api_key=config.GEMINI_API_KEY)

    # ── Build prompt with deduplication context ───────────────
    past_topics = get_past_topics(limit=50)
    if past_topics:
        history_text = "\n".join(
            f"- [{t.get('language', '?')}] {t.get('title', t.get('topic', ''))}"
            for t in past_topics
        )
    else:
        history_text = "(None yet — this is the first video! Pick something exciting.)"

    user_prompt = f"""{SYSTEM_PROMPT}

══ PREVIOUSLY GENERATED TOPICS (DO NOT REPEAT ANY) ══
{history_text}

Now generate a brand new, unique coding tip. Pick a DIFFERENT language and category from the ones listed above. Return valid JSON only."""

    # ── Retry loop ────────────────────────────────────────────
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"Gemini API call (attempt {attempt}/{MAX_RETRIES})...")
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.9,
                    top_p=0.95,
                    max_output_tokens=2048,
                ),
            )

            # Parse JSON response (with repair for common LLM issues)
            raw_text = response.text.strip()
            data = _repair_json(raw_text)

            # Validate required fields
            _validate_content(data)

            logger.info(f"Content generated: [{data['language']}] {data['title']}")
            return data

        except Exception as e:
            last_error = e
            logger.warning(f"Attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                logger.info(f"Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)

    raise RuntimeError(
        f"Failed to generate content after {MAX_RETRIES} attempts. "
        f"Last error: {last_error}"
    )


def _validate_content(data: dict) -> None:
    """Validate the LLM output has all required fields with sane values."""
    required = ["title", "script", "code", "language", "hashtags"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Missing fields in LLM response: {missing}")

    if not data["code"].strip():
        raise ValueError("Code snippet is empty")

    word_count = len(data["script"].split())
    if word_count < 15:
        raise ValueError(f"Script too short: {word_count} words (minimum 15)")

    if not isinstance(data["hashtags"], list) or len(data["hashtags"]) < 3:
        raise ValueError("Need at least 3 hashtags")

    # Ensure title ends with #Shorts
    if "#Shorts" not in data["title"] and "#shorts" not in data["title"]:
        data["title"] = data["title"].rstrip() + " #Shorts"

    # Normalize language name
    data["language"] = data["language"].lower().strip()
