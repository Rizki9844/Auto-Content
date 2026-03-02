"""
Theme loader — Phase 4.4.

Loads a color/syntax theme from ``themes/<name>.json`` and patches the
``src.config`` module in-place so the renderer picks up the new values
without any changes to its own source.

Available themes (bundled):
    github_dark   — default (matches original hardcoded colors)
    monokai       — Monokai Pro warm dark
    dracula       — Dracula purple-tinted dark

Environment variables:
    ACTIVE_THEME          name of the theme to use (default: "github_dark")
    AUTO_ROTATE_THEMES    "1" to rotate themes daily (overrides ACTIVE_THEME)
    THEME_ROTATION_LIST   comma-separated list of themes to rotate through
                          (default: "github_dark,monokai,dracula")
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from pygments.token import Token

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────
_THEMES_DIR = Path(__file__).resolve().parent.parent / "themes"

# ── Pygments token → theme syntax key mapping ─────────────────
_TOKEN_KEY_MAP = {
    Token.Keyword:                  "keyword",
    Token.Keyword.Constant:         "keyword_constant",
    Token.Keyword.Declaration:      "keyword",
    Token.Keyword.Namespace:        "keyword",
    Token.Keyword.Pseudo:           "keyword",
    Token.Keyword.Reserved:         "keyword",
    Token.Keyword.Type:             "keyword_type",
    Token.Name.Function:            "name_function",
    Token.Name.Function.Magic:      "name_function",
    Token.Name.Class:               "name_class",
    Token.Name.Decorator:           "name_decorator",
    Token.Name.Builtin:             "name_builtin",
    Token.Name.Builtin.Pseudo:      "name_builtin_pseudo",
    Token.Name.Tag:                 "name_tag",
    Token.Name.Attribute:           "name_attribute",
    Token.Name.Variable:            "name_variable",
    Token.Name.Constant:            "name_constant",
    Token.Literal.String:           "string",
    Token.Literal.String.Doc:       "string_doc",
    Token.Literal.String.Interpol:  "string",
    Token.Literal.String.Escape:    "string_escape",
    Token.Literal.String.Affix:     "string_affix",
    Token.Literal.Number:           "number",
    Token.Literal.Number.Integer:   "number",
    Token.Literal.Number.Float:     "number",
    Token.Comment:                  "comment",
    Token.Comment.Single:           "comment",
    Token.Comment.Multiline:        "comment",
    Token.Comment.Hashbang:         "comment",
    Token.Comment.Preproc:          "comment_preproc",
    Token.Operator:                 "operator",
    Token.Operator.Word:            "operator",
    Token.Punctuation:              "punctuation",
    Token.Name:                     "default",
    Token.Text:                     "default",
    Token.Text.Whitespace:          "default",
}


# ══════════════════════════════════════════════════════════════
#  Public API
# ══════════════════════════════════════════════════════════════

def list_themes() -> list[str]:
    """Return sorted list of available theme names (JSON file stems)."""
    return sorted(p.stem for p in _THEMES_DIR.glob("*.json"))


def load_theme(name: str) -> dict:
    """
    Load a theme by name from ``themes/<name>.json``.

    Falls back to ``github_dark`` if the file is not found.

    Args:
        name: Theme name (without ``.json`` extension).

    Returns:
        Parsed theme dict.
    """
    path = _THEMES_DIR / f"{name}.json"
    if not path.exists():
        logger.warning(f"Theme '{name}' not found at {path}, falling back to github_dark")
        path = _THEMES_DIR / "github_dark.json"
    with path.open(encoding="utf-8") as f:
        theme = json.load(f)
    logger.debug(f"Loaded theme: {theme.get('_name', name)}")
    return theme


def get_active_theme() -> dict:
    """
    Determine and load the active theme based on environment variables.

    Priority:
      1. ``AUTO_ROTATE_THEMES=1``  → rotate daily from ``THEME_ROTATION_LIST``
      2. ``ACTIVE_THEME`` env var  → explicit theme name
      3. Default: ``github_dark``

    Returns:
        Loaded theme dict.
    """
    import os
    if os.environ.get("AUTO_ROTATE_THEMES", "").strip() == "1":
        rotation_list = [
            t.strip()
            for t in os.environ.get(
                "THEME_ROTATION_LIST", "github_dark,monokai,dracula"
            ).split(",")
            if t.strip()
        ]
        if rotation_list:
            idx = date.today().toordinal() % len(rotation_list)
            name = rotation_list[idx]
            logger.info(f"Auto-rotate: using theme '{name}' (day index {idx})")
            return load_theme(name)

    name = os.environ.get("ACTIVE_THEME", "github_dark").strip()
    return load_theme(name)


def build_syntax_colors(theme: dict) -> dict:
    """
    Build a Pygments ``Token → hex_color`` dict from a theme dict.

    Args:
        theme: Loaded theme dict (from ``load_theme()``).

    Returns:
        Dict mapping Pygments Token types to hex color strings.
    """
    syntax = theme.get("syntax", {})
    result: dict = {}
    for token, key in _TOKEN_KEY_MAP.items():
        color = syntax.get(key, syntax.get("default", "#e6edf3"))
        result[token] = color
    return result


def patch_config(theme: dict) -> None:
    """
    Overwrite color constants in ``src.config`` with values from ``theme``.

    Only color-related constants are patched; font sizes, dimensions, API keys,
    and animation timing are untouched.

    This is idempotent — calling it with the same theme twice is safe.

    Args:
        theme: Loaded theme dict.
    """
    try:
        from src import config  # local import to avoid circular deps

        # ── Background ─────────────────────────────────────────
        top = theme.get("bg_gradient_top")
        bot = theme.get("bg_gradient_bottom")
        if top:
            config.BG_GRADIENT_TOP    = tuple(top)
        if bot:
            config.BG_GRADIENT_BOTTOM = tuple(bot)

        # ── Chrome / code editor panel ─────────────────────────
        _set(config, "CHROME_BG",         theme, "chrome_bg")
        dots = theme.get("chrome_dot_colors")
        if dots:
            config.CHROME_DOT_COLORS = tuple(dots)
        _set(config, "CODE_BG",           theme, "code_bg")
        _set(config, "LINE_HIGHLIGHT",    theme, "line_highlight")
        _set(config, "SEPARATOR",         theme, "separator")
        _set(config, "LINE_NUM_COLOR",    theme, "line_num_color")
        _set(config, "DEFAULT_TEXT_COLOR",theme, "default_text_color")
        _set(config, "CURSOR_COLOR",      theme, "cursor_color")

        # ── Subtitles / watermark ──────────────────────────────
        _set(config, "SUBTITLE_TEXT_COLOR",   theme, "subtitle_text_color")
        _set(config, "SUBTITLE_ACTIVE_COLOR", theme, "subtitle_active_color")
        _set(config, "SUBTITLE_BG_COLOR",     theme, "subtitle_bg_color")
        _set(config, "WATERMARK_COLOR",       theme, "watermark_color")
        _set(config, "PREVIEW_RUNNING_COLOR", theme, "preview_running_color")

        # ── Output panel ───────────────────────────────────────
        _set(config, "OUTPUT_BG",           theme, "output_bg")
        _set(config, "OUTPUT_HEADER_BG",    theme, "output_header_bg")
        _set(config, "OUTPUT_TEXT_COLOR",   theme, "output_text_color")
        _set(config, "OUTPUT_ERROR_COLOR",  theme, "output_error_color")
        _set(config, "OUTPUT_PROMPT_COLOR", theme, "output_prompt_color")

        # ── Intro / outro accent colors ────────────────────────
        _set(config, "ACCENT_GRADIENT_LEFT",  theme, "accent_gradient_left")
        _set(config, "ACCENT_GRADIENT_RIGHT", theme, "accent_gradient_right")
        _set(config, "INTRO_TITLE_COLOR",     theme, "intro_title_color")
        _set(config, "INTRO_SUBTITLE_COLOR",  theme, "intro_subtitle_color")
        _set(config, "OUTRO_CTA_COLOR",       theme, "outro_cta_color")

        logger.info(f"Config patched with theme: {theme.get('_name', '?')}")
    except Exception as exc:
        logger.warning(f"patch_config failed (non-critical): {exc}")


def _set(obj, attr: str, theme: dict, key: str) -> None:
    """Set obj.attr = theme[key] if key exists in theme."""
    val = theme.get(key)
    if val is not None:
        setattr(obj, attr, val)
