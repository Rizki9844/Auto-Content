"""
Telegram notification module.
Sends pipeline status notifications via Telegram Bot API.
Supports success (with YouTube link) and failure (with error message) alerts.

Setup:
  1. Create a bot via @BotFather on Telegram → get BOT_TOKEN
  2. Start a chat with the bot, or add it to a group
  3. Get your CHAT_ID via https://api.telegram.org/bot<TOKEN>/getUpdates
  4. Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID as GitHub Secrets
"""
import logging
import urllib.request
import urllib.parse
import json

from src import config

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_notification(
    status: str,
    title: str = "",
    youtube_id: str | None = None,
    error_message: str = "",
    language: str = "",
    content_type: str = "tip",
    duration: float = 0,
) -> bool:
    """
    Send a Telegram notification about pipeline result.

    Args:
        status: "success" or "failed"
        title: Video title
        youtube_id: YouTube video ID (on success)
        error_message: Error description (on failure)
        language: Programming language used
        content_type: Content type (tip, quiz, etc.)
        duration: Video duration in seconds

    Returns:
        True if sent successfully, False otherwise.
    """
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.info("Telegram not configured — skipping notification")
        return False

    try:
        if status == "success":
            message = _format_success(title, youtube_id, language, content_type, duration)
        else:
            message = _format_failure(title, error_message)

        return _send_message(message)

    except Exception as e:
        logger.warning(f"Telegram notification failed (non-critical): {e}")
        return False


def _format_success(
    title: str,
    youtube_id: str | None,
    language: str,
    content_type: str,
    duration: float,
) -> str:
    """Format a success notification message."""
    type_emoji = {
        "tip": "💡",
        "output_demo": "▶️",
        "quiz": "🧠",
        "before_after": "✨",
    }
    emoji = type_emoji.get(content_type, "📹")

    lines = [
        f"✅ *Pipeline Berhasil!*",
        f"",
        f"{emoji} *{_escape_md(title)}*",
        f"",
        f"📝 Tipe: `{content_type}`",
        f"💻 Bahasa: `{language}`",
        f"⏱ Durasi: `{duration:.1f}s`",
    ]

    if youtube_id:
        lines.append(f"")
        lines.append(f"🎬 [Tonton di YouTube](https://youtube.com/shorts/{youtube_id})")

    lines.append(f"")
    lines.append(f"_{config.CHANNEL_NAME}_")

    return "\n".join(lines)


def _format_failure(title: str, error_message: str) -> str:
    """Format a failure notification message."""
    lines = [
        f"❌ *Pipeline Gagal!*",
        f"",
        f"📝 Topik: {_escape_md(title or '(unknown)')}",
        f"",
        f"⚠️ Error:",
        f"`{_escape_md(error_message[:300])}`",
        f"",
        f"Cek log di GitHub Actions untuk detail.",
    ]
    return "\n".join(lines)


def _escape_md(text: str) -> str:
    """Escape special Markdown characters for Telegram."""
    for char in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        text = text.replace(char, f'\\{char}')
    return text


def _send_message(text: str) -> bool:
    """Send a message via Telegram Bot API (stdlib only, no extra deps)."""
    url = TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN)

    payload = json.dumps({
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                logger.info("Telegram notification sent successfully")
                return True
            else:
                logger.warning(f"Telegram API returned status {resp.status}")
                return False
    except Exception as e:
        logger.warning(f"Telegram send failed: {e}")
        return False
