"""
Tests for Phase 3 — Feature Hardening.
Covers: quality scoring, video verification, deduplication, graceful degradation,
dynamic font scaling, rate limiting, and error classification.
"""
import time
import pytest
from unittest.mock import patch, MagicMock

from src.quality import score_content, _range_score, QUALITY_THRESHOLD
from src.errors import (
    ErrorClass, PipelineError, TransientError, PermanentError, ContentError,
    classify_error, is_retryable,
)
from src.rate_limiter import RateLimiter, YOUTUBE_DAILY_QUOTA, YOUTUBE_UPLOAD_COST
from src.renderer import compute_dynamic_font_size
from src.video import verify_video, MIN_FILE_SIZE_KB, MAX_FILE_SIZE_MB
from src.db import _normalize_code


# ══════════════════════════════════════════════════════════════
#  3.1 — CONTENT QUALITY SCORING
# ══════════════════════════════════════════════════════════════

class TestQualityScoring:
    """Tests for content quality scoring (Phase 3.1)."""

    def test_perfect_content_passes(self, sample_content):
        """Well-formed content should pass quality check."""
        result = score_content(sample_content)
        assert result["passed"]
        assert result["total_score"] >= QUALITY_THRESHOLD

    def test_total_score_range(self, sample_content):
        assert 0 <= score_content(sample_content)["total_score"] <= 100

    def test_breakdown_has_all_dimensions(self, sample_content):
        result = score_content(sample_content)
        assert "script_words" in result["breakdown"]
        assert "code_lines" in result["breakdown"]
        assert "hashtags" in result["breakdown"]
        assert "code_quality" in result["breakdown"]
        assert "diversity" in result["breakdown"]

    def test_short_script_penalized(self):
        content = {
            "title": "T #Shorts",
            "script": "Too short",
            "code": "x = 1\ny = 2\nprint(x + y)",
            "hashtags": ["#A", "#B", "#C", "#D", "#E"],
            "content_type": "tip",
        }
        result = score_content(content)
        assert result["breakdown"]["script_words"] < 25
        assert any("short" in r.lower() for r in result["reasons"])

    def test_long_script_penalized(self):
        content = {
            "title": "T #Shorts",
            "script": " ".join(["word"] * 100),
            "code": "x = 1\ny = 2\nprint(x + y)",
            "hashtags": ["#A", "#B", "#C", "#D", "#E"],
            "content_type": "tip",
        }
        result = score_content(content)
        assert result["breakdown"]["script_words"] < 25

    def test_too_few_code_lines_penalized(self):
        content = {
            "title": "T #Shorts",
            "script": " ".join(["word"] * 50),
            "code": "x = 1",
            "hashtags": ["#A", "#B", "#C", "#D", "#E"],
            "content_type": "tip",
        }
        result = score_content(content)
        assert result["breakdown"]["code_lines"] < 25

    def test_too_few_hashtags_penalized(self):
        content = {
            "title": "T #Shorts",
            "script": " ".join(["word"] * 50),
            "code": "x = 1\ny = 2\nz = 3\nprint(x + y + z)",
            "hashtags": ["#A", "#B"],
            "content_type": "tip",
        }
        result = score_content(content)
        assert result["breakdown"]["hashtags"] < 15

    def test_diversity_penalty_same_type(self):
        content = {
            "title": "T #Shorts",
            "script": " ".join(["word"] * 50),
            "code": "x = 1\ny = 2\nz = 3\nprint(x + y + z)",
            "hashtags": ["#A", "#B", "#C", "#D", "#E"],
            "content_type": "tip",
        }
        result = score_content(content, recent_types=["tip", "tip", "tip"])
        assert result["breakdown"]["diversity"] < 15

    def test_diversity_bonus_unique_type(self):
        content = {
            "title": "T #Shorts",
            "script": " ".join(["word"] * 50),
            "code": "x = 1\ny = 2\nz = 3\nprint(x + y + z)",
            "hashtags": ["#A", "#B", "#C", "#D", "#E"],
            "content_type": "quiz",
        }
        result = score_content(content, recent_types=["tip", "output_demo", "before_after"])
        assert result["breakdown"]["diversity"] == 15

    def test_placeholder_code_penalized(self):
        content = {
            "title": "T #Shorts",
            "script": " ".join(["word"] * 50),
            "code": "# TODO: your code here\npass",
            "hashtags": ["#A", "#B", "#C", "#D", "#E"],
            "content_type": "tip",
        }
        result = score_content(content)
        assert any("placeholder" in r.lower() for r in result["reasons"])


class TestRangeScore:
    """Tests for the _range_score utility."""

    def test_in_range_gets_max(self):
        assert _range_score(5, 3, 10, 25) == 25

    def test_below_range_scaled(self):
        score = _range_score(1, 3, 10, 25)
        assert 0 < score < 25

    def test_zero_gets_zero(self):
        assert _range_score(0, 3, 10, 25) == 0

    def test_above_range_penalized(self):
        score = _range_score(15, 3, 10, 25)
        assert score < 25


# ══════════════════════════════════════════════════════════════
#  3.2 — VIDEO QUALITY VERIFICATION
# ══════════════════════════════════════════════════════════════

class TestVideoVerification:
    """Tests for video quality verification (Phase 3.2)."""

    def test_nonexistent_file_fails(self, tmp_path):
        result = verify_video(str(tmp_path / "nonexistent.mp4"))
        assert not result["passed"]
        assert any("not found" in e for e in result["errors"])

    def test_empty_file_fails(self, tmp_path):
        f = tmp_path / "empty.mp4"
        f.write_bytes(b"")
        result = verify_video(str(f))
        assert not result["passed"]
        assert any("too small" in e.lower() for e in result["errors"])

    def test_tiny_file_fails(self, tmp_path):
        f = tmp_path / "tiny.mp4"
        f.write_bytes(b"x" * 50)  # 50 bytes < 100KB
        result = verify_video(str(f))
        assert not result["passed"]

    def test_valid_size_passes_size_check(self, tmp_path):
        f = tmp_path / "ok.mp4"
        f.write_bytes(b"x" * (200 * 1024))  # 200 KB
        result = verify_video(str(f))
        assert result["checks"]["size_ok"]

    def test_oversized_file_fails(self, tmp_path):
        """Files > 50MB should fail (we test at boundary)."""
        f = tmp_path / "big.mp4"
        # Write just over 50MB
        f.write_bytes(b"x" * (51 * 1024 * 1024))
        result = verify_video(str(f))
        assert not result["checks"]["size_ok"]
        assert any("too large" in e.lower() for e in result["errors"])


# ══════════════════════════════════════════════════════════════
#  3.3 — CONTENT DEDUPLICATION
# ══════════════════════════════════════════════════════════════

class TestContentDeduplication:
    """Tests for code similarity and deduplication (Phase 3.3)."""

    def test_normalize_strips_comments(self):
        code = "x = 1  # set x\ny = 2  # set y"
        result = _normalize_code(code)
        assert "#" not in result
        assert "set" not in result

    def test_normalize_collapses_whitespace(self):
        code = "x  =   1\n\n\ny = 2"
        result = _normalize_code(code)
        assert "  " not in result

    def test_normalize_lowercases(self):
        code = "MyVar = 42"
        result = _normalize_code(code)
        assert result == "myvar = 42"

    def test_normalize_strips_multiline_comments(self):
        code = "x = 1\n/* this is\na comment */\ny = 2"
        result = _normalize_code(code)
        assert "comment" not in result

    def test_normalize_js_comments(self):
        code = "let x = 1; // initialize\nlet y = 2;"
        result = _normalize_code(code)
        assert "initialize" not in result


# ══════════════════════════════════════════════════════════════
#  3.5 — DYNAMIC FONT SCALING
# ══════════════════════════════════════════════════════════════

class TestDynamicFontScaling:
    """Tests for dynamic font scaling (Phase 3.5)."""

    def test_short_code_keeps_default_size(self):
        code = "x = 1\ny = 2\nprint(x + y)"
        assert compute_dynamic_font_size(code, 24) == 24

    def test_many_lines_shrinks_font(self):
        code = "\n".join(f"line_{i} = {i}" for i in range(20))
        result = compute_dynamic_font_size(code, 24)
        assert result < 24

    def test_long_lines_shrinks_font(self):
        code = "x" * 80 + "\ny = 1"
        result = compute_dynamic_font_size(code, 24)
        assert result < 24

    def test_minimum_font_size_enforced(self):
        code = "\n".join("x" * 100 for _ in range(50))
        result = compute_dynamic_font_size(code, 24)
        assert result >= 16

    def test_maximum_font_size_enforced(self):
        code = "x = 1"
        result = compute_dynamic_font_size(code, 30)
        assert result <= 28

    def test_empty_code_returns_base(self):
        assert compute_dynamic_font_size("", 24) == 24

    def test_exactly_12_lines_keeps_default(self):
        code = "\n".join(f"line {i}" for i in range(12))
        assert compute_dynamic_font_size(code, 24) == 24


# ══════════════════════════════════════════════════════════════
#  3.6 — RATE LIMITING
# ══════════════════════════════════════════════════════════════

class TestRateLimiter:
    """Tests for rate limiting awareness (Phase 3.6)."""

    def test_initial_state(self):
        rl = RateLimiter()
        status = rl.get_status()
        assert status["gemini_rpm_used"] == 0
        assert status["youtube_can_upload"]

    def test_pre_gemini_no_delay_initially(self):
        rl = RateLimiter()
        delay = rl.pre_gemini_call()
        assert delay == 0.0

    def test_record_gemini_increments(self):
        rl = RateLimiter()
        rl.record_gemini_call()
        rl.record_gemini_call()
        status = rl.get_status()
        assert status["gemini_rpm_used"] == 2

    def test_youtube_quota_initial(self):
        rl = RateLimiter()
        result = rl.check_youtube_quota()
        assert result["can_upload"]
        assert result["remaining"] == YOUTUBE_DAILY_QUOTA

    def test_youtube_quota_after_upload(self):
        rl = RateLimiter()
        rl.record_youtube_upload()
        result = rl.check_youtube_quota()
        assert result["used"] == YOUTUBE_UPLOAD_COST
        assert result["remaining"] == YOUTUBE_DAILY_QUOTA - YOUTUBE_UPLOAD_COST

    def test_youtube_quota_exceeded(self):
        rl = RateLimiter()
        # Simulate 7 uploads (7 × 1600 = 11,200 > 10,000)
        for _ in range(7):
            rl.record_youtube_upload()
        result = rl.check_youtube_quota()
        assert not result["can_upload"]

    def test_parse_gemini_headers(self):
        rl = RateLimiter()
        rl.record_gemini_call(response_headers={
            "X-RateLimit-Limit": "60",
            "X-RateLimit-Remaining": "58",
        })
        assert rl._gemini_rpm_limit == 60

    def test_get_status_structure(self):
        rl = RateLimiter()
        status = rl.get_status()
        assert "gemini_rpm_used" in status
        assert "gemini_rpm_limit" in status
        assert "youtube_quota_used" in status
        assert "youtube_quota_remaining" in status
        assert "youtube_can_upload" in status

    def test_youtube_api_call_cost(self):
        rl = RateLimiter()
        rl.record_youtube_api_call(cost=5)
        assert rl._youtube_quota_used == 5


# ══════════════════════════════════════════════════════════════
#  3.7 — ERROR CLASSIFICATION
# ══════════════════════════════════════════════════════════════

class TestErrorClassification:
    """Tests for improved error classification (Phase 3.7)."""

    # ── Error class constants ─────────────────────────────────

    def test_error_class_values(self):
        assert ErrorClass.TRANSIENT == "TRANSIENT"
        assert ErrorClass.PERMANENT == "PERMANENT"
        assert ErrorClass.CONTENT == "CONTENT"

    # ── PipelineError hierarchy ───────────────────────────────

    def test_transient_error(self):
        err = TransientError("timeout", step="gemini")
        assert err.error_class == ErrorClass.TRANSIENT
        assert err.step == "gemini"

    def test_permanent_error(self):
        err = PermanentError("quota exceeded", step="upload")
        assert err.error_class == ErrorClass.PERMANENT

    def test_content_error(self):
        err = ContentError("safety filter", step="content")
        assert err.error_class == ErrorClass.CONTENT

    def test_pipeline_error_repr(self):
        err = PipelineError("test error", ErrorClass.TRANSIENT, step="test")
        assert "TRANSIENT" in repr(err)
        assert "test" in repr(err)

    def test_pipeline_error_wraps_original(self):
        orig = ValueError("bad value")
        err = ContentError("wrapped", original=orig, step="validate")
        assert err.original is orig

    # ── classify_error ────────────────────────────────────────

    def test_classify_timeout(self):
        err = classify_error(TimeoutError("connection timed out"))
        assert err.error_class == ErrorClass.TRANSIENT

    def test_classify_connection_error(self):
        err = classify_error(ConnectionError("connection refused"))
        assert err.error_class == ErrorClass.TRANSIENT

    def test_classify_rate_limit(self):
        err = classify_error(Exception("429 Too Many Requests"))
        assert err.error_class == ErrorClass.TRANSIENT

    def test_classify_server_unavailable(self):
        err = classify_error(Exception("503 Service Unavailable"))
        assert err.error_class == ErrorClass.TRANSIENT

    def test_classify_invalid_credentials(self):
        err = classify_error(Exception("Invalid API key provided"))
        assert err.error_class == ErrorClass.PERMANENT

    def test_classify_quota_exceeded(self):
        err = classify_error(Exception("Quota exceeded for project"))
        assert err.error_class == ErrorClass.PERMANENT

    def test_classify_permission_denied(self):
        err = classify_error(PermissionError("access denied"))
        assert err.error_class == ErrorClass.PERMANENT

    def test_classify_safety_filter(self):
        err = classify_error(RuntimeError("Content blocked by safety filter"))
        assert err.error_class == ErrorClass.CONTENT

    def test_classify_missing_fields(self):
        err = classify_error(ValueError("Missing fields in response"))
        assert err.error_class == ErrorClass.CONTENT

    def test_classify_script_too_short(self):
        err = classify_error(ValueError("Script too short: 10 words"))
        assert err.error_class == ErrorClass.CONTENT

    def test_classify_already_classified(self):
        """Already-classified errors should pass through."""
        orig = TransientError("already classified")
        result = classify_error(orig)
        assert result is orig

    def test_classify_preserves_step(self):
        err = classify_error(Exception("timeout"), step="gemini")
        assert err.step == "gemini"

    def test_classify_unknown_defaults_transient(self):
        """Unknown errors default to TRANSIENT (safer — allows retry)."""
        err = classify_error(RuntimeError("something weird happened"))
        assert err.error_class == ErrorClass.TRANSIENT

    # ── is_retryable ──────────────────────────────────────────

    def test_is_retryable_transient(self):
        assert is_retryable(TransientError("timeout"))

    def test_is_not_retryable_permanent(self):
        assert not is_retryable(PermanentError("invalid key"))

    def test_is_not_retryable_content(self):
        assert not is_retryable(ContentError("bad content"))

    def test_is_retryable_unclassified_timeout(self):
        assert is_retryable(TimeoutError("timed out"))

    def test_is_not_retryable_unclassified_quota(self):
        assert not is_retryable(Exception("Quota exceeded"))


# ══════════════════════════════════════════════════════════════
#  3.4 — GRACEFUL DEGRADATION (via integration tests only)
# ══════════════════════════════════════════════════════════════
# Graceful degradation is tested through integration test overrides.
# The DB functions (save_pending_upload, get_pending_uploads, etc.)
# require MongoDB and are tested via mocking in test_integration.py.
