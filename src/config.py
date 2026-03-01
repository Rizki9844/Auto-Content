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


# ══════════════════════════════════════════════════════════════
#  LAYOUT (pixel coordinates for 1080×1920 canvas)
# ══════════════════════════════════════════════════════════════
PADDING = 50

# Window chrome (title bar)
CHROME_Y = 100
CHROME_H = 48

# Code editor area
CODE_TOP = CHROME_Y + CHROME_H + 25        # 173
CODE_LEFT = PADDING + 72                    # 122  (after line-number gutter)
LINE_NUM_RIGHT_X = PADDING + 52             # 102  (right-align anchor)
GUTTER_X = PADDING + 62                     # 112  (vertical gutter separator)

# Subtitles & watermark
SUBTITLE_Y = 1500
WATERMARK_Y = 1820


# ══════════════════════════════════════════════════════════════
#  FONT SIZES
# ══════════════════════════════════════════════════════════════
CODE_FONT_SIZE = 28
LINE_NUM_FONT_SIZE = 22
SUBTITLE_FONT_SIZE = 44
WATERMARK_FONT_SIZE = 22
CHROME_FONT_SIZE = 16
TITLE_FONT_SIZE = 52
TITLE_SUB_FONT_SIZE = 30
OUTPUT_FONT_SIZE = 24
OUTRO_FONT_SIZE = 40
OUTRO_SUB_FONT_SIZE = 28


# ══════════════════════════════════════════════════════════════
#  ANIMATION TIMING
# ══════════════════════════════════════════════════════════════
TYPING_CPS = 25            # characters per second
CURSOR_BLINK_HZ = 3        # blinks per second
TYPING_DELAY_START = 0.5   # seconds of pause before typing starts
TYPING_DELAY_END = 1.0     # seconds of pause after typing finishes

# Intro / Outro timing
INTRO_DURATION = 2.0       # seconds for title card intro
OUTRO_DURATION = 2.5       # seconds for subscribe outro
OUTPUT_REVEAL_DURATION = 1.5  # seconds for output panel reveal


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
TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-GuyNeural")


# ══════════════════════════════════════════════════════════════
#  API KEYS & CREDENTIALS  (loaded from env / GitHub Secrets)
# ══════════════════════════════════════════════════════════════
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

MONGODB_URI = os.environ.get("MONGODB_URI", "")

YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")


# ══════════════════════════════════════════════════════════════
#  TELEGRAM NOTIFICATIONS
# ══════════════════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


# ══════════════════════════════════════════════════════════════
#  BRANDING
# ══════════════════════════════════════════════════════════════
CHANNEL_NAME = os.environ.get("CHANNEL_NAME", "@DevInSeconds")
