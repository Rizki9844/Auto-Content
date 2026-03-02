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

# JSON schema for structured Gemini output
_RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    required=["title", "script", "code", "language", "hashtags", "content_type"],
    properties={
        "title": types.Schema(type=types.Type.STRING),
        "script": types.Schema(type=types.Type.STRING),
        "code": types.Schema(type=types.Type.STRING),
        "language": types.Schema(type=types.Type.STRING),
        "hashtags": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
        ),
        "content_type": types.Schema(type=types.Type.STRING),
        "expected_output": types.Schema(type=types.Type.STRING),
        "quiz_answer": types.Schema(type=types.Type.STRING),
        "code_before": types.Schema(type=types.Type.STRING),
    },
)

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
#  SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """You are an expert coding educator who creates viral short-form video content for YouTube Shorts. Your goal is to generate a unique, practical, educational coding tip that makes developers think "I didn't know that!"

CONTENT TYPES — You MUST pick ONE of these 4 types for each generation:

1. "tip" — A quick coding trick or one-liner. Classic format.
2. "output_demo" — Code that produces SURPRISING or INTERESTING output when run.
   You MUST provide expected_output showing exactly what prints when the code executes.
   Great for: list tricks, math surprises, string manipulation, one-liner magic.
3. "quiz" — A "What does this code print?" challenge.
   Show tricky code, the narration asks viewers to guess, then reveal the answer.
   You MUST provide quiz_answer with the correct explanation.
4. "before_after" — Show a BAD way (code_before) then a BETTER way (code).
   The narration explains why the second approach is superior.
   You MUST provide code_before with the ugly/slow/old approach.

STRICT RULES:
1. The code snippet MUST be concise (3–15 lines max), syntactically correct, and demonstrate ONE clear concept.
2. The narration script MUST be exactly 40–60 words. Start with a hook question or surprising statement. Be conversational, energetic, educational.
3. The title MUST be catchy, max 80 characters, and end with " #Shorts".
4. Generate exactly 5–8 relevant hashtags (with # prefix).
5. The code MUST use proper indentation (spaces, not tabs).
6. VARY the programming language, category, and CONTENT TYPE across generations.
7. For "output_demo": the code MUST be safe to execute (no file I/O, no network, no imports beyond stdlib). The expected_output MUST be the exact stdout.
8. For "quiz": make the code tricky but fair — something that tests real knowledge.
9. For "before_after": code_before should be noticeably worse (verbose, slow, or outdated).

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
  "content_type": "tip|output_demo|quiz|before_after",
  "title": "catchy title ending with #Shorts",
  "script": "40-60 word narration script",
  "code": "the code snippet with proper formatting",
  "language": "python|javascript|typescript|css|html|sql|bash|go|rust|java",
  "hashtags": ["#CodingTips", "#Programming", ...],
  "expected_output": "(REQUIRED for output_demo) exact stdout when code runs",
  "quiz_answer": "(REQUIRED for quiz) correct answer + brief explanation",
  "code_before": "(REQUIRED for before_after) the bad/old approach code"
}"""

MAX_RETRIES = 3
BASE_RETRY_DELAY = 5  # seconds (exponential: 5, 10, 20 …)


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

    # Step 4: Try to close truncated JSON (missing closing braces/brackets)
    try:
        # Count open/close braces and brackets
        open_braces = fixed.count('{') - fixed.count('}')
        open_brackets = fixed.count('[') - fixed.count(']')
        # Close any unterminated string
        if fixed.count('"') % 2 != 0:
            fixed += '"'
        fixed += ']' * max(0, open_brackets)
        fixed += '}' * max(0, open_braces)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Step 5: Try to extract individual fields with regex as last resort
    try:
        title = re.search(r'"title"\s*:\s*"([^"]*)"', text)
        script = re.search(r'"script"\s*:\s*"([^"]*)"', text)
        lang = re.search(r'"language"\s*:\s*"([^"]*)"', text)
        hashtags = re.search(r'"hashtags"\s*:\s*\[(.*?)\]', text, re.DOTALL)

        # Code field — grab everything between "code": " and a closing quote
        # followed by comma/brace (handles any key order)
        code_match = re.search(
            r'"code"\s*:\s*"(.*?)"\s*[,}]',
            text, re.DOTALL
        )

        if title and script and lang:
            tags = []
            if hashtags:
                tags = re.findall(r'"(#[^"]+)"', hashtags.group(1))

            code_text = ""
            if code_match:
                code_text = code_match.group(1).replace('\\n', '\n').replace('\\t', '\t')

            return {
                "title": title.group(1),
                "script": script.group(1),
                "code": code_text or "# Code generation failed",
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
                    response_schema=_RESPONSE_SCHEMA,
                    temperature=0.9,
                    top_p=0.95,
                    max_output_tokens=2048,
                ),
            )

            # Parse JSON response (with repair for common LLM issues)
            raw_text = response.text.strip()
            logger.debug(f"Raw Gemini response ({len(raw_text)} chars): {raw_text[:500]}")
            data = _repair_json(raw_text)

            # Validate required fields
            _validate_content(data)

            logger.info(f"Content generated: [{data['language']}] {data['title']}")
            return data

        except Exception as e:
            last_error = e
            logger.warning(f"Attempt {attempt}/{MAX_RETRIES} failed: {e}")
            # Log the raw response for debugging on parse failures
            if 'raw_text' in locals():
                logger.info(f"Raw response preview: {raw_text[:300]}...")
            if attempt < MAX_RETRIES:
                delay = BASE_RETRY_DELAY * (2 ** (attempt - 1))  # 5, 10, 20
                logger.info(f"Retrying in {delay}s...")
                time.sleep(delay)

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

    # Normalize and validate content_type
    ct = data.get("content_type", "tip").lower().strip()
    if ct not in ("tip", "output_demo", "quiz", "before_after"):
        ct = "tip"
    data["content_type"] = ct

    # Ensure type-specific fields have defaults
    if ct == "output_demo" and not data.get("expected_output"):
        data["expected_output"] = ""
    if ct == "quiz" and not data.get("quiz_answer"):
        data["quiz_answer"] = ""
    if ct == "before_after" and not data.get("code_before"):
        data["code_before"] = ""
