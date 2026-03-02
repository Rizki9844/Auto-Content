"""
Telegram notification module.
Sends pipeline status notifications via Telegram Bot API.
Supports success (with YouTube link) and failure (with error message) alerts.

Setup:
  1. Create a bot via @BotFather on Telegram → get BOT_TOKEN
  2. Start a chat with the bot, or add it to a group → get CHAT_ID
     (kirim /start ke bot, lalu buka: https://api.telegram.org/bot<TOKEN>/getUpdates)
  3. Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID as GitHub Secrets /
     environment variables.

Troubleshoot:
  - Jalankan: python -m src.notifier  (untuk test kirim notif langsung)
  - Pastikan bot sudah di-/start dari chat yang sama dengan CHAT_ID
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
    error_class: str = "",
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
        error_class: Error classification (TRANSIENT/PERMANENT/CONTENT) — Phase 3.7

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
            message = _format_failure(title, error_message, error_class)

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
    """Format a success notification message using HTML."""
    type_emoji = {
        "tip": "💡",
        "output_demo": "▶️",
        "quiz": "🧠",
        "before_after": "✨",
    }
    emoji = type_emoji.get(content_type, "📹")

    lines = [
        "✅ <b>Pipeline Berhasil!</b>",
        "",
        f"{emoji} <b>{_escape_html(title)}</b>",
        "",
        f"📝 Tipe: <code>{_escape_html(content_type)}</code>",
        f"💻 Bahasa: <code>{_escape_html(language)}</code>",
        f"⏱ Durasi: <code>{duration:.1f}s</code>",
    ]

    if youtube_id:
        lines.append("")
        lines.append(
            f'🎬 <a href="https://youtube.com/shorts/{youtube_id}">Tonton di YouTube</a>'
        )

    lines.append("")
    lines.append(f"<i>{_escape_html(config.CHANNEL_NAME)}</i>")

    return "\n".join(lines)


def _format_failure(title: str, error_message: str, error_class: str = "") -> str:
    """Format a failure notification message using HTML (with error class — Phase 3.7)."""
    _class_emoji = {
        "TRANSIENT": "🔄",
        "PERMANENT": "🛑",
        "CONTENT": "📝",
    }
    class_label = ""
    if error_class:
        emoji = _class_emoji.get(error_class, "⚠️")
        class_label = f"\n{emoji} Kelas: <code>{error_class}</code>"

        # Add actionable advice based on error class
        advice = {
            "TRANSIENT": "Retry otomatis akan dilakukan di run berikutnya.",
            "PERMANENT": "Cek credentials dan quota — butuh intervensi manual.",
            "CONTENT": "Content akan di-regenerate otomatis.",
        }
        class_label += f"\n💡 {advice.get(error_class, '')}"

    lines = [
        "❌ <b>Pipeline Gagal!</b>",
        "",
        f"📝 Topik: {_escape_html(title or '(unknown)')}",
        class_label,
        "",
        "⚠️ Error:",
        f"<code>{_escape_html(error_message[:300])}</code>",
        "",
        "Cek log di GitHub Actions untuk detail.",
    ]
    return "\n".join(lines)


def _escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse_mode."""
    return (
        text
        .replace("&", "&amp;")   # must be first!
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _send_message(text: str) -> bool:
    """Send a message via Telegram Bot API (stdlib only, no extra deps)."""
    url = TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN)

    payload = json.dumps({
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": False},
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            if resp.status == 200:
                logger.info("Telegram notification sent successfully")
                return True
            else:
                logger.warning(f"Telegram API returned {resp.status}: {body}")
                return False
    except urllib.error.HTTPError as e:
        # Telegram returns 4xx errors as HTTPError — read the body for diagnosis
        try:
            body = e.read().decode("utf-8")
        except Exception:
            body = str(e)
        logger.warning(f"Telegram API error {e.code}: {body}")
        return False
    except Exception as e:
        logger.warning(f"Telegram send failed: {e}")
        return False


# ── Quick CLI test ────────────────────────────────────────────
# Usage: python -m src.notifier
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s │ %(message)s")

    if not config.TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    if not config.TELEGRAM_CHAT_ID:
        print("ERROR: TELEGRAM_CHAT_ID not set", file=sys.stderr)
        sys.exit(1)

    ok = send_notification(
        status="success",
        title="Python List Trick #Shorts",
        youtube_id="dQw4w9WgXcQ",
        language="python",
        content_type="tip",
        duration=42.5,
    )
    sys.exit(0 if ok else 1)
