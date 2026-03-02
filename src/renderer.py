"""
Video frame renderer v2 — Pillow + Pygments.
Enhanced with:
  - Intro title card with gradient accent
  - Multiple content types (tip, output_demo, quiz, before_after)
  - Terminal output panel for code execution results
  - Outro with subscribe CTA
  - Smoother animations with easing
  - Karaoke-style subtitles synced to TTS
  - Channel branding watermark
"""
import logging
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
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
    Token.Keyword.Type:             "#ffa657",
    Token.Name.Function:            "#d2a8ff",
    Token.Name.Function.Magic:      "#d2a8ff",
    Token.Name.Class:               "#ffa657",
    Token.Name.Decorator:           "#d2a8ff",
    Token.Name.Builtin:             "#ffa657",
    Token.Name.Builtin.Pseudo:      "#79c0ff",
    Token.Name.Tag:                 "#7ee787",
    Token.Name.Attribute:           "#79c0ff",
    Token.Name.Variable:            "#ffa657",
    Token.Name.Constant:            "#79c0ff",
    Token.Literal.String:           "#a5d6ff",
    Token.Literal.String.Doc:       "#8b949e",
    Token.Literal.String.Interpol:  "#a5d6ff",
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
    "output_demo": "▶ OUTPUT DEMO",
    "quiz": "🧠 CODE QUIZ",
    "before_after": "✨ BEFORE → AFTER",
}


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

        logger.info(
            f"FrameRenderer ready: type={self.content_type}, "
            f"{self.total_chars} chars, {self.total_lines} lines, "
            f"output={'yes' if self.code_output else 'no'}"
        )

    # ──────────────────────────────────────────────────────────
    #  INITIALIZATION
    # ──────────────────────────────────────────────────────────

    def _load_fonts(self):
        """Load font files and compute character metrics."""
        self.code_font = ImageFont.truetype(config.FONT_REGULAR, config.CODE_FONT_SIZE)
        self.code_font_bold = ImageFont.truetype(config.FONT_BOLD, config.CODE_FONT_SIZE)
        self.line_num_font = ImageFont.truetype(config.FONT_REGULAR, config.LINE_NUM_FONT_SIZE)
        self.subtitle_font = ImageFont.truetype(config.FONT_BOLD, config.SUBTITLE_FONT_SIZE)
        self.watermark_font = ImageFont.truetype(config.FONT_REGULAR, config.WATERMARK_FONT_SIZE)
        self.chrome_font = ImageFont.truetype(config.FONT_REGULAR, config.CHROME_FONT_SIZE)
        self.title_font = ImageFont.truetype(config.FONT_BOLD, config.TITLE_FONT_SIZE)
        self.title_sub_font = ImageFont.truetype(config.FONT_REGULAR, config.TITLE_SUB_FONT_SIZE)
        self.output_font = ImageFont.truetype(config.FONT_REGULAR, config.OUTPUT_FONT_SIZE)
        self.outro_font = ImageFont.truetype(config.FONT_BOLD, config.OUTRO_FONT_SIZE)
        self.outro_sub_font = ImageFont.truetype(config.FONT_REGULAR, config.OUTRO_SUB_FONT_SIZE)

        # Monospace char dimensions
        bbox = self.code_font.getbbox("M")
        self.char_width = bbox[2] - bbox[0]
        self.line_height = int(config.CODE_FONT_SIZE * 1.65)

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
        """Pre-compute (char, x, y, color) for every printable character."""
        self.char_data: list[tuple[str, int, int, str]] = []
        x = config.CODE_LEFT
        y = config.CODE_TOP
        self.total_lines = 1

        for token_type, token_text in self.tokens:
            color = self._resolve_color(token_type)
            for ch in token_text:
                if ch == "\n":
                    x = config.CODE_LEFT
                    y += self.line_height
                    self.total_lines += 1
                elif ch == "\t":
                    for _ in range(4):
                        self.char_data.append((" ", x, y, color))
                        x += self.char_width
                else:
                    self.char_data.append((ch, x, y, color))
                    x += self.char_width

        self.total_chars = len(self.char_data)

        # Also compute before_char_data for before_after type
        if self.code_before:
            self.before_char_data = []
            bx = config.CODE_LEFT
            by = config.CODE_TOP
            self.before_total_lines = 1
            for token_type, token_text in self.before_tokens:
                color = self._resolve_color(token_type)
                for ch in token_text:
                    if ch == "\n":
                        bx = config.CODE_LEFT
                        by += self.line_height
                        self.before_total_lines += 1
                    elif ch == "\t":
                        for _ in range(4):
                            self.before_char_data.append((" ", bx, by, color))
                            bx += self.char_width
                    else:
                        self.before_char_data.append((ch, bx, by, color))
                        bx += self.char_width
            self.before_total_chars = len(self.before_char_data)

    def _resolve_color(self, token_type) -> str:
        tt = token_type
        while tt:
            if tt in SYNTAX_COLORS:
                return SYNTAX_COLORS[tt]
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
        return Image.fromarray(arr, "RGB")

    def _create_base_image(self):
        """Build the static code editor base image."""
        self.base = self._gradient_bg.copy()
        draw = ImageDraw.Draw(self.base)

        # Code panel bg
        panel_bottom = config.CODE_TOP + (max(self.total_lines, 6) * self.line_height) + 40
        self._panel_bottom = panel_bottom
        draw.rounded_rectangle(
            [config.PADDING, config.CHROME_Y, self.width - config.PADDING, panel_bottom],
            radius=12, fill=config.CODE_BG,
        )

        # Chrome title bar
        chrome_bottom = config.CHROME_Y + config.CHROME_H
        draw.rounded_rectangle(
            [config.PADDING, config.CHROME_Y,
             self.width - config.PADDING, config.CHROME_Y + 24],
            radius=12, fill=config.CHROME_BG,
        )
        draw.rectangle(
            [config.PADDING, config.CHROME_Y + 12,
             self.width - config.PADDING, chrome_bottom],
            fill=config.CHROME_BG,
        )

        # Traffic lights
        dot_cy = config.CHROME_Y + config.CHROME_H // 2
        dot_start_x = config.PADDING + 28
        for i, color in enumerate(config.CHROME_DOT_COLORS):
            cx = dot_start_x + i * 25
            draw.ellipse([cx - 7, dot_cy - 7, cx + 7, dot_cy + 7], fill=color)

        # Filename
        ext = EXT_MAP.get(self.language, ".txt")
        filename = f"main{ext}"
        draw.text(
            (self.width // 2, dot_cy), filename,
            fill="#8b949e", font=self.chrome_font, anchor="mm",
        )

        # Separator
        draw.line(
            [(config.PADDING, chrome_bottom), (self.width - config.PADDING, chrome_bottom)],
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

        # Content type badge (top-left, above code panel)
        badge_text = CONTENT_TYPE_LABELS.get(self.content_type, "💡 TIP")
        badge_bbox = self.chrome_font.getbbox(badge_text)
        badge_w = badge_bbox[2] - badge_bbox[0] + 24
        badge_h = badge_bbox[3] - badge_bbox[1] + 12
        badge_x = config.PADDING
        badge_y = config.CHROME_Y - badge_h - 10
        draw.rounded_rectangle(
            [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
            radius=6, fill="#58a6ff",
        )
        draw.text(
            (badge_x + 12, badge_y + 6), badge_text,
            fill="#ffffff", font=self.chrome_font,
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

        # Title text (word-wrap)
        title_text = self.title.replace(" #Shorts", "").replace(" #shorts", "").strip()
        self._draw_wrapped_text(
            draw, title_text, self.title_font,
            config.INTRO_TITLE_COLOR, center_y, max_width=self.width - 160,
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

    def _create_outro_image(self):
        """Create a creative outro card with code-themed design."""
        self.outro = self._gradient_bg.copy()
        draw = ImageDraw.Draw(self.outro)

        cx = self.width // 2
        cy = self.height // 2

        # ── Decorative code comment (top) ─────────────────────
        draw.text(
            (cx, cy - 200),
            "// TODO: hit subscribe 😄",
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
        draw.text(
            (cx, cy + 165),
            "New coding tips every day! 🚀",
            fill=config.OUTRO_CTA_COLOR,
            font=self.outro_sub_font,
            anchor="mm",
        )

    def _prepare_output_panel(self):
        """Pre-render the output panel data."""
        if not self.code_output:
            return

        self.output_top = self._panel_bottom + 20
        output_line_h = int(config.OUTPUT_FONT_SIZE * 1.5)
        output_lines = self.code_output.strip().split("\n")
        self.output_lines = output_lines[:10]
        self.output_line_height = output_line_h
        self.output_panel_height = len(self.output_lines) * output_line_h + 60
        self.output_bottom = self.output_top + self.output_panel_height

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
        """Render outro card with fast crossfade."""
        elapsed = t - self.outro_start
        # Quick 0.8s crossfade so creative outro is visible longer
        progress = min(elapsed / 0.8, 1.0)
        alpha = _ease_out_cubic(progress)
        frame = Image.blend(self.base, self.outro, alpha)
        return np.array(frame)

    def _render_code_phase(self, t: float) -> np.ndarray:
        """Render the main code editor phase."""
        frame = self.base.copy()
        draw = ImageDraw.Draw(frame)

        # Before/after: show both phases
        if self.content_type == "before_after" and self.code_before:
            return self._render_before_after(t, frame, draw)

        # Normal typing
        n_chars = self._get_visible_chars(t)

        # Current line highlight
        if 0 < n_chars <= self.total_chars:
            idx = min(n_chars - 1, self.total_chars - 1)
            _, _, cur_y, _ = self.char_data[idx]
            draw.rectangle(
                [config.PADDING + 1, cur_y - 2,
                 self.width - config.PADDING - 1, cur_y + self.line_height - 4],
                fill=config.LINE_HIGHLIGHT,
            )

        # Draw code characters
        for i in range(n_chars):
            ch, x, y, color = self.char_data[i]
            if ch.strip():
                draw.text((x, y), ch, fill=color, font=self.code_font)

        # Cursor
        self._draw_cursor(draw, t, n_chars)

        # Output panel
        if self.code_output and hasattr(self, 'output_reveal_time'):
            self._draw_output_panel(draw, t)

        # Subtitles
        self._draw_subtitles(draw, t)

        return np.array(frame)

    def _render_before_after(
        self, t: float, frame: Image.Image, draw: ImageDraw.ImageDraw
    ) -> np.ndarray:
        """Render before/after — old code first half, new code second half."""
        code_duration = self.code_end - self.code_start
        midpoint = self.code_start + code_duration * 0.45

        if t < midpoint:
            # BEFORE phase
            self._draw_phase_badge(draw, "❌ BEFORE", "#ff7b72")
            n = self._get_visible_chars_custom(
                t, self.code_start, midpoint - 0.5,
                getattr(self, 'before_total_chars', 0),
            )
            for i in range(min(n, len(getattr(self, 'before_char_data', [])))):
                ch, x, y, color = self.before_char_data[i]
                if ch.strip():
                    draw.text((x, y), ch, fill=color, font=self.code_font)
        else:
            # Transition flash
            tr = min((t - midpoint) / 0.3, 1.0)
            if tr < 0.5:
                overlay = Image.new("RGB", (self.width, self.height), "#58a6ff")
                frame = Image.blend(frame, overlay, (1.0 - tr * 2) * 0.3)
                draw = ImageDraw.Draw(frame)

            # AFTER phase
            self._draw_phase_badge(draw, "✅ AFTER", "#7ee787")
            n = self._get_visible_chars_custom(
                t, midpoint + 0.3, self.code_end - 0.5, self.total_chars,
            )
            for i in range(n):
                ch, x, y, color = self.char_data[i]
                if ch.strip():
                    draw.text((x, y), ch, fill=color, font=self.code_font)

        self._draw_subtitles(draw, t)
        return np.array(frame)

    def _draw_phase_badge(self, draw: ImageDraw.ImageDraw, text: str, color: str):
        """Draw BEFORE/AFTER badge above code panel."""
        badge_x = self.width - config.PADDING - 160
        badge_y = config.CHROME_Y - 32
        draw.rounded_rectangle(
            [badge_x, badge_y, badge_x + 150, badge_y + 26],
            radius=6, fill=color,
        )
        draw.text(
            (badge_x + 75, badge_y + 13), text,
            fill="#0d1117", font=self.chrome_font, anchor="mm",
        )

    def _draw_output_panel(self, draw: ImageDraw.ImageDraw, t: float):
        """Draw terminal-style output panel below code."""
        if t < self.output_reveal_time:
            return

        reveal_progress = min(
            (t - self.output_reveal_time) / config.OUTPUT_REVEAL_DURATION, 1.0
        )
        alpha = _ease_out_cubic(reveal_progress)
        visible_height = int(self.output_panel_height * alpha)
        if visible_height < 10:
            return

        # Header
        header_h = 30
        draw.rounded_rectangle(
            [config.PADDING, self.output_top,
             self.width - config.PADDING, self.output_top + header_h],
            radius=8, fill=config.OUTPUT_HEADER_BG,
        )
        header_label = "▶ Output" if self.content_type != "quiz" else "🧠 Answer"
        draw.text(
            (config.PADDING + 20, self.output_top + 8),
            header_label, fill="#8b949e", font=self.chrome_font,
        )

        # Body
        body_top = self.output_top + header_h
        draw.rectangle(
            [config.PADDING, body_top,
             self.width - config.PADDING,
             min(body_top + visible_height, self.output_bottom)],
            fill=config.OUTPUT_BG,
        )

        # Lines
        total = len(self.output_lines)
        visible = max(1, int(total * alpha))

        for i in range(visible):
            line_y = body_top + 15 + i * self.output_line_height
            if line_y > self.output_bottom - 10:
                break
            draw.text(
                (config.PADDING + 20, line_y),
                "❯ " if i == 0 else "  ",
                fill=config.OUTPUT_PROMPT_COLOR, font=self.output_font,
            )
            text_color = config.OUTPUT_TEXT_COLOR
            if self.content_type == "quiz":
                text_color = config.OUTRO_CTA_COLOR
            draw.text(
                (config.PADDING + 55, line_y),
                self.output_lines[i],
                fill=text_color, font=self.output_font,
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
        """Draw blinking cursor."""
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

        draw.rectangle(
            [cx, cy + 2, cx + 3, cy + self.line_height - 6],
            fill=config.CURSOR_COLOR,
        )

    def _draw_subtitles(self, draw: ImageDraw.ImageDraw, t: float):
        """Draw karaoke-style subtitles."""
        active_group = None
        active_word_idx = -1

        for group in self.caption_groups:
            if not group:
                continue
            gs = group[0]["start_s"]
            ge = group[-1]["end_s"]
            if gs - 0.1 <= t <= ge + 0.5:
                active_group = group
                for i, wt in enumerate(group):
                    if wt["start_s"] - 0.05 <= t <= wt["end_s"] + 0.15:
                        active_word_idx = i
                        break
                break

        if not active_group:
            return

        words = [wt["text"] for wt in active_group]
        full_text = "  ".join(words)
        bbox = self.subtitle_font.getbbox(full_text)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        text_x = (self.width - text_w) // 2
        text_y = config.SUBTITLE_Y

        pad_x, pad_y = 28, 18
        draw.rounded_rectangle(
            [text_x - pad_x, text_y - pad_y,
             text_x + text_w + pad_x, text_y + text_h + pad_y],
            radius=16, fill=config.SUBTITLE_BG_COLOR,
        )

        space_w = self.subtitle_font.getlength("  ")
        word_x = float(text_x)
        for i, word in enumerate(words):
            color = (
                config.SUBTITLE_ACTIVE_COLOR
                if i == active_word_idx
                else config.SUBTITLE_TEXT_COLOR
            )
            draw.text((int(word_x), text_y), word, fill=color, font=self.subtitle_font)
            word_x += self.subtitle_font.getlength(word) + space_w
