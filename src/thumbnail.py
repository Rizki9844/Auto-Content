"""
Thumbnail generator — Phase 4.6 + Phase 9.5 AI upgrade.

Generates a 1280×720 YouTube thumbnail for each video.

Two modes (controlled by config.THUMBNAIL_STYLE):
  - "pillow" (default): Pure Pillow-based rendering (Phase 4.6)
  - "ai":   AI-generated background via Stability AI + Pillow text overlay (Phase 9.5)

Features (AI mode):
  - Generates background using Stability AI (stable-diffusion-xl-1024-v1-0)
  - Prompt auto-generated from language + content context
  - Background cache: same language = same background (saves API calls)
  - Falls back to Pillow-only mode if AI API fails

Usage:
    from src.thumbnail import generate_thumbnail, upload_thumbnail

    path = generate_thumbnail(
        title="Python Dict Comprehension",
        language="python",
        code="result = {k: v for k, v in items}",
        output_path=Path("output/thumb.png"),
    )
    upload_thumbnail(youtube_video_id="abc123", image_path=path)
"""
from __future__ import annotations

import logging
import textwrap
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pygments import lex
from pygments.lexers import get_lexer_by_name, TextLexer

from src import config

logger = logging.getLogger(__name__)

# ── Thumbnail dimensions ──────────────────────────────────────
THUMB_W = 1280
THUMB_H = 720

# ── Layout constants ──────────────────────────────────────────
_PAD        = 48
_CODE_TOP   = 340    # y where code preview starts
_CODE_LEFT  = 52
_CODE_RIGHT = THUMB_W - 52
_CODE_H     = 300    # height of code pane

# Language display: emoji + pretty name
_LANG_DISPLAY: dict[str, tuple[str, str]] = {
    "python":     ("🐍", "Python"),
    "javascript": ("🌐", "JavaScript"),
    "typescript": ("📘", "TypeScript"),
    "go":         ("🐹", "Go"),
    "rust":       ("🦀", "Rust"),
    "java":       ("☕", "Java"),
    "cpp":        ("⚙️", "C++"),
    "c":          ("⚙️", "C"),
    "kotlin":     ("💜", "Kotlin"),
    "swift":      ("🦅", "Swift"),
    "ruby":       ("💎", "Ruby"),
    "php":        ("🐘", "PHP"),
    "bash":       ("🖥️", "Bash"),
    "sql":        ("🗄️", "SQL"),
    "html":       ("🌍", "HTML"),
    "css":        ("🎨", "CSS"),
    "json":       ("📋", "JSON"),
    "yaml":       ("📄", "YAML"),
}


# ══════════════════════════════════════════════════════════════
#  Internal helpers
# ══════════════════════════════════════════════════════════════

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _make_gradient(w: int, h: int, top_rgb: tuple, bottom_rgb: tuple) -> Image.Image:
    """Create a vertical gradient PIL image."""
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for i, (a, b) in enumerate(zip(top_rgb, bottom_rgb)):
        col = np.linspace(a, b, h, dtype=np.float32)
        arr[:, :, i] = np.broadcast_to(col[:, None], (h, w))
    return Image.fromarray(arr)


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _get_syntax_colors() -> dict:
    """Get syntax color dict from the active theme."""
    try:
        from src.theme_loader import build_syntax_colors, get_active_theme
        return build_syntax_colors(get_active_theme())
    except Exception:
        # Fallback: use renderer's module-level SYNTAX_COLORS
        from src.renderer import SYNTAX_COLORS
        return SYNTAX_COLORS


# ══════════════════════════════════════════════════════════════
#  AI BACKGROUND GENERATION  (Phase 9.5)
# ══════════════════════════════════════════════════════════════

# Cache directory for AI-generated backgrounds
_BG_CACHE_DIR = config.OUTPUT_DIR / "thumb_bg_cache"


def _get_ai_bg_prompt(language: str) -> str:
    """Generate a prompt for Stability AI based on language."""
    lang_themes = {
        "python": "neon green Python snake patterns",
        "javascript": "neon yellow JavaScript energy waves",
        "typescript": "electric blue TypeScript angular shapes",
        "go": "teal Go gopher geometric patterns",
        "rust": "orange Rust crab metallic textures",
        "java": "warm red Java coffee steam patterns",
        "cpp": "purple C++ circuit board patterns",
    }
    theme = lang_themes.get(language.lower(), f"neon {language} code patterns")
    return (
        f"Dark coding wallpaper, {theme}, "
        "dark background, subtle glow, minimalist, abstract, "
        "high quality, 1280x720, digital art, no text"
    )


def _get_cached_bg(language: str) -> Path | None:
    """Return cached background for this language if it exists."""
    cache_path = _BG_CACHE_DIR / f"{language.lower()}_bg.png"
    if cache_path.exists() and cache_path.stat().st_size > 1000:
        return cache_path
    return None


def _save_bg_cache(language: str, image: Image.Image) -> Path:
    """Cache an AI-generated background."""
    _BG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _BG_CACHE_DIR / f"{language.lower()}_bg.png"
    image.save(str(cache_path), "PNG")
    logger.info(f"Cached AI background: {cache_path}")
    return cache_path


def generate_ai_background(language: str) -> Image.Image | None:
    """
    Generate a thumbnail background using Stability AI.

    Uses stable-diffusion-xl-1024-v1-0 via REST API.
    Returns a 1280×720 PIL Image, or None if generation fails.
    """
    api_key = config.STABILITY_API_KEY
    if not api_key:
        logger.warning("STABILITY_API_KEY not set — cannot generate AI background")
        return None

    # Check cache first
    cached = _get_cached_bg(language)
    if cached:
        logger.info(f"Using cached AI background for {language}")
        return Image.open(str(cached))

    prompt = _get_ai_bg_prompt(language)
    logger.info(f"Generating AI background: {prompt[:80]}...")

    try:
        import requests

        response = requests.post(
            "https://api.stability.ai/v1/generation/"
            "stable-diffusion-xl-1024-v1-0/text-to-image",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "text_prompts": [{"text": prompt, "weight": 1.0}],
                "cfg_scale": 7,
                "width": 1280,
                "height": 704,  # closest supported resolution to 720
                "steps": 30,
                "samples": 1,
                "style_preset": "neon-punk",
            },
            timeout=60,
        )

        if response.status_code != 200:
            logger.warning(
                f"Stability AI request failed ({response.status_code}): "
                f"{response.text[:200]}"
            )
            return None

        data = response.json()
        artifacts = data.get("artifacts", [])
        if not artifacts:
            logger.warning("Stability AI returned no artifacts")
            return None

        import base64
        import io

        img_data = base64.b64decode(artifacts[0]["base64"])
        img = Image.open(io.BytesIO(img_data)).convert("RGB")

        # Resize to exact thumbnail dimensions
        img = img.resize((THUMB_W, THUMB_H), Image.Resampling.LANCZOS)

        # Cache for future use
        _save_bg_cache(language, img)

        return img

    except Exception as exc:
        logger.warning(f"AI background generation failed: {exc}")
        return None


# ══════════════════════════════════════════════════════════════
#  Public API
# ══════════════════════════════════════════════════════════════

def generate_thumbnail(
    title: str,
    language: str,
    code: str,
    output_path: Path | None = None,
    channel_name: str | None = None,
) -> Path:
    """
    Generate a 1280×720 PNG thumbnail.

    Args:
        title:       Video title (max ~55 chars before wrapping).
        language:    Programming language key (e.g. "python").
        code:        Code snippet (first 8 lines used).
        output_path: Where to save the PNG. Defaults to output/thumbnail.png.
        channel_name: Channel branding. Defaults to config.CHANNEL_NAME.

    Returns:
        Path to the saved PNG file.
    """
    from src.theme_loader import get_active_theme, patch_config
    theme = get_active_theme()
    patch_config(theme)

    if output_path is None:
        output_path = config.OUTPUT_DIR / "thumbnail.png"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    channel = channel_name or config.CHANNEL_NAME
    lang_key = language.lower()
    lang_emoji, lang_name = _LANG_DISPLAY.get(lang_key, ("💻", language.title()))

    syntax_colors = _get_syntax_colors()

    # ── Build image ────────────────────────────────────────────
    # Phase 9.5: Use AI background if THUMBNAIL_STYLE == "ai"
    ai_bg = None
    if config.THUMBNAIL_STYLE == "ai":
        ai_bg = generate_ai_background(lang_key)

    if ai_bg is not None:
        img = ai_bg.convert("RGB")
        # Darken AI background slightly for text readability
        from PIL import ImageEnhance
        img = ImageEnhance.Brightness(img).enhance(0.6)
    else:
        img = _make_gradient(
            THUMB_W, THUMB_H,
            tuple(config.BG_GRADIENT_TOP),
            tuple(config.BG_GRADIENT_BOTTOM),
        ).convert("RGB")
    draw = ImageDraw.Draw(img)

    # ── Fonts ──────────────────────────────────────────────────
    f_title   = _load_font(config.FONT_BOLD,    72)
    f_lang    = _load_font(config.FONT_BOLD,    36)
    f_code    = _load_font(config.FONT_REGULAR, 26)
    f_linenum = _load_font(config.FONT_REGULAR, 22)
    f_water   = _load_font(config.FONT_REGULAR, 24)

    # ── Accent bar (top) ───────────────────────────────────────
    left_rgb  = _hex_to_rgb(config.ACCENT_GRADIENT_LEFT)
    right_rgb = _hex_to_rgb(config.ACCENT_GRADIENT_RIGHT)
    for x in range(THUMB_W):
        t = x / THUMB_W
        r = int(left_rgb[0] + (right_rgb[0] - left_rgb[0]) * t)
        g = int(left_rgb[1] + (right_rgb[1] - left_rgb[1]) * t)
        b = int(left_rgb[2] + (right_rgb[2] - left_rgb[2]) * t)
        draw.line([(x, 0), (x, 8)], fill=(r, g, b))

    # ── Language badge ─────────────────────────────────────────
    badge_text = f"{lang_emoji}  {lang_name}"
    draw.text((_PAD, _PAD + 10), badge_text, font=f_lang,
              fill=config.ACCENT_GRADIENT_LEFT)

    # ── Title (wrapped) ────────────────────────────────────────
    # Strip "#Shorts" from display title
    display_title = title.replace("#Shorts", "").replace("#shorts", "").strip()
    wrapped = textwrap.fill(display_title, width=26)
    title_y = _PAD + 70
    for line in wrapped.split("\n"):
        draw.text((_PAD, title_y), line, font=f_title,
                  fill=config.INTRO_TITLE_COLOR)
        bbox = f_title.getbbox(line)
        title_y += (bbox[3] - bbox[1]) + 10

    # ── Code preview panel ────────────────────────────────────
    code_lines = code.rstrip().split("\n")[:8]   # max 8 lines
    panel_rect = [(_CODE_LEFT - 12, _CODE_TOP - 12),
                  (_CODE_RIGHT + 12, _CODE_TOP + _CODE_H + 12)]
    draw.rounded_rectangle(panel_rect, radius=12,
                            fill=config.CODE_BG)

    # Draw code with syntax highlighting
    code_snippet = "\n".join(code_lines)
    try:
        lexer = get_lexer_by_name(lang_key)
    except Exception:
        lexer = TextLexer()
    tokens = list(lex(code_snippet, lexer))

    line_h = 34
    char_w_bbox = f_code.getbbox("M")
    char_w = (char_w_bbox[2] - char_w_bbox[0]) or 15

    cur_x = _CODE_LEFT + 50  # leave room for line nums
    cur_y = _CODE_TOP
    line_no = 1

    # Draw first line number
    draw.text((_CODE_LEFT, cur_y), str(line_no), font=f_linenum,
              fill=config.LINE_NUM_COLOR)

    for ttype, value in tokens:
        color = syntax_colors.get(ttype, config.DEFAULT_TEXT_COLOR)
        if isinstance(color, str) and color.startswith("#"):
            fill_color = color
        else:
            fill_color = config.DEFAULT_TEXT_COLOR

        for char in value:
            if cur_y >= _CODE_TOP + _CODE_H - line_h:
                break  # clip overflow
            if char == "\n":
                cur_y += line_h
                cur_x = _CODE_LEFT + 50
                line_no += 1
                if cur_y < _CODE_TOP + _CODE_H - line_h:
                    draw.text((_CODE_LEFT, cur_y), str(line_no),
                              font=f_linenum, fill=config.LINE_NUM_COLOR)
                continue
            if cur_x + char_w > _CODE_RIGHT:
                continue   # skip overflowing chars
            draw.text((cur_x, cur_y), char, font=f_code, fill=fill_color)
            cur_x += char_w

    # ── Channel watermark ──────────────────────────────────────
    draw.text(
        (THUMB_W - _PAD, THUMB_H - _PAD),
        channel,
        font=f_water,
        fill=config.WATERMARK_COLOR,
        anchor="rb",
    )

    img.save(str(output_path), "PNG", optimize=True)
    logger.info(f"Thumbnail saved: {output_path} ({THUMB_W}×{THUMB_H})")
    return output_path


def upload_thumbnail(
    youtube_video_id: str,
    image_path: Path,
    youtube_service=None,
) -> bool:
    """
    Upload a thumbnail to YouTube via ``thumbnails.set()``.

    Args:
        youtube_video_id: The YouTube video ID to attach the thumbnail to.
        image_path:       Local path to the PNG thumbnail.
        youtube_service:  Pre-built googleapiclient Resource object.
                          If None, builds one from config credentials.

    Returns:
        True on success, False on failure.
    """
    try:
        from googleapiclient.http import MediaFileUpload

        if youtube_service is None:
            from src.uploader_youtube import _build_youtube_service
            youtube_service = _build_youtube_service()

        media = MediaFileUpload(str(image_path), mimetype="image/png",
                                resumable=True)
        request = youtube_service.thumbnails().set(
            videoId=youtube_video_id,
            media_body=media,
        )
        response = request.execute()
        logger.info(f"Thumbnail uploaded for {youtube_video_id}: {response}")
        return True
    except Exception as exc:
        logger.warning(f"Thumbnail upload failed (non-critical): {exc}")
        return False
