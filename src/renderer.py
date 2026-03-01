"""
Video frame renderer — Pillow + Pygments.
Generates individual video frames with:
  - Dark-themed code editor UI
  - Animated typing effect with syntax highlighting
  - Dynamic word-by-word subtitles synced to TTS audio
  - Channel branding watermark
"""
import logging
from functools import lru_cache

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
    # Keywords
    Token.Keyword:                  "#ff7b72",
    Token.Keyword.Constant:         "#79c0ff",
    Token.Keyword.Declaration:      "#ff7b72",
    Token.Keyword.Namespace:        "#ff7b72",
    Token.Keyword.Pseudo:           "#ff7b72",
    Token.Keyword.Reserved:         "#ff7b72",
    Token.Keyword.Type:             "#ffa657",

    # Names
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

    # Literals
    Token.Literal.String:           "#a5d6ff",
    Token.Literal.String.Doc:       "#8b949e",
    Token.Literal.String.Interpol:  "#a5d6ff",
    Token.Literal.String.Escape:    "#79c0ff",
    Token.Literal.String.Affix:     "#ff7b72",
    Token.Literal.Number:           "#79c0ff",
    Token.Literal.Number.Integer:   "#79c0ff",
    Token.Literal.Number.Float:     "#79c0ff",

    # Comments
    Token.Comment:                  "#8b949e",
    Token.Comment.Single:           "#8b949e",
    Token.Comment.Multiline:        "#8b949e",
    Token.Comment.Hashbang:         "#8b949e",
    Token.Comment.Preproc:          "#ff7b72",

    # Operators & Punctuation
    Token.Operator:                 "#ff7b72",
    Token.Operator.Word:            "#ff7b72",
    Token.Punctuation:              "#e6edf3",

    # Generic
    Token.Name:                     "#e6edf3",
    Token.Text:                     "#e6edf3",
    Token.Text.Whitespace:          "#e6edf3",
}

# File extension mapping
EXT_MAP = {
    "python": ".py", "javascript": ".js", "typescript": ".ts",
    "css": ".css", "html": ".html", "sql": ".sql", "bash": ".sh",
    "go": ".go", "rust": ".rs", "java": ".java", "cpp": ".cpp",
    "c": ".c", "ruby": ".rb", "php": ".php", "swift": ".swift",
    "kotlin": ".kt", "json": ".json", "yaml": ".yml", "tsx": ".tsx",
    "jsx": ".jsx",
}


class FrameRenderer:
    """
    Pre-computes static elements and renders per-frame dynamic content.
    Designed to be called once per video, then render_frame(t) per frame.
    """

    def __init__(
        self,
        code: str,
        language: str,
        word_timestamps: list,
        duration: float,
        channel_name: str | None = None,
    ):
        self.code = code.rstrip()
        self.language = language.lower()
        self.duration = duration
        self.channel_name = channel_name or config.CHANNEL_NAME
        self.width = config.VIDEO_WIDTH
        self.height = config.VIDEO_HEIGHT

        # Convert WordTimestamp objects to dicts for easier access
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
        self._tokenize_code()
        self._compute_char_positions()
        self._create_base_image()
        self._create_subtitle_groups()

        logger.info(
            f"FrameRenderer ready: {self.total_chars} chars, "
            f"{self.total_lines} lines, {len(self.caption_groups)} caption groups"
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

    def _compute_char_positions(self):
        """
        Pre-compute the (char, x, y, color) data for every printable character.
        This makes per-frame rendering O(n) with minimal computation.
        """
        self.char_data: list[tuple[str, int, int, str]] = []  # (char, x, y, color)
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
                    # Tab = 4 spaces (add invisible chars for consistent typing speed)
                    for _ in range(4):
                        self.char_data.append((" ", x, y, color))
                        x += self.char_width
                else:
                    self.char_data.append((ch, x, y, color))
                    x += self.char_width

        self.total_chars = len(self.char_data)

    def _resolve_color(self, token_type) -> str:
        """Walk up the Pygments token hierarchy to find a matching color."""
        tt = token_type
        while tt:
            if tt in SYNTAX_COLORS:
                return SYNTAX_COLORS[tt]
            tt = tt.parent
        return config.DEFAULT_TEXT_COLOR

    def _create_base_image(self):
        """
        Build the static base image (rendered once, copied per frame):
        gradient background + window chrome + line numbers + watermark.
        """
        # ── Gradient background ───────────────────────────────
        self.base = Image.new("RGB", (self.width, self.height))
        draw = ImageDraw.Draw(self.base)

        r1, g1, b1 = config.BG_GRADIENT_TOP
        r2, g2, b2 = config.BG_GRADIENT_BOTTOM
        for y_pos in range(self.height):
            ratio = y_pos / self.height
            r = int(r1 + (r2 - r1) * ratio)
            g = int(g1 + (g2 - g1) * ratio)
            b = int(b1 + (b2 - b1) * ratio)
            draw.line([(0, y_pos), (self.width, y_pos)], fill=(r, g, b))

        # ── Window panel (code editor background) ─────────────
        panel_bottom = config.CODE_TOP + (max(self.total_lines, 6) * self.line_height) + 40
        draw.rounded_rectangle(
            [config.PADDING, config.CHROME_Y, self.width - config.PADDING, panel_bottom],
            radius=12,
            fill=config.CODE_BG,
        )

        # ── Chrome title bar ──────────────────────────────────
        chrome_bottom = config.CHROME_Y + config.CHROME_H
        # Top rounded part
        draw.rounded_rectangle(
            [config.PADDING, config.CHROME_Y,
             self.width - config.PADDING, config.CHROME_Y + 24],
            radius=12,
            fill=config.CHROME_BG,
        )
        # Full chrome bar (flat bottom)
        draw.rectangle(
            [config.PADDING, config.CHROME_Y + 12,
             self.width - config.PADDING, chrome_bottom],
            fill=config.CHROME_BG,
        )

        # Traffic light dots
        dot_cy = config.CHROME_Y + config.CHROME_H // 2
        dot_start_x = config.PADDING + 28
        for i, color in enumerate(config.CHROME_DOT_COLORS):
            cx = dot_start_x + i * 25
            draw.ellipse([cx - 7, dot_cy - 7, cx + 7, dot_cy + 7], fill=color)

        # Filename text (centered in chrome bar)
        ext = EXT_MAP.get(self.language, ".txt")
        filename = f"main{ext}"
        draw.text(
            (self.width // 2, dot_cy),
            filename,
            fill="#8b949e",
            font=self.chrome_font,
            anchor="mm",
        )

        # ── Separator line ────────────────────────────────────
        draw.line(
            [(config.PADDING, chrome_bottom), (self.width - config.PADDING, chrome_bottom)],
            fill=config.SEPARATOR,
            width=1,
        )

        # ── Line numbers ──────────────────────────────────────
        for i in range(self.total_lines):
            ln_y = config.CODE_TOP + i * self.line_height
            draw.text(
                (config.LINE_NUM_RIGHT_X, ln_y),
                str(i + 1),
                fill=config.LINE_NUM_COLOR,
                font=self.line_num_font,
                anchor="ra",
            )

        # ── Gutter separator ──────────────────────────────────
        gutter_top_y = config.CODE_TOP - 8
        gutter_bottom_y = config.CODE_TOP + self.total_lines * self.line_height + 10
        draw.line(
            [(config.GUTTER_X, gutter_top_y), (config.GUTTER_X, gutter_bottom_y)],
            fill=config.SEPARATOR,
            width=1,
        )

        # ── Watermark ─────────────────────────────────────────
        draw.text(
            (self.width - config.PADDING - 10, config.WATERMARK_Y),
            self.channel_name,
            fill=config.WATERMARK_COLOR,
            font=self.watermark_font,
            anchor="ra",
        )

    def _create_subtitle_groups(self):
        """
        Group word timestamps into caption chunks (5–7 words each).
        Splits on punctuation or max word count.
        """
        self.caption_groups: list[list[dict]] = []
        current_group: list[dict] = []

        for wt in self.word_timestamps:
            current_group.append(wt)
            text = wt["text"]
            # Split on punctuation or max group size
            if (
                len(current_group) >= 6
                or text.endswith((".", "!", "?", ";"))
                or (text.endswith(",") and len(current_group) >= 4)
            ):
                self.caption_groups.append(current_group)
                current_group = []

        if current_group:
            self.caption_groups.append(current_group)

    # ──────────────────────────────────────────────────────────
    #  PER-FRAME RENDERING
    # ──────────────────────────────────────────────────────────

    def render_frame(self, t: float) -> np.ndarray:
        """
        Render a single video frame at time `t` seconds.
        Returns numpy array of shape (height, width, 3) with dtype uint8.
        """
        # Copy the pre-rendered base image
        frame = self.base.copy()
        draw = ImageDraw.Draw(frame)

        # ── Calculate visible characters ──────────────────────
        n_chars = self._get_visible_chars(t)

        # ── Current line highlight ────────────────────────────
        if 0 < n_chars <= self.total_chars:
            idx = min(n_chars - 1, self.total_chars - 1)
            _, _, cur_y, _ = self.char_data[idx]
            draw.rectangle(
                [config.PADDING + 1, cur_y - 2,
                 self.width - config.PADDING - 1, cur_y + self.line_height - 4],
                fill=config.LINE_HIGHLIGHT,
            )

        # ── Draw code characters ──────────────────────────────
        for i in range(n_chars):
            ch, x, y, color = self.char_data[i]
            if ch.strip():  # skip spaces (invisible anyway)
                draw.text((x, y), ch, fill=color, font=self.code_font)

        # ── Typing cursor ─────────────────────────────────────
        self._draw_cursor(draw, t, n_chars)

        # ── Subtitles ─────────────────────────────────────────
        self._draw_subtitles(draw, t)

        return np.array(frame)

    def _get_visible_chars(self, t: float) -> int:
        """Calculate how many characters should be visible at time t."""
        if self.total_chars == 0:
            return 0

        # Calculate typing duration (proportional to code length)
        natural_typing_time = self.total_chars / config.TYPING_CPS
        max_typing_time = self.duration - config.TYPING_DELAY_START - config.TYPING_DELAY_END
        typing_duration = min(natural_typing_time, max(max_typing_time, 2.0))

        if t < config.TYPING_DELAY_START:
            return 0
        elif t < config.TYPING_DELAY_START + typing_duration:
            progress = (t - config.TYPING_DELAY_START) / typing_duration
            return int(progress * self.total_chars)
        else:
            return self.total_chars

    def _draw_cursor(self, draw: ImageDraw.ImageDraw, t: float, n_chars: int):
        """Draw a blinking cursor at the current typing position."""
        blink_on = int(t * config.CURSOR_BLINK_HZ * 2) % 2 == 0
        if not blink_on:
            return

        if n_chars == 0:
            # Cursor at start position
            cx, cy = config.CODE_LEFT, config.CODE_TOP
        elif n_chars < self.total_chars:
            # Cursor after last typed character
            _, last_x, last_y, _ = self.char_data[n_chars - 1]
            cx, cy = last_x + self.char_width, last_y
        else:
            # All typed — no cursor
            return

        draw.rectangle(
            [cx, cy + 2, cx + 3, cy + self.line_height - 6],
            fill=config.CURSOR_COLOR,
        )

    def _draw_subtitles(self, draw: ImageDraw.ImageDraw, t: float):
        """
        Draw karaoke-style subtitles: all words visible,
        currently spoken word highlighted in yellow.
        """
        # Find the active caption group
        active_group = None
        active_word_idx = -1

        for group in self.caption_groups:
            if not group:
                continue
            group_start = group[0]["start_s"]
            group_end = group[-1]["end_s"]

            if group_start - 0.1 <= t <= group_end + 0.5:
                active_group = group
                # Find which word is currently spoken
                for i, wt in enumerate(group):
                    if wt["start_s"] - 0.05 <= t <= wt["end_s"] + 0.15:
                        active_word_idx = i
                        break
                break

        if not active_group:
            return

        # ── Measure subtitle text ─────────────────────────────
        words = [wt["text"] for wt in active_group]
        full_text = "  ".join(words)
        bbox = self.subtitle_font.getbbox(full_text)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        text_x = (self.width - text_w) // 2
        text_y = config.SUBTITLE_Y

        # ── Background pill ───────────────────────────────────
        pad_x, pad_y = 28, 18
        draw.rounded_rectangle(
            [text_x - pad_x, text_y - pad_y,
             text_x + text_w + pad_x, text_y + text_h + pad_y],
            radius=16,
            fill=config.SUBTITLE_BG_COLOR,
        )

        # ── Draw words with highlighting ──────────────────────
        space_w = self.subtitle_font.getlength("  ")
        word_x = float(text_x)

        for i, word in enumerate(words):
            color = (
                config.SUBTITLE_ACTIVE_COLOR
                if i == active_word_idx
                else config.SUBTITLE_TEXT_COLOR
            )
            draw.text((int(word_x), text_y), word, fill=color, font=self.subtitle_font)
            word_w = self.subtitle_font.getlength(word)
            word_x += word_w + space_w
