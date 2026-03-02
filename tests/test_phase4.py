"""
Tests for Phase 4.1 — Multi-Platform Upload abstraction.
Covers: UploaderBase, UploadResult, registry, get_uploaders, and
adapter classes for YouTube, TikTok, Instagram.
"""
from unittest.mock import patch

from src.uploader_base import (
    UploadResult, get_uploaders, _REGISTRY,
)


# ──────────────────────────────────────────────────────────────
#  UploadResult dataclass
# ──────────────────────────────────────────────────────────────
class TestUploadResult:
    def test_success_result(self):
        r = UploadResult(platform="youtube", success=True, video_id="abc123",
                         url="https://youtube.com/shorts/abc123")
        assert r.platform == "youtube"
        assert r.success is True
        assert r.video_id == "abc123"
        assert r.url == "https://youtube.com/shorts/abc123"
        assert r.error == ""

    def test_failure_result(self):
        r = UploadResult(platform="tiktok", success=False, error="Network error")
        assert r.success is False
        assert r.video_id == ""
        assert r.error == "Network error"

    def test_frozen(self):
        r = UploadResult(platform="youtube", success=True)
        try:
            r.platform = "tiktok"  # type: ignore[misc]
            assert False, "Should not be mutable"
        except AttributeError:
            pass


# ──────────────────────────────────────────────────────────────
#  Registry & get_uploaders factory
# ──────────────────────────────────────────────────────────────
class TestRegistry:
    def test_register_uploader_adds_to_registry(self):
        """Built-in uploaders should be discoverable after import."""
        # Force discovery
        from src.uploader_base import _discover_uploaders
        _discover_uploaders()
        assert "youtube" in _REGISTRY

    def test_get_uploaders_returns_configured_only(self):
        """Uploaders without credentials should be skipped."""
        with (
            patch("src.config.UPLOAD_TARGETS", "youtube,tiktok,instagram"),
            patch("src.config.YOUTUBE_CLIENT_ID", "fake-id"),
            patch("src.config.YOUTUBE_REFRESH_TOKEN", "fake-token"),
            patch("src.config.TIKTOK_ACCESS_TOKEN", ""),
            patch("src.config.INSTAGRAM_ACCESS_TOKEN", ""),
            patch("src.config.INSTAGRAM_ACCOUNT_ID", ""),
        ):
            uploaders = get_uploaders()
            names = [u.name for u in uploaders]
            assert "youtube" in names
            assert "tiktok" not in names
            assert "instagram" not in names

    def test_get_uploaders_unknown_target_skipped(self):
        """Unknown platform names should be silently skipped."""
        with patch("src.config.UPLOAD_TARGETS", "youtube,fakebook"):
            with (
                patch("src.config.YOUTUBE_CLIENT_ID", "id"),
                patch("src.config.YOUTUBE_REFRESH_TOKEN", "tok"),
            ):
                uploaders = get_uploaders()
                assert all(u.name != "fakebook" for u in uploaders)

    def test_get_uploaders_empty_targets(self):
        """Empty UPLOAD_TARGETS should return empty list."""
        with patch("src.config.UPLOAD_TARGETS", ""):
            assert get_uploaders() == []

    def test_get_uploaders_default_youtube(self):
        """Default UPLOAD_TARGETS='youtube' should work."""
        with (
            patch("src.config.UPLOAD_TARGETS", "youtube"),
            patch("src.config.YOUTUBE_CLIENT_ID", "id"),
            patch("src.config.YOUTUBE_REFRESH_TOKEN", "tok"),
        ):
            uploaders = get_uploaders()
            assert len(uploaders) == 1
            assert uploaders[0].name == "youtube"


# ──────────────────────────────────────────────────────────────
#  YouTube adapter
# ──────────────────────────────────────────────────────────────
class TestYouTubeUploader:
    def test_name(self):
        from src.uploader_youtube import YouTubeUploader
        assert YouTubeUploader().name == "youtube"

    def test_is_configured_true(self):
        from src.uploader_youtube import YouTubeUploader
        with (
            patch("src.config.YOUTUBE_CLIENT_ID", "id"),
            patch("src.config.YOUTUBE_REFRESH_TOKEN", "tok"),
        ):
            assert YouTubeUploader().is_configured() is True

    def test_is_configured_false_no_token(self):
        from src.uploader_youtube import YouTubeUploader
        with (
            patch("src.config.YOUTUBE_CLIENT_ID", "id"),
            patch("src.config.YOUTUBE_REFRESH_TOKEN", ""),
        ):
            assert YouTubeUploader().is_configured() is False

    def test_upload_success(self):
        from src.uploader_youtube import YouTubeUploader
        with patch("src.uploader_youtube.upload_to_youtube", return_value="vid123"):
            result = YouTubeUploader().upload("/tmp/v.mp4", "T", "D", ["#tag"])
        assert result.success is True
        assert result.video_id == "vid123"
        assert "youtube.com" in result.url

    def test_upload_returns_none(self):
        from src.uploader_youtube import YouTubeUploader
        with patch("src.uploader_youtube.upload_to_youtube", return_value=None):
            result = YouTubeUploader().upload("/tmp/v.mp4", "T", "D")
        assert result.success is False

    def test_upload_exception_caught(self):
        from src.uploader_youtube import YouTubeUploader
        with patch("src.uploader_youtube.upload_to_youtube", side_effect=RuntimeError("boom")):
            result = YouTubeUploader().upload("/tmp/v.mp4", "T", "D")
        assert result.success is False
        assert "boom" in result.error


# ──────────────────────────────────────────────────────────────
#  TikTok adapter
# ──────────────────────────────────────────────────────────────
class TestTikTokUploader:
    def test_name(self):
        from src.uploader_tiktok import TikTokUploader
        assert TikTokUploader().name == "tiktok"

    def test_is_configured_true(self):
        from src.uploader_tiktok import TikTokUploader
        with patch("src.config.TIKTOK_ACCESS_TOKEN", "tok"):
            assert TikTokUploader().is_configured() is True

    def test_is_configured_false(self):
        from src.uploader_tiktok import TikTokUploader
        with patch("src.config.TIKTOK_ACCESS_TOKEN", ""):
            assert TikTokUploader().is_configured() is False

    def test_upload_success(self):
        from src.uploader_tiktok import TikTokUploader
        with patch("src.uploader_tiktok.upload_to_tiktok", return_value="tt_123"):
            result = TikTokUploader().upload("/tmp/v.mp4", "T", "D", ["#tag"])
        assert result.success is True
        assert result.video_id == "tt_123"

    def test_upload_exception_caught(self):
        from src.uploader_tiktok import TikTokUploader
        with patch("src.uploader_tiktok.upload_to_tiktok", side_effect=RuntimeError("fail")):
            result = TikTokUploader().upload("/tmp/v.mp4", "T", "D")
        assert result.success is False
        assert "fail" in result.error


# ──────────────────────────────────────────────────────────────
#  Instagram adapter
# ──────────────────────────────────────────────────────────────
class TestInstagramUploader:
    def test_name(self):
        from src.uploader_instagram import InstagramUploader
        assert InstagramUploader().name == "instagram"

    def test_is_configured_true(self):
        from src.uploader_instagram import InstagramUploader
        with (
            patch("src.config.INSTAGRAM_ACCESS_TOKEN", "tok"),
            patch("src.config.INSTAGRAM_ACCOUNT_ID", "123"),
        ):
            assert InstagramUploader().is_configured() is True

    def test_is_configured_false_no_token(self):
        from src.uploader_instagram import InstagramUploader
        with (
            patch("src.config.INSTAGRAM_ACCESS_TOKEN", ""),
            patch("src.config.INSTAGRAM_ACCOUNT_ID", "123"),
        ):
            assert InstagramUploader().is_configured() is False

    def test_upload_no_video_url_returns_false(self):
        """Instagram upload requires public URL — without it, should return failure."""
        from src.uploader_instagram import InstagramUploader
        with (
            patch("src.config.INSTAGRAM_ACCESS_TOKEN", "tok"),
            patch("src.config.INSTAGRAM_ACCOUNT_ID", "123"),
        ):
            result = InstagramUploader().upload("/tmp/v.mp4", "T", "D")
        assert result.success is False
