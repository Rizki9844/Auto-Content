"""
Abstract base for all platform uploaders.

Every concrete uploader (YouTube, TikTok, Instagram) subclasses
``UploaderBase`` and implements the three required methods.

The ``get_uploaders()`` factory reads ``UPLOAD_TARGETS`` from config
and returns only the configured / available instances.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from src import config

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  Upload result value-object
# ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class UploadResult:
    """Immutable result returned by every uploader."""

    platform: str
    success: bool
    video_id: str = ""
    url: str = ""
    error: str = ""


# ──────────────────────────────────────────────────────────────
#  Abstract base
# ──────────────────────────────────────────────────────────────
class UploaderBase(ABC):
    """Interface every platform uploader must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short platform identifier (e.g. 'youtube', 'tiktok')."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return *True* if all required credentials / env vars are present."""

    @abstractmethod
    def upload(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: list[str] | None = None,
    ) -> UploadResult:
        """
        Upload a video and return an ``UploadResult``.

        Must **never** raise — catch exceptions internally and return
        an ``UploadResult(success=False, error=...)`` instead.
        """


# ──────────────────────────────────────────────────────────────
#  Registry & factory
# ──────────────────────────────────────────────────────────────
_REGISTRY: dict[str, type[UploaderBase]] = {}


def register_uploader(cls: type[UploaderBase]) -> type[UploaderBase]:
    """Class decorator — registers an uploader by its ``name``."""
    instance = cls()
    _REGISTRY[instance.name] = cls
    return cls


def get_uploaders() -> list[UploaderBase]:
    """
    Read ``UPLOAD_TARGETS`` (comma-separated) and return **configured**
    uploader instances.  Unknown or unconfigured targets are skipped
    with a warning.
    """
    # Force-import concrete subclasses so they auto-register
    _discover_uploaders()

    targets = [
        t.strip().lower()
        for t in config.UPLOAD_TARGETS.split(",")
        if t.strip()
    ]

    uploaders: list[UploaderBase] = []
    for target in targets:
        cls = _REGISTRY.get(target)
        if cls is None:
            logger.warning(f"Unknown upload target '{target}' — skipped")
            continue
        inst = cls()
        if not inst.is_configured():
            logger.warning(
                f"Upload target '{target}' is not configured "
                "(missing credentials) — skipped"
            )
            continue
        uploaders.append(inst)

    if not uploaders:
        logger.warning("No upload targets configured — videos will not be uploaded")

    return uploaders


def _discover_uploaders() -> None:
    """Import every uploader_*.py module so decorators run."""
    import importlib

    for mod_name in (
        "src.uploader_youtube",
        "src.uploader_tiktok",
        "src.uploader_instagram",
    ):
        try:
            importlib.import_module(mod_name)
        except Exception:
            pass  # module may not exist yet or have missing deps
