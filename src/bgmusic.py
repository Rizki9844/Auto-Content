"""
Background music mixer — Phase 9.1.

Mixes a low-volume background music track with the TTS audio.
Features:
  - Random track selection from assets/music/ (MP3/OGG)
  - Anti-repeat: won't pick the same track 3× in a row
  - Fade in (first 1s) and fade out (last 1s)
  - Configurable volume via BGMUSIC_VOLUME (default 7%)

Usage:
    from src.bgmusic import mix_background_music
    final_path = mix_background_music("output/audio.mp3", "output/audio_mixed.mp3")
"""
from __future__ import annotations

import json
import logging
import random
from pathlib import Path

from src import config

logger = logging.getLogger(__name__)

# Track recent selections to avoid repeats
_HISTORY_FILE = config.OUTPUT_DIR / ".bgmusic_history.json"
_MAX_CONSECUTIVE = 3


def list_tracks() -> list[Path]:
    """Return all MP3/OGG files in the music directory."""
    music_dir = config.MUSIC_DIR
    if not music_dir.exists():
        return []
    exts = {".mp3", ".ogg", ".wav"}
    return sorted(p for p in music_dir.iterdir() if p.suffix.lower() in exts)


def _load_history() -> list[str]:
    """Load recent track selection history."""
    try:
        if _HISTORY_FILE.exists():
            return json.loads(_HISTORY_FILE.read_text())
    except Exception:
        pass
    return []


def _save_history(history: list[str]) -> None:
    """Persist the last N track selections."""
    try:
        _HISTORY_FILE.write_text(json.dumps(history[-10:]))
    except Exception:
        pass


def select_track(tracks: list[Path] | None = None) -> Path | None:
    """
    Select a random background music track, avoiding 3× consecutive repeats.

    Returns:
        Path to the selected track, or None if no tracks available.
    """
    if tracks is None:
        tracks = list_tracks()
    if not tracks:
        return None

    history = _load_history()

    # Filter out tracks used in last (MAX_CONSECUTIVE - 1) selections
    recent = history[-((_MAX_CONSECUTIVE - 1)):]
    candidates = [t for t in tracks if t.name not in recent]
    if not candidates:
        candidates = tracks  # fallback: pick any

    chosen = random.choice(candidates)
    history.append(chosen.name)
    _save_history(history)

    logger.info(f"Selected background music: {chosen.name}")
    return chosen


def mix_background_music(
    tts_audio_path: str,
    output_path: str | None = None,
    volume: float | None = None,
    track_path: str | None = None,
) -> str:
    """
    Mix background music with TTS audio.

    Args:
        tts_audio_path: Path to the TTS-generated audio file.
        output_path:    Where to save the mixed audio. Defaults to same dir as input.
        volume:         Background music volume (0.0–1.0). Defaults to config.BGMUSIC_VOLUME.
        track_path:     Explicit music track path. If None, selects randomly.

    Returns:
        Path to the mixed audio file.
    """
    from moviepy import AudioFileClip, CompositeAudioClip

    volume = volume if volume is not None else config.BGMUSIC_VOLUME
    if output_path is None:
        p = Path(tts_audio_path)
        output_path = str(p.parent / f"{p.stem}_mixed{p.suffix}")

    # Select track
    if track_path:
        music_file = Path(track_path)
    else:
        music_file = select_track()

    if music_file is None or not music_file.exists():
        logger.warning("No background music tracks available — returning original audio")
        return tts_audio_path

    logger.info(f"Mixing background music: {music_file.name} at {volume:.0%} volume")

    # Load TTS audio
    tts_clip = AudioFileClip(tts_audio_path)
    tts_duration = tts_clip.duration

    # Load and prepare background music
    bg_clip = AudioFileClip(str(music_file))

    # Loop or trim to match TTS duration
    if bg_clip.duration < tts_duration:
        # Loop the background music
        import math as _math
        loops_needed = _math.ceil(tts_duration / bg_clip.duration)
        from moviepy import concatenate_audioclips
        bg_clip = concatenate_audioclips([bg_clip] * loops_needed)

    # Trim to TTS duration
    bg_clip = bg_clip.subclipped(0, tts_duration)

    # Apply volume
    bg_clip = bg_clip.with_volume_scaled(volume)

    # Apply fade in/out (1 second each)
    fade_duration = min(1.0, tts_duration * 0.1)
    bg_clip = bg_clip.audio_fadein(fade_duration)
    bg_clip = bg_clip.audio_fadeout(fade_duration)

    # Composite: TTS (full volume) + background music
    mixed = CompositeAudioClip([tts_clip, bg_clip])

    # Export
    mixed.write_audiofile(output_path, logger=None)

    # Cleanup
    tts_clip.close()
    bg_clip.close()

    logger.info(f"Mixed audio saved: {output_path}")
    return output_path
