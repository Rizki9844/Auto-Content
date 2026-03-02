"""
Text-to-Speech module using edge-tts (Microsoft Edge Neural Voices).
Generates high-quality voiceover audio with word-level timestamps for subtitle sync.
"""
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

import edge_tts

from src import config

logger = logging.getLogger(__name__)


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
    communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")
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
    voice = voice or config.TTS_VOICE
    output_path = output_path or str(config.OUTPUT_DIR / "audio.mp3")

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Generating TTS: voice={voice}, text={len(text)} chars")

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

    return str(audio_path), word_timestamps


def get_audio_duration(audio_path: str) -> float:
    """Get the duration of an audio file in seconds using moviepy."""
    from moviepy import AudioFileClip
    clip = AudioFileClip(audio_path)
    duration = clip.duration
    clip.close()
    return duration
