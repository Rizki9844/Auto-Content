"""
Configuration & environment variable loading.
All constants, paths, colors, and API keys are centralized here.
"""
import os
from pathlib import Path

# ─── Load .env for local development ──────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ══════════════════════════════════════════════════════════════
#  PATHS
# ══════════════════════════════════════════════════════════════
ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
OUTPUT_DIR = ROOT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# ─── Font files (bundled in repo) ─────────────────────────────
FONT_REGULAR = str(FONTS_DIR / "JetBrainsMono-Regular.ttf")
FONT_BOLD = str(FONTS_DIR / "JetBrainsMono-Bold.ttf")


# ══════════════════════════════════════════════════════════════
#  VIDEO DIMENSIONS
# ══════════════════════════════════════════════════════════════
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30


# ══════════════════════════════════════════════════════════════
#  COLOR PALETTE  (GitHub Dark theme inspired)
# ══════════════════════════════════════════════════════════════
BG_GRADIENT_TOP = (13, 17, 23)       # #0d1117
BG_GRADIENT_BOTTOM = (22, 27, 34)    # #161b22

CHROME_BG = "#1c2128"
CHROME_DOT_COLORS = ("#ff5f57", "#febc2e", "#28c840")
CODE_BG = "#0d1117"
LINE_HIGHLIGHT = "#161b22"
SEPARATOR = "#30363d"
LINE_NUM_COLOR = "#484f58"
DEFAULT_TEXT_COLOR = "#e6edf3"
CURSOR_COLOR = "#58a6ff"

SUBTITLE_TEXT_COLOR = "#ffffff"
SUBTITLE_ACTIVE_COLOR = "#ffd700"
SUBTITLE_BG_COLOR = "#010409"
WATERMARK_COLOR = "#484f58"
PREVIEW_RUNNING_COLOR = "#58a6ff"     # spinner + "Running..." text


# ══════════════════════════════════════════════════════════════
#  SPLIT-SCREEN LAYOUT (1080×1920 canvas)
# ══════════════════════════════════════════════════════════════
PADDING = 50

# ── Preview panel (top) — output / demo / concept ────────────
PREVIEW_Y = 50
PREVIEW_CHROME_H = 40
PREVIEW_CONTENT_Y = PREVIEW_Y + PREVIEW_CHROME_H + 15   # 105
PREVIEW_CODE_TOP = PREVIEW_Y + PREVIEW_CHROME_H + 25    # 115
PREVIEW_BOTTOM = 680

# ── Gradient divider ─────────────────────────────────────────
DIVIDER_Y = 700

# ── Code editor panel (bottom) — typing animation ────────────
CHROME_Y = 730
CHROME_H = 44
CODE_TOP = CHROME_Y + CHROME_H + 25        # 799
CODE_LEFT = PADDING + 72                    # 122
LINE_NUM_RIGHT_X = PADDING + 52             # 102
GUTTER_X = PADDING + 62                     # 112

# ── Subtitles & watermark ────────────────────────────────────
SUBTITLE_Y = 1520
WATERMARK_Y = 1840


# ══════════════════════════════════════════════════════════════
#  FONT SIZES
# ══════════════════════════════════════════════════════════════
CODE_FONT_SIZE = 24
LINE_NUM_FONT_SIZE = 20
SUBTITLE_FONT_SIZE = 42
WATERMARK_FONT_SIZE = 20
CHROME_FONT_SIZE = 15
TITLE_FONT_SIZE = 48
TITLE_SUB_FONT_SIZE = 28
OUTPUT_FONT_SIZE = 22
OUTRO_FONT_SIZE = 40
OUTRO_SUB_FONT_SIZE = 28
PREVIEW_CODE_FONT_SIZE = 22
PREVIEW_LINE_NUM_SIZE = 18

# ══════════════════════════════════════════════════════════════
#  ANIMATION TIMING
# ══════════════════════════════════════════════════════════════
TYPING_CPS = 18            # characters per second (slower = more readable)
CURSOR_BLINK_HZ = 3        # blinks per second
TYPING_DELAY_START = 0.3   # seconds of pause before typing starts
TYPING_DELAY_END = 1.0     # seconds of pause after typing finishes

# Intro / Outro timing
INTRO_DURATION = 0.0       # seconds (0 = no intro, jump straight to code)
OUTRO_DURATION = 3.0       # seconds for creative outro card
OUTPUT_REVEAL_DURATION = 1.0  # seconds for output panel reveal


# ══════════════════════════════════════════════════════════════
#  OUTPUT PANEL  (terminal-style panel below code)
# ══════════════════════════════════════════════════════════════
OUTPUT_BG = "#161b22"
OUTPUT_HEADER_BG = "#1c2128"
OUTPUT_TEXT_COLOR = "#7ee787"     # green terminal text
OUTPUT_ERROR_COLOR = "#ff7b72"   # red for errors
OUTPUT_PROMPT_COLOR = "#8b949e"  # grey for "$ " prompt


# ══════════════════════════════════════════════════════════════
#  INTRO / OUTRO COLORS
# ══════════════════════════════════════════════════════════════
ACCENT_GRADIENT_LEFT = "#58a6ff"     # blue accent
ACCENT_GRADIENT_RIGHT = "#d2a8ff"    # purple accent
INTRO_TITLE_COLOR = "#ffffff"
INTRO_SUBTITLE_COLOR = "#8b949e"
OUTRO_CTA_COLOR = "#ffd700"          # gold "Subscribe" text


# ══════════════════════════════════════════════════════════════
#  CONTENT TYPES
# ══════════════════════════════════════════════════════════════
CONTENT_TYPES = ["tip", "output_demo", "quiz", "before_after"]


# ══════════════════════════════════════════════════════════════
#  TTS  (Microsoft Edge Neural Voices via edge-tts)
# ══════════════════════════════════════════════════════════════
TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-ChristopherNeural")
TTS_RATE = os.environ.get("TTS_RATE", "+10%")  # speed up to compress pauses


# ══════════════════════════════════════════════════════════════
#  API KEYS & CREDENTIALS  (loaded from env / GitHub Secrets)
# ══════════════════════════════════════════════════════════════
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

MONGODB_URI = os.environ.get("MONGODB_URI", "")

YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")

# ─── TikTok Content Posting API ──────────────────────────────
TIKTOK_ACCESS_TOKEN = os.environ.get("TIKTOK_ACCESS_TOKEN", "")

# ─── Instagram Graph API ─────────────────────────────────────
INSTAGRAM_ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
INSTAGRAM_ACCOUNT_ID = os.environ.get("INSTAGRAM_ACCOUNT_ID", "")

# ─── Multi-platform upload targets ───────────────────────────
# Comma-separated: "youtube", "tiktok", "instagram"
UPLOAD_TARGETS = os.environ.get("UPLOAD_TARGETS", "youtube")


# ══════════════════════════════════════════════════════════════
#  THEME SYSTEM  (Phase 4.4)
# ══════════════════════════════════════════════════════════════
# Name of the color theme to load from themes/<name>.json
ACTIVE_THEME = os.environ.get("ACTIVE_THEME", "github_dark")

# Set to "1" to rotate themes daily (overrides ACTIVE_THEME)
AUTO_ROTATE_THEMES = os.environ.get("AUTO_ROTATE_THEMES", "0")

# Comma-separated list used when AUTO_ROTATE_THEMES=1
THEME_ROTATION_LIST = os.environ.get(
    "THEME_ROTATION_LIST", "github_dark,monokai,dracula"
)


# ══════════════════════════════════════════════════════════════
#  THUMBNAIL  (Phase 4.6)
# ══════════════════════════════════════════════════════════════
# Set to "1" to generate + upload a custom thumbnail after each upload
ENABLE_THUMBNAILS = os.environ.get("ENABLE_THUMBNAILS", "0")


# ══════════════════════════════════════════════════════════════
#  TELEGRAM NOTIFICATIONS
# ══════════════════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


# ══════════════════════════════════════════════════════════════
#  BRANDING
# ══════════════════════════════════════════════════════════════
CHANNEL_NAME = os.environ.get("CHANNEL_NAME", "@DevInSeconds")
