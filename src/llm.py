"""
LLM content generation module using Google Gemini Pro.
Generates structured JSON with title, narration script, code snippet, and hashtags.

Phase 6.5: Prompt A/B Testing — two system prompt variants + auto rotation.
Phase 6.6: Content Templates Library — 30% chance to use template as starting point.
Phase 6.7: Voice & Tone Variety — narrator tone injected into prompt.
Phase 11:  Content Pivot — visual UI/animation showcase mode.
"""
import json
import re
import time
import logging
import random
from datetime import datetime, timezone

from google import genai
from google.genai import types

from src import config
from src.db import get_past_topics

# JSON schema for structured Gemini output (coding_tips mode)
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

# JSON schema for visual UI mode (Phase 11)
_VISUAL_UI_RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    required=["title", "script", "html_code", "display_code", "language",
              "hashtags", "content_type", "ui_category"],
    properties={
        "title": types.Schema(type=types.Type.STRING),
        "script": types.Schema(type=types.Type.STRING),
        "html_code": types.Schema(type=types.Type.STRING),
        "display_code": types.Schema(type=types.Type.STRING),
        "language": types.Schema(type=types.Type.STRING),
        "hashtags": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
        ),
        "content_type": types.Schema(type=types.Type.STRING),
        "ui_category": types.Schema(type=types.Type.STRING),
    },
)

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
#  SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """You are a friendly coding educator who creates viral short-form video content for YouTube Shorts. Your audience is BEGINNER developers who are just starting to learn programming. Your goal is to generate a unique, practical, easy-to-understand coding tip that makes beginners think "Wow, I just learned something useful!"

CONTENT TYPES — You MUST pick ONE of these 3 types for each generation:

1. "tip" — A quick coding trick, shortcut, or beginner-friendly concept.
   Keep it simple — ONE clear idea that a beginner can immediately use.
2. "quiz" — A "What does this code print?" challenge.
   Show simple but educational code, the narration asks viewers to guess, then reveal the answer.
   You MUST provide quiz_answer with the correct explanation in simple terms.
3. "before_after" — Show a BAD way (code_before) then a BETTER way (code).
   The narration explains WHY the second approach is better, using beginner-friendly language.
   You MUST provide code_before with the ugly/slow/old approach.

STRICT RULES:
1. The code snippet MUST be concise (3–10 lines max), syntactically correct, and demonstrate ONE clear concept.
2. Use simple variable names (name, age, items, result — NOT x, y, z). Add a brief comment on tricky lines.
3. The narration script MUST be exactly 40–70 words. Start with a hook question or surprising statement. Be conversational, energetic, educational. Use commas and dashes for pacing — keep it FAST and flowing.
4. The title MUST be catchy, max 80 characters, and end with " #Shorts".
5. Generate exactly 5–8 relevant hashtags (with # prefix).
6. The code MUST use proper indentation (spaces, not tabs).
7. VARY the programming language, category, and CONTENT TYPE across generations.
8. Prioritize Python and JavaScript — these are the most popular beginner languages.
9. For "quiz": make the code educational but fair — something that teaches a real concept.
10. For "before_after": code_before should be noticeably worse (verbose, slow, or outdated).

CATEGORIES TO ROTATE BETWEEN:
- Python for beginners (basic tricks, list comprehensions, f-strings)
- JavaScript basics (ES6+ features, array methods, template literals)
- Python one-liners & shortcuts
- JavaScript modern patterns (destructuring, spread, arrow functions)
- CSS tricks & animations
- HTML5 useful features
- Git essential commands
- TypeScript basics
- SQL query fundamentals
- Algorithm tricks for beginners
- React hooks & patterns
- API design basics

Return valid JSON with this exact schema:
{
  "content_type": "tip|quiz|before_after",
  "title": "catchy title ending with #Shorts",
  "script": "40-70 word narration script",
  "code": "the code snippet with proper formatting",
  "language": "python|javascript|typescript|css|html|sql|bash|go|rust|java",
  "hashtags": ["#CodingTips", "#Programming", ...],
  "expected_output": "(optional) exact stdout when code runs",
  "quiz_answer": "(REQUIRED for quiz) correct answer + brief explanation",
  "code_before": "(REQUIRED for before_after) the bad/old approach code"
}"""

# ══════════════════════════════════════════════════════════════
#  SYSTEM PROMPT B — Alternative (Phase 6.5)
# ══════════════════════════════════════════════════════════════
SYSTEM_PROMPT_B = """You are a witty, no-nonsense coding mentor who makes lightning-fast tutorial content for YouTube Shorts. Your audience is developers at any level who love clever tricks. Your mission: share ONE mind-blowing snippet that makes viewers hit "Save" instantly.

CONTENT TYPES — pick ONE per generation:

1. "tip" — A surprisingly clever trick that even experienced devs might not know.
   Focus on real-world productivity wins.
2. "quiz" — A tricky "What's the output?" puzzle that tests a subtle language feature.
   MUST include quiz_answer with a clear, concise explanation.
3. "before_after" — An ugly old-school pattern versus its modern, elegant replacement.
   MUST include code_before with the verbose/ugly approach.

STRICT RULES:
1. Code: 3–10 lines max. Syntactically correct. ONE clear concept. Add a comment ONLY on non-obvious lines.
2. Narration: exactly 40–70 words. Open with a bold, punchy hook — make them stop scrolling. Use short sentences. Heavy pacing with dashes and ellipses.
3. Title: max 80 chars, end with " #Shorts". Be provocative or intriguing.
4. Exactly 5–8 hashtags (with #).
5. Proper indentation (spaces, no tabs).
6. VARY language, category, and content type. Prioritize Python & JavaScript.
7. For quiz: test a real language nuance (type coercion, scoping, mutability).
8. For before_after: the difference should be dramatic.

CATEGORIES:
- Python hidden gems (walrus, match-case, itertools)
- JavaScript gotchas (closures, this, async pitfalls)
- Modern CSS (grid, container queries, :has())
- TypeScript utility types & generics
- SQL window functions & CTEs
- Git power moves (rebase, cherry-pick, bisect)
- React performance patterns
- API & system design nuggets
- Bash automation tricks
- Algorithm one-liners

Return valid JSON:
{
  "content_type": "tip|quiz|before_after",
  "title": "catchy title ending with #Shorts",
  "script": "40-70 word narration",
  "code": "the code",
  "language": "python|javascript|typescript|css|html|sql|bash|go|rust|java",
  "hashtags": ["#CodingTips", ...],
  "expected_output": "(optional)",
  "quiz_answer": "(REQUIRED for quiz)",
  "code_before": "(REQUIRED for before_after)"
}"""


# ══════════════════════════════════════════════════════════════
#  SYSTEM PROMPT — VISUAL UI MODE  (Phase 11)
# ══════════════════════════════════════════════════════════════
SYSTEM_PROMPT_VISUAL_UI = """You are an ELITE front-end developer and creative coder who creates STUNNING visual UI demos for YouTube Shorts / Reels. Your audience loves beautiful web designs, creative animations, and impressive CSS/JS effects.

Your mission: generate a COMPLETE, self-contained HTML page that produces a visually BREATHTAKING effect that makes viewers STOP SCROLLING.

IMPORTANT VISUAL QUALITY RULES:
1. Your HTML MUST look like a REAL professional website — NOT a single centered div on a dark background.
2. For landing_page/portfolio types: include AT LEAST a hero section with navigation, content area, and visual hierarchy.
3. Use gradient-based placeholder images (linear-gradient backgrounds with rounded rectangles) to simulate real photos/thumbnails — NEVER leave empty voids.
4. Add realistic typography hierarchy: large headings (40-60px), medium subheadings (20-28px), body text (14-16px).
5. Include realistic UI elements: navigation bars, buttons, cards with shadows, badges, profile images (circular gradient divs).
6. Every pixel of the 1000x700 viewport should feel intentional and designed.

PROJECT CATEGORIES — pick ONE per generation:
1. "landing_page" — Full hero section with nav bar, headline, CTA button, floating decorative elements, gradient backgrounds.
2. "login_page" — Beautiful auth form with glassmorphism, neon glow, aurora effects, creative input animations. Must have email/password fields.
3. "portfolio" — Personal portfolio with profile picture (gradient circle), name, project cards (with gradient thumbnail placeholders), navigation.
4. "animation" — A pure CSS/JS animation: particles, cursor effects, waves, morphing shapes, loading spinners, aurora effects.
5. "interactive_component" — Standalone micro-interaction: Add to cart button with badge animation, toggle switch, like button with particles, form validation.
6. "creative_ui" — Any other creative web UI: 404 pages, dark mode toggles, pricing cards, dashboards with animated charts.

STRICT RULES:
1. Generate a COMPLETE self-contained HTML file with INLINE CSS and JS (no external deps like CDN links).
2. The visual MUST be eye-catching within the first 2 seconds.
3. Must render beautifully in a 1000x700 viewport with dark background (#0d1117 or custom dark palette).
4. Use MODERN CSS: gradients, backdrop-filter, @keyframes, transforms, transitions, custom properties, box-shadows.
5. Use creative color palettes: neon purples (#a855f7), electric blues (#3b82f6), hot pinks (#ec4899), emerald (#10b981), gold (#fbbf24). AVOID plain colors.
6. For elements that would normally have images, use rich CSS gradient backgrounds (linear-gradient, radial-gradient) as placeholders.
7. CRITICAL FOR INTERACTIVE COMPONENTS: Include JavaScript that auto-triggers interactions in a loop (e.g., `setInterval(() => btn.click(), 1500)`) for screen recording.
8. Keep JS minimal but impactful. Canvas animations, requestAnimationFrame, cursor tracking are great.
9. The code MUST be syntactically correct and render without console errors.
10. The `display_code` field should contain ONLY the 8-10 most creative/interesting CSS or JS lines — this is a TEASER. Viewers comment for full code. Keep it SHORT and CLEAN — it must fit on screen without scrolling.
11. The narration script (40-70 words) should describe what the viewer is seeing with excitement.
12. Title must be catchy, max 80 chars, end with " #Shorts".
13. Generate 5-8 hashtags including #WebDev, #CSS, #Frontend.

CATEGORIES TO ROTATE BETWEEN:
- Full landing page hero sections with animated gradients
- Portfolio cards with holographic/iridescent effects
- Glassmorphism UI (frosted glass panels)
- Neon glow / cyberpunk interfaces
- Particle systems (canvas-based)
- CSS-only @keyframes animations
- 3D card flip / tilt effects
- Animated navigation menus
- Creative button hover effects (ripple, morph, glow)
- Dashboard UI with animated charts/progress bars
- Pricing cards with hover reveal
- Creative 404 / error pages
- Dark mode toggle with smooth transition
- Scroll-triggered element reveals
- Cursor-following glow effects

Return valid JSON with this exact schema:
{
  "content_type": "landing_page|login_page|portfolio|animation|interactive_component|creative_ui",
  "ui_category": "short description of the specific effect, e.g. 'Holographic Portfolio Card with 3D Tilt'",
  "title": "catchy title ending with #Shorts",
  "script": "40-70 word narration describing what viewer sees",
  "html_code": "the COMPLETE self-contained HTML with inline CSS/JS",
  "display_code": "8-15 lines of the MOST creative CSS/JS to show in video",
  "language": "html",
  "hashtags": ["#WebDev", "#CSS", "#Frontend", ...]
}"""


# ══════════════════════════════════════════════════════════════
#  NARRATOR TONE INSTRUCTIONS  (Phase 6.7)
# ══════════════════════════════════════════════════════════════
_TONE_INSTRUCTIONS: dict[str, str] = {
    "energetic": (
        "  • Tone: HIGH energy. Start with exclamations like 'WAIT—', "
        "'Mind = BLOWN!', 'You NEED to know this!'\n"
        "  • Use ALL-CAPS for emphasis. Short, punchy sentences. Lots of dashes."
    ),
    "calm": (
        "  • Tone: Calm and wise. Start with 'Here's a little secret...', "
        "'Did you know...', 'One thing most devs overlook...'\n"
        "  • Use a thoughtful, mentor-like voice. Measured pacing."
    ),
    "curious": (
        "  • Tone: Curious and questioning. Start with a rhetorical question: "
        "'Ever wondered why...?', 'What if I told you...?', 'Why does this happen?'\n"
        "  • Make the viewer THINK before revealing the answer."
    ),
    "dramatic": (
        "  • Tone: Dramatic and suspenseful. Start with 'Most developers NEVER "
        "know this...', 'This one trick changed everything...', 'Stop. Read this.'\n"
        "  • Build tension, then deliver the payoff."
    ),
}

_TONE_ROTATION_ORDER = ["energetic", "calm", "curious", "dramatic"]


def resolve_tone() -> str:
    """
    Resolve the active narrator tone.

    Returns one of: 'energetic', 'calm', 'curious', 'dramatic'.
    If NARRATOR_TONE='auto', rotates daily.
    """
    tone = config.NARRATOR_TONE.lower().strip()
    if tone == "auto":
        day_of_year = datetime.now(timezone.utc).timetuple().tm_yday
        tone = _TONE_ROTATION_ORDER[day_of_year % len(_TONE_ROTATION_ORDER)]
    if tone not in _TONE_INSTRUCTIONS:
        tone = "energetic"
    return tone


def get_tone_hint(tone: str) -> str:
    """Return the prompt hint block for the given tone."""
    instruction = _TONE_INSTRUCTIONS.get(tone, _TONE_INSTRUCTIONS["energetic"])
    return (
        f"\n\n══ NARRATOR TONE ══\n"
        f"{instruction}\n"
        f"  • Apply this tone to the script field only. Code stays neutral."
    )


# ══════════════════════════════════════════════════════════════
#  PROMPT VARIANT RESOLVER  (Phase 6.5)
# ══════════════════════════════════════════════════════════════

def resolve_prompt_variant() -> str:
    """
    Resolve which prompt variant to use.

    Returns 'A' or 'B'.
    - 'A' or 'B': explicit selection
    - 'auto': A on odd days, B on even days (day-of-month)
    """
    variant = config.PROMPT_VARIANT.upper().strip()
    if variant == "AUTO":
        day = datetime.now(timezone.utc).day
        return "A" if day % 2 == 1 else "B"
    if variant == "B":
        return "B"
    return "A"


def get_system_prompt(variant: str) -> str:
    """Return the system prompt for the given variant."""
    return SYSTEM_PROMPT_B if variant == "B" else SYSTEM_PROMPT


# ══════════════════════════════════════════════════════════════
#  CONTENT TEMPLATES LIBRARY  (Phase 6.6)
# ══════════════════════════════════════════════════════════════

_TEMPLATES: list[dict] | None = None   # lazy-loaded cache


def _load_templates() -> list[dict]:
    """
    Load all template JSON files from the ``templates/`` directory.
    Returns a flat list of template dicts. Cached after first call.
    """
    global _TEMPLATES
    if _TEMPLATES is not None:
        return _TEMPLATES

    templates_dir = config.ROOT_DIR / "templates"
    _TEMPLATES = []
    if not templates_dir.is_dir():
        return _TEMPLATES

    for fp in sorted(templates_dir.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(data, list):
                _TEMPLATES.extend(data)
            elif isinstance(data, dict) and "templates" in data:
                _TEMPLATES.extend(data["templates"])
        except Exception as e:
            logger.warning(f"Failed to load template {fp.name}: {e}")

    logger.info(f"Loaded {len(_TEMPLATES)} content templates from {templates_dir}")
    return _TEMPLATES


def pick_template(
    avoid_languages: list[str] | None = None,
    recent_types: list[str] | None = None,
) -> dict | None:
    """
    Select a template for inspiration, avoiding repetition.

    Returns a template dict or None if templates are unavailable or
    the 30% probability roll fails.
    """
    templates = _load_templates()
    if not templates:
        return None

    # 30% chance to use a template
    if random.random() > 0.30:
        return None

    candidates = list(templates)

    # Filter out languages we want to avoid
    if avoid_languages:
        avoid_set = {lang.lower() for lang in avoid_languages}
        filtered = [t for t in candidates if t.get("language", "").lower() not in avoid_set]
        if filtered:
            candidates = filtered

    # Prefer content types not recently used
    if recent_types and len(recent_types) >= 3:
        last_three = set(recent_types[:3])
        diverse = [t for t in candidates if t.get("content_type", "") not in last_three]
        if diverse:
            candidates = diverse

    return random.choice(candidates) if candidates else None


def build_template_hint(template: dict) -> str:
    """Build a prompt hint from a selected template."""
    lines = ["══ TEMPLATE INSPIRATION (use as starting point, add your own twist) ══"]
    if template.get("topic"):
        lines.append(f"  • Topic: {template['topic']}")
    if template.get("hook"):
        lines.append(f"  • Hook: {template['hook']}")
    if template.get("language"):
        lines.append(f"  • Language: {template['language']}")
    if template.get("content_type"):
        lines.append(f"  • Content type: {template['content_type']}")
    if template.get("code_skeleton"):
        lines.append(f"  • Code skeleton:\n    {template['code_skeleton']}")
    if template.get("category"):
        lines.append(f"  • Category: {template['category']}")
    lines.append("  • You MUST modify and expand this — do NOT copy verbatim.")
    return "\n".join(lines)

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


def generate_content(
    avoid_languages: list[str] | None = None,
    series_context: dict | None = None,
) -> dict:
    """
    Generate content using Gemini Pro.

    Supports two modes via config.CONTENT_MODE:
    - "coding_tips": coding tip/quiz/before_after (original)
    - "visual_ui":   visual UI/animation showcase (Phase 11)

    Returns a dict with keys: title, script, code, language, hashtags,
    plus metadata: prompt_variant, narrator_tone, template_used.
    Raises RuntimeError after MAX_RETRIES failed attempts.
    """
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    client = genai.Client(api_key=config.GEMINI_API_KEY)

    # ── Phase 11: Branch berdasarkan CONTENT_MODE ─────────────
    is_visual_ui = config.CONTENT_MODE == "visual_ui"

    # ── Resolve prompt variant (Phase 6.5) ────────────────────
    variant = resolve_prompt_variant()
    if is_visual_ui:
        active_prompt = SYSTEM_PROMPT_VISUAL_UI
    else:
        active_prompt = get_system_prompt(variant)
    logger.info(f"Prompt variant: {variant}")

    # ── Resolve narrator tone (Phase 6.7) ─────────────────────
    tone = resolve_tone()
    tone_hint = get_tone_hint(tone)
    logger.info(f"Narrator tone: {tone}")

    # ── Build prompt with deduplication context ───────────────
    past_topics = get_past_topics(limit=50)
    if past_topics:
        history_text = "\n".join(
            f"- [{t.get('language', '?')}] {t.get('title', t.get('topic', ''))}"
            for t in past_topics
        )
    else:
        history_text = "(None yet — this is the first video! Pick something exciting.)"

    # Language balancing hint (Phase 3.3)
    lang_hint = ""
    if avoid_languages:
        lang_hint = (
            f"\n\n══ LANGUAGE BALANCING ══\n"
            f"These languages have been used too frequently recently: "
            f"{', '.join(avoid_languages)}.\n"
            f"Please pick a DIFFERENT language to maintain variety."
        )

    # Trending topics hint (Phase 6.1) — optional, enabled via ENABLE_TRENDING=1
    trending_hint = ""
    if config.ENABLE_TRENDING == "1":
        try:
            from src.trending import get_trending_topics
            trending = get_trending_topics(api_key=config.YOUTUBE_API_KEY)
            if trending:
                topics_list = "\n".join(f"  • {t}" for t in trending)
                trending_hint = (
                    f"\n\n══ TRENDING TOPICS (optional inspiration) ══\n"
                    f"These coding topics are currently trending:\n"
                    f"{topics_list}\n"
                    f"You MAY use one as inspiration, but it's optional. "
                    f"Prioritize uniqueness and beginner-friendliness above all."
                )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Trending topics fetch skipped: {e}")

    # Analytics feedback hint (Phase 6.2) — enabled via ENABLE_YT_ANALYTICS=1
    analytics_hint = ""
    if config.ENABLE_YT_ANALYTICS == "1":
        try:
            from src.yt_analytics import get_best_content_type, get_best_language
            best_type = get_best_content_type()
            best_lang = get_best_language()
            hints: list[str] = []
            if best_type:
                hints.append(
                    f'content_type "{best_type}" tends to get the most views on this channel'
                )
            if best_lang:
                hints.append(
                    f'language "{best_lang}" tends to get the most views on this channel'
                )
            if hints:
                analytics_hint = (
                    "\n\n══ PERFORMANCE FEEDBACK (optional guidance) ══\n"
                    + "\n".join(f"  • {h}" for h in hints)
                    + "\n  Use these as loose guidance — don't repeat the same topic every time."
                )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Analytics hint skipped: {e}")

    # Series context hint (Phase 6.4) — injected when content is part of a series
    series_hint = ""
    if series_context:
        try:
            ep_num  = series_context.get("episode", 1)
            ep_tot  = series_context.get("total", 1)
            s_theme = series_context.get("theme", "")
            s_topic = series_context.get("topic", "")
            s_ctype = series_context.get("content_type", "")
            s_lang  = series_context.get("language", "")
            lines = [
                f"  • This is episode {ep_num} of {ep_tot} in the series: \"{s_theme}\"",
            ]
            if s_topic:
                lines.append(f"  • Suggested topic: {s_topic}")
            if s_ctype:
                lines.append(f"  • Use content_type: \"{s_ctype}\"")
            if s_lang:
                lines.append(f"  • Use language: {s_lang}")
            lines.append(
                "  • The content should stand alone but feel connected to the series theme."
            )
            series_hint = (
                "\n\n══ SERIES CONTEXT ══\n"
                + "\n".join(lines)
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Series context hint skipped: {e}")

    # Narration language instruction (Phase 6.3) — enabled via CONTENT_LANGUAGE=id
    narration_lang_hint = ""
    if config.CONTENT_LANGUAGE == "id":
        narration_lang_hint = (
            "\n\n══ LANGUAGE INSTRUCTION ══\n"
            "  • Write the ENTIRE narration (script) in natural, casual Bahasa Indonesia.\n"
            "  • Use informal, friendly tones: 'Tau gak sih...', 'Nih, tips kece:', "
            "'Yuk kita lihat...', 'Gampang banget kan?'\n"
            "  • Keep ALL code identifiers, keywords, and library names in English.\n"
            "  • The title field may stay in English for SEO searchability."
        )

    # Content template hint (Phase 6.6) — 30% chance to inject a template
    template_hint = ""
    template_used = None
    try:
        from src.db import get_language_frequency
        _freq = get_language_frequency()
        recent_types = _freq.get("recent_types", [])
    except Exception:
        recent_types = []
    selected_template = pick_template(
        avoid_languages=avoid_languages,
        recent_types=recent_types,
    )
    if selected_template:
        template_hint = "\n\n" + build_template_hint(selected_template)
        template_used = selected_template.get("topic", "unknown")
        logger.info(f"Template selected: {template_used}")

    # Phase 11.4 — Self-Improving Prompt (Performance Feedback)
    performance_hint = ""
    if config.ENABLE_YT_ANALYTICS == "1":
        try:
            from src.db import get_top_performing_topics
            top_performers = get_top_performing_topics(limit=2, content_mode=config.CONTENT_MODE)
            if top_performers:
                examples_text = ""
                for i, p in enumerate(top_performers, 1):
                    examples_text += f"\nExample {i} (Highly successful):\n"
                    examples_text += f"Title: {p.get('title')}\n"
                    examples_text += f"Script: {p.get('script')}\n"
                    
                performance_hint = (
                    f"\n\n══ TOP PERFORMING EXAMPLES ══\n"
                    f"Study these top-performing past videos to understand what works:\n"
                    f"{examples_text}\n"
                    f"Use these as inspiration for QUALITY pacing and structure, but create an entirely NEW topic."
                )
        except Exception as e:
            logger.warning(f"Performance examples skipped: {e}")

    prompt_ending = (
        "Now generate a brand new, stunning visual UI component." if is_visual_ui 
        else "Now generate a brand new, unique coding tip."
    )

    user_prompt = f"""{active_prompt}

══ PREVIOUSLY GENERATED TOPICS (DO NOT REPEAT ANY) ══
{history_text}{lang_hint}{trending_hint}{analytics_hint}{series_hint}{narration_lang_hint}{tone_hint}{template_hint}{performance_hint}

{prompt_ending} Pick a DIFFERENT language and category from the ones listed above. Return valid JSON only."""

    # ── Pilih schema berdasarkan mode ──────────────────────────
    active_schema = _VISUAL_UI_RESPONSE_SCHEMA if is_visual_ui else _RESPONSE_SCHEMA
    max_tokens = 4096 if is_visual_ui else 2048  # Visual UI butuh lebih banyak token

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
                    response_schema=active_schema,
                    temperature=0.9,
                    top_p=0.95,
                    max_output_tokens=max_tokens,
                ),
            )

            # Parse JSON response (with repair for common LLM issues)
            raw_text = response.text.strip()
            logger.debug(f"Raw Gemini response ({len(raw_text)} chars): {raw_text[:500]}")
            data = _repair_json(raw_text)

            # Validate required fields
            if is_visual_ui:
                _validate_visual_ui_content(data)
            else:
                _validate_content(data)

            # Attach generation metadata (Phase 6.5 / 6.6 / 6.7)
            data["prompt_variant"] = variant
            data["narrator_tone"] = tone
            data["content_mode"] = config.CONTENT_MODE
            if template_used:
                data["template_used"] = template_used

            # Phase 11: Map visual UI fields ke field standar untuk backward compat
            if is_visual_ui:
                data["code"] = data.get("display_code", "")
                data["language"] = data.get("language", "html")

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

    # Phase 8.1: Try fallback model before giving up
    fallback_result = _try_fallback_model(
        client, user_prompt, variant, tone, template_used,
    )
    if fallback_result is not None:
        return fallback_result

    raise RuntimeError(
        f"Failed to generate content after {MAX_RETRIES} attempts. "
        f"Last error: {last_error}"
    )


def _try_fallback_model(client, user_prompt, variant, tone, template_used):
    """
    Phase 8.1: Attempt content generation with the fallback model.

    Called when all retries with the primary model have been exhausted.
    Returns the generated content dict, or raises RuntimeError.
    """
    fallback_model = config.GEMINI_FALLBACK_MODEL
    if not fallback_model or fallback_model == config.GEMINI_MODEL:
        return None  # No distinct fallback configured

    logger.warning(
        f"Primary model '{config.GEMINI_MODEL}' failed. "
        f"Trying fallback model '{fallback_model}'..."
    )

    try:
        response = client.models.generate_content(
            model=fallback_model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_RESPONSE_SCHEMA,
                temperature=0.9,
                top_p=0.95,
                max_output_tokens=2048,
            ),
        )
        raw_text = response.text.strip()
        data = _repair_json(raw_text)
        _validate_content(data)

        data["prompt_variant"] = variant
        data["narrator_tone"] = tone
        data["fallback_model_used"] = fallback_model
        if template_used:
            data["template_used"] = template_used

        logger.info(
            f"Fallback model succeeded: [{data['language']}] {data['title']}"
        )
        return data
    except Exception as e:
        logger.error(f"Fallback model also failed: {e}")
        return None


def _validate_content(data: dict) -> None:
    """Validate the LLM output has all required fields with sane values."""
    required = ["title", "script", "code", "language", "hashtags"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Missing fields in LLM response: {missing}")

    if not data["code"].strip():
        raise ValueError("Code snippet is empty")

    word_count = len(data["script"].split())
    if word_count < 25:
        raise ValueError(f"Script too short: {word_count} words (minimum 25)")

    if not isinstance(data["hashtags"], list) or len(data["hashtags"]) < 3:
        raise ValueError("Need at least 3 hashtags")

    # Ensure title ends with #Shorts
    if "#Shorts" not in data["title"] and "#shorts" not in data["title"]:
        data["title"] = data["title"].rstrip() + " #Shorts"

    # Normalize language name
    data["language"] = data["language"].lower().strip()

    # Normalize and validate content_type
    ct = data.get("content_type", "tip").lower().strip()
    if ct not in ("tip", "quiz", "before_after"):
        ct = "tip"
    data["content_type"] = ct

    # Ensure type-specific fields have defaults
    if ct == "quiz" and not data.get("quiz_answer"):
        data["quiz_answer"] = ""
    if ct == "before_after" and not data.get("code_before"):
        data["code_before"] = ""


def _validate_visual_ui_content(data: dict) -> None:
    """Validate visual UI content from LLM (Phase 11).
    
    Provides sensible defaults for optional fields that Gemini
    sometimes omits, instead of raising hard errors.
    """
    # Hard-required: at minimum we need title, script, and html_code
    hard_required = ["title", "script", "html_code"]
    missing = [k for k in hard_required if k not in data or not data[k]]
    if missing:
        raise ValueError(f"Missing fields in visual UI response: {missing}")

    if not data["html_code"].strip():
        raise ValueError("html_code is empty")

    # Soft-required: provide defaults if Gemini didn't include them
    if "display_code" not in data or not data.get("display_code", "").strip():
        # Extract a representative snippet from html_code as fallback
        html = data["html_code"]
        # Try to find <style> or <script> content for display_code
        import re
        style_match = re.search(r'<style[^>]*>(.*?)</style>', html, re.DOTALL)
        script_match = re.search(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
        if style_match:
            snippet = style_match.group(1).strip()
        elif script_match:
            snippet = script_match.group(1).strip()
        else:
            # Take the first 10 lines of the html
            snippet = '\n'.join(html.strip().splitlines()[:10])
        data["display_code"] = snippet
        logger.info("display_code was missing — auto-extracted from html_code")
        
    # CRITICAL FIX (Phase 12.2): map display_code to 'code' because the pipeline (main.py, renderer)
    # strictly looks for content["code"] to put in the editor panel.
    data["code"] = data["display_code"]

    if "hashtags" not in data or not isinstance(data.get("hashtags"), list) or len(data.get("hashtags", [])) < 1:
        data["hashtags"] = ["#WebDev", "#CSS", "#Frontend", "#JavaScript", "#Coding"]
        logger.info("hashtags were missing — using default set")

    word_count = len(data["script"].split())
    if word_count < 20:
        raise ValueError(f"Script too short: {word_count} words (minimum 20)")

    if len(data["hashtags"]) < 3:
        # Pad hashtags to minimum 3
        defaults = ["#WebDev", "#CSS", "#Frontend", "#JavaScript", "#Coding"]
        while len(data["hashtags"]) < 3:
            for d in defaults:
                if d not in data["hashtags"]:
                    data["hashtags"].append(d)
                    break

    # Ensure title ends with #Shorts
    if "#Shorts" not in data["title"] and "#shorts" not in data["title"]:
        data["title"] = data["title"].rstrip() + " #Shorts"

    # Normalize content_type — include interactive_component (Phase 11.6)
    ct = data.get("content_type", "creative_ui").lower().strip()
    valid_types = {
        "landing_page", "login_page", "portfolio",
        "animation", "interactive_component", "creative_ui",
    }
    if ct not in valid_types:
        ct = "creative_ui"
    data["content_type"] = ct

    # Normalize language
    data["language"] = data.get("language", "html").lower().strip()

    # Default ui_category
    if not data.get("ui_category"):
        data["ui_category"] = ct.replace("_", " ").title()
