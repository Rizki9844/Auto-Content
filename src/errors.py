"""
Improved Error Classification — Phase 3.7

Classifies pipeline errors into three categories:
  TRANSIENT  — network timeouts, API overload → worth retrying
  PERMANENT  — invalid credentials, quota exceeded → do NOT retry
  CONTENT    — safety filter, validation failure → regenerate content

Each error carries a class, original exception, and human-readable message.
The notifier uses the class to tailor Telegram alerts.
"""
import re
import logging

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
#  ERROR CLASSES
# ══════════════════════════════════════════════════════════════

class ErrorClass:
    """Error classification constants."""
    TRANSIENT = "TRANSIENT"
    PERMANENT = "PERMANENT"
    CONTENT = "CONTENT"


class PipelineError(Exception):
    """
    Base exception for classified pipeline errors.

    Attributes:
        error_class: One of ErrorClass.TRANSIENT / PERMANENT / CONTENT
        original:    The original exception (if wrapping)
        step:        Pipeline step where error occurred (e.g., "gemini", "upload")
    """

    def __init__(
        self,
        message: str,
        error_class: str = ErrorClass.TRANSIENT,
        original: Exception | None = None,
        step: str = "unknown",
    ):
        super().__init__(message)
        self.error_class = error_class
        self.original = original
        self.step = step

    def __repr__(self):
        return (
            f"PipelineError(class={self.error_class}, step={self.step}, "
            f"msg={str(self)[:80]})"
        )


class TransientError(PipelineError):
    """Temporary failure — safe to retry."""

    def __init__(self, message: str, original: Exception | None = None, step: str = "unknown"):
        super().__init__(message, ErrorClass.TRANSIENT, original, step)


class PermanentError(PipelineError):
    """Unrecoverable failure — do NOT retry."""

    def __init__(self, message: str, original: Exception | None = None, step: str = "unknown"):
        super().__init__(message, ErrorClass.PERMANENT, original, step)


class ContentError(PipelineError):
    """Content-level failure — regenerate content."""

    def __init__(self, message: str, original: Exception | None = None, step: str = "unknown"):
        super().__init__(message, ErrorClass.CONTENT, original, step)


# ══════════════════════════════════════════════════════════════
#  CLASSIFICATION LOGIC
# ══════════════════════════════════════════════════════════════

# Patterns that indicate transient (retryable) errors
_TRANSIENT_PATTERNS = [
    re.compile(r"timeout", re.I),
    re.compile(r"timed?\s*out", re.I),
    re.compile(r"connection\s*(reset|refused|aborted|error)", re.I),
    re.compile(r"server\s*(unavailable|error|busy)", re.I),
    re.compile(r"502|503|504|429", re.I),
    re.compile(r"rate\s*limit", re.I),
    re.compile(r"too\s*many\s*requests", re.I),
    re.compile(r"temporary", re.I),
    re.compile(r"resource\s*exhausted", re.I),
    re.compile(r"UNAVAILABLE", re.I),
    re.compile(r"network", re.I),
    re.compile(r"retry", re.I),
    re.compile(r"overloaded", re.I),
]

# Patterns that indicate permanent (non-retryable) errors
_PERMANENT_PATTERNS = [
    re.compile(r"invalid\s*(api\s*key|credentials?|token)", re.I),
    re.compile(r"authentication?\s*(failed|error)", re.I),
    re.compile(r"unauthorized|forbidden|403|401", re.I),
    re.compile(r"quota\s*(exceeded|depleted)", re.I),
    re.compile(r"billing", re.I),
    re.compile(r"not\s*configured", re.I),
    re.compile(r"permission\s*denied", re.I),
    re.compile(r"PERMISSION_DENIED", re.I),
    re.compile(r"daily\s*limit", re.I),
]

# Patterns that indicate content-level errors
_CONTENT_PATTERNS = [
    re.compile(r"blocked\s*(by\s*)?safety", re.I),
    re.compile(r"content\s*blocked", re.I),
    re.compile(r"safety\s*filter", re.I),
    re.compile(r"missing\s*fields?", re.I),
    re.compile(r"code\s*snippet\s*is\s*empty", re.I),
    re.compile(r"script\s*too\s*short", re.I),
    re.compile(r"quality\s*score", re.I),
    re.compile(r"validation", re.I),
    re.compile(r"blocked\s*keyword", re.I),
]


def classify_error(error: Exception, step: str = "unknown") -> PipelineError:
    """
    Classify an arbitrary exception into TRANSIENT, PERMANENT, or CONTENT.

    Args:
        error: The original exception.
        step:  Pipeline step name (e.g., "gemini", "tts", "render", "upload").

    Returns:
        A typed PipelineError subclass wrapping the original.
    """
    msg = str(error)

    # Already classified?
    if isinstance(error, PipelineError):
        return error

    # Check content patterns first (most specific)
    for pattern in _CONTENT_PATTERNS:
        if pattern.search(msg):
            return ContentError(msg, original=error, step=step)

    # Check permanent patterns
    for pattern in _PERMANENT_PATTERNS:
        if pattern.search(msg):
            return PermanentError(msg, original=error, step=step)

    # Check transient patterns
    for pattern in _TRANSIENT_PATTERNS:
        if pattern.search(msg):
            return TransientError(msg, original=error, step=step)

    # Check exception types as fallback
    exc_type = type(error).__name__
    if exc_type in ("TimeoutError", "ConnectionError", "ConnectionResetError",
                     "BrokenPipeError", "OSError"):
        return TransientError(msg, original=error, step=step)

    if exc_type in ("ValueError", "KeyError", "TypeError"):
        return ContentError(msg, original=error, step=step)

    if exc_type in ("PermissionError",):
        return PermanentError(msg, original=error, step=step)

    # Default: treat unknown errors as transient (safer — allows retry)
    logger.debug(f"Unclassified error at step '{step}': {exc_type}: {msg}")
    return TransientError(msg, original=error, step=step)


def is_retryable(error: Exception) -> bool:
    """Quick check: is this error worth retrying?"""
    if isinstance(error, PipelineError):
        return error.error_class == ErrorClass.TRANSIENT
    classified = classify_error(error)
    return classified.error_class == ErrorClass.TRANSIENT
