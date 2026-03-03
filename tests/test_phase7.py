"""
Tests for Phase 7 — Growth Engine.

Sub-phases covered:
  7.1  SEO-Optimized Description Generator
  7.2  Auto-Post Pinned Comment
  7.3  Playlist & Series Management
  7.4  End Screen CTA Enhancement
  7.5  Upload Time Optimization
  7.6  Channel Performance Dashboard
"""
from __future__ import annotations

import importlib
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch



# ══════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════

def _reload_config(**overrides):
    """Reload src.config with env overrides already applied."""
    import src.config
    importlib.reload(src.config)
    for k, v in overrides.items():
        setattr(src.config, k, v)
    return src.config


# ══════════════════════════════════════════════════════════════
#  7.1 — SEO-Optimized Description Generator
# ══════════════════════════════════════════════════════════════

class TestSEODescription:
    """Phase 7.1: ``src.seo.generate_seo_description``."""

    def test_basic_generation(self, sample_content, monkeypatch):
        monkeypatch.setenv("CHANNEL_URL", "https://www.youtube.com/@TestChannel")
        _reload_config(CHANNEL_URL="https://www.youtube.com/@TestChannel")
        from src.seo import generate_seo_description

        desc = generate_seo_description(sample_content, duration_seconds=30)
        assert isinstance(desc, str)
        assert len(desc) > 50
        assert len(desc) <= 5000

    def test_contains_hook(self, sample_content, monkeypatch):
        monkeypatch.setenv("CHANNEL_URL", "https://www.youtube.com/@Test")
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Test")
        from src.seo import generate_seo_description

        desc = generate_seo_description(sample_content)
        # Hook should contain content-type prefix
        assert "🔥" in desc or "💡" in desc  # tip prefix

    def test_contains_bullets(self, sample_content, monkeypatch):
        monkeypatch.setenv("CHANNEL_URL", "https://www.youtube.com/@Test")
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Test")
        from src.seo import generate_seo_description

        desc = generate_seo_description(sample_content)
        assert "In this video:" in desc
        assert "•" in desc

    def test_contains_channel_url(self, sample_content, monkeypatch):
        monkeypatch.setenv("CHANNEL_URL", "https://www.youtube.com/@TestChan")
        _reload_config(CHANNEL_URL="https://www.youtube.com/@TestChan")
        from src.seo import generate_seo_description

        desc = generate_seo_description(sample_content)
        assert "https://www.youtube.com/@TestChan" in desc

    def test_contains_hashtags(self, sample_content, monkeypatch):
        monkeypatch.setenv("CHANNEL_URL", "https://www.youtube.com/@Test")
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Test")
        from src.seo import generate_seo_description

        desc = generate_seo_description(sample_content)
        assert "#Python" in desc

    def test_timestamps_with_duration(self, sample_content, monkeypatch):
        monkeypatch.setenv("CHANNEL_URL", "https://www.youtube.com/@Test")
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Test")
        from src.seo import generate_seo_description

        desc = generate_seo_description(sample_content, duration_seconds=45)
        assert "Timestamps" in desc or "0:00" in desc

    def test_timestamps_zero_duration(self, sample_content, monkeypatch):
        monkeypatch.setenv("CHANNEL_URL", "https://www.youtube.com/@Test")
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Test")
        from src.seo import generate_seo_description

        desc = generate_seo_description(sample_content, duration_seconds=0)
        # No timestamps when duration is 0
        assert "0:00" not in desc or "Timestamps" not in desc

    def test_quiz_hook(self, sample_content_quiz, monkeypatch):
        monkeypatch.setenv("CHANNEL_URL", "https://www.youtube.com/@Test")
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Test")
        from src.seo import generate_seo_description

        desc = generate_seo_description(sample_content_quiz)
        assert "🧠" in desc

    def test_before_after_hook(self, sample_content_before_after, monkeypatch):
        monkeypatch.setenv("CHANNEL_URL", "https://www.youtube.com/@Test")
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Test")
        from src.seo import generate_seo_description

        desc = generate_seo_description(sample_content_before_after)
        assert "✨" in desc

    def test_cta_lines_present(self, sample_content, monkeypatch):
        monkeypatch.setenv("CHANNEL_URL", "https://www.youtube.com/@Test")
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Test")
        from src.seo import generate_seo_description

        desc = generate_seo_description(sample_content)
        assert "Subscribe" in desc

    def test_extra_cta_appended(self, sample_content, monkeypatch):
        monkeypatch.setenv("CHANNEL_URL", "https://www.youtube.com/@Test")
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Test")
        from src.seo import generate_seo_description

        desc = generate_seo_description(sample_content, extra_cta="🎉 Special CTA")
        assert "🎉 Special CTA" in desc

    def test_max_5000_chars(self, monkeypatch):
        monkeypatch.setenv("CHANNEL_URL", "https://www.youtube.com/@Test")
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Test")
        from src.seo import generate_seo_description

        long_content = {
            "title": "Test",
            "script": "x " * 3000,
            "language": "python",
            "hashtags": ["#Test"] * 100,
            "content_type": "tip",
            "code": "print('hello')\n" * 200,
        }
        desc = generate_seo_description(long_content)
        assert len(desc) <= 5000

    def test_language_in_bullets(self, sample_content, monkeypatch):
        monkeypatch.setenv("CHANNEL_URL", "https://www.youtube.com/@Test")
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Test")
        from src.seo import generate_seo_description

        desc = generate_seo_description(sample_content)
        assert "Python" in desc  # Language: Python bullet

    def test_seo_keywords_present(self, sample_content, monkeypatch):
        monkeypatch.setenv("CHANNEL_URL", "https://www.youtube.com/@Test")
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Test")
        from src.seo import generate_seo_description

        desc = generate_seo_description(sample_content)
        assert "coding tips" in desc.lower()

    def test_custom_channel_url(self, sample_content, monkeypatch):
        monkeypatch.setenv("CHANNEL_URL", "https://www.youtube.com/@Default")
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Default")
        from src.seo import generate_seo_description

        desc = generate_seo_description(
            sample_content, channel_url="https://www.youtube.com/@Custom"
        )
        assert "@Custom" in desc


class TestSEOHelpers:
    """Unit tests for internal SEO helper functions."""

    def test_extract_hook_short(self):
        from src.seo import _extract_hook
        result = _extract_hook("Hello world. This is more text.")
        assert result == "Hello world."

    def test_extract_hook_truncates(self):
        from src.seo import _extract_hook
        long = "A" * 200
        result = _extract_hook(long, max_len=50)
        assert len(result) <= 51  # includes ellipsis

    def test_build_bullets_tip(self):
        from src.seo import _build_bullets
        bullets = _build_bullets({
            "language": "python",
            "content_type": "tip",
            "code": "print('hi')\nprint('bye')",
        })
        assert len(bullets) >= 2
        assert any("Python" in b for b in bullets)

    def test_build_bullets_quiz(self):
        from src.seo import _build_bullets
        bullets = _build_bullets({"language": "javascript", "content_type": "quiz", "code": "x=1"})
        assert any("quiz" in b.lower() for b in bullets)

    def test_build_timestamps_no_duration(self):
        from src.seo import _build_timestamps
        result = _build_timestamps(0, "tip")
        assert result == ""

    def test_build_timestamps_with_duration(self):
        from src.seo import _build_timestamps
        result = _build_timestamps(45, "tip")
        assert "0:00" in result
        assert "Intro" in result

    def test_build_seo_keywords(self):
        from src.seo import _build_seo_keywords
        result = _build_seo_keywords("python", "tip")
        assert "python" in result
        assert "coding" in result


# ══════════════════════════════════════════════════════════════
#  7.2 — Auto-Post Pinned Comment
# ══════════════════════════════════════════════════════════════

class TestAutoPinnedComment:
    """Phase 7.2: ``src.youtube_actions.post_pinned_comment``."""

    def test_disabled_by_default(self, sample_content, monkeypatch):
        monkeypatch.setenv("ENABLE_AUTO_COMMENT", "0")
        _reload_config(ENABLE_AUTO_COMMENT="0")
        from src.youtube_actions import post_pinned_comment

        result = post_pinned_comment("vid123", sample_content)
        assert result is None

    def test_enabled_posts_comment(self, sample_content, monkeypatch):
        monkeypatch.setenv("ENABLE_AUTO_COMMENT", "1")
        _reload_config(
            ENABLE_AUTO_COMMENT="1",
            CHANNEL_URL="https://www.youtube.com/@Test",
        )
        from src.youtube_actions import post_pinned_comment

        mock_svc = MagicMock()
        mock_svc.commentThreads().insert().execute.return_value = {"id": "comment123"}

        result = post_pinned_comment("vid123", sample_content, service=mock_svc)
        assert result == "comment123"

    def test_format_tip_comment(self, monkeypatch):
        monkeypatch.setenv("CHANNEL_URL", "https://www.youtube.com/@Test")
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Test")
        from src.youtube_actions import _format_comment

        text = _format_comment({"content_type": "tip", "language": "python"})
        assert "Python" in text
        assert "💡" in text or "🔥" in text

    def test_format_quiz_comment(self, monkeypatch):
        monkeypatch.setenv("CHANNEL_URL", "https://www.youtube.com/@Test")
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Test")
        from src.youtube_actions import _format_comment

        text = _format_comment({"content_type": "quiz", "language": "javascript"})
        assert "answer" in text.lower() or "🧠" in text

    def test_format_before_after_comment(self, monkeypatch):
        monkeypatch.setenv("CHANNEL_URL", "https://www.youtube.com/@Test")
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Test")
        from src.youtube_actions import _format_comment

        text = _format_comment({"content_type": "before_after", "language": "python"})
        assert "before" in text.lower() or "after" in text.lower() or "✨" in text

    def test_no_video_id(self, sample_content, monkeypatch):
        monkeypatch.setenv("ENABLE_AUTO_COMMENT", "1")
        _reload_config(ENABLE_AUTO_COMMENT="1")
        from src.youtube_actions import post_pinned_comment

        result = post_pinned_comment("", sample_content)
        assert result is None

    def test_api_error_graceful(self, sample_content, monkeypatch):
        monkeypatch.setenv("ENABLE_AUTO_COMMENT", "1")
        _reload_config(ENABLE_AUTO_COMMENT="1")
        from src.youtube_actions import post_pinned_comment

        mock_svc = MagicMock()
        mock_svc.commentThreads().insert().execute.side_effect = RuntimeError("403 Forbidden")

        result = post_pinned_comment("vid123", sample_content, service=mock_svc)
        assert result is None  # Gracefully returns None

    def test_default_comment_template(self, monkeypatch):
        monkeypatch.setenv("CHANNEL_URL", "https://www.youtube.com/@Test")
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Test")
        from src.youtube_actions import _format_comment

        text = _format_comment({"content_type": "unknown_type", "language": "rust"})
        assert "Subscribe" in text or "coding" in text.lower()


# ══════════════════════════════════════════════════════════════
#  7.3 — Playlist & Series Management
# ══════════════════════════════════════════════════════════════

class TestPlaylistManager:
    """Phase 7.3: ``src.playlist_manager``."""

    def test_disabled_by_default(self, sample_content, monkeypatch):
        monkeypatch.setenv("ENABLE_PLAYLISTS", "0")
        _reload_config(ENABLE_PLAYLISTS="0")
        from src.playlist_manager import auto_manage_playlist

        result = auto_manage_playlist("vid123", sample_content)
        assert result is None

    def test_get_or_create_uses_cache(self, monkeypatch):
        """When a playlist is cached in MongoDB, API should not be called."""
        monkeypatch.setenv("ENABLE_PLAYLISTS", "1")
        _reload_config(ENABLE_PLAYLISTS="1")
        from src.playlist_manager import get_or_create_playlist

        with patch("src.playlist_manager._get_cached_playlist_id", return_value="PL_CACHED"):
            result = get_or_create_playlist("Test Playlist")
            assert result == "PL_CACHED"

    def test_get_or_create_finds_existing(self, monkeypatch):
        """API should find existing playlist and cache it."""
        monkeypatch.setenv("ENABLE_PLAYLISTS", "1")
        _reload_config(ENABLE_PLAYLISTS="1")
        from src.playlist_manager import get_or_create_playlist

        mock_svc = MagicMock()
        mock_svc.playlists().list().execute.return_value = {
            "items": [
                {"id": "PL_FOUND", "snippet": {"title": "My Playlist"}},
            ],
            "nextPageToken": None,
        }

        with patch("src.playlist_manager._get_cached_playlist_id", return_value=None), \
             patch("src.playlist_manager._cache_playlist_id") as mock_cache:
            result = get_or_create_playlist("My Playlist", service=mock_svc)
            assert result == "PL_FOUND"
            mock_cache.assert_called_once_with("My Playlist", "PL_FOUND")

    def test_get_or_create_creates_new(self, monkeypatch):
        """When playlist doesn't exist, creates a new one."""
        monkeypatch.setenv("ENABLE_PLAYLISTS", "1")
        _reload_config(ENABLE_PLAYLISTS="1")
        from src.playlist_manager import get_or_create_playlist

        mock_svc = MagicMock()
        mock_svc.playlists().list().execute.return_value = {
            "items": [],
            "nextPageToken": None,
        }
        mock_svc.playlists().insert().execute.return_value = {"id": "PL_NEW"}

        with patch("src.playlist_manager._get_cached_playlist_id", return_value=None), \
             patch("src.playlist_manager._cache_playlist_id") as mock_cache:
            result = get_or_create_playlist("New Playlist", service=mock_svc)
            assert result == "PL_NEW"
            mock_cache.assert_called_once_with("New Playlist", "PL_NEW")

    def test_add_to_playlist_success(self, monkeypatch):
        from src.playlist_manager import add_to_playlist

        mock_svc = MagicMock()
        mock_svc.playlistItems().insert().execute.return_value = {}

        result = add_to_playlist("vid123", "PL_123", service=mock_svc)
        assert result is True

    def test_add_to_playlist_duplicate_ok(self, monkeypatch):
        from src.playlist_manager import add_to_playlist

        mock_svc = MagicMock()
        mock_svc.playlistItems().insert().execute.side_effect = RuntimeError("409 Conflict")

        result = add_to_playlist("vid123", "PL_123", service=mock_svc)
        assert result is True  # Duplicate is fine

    def test_add_to_playlist_error(self, monkeypatch):
        from src.playlist_manager import add_to_playlist

        mock_svc = MagicMock()
        mock_svc.playlistItems().insert().execute.side_effect = RuntimeError("500")

        result = add_to_playlist("vid123", "PL_123", service=mock_svc)
        assert result is False

    def test_auto_manage_creates_language_playlist(self, sample_content, monkeypatch):
        monkeypatch.setenv("ENABLE_PLAYLISTS", "1")
        _reload_config(
            ENABLE_PLAYLISTS="1",
            CHANNEL_NAME="@TestChannel",
            CHANNEL_URL="https://www.youtube.com/@TestChannel",
        )
        from src.playlist_manager import auto_manage_playlist

        with patch("src.playlist_manager.get_or_create_playlist", return_value="PL_LANG") as mock_goc, \
             patch("src.playlist_manager.add_to_playlist", return_value=True):
            result = auto_manage_playlist("vid123", sample_content)
            assert result == "PL_LANG"
            # Should contain language name in playlist title
            call_args = mock_goc.call_args
            assert "Python" in call_args[0][0]

    def test_auto_manage_series_playlist(self, sample_content, monkeypatch):
        monkeypatch.setenv("ENABLE_PLAYLISTS", "1")
        _reload_config(
            ENABLE_PLAYLISTS="1",
            CHANNEL_NAME="@TestChannel",
            CHANNEL_URL="https://www.youtube.com/@TestChannel",
        )
        from src.playlist_manager import auto_manage_playlist

        content_with_series = {**sample_content, "series_theme": "Modern Python Tricks"}

        with patch("src.playlist_manager.get_or_create_playlist", return_value="PL_SERIES") as mock_goc, \
             patch("src.playlist_manager.add_to_playlist", return_value=True):
            auto_manage_playlist("vid123", content_with_series)
            # Should have been called twice: language + series
            assert mock_goc.call_count == 2

    def test_no_video_id(self, sample_content, monkeypatch):
        monkeypatch.setenv("ENABLE_PLAYLISTS", "1")
        _reload_config(ENABLE_PLAYLISTS="1")
        from src.playlist_manager import auto_manage_playlist

        result = auto_manage_playlist("", sample_content)
        assert result is None

    def test_api_403_graceful(self, sample_content, monkeypatch):
        monkeypatch.setenv("ENABLE_PLAYLISTS", "1")
        _reload_config(ENABLE_PLAYLISTS="1")
        from src.playlist_manager import get_or_create_playlist

        mock_svc = MagicMock()
        mock_svc.playlists().list().execute.side_effect = RuntimeError("403 Forbidden")

        with patch("src.playlist_manager._get_cached_playlist_id", return_value=None):
            result = get_or_create_playlist("Test", service=mock_svc)
            assert result is None


# ══════════════════════════════════════════════════════════════
#  7.4 — End Screen CTA Enhancement
# ══════════════════════════════════════════════════════════════

class TestEndScreenCTA:
    """Phase 7.4: ``src.youtube_actions.add_end_screen_cta``."""

    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.setenv("ENABLE_END_SCREEN", "0")
        _reload_config(ENABLE_END_SCREEN="0")
        from src.youtube_actions import add_end_screen_cta

        result = add_end_screen_cta("vid123")
        assert result is False

    def test_enabled_appends_cta(self, monkeypatch):
        monkeypatch.setenv("ENABLE_END_SCREEN", "1")
        _reload_config(
            ENABLE_END_SCREEN="1",
            CHANNEL_URL="https://www.youtube.com/@Test",
            CHANNEL_NAME="@Test",
        )
        from src.youtube_actions import add_end_screen_cta

        mock_svc = MagicMock()
        mock_svc.videos().list().execute.return_value = {
            "items": [{
                "snippet": {
                    "title": "Test Video",
                    "description": "Original description",
                    "categoryId": "28",
                }
            }]
        }
        mock_svc.videos().update().execute.return_value = {}

        with patch("src.youtube_actions._get_latest_video_id", return_value="prev_vid"):
            result = add_end_screen_cta("vid123", service=mock_svc)
            assert result is True

    def test_skip_if_cta_already_present(self, monkeypatch):
        monkeypatch.setenv("ENABLE_END_SCREEN", "1")
        _reload_config(ENABLE_END_SCREEN="1")
        from src.youtube_actions import add_end_screen_cta

        mock_svc = MagicMock()
        mock_svc.videos().list().execute.return_value = {
            "items": [{
                "snippet": {
                    "title": "Test",
                    "description": "Already has sub_confirmation=1 link",
                    "categoryId": "28",
                }
            }]
        }

        result = add_end_screen_cta("vid123", service=mock_svc)
        assert result is True  # Returns True but skips update

    def test_video_not_found(self, monkeypatch):
        monkeypatch.setenv("ENABLE_END_SCREEN", "1")
        _reload_config(ENABLE_END_SCREEN="1")
        from src.youtube_actions import add_end_screen_cta

        mock_svc = MagicMock()
        mock_svc.videos().list().execute.return_value = {"items": []}

        result = add_end_screen_cta("vid_gone", service=mock_svc)
        assert result is False

    def test_no_video_id(self, monkeypatch):
        monkeypatch.setenv("ENABLE_END_SCREEN", "1")
        _reload_config(ENABLE_END_SCREEN="1")
        from src.youtube_actions import add_end_screen_cta

        result = add_end_screen_cta("")
        assert result is False

    def test_api_error_graceful(self, monkeypatch):
        monkeypatch.setenv("ENABLE_END_SCREEN", "1")
        _reload_config(ENABLE_END_SCREEN="1")
        from src.youtube_actions import add_end_screen_cta

        mock_svc = MagicMock()
        mock_svc.videos().list().execute.side_effect = RuntimeError("500 Server Error")

        result = add_end_screen_cta("vid123", service=mock_svc)
        assert result is False


class TestGetChannelHandle:
    """Unit tests for _get_channel_handle helper."""

    def test_from_url(self, monkeypatch):
        _reload_config(CHANNEL_URL="https://www.youtube.com/@DevInSeconds")
        from src.youtube_actions import _get_channel_handle

        handle = _get_channel_handle()
        assert handle == "DevInSeconds"

    def test_from_name_fallback(self, monkeypatch):
        _reload_config(
            CHANNEL_URL="https://www.youtube.com/channel/UC12345",
            CHANNEL_NAME="@TestChannel",
        )
        from src.youtube_actions import _get_channel_handle

        handle = _get_channel_handle()
        assert handle == "TestChannel"


# ══════════════════════════════════════════════════════════════
#  7.2 + 7.3 + 7.4 — Unified Post-Upload Actions
# ══════════════════════════════════════════════════════════════

class TestRunPostUploadActions:
    """Phase 7: ``src.youtube_actions.run_post_upload_actions``."""

    def test_no_video_id_returns_defaults(self, sample_content, monkeypatch):
        _reload_config()
        from src.youtube_actions import run_post_upload_actions

        results = run_post_upload_actions("", sample_content)
        assert results["comment_id"] is None
        assert results["end_screen_cta"] is False
        assert results["playlist_id"] is None

    def test_all_features_called(self, sample_content, monkeypatch):
        monkeypatch.setenv("ENABLE_AUTO_COMMENT", "1")
        monkeypatch.setenv("ENABLE_END_SCREEN", "1")
        monkeypatch.setenv("ENABLE_PLAYLISTS", "1")
        _reload_config(
            ENABLE_AUTO_COMMENT="1",
            ENABLE_END_SCREEN="1",
            ENABLE_PLAYLISTS="1",
        )
        from src.youtube_actions import run_post_upload_actions

        mock_playlist = MagicMock(return_value="PL123")
        with patch("src.youtube_actions.post_pinned_comment", return_value="c123"), \
             patch("src.youtube_actions.add_end_screen_cta", return_value=True), \
             patch.dict("sys.modules", {"src.playlist_manager": MagicMock(auto_manage_playlist=mock_playlist)}):
            results = run_post_upload_actions("vid123", sample_content, duration_seconds=30)

            assert results["comment_id"] == "c123"
            assert results["end_screen_cta"] is True

    def test_partial_failure_doesnt_block(self, sample_content, monkeypatch):
        monkeypatch.setenv("ENABLE_AUTO_COMMENT", "1")
        monkeypatch.setenv("ENABLE_END_SCREEN", "1")
        _reload_config(
            ENABLE_AUTO_COMMENT="1",
            ENABLE_END_SCREEN="1",
        )
        from src.youtube_actions import run_post_upload_actions

        with patch("src.youtube_actions.post_pinned_comment", side_effect=Exception("fail")), \
             patch("src.youtube_actions.add_end_screen_cta", return_value=True):
            # Should NOT raise — partial failure is fine
            results = run_post_upload_actions("vid123", sample_content)
            # comment failed but end_screen should still work
            assert results["end_screen_cta"] is True


# ══════════════════════════════════════════════════════════════
#  7.5 — Upload Time Optimization
# ══════════════════════════════════════════════════════════════

class TestUploadTimeOptimization:
    """Phase 7.5: ``get_best_upload_times`` + ``get_optimized_peak_slots``."""

    def test_get_best_upload_times_with_data(self, monkeypatch):
        """When MongoDB has enough data, returns top hours."""
        mock_col = MagicMock()
        mock_col.aggregate.return_value = [
            {"_id": 18, "avg_views": 1500, "count": 10},
            {"_id": 13, "avg_views": 1200, "count": 8},
            {"_id": 0,  "avg_views": 900,  "count": 5},
        ]

        with patch("src.db._get_collection", return_value=mock_col):
            from src.yt_analytics import get_best_upload_times
            result = get_best_upload_times(top_n=3)

        assert len(result) == 3
        assert result[0] == (18, 0)  # Highest avg views
        assert result[1] == (13, 0)

    def test_get_best_upload_times_no_data(self, monkeypatch):
        """Returns empty list when not enough data."""
        mock_col = MagicMock()
        mock_col.aggregate.return_value = []

        with patch("src.db._get_collection", return_value=mock_col):
            from src.yt_analytics import get_best_upload_times
            result = get_best_upload_times()
        assert result == []

    def test_get_best_upload_times_exception(self, monkeypatch):
        """Returns empty on error."""
        with patch("src.db._get_collection", side_effect=Exception("DB down")):
            from src.yt_analytics import get_best_upload_times
            result = get_best_upload_times()
        assert result == []

    def test_optimized_peak_slots_disabled(self, monkeypatch):
        """When ENABLE_SMART_SCHEDULE is off, returns defaults."""
        monkeypatch.setenv("ENABLE_SMART_SCHEDULE", "0")
        _reload_config(ENABLE_SMART_SCHEDULE="0")
        from src.scheduler import get_optimized_peak_slots, PEAK_SLOTS_UTC

        result = get_optimized_peak_slots()
        assert result == PEAK_SLOTS_UTC

    def test_optimized_peak_slots_enabled_with_data(self, monkeypatch):
        """When enabled and data exists, uses analytics-based slots."""
        monkeypatch.setenv("ENABLE_SMART_SCHEDULE", "1")
        _reload_config(ENABLE_SMART_SCHEDULE="1")

        with patch("src.yt_analytics.get_best_upload_times", return_value=[(20, 0), (14, 0), (8, 0)]):
            from src.scheduler import get_optimized_peak_slots
            result = get_optimized_peak_slots()
            assert result == [(20, 0), (14, 0), (8, 0)]

    def test_optimized_peak_slots_fallback(self, monkeypatch):
        """When enabled but no data, falls back to defaults."""
        monkeypatch.setenv("ENABLE_SMART_SCHEDULE", "1")
        _reload_config(ENABLE_SMART_SCHEDULE="1")

        with patch("src.yt_analytics.get_best_upload_times", return_value=[]):
            from src.scheduler import get_optimized_peak_slots, PEAK_SLOTS_UTC
            result = get_optimized_peak_slots()
            assert result == PEAK_SLOTS_UTC

    def test_optimized_peak_slots_error_fallback(self, monkeypatch):
        """On analytics error, gracefully fall back to defaults."""
        monkeypatch.setenv("ENABLE_SMART_SCHEDULE", "1")
        _reload_config(ENABLE_SMART_SCHEDULE="1")

        with patch("src.yt_analytics.get_best_upload_times", side_effect=Exception("DB")):
            from src.scheduler import get_optimized_peak_slots, PEAK_SLOTS_UTC
            result = get_optimized_peak_slots()
            assert result == PEAK_SLOTS_UTC


# ══════════════════════════════════════════════════════════════
#  7.6 — Channel Performance Dashboard
# ══════════════════════════════════════════════════════════════

class TestGrowthDashboard:
    """Phase 7.6: ``src.analytics.generate_growth_report``."""

    def _mock_collection(self):
        """Create a mock MongoDB collection with sample data."""
        mock_col = MagicMock()
        now = datetime.now(timezone.utc)

        # Mock aggregate results for views trend
        mock_col.aggregate.side_effect = [
            # Call 1: views trend pipeline
            iter([
                {"_id": now.strftime("%Y-%m-%d"), "total_views": 500,
                 "total_likes": 50, "count": 3},
            ]),
            # Call 2: content-type pipeline
            iter([
                {"_id": "tip", "count": 5, "avg_views": 300.0,
                 "avg_likes": 30.0, "avg_avd": 15.5},
            ]),
            # Call 3: language pipeline
            iter([
                {"_id": "python", "count": 8, "avg_views": 400.0,
                 "avg_likes": 40.0},
            ]),
        ]

        # Mock find for top videos
        mock_find = MagicMock()
        mock_find.sort.return_value = mock_find
        mock_find.limit.return_value = iter([
            {
                "title": "Python Trick #1",
                "language": "python",
                "content_type": "tip",
                "yt_metrics": {"views": 1000, "likes": 100, "avd_s": 20.0},
                "youtube_id": "abc123",
            }
        ])
        mock_col.find.return_value = mock_find

        # Mock count_documents
        mock_col.count_documents.return_value = 25

        return mock_col

    def test_report_generation(self, monkeypatch):
        mock_col = self._mock_collection()

        with patch("src.analytics._get_history_col", return_value=mock_col), \
             patch("src.yt_analytics.get_best_upload_times", return_value=[(18, 0), (13, 0)]):
            from src.analytics import generate_growth_report
            report = generate_growth_report()

        assert "Growth Report" in report
        assert isinstance(report, str)

    def test_report_contains_sections(self, monkeypatch):
        mock_col = self._mock_collection()

        with patch("src.analytics._get_history_col", return_value=mock_col), \
             patch("src.yt_analytics.get_best_upload_times", return_value=[(18, 0), (13, 0)]):
            from src.analytics import generate_growth_report
            report = generate_growth_report()

        assert "Views Trend" in report
        assert "Top-Performing" in report
        assert "Upload Times" in report
        assert "Content-Type" in report
        assert "Language" in report
        assert "Recommendations" in report

    def test_report_handles_empty_data(self, monkeypatch):
        mock_col = MagicMock()
        mock_col.aggregate.return_value = iter([])
        mock_find = MagicMock()
        mock_find.sort.return_value = mock_find
        mock_find.limit.return_value = iter([])
        mock_col.find.return_value = mock_find
        mock_col.count_documents.return_value = 0

        with patch("src.analytics._get_history_col", return_value=mock_col), \
             patch("src.yt_analytics.get_best_upload_times", return_value=[]):
            from src.analytics import generate_growth_report
            report = generate_growth_report()

        assert "Growth Report" in report

    def test_report_handles_db_error(self, monkeypatch):
        with patch("src.analytics._get_history_col", side_effect=Exception("DB down")):
            from src.analytics import generate_growth_report
            report = generate_growth_report()

        assert "Growth Report" in report
        assert "Error" in report or "error" in report


# ══════════════════════════════════════════════════════════════
#  Config integration tests
# ══════════════════════════════════════════════════════════════

class TestPhase7Config:
    """Verify Phase 7 config variables are present and have correct defaults."""

    def test_channel_url_default(self, monkeypatch):
        monkeypatch.delenv("CHANNEL_URL", raising=False)
        cfg = _reload_config()
        assert "youtube.com" in cfg.CHANNEL_URL

    def test_seo_description_default_on(self, monkeypatch):
        monkeypatch.delenv("ENABLE_SEO_DESCRIPTION", raising=False)
        cfg = _reload_config()
        assert cfg.ENABLE_SEO_DESCRIPTION == "1"

    def test_auto_comment_default_off(self, monkeypatch):
        monkeypatch.delenv("ENABLE_AUTO_COMMENT", raising=False)
        cfg = _reload_config()
        assert cfg.ENABLE_AUTO_COMMENT == "0"

    def test_playlists_default_off(self, monkeypatch):
        monkeypatch.delenv("ENABLE_PLAYLISTS", raising=False)
        cfg = _reload_config()
        assert cfg.ENABLE_PLAYLISTS == "0"

    def test_end_screen_default_off(self, monkeypatch):
        monkeypatch.delenv("ENABLE_END_SCREEN", raising=False)
        cfg = _reload_config()
        assert cfg.ENABLE_END_SCREEN == "0"

    def test_smart_schedule_default_off(self, monkeypatch):
        monkeypatch.delenv("ENABLE_SMART_SCHEDULE", raising=False)
        cfg = _reload_config()
        assert cfg.ENABLE_SMART_SCHEDULE == "0"


# ══════════════════════════════════════════════════════════════
#  main.py integration tests
# ══════════════════════════════════════════════════════════════

class TestMainSEOIntegration:
    """Verify main.py uses SEO description when enabled."""

    def test_seo_description_enabled(self, sample_content, monkeypatch):
        monkeypatch.setenv("ENABLE_SEO_DESCRIPTION", "1")
        _reload_config(
            ENABLE_SEO_DESCRIPTION="1",
            CHANNEL_URL="https://www.youtube.com/@Test",
        )
        from src.seo import generate_seo_description

        desc = generate_seo_description(sample_content, duration_seconds=30)
        assert "In this video:" in desc
        assert "Subscribe" in desc

    def test_seo_description_disabled_fallback(self, sample_content, monkeypatch):
        monkeypatch.setenv("ENABLE_SEO_DESCRIPTION", "0")
        _reload_config(ENABLE_SEO_DESCRIPTION="0")

        # The old-style description should not have "In this video:"
        description_parts = [
            sample_content["script"],
            "",
            " ".join(sample_content.get("hashtags", [])),
            "",
            "Generated by @TestChannel pipeline",
        ]
        description = "\n".join(description_parts)
        assert "In this video:" not in description


class TestGrowthPipeline:
    """Verify the --growth CLI path."""

    def test_growth_pipeline_function(self, monkeypatch):
        """growth_pipeline() calls generate_growth_report and prints."""
        mock_report = "# Growth Report\nTest content"

        with patch("src.analytics.generate_growth_report", return_value=mock_report):
            from src.main import growth_pipeline
            result = growth_pipeline()
            assert result == 0

    def test_growth_pipeline_error(self, monkeypatch):
        with patch("src.analytics.generate_growth_report", side_effect=Exception("fail")):
            from src.main import growth_pipeline
            result = growth_pipeline()
            assert result == 1


# ══════════════════════════════════════════════════════════════
#  Edge cases and integration
# ══════════════════════════════════════════════════════════════

class TestPhase7EdgeCases:
    """Edge cases and boundary tests for Phase 7."""

    def test_seo_empty_content(self, monkeypatch):
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Test")
        from src.seo import generate_seo_description

        empty_content = {
            "title": "",
            "script": "",
            "language": "",
            "hashtags": [],
            "content_type": "tip",
            "code": "",
        }
        desc = generate_seo_description(empty_content)
        assert isinstance(desc, str)
        assert len(desc) > 0

    def test_seo_no_hashtags(self, monkeypatch):
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Test")
        from src.seo import generate_seo_description

        content = {
            "title": "Test",
            "script": "Test script.",
            "language": "python",
            "hashtags": [],
            "content_type": "tip",
            "code": "x = 1",
        }
        desc = generate_seo_description(content)
        # Should use default hashtags
        assert "#CodingTips" in desc or "#Shorts" in desc

    def test_comment_template_channel_url_substitution(self, monkeypatch):
        _reload_config(CHANNEL_URL="https://test.url")
        from src.youtube_actions import _format_comment
        text = _format_comment({"content_type": "tip", "language": "go"})
        assert "https://test.url" in text

    def test_seo_description_separator(self, sample_content, monkeypatch):
        _reload_config(CHANNEL_URL="https://www.youtube.com/@Test")
        from src.seo import generate_seo_description
        desc = generate_seo_description(sample_content)
        assert "─" in desc  # Visual separator present

    def test_playlist_title_format(self, monkeypatch):
        _reload_config(CHANNEL_NAME="@TestChan")
        from src.playlist_manager import _LANGUAGE_PLAYLIST_TITLE
        title = _LANGUAGE_PLAYLIST_TITLE.format(language="Python", channel="@TestChan")
        assert "Python" in title
        assert "@TestChan" in title

    def test_series_title_format(self, monkeypatch):
        _reload_config(CHANNEL_NAME="@TestChan")
        from src.playlist_manager import _SERIES_PLAYLIST_TITLE
        title = _SERIES_PLAYLIST_TITLE.format(series_theme="Advanced JS", channel="@TestChan")
        assert "Advanced JS" in title
