"""
Video assembly module — moviepy.
Combines rendered frames + TTS audio into a final MP4 (H.264 + AAC).
Output format: 1080×1920 @ 30fps, optimized for YouTube Shorts / TikTok.
"""
import logging
from pathlib import Path

from src import config
from src.renderer import FrameRenderer

logger = logging.getLogger(__name__)


def create_video(
    code: str,
    language: str,
    word_timestamps: list,
    audio_path: str,
    output_path: str | None = None,
    channel_name: str | None = None,
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
        preset="fast",
        threads=2,
        ffmpeg_params=[
            "-crf", "20",           # High quality (lower = better, 0–51)
            "-pix_fmt", "yuv420p",  # Maximum compatibility
            "-movflags", "+faststart",  # Web-optimized (progressive download)
        ],
        logger=None,  # Suppress moviepy progress bar in CI
    )

    # Cleanup
    audio.close()

    file_size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    logger.info(f"Video saved: {output_path} ({file_size_mb:.1f} MB, {duration:.1f}s)")

    return output_path
