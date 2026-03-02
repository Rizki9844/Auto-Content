"""
Main orchestrator — runs the complete pipeline:
  1. Generate content (Gemini Pro)
  2. Generate voiceover (edge-tts)
  3. Render video (Pillow + Pygments + moviepy)
  4. Upload to configured platforms
  5. Save record to MongoDB Atlas

Usage:
    python -m src.main                # normal run (generate + upload immediately)
    python -m src.main --batch 3      # generate 3 videos, schedule for peak times
    python -m src.main --upload-queue # upload due jobs from the schedule queue
    python -m src.main --analytics    # print analytics report to stdout
    python -m src.main --analytics --save  # also write report to output/
    python -m src.main --health       # health-check (exit 0 = OK)

    Environment variables for Phase 4.4/4.6:
    ACTIVE_THEME=monokai              # use a different color theme
    AUTO_ROTATE_THEMES=1              # rotate themes daily
    ENABLE_THUMBNAILS=1               # generate + upload YouTube thumbnails
"""
import json as _json
import os
import sys
import logging
import re
import time
from datetime import datetime, timezone


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
class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line (structured logging)."""
    def format(self, record):
        # Let CredentialFilter run first (it patches record.msg)
        return _json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }, ensure_ascii=False)


_log_format = os.environ.get("LOG_FORMAT", "").strip().lower()
if _log_format == "json":
    _handler = logging.StreamHandler()
    _handler.setFormatter(_JsonFormatter())
    logging.root.addHandler(_handler)
    logging.root.setLevel(logging.INFO)
else:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s │ %(name)-18s │ %(levelname)-7s │ %(message)s",
        datefmt="%H:%M:%S",
    )
# Apply credential filter to root logger
logging.getLogger().addFilter(CredentialFilter())
logger = logging.getLogger("pipeline")


# ── Content safety filter ──────────────────────────────────────
# NOTE: single generic words (kill, bomb, exploit, weapon) are intentionally
# excluded — they are common programming terms:
#   kill -9, time-bomb pattern, exploit a bug, weapon class in game dev, etc.
# Only use multi-word phrases or words that NEVER appear in legit coding content.
_BLOCKED_KEYWORDS = frozenset([
    # Violence / harm (specific phrases only)
    "murder", "how to hurt", "self harm", "suicide method",
    # Hate speech
    "racist", "sexist", "slur", "hate speech",
    # Adult / explicit
    "porn", "nsfw", "xxx", "nude",
    # Illegal activity
    "hack someone", "ddos", "ransomware", "phishing",
    "steal password", "keylogger", "make a bomb", "build a bomb",
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
    from src.video import create_video, verify_video
    from src.uploader_base import get_uploaders
    from src.db import (
        save_record, save_pending_upload,
        check_code_similarity, get_language_frequency,
    )
    from src.code_runner import get_output_for_content
    from src.notifier import send_notification
    from src.quality import score_content, QUALITY_THRESHOLD
    from src.rate_limiter import RateLimiter
    from src.errors import (
        classify_error, PipelineError, ContentError,
    )

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

    # Initialize rate limiter (Phase 3.6)
    rate_limiter = RateLimiter()

    # Resolve upload targets (Phase 4.1)
    uploaders = get_uploaders()
    logger.info(f"Upload targets: {[u.name for u in uploaders] or ['none']}")

    # Tracking record for MongoDB
    record: dict = {
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
    }
    metrics: dict = {}
    _t_pipeline = time.perf_counter()

    try:
        # ╔════════════════════════════════════════════════════╗
        # ║  STEP 0 — Retry Pending Uploads (Phase 3.4)      ║
        # ╚════════════════════════════════════════════════════╝
        _retry_pending_uploads(
            uploaders=uploaders,
            rate_limiter=rate_limiter,
        )

        # ╔════════════════════════════════════════════════════╗
        # ║  STEP 1 — Generate Content (Gemini Pro)           ║
        # ╚════════════════════════════════════════════════════╝
        logger.info("STEP 1/6 │ Generating content with Gemini Pro...")

        # Rate limit check (Phase 3.6)
        delay = rate_limiter.pre_gemini_call()
        if delay > 0:
            logger.info(f"  ⏳ Rate limit delay: {delay:.1f}s")
            time.sleep(delay)

        # Language frequency data for deduplication (Phase 3.3)
        lang_freq = get_language_frequency()

        _t0 = time.perf_counter()
        content = generate_content(
            avoid_languages=lang_freq.get("suggested_avoid", []),
        )
        metrics["gemini_latency_ms"] = round((time.perf_counter() - _t0) * 1000)
        rate_limiter.record_gemini_call()

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
            raise ContentError(
                f"Content blocked by safety filter: {reason}",
                step="content_safety",
            )

        # ── Content quality scoring (Phase 3.1) ──────────────
        quality = score_content(
            content,
            recent_types=lang_freq.get("recent_types", []),
        )
        metrics["quality_score"] = quality["total_score"]
        record["quality_score"] = quality["total_score"]

        if not quality["passed"]:
            logger.warning(
                f"Quality score {quality['total_score']}/{100} below threshold "
                f"({QUALITY_THRESHOLD}). Reasons: {quality['reasons']}"
            )
            # Try regeneration (max 2 extra attempts)
            for regen_attempt in range(1, 3):
                logger.info(f"Regenerating content (attempt {regen_attempt}/2)...")
                delay = rate_limiter.pre_gemini_call()
                if delay > 0:
                    time.sleep(delay)
                content = generate_content(
                    avoid_languages=lang_freq.get("suggested_avoid", []),
                )
                rate_limiter.record_gemini_call()

                safe, reason = _is_content_safe(content)
                if not safe:
                    continue

                quality = score_content(
                    content,
                    recent_types=lang_freq.get("recent_types", []),
                )
                metrics["quality_score"] = quality["total_score"]
                record["quality_score"] = quality["total_score"]
                if quality["passed"]:
                    logger.info(f"Regenerated content passed quality check (attempt {regen_attempt})")
                    break
            else:
                logger.warning("Using best content after quality regeneration attempts")

            # Update record with new content
            record.update({
                "topic": content["title"],
                "title": content["title"],
                "script": content["script"],
                "code": content["code"],
                "language": content["language"],
                "hashtags": content.get("hashtags", []),
                "content_type": content.get("content_type", "tip"),
            })

        # ── Code similarity check (Phase 3.3) ────────────────
        sim_result = check_code_similarity(content["code"])
        if sim_result["is_duplicate"]:
            logger.warning(
                f"Code too similar ({sim_result['max_similarity']:.0%}) to "
                f"'{sim_result['similar_to']}' — proceeding with warning"
            )
            metrics["code_similarity"] = sim_result["max_similarity"]

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
        logger.info("STEP 2/6 │ Generating voiceover with edge-tts...")
        _t0 = time.perf_counter()
        audio_path, word_timestamps = generate_speech(
            text=content["script"],
            voice=config.TTS_VOICE,
        )
        metrics["tts_latency_ms"] = round((time.perf_counter() - _t0) * 1000)

        logger.info(f"  ✓ Audio:      {audio_path}")
        logger.info(f"  ✓ Timestamps: {len(word_timestamps)} words")

        # ╔════════════════════════════════════════════════════╗
        # ║  STEP 3 — Render Video (Pillow + moviepy)         ║
        # ╚════════════════════════════════════════════════════╝
        logger.info("STEP 3/6 │ Rendering video...")
        _t0 = time.perf_counter()
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
        metrics["render_latency_ms"] = round((time.perf_counter() - _t0) * 1000)

        # Get video duration for record
        from src.tts import get_audio_duration
        try:
            record["duration_seconds"] = round(get_audio_duration(audio_path), 1)
        except Exception:
            record["duration_seconds"] = 0

        logger.info(f"  ✓ Video: {video_path}")

        # ╔════════════════════════════════════════════════════╗
        # ║  STEP 3b — Video Quality Verification (3.2)       ║
        # ╚════════════════════════════════════════════════════╝
        vq = verify_video(video_path)
        metrics["video_verification"] = vq["checks"]
        if not vq["passed"]:
            logger.error(f"Video quality check FAILED: {vq['errors']}")
            raise ContentError(
                f"Video verification failed: {'; '.join(vq['errors'])}",
                step="video_verify",
            )

        # ╔════════════════════════════════════════════════════╗
        # ║  STEP 4 — Upload to Platforms (Phase 4.1)         ║
        # ╚════════════════════════════════════════════════════╝
        logger.info(f"STEP 4/6 │ Uploading to {len(uploaders)} platform(s)...")

        # Build description once for all platforms
        description_parts = [
            content["script"],
            "",
            " ".join(content.get("hashtags", [])),
            "",
            f"Generated by {config.CHANNEL_NAME} pipeline",
        ]
        description = "\n".join(description_parts)

        upload_results: dict[str, str | None] = {}
        _t0 = time.perf_counter()

        if not uploaders:
            logger.warning("No uploaders configured — saving for later")
            save_pending_upload(video_path, record.copy())
        else:
            for uploader in uploaders:
                # YouTube-specific quota check
                if uploader.name == "youtube":
                    quota_status = rate_limiter.check_youtube_quota()
                    if not quota_status["can_upload"]:
                        logger.warning(
                            f"YouTube quota insufficient ({quota_status['remaining']} remaining). "
                            "Saving video for later upload."
                        )
                        save_pending_upload(video_path, record.copy())
                        upload_results["youtube"] = None
                        continue

                logger.info(f"  ↗ Uploading to {uploader.name}...")
                result = uploader.upload(
                    video_path=video_path,
                    title=content["title"],
                    description=description,
                    tags=content.get("hashtags", []),
                )

                if result.success:
                    upload_results[result.platform] = result.video_id
                    logger.info(f"  ✓ {result.platform}: {result.url}")
                    if result.platform == "youtube":
                        rate_limiter.record_youtube_upload()
                        # Thumbnail (Phase 4.6)
                        _thumbnail_step(
                            youtube_id=result.video_id or "",
                            title=content["title"],
                            language=content["language"],
                            code=content["code"],
                        )
                else:
                    upload_results[result.platform] = None
                    classified = classify_error(
                        RuntimeError(result.error), step=f"upload_{result.platform}"
                    )
                    logger.warning(
                        f"  ✗ {result.platform} failed ({classified.error_class}): "
                        f"{result.error[:200]}"
                    )
                    # Graceful degradation — save for retry (Phase 3.4)
                    if result.platform == "youtube":
                        save_pending_upload(video_path, record.copy())

        metrics["upload_latency_ms"] = round((time.perf_counter() - _t0) * 1000)

        # Backwards-compatible: keep youtube_id in record
        youtube_id = upload_results.get("youtube")
        record["youtube_id"] = youtube_id
        record["upload_results"] = upload_results

        any_success = any(v for v in upload_results.values())
        if any_success:
            platform_summary = ", ".join(
                f"{p}={vid}" for p, vid in upload_results.items() if vid
            )
            logger.info(f"  ✓ Uploaded: {platform_summary}")
        else:
            logger.info("  ⚠ All uploads skipped or deferred")

        # ╔════════════════════════════════════════════════════╗
        # ║  STEP 5 — Save Record to MongoDB                  ║
        # ╚════════════════════════════════════════════════════╝
        logger.info("STEP 5/6 │ Saving record to MongoDB Atlas...")
        record["status"] = "success" if any_success else "rendered_not_uploaded"
        record["published_at"] = datetime.now(timezone.utc)
        metrics["total_latency_ms"] = round((time.perf_counter() - _t_pipeline) * 1000)
        record["metrics"] = metrics
        doc_id = save_record(record)

        logger.info(f"  ✓ MongoDB: {doc_id}")

        # ── Done! ─────────────────────────────────────────────
        logger.info("=" * 55)
        logger.info("  ✅  Pipeline completed successfully!")
        logger.info(f"  ⏱  Gemini: {metrics.get('gemini_latency_ms', 0)}ms │ "
                     f"TTS: {metrics.get('tts_latency_ms', 0)}ms │ "
                     f"Render: {metrics.get('render_latency_ms', 0)}ms │ "
                     f"Upload: {metrics.get('upload_latency_ms', 0)}ms │ "
                     f"Total: {metrics.get('total_latency_ms', 0)}ms")
        logger.info(f"  📊 Quality: {metrics.get('quality_score', '?')}/100")
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
        # ── Classify and handle failure (Phase 3.7) ───────────
        classified = classify_error(e, step="pipeline")
        if isinstance(e, PipelineError):
            classified = e

        logger.error(
            f"Pipeline FAILED [{classified.error_class}]: {e}",
            exc_info=True,
        )

        record["status"] = "failed"
        record["error_message"] = str(e)[:500]
        record["error_class"] = classified.error_class

        try:
            save_record(record)
            logger.info("Failure record saved to MongoDB")
        except Exception as db_err:
            logger.error(f"Could not save failure record: {db_err}")

        # ── Telegram failure notification with error class ────
        try:
            send_notification(
                status="failed",
                title=record.get("title", ""),
                error_message=str(e)[:300],
                error_class=classified.error_class,
            )
        except Exception:
            pass

        sys.exit(1)

    finally:
        # ── Cleanup temporary files ───────────────────────────
        _cleanup_output_dir()


def _retry_pending_uploads(uploaders, rate_limiter):
    """
    Phase 3.4 + 4.1: Retry previously failed uploads using all
    configured uploaders.
    """
    from src.db import (
        get_pending_uploads, mark_upload_complete, increment_retry_count,
    )
    import os

    pending = get_pending_uploads(limit=3)
    if not pending:
        return

    # Find the YouTube uploader for quota-aware retry
    yt_uploader = next((u for u in uploaders if u.name == "youtube"), None)
    if not yt_uploader:
        logger.info("No YouTube uploader configured — skipping pending retries")
        return

    logger.info(f"Found {len(pending)} pending upload(s) to retry...")

    for doc in pending:
        video_path = doc.get("video_path", "")
        if not video_path or not os.path.exists(video_path):
            logger.warning(f"Pending upload video missing: {video_path}")
            increment_retry_count(doc["_id"])
            continue

        quota = rate_limiter.check_youtube_quota()
        if not quota["can_upload"]:
            logger.warning("YouTube quota insufficient for retry — skipping")
            break

        title = doc.get("title", "Untitled #Shorts")
        description = doc.get("script", "")
        tags = doc.get("hashtags", [])

        result = yt_uploader.upload(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
        )

        if result.success:
            mark_upload_complete(doc["_id"], result.video_id)
            rate_limiter.record_youtube_upload()
            logger.info(f"Retry upload succeeded: {result.video_id}")
        else:
            logger.warning(f"Retry upload failed: {result.error}")
            increment_retry_count(doc["_id"])


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


def _thumbnail_step(
    youtube_id: str,
    title: str,
    language: str,
    code: str,
) -> None:
    """
    Phase 4.6: Generate and upload a thumbnail (best-effort, never raises).
    Only runs when config.ENABLE_THUMBNAILS == "1".
    """
    from src import config as _cfg
    if _cfg.ENABLE_THUMBNAILS != "1":
        return
    try:
        from src.thumbnail import generate_thumbnail, upload_thumbnail
        thumb_path = generate_thumbnail(
            title=title,
            language=language,
            code=code,
        )
        ok = upload_thumbnail(youtube_video_id=youtube_id, image_path=thumb_path)
        if ok:
            logger.info(f"Thumbnail uploaded for {youtube_id}")
    except Exception as exc:
        logger.warning(f"Thumbnail step failed (non-critical): {exc}")


# ══════════════════════════════════════════════════════════════
#  BATCH PIPELINE  (python -m src.main --batch N)
# ══════════════════════════════════════════════════════════════
def batch_pipeline(n: int) -> int:
    """
    Phase 4.2: Generate ``n`` videos and add them to the publish queue.

    Each video is assigned the next available peak-time slot.
    Videos are **not** uploaded immediately — ``upload_queue_pipeline``
    handles that at the scheduled time.

    Returns the number of videos successfully queued.
    """
    from src import config
    from src.llm import generate_content
    from src.tts import generate_speech
    from src.video import create_video, verify_video
    from src.db import check_code_similarity, get_language_frequency
    from src.code_runner import get_output_for_content
    from src.quality import score_content
    from src.rate_limiter import RateLimiter
    from src.errors import classify_error
    from src.scheduler import add_to_schedule, next_available_slots

    logger.info("=" * 55)
    logger.info(f"  Batch Pipeline — Generating {n} video(s)")
    logger.info("=" * 55)

    errors = []
    if not config.GEMINI_API_KEY:
        errors.append("GEMINI_API_KEY")
    if not config.MONGODB_URI:
        errors.append("MONGODB_URI")
    if errors:
        logger.error(f"Missing required secrets: {', '.join(errors)}")
        sys.exit(1)

    rate_limiter = RateLimiter()
    lang_freq = get_language_frequency()

    # Reserve N slots upfront so each video gets a distinct time
    slots = next_available_slots(n)
    if len(slots) < n:
        logger.warning(f"Only {len(slots)} slots available (requested {n})")
        n = len(slots)

    queued = 0

    for i in range(n):
        slot = slots[i]
        logger.info(f"  [{i + 1}/{n}] Generating for slot {slot.strftime('%Y-%m-%d %H:%M UTC')}...")

        # Rate limit guard
        delay = rate_limiter.pre_gemini_call()
        if delay > 0:
            time.sleep(delay)

        try:
            content = generate_content(
                avoid_languages=lang_freq.get("suggested_avoid", []),
            )
            rate_limiter.record_gemini_call()

            # Safety gate
            safe, reason = _is_content_safe(content)
            if not safe:
                logger.warning(f"  [{i + 1}] Blocked: {reason} — skipping")
                continue

            # Quality check (one attempt only in batch mode)
            quality = score_content(content, recent_types=lang_freq.get("recent_types", []))
            if not quality["passed"]:
                logger.warning(
                    f"  [{i + 1}] Quality {quality['total_score']}/100 below threshold "
                    f"— proceeding anyway (batch mode)"
                )

            # TTS
            audio_path, word_timestamps = generate_speech(
                text=content["script"],
                voice=config.TTS_VOICE,
            )

            # Code execution (for output_demo / quiz)
            code_output = get_output_for_content(content)

            # Render
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

            # Video verification
            vq = verify_video(video_path)
            if not vq["passed"]:
                logger.warning(
                    f"  [{i + 1}] Video quality check failed: {vq['errors']} — skipping"
                )
                continue

            # Similarity guard
            sim = check_code_similarity(content["code"])
            if sim["is_duplicate"]:
                logger.warning(
                    f"  [{i + 1}] Code too similar to existing ({sim['max_similarity']:.0%}) "
                    f"— skipping"
                )
                continue

            # Add to schedule queue
            add_to_schedule(
                content=content,
                video_path=video_path,
                audio_path=audio_path,
                publish_at=slot,
                quality_score=float(quality["total_score"]),
            )
            queued += 1
            logger.info(f"  [{i + 1}] ✓ Queued for {slot.strftime('%Y-%m-%d %H:%M UTC')}")

        except Exception as exc:
            classified = classify_error(exc, step=f"batch_item_{i + 1}")
            logger.error(
                f"  [{i + 1}] Failed [{classified.error_class}]: {exc}",
                exc_info=True,
            )

    logger.info("=" * 55)
    logger.info(f"  Batch complete: {queued}/{n} video(s) queued")
    logger.info("=" * 55)
    return queued


# ══════════════════════════════════════════════════════════════
#  UPLOAD QUEUE PIPELINE  (python -m src.main --upload-queue)
# ══════════════════════════════════════════════════════════════
def upload_queue_pipeline() -> int:
    """
    Phase 4.2: Upload all due jobs from the ``scheduled`` collection.

    A job is "due" when ``publish_at <= now`` and ``status == pending``.
    Each job is uploaded via all configured uploaders (Phase 4.1).

    Returns the number of jobs successfully uploaded.
    """
    from src import config
    from src.uploader_base import get_uploaders
    from src.db import save_record
    from src.notifier import send_notification
    from src.rate_limiter import RateLimiter
    from src.errors import classify_error
    from src.scheduler import (
        get_due_jobs, mark_job_done, mark_job_failed, get_schedule_summary,
    )

    logger.info("=" * 55)
    logger.info("  Upload Queue Pipeline — Processing due jobs")
    logger.info("=" * 55)

    errors = []
    if not config.GEMINI_API_KEY:
        errors.append("GEMINI_API_KEY")
    if not config.MONGODB_URI:
        errors.append("MONGODB_URI")
    if errors:
        logger.error(f"Missing required secrets: {', '.join(errors)}")
        sys.exit(1)

    rate_limiter = RateLimiter()
    uploaders = get_uploaders()
    due_jobs = get_due_jobs(limit=5)

    if not due_jobs:
        summary = get_schedule_summary()
        logger.info(
            f"No due jobs. Queue: {summary['pending_future']} pending, "
            f"{summary['done_today']} done today."
        )
        return 0

    logger.info(f"Found {len(due_jobs)} due job(s) to process...")
    succeeded = 0

    for job in due_jobs:
        job_id = job["_id"]
        title = job.get("title", "Untitled")
        video_path = job.get("video_path", "")

        if not video_path or not os.path.exists(video_path):
            logger.warning(f"Job {job_id}: video file missing '{video_path}' — marking failed")
            mark_job_failed(job_id, "Video file not found on disk")
            continue

        logger.info(f"  → Uploading '{title}' (job {job_id})...")

        # Quota check for YouTube
        quota_status = rate_limiter.check_youtube_quota()
        if not quota_status["can_upload"]:
            logger.warning("YouTube quota exhausted — stopping queue processing")
            break

        description_parts = [
            job.get("script", ""),
            "",
            " ".join(job.get("hashtags", [])),
            "",
            f"Generated by {config.CHANNEL_NAME} pipeline",
        ]
        description = "\n".join(description_parts)

        upload_results: dict[str, str | None] = {}
        any_success = False

        for uploader in uploaders:
            result = uploader.upload(
                video_path=video_path,
                title=title,
                description=description,
                tags=job.get("hashtags", []),
            )
            upload_results[result.platform] = result.video_id if result.success else None
            if result.success:
                any_success = True
                logger.info(f"    ✓ {result.platform}: {result.url}")
                if result.platform == "youtube":
                    rate_limiter.record_youtube_upload()
                    # Thumbnail (Phase 4.6)
                    _thumbnail_step(
                        youtube_id=result.video_id or "",
                        title=title,
                        language=job.get("language", ""),
                        code=job.get("code", ""),
                    )
            else:
                classified = classify_error(
                    RuntimeError(result.error), step=f"queue_{result.platform}"
                )
                logger.warning(f"    ✗ {result.platform} ({classified.error_class}): {result.error[:150]}")

        if any_success:
            mark_job_done(job_id, upload_results)
            youtube_id = upload_results.get("youtube")

            # Save to history collection
            from src.tts import get_audio_duration
            try:
                duration = round(get_audio_duration(job.get("audio_path", "")), 1)
            except Exception:
                duration = 0

            record = {
                "status": "success",
                "title": title,
                "script": job.get("script", ""),
                "language": job.get("language", ""),
                "hashtags": job.get("hashtags", []),
                "content_type": job.get("content_type", "tip"),
                "youtube_id": youtube_id,
                "upload_results": upload_results,
                "quality_score": job.get("quality_score", 0),
                "duration_seconds": duration,
                "created_at": job.get("created_at", datetime.now(timezone.utc)),
                "published_at": datetime.now(timezone.utc),
                "source": "scheduled_queue",
            }
            try:
                save_record(record)
            except Exception as db_err:
                logger.warning(f"Could not save history record: {db_err}")

            # Telegram notification
            try:
                send_notification(
                    status="success",
                    title=title,
                    youtube_id=youtube_id,
                    language=job.get("language", ""),
                    content_type=job.get("content_type", "tip"),
                    duration=duration,
                )
            except Exception:
                pass

            succeeded += 1
        else:
            mark_job_failed(job_id, "All uploaders failed")
            try:
                send_notification(
                    status="failed",
                    title=title,
                    error_message="All upload platforms failed",
                )
            except Exception:
                pass

    logger.info("=" * 55)
    logger.info(f"  Queue run complete: {succeeded}/{len(due_jobs)} job(s) uploaded")
    logger.info("=" * 55)
    return succeeded



def _health_check() -> int:
    """
    Verify external dependencies are reachable.
    Returns exit code 0 (all OK) or 1 (at least one failure).
    """
    from src import config
    checks: dict[str, bool] = {}

    # 1. MongoDB
    try:
        from pymongo import MongoClient
        if not config.MONGODB_URI:
            raise RuntimeError("MONGODB_URI not set")
        client = MongoClient(config.MONGODB_URI, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        client.close()
        checks["mongodb"] = True
    except Exception as e:
        logger.error(f"MongoDB: {e}")
        checks["mongodb"] = False

    # 2. Gemini API
    try:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY not set")
        from google import genai
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        # lightweight list-models call to verify key
        next(iter(client.models.list()))
        checks["gemini"] = True
    except Exception as e:
        logger.error(f"Gemini: {e}")
        checks["gemini"] = False

    # 3. YouTube Credentials
    try:
        has_creds = all([
            config.YOUTUBE_CLIENT_ID,
            config.YOUTUBE_CLIENT_SECRET,
            config.YOUTUBE_REFRESH_TOKEN,
        ])
        if not has_creds:
            raise RuntimeError("YouTube OAuth credentials incomplete")
        checks["youtube_creds"] = True
    except Exception as e:
        logger.error(f"YouTube: {e}")
        checks["youtube_creds"] = False

    # 4. edge-tts availability
    try:
        import edge_tts  # noqa: F401
        checks["edge_tts"] = True
    except ImportError:
        logger.error("edge-tts package not installed")
        checks["edge_tts"] = False

    # Summary
    all_ok = all(checks.values())
    status = "HEALTHY" if all_ok else "UNHEALTHY"
    for name, ok in checks.items():
        icon = "✓" if ok else "✗"
        logger.info(f"  {icon} {name}")
    logger.info(f"Health check: {status}")
    return 0 if all_ok else 1


def analytics_pipeline(save: bool = False) -> int:
    """
    Phase 4.3: Generate analytics report from MongoDB history.

    Args:
        save: If True, also write report to output/ directory.

    Returns:
        0 on success, 1 on error.
    """
    from src.analytics import generate_report, save_report

    try:
        report = generate_report()
        print(report)
        if save:
            path = save_report()
            logger.info(f"Report saved to: {path}")
        return 0
    except Exception as exc:
        logger.error(f"Analytics failed: {exc}", exc_info=True)
        return 1


if __name__ == "__main__":
    if "--health" in sys.argv:
        sys.exit(_health_check())
    if "--analytics" in sys.argv:
        sys.exit(analytics_pipeline(save="--save" in sys.argv))
    elif "--upload-queue" in sys.argv:
        upload_queue_pipeline()
    elif "--batch" in sys.argv:
        try:
            idx = sys.argv.index("--batch")
            n = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            logger.error("Usage: python -m src.main --batch <N>")
            sys.exit(1)
        batch_pipeline(n)
    else:
        main()
