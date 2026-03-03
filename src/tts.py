"""
Text-to-Speech module using edge-tts (Microsoft Edge Neural Voices).
Generates high-quality voiceover audio with word-level timestamps for subtitle sync.

Phase 8.1: Fallback to gTTS if edge-tts fails 3 consecutive times.
"""
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

import edge_tts

from src import config

logger = logging.getLogger(__name__)

# Phase 8.1: Track consecutive edge-tts failures for fallback
_edge_tts_consecutive_failures = 0
_EDGE_TTS_MAX_FAILURES = 3


@dataclass
class WordTimestamp:
    """A single word with its timing in the audio."""
    text: str
    start_s: float  # start time in seconds
    end_s: float    # end time in seconds


async def _generate_speech_async(
    text: str,
    voice: str,
    output_path: str,
) -> list[WordTimestamp]:
    """
    Internal async implementation.
    Streams audio to file and collects word-level timestamps.
    """
    communicate = edge_tts.Communicate(text, voice, rate=config.TTS_RATE, boundary="WordBoundary")
    word_timestamps: list[WordTimestamp] = []

    with open(output_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])

            elif chunk["type"] == "WordBoundary":
                # edge-tts returns offset/duration in 100-nanosecond ticks
                # Convert to seconds: ticks / 10_000_000
                offset_ticks = chunk.get("offset", 0)
                duration_ticks = chunk.get("duration", 0)
                word_text = chunk.get("text", "")

                if word_text.strip():
                    word_timestamps.append(
                        WordTimestamp(
                            text=word_text,
                            start_s=offset_ticks / 10_000_000,
                            end_s=(offset_ticks + duration_ticks) / 10_000_000,
                        )
                    )

    return word_timestamps


def generate_speech(
    text: str,
    voice: str | None = None,
    output_path: str | None = None,
) -> tuple[str, list[WordTimestamp]]:
    """
    Generate TTS audio from text with word-level timestamps.

    Args:
        text: The narration script to convert to speech.
        voice: Edge TTS voice name (default from config).
        output_path: Where to save the MP3 file (default: output/audio.mp3).

    Returns:
        Tuple of (audio_file_path, list_of_word_timestamps).
    """
    global _edge_tts_consecutive_failures

    if voice is None:
        # Auto-select language-appropriate voice (Phase 6.3)
        voice = (
            config.TTS_VOICE_ID
            if config.CONTENT_LANGUAGE == "id"
            else config.TTS_VOICE
        )
    output_path = output_path or str(config.OUTPUT_DIR / "audio.mp3")

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Generating TTS: voice={voice}, text={len(text)} chars")

    # Phase 8.1: If edge-tts has failed too many times, go straight to fallback
    if _edge_tts_consecutive_failures >= _EDGE_TTS_MAX_FAILURES:
        logger.warning(
            f"edge-tts failed {_edge_tts_consecutive_failures}× consecutively, "
            "using gTTS fallback"
        )
        return _gtts_fallback(text, output_path)

    try:
        # Run async edge-tts in sync context (Python 3.10+ safe)
        word_timestamps = asyncio.run(
            _generate_speech_async(text, voice, output_path)
        )

        # Verify output
        audio_path = Path(output_path)
        if not audio_path.exists() or audio_path.stat().st_size < 100:
            raise RuntimeError(f"TTS failed: audio file is missing or too small at {output_path}")

        logger.info(
            f"TTS complete: {audio_path.stat().st_size / 1024:.1f} KB, "
            f"{len(word_timestamps)} word timestamps"
        )

        # Reset failure counter on success
        _edge_tts_consecutive_failures = 0
        return str(audio_path), word_timestamps

    except Exception as e:
        _edge_tts_consecutive_failures += 1
        logger.warning(
            f"edge-tts failed (attempt {_edge_tts_consecutive_failures}/"
            f"{_EDGE_TTS_MAX_FAILURES}): {e}"
        )
        if _edge_tts_consecutive_failures >= _EDGE_TTS_MAX_FAILURES:
            logger.warning("edge-tts max failures reached, falling back to gTTS")
            return _gtts_fallback(text, output_path)
        # Re-raise if not yet at max failures
        raise


def _gtts_fallback(text: str, output_path: str) -> tuple[str, list[WordTimestamp]]:
    """
    Phase 8.1: Fallback TTS using gTTS (Google Text-to-Speech).

    gTTS doesn't provide word-level timestamps, so we generate
    approximate timestamps based on word count and audio duration.

    Returns:
        Tuple of (audio_file_path, list_of_approximate_timestamps).
    """
    try:
        from gtts import gTTS
    except ImportError:
        raise RuntimeError(
            "gTTS fallback unavailable: pip install gTTS. "
            "edge-tts also failed."
        )

    logger.info("Generating TTS via gTTS fallback...")

    lang = "id" if config.CONTENT_LANGUAGE == "id" else "en"
    tts = gTTS(text=text, lang=lang, slow=False)

    # gTTS outputs MP3
    tts.save(output_path)

    audio_path = Path(output_path)
    if not audio_path.exists() or audio_path.stat().st_size < 100:
        raise RuntimeError(f"gTTS fallback failed: audio file missing at {output_path}")

    # Generate approximate word timestamps from audio duration
    duration = get_audio_duration(output_path)
    words = text.split()
    word_timestamps = _approximate_timestamps(words, duration)

    logger.info(
        f"gTTS fallback complete: {audio_path.stat().st_size / 1024:.1f} KB, "
        f"~{len(word_timestamps)} word timestamps (approximate)"
    )
    return str(audio_path), word_timestamps


def _approximate_timestamps(
    words: list[str], total_duration: float
) -> list[WordTimestamp]:
    """
    Generate approximate word timestamps by distributing evenly across duration.

    Not as accurate as edge-tts WordBoundary, but functional for subtitle sync.
    """
    if not words or total_duration <= 0:
        return []

    avg_duration = total_duration / len(words)
    timestamps = []
    for i, word in enumerate(words):
        start = i * avg_duration
        end = start + avg_duration
        timestamps.append(WordTimestamp(text=word, start_s=start, end_s=end))
    return timestamps


def get_audio_duration(audio_path: str) -> float:
    """Get the duration of an audio file in seconds using moviepy."""
    from moviepy import AudioFileClip
    clip = AudioFileClip(audio_path)
    duration = clip.duration
    clip.close()
    return duration
