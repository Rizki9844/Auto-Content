"""
Video assembly module — moviepy.
Combines rendered frames + TTS audio into a final MP4 (H.264 + AAC).
Output format: 1080×1920 @ 30fps, optimized for YouTube Shorts.

Phase 3.2: verify_video() checks file size, duration, and codec after render.
"""
import logging
import shutil
import subprocess
from pathlib import Path

from src import config
from src.renderer import FrameRenderer

logger = logging.getLogger(__name__)

# ── Video quality thresholds ──────────────────────────────────
MIN_FILE_SIZE_KB = 100         # minimum 100 KB
MAX_FILE_SIZE_MB = 50          # maximum 50 MB
MIN_DURATION_S = 5.0           # minimum 5 seconds
MAX_DURATION_S = 61.0          # YouTube Shorts max ~60s (1s tolerance)
REQUIRED_CODEC = "h264"        # expected video codec


def create_video(
    code: str,
    language: str,
    word_timestamps: list,
    audio_path: str,
    output_path: str | None = None,
    channel_name: str | None = None,
    content_type: str = "tip",
    code_output: str | None = None,
    code_before: str | None = None,
    title: str = "",
    series_part: int = 0,
) -> str:
    """
    Render a complete video from code + audio.

    Args:
        code: The code snippet to display.
        language: Programming language name (for syntax highlighting).
        word_timestamps: List of WordTimestamp objects from TTS module.
        audio_path: Path to the TTS-generated MP3 file.
        output_path: Where to save the final MP4 (default: output/video.mp4).
        channel_name: Override branding watermark text.
        content_type: One of "tip", "output_demo", "quiz", "before_after".
        code_output: Code execution output or quiz answer to display.
        code_before: "Before" code for before_after content type.
        title: Video title for intro card.
        series_part: Episode number in a series; 0 means standalone (Phase 6.4).

    Returns:
        Path to the rendered video file.
    """
    # Lazy import — moviepy is heavy, only load when needed
    from moviepy import VideoClip, AudioFileClip

    output_path = output_path or str(config.OUTPUT_DIR / "video.mp4")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # ── Load audio & determine duration ───────────────────────
    audio = AudioFileClip(audio_path)
    duration = audio.duration
    logger.info(f"Audio duration: {duration:.2f}s")

    # Safety check: YouTube Shorts max 60 seconds
    if duration > 59.0:
        logger.warning(f"Audio too long ({duration:.1f}s), truncating to 59s")
        duration = 59.0
        audio = audio.subclipped(0, 59.0)

    # ── Initialize frame renderer ─────────────────────────────
    renderer = FrameRenderer(
        code=code,
        language=language,
        word_timestamps=word_timestamps,
        duration=duration,
        channel_name=channel_name,
        content_type=content_type,
        code_output=code_output,
        code_before=code_before,
        title=title,
        series_part=series_part,
    )

    # ── Create video clip from frame function ─────────────────
    logger.info("Rendering video frames...")

    video = VideoClip(
        renderer.render_frame,
        duration=duration,
    )

    # Attach audio
    try:
        video = video.with_audio(audio)
    except AttributeError:
        # Fallback for older moviepy versions
        video.audio = audio

    # ── Export ─────────────────────────────────────────────────
    logger.info(f"Encoding video to {output_path}...")

    video.write_videofile(
        output_path,
        fps=config.VIDEO_FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=2,
        ffmpeg_params=[
            "-crf", "18",               # Higher quality (was 20)
            "-pix_fmt", "yuv420p",      # Maximum compatibility
            "-movflags", "+faststart",  # Web-optimized (progressive download)
            "-tune", "stillimage",      # Optimize for mostly-static code screens
            "-b:a", "192k",             # Better TTS audio quality
        ],
        logger=None,  # Suppress moviepy progress bar in CI
    )

    # Cleanup
    audio.close()

    file_size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    logger.info(f"Video saved: {output_path} ({file_size_mb:.1f} MB, {duration:.1f}s)")

    return output_path


# ══════════════════════════════════════════════════════════════
#  VIDEO QUALITY VERIFICATION  (Phase 3.2)
# ══════════════════════════════════════════════════════════════

def verify_video(video_path: str) -> dict:
    """
    Verify rendered video meets quality requirements.

    Checks:
      1. File exists and size is within range (100KB – 50MB)
      2. Duration is within range (5s – 61s)
      3. Video codec is H.264 (if ffprobe is available)

    Args:
        video_path: Path to the rendered MP4 file.

    Returns:
        Dict with keys:
          - passed (bool): True if all checks pass
          - checks (dict): Individual check results
          - errors (list[str]): Human-readable error descriptions
    """
    checks = {}
    errors = []
    path = Path(video_path)

    # ── 1. File existence & size ──────────────────────────────
    if not path.exists():
        checks["file_exists"] = False
        errors.append(f"Video file not found: {video_path}")
        return {"passed": False, "checks": checks, "errors": errors}

    checks["file_exists"] = True

    file_size_kb = path.stat().st_size / 1024
    file_size_mb = file_size_kb / 1024
    checks["file_size_kb"] = round(file_size_kb, 1)

    if file_size_kb < MIN_FILE_SIZE_KB:
        checks["size_ok"] = False
        errors.append(f"File too small: {file_size_kb:.1f} KB (min {MIN_FILE_SIZE_KB} KB)")
    elif file_size_mb > MAX_FILE_SIZE_MB:
        checks["size_ok"] = False
        errors.append(f"File too large: {file_size_mb:.1f} MB (max {MAX_FILE_SIZE_MB} MB)")
    else:
        checks["size_ok"] = True

    # ── 2. Duration check (via ffprobe if available) ──────────
    duration = _get_video_duration(video_path)
    checks["duration_s"] = duration

    if duration is not None:
        if duration < MIN_DURATION_S:
            checks["duration_ok"] = False
            errors.append(f"Video too short: {duration:.1f}s (min {MIN_DURATION_S}s)")
        elif duration > MAX_DURATION_S:
            checks["duration_ok"] = False
            errors.append(f"Video too long: {duration:.1f}s (max {MAX_DURATION_S}s)")
        else:
            checks["duration_ok"] = True
    else:
        checks["duration_ok"] = None  # Could not determine
        logger.warning("Could not determine video duration (ffprobe not available)")

    # ── 3. Codec verification (via ffprobe if available) ──────
    codec = _get_video_codec(video_path)
    checks["codec"] = codec

    if codec is not None:
        checks["codec_ok"] = codec == REQUIRED_CODEC
        if not checks["codec_ok"]:
            errors.append(f"Wrong codec: '{codec}' (expected '{REQUIRED_CODEC}')")
    else:
        checks["codec_ok"] = None  # Could not determine

    passed = all(
        v is True
        for k, v in checks.items()
        if k.endswith("_ok")
    )
    checks["passed"] = passed

    if passed:
        logger.info(f"Video verification PASSED: {file_size_mb:.1f} MB, {duration or '?'}s, codec={codec or '?'}")
    else:
        logger.warning(f"Video verification FAILED: {errors}")

    return {"passed": passed, "checks": checks, "errors": errors}


def _get_video_duration(video_path: str) -> float | None:
    """Get video duration in seconds using ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "quiet",
                "-print_format", "json",
                "-show_format", video_path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        import json
        info = json.loads(result.stdout)
        return float(info.get("format", {}).get("duration", 0))
    except Exception as e:
        logger.debug(f"ffprobe duration check failed: {e}")
        return None


def _get_video_codec(video_path: str) -> str | None:
    """Get video codec name using ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "quiet",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_name",
                "-print_format", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        codec = result.stdout.strip()
        return codec if codec else None
    except Exception as e:
        logger.debug(f"ffprobe codec check failed: {e}")
        return None
