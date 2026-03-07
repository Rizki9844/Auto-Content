"""Video frame renderer v3 — Pillow + Pygments.
Enhanced with:
  - Intro title card with gradient accent
  - Multiple content types (tip, quiz, before_after)
  - Terminal output panel for code execution results
  - Animated outro with subscribe CTA pulse (Phase 5.8)
  - Per-line slide-in animation (Phase 5.5)
  - Redesigned preview panels per content type (Phase 5.6)
  - Adaptive multi-line karaoke subtitles (Phase 5.7)
  - Subtle background particle effects (Phase 5.9)
  - Channel branding watermark
  - Theme system support (Phase 4.4)
"""
import logging
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pygments import lex
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.token import Token

from src import config

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
#  SYNTAX HIGHLIGHTING — GitHub Dark Theme
# ══════════════════════════════════════════════════════════════
SYNTAX_COLORS: dict = {
    Token.Keyword:                  "#ff7b72",
    Token.Keyword.Constant:         "#79c0ff",
    Token.Keyword.Declaration:      "#ff7b72",
    Token.Keyword.Namespace:        "#ff7b72",
    Token.Keyword.Pseudo:           "#ff7b72",
    Token.Keyword.Reserved:         "#ff7b72",
    Token.Keyword.Type:             "#ffb86c",      # warmer orange
    Token.Name.Function:            "#e2b5ff",      # brighter purple
    Token.Name.Function.Magic:      "#e2b5ff",
    Token.Name.Class:               "#ffb86c",      # warmer orange
    Token.Name.Decorator:           "#e2b5ff",
    Token.Name.Builtin:             "#ffb86c",      # warmer orange
    Token.Name.Builtin.Pseudo:      "#79c0ff",
    Token.Name.Tag:                 "#7ee787",
    Token.Name.Attribute:           "#79c0ff",
    Token.Name.Variable:            "#ffb86c",
    Token.Name.Constant:            "#79c0ff",
    Token.Literal.String:           "#79dafa",      # brighter blue
    Token.Literal.String.Doc:       "#8b949e",
    Token.Literal.String.Interpol:  "#79dafa",
    Token.Literal.String.Escape:    "#79c0ff",
    Token.Literal.String.Affix:     "#ff7b72",
    Token.Literal.Number:           "#79c0ff",
    Token.Literal.Number.Integer:   "#79c0ff",
    Token.Literal.Number.Float:     "#79c0ff",
    Token.Comment:                  "#8b949e",
    Token.Comment.Single:           "#8b949e",
    Token.Comment.Multiline:        "#8b949e",
    Token.Comment.Hashbang:         "#8b949e",
    Token.Comment.Preproc:          "#ff7b72",
    Token.Operator:                 "#ff7b72",
    Token.Operator.Word:            "#ff7b72",
    Token.Punctuation:              "#e6edf3",
    Token.Name:                     "#e6edf3",
    Token.Text:                     "#e6edf3",
    Token.Text.Whitespace:          "#e6edf3",
}

EXT_MAP = {
    "python": ".py", "javascript": ".js", "typescript": ".ts",
    "css": ".css", "html": ".html", "sql": ".sql", "bash": ".sh",
    "go": ".go", "rust": ".rs", "java": ".java", "cpp": ".cpp",
    "c": ".c", "ruby": ".rb", "php": ".php", "swift": ".swift",
    "kotlin": ".kt", "json": ".json", "yaml": ".yml", "tsx": ".tsx",
    "jsx": ".jsx",
}

# Content type labels for intro
CONTENT_TYPE_LABELS = {
    "tip": "💡 CODING TIP",
    "quiz": "🧠 CODE QUIZ",
    "before_after": "✨ BEFORE → AFTER",
}


# ══════════════════════════════════════════════════════════════
#  DYNAMIC FONT SCALING  (Phase 3.5)
# ══════════════════════════════════════════════════════════════

# Thresholds for triggering dynamic scaling
_MAX_LINES_DEFAULT_FONT = 12
_MAX_CHARS_PER_LINE_DEFAULT = 45
_MIN_FONT_SIZE = 16
_MAX_FONT_SIZE = 28  # never go above this


def compute_dynamic_font_size(code: str, base_size: int = 24) -> int:
    """
    Compute optimal font size for code so it fits in the editor panel.

    Rules:
      - If lines > 12 or max line > 45 chars: shrink font.
      - Minimum font: 16px.  Maximum: 28px.
      - Scaling is continuous (not step-function).

    Args:
        code: The code snippet to render.
        base_size: Default font size from config.

    Returns:
        Adjusted font size (int).
    """
    lines = code.rstrip().split("\n")
    num_lines = len(lines)
    max_line_len = max((len(line) for line in lines), default=0)

    font_size = base_size

    # Shrink for too many lines
    if num_lines > _MAX_LINES_DEFAULT_FONT:
        line_ratio = _MAX_LINES_DEFAULT_FONT / num_lines
        font_size = int(font_size * line_ratio)

    # Shrink for very long lines
    if max_line_len > _MAX_CHARS_PER_LINE_DEFAULT:
        char_ratio = _MAX_CHARS_PER_LINE_DEFAULT / max_line_len
        candidate = int(base_size * char_ratio)
        font_size = min(font_size, candidate)

    # Clamp
    font_size = max(_MIN_FONT_SIZE, min(_MAX_FONT_SIZE, font_size))

    return font_size


def _ease_out_cubic(t: float) -> float:
    """Cubic ease-out for smooth animations."""
    return 1 - (1 - min(max(t, 0), 1)) ** 3


def _ease_in_out(t: float) -> float:
    """Ease-in-out for smooth transitions."""
    t = min(max(t, 0), 1)
    if t < 0.5:
        return 4 * t * t * t
    return 1 - (-2 * t + 2) ** 3 / 2


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert '#rrggbb' to (r, g, b) tuple."""
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _lerp_color(c1: tuple, c2: tuple, t: float) -> tuple[int, int, int]:
    """Linearly interpolate between two RGB colors."""
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


class FrameRenderer:
    """
    Pre-computes static elements and renders per-frame dynamic content.
    Supports multiple content types and output panels.
    """

    def __init__(
        self,
        code: str,
        language: str,
        word_timestamps: list,
        duration: float,
        channel_name: str | None = None,
        content_type: str = "tip",
        code_output: str | None = None,
        code_before: str | None = None,
        title: str = "",
        series_part: int = 0,
        preview_image: "Image.Image | list[Image.Image] | None" = None,
    ):
        self.code = code.rstrip()
        self.language = language.lower()
        self.duration = duration
        self.channel_name = channel_name or config.CHANNEL_NAME
        self.width = config.VIDEO_WIDTH
        self.height = config.VIDEO_HEIGHT
        self.content_type = content_type
        self.code_output = code_output
        self.code_before = code_before
        self.title = title
        self.series_part = series_part  # Phase 6.4 — 0 means not part of a series

        # Phase 10.1 & 11.2: Pre-captured visual preview image(s)
        self.preview_image = self._fit_preview_images(preview_image)

        # Apply active theme (Phase 4.4) — patches config before any rendering
        try:
            from src.theme_loader import get_active_theme, patch_config
            _theme = get_active_theme()
            patch_config(_theme)
            from src.theme_loader import build_syntax_colors
            self._syntax_colors = build_syntax_colors(_theme)
        except Exception as _te:
            logger.debug(f"Theme loader unavailable, using defaults: {_te}")
            self._syntax_colors = SYNTAX_COLORS

        # Intro/outro timing
        self.intro_end = min(config.INTRO_DURATION, duration * 0.15)
        self.outro_start = max(duration - config.OUTRO_DURATION, duration * 0.85)
        self.code_start = self.intro_end
        self.code_end = self.outro_start

        # Convert WordTimestamp objects to dicts
        self.word_timestamps = []
        for wt in word_timestamps:
            if hasattr(wt, "text"):
                self.word_timestamps.append({
                    "text": wt.text,
                    "start_s": wt.start_s,
                    "end_s": wt.end_s,
                })
            else:
                self.word_timestamps.append(wt)

        # Pre-compute everything
        self.total_chars = 0
        self.total_lines = 0
        self._load_fonts()
        self._gradient_bg = self._create_gradient_bg()
        self._tokenize_code()
        if self.code_before:
            self._tokenize_before_code()
        self._compute_char_positions()
        self._create_base_image()
        if config.INTRO_DURATION > 0:
            self._create_intro_image()
        self._create_outro_image()
        if self.code_output:
            self._prepare_output_panel()
        self._create_subtitle_groups()
        self._init_bg_particles()

        # Phase 9.2: Build code-to-narration keyword index for animated highlighting
        self._build_code_keyword_index()

        logger.info(
            f"FrameRenderer ready: type={self.content_type}, "
            f"{self.total_chars} chars, {self.total_lines} lines, "
            f"output={'yes' if self.code_output else 'no'}"
        )

    # ──────────────────────────────────────────────────────────
    #  INITIALIZATION
    # ──────────────────────────────────────────────────────────

    def _load_fonts(self):
        """Load font files and compute character metrics.
        Applies dynamic font scaling (Phase 3.5) when code is long.
        """
        # ── Dynamic font scaling (Phase 3.5) ──────────────────
        self.code_font_size = compute_dynamic_font_size(
            self.code, config.CODE_FONT_SIZE
        )
        self.line_num_font_size = max(
            14, self.code_font_size - 4
        )

        self.code_font = ImageFont.truetype(config.FONT_REGULAR, self.code_font_size)
        self.code_font_bold = ImageFont.truetype(config.FONT_BOLD, self.code_font_size)
        self.line_num_font = ImageFont.truetype(config.FONT_REGULAR, self.line_num_font_size)
        self.subtitle_font = ImageFont.truetype(config.FONT_BOLD, config.SUBTITLE_FONT_SIZE)
        self.subtitle_font_small = ImageFont.truetype(config.FONT_BOLD, 40)
        self.watermark_font = ImageFont.truetype(config.FONT_REGULAR, config.WATERMARK_FONT_SIZE)
        self.chrome_font = ImageFont.truetype(config.FONT_REGULAR, config.CHROME_FONT_SIZE)
        self.title_font = ImageFont.truetype(config.FONT_BOLD, config.TITLE_FONT_SIZE)
        self.title_sub_font = ImageFont.truetype(config.FONT_REGULAR, config.TITLE_SUB_FONT_SIZE)
        self.output_font = ImageFont.truetype(config.FONT_REGULAR, config.OUTPUT_FONT_SIZE)
        self.outro_font = ImageFont.truetype(config.FONT_BOLD, config.OUTRO_FONT_SIZE)
        self.outro_sub_font = ImageFont.truetype(config.FONT_REGULAR, config.OUTRO_SUB_FONT_SIZE)

        # Phase 12: Title header fonts (big gradient title)
        self.title_header_font = ImageFont.truetype(config.FONT_BOLD, config.TITLE_HEADER_FONT_SIZE)
        self.title_header_accent_font = ImageFont.truetype(config.FONT_BOLD, config.TITLE_HEADER_ACCENT_SIZE)
        self.cta_chrome_font = ImageFont.truetype(config.FONT_BOLD, config.CHROME_FONT_SIZE + 2)

        # Preview panel fonts (slightly smaller for top half)
        self.preview_code_font = ImageFont.truetype(config.FONT_REGULAR, config.PREVIEW_CODE_FONT_SIZE)
        self.preview_line_num_font = ImageFont.truetype(config.FONT_REGULAR, config.PREVIEW_LINE_NUM_SIZE)
        preview_bbox = self.preview_code_font.getbbox("M")
        self.preview_char_width = preview_bbox[2] - preview_bbox[0]
        self.preview_line_height = int(config.PREVIEW_CODE_FONT_SIZE * 1.65)

        # Monospace char dimensions (using dynamically scaled size)
        bbox = self.code_font.getbbox("M")
        self.char_width = bbox[2] - bbox[0]
        self.line_height = int(self.code_font_size * 1.65)

        if self.code_font_size != config.CODE_FONT_SIZE:
            logger.info(
                f"Dynamic font scaling: {config.CODE_FONT_SIZE} → {self.code_font_size}px"
            )

    def _tokenize_code(self):
        """Tokenize code using Pygments for syntax highlighting."""
        try:
            lexer = get_lexer_by_name(self.language)
        except Exception:
            logger.warning(f"Unknown language '{self.language}', falling back to plain text")
            lexer = TextLexer()
        self.tokens = list(lex(self.code, lexer))

    def _tokenize_before_code(self):
        """Tokenize the 'before' code for before_after content type."""
        try:
            lexer = get_lexer_by_name(self.language)
        except Exception:
            lexer = TextLexer()
        self.before_tokens = list(lex(self.code_before, lexer))

    def _compute_char_positions(self):
        """Pre-compute (char, x, y, color) for every printable character.

        Characters that exceed the code panel right boundary are skipped (clipped)
        so they never overflow the screen.
        """
        self.char_data: list[tuple[str, int, int, str]] = []
        x = config.CODE_LEFT
        y = config.CODE_TOP
        self.total_lines = 1
        # Right clipping boundary: leave a small margin inside the panel
        right_clip = self.width - config.PADDING - 16

        for token_type, token_text in self.tokens:
            color = self._resolve_color(token_type)
            for ch in token_text:
                if ch == "\n":
                    x = config.CODE_LEFT
                    y += self.line_height
                    self.total_lines += 1
                elif ch == "\t":
                    for _ in range(4):
                        if x < right_clip:
                            self.char_data.append((" ", x, y, color))
                        x += self.char_width
                else:
                    if x < right_clip:  # only draw if within panel bounds
                        self.char_data.append((ch, x, y, color))
                    x += self.char_width

        self.total_chars = len(self.char_data)

        # Compute preview-positioned char data for before_after (top panel)
        if self.code_before:
            self.preview_before_data = []
            px = config.PADDING + 72
            py = config.PREVIEW_CODE_TOP
            self.preview_before_lines = 1
            for token_type, token_text in self.before_tokens:
                color = self._resolve_color(token_type)
                for ch in token_text:
                    if ch == "\n":
                        px = config.PADDING + 72
                        py += self.preview_line_height
                        self.preview_before_lines += 1
                    elif ch == "\t":
                        for _ in range(4):
                            self.preview_before_data.append((" ", px, py, color))
                            px += self.preview_char_width
                    else:
                        self.preview_before_data.append((ch, px, py, color))
                        px += self.preview_char_width

    def _resolve_color(self, token_type) -> str:
        tt = token_type
        while tt:
            if tt in self._syntax_colors:
                return self._syntax_colors[tt]
            tt = tt.parent
        return config.DEFAULT_TEXT_COLOR

    def _create_gradient_bg(self) -> Image.Image:
        """Create gradient background image using numpy (fast)."""
        r1, g1, b1 = config.BG_GRADIENT_TOP
        r2, g2, b2 = config.BG_GRADIENT_BOTTOM
        # Build gradient via numpy — ~100× faster than draw.line() per row
        ratios = np.linspace(0, 1, self.height, dtype=np.float32).reshape(-1, 1)
        top = np.array([r1, g1, b1], dtype=np.float32)
        bottom = np.array([r2, g2, b2], dtype=np.float32)
        gradient = (top + (bottom - top) * ratios).astype(np.uint8)
        # Broadcast to full width
        arr = np.broadcast_to(gradient[:, np.newaxis, :], (self.height, self.width, 3)).copy()
        return Image.fromarray(arr)

    def _create_base_image(self):
        """Build the static split-screen base image with preview + code panels."""
        self.base = self._gradient_bg.copy()
        draw = ImageDraw.Draw(self.base)

        # ══ TOP: Preview Panel ════════════════════════════════
        draw.rounded_rectangle(
            [config.PADDING, config.PREVIEW_Y,
             self.width - config.PADDING, config.PREVIEW_BOTTOM],
            radius=16, fill=config.CODE_BG,
        )

        # Preview chrome bar
        pch_bottom = config.PREVIEW_Y + config.PREVIEW_CHROME_H
        draw.rounded_rectangle(
            [config.PADDING, config.PREVIEW_Y,
             self.width - config.PADDING, config.PREVIEW_Y + 20],
            radius=16, fill=config.CHROME_BG,
        )
        draw.rectangle(
            [config.PADDING, config.PREVIEW_Y + 12,
             self.width - config.PADDING, pch_bottom],
            fill=config.CHROME_BG,
        )

        # Preview traffic lights
        dot_cy = config.PREVIEW_Y + config.PREVIEW_CHROME_H // 2
        dot_start_x = config.PADDING + 28
        for i, color in enumerate(config.CHROME_DOT_COLORS):
            cx = dot_start_x + i * 22
            draw.ellipse([cx - 5, dot_cy - 5, cx + 5, dot_cy + 5], fill=color)

        # Preview panel label
        _preview_labels = {
            "output_demo": "▶ Output",
            "quiz": "🧠 Challenge",
            "before_after": "❌ Before",
            "tip": "💡 Concept",
        }
        plabel = _preview_labels.get(self.content_type, "▶ Preview")
        draw.text(
            (self.width // 2, dot_cy), plabel,
            fill="#8b949e", font=self.chrome_font, anchor="mm",
        )

        # Preview separator line
        draw.line(
            [(config.PADDING, pch_bottom),
             (self.width - config.PADDING, pch_bottom)],
            fill=config.SEPARATOR, width=1,
        )

        # Before/after: draw "before" code + line numbers into preview (static)
        if self.content_type == "before_after" and self.code_before:
            for i in range(getattr(self, 'preview_before_lines', 0)):
                ln_y = config.PREVIEW_CODE_TOP + i * self.preview_line_height
                if ln_y < config.PREVIEW_BOTTOM - 20:
                    draw.text(
                        (config.PADDING + 52, ln_y), str(i + 1),
                        fill=config.LINE_NUM_COLOR, font=self.preview_line_num_font,
                        anchor="ra",
                    )
            # Gutter
            g_top = config.PREVIEW_CODE_TOP - 5
            g_bot = min(
                config.PREVIEW_CODE_TOP + getattr(self, 'preview_before_lines', 1) * self.preview_line_height + 5,
                config.PREVIEW_BOTTOM - 10,
            )
            draw.line(
                [(config.PADDING + 62, g_top), (config.PADDING + 62, g_bot)],
                fill=config.SEPARATOR, width=1,
            )
            for ch, x, y, color in getattr(self, 'preview_before_data', []):
                if ch.strip() and y < config.PREVIEW_BOTTOM - 20:
                    draw.text((x, y), ch, fill=color, font=self.preview_code_font)

        # ══ GRADIENT DIVIDER ══════════════════════════════════
        left_rgb = _hex_to_rgb(config.ACCENT_GRADIENT_LEFT)
        right_rgb = _hex_to_rgb(config.ACCENT_GRADIENT_RIGHT)
        for x in range(config.PADDING, self.width - config.PADDING):
            t = (x - config.PADDING) / max(self.width - 2 * config.PADDING, 1)
            c = _lerp_color(left_rgb, right_rgb, t)
            draw.line([(x, config.DIVIDER_Y), (x, config.DIVIDER_Y + 3)], fill=c)

        # ══ BOTTOM: Code Editor Panel ═════════════════════════
        panel_bottom = config.CODE_TOP + (max(self.total_lines, 5) * self.line_height) + 40
        self._panel_bottom = panel_bottom
        draw.rounded_rectangle(
            [config.PADDING, config.CHROME_Y,
             self.width - config.PADDING, panel_bottom],
            radius=16, fill=config.CODE_BG,
        )

        # Code chrome bar
        chrome_bottom = config.CHROME_Y + config.CHROME_H
        draw.rounded_rectangle(
            [config.PADDING, config.CHROME_Y,
             self.width - config.PADDING, config.CHROME_Y + 22],
            radius=16, fill=config.CHROME_BG,
        )
        draw.rectangle(
            [config.PADDING, config.CHROME_Y + 12,
             self.width - config.PADDING, chrome_bottom],
            fill=config.CHROME_BG,
        )

        # Code traffic lights
        dot_cy2 = config.CHROME_Y + config.CHROME_H // 2
        for i, color in enumerate(config.CHROME_DOT_COLORS):
            cx = dot_start_x + i * 22
            draw.ellipse([cx - 5, dot_cy2 - 5, cx + 5, dot_cy2 + 5], fill=color)

        # Filename + CTA label in chrome bar (Phase 12C)
        ext = EXT_MAP.get(self.language, ".txt")
        filename = f"main{ext}"
        if self.content_type == "before_after":
            filename = f"✅ main{ext}  (AFTER)"
        draw.text(
            (dot_start_x + 80, dot_cy2), filename,
            fill="#8b949e", font=self.chrome_font, anchor="lm",
        )
        # Phase 12C: Persistent CTA text in chrome bar — "Comm 'X' for code"
        cta_keyword = self.title.split()[0] if self.title else "code"
        # Pick a short, memorable keyword from title
        if len(cta_keyword) > 8:
            cta_keyword = "code"
        cta_text = f'Comm "{cta_keyword}" for code'
        draw.text(
            (self.width - config.PADDING - 16, dot_cy2), cta_text,
            fill="#7ee787", font=self.cta_chrome_font, anchor="rm",
        )

        # Separator
        draw.line(
            [(config.PADDING, chrome_bottom),
             (self.width - config.PADDING, chrome_bottom)],
            fill=config.SEPARATOR, width=1,
        )

        # Line numbers
        for i in range(self.total_lines):
            ln_y = config.CODE_TOP + i * self.line_height
            draw.text(
                (config.LINE_NUM_RIGHT_X, ln_y), str(i + 1),
                fill=config.LINE_NUM_COLOR, font=self.line_num_font, anchor="ra",
            )

        # Gutter separator
        gutter_top_y = config.CODE_TOP - 8
        gutter_bottom_y = config.CODE_TOP + self.total_lines * self.line_height + 10
        draw.line(
            [(config.GUTTER_X, gutter_top_y), (config.GUTTER_X, gutter_bottom_y)],
            fill=config.SEPARATOR, width=1,
        )

        # Watermark
        draw.text(
            (self.width - config.PADDING - 10, config.WATERMARK_Y),
            self.channel_name,
            fill=config.WATERMARK_COLOR, font=self.watermark_font, anchor="ra",
        )

    def _create_intro_image(self):
        """Create the intro title card."""
        self.intro = self._gradient_bg.copy()
        draw = ImageDraw.Draw(self.intro)

        center_y = self.height // 2

        # Accent gradient bar (horizontal stripe)
        bar_y = center_y - 90
        bar_h = 4
        left_rgb = _hex_to_rgb(config.ACCENT_GRADIENT_LEFT)
        right_rgb = _hex_to_rgb(config.ACCENT_GRADIENT_RIGHT)
        bar_left = 150
        bar_right = self.width - 150
        for x in range(bar_left, bar_right):
            t = (x - bar_left) / max(bar_right - bar_left, 1)
            c = _lerp_color(left_rgb, right_rgb, t)
            draw.line([(x, bar_y), (x, bar_y + bar_h)], fill=c)

        # Content type label
        type_label = CONTENT_TYPE_LABELS.get(self.content_type, "💡 TIP")
        draw.text(
            (self.width // 2, center_y - 60),
            type_label,
            fill=config.ACCENT_GRADIENT_LEFT,
            font=self.title_sub_font,
            anchor="mm",
        )

        # Title text (gradient word-wrap)
        title_text = self.title.replace(" #Shorts", "").replace(" #shorts", "").strip()
        self._draw_wrapped_text_gradient(
            draw, title_text, self.title_font,
            _hex_to_rgb(config.ACCENT_GRADIENT_LEFT), _hex_to_rgb(config.ACCENT_GRADIENT_RIGHT), 
            center_y, max_width=self.width - 160,
        )

        # Channel name
        draw.text(
            (self.width // 2, center_y + 120),
            self.channel_name,
            fill=config.INTRO_SUBTITLE_COLOR,
            font=self.title_sub_font,
            anchor="mm",
        )

        # Bottom accent bar
        bar_y2 = center_y + 160
        for x in range(bar_left, bar_right):
            t = (x - bar_left) / max(bar_right - bar_left, 1)
            c = _lerp_color(right_rgb, left_rgb, t)
            draw.line([(x, bar_y2), (x, bar_y2 + bar_h)], fill=c)

        # Series part badge (Phase 6.4) — top-right pill when part of a series
        if self.series_part > 0:
            badge_text = f"Part {self.series_part}"
            bbox = draw.textbbox((0, 0), badge_text, font=self.title_sub_font)
            bw = (bbox[2] - bbox[0]) + 28
            bh = (bbox[3] - bbox[1]) + 14
            bx = self.width - 60
            by = 130
            badge_color = _hex_to_rgb(config.ACCENT_GRADIENT_LEFT)
            draw.rectangle(
                [(bx - bw, by - bh // 2), (bx, by + bh // 2)],
                fill=badge_color,
            )
            draw.text(
                (bx - bw // 2, by),
                badge_text,
                fill="#ffffff",
                font=self.title_sub_font,
                anchor="mm",
            )

    def _create_outro_image(self):
        """Create a creative outro card with code-themed design."""
        self.outro = self._gradient_bg.copy()
        draw = ImageDraw.Draw(self.outro)

        cx = self.width // 2
        cy = self.height // 2

        # ── Decorative code comment (top) ─────────────────────
        comment_text = "<!-- TODO: hit subscribe 😄 -->" if config.CONTENT_MODE == "visual_ui" else "// TODO: hit subscribe 😄"
        draw.text(
            (cx, cy - 200),
            comment_text,
            fill="#484f58",
            font=self.title_sub_font,
            anchor="mm",
        )

        # ── Top gradient accent bar ───────────────────────
        left_rgb = _hex_to_rgb(config.ACCENT_GRADIENT_LEFT)
        right_rgb = _hex_to_rgb(config.ACCENT_GRADIENT_RIGHT)
        bar_left = 150
        bar_right = self.width - 150
        bar_y1 = cy - 160
        for x in range(bar_left, bar_right):
            t = (x - bar_left) / max(bar_right - bar_left, 1)
            c = _lerp_color(left_rgb, right_rgb, t)
            draw.line([(x, bar_y1), (x, bar_y1 + 3)], fill=c)

        # ── Channel name (large) ─────────────────────────
        draw.text(
            (cx, cy - 110),
            self.channel_name,
            fill="#e6edf3",
            font=self.title_font,
            anchor="mm",
        )

        # ── Subscribe button (YouTube-style red pill) ─────
        btn_w, btn_h = 360, 64
        btn_x = cx - btn_w // 2
        btn_y = cy - 20
        draw.rounded_rectangle(
            [btn_x, btn_y, btn_x + btn_w, btn_y + btn_h],
            radius=32, fill="#ff0000",
        )
        draw.text(
            (cx, btn_y + btn_h // 2),
            "🔔  S U B S C R I B E",
            fill="#ffffff",
            font=self.outro_sub_font,
            anchor="mm",
        )

        # ── Action row ─────────────────────────────────
        draw.text(
            (cx, cy + 80),
            "👍 Like  ·  🔗 Share  ·  💬 Comment",
            fill="#8b949e",
            font=self.title_sub_font,
            anchor="mm",
        )

        # ── Bottom gradient accent bar ────────────────────
        bar_y2 = cy + 120
        for x in range(bar_left, bar_right):
            t = (x - bar_left) / max(bar_right - bar_left, 1)
            c = _lerp_color(right_rgb, left_rgb, t)
            draw.line([(x, bar_y2), (x, bar_y2 + 3)], fill=c)

        # ── Tagline ───────────────────────────────────
        tagline = "New UI designs every day! ✨" if config.CONTENT_MODE == "visual_ui" else "New coding tips every day! 🚀"
        draw.text(
            (cx, cy + 165),
            tagline,
            fill=config.OUTRO_CTA_COLOR,
            font=self.outro_sub_font,
            anchor="mm",
        )

    def _prepare_output_panel(self):
        """Pre-compute output panel data and reveal timing."""
        if not self.code_output:
            return

        output_line_h = int(config.OUTPUT_FONT_SIZE * 1.5)
        output_lines = self.code_output.strip().split("\n")
        self.output_lines = output_lines[:12]
        self.output_line_height = output_line_h

        # Output appears after typing finishes
        natural_typing = self.total_chars / config.TYPING_CPS
        max_typing = self.code_end - self.code_start - config.TYPING_DELAY_START - config.TYPING_DELAY_END
        typing_dur = min(natural_typing, max(max_typing, 2.0))
        self.output_reveal_time = self.code_start + config.TYPING_DELAY_START + typing_dur + 0.3

    def _create_subtitle_groups(self):
        """Group word timestamps into caption chunks."""
        self.caption_groups: list[list[dict]] = []
        current_group: list[dict] = []

        for wt in self.word_timestamps:
            current_group.append(wt)
            text = wt["text"]
            if (
                len(current_group) >= 6
                or text.endswith((".", "!", "?", ";"))
                or (text.endswith(",") and len(current_group) >= 4)
            ):
                self.caption_groups.append(current_group)
                current_group = []

        if current_group:
            self.caption_groups.append(current_group)

    def _draw_wrapped_text(self, draw, text, font, color, center_y, max_width):
        """Draw text centered with word-wrapping."""
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            test = f"{current_line} {word}".strip()
            bbox = font.getbbox(test)
            if bbox[2] - bbox[0] > max_width and current_line:
                lines.append(current_line)
                current_line = word
            else:
                current_line = test
        if current_line:
            lines.append(current_line)

        line_spacing = int(font.size * 1.3)
        total_h = len(lines) * line_spacing
        start_y = center_y - total_h // 2

        for i, line in enumerate(lines):
            y = start_y + i * line_spacing
            draw.text(
                (self.width // 2, y),
                line, fill=color, font=font, anchor="ma",
            )

    def _draw_wrapped_text_gradient(self, draw, text, font, color_left, color_right, center_y, max_width):
        """Draw text centered with word-wrapping and a horizontal gradient fill."""
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            test = f"{current_line} {word}".strip()
            bbox = font.getbbox(test)
            if bbox[2] - bbox[0] > max_width and current_line:
                lines.append(current_line)
                current_line = word
            else:
                current_line = test
        if current_line:
            lines.append(current_line)

        line_spacing = int(font.size * 1.3)
        total_h = len(lines) * line_spacing
        start_y = center_y - total_h // 2

        # Create a temporary image for the text mask
        mask = Image.new("L", (self.width, self.height), 0)
        mask_draw = ImageDraw.Draw(mask)

        for i, line in enumerate(lines):
            y = start_y + i * line_spacing
            mask_draw.text(
                (self.width // 2, y),
                line, fill=255, font=font, anchor="ma",
            )

        # Paste gradient using text mask
        bbox = mask.getbbox()
        if not bbox:
            return
            
        grad = Image.new("RGB", (self.width, self.height))
        grad_draw = ImageDraw.Draw(grad)
        
        left, top, right, bottom = bbox
        for x in range(left, right):
            t = (x - left) / max(right - left, 1)
            c = _lerp_color(color_left, color_right, t)
            grad_draw.line([(x, top), (x, bottom)], fill=c)

        draw._image.paste(grad, (0, 0), mask)

    # ──────────────────────────────────────────────────────────
    #  ANIMATION HELPERS  (Phase 5)
    # ──────────────────────────────────────────────────────────

    def _init_bg_particles(self):
        """Pre-compute floating code particle positions (deterministic, no random)."""
        chars  = ["{}" , "=>", "0x", "let", "def", "//"]
        speeds = [18, 24, 15, 22, 28, 20]          # px/sec
        ys     = [165, 295, 430, 560, 640, 380]    # y positions
        x0s    = [0, 220, 440, 660, 110, 330]      # starting x offsets
        self._bg_particles = [
            {"char": chars[i], "y": ys[i], "speed": speeds[i], "x0": x0s[i]}
            for i in range(len(chars))
        ]

    def _draw_bg_particles(self, draw: ImageDraw.ImageDraw, t: float):
        """Draw very subtle floating code fragments in the background."""
        # Blend between CODE_BG and LINE_HIGHLIGHT at 55% — barely visible
        particle_color = _lerp_color(
            _hex_to_rgb(config.CODE_BG),
            _hex_to_rgb(config.LINE_HIGHLIGHT),
            0.55,
        )
        for p in self._bg_particles:
            x = int((p["x0"] + t * p["speed"]) % (self.width + 120))
            draw.text((x, p["y"]), p["char"], fill=particle_color, font=self.chrome_font)

    def _get_line_slide_offset(self, n_chars: int) -> tuple[int, int]:
        """Return (active_line_y, x_offset) for per-line slide-in animation."""
        if n_chars <= 0 or n_chars >= self.total_chars:
            return -1, 0

        _, _, cur_y, _ = self.char_data[n_chars - 1]

        # Walk back to find the first char on this line
        line_start_idx = n_chars - 1
        while line_start_idx > 0 and self.char_data[line_start_idx - 1][2] == cur_y:
            line_start_idx -= 1

        chars_on_line = n_chars - line_start_idx

        # Count total chars on this line
        total_on_line = chars_on_line
        for i in range(n_chars, self.total_chars):
            if self.char_data[i][2] == cur_y:
                total_on_line += 1
            else:
                break

        if total_on_line == 0:
            return cur_y, 0

        # Slide completes over the first 40% of the line being typed
        progress = chars_on_line / max(total_on_line, 1)
        eased = _ease_out_cubic(min(progress / 0.4, 1.0))
        x_offset = int(-config.LINE_SLIDE_OFFSET * (1.0 - eased))
        return cur_y, x_offset

    def _draw_before_label(self, draw: ImageDraw.ImageDraw):
        """Overlay '\u274c BEFORE' label on the preview panel for before_after type."""
        label_y = config.PREVIEW_Y + config.PREVIEW_CHROME_H + 3
        label_h = 26
        draw.rectangle(
            [config.PADDING + 2, label_y,
             config.PADDING + 190, label_y + label_h],
            fill="#3d1212",
        )
        draw.text(
            (config.PADDING + 96, label_y + label_h // 2),
            "\u274c  BEFORE",
            fill="#ff7b72", font=self.chrome_font, anchor="mm",
        )

    # ──────────────────────────────────────────────────────────
    #  ANIMATED CODE HIGHLIGHTING  (Phase 9.2)
    # ──────────────────────────────────────────────────────────

    def _build_code_keyword_index(self):
        """
        Build a mapping of identifiers in the code to their line numbers.
        Used by _get_highlighted_line() to find which line to glow
        when the narrator speaks a matching keyword.
        """
        import re
        self._keyword_to_lines: dict[str, list[int]] = {}
        code_lines = self.code.rstrip().split("\n")
        # Extract identifiers (3+ chars) from each line
        ident_pattern = re.compile(r"[A-Za-z_]\w{2,}")
        for line_idx, line in enumerate(code_lines):
            for match in ident_pattern.finditer(line):
                word = match.group().lower()
                if word not in self._keyword_to_lines:
                    self._keyword_to_lines[word] = []
                if line_idx not in self._keyword_to_lines[word]:
                    self._keyword_to_lines[word].append(line_idx)

    def _get_highlighted_line(self, t: float) -> int | None:
        """
        Return the 0-based line index that should be highlighted at time t,
        based on the currently spoken narration word matching a code identifier.

        Returns None if no match is found (default: no special highlight).
        """
        if not self.word_timestamps or not self._keyword_to_lines:
            return None

        # Find the current narration word at time t
        current_word = None
        for wt in self.word_timestamps:
            start = wt.get("start_s", 0) if isinstance(wt, dict) else wt.start_s
            end = wt.get("end_s", 0) if isinstance(wt, dict) else wt.end_s
            text = wt.get("text", "") if isinstance(wt, dict) else wt.text
            if start <= t <= end:
                current_word = text.lower().strip(".,!?;:'\"()[]{}#")
                break

        if not current_word or len(current_word) < 3:
            return None

        # Look up matching code lines
        matching_lines = self._keyword_to_lines.get(current_word)
        if matching_lines:
            return matching_lines[0]
        return None

    def _draw_line_highlight_glow(
        self, draw: ImageDraw.ImageDraw, line_idx: int, n_chars: int
    ):
        """
        Draw a glow effect on the specified code line (Phase 9.2).
        - Semi-transparent highlight background (brighter than default)
        - Accent-colored vertical strip on the left gutter
        """
        # Compute y position for the target line
        target_y = config.CODE_TOP + line_idx * self.line_height

        # Don't highlight lines not yet typed
        if n_chars <= 0:
            return
        last_visible_y = self.char_data[min(n_chars - 1, self.total_chars - 1)][2]
        if target_y > last_visible_y:
            return

        # Background highlight (brighter)
        hl_color = config.LINE_HIGHLIGHT_ACTIVE
        draw.rectangle(
            [config.PADDING + 1, target_y - 2,
             self.width - config.PADDING - 1, target_y + self.line_height - 4],
            fill=hl_color,
        )

        # Accent glow strip on the left
        accent_color = config.ACCENT_GRADIENT_LEFT
        draw.rectangle(
            [config.PADDING + 1, target_y - 2,
             config.PADDING + 5, target_y + self.line_height - 4],
            fill=accent_color,
        )

    # ──────────────────────────────────────────────────────────
    #  PER-FRAME RENDERING
    # ──────────────────────────────────────────────────────────

    def render_frame(self, t: float) -> np.ndarray:
        """Render a single video frame at time t seconds."""

        # INTRO (skipped when INTRO_DURATION = 0)
        if self.intro_end > 0 and t < self.intro_end:
            return self._render_intro(t)

        # OUTRO
        if t >= self.outro_start:
            return self._render_outro(t)

        # MAIN CODE
        return self._render_code_phase(t)

    def _render_intro(self, t: float) -> np.ndarray:
        """Render intro title card with fade-in."""
        progress = min(t / max(self.intro_end, 0.1), 1.0)
        alpha = _ease_out_cubic(progress)
        # Reuse pre-computed gradient background (not re-created per frame)
        frame = Image.blend(self._gradient_bg, self.intro, alpha)
        return np.array(frame)

    def _render_outro(self, t: float) -> np.ndarray:
        """Render outro — crossfade then animated subscribe button pulse (Phase 5.8)."""
        elapsed = t - self.outro_start
        progress = min(elapsed / 0.8, 1.0)
        alpha = _ease_out_cubic(progress)
        frame = Image.blend(self.base, self.outro, alpha)

        # After crossfade: pulse the Subscribe button per-frame
        if progress >= 1.0:
            draw = ImageDraw.Draw(frame)
            cx = self.width // 2
            cy = self.height // 2
            pulse = 1.0 + 0.04 * math.sin(elapsed * 4.0)
            btn_w = int(360 * pulse)
            btn_h = int(64 * pulse)
            btn_x = cx - btn_w // 2
            btn_y = cy - 20
            draw.rounded_rectangle(
                [btn_x, btn_y, btn_x + btn_w, btn_y + btn_h],
                radius=32, fill="#ff0000",
            )
            draw.text(
                (cx, btn_y + btn_h // 2), "\U0001f514  S U B S C R I B E",
                fill="#ffffff", font=self.outro_sub_font, anchor="mm",
            )

        return np.array(frame)

    # ──────────────────────────────────────────────────────────
    #  PHASE 12B: TITLE HEADER — Big gradient title at top
    # ──────────────────────────────────────────────────────────

    def _draw_title_header(self, draw: ImageDraw.ImageDraw, t: float):
        """Draw a large, eye-catching title at the top of the frame.

        The last word renders in green accent (#7ee787) while the rest
        is white. Auto-scales font size to fit within screen width.
        Includes a subtle fade-in during the first 0.5 seconds.
        """
        if not self.title:
            return

        # Clean title: remove #Shorts and hashtags for display
        display_title = self.title.replace("#Shorts", "").replace("#shorts", "").strip()
        # Remove any remaining hashtags
        words = [w for w in display_title.split() if not w.startswith("#")]
        if not words:
            return

        # Fade-in animation (first 0.5s)
        alpha = min(t / 0.5, 1.0)
        if alpha < 0.01:
            return

        center_x = self.width // 2
        center_y = config.TITLE_HEADER_Y + config.TITLE_HEADER_H // 2
        max_w = self.width - 2 * config.PADDING  # max allowed title width

        if len(words) == 1:
            # Single word — render entirely in accent, auto-scale
            font = self.title_header_accent_font
            bbox = font.getbbox(words[0])
            text_w = bbox[2] - bbox[0]
            if text_w > max_w:
                scale = max_w / text_w
                new_size = max(int(config.TITLE_HEADER_ACCENT_SIZE * scale), 30)
                font = ImageFont.truetype(font.path, new_size)
            draw.text(
                (center_x, center_y), words[0],
                fill="#7ee787", font=font, anchor="mm",
            )
            return

        # Multi-word: last word in accent green, rest in white
        prefix = " ".join(words[:-1])
        accent_word = words[-1]

        # Auto-scale: shrink font if title exceeds screen width
        main_font = self.title_header_font
        accent_font = self.title_header_accent_font
        main_size = config.TITLE_HEADER_FONT_SIZE
        accent_size = config.TITLE_HEADER_ACCENT_SIZE

        for _ in range(20):  # max 20 shrink attempts
            prefix_bbox = main_font.getbbox(prefix + " ")
            prefix_w = prefix_bbox[2] - prefix_bbox[0]
            accent_bbox = accent_font.getbbox(accent_word)
            accent_w = accent_bbox[2] - accent_bbox[0]
            total_w = prefix_w + accent_w

            if total_w <= max_w or main_size <= 30:
                break
            # Shrink by ~10% each step
            main_size = max(int(main_size * 0.88), 30)
            accent_size = max(int(accent_size * 0.88), 32)
            main_font = ImageFont.truetype(main_font.path, main_size)
            accent_font = ImageFont.truetype(accent_font.path, accent_size)

        # Re-measure after scaling
        prefix_bbox = main_font.getbbox(prefix + " ")
        prefix_w = prefix_bbox[2] - prefix_bbox[0]
        accent_bbox = accent_font.getbbox(accent_word)
        accent_w = accent_bbox[2] - accent_bbox[0]
        total_w = prefix_w + accent_w

        # Truncate title if still too wide (ultimate fallback)
        while total_w > max_w and len(prefix) > 8:
            words_left = prefix.split()
            if len(words_left) <= 1:
                break
            words_left = words_left[:-1]
            prefix = " ".join(words_left)
            prefix_bbox = main_font.getbbox(prefix + "… ")
            prefix_w = prefix_bbox[2] - prefix_bbox[0]
            total_w = prefix_w + accent_w
            prefix = prefix + "…"

        start_x = center_x - total_w // 2

        # Draw prefix (white)
        draw.text(
            (start_x, center_y), prefix + " ",
            fill="#ffffff", font=main_font, anchor="lm",
        )
        # Draw accent word (green)
        draw.text(
            (start_x + prefix_w, center_y), accent_word,
            fill="#7ee787", font=accent_font, anchor="lm",
        )

        # Subtle gradient underline below title
        line_y = center_y + main_size // 2 + 8
        bar_left = max(start_x, 0)
        bar_right = min(start_x + total_w, self.width)
        left_rgb = _hex_to_rgb("#7ee787")
        right_rgb = _hex_to_rgb("#58a6ff")
        for x in range(bar_left, bar_right):
            t_bar = (x - bar_left) / max(bar_right - bar_left, 1)
            c = _lerp_color(left_rgb, right_rgb, t_bar)
            draw.line([(x, line_y), (x, line_y + 3)], fill=c)

    def _render_code_phase(self, t: float) -> np.ndarray:
        """Render split-screen: title header + preview (top) + code editor (bottom).

        Code is displayed STATICALLY (no typing animation) — the focus is on
        the live Playwright preview panel above, not the code.
        """
        frame = self.base.copy()
        draw = ImageDraw.Draw(frame)

        # ── Subtle background particles (Phase 5.9) ────────
        self._draw_bg_particles(draw, t)

        # ── Phase 12B: Big gradient title header ────────────
        self._draw_title_header(draw, t)

        # ── Top panel: dynamic preview content ──────────────
        self._draw_preview_content(draw, t)

        # ── Bottom panel: STATIC code display (all chars visible) ──
        n_chars = self.total_chars  # Show everything from the start

        # Draw all code characters statically (no animation)
        for i in range(n_chars):
            ch, x, y, color = self.char_data[i]
            if ch.strip():
                draw.text((x, y), ch, fill=color, font=self.code_font)

        # Phase 10.1: CTA overlay — "Comment 'X' for code" (persistent)
        self._draw_cta_overlay(draw, t)

        # Karaoke subtitles
        self._draw_subtitles(draw, t)

        return np.array(frame)

    # ──────────────────────────────────────────────────────────
    #  PREVIEW PANEL RENDERING (top half)
    # ──────────────────────────────────────────────────────────

    def _draw_preview_content(self, draw: ImageDraw.ImageDraw, t: float):
        """Draw dynamic content in the top preview panel."""
        # Phase 10.1 & 11.2: If we have captured preview images, use them instead
        if self.preview_image is not None:
            self._draw_captured_preview(draw, t)
            return

        if self.content_type == "output_demo":
            self._draw_preview_output(draw, t)
        elif self.content_type == "quiz":
            self._draw_preview_quiz(draw, t)
        elif self.content_type == "before_after":
            self._draw_before_label(draw)  # overlay BEFORE label (Phase 5.6)
        else:  # tip
            self._draw_preview_tip(draw, t)

    # ──────────────────────────────────────────────────────────
    #  Phase 10.1: VISUAL PREVIEW + CTA OVERLAY
    # ──────────────────────────────────────────────────────────

    def _fit_preview_images(
        self, imgs: "Image.Image | list[Image.Image] | None"
    ) -> "Image.Image | list[Image.Image] | None":
        if imgs is None:
            return None
        if isinstance(imgs, list):
            return [img for img in (self._fit_single_preview_image(img) for img in imgs) if img is not None]
        return self._fit_single_preview_image(imgs)

    def _fit_single_preview_image(self, img: "Image.Image | None") -> "Image.Image | None":
        """Resize a captured preview image to fit the preview panel area."""
        if img is None:
            return None
        panel_w = self.width - 2 * config.PADDING - 4   # inner panel width
        panel_h = config.PREVIEW_BOTTOM - (config.PREVIEW_Y + config.PREVIEW_CHROME_H) - 10
        # Maintain aspect ratio, fit within bounds
        img_ratio = img.width / max(img.height, 1)
        panel_ratio = panel_w / max(panel_h, 1)
        if img_ratio > panel_ratio:
            new_w = panel_w
            new_h = int(panel_w / max(img_ratio, 0.01))
        else:
            new_h = panel_h
            new_w = int(panel_h * img_ratio)
        try:
            return img.resize((max(new_w, 1), max(new_h, 1)), Image.LANCZOS)
        except Exception:
            return img.resize((max(new_w, 1), max(new_h, 1)))

    def _get_animated_preview_frame(self, t: float) -> "Image.Image | None":
        if self.preview_image is None:
            return None
        if not isinstance(self.preview_image, list):
            return self.preview_image
        if not self.preview_image:
            return None
        
        # Loop animation at 15 FPS
        fps = 15.0
        frame_idx = int(t * fps) % len(self.preview_image)
        return self.preview_image[frame_idx]

    def _draw_captured_preview(self, draw: ImageDraw.ImageDraw, t: float):
        """Paste the pre-captured animated/static preview image into the panel."""
        img_frame = self._get_animated_preview_frame(t)
        if img_frame is None:
            return
        
        panel_x = config.PADDING + 2
        panel_top = config.PREVIEW_Y + config.PREVIEW_CHROME_H + 1
        panel_w = self.width - 2 * config.PADDING - 4
        panel_h = config.PREVIEW_BOTTOM - panel_top - 5
        # Center the image within the panel
        x_offset = panel_x + (panel_w - img_frame.width) // 2
        y_offset = panel_top + (panel_h - img_frame.height) // 2
        # Paste onto the frame Image — we access via draw's internal image
        try:
            draw._image.paste(img_frame, (x_offset, y_offset))
        except Exception:
            # Fallback
            draw.rectangle(
                [panel_x, panel_top, panel_x + panel_w, panel_top + panel_h],
                fill="#161b22",
            )
            draw.text(
                (self.width // 2, panel_top + panel_h // 2),
                "[ Preview Error ]", fill="#484f58", font=self.chrome_font, anchor="mm",
            )

    def _draw_cta_overlay(self, draw: ImageDraw.ImageDraw, t: float):
        """Draw 'Comment X for code' CTA pill in the last seconds before outro."""
        if not config.ENABLE_CTA_OVERLAY:
            return
        # Only show in the window: (outro_start - CTA_LEAD_TIME) to outro_start
        cta_start = self.outro_start - config.CTA_LEAD_TIME
        if t < cta_start or t >= self.outro_start:
            return

        elapsed = t - cta_start
        # Fade in over 0.5s
        alpha = min(elapsed / 0.5, 1.0)
        if alpha < 0.05:
            return

        # Build CTA text from language
        if config.CONTENT_MODE == "visual_ui":
            cta_text = '💬  Comment "SOURCE" for code'
        else:
            lang_upper = self.language.upper()
            _lang_display = {
                "javascript": "JS", "typescript": "TS", "python": "PYTHON",
                "html": "HTML", "css": "CSS", "bash": "BASH", "java": "JAVA",
                "go": "GO", "rust": "RUST", "c": "C", "cpp": "C++",
                "csharp": "C#", "ruby": "RUBY", "php": "PHP", "swift": "SWIFT",
                "kotlin": "KOTLIN", "dart": "DART", "sql": "SQL", "r": "R",
            }
            keyword = _lang_display.get(self.language, lang_upper[:8])
            cta_text = f'\U0001f4ac  Comment "{keyword}" for code'

        cx = self.width // 2
        cy = config.CTA_Y

        # Measure text
        try:
            bbox = self.chrome_font.getbbox(cta_text)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        except Exception:
            tw, th = 300, 20

        pill_w = tw + 40
        pill_h = th + 20
        pill_x = cx - pill_w // 2
        pill_y = cy - pill_h // 2

        # Semi-transparent dark background (approximation — full alpha needs composite)
        bg_color = (1, 4, 9)  # very dark, near-black
        draw.rounded_rectangle(
            [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
            radius=pill_h // 2, fill=bg_color,
        )
        # Border
        draw.rounded_rectangle(
            [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
            radius=pill_h // 2, outline="#30363d", width=1,
        )
        # Text
        text_color = config.OUTRO_CTA_COLOR  # gold #ffd700
        draw.text(
            (cx, cy), cta_text,
            fill=text_color, font=self.chrome_font, anchor="mm",
        )

    def _draw_preview_tip(self, draw: ImageDraw.ImageDraw, t: float):
        """Draw styled concept card — bobbing emoji, gradient badge, tag chips (Phase 5.6)."""
        cx = self.width // 2
        top = config.PREVIEW_CONTENT_Y

        # Bobbing emoji — gentle up-down oscillation
        emoji_y = top + 100 + int(5 * math.sin(t * 2.5))
        draw.text(
            (cx, emoji_y), "\U0001f4a1",
            fill="#ffd700", font=self.title_font, anchor="mm",
        )

        # Title text (gradient word-wrapped)
        title = self.title.replace(" #Shorts", "").replace(" #shorts", "").strip()
        if title:
            c_left = _hex_to_rgb(config.ACCENT_GRADIENT_LEFT)
            c_right = _hex_to_rgb(config.ACCENT_GRADIENT_RIGHT)
            self._draw_wrapped_text_gradient(
                draw, title, self.title_sub_font,
                c_left, c_right, top + 240, max_width=self.width - 160,
            )

        # Full-width language badge with accent fill
        lang = self.language.upper()
        badge_left = config.PADDING + 20
        badge_right = self.width - config.PADDING - 20
        badge_y = top + 355
        badge_h = 48
        draw.rounded_rectangle(
            [badge_left, badge_y, badge_right, badge_y + badge_h],
            radius=24, fill="#1a2744",
        )
        draw.text(
            (cx, badge_y + badge_h // 2), f"  {lang}  ",
            fill=config.ACCENT_GRADIENT_LEFT, font=self.title_sub_font, anchor="mm",
        )

        # Tag chips from title keywords
        title_words = [w.strip(".,!?#") for w in title.split() if len(w) > 3][:3]
        chip_x = config.PADDING + 20
        chip_y = badge_y + badge_h + 12
        for word in title_words:
            cb = self.chrome_font.getbbox(f"  {word}  ")
            cw = cb[2] - cb[0] + 10
            ch = cb[3] - cb[1] + 8
            if chip_x + cw > self.width - config.PADDING - 20:
                break
            draw.rounded_rectangle(
                [chip_x, chip_y, chip_x + cw, chip_y + ch],
                radius=8, fill="#30363d",
            )
            draw.text(
                (chip_x + cw // 2, chip_y + ch // 2), f"  {word}  ",
                fill="#8b949e", font=self.chrome_font, anchor="mm",
            )
            chip_x += cw + 8

    def _draw_preview_output(self, draw: ImageDraw.ImageDraw, t: float):
        """Terminal-style output in preview panel with spinner then line-by-line reveal."""
        if not self.code_output:
            return

        content_y = config.PREVIEW_CONTENT_Y + 20

        if t < getattr(self, 'output_reveal_time', float('inf')):
            # Spinner animation: "Running..."
            spinner = "\u28cb\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f"
            idx = int(t * 10) % len(spinner)
            draw.text(
                (config.PADDING + 30, content_y),
                f"  {spinner[idx]}  Running...",
                fill=config.PREVIEW_RUNNING_COLOR, font=self.output_font,
            )
            return

        # Line-by-line reveal after typing finishes
        elapsed = t - self.output_reveal_time
        lines_per_sec = 4
        visible_count = min(
            int(elapsed * lines_per_sec) + 1,
            len(getattr(self, 'output_lines', [])),
        )

        for i in range(visible_count):
            line_y = content_y + i * self.output_line_height
            if line_y > config.PREVIEW_BOTTOM - 30:
                break
            prompt = "\u276f " if i == 0 else "  "
            draw.text(
                (config.PADDING + 30, line_y),
                prompt, fill=config.OUTPUT_PROMPT_COLOR, font=self.output_font,
            )
            draw.text(
                (config.PADDING + 65, line_y),
                self.output_lines[i],
                fill=config.OUTPUT_TEXT_COLOR, font=self.output_font,
            )

    def _draw_preview_quiz(self, draw: ImageDraw.ImageDraw, t: float):
        """Quiz challenge with progress bar + slide-up answer reveal (Phase 5.6)."""
        cx = self.width // 2
        top = config.PREVIEW_CONTENT_Y
        reveal_time = getattr(self, 'output_reveal_time', float('inf'))

        if t < reveal_time:
            # Challenge phase
            draw.text(
                (cx, top + 90), "What does this",
                fill="#e6edf3", font=self.title_sub_font, anchor="mm",
            )
            draw.text(
                (cx, top + 140), "code output?",
                fill="#e6edf3", font=self.title_sub_font, anchor="mm",
            )
            # Animated pulsing "?"
            pulse = 1.0 + 0.15 * math.sin(t * 5)
            q_size = int(config.TITLE_FONT_SIZE * pulse)
            q_font = ImageFont.truetype(config.FONT_BOLD, min(q_size, 80))
            draw.text(
                (cx, top + 275), "?",
                fill="#58a6ff", font=q_font, anchor="mm",
            )
            # Progress bar — shows typing progress toward reveal
            bar_left = config.PADDING + 30
            bar_right = self.width - config.PADDING - 30
            bar_y = top + 385
            bar_h = 5
            draw.rounded_rectangle(
                [bar_left, bar_y, bar_right, bar_y + bar_h],
                radius=3, fill="#30363d",
            )
            progress = min(t / max(reveal_time, 0.1), 1.0)
            fill_x = int(bar_left + (bar_right - bar_left) * progress)
            if fill_x > bar_left + 2:
                draw.rounded_rectangle(
                    [bar_left, bar_y, fill_x, bar_y + bar_h],
                    radius=3, fill=config.ACCENT_GRADIENT_LEFT,
                )
            draw.text(
                (cx, bar_y + 22), "Answer reveals when typing ends...",
                fill="#484f58", font=self.chrome_font, anchor="mm",
            )
        else:
            # Reveal phase — slide-up animation
            elapsed = t - reveal_time
            slide_offset = int(35 * (1.0 - _ease_out_cubic(min(elapsed / 0.35, 1.0))))
            reveal_y = top + 60 + slide_offset
            draw.text(
                (cx, reveal_y), "\u2705 Answer:",
                fill="#7ee787", font=self.title_sub_font, anchor="mm",
            )
            content_y = reveal_y + 60
            for i, line in enumerate(getattr(self, 'output_lines', [])):
                line_y = content_y + i * getattr(self, 'output_line_height', 36)
                if line_y > config.PREVIEW_BOTTOM - 30:
                    break
                draw.text(
                    (config.PADDING + 30, line_y),
                    line, fill=config.OUTRO_CTA_COLOR, font=self.output_font,
                )

    def _get_visible_chars(self, t: float) -> int:
        """Visible chars at time t during main code phase."""
        return self._get_visible_chars_custom(
            t, self.code_start, self.code_end, self.total_chars
        )

    def _get_visible_chars_custom(
        self, t: float, start: float, end: float, total: int
    ) -> int:
        """Calculate visible chars within a custom time window."""
        if total == 0:
            return 0

        typing_start = start + config.TYPING_DELAY_START
        typing_end = end - config.TYPING_DELAY_END
        natural_time = total / config.TYPING_CPS
        typing_duration = min(natural_time, max(typing_end - typing_start, 2.0))

        if t < typing_start:
            return 0
        elif t < typing_start + typing_duration:
            progress = (t - typing_start) / typing_duration
            eased = _ease_in_out(progress)
            return int(eased * total)
        else:
            return total

    def _draw_cursor(self, draw: ImageDraw.ImageDraw, t: float, n_chars: int):
        """Draw blinking cursor with glow effect."""
        blink_on = int(t * config.CURSOR_BLINK_HZ * 2) % 2 == 0
        if not blink_on:
            return

        if n_chars == 0:
            cx, cy = config.CODE_LEFT, config.CODE_TOP
        elif n_chars < self.total_chars:
            _, last_x, last_y, _ = self.char_data[n_chars - 1]
            cx, cy = last_x + self.char_width, last_y
        else:
            return

        # Soft glow behind cursor (wider, semi-transparent effect via lighter color)
        cursor_rgb = _hex_to_rgb(config.CURSOR_COLOR)
        glow_color = _lerp_color(cursor_rgb, _hex_to_rgb(config.CODE_BG), 0.7)
        draw.rectangle(
            [cx - 3, cy, cx + 6, cy + self.line_height - 2],
            fill=glow_color,
        )
        # Main cursor bar
        draw.rectangle(
            [cx, cy + 2, cx + 2, cy + self.line_height - 4],
            fill=config.CURSOR_COLOR,
        )

    def _draw_subtitles(self, draw: ImageDraw.ImageDraw, t: float):
        """Draw karaoke subtitles — adaptive font, multi-line, tighter timing (Phase 5.7)."""
        active_group = None
        active_word_idx = -1

        for group in self.caption_groups:
            if not group:
                continue
            gs = group[0]["start_s"]
            ge = group[-1]["end_s"]
            if gs - 0.1 <= t <= ge + 0.3:     # tightened: 0.5 → 0.3
                active_group = group
                for i, wt in enumerate(group):
                    if wt["start_s"] - 0.05 <= t <= wt["end_s"] + 0.15:
                        active_word_idx = i
                        break
                break

        if not active_group:
            return

        words = [wt["text"] for wt in active_group]

        # Adaptive font — use smaller size for long groups
        full_text = "  ".join(words)
        sfont = self.subtitle_font_small if len(full_text) > 24 else self.subtitle_font

        # Multi-line split: max 4 words per line
        if len(words) > 4:
            line1_words = words[:4]
            line2_words = words[4:]
        else:
            line1_words = words
            line2_words = []

        def _render_line(line_words: list, base_y: int, word_offset: int):
            if not line_words:
                return
            line_text = "  ".join(line_words)
            bbox = sfont.getbbox(line_text)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = (self.width - tw) // 2
            pad_x, pad_y = 24, 14
            draw.rounded_rectangle(
                [tx - pad_x, base_y - pad_y,
                 tx + tw + pad_x, base_y + th + pad_y],
                radius=14, fill=config.SUBTITLE_BG_COLOR,
            )
            space_w = sfont.getlength("  ")
            wx = float(tx)
            for j, word in enumerate(line_words):
                gidx = j + word_offset
                color = (
                    config.SUBTITLE_ACTIVE_COLOR
                    if gidx == active_word_idx
                    else config.SUBTITLE_TEXT_COLOR
                )
                draw.text((int(wx) + 2, base_y + 2), word, fill="#000000", font=sfont)
                draw.text((int(wx), base_y), word, fill=color, font=sfont)
                wx += sfont.getlength(word) + space_w

        bh = sfont.getbbox("Mg")[3] - sfont.getbbox("Mg")[1]
        line_spacing = bh + 36

        if line2_words:
            _render_line(line1_words, config.SUBTITLE_Y - line_spacing, 0)
            _render_line(line2_words, config.SUBTITLE_Y, len(line1_words))
        else:
            _render_line(line1_words, config.SUBTITLE_Y, 0)
