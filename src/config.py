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
#  VIDEO DIMENSIONS & RESOLUTION (Phase 11.5)
# ══════════════════════════════════════════════════════════════
VIDEO_RESOLUTION = os.environ.get("VIDEO_RESOLUTION", "1080p").lower()
SCALE = 2 if VIDEO_RESOLUTION == "4k" else 1

VIDEO_WIDTH = 1080 * SCALE
VIDEO_HEIGHT = 1920 * SCALE
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
#  SPLIT-SCREEN LAYOUT (Canvas config)
# ══════════════════════════════════════════════════════════════
PADDING = 40 * SCALE

# ── Preview panel (top) — output / demo / concept ────────────
PREVIEW_Y = 50 * SCALE
PREVIEW_CHROME_H = 40 * SCALE
PREVIEW_CONTENT_Y = PREVIEW_Y + PREVIEW_CHROME_H + (15 * SCALE)
PREVIEW_CODE_TOP = PREVIEW_Y + PREVIEW_CHROME_H + (25 * SCALE)
PREVIEW_BOTTOM = 680 * SCALE

# ── Gradient divider ─────────────────────────────────────────
DIVIDER_Y = 700 * SCALE

# ── Code editor panel (bottom) — typing animation ────────────
CHROME_Y = 730 * SCALE
CHROME_H = 44 * SCALE
CODE_TOP = CHROME_Y + CHROME_H + (25 * SCALE)
CODE_LEFT = PADDING + (72 * SCALE)
LINE_NUM_RIGHT_X = PADDING + (52 * SCALE)
GUTTER_X = PADDING + (62 * SCALE)

# ── Subtitles & watermark ────────────────────────────────────
SUBTITLE_Y = 1480 * SCALE
WATERMARK_Y = 1840 * SCALE

# ── CTA Overlay (Phase 10.1) ─────────────────────────────────
CTA_Y = 1750 * SCALE
CTA_HEIGHT = 80 * SCALE
CTA_RADIUS = 40 * SCALE


# ══════════════════════════════════════════════════════════════
#  FONT SIZES
# ══════════════════════════════════════════════════════════════
CODE_FONT_SIZE = 26 * SCALE
LINE_NUM_FONT_SIZE = 20 * SCALE
SUBTITLE_FONT_SIZE = 48 * SCALE
WATERMARK_FONT_SIZE = 16 * SCALE
CHROME_FONT_SIZE = 15 * SCALE
TITLE_FONT_SIZE = 48 * SCALE
TITLE_SUB_FONT_SIZE = 28 * SCALE
OUTPUT_FONT_SIZE = 22 * SCALE
OUTRO_FONT_SIZE = 40 * SCALE
OUTRO_SUB_FONT_SIZE = 28 * SCALE
PREVIEW_CODE_FONT_SIZE = 22 * SCALE
PREVIEW_LINE_NUM_SIZE = 18 * SCALE
CTA_FONT_SIZE = 32 * SCALE


# ══════════════════════════════════════════════════════════════
#  ANIMATION TIMING
# ══════════════════════════════════════════════════════════════
TYPING_CPS = 18
CURSOR_BLINK_HZ = 3
LINE_SLIDE_OFFSET = 60 * SCALE     # pixels slide-in from left for each new line
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
CONTENT_TYPES = ["tip", "quiz", "before_after"]


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

# ─── Upload target (YouTube only) ─────────────────────────────
UPLOAD_TARGETS = "youtube"


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
#  PLUGIN SYSTEM  (Phase 4.5)
# ══════════════════════════════════════════════════════════════
# Comma-separated dotted module paths for custom plugins
# Example: PLUGINS=mypackage.social,mypackage.analytics
PLUGINS = os.environ.get("PLUGINS", "")


# ══════════════════════════════════════════════════════════════
#  TELEGRAM NOTIFICATIONS
# ══════════════════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


# ══════════════════════════════════════════════════════════════
#  TRENDING TOPICS  (Phase 6.1)
# ══════════════════════════════════════════════════════════════
# Set to "1" to inject trending topic hints into the LLM prompt.
# Requires optional dep: pytrends  (pip install pytrends)
# YOUTUBE_API_KEY is used for YouTube Trending (same key as upload or a
# separate browser-API key with no OAuth required).
ENABLE_TRENDING = os.environ.get("ENABLE_TRENDING", "0")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")


# ══════════════════════════════════════════════════════════════
#  YOUTUBE ANALYTICS  (Phase 6.2)
# ══════════════════════════════════════════════════════════════
# Set to "1" to enable analytics feedback loop.
# YOUTUBE_CHANNEL_ID is required for AVD + CTR via Analytics API v2.
# (Re-auth with yt-analytics.readonly scope via scripts/auth_youtube.py if
#  those metrics are needed; views/likes work with existing upload scope.)
ENABLE_YT_ANALYTICS = os.environ.get("ENABLE_YT_ANALYTICS", "0")
YOUTUBE_CHANNEL_ID  = os.environ.get("YOUTUBE_CHANNEL_ID", "")


# ══════════════════════════════════════════════════════════════
#  MULTI-LANGUAGE CONTENT  (Phase 6.3)
# ══════════════════════════════════════════════════════════════
# Set CONTENT_LANGUAGE="id" to switch narration + TTS to Bahasa Indonesia.
# Supported values: "en" (default) | "id"
CONTENT_LANGUAGE = os.environ.get("CONTENT_LANGUAGE", "en")

# Indonesian TTS voice used automatically when CONTENT_LANGUAGE="id".
# Override via TTS_VOICE_ID env var if a different ID voice is preferred.
TTS_VOICE_ID = os.environ.get("TTS_VOICE_ID", "id-ID-GadisNeural")


# ══════════════════════════════════════════════════════════════
#  PROMPT A/B TESTING  (Phase 6.5)
# ══════════════════════════════════════════════════════════════
# "A" = default prompt | "B" = alternative prompt | "auto" = day-based rotation
PROMPT_VARIANT = os.environ.get("PROMPT_VARIANT", "A")


# ══════════════════════════════════════════════════════════════
#  VOICE & TONE VARIETY  (Phase 6.7)
# ══════════════════════════════════════════════════════════════
# Values: "energetic" | "calm" | "curious" | "dramatic" | "auto"
# "auto" rotates daily across all 4 tones.
NARRATOR_TONE = os.environ.get("NARRATOR_TONE", "energetic")


# ══════════════════════════════════════════════════════════════
#  BRANDING
# ══════════════════════════════════════════════════════════════
CHANNEL_NAME = os.environ.get("CHANNEL_NAME", "@DevInSeconds")
CHANNEL_URL = os.environ.get(
    "CHANNEL_URL", "https://www.youtube.com/@DevInSeconds"
)


# ══════════════════════════════════════════════════════════════
#  GROWTH ENGINE  (Phase 7)
# ══════════════════════════════════════════════════════════════
# 7.1 — SEO-optimized YouTube descriptions
ENABLE_SEO_DESCRIPTION = os.environ.get("ENABLE_SEO_DESCRIPTION", "1")

# 7.2 — Auto-post a pinned CTA comment after upload
ENABLE_AUTO_COMMENT = os.environ.get("ENABLE_AUTO_COMMENT", "0")

# 7.3 — Auto-manage playlists per language / series
ENABLE_PLAYLISTS = os.environ.get("ENABLE_PLAYLISTS", "0")

# 7.4 — Append end-screen CTA to video description
ENABLE_END_SCREEN = os.environ.get("ENABLE_END_SCREEN", "0")

# 7.5 — Use analytics-based upload time optimization
ENABLE_SMART_SCHEDULE = os.environ.get("ENABLE_SMART_SCHEDULE", "0")


# ══════════════════════════════════════════════════════════════
#  PRODUCTION RELIABILITY  (Phase 8)
# ══════════════════════════════════════════════════════════════

# 8.1 — Gemini fallback model when primary is unavailable
GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-1.5-flash")

# 8.2 — Archive old records after N days
ARCHIVE_DAYS = int(os.environ.get("ARCHIVE_DAYS", "90"))
# MongoDB storage alert threshold in MB (80% of free tier 512MB)
MONGO_STORAGE_ALERT_MB = int(os.environ.get("MONGO_STORAGE_ALERT_MB", "400"))

# 8.4 — Graceful pipeline timeouts (seconds)
STEP_TIMEOUT_S = int(os.environ.get("STEP_TIMEOUT_S", "120"))
RENDER_TIMEOUT_S = int(os.environ.get("RENDER_TIMEOUT_S", "300"))

# 8.5 — Environment: "production" or "staging"
ENVIRONMENT = os.environ.get("ENVIRONMENT", "production")


# ══════════════════════════════════════════════════════════════
#  ADVANCED FEATURES  (Phase 9)
# ══════════════════════════════════════════════════════════════

# 9.1 — Background music (opt-in)
ENABLE_BGMUSIC = os.environ.get("ENABLE_BGMUSIC", "0")
BGMUSIC_VOLUME = float(os.environ.get("BGMUSIC_VOLUME", "0.07"))
MUSIC_DIR = ASSETS_DIR / "music"

# 9.2 — Animated code highlighting
ENABLE_LINE_HIGHLIGHT = os.environ.get("ENABLE_LINE_HIGHLIGHT", "1")
LINE_HIGHLIGHT_ACTIVE = os.environ.get("LINE_HIGHLIGHT_ACTIVE", "#1f2937")

# 9.3 — Multi-channel YouTube support
# JSON list of channel configs: [{"name":"en","client_id":"...","client_secret":"...","refresh_token":"..."}]
YOUTUBE_CHANNELS = os.environ.get("YOUTUBE_CHANNELS", "")

# 9.4 — Dashboard
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", "5050"))
DASHBOARD_SECRET_KEY = os.environ.get("DASHBOARD_SECRET_KEY", "dev-secret-change-me")

# 9.5 — AI-generated thumbnail v2
# "pillow" = Phase 4.6 generator | "ai" = AI background + Pillow overlay
THUMBNAIL_STYLE = os.environ.get("THUMBNAIL_STYLE", "pillow")
STABILITY_API_KEY = os.environ.get("STABILITY_API_KEY", "")


# ══════════════════════════════════════════════════════════════
#  VISUAL PREVIEW  (Phase 10.1)
# ══════════════════════════════════════════════════════════════
# Set to "1" to generate a real visual preview in the top panel.
# HTML/CSS/JS → Playwright browser screenshot; Python/Bash → terminal panel.
ENABLE_VISUAL_PREVIEW = os.environ.get("ENABLE_VISUAL_PREVIEW", "1") == "1"

# Playwright headless browser settings
PLAYWRIGHT_TIMEOUT_MS = int(os.environ.get("PLAYWRIGHT_TIMEOUT_MS", "5000"))
PLAYWRIGHT_VIEWPORT = (1000, 560)  # (width, height) for browser capture

# CTA overlay — "Comment 'X' for code" pill in last seconds before outro
ENABLE_CTA_OVERLAY = os.environ.get("ENABLE_CTA_OVERLAY", "1") == "1"
CTA_LEAD_TIME = float(os.environ.get("CTA_LEAD_TIME", "4.0"))  # seconds before outro
CTA_Y = 1560  # y-position of CTA pill


# ══════════════════════════════════════════════════════════════
#  CONTENT MODE  (Phase 11)
# ══════════════════════════════════════════════════════════════
# "coding_tips" = mode asli (tip/quiz/before_after)
# "visual_ui"   = mode baru (visual UI/animation showcase)
CONTENT_MODE = os.environ.get("CONTENT_MODE", "visual_ui")

# Tipe konten visual UI
VISUAL_UI_TYPES = [
    "landing_page", "login_page", "portfolio",
    "animation", "creative_ui",
]

# Kategori visual UI untuk rotasi
VISUAL_UI_CATEGORIES = [
    "Glassmorphism Login Form",
    "Neon Glow Button Hover",
    "Particle Cursor Animation",
    "Parallax Hero Section",
    "Animated Gradient Background",
    "Card Flip 3D Effect",
    "Typewriter Text Animation",
    "Dark Mode Toggle",
    "Floating Navigation Menu",
    "Loading Spinner Animation",
    "Neumorphism Calculator",
    "Water Ripple Hover Effect",
    "Portfolio Grid Layout",
    "Scroll-Triggered Animation",
    "Creative 404 Page",
]

# Self-improving prompt (Phase 11.4)
ENABLE_SELF_IMPROVING_PROMPT = os.environ.get("ENABLE_SELF_IMPROVING_PROMPT", "0")
PERFORMANCE_EXAMPLE_COUNT = int(os.environ.get("PERFORMANCE_EXAMPLE_COUNT", "3"))

# Resolution upgrade (Phase 11.5)
VIDEO_RESOLUTION = os.environ.get("VIDEO_RESOLUTION", "1080p")
_RESOLUTION_SCALE = 2.0 if VIDEO_RESOLUTION == "4k" else 1.0
