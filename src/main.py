"""
Main orchestrator — runs the complete pipeline:
  1. Generate content (Gemini Pro)
  2. Generate voiceover (edge-tts)
  3. Render video (Pillow + Pygments + moviepy)
  4. Upload to YouTube Shorts
  5. Save record to MongoDB Atlas

Usage:
    python -m src.main
"""
import sys
import logging
import re
from datetime import datetime, timezone
from pathlib import Path


# ── Credential-safe logging filter ────────────────────────────
class CredentialFilter(logging.Filter):
    """Redact any accidental credential leaks in log output."""
    PATTERNS = [
        # (regex, replacement) — each tailored to its capture groups
        (re.compile(r"(mongodb\+srv://[^:]+:)[^@]+(@)", re.I),
         r"\1***REDACTED***\2"),
        (re.compile(r"AIza[A-Za-z0-9_-]{35}", re.I),
         "***REDACTED_API_KEY***"),
        (re.compile(r"ya29\.[A-Za-z0-9_-]+", re.I),
         "***REDACTED_TOKEN***"),
        (re.compile(r"1//[A-Za-z0-9_-]{20,}", re.I),
         "***REDACTED_REFRESH***"),
    ]

    def filter(self, record):
        # Materialize the message once (handles both %-style and str args)
        try:
            msg = record.getMessage()
        except Exception:
            return True
        for pat, repl in self.PATTERNS:
            msg = pat.sub(repl, msg)
        record.msg = msg
        record.args = None  # None is safer than () — prevents TypeError on %s
        return True


# ── Configure logging ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-18s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
# Apply credential filter to root logger
logging.getLogger().addFilter(CredentialFilter())
logger = logging.getLogger("pipeline")


# ── Content safety filter ──────────────────────────────────────
_BLOCKED_KEYWORDS = frozenset([
    # Violence / harm
    "kill", "murder", "suicide", "bomb", "exploit", "weapon",
    # Hate speech
    "racist", "sexist", "slur", "hate speech",
    # Adult / explicit
    "porn", "nsfw", "xxx", "nude",
    # Illegal activity
    "hack someone", "ddos", "ransomware", "phishing",
    "steal password", "keylogger",
])


def _is_content_safe(content: dict) -> tuple[bool, str]:
    """
    Lightweight keyword filter on generated content.
    Returns (True, '') if safe, or (False, reason) if blocked.
    """
    text = " ".join([
        content.get("title", ""),
        content.get("script", ""),
        content.get("code", ""),
        content.get("code_before", ""),
        content.get("expected_output", ""),
    ]).lower()
    for kw in _BLOCKED_KEYWORDS:
        if kw in text:
            return False, f"Blocked keyword found: '{kw}'"
    return True, ""


def main():
    from src import config
    from src.llm import generate_content
    from src.tts import generate_speech
    from src.video import create_video
    from src.uploader_youtube import upload_to_youtube
    from src.db import save_record
    from src.code_runner import get_output_for_content
    from src.notifier import send_notification

    logger.info("=" * 55)
    logger.info("  Automated Coding Shorts Pipeline — Starting")
    logger.info("=" * 55)

    # ── Validate required environment variables ───────────────
    errors = []
    if not config.GEMINI_API_KEY:
        errors.append("GEMINI_API_KEY")
    if not config.MONGODB_URI:
        errors.append("MONGODB_URI")
    if errors:
        logger.error(f"Missing required secrets: {', '.join(errors)}")
        sys.exit(1)

    # Tracking record for MongoDB
    record: dict = {
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
    }

    try:
        # ╔════════════════════════════════════════════════════╗
        # ║  STEP 1 — Generate Content (Gemini Pro)           ║
        # ╚════════════════════════════════════════════════════╝
        logger.info("STEP 1/5 │ Generating content with Gemini Pro...")
        content = generate_content()

        record.update({
            "topic": content["title"],
            "title": content["title"],
            "script": content["script"],
            "code": content["code"],
            "language": content["language"],
            "hashtags": content.get("hashtags", []),
            "content_type": content.get("content_type", "tip"),
        })

        logger.info(f"  ✓ Title:    {content['title']}")
        logger.info(f"  ✓ Type:     {content.get('content_type', 'tip')}")
        logger.info(f"  ✓ Language: {content['language']}")
        logger.info(f"  ✓ Code:     {len(content['code'])} chars, {content['code'].count(chr(10))+1} lines")
        logger.info(f"  ✓ Script:   {len(content['script'].split())} words")

        # ── Content safety gate ───────────────────────────────
        safe, reason = _is_content_safe(content)
        if not safe:
            raise RuntimeError(f"Content blocked by safety filter: {reason}")

        # ╔════════════════════════════════════════════════════╗
        # ║  STEP 1b — Run Code (for output_demo/quiz)        ║
        # ╚════════════════════════════════════════════════════╝
        code_output = get_output_for_content(content)
        if code_output:
            logger.info(f"  ✓ Output:   {len(code_output)} chars")
            record["code_output"] = code_output[:500]

        # ╔════════════════════════════════════════════════════╗
        # ║  STEP 2 — Generate Voiceover (edge-tts)           ║
        # ╚════════════════════════════════════════════════════╝
        logger.info("STEP 2/5 │ Generating voiceover with edge-tts...")
        audio_path, word_timestamps = generate_speech(
            text=content["script"],
            voice=config.TTS_VOICE,
        )

        logger.info(f"  ✓ Audio:      {audio_path}")
        logger.info(f"  ✓ Timestamps: {len(word_timestamps)} words")

        # ╔════════════════════════════════════════════════════╗
        # ║  STEP 3 — Render Video (Pillow + moviepy)         ║
        # ╚════════════════════════════════════════════════════╝
        logger.info("STEP 3/5 │ Rendering video...")
        video_path = create_video(
            code=content["code"],
            language=content["language"],
            word_timestamps=word_timestamps,
            audio_path=audio_path,
            channel_name=config.CHANNEL_NAME,
            content_type=content.get("content_type", "tip"),
            code_output=code_output,
            code_before=content.get("code_before"),
            title=content["title"],
        )

        # Get video duration for record
        from src.tts import get_audio_duration
        try:
            record["duration_seconds"] = round(get_audio_duration(audio_path), 1)
        except Exception:
            record["duration_seconds"] = 0

        logger.info(f"  ✓ Video: {video_path}")

        # ╔════════════════════════════════════════════════════╗
        # ║  STEP 4 — Upload to YouTube Shorts                ║
        # ╚════════════════════════════════════════════════════╝
        logger.info("STEP 4/5 │ Uploading to YouTube Shorts...")

        # Build description: narration + newlines + hashtags
        description_parts = [
            content["script"],
            "",
            " ".join(content.get("hashtags", [])),
            "",
            f"Generated by {config.CHANNEL_NAME} pipeline",
        ]
        description = "\n".join(description_parts)

        youtube_id = upload_to_youtube(
            video_path=video_path,
            title=content["title"],
            description=description,
            tags=content.get("hashtags", []),
        )

        record["youtube_id"] = youtube_id
        if youtube_id:
            logger.info(f"  ✓ YouTube: https://youtube.com/shorts/{youtube_id}")
        else:
            logger.info("  ⚠ YouTube upload skipped (no credentials)")

        # ╔════════════════════════════════════════════════════╗
        # ║  STEP 5 — Save Record to MongoDB                  ║
        # ╚════════════════════════════════════════════════════╝
        logger.info("STEP 5/5 │ Saving record to MongoDB Atlas...")
        record["status"] = "success"
        record["published_at"] = datetime.now(timezone.utc)
        doc_id = save_record(record)

        logger.info(f"  ✓ MongoDB: {doc_id}")

        # ── Done! ─────────────────────────────────────────────
        logger.info("=" * 55)
        logger.info("  ✅  Pipeline completed successfully!")
        logger.info("=" * 55)

        # ── Telegram notification ─────────────────────────────
        send_notification(
            status="success",
            title=content["title"],
            youtube_id=youtube_id,
            language=content["language"],
            content_type=content.get("content_type", "tip"),
            duration=record.get("duration_seconds", 0),
        )

    except Exception as e:
        # ── Handle failure ────────────────────────────────────
        logger.error(f"Pipeline FAILED: {e}", exc_info=True)

        record["status"] = "failed"
        record["error_message"] = str(e)[:500]

        try:
            save_record(record)
            logger.info("Failure record saved to MongoDB")
        except Exception as db_err:
            logger.error(f"Could not save failure record: {db_err}")

        # ── Telegram failure notification ─────────────────────
        try:
            send_notification(
                status="failed",
                title=record.get("title", ""),
                error_message=str(e)[:300],
            )
        except Exception:
            pass

        sys.exit(1)

    finally:
        # ── Cleanup temporary files ───────────────────────────
        _cleanup_output_dir()


def _cleanup_output_dir():
    """Remove temporary files from the output directory."""
    from src import config
    try:
        for f in config.OUTPUT_DIR.iterdir():
            if f.is_file():
                f.unlink()
                logger.debug(f"Cleaned up: {f.name}")
    except Exception as e:
        logger.warning(f"Cleanup failed (non-critical): {e}")


if __name__ == "__main__":
    main()
