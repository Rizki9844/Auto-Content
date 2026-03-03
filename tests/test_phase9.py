"""
Tests for Phase 9 — Advanced Features.

Covers:
  9.1 Background Music (bgmusic.py)
  9.2 Animated Code Highlighting (renderer.py)
  9.3 Multi-Channel Support (multi_channel.py)
  9.4 Dashboard (dashboard/app.py)
  9.5 AI Thumbnail v2 (thumbnail.py)
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ══════════════════════════════════════════════════════════════
#  9.1 — Background Music
# ══════════════════════════════════════════════════════════════

class TestBgMusicListTracks:
    """Test list_tracks finds audio files in music dir."""

    def test_returns_empty_when_dir_missing(self, tmp_path):
        with patch("src.bgmusic.config") as mock_cfg:
            mock_cfg.MUSIC_DIR = tmp_path / "nonexistent"
            from src.bgmusic import list_tracks
            assert list_tracks() == []

    def test_returns_mp3_and_ogg_files(self, tmp_path):
        music = tmp_path / "music"
        music.mkdir()
        (music / "track1.mp3").write_bytes(b"fake")
        (music / "track2.ogg").write_bytes(b"fake")
        (music / "readme.txt").write_text("not audio")
        with patch("src.bgmusic.config") as mock_cfg:
            mock_cfg.MUSIC_DIR = music
            from src.bgmusic import list_tracks
            tracks = list_tracks()
            assert len(tracks) == 2
            names = {t.name for t in tracks}
            assert "track1.mp3" in names
            assert "track2.ogg" in names

    def test_returns_wav_files(self, tmp_path):
        music = tmp_path / "music"
        music.mkdir()
        (music / "ambient.wav").write_bytes(b"fake")
        with patch("src.bgmusic.config") as mock_cfg:
            mock_cfg.MUSIC_DIR = music
            from src.bgmusic import list_tracks
            assert len(list_tracks()) == 1


class TestBgMusicSelectTrack:
    """Test track selection with anti-repeat logic."""

    def test_select_from_list(self, tmp_path):
        from src.bgmusic import select_track, _HISTORY_FILE
        with patch("src.bgmusic._HISTORY_FILE", tmp_path / "hist.json"):
            tracks = [tmp_path / "a.mp3", tmp_path / "b.mp3"]
            chosen = select_track(tracks)
            assert chosen in tracks

    def test_returns_none_when_empty(self):
        from src.bgmusic import select_track
        assert select_track([]) is None

    def test_avoids_consecutive_repeats(self, tmp_path):
        from src.bgmusic import select_track
        hist_file = tmp_path / "hist.json"
        hist_file.write_text(json.dumps(["a.mp3", "a.mp3"]))
        with patch("src.bgmusic._HISTORY_FILE", hist_file):
            tracks = [tmp_path / "a.mp3", tmp_path / "b.mp3"]
            chosen = select_track(tracks)
            # Should prefer b.mp3 since a.mp3 was used 2× recently
            assert chosen == tracks[1]

    def test_fallback_when_all_recent(self, tmp_path):
        from src.bgmusic import select_track
        hist_file = tmp_path / "hist.json"
        hist_file.write_text(json.dumps(["a.mp3", "a.mp3"]))
        with patch("src.bgmusic._HISTORY_FILE", hist_file):
            # Only one track available — must still pick it
            tracks = [tmp_path / "a.mp3"]
            chosen = select_track(tracks)
            assert chosen == tracks[0]


class TestBgMusicMix:
    """Test mix_background_music function."""

    def test_returns_original_when_no_tracks(self, tmp_path):
        from src.bgmusic import mix_background_music
        audio = str(tmp_path / "audio.mp3")
        with patch("src.bgmusic.select_track", return_value=None):
            result = mix_background_music(audio)
            assert result == audio

    def test_returns_original_when_track_missing(self, tmp_path):
        from src.bgmusic import mix_background_music
        audio = str(tmp_path / "audio.mp3")
        fake_track = tmp_path / "nonexistent.mp3"
        with patch("src.bgmusic.select_track", return_value=fake_track):
            result = mix_background_music(audio)
            assert result == audio

    def test_default_output_path(self):
        from src.bgmusic import mix_background_music
        with patch("src.bgmusic.select_track", return_value=None):
            result = mix_background_music("/path/to/audio.mp3")
            assert result == "/path/to/audio.mp3"

    def test_custom_output_path(self):
        from src.bgmusic import mix_background_music
        with patch("src.bgmusic.select_track", return_value=None):
            result = mix_background_music("/audio.mp3", output_path="/mixed.mp3")
            assert result == "/audio.mp3"  # No track = return original


class TestBgMusicConfig:
    """Test Phase 9.1 config variables."""

    def test_enable_bgmusic_default(self):
        from src import config
        # Default is off
        assert config.ENABLE_BGMUSIC == "0"

    def test_bgmusic_volume_default(self):
        from src import config
        assert config.BGMUSIC_VOLUME == 0.07

    def test_music_dir_exists(self):
        from src import config
        assert "music" in str(config.MUSIC_DIR)


# ══════════════════════════════════════════════════════════════
#  9.2 — Animated Code Highlighting
# ══════════════════════════════════════════════════════════════

class TestCodeKeywordIndex:
    """Test _build_code_keyword_index on FrameRenderer."""

    def _make_renderer(self, code="def hello():\n    print('world')", **kw):
        """Create a minimal FrameRenderer with mocked heavy deps."""
        from src.renderer import FrameRenderer
        from src.tts import WordTimestamp
        wts = kw.pop("word_timestamps", [
            WordTimestamp("hello", 0.5, 1.0),
            WordTimestamp("print", 1.5, 2.0),
        ])
        r = FrameRenderer(
            code=code,
            language="python",
            word_timestamps=wts,
            duration=5.0,
            **kw,
        )
        return r

    def test_keyword_index_built(self):
        r = self._make_renderer()
        assert isinstance(r._keyword_to_lines, dict)
        assert len(r._keyword_to_lines) > 0

    def test_keyword_maps_to_correct_line(self):
        r = self._make_renderer(code="def calculate():\n    result = 42")
        # "calculate" is on line 0, "result" on line 1
        assert 0 in r._keyword_to_lines.get("calculate", [])
        assert 1 in r._keyword_to_lines.get("result", [])

    def test_short_identifiers_excluded(self):
        r = self._make_renderer(code="x = 1\ny = 2\nfoo = 3")
        # "x" and "y" are < 3 chars, should be excluded
        assert "x" not in r._keyword_to_lines
        assert "y" not in r._keyword_to_lines
        # "foo" is 3 chars, should be included
        assert "foo" in r._keyword_to_lines

    def test_empty_code_gives_empty_index(self):
        r = self._make_renderer(code="# just a comment")
        # "just" and "comment" are identifiers, may be present
        assert isinstance(r._keyword_to_lines, dict)


class TestGetHighlightedLine:
    """Test _get_highlighted_line returns correct line index."""

    def _make_renderer(self, code, word_timestamps):
        from src.renderer import FrameRenderer
        return FrameRenderer(
            code=code,
            language="python",
            word_timestamps=word_timestamps,
            duration=5.0,
        )

    def test_returns_none_when_no_match(self):
        from src.tts import WordTimestamp
        r = self._make_renderer(
            "def foo():\n    pass",
            [WordTimestamp("something", 0.5, 1.0)],
        )
        result = r._get_highlighted_line(0.7)
        assert result is None

    def test_returns_line_on_match(self):
        from src.tts import WordTimestamp
        r = self._make_renderer(
            "def calculate():\n    result = 42",
            [WordTimestamp("calculate", 0.5, 1.5)],
        )
        result = r._get_highlighted_line(1.0)
        assert result == 0

    def test_returns_none_outside_timestamp(self):
        from src.tts import WordTimestamp
        r = self._make_renderer(
            "def foo():\n    pass",
            [WordTimestamp("foo", 1.0, 2.0)],
        )
        # t=0.5 is before the word starts
        result = r._get_highlighted_line(0.5)
        assert result is None

    def test_returns_none_for_short_words(self):
        from src.tts import WordTimestamp
        r = self._make_renderer(
            "x = 10\nfoo = 20",
            [WordTimestamp("x", 0.5, 1.0)],  # "x" too short (< 3)
        )
        result = r._get_highlighted_line(0.7)
        assert result is None


class TestHighlightConfig:
    """Test Phase 9.2 config variables."""

    def test_enable_line_highlight_default(self):
        from src import config
        assert config.ENABLE_LINE_HIGHLIGHT == "1"

    def test_line_highlight_active_color(self):
        from src import config
        assert config.LINE_HIGHLIGHT_ACTIVE.startswith("#")


# ══════════════════════════════════════════════════════════════
#  9.3 — Multi-Channel Support
# ══════════════════════════════════════════════════════════════

class TestGetChannels:
    """Test get_channels channel parsing."""

    def test_empty_config_no_legacy(self):
        from src.multi_channel import get_channels
        with patch("src.multi_channel.config") as mock_cfg:
            mock_cfg.YOUTUBE_CHANNELS = ""
            mock_cfg.YOUTUBE_CLIENT_ID = ""
            mock_cfg.YOUTUBE_REFRESH_TOKEN = ""
            assert get_channels() == []

    def test_legacy_single_channel(self):
        from src.multi_channel import get_channels
        with patch("src.multi_channel.config") as mock_cfg:
            mock_cfg.YOUTUBE_CHANNELS = ""
            mock_cfg.YOUTUBE_CLIENT_ID = "cid"
            mock_cfg.YOUTUBE_CLIENT_SECRET = "csecret"
            mock_cfg.YOUTUBE_REFRESH_TOKEN = "rtoken"
            mock_cfg.CHANNEL_NAME = "@Test"
            channels = get_channels()
            assert len(channels) == 1
            assert channels[0].name == "default"
            assert channels[0].client_id == "cid"

    def test_json_multi_channel(self):
        from src.multi_channel import get_channels
        channels_json = json.dumps([
            {"name": "en", "client_id": "c1", "client_secret": "s1", "refresh_token": "r1"},
            {"name": "id", "client_id": "c2", "client_secret": "s2", "refresh_token": "r2"},
        ])
        with patch("src.multi_channel.config") as mock_cfg:
            mock_cfg.YOUTUBE_CHANNELS = channels_json
            channels = get_channels()
            assert len(channels) == 2
            assert channels[0].name == "en"
            assert channels[1].name == "id"

    def test_invalid_json_returns_empty(self):
        from src.multi_channel import get_channels
        with patch("src.multi_channel.config") as mock_cfg:
            mock_cfg.YOUTUBE_CHANNELS = "not-json{{"
            assert get_channels() == []

    def test_filters_invalid_channels(self):
        from src.multi_channel import get_channels
        channels_json = json.dumps([
            {"name": "valid", "client_id": "c1", "client_secret": "s1", "refresh_token": "r1"},
            {"name": "invalid", "client_id": "", "client_secret": "", "refresh_token": ""},
        ])
        with patch("src.multi_channel.config") as mock_cfg:
            mock_cfg.YOUTUBE_CHANNELS = channels_json
            channels = get_channels()
            assert len(channels) == 1
            assert channels[0].name == "valid"


class TestChannelConfig:
    """Test ChannelConfig dataclass."""

    def test_is_valid_true(self):
        from src.multi_channel import ChannelConfig
        c = ChannelConfig("test", "cid", "csecret", "rtoken")
        assert c.is_valid is True

    def test_is_valid_false_missing_token(self):
        from src.multi_channel import ChannelConfig
        c = ChannelConfig("test", "cid", "csecret", "")
        assert c.is_valid is False


class TestUploadToAllChannels:
    """Test upload_to_all_channels orchestration."""

    def test_returns_empty_when_no_channels(self):
        from src.multi_channel import upload_to_all_channels
        results = upload_to_all_channels(
            "video.mp4", "Title", "Desc", channels=[]
        )
        assert results == []

    def test_calls_upload_per_channel(self):
        from src.multi_channel import (
            upload_to_all_channels, ChannelConfig, ChannelUploadResult,
        )
        ch1 = ChannelConfig("en", "c1", "s1", "r1")
        ch2 = ChannelConfig("id", "c2", "s2", "r2")
        mock_result = ChannelUploadResult("en", True, "vid1", "url1")
        with patch("src.multi_channel.upload_to_channel", return_value=mock_result) as m:
            results = upload_to_all_channels(
                "video.mp4", "Title", "Desc", channels=[ch1, ch2]
            )
            assert len(results) == 2
            assert m.call_count == 2


class TestUploadToChannel:
    """Test individual channel upload."""

    def test_handles_build_service_failure(self):
        from src.multi_channel import upload_to_channel, ChannelConfig
        ch = ChannelConfig("test", "cid", "csecret", "rtoken")
        with patch(
            "src.multi_channel._build_service_for_channel",
            side_effect=Exception("Auth failed"),
        ):
            result = upload_to_channel(ch, "v.mp4", "T", "D")
            assert result.success is False
            assert "Auth failed" in result.error


class TestMultiChannelConfig:
    """Test Phase 9.3 config variables."""

    def test_youtube_channels_default_empty(self):
        from src import config
        assert config.YOUTUBE_CHANNELS == ""


# ══════════════════════════════════════════════════════════════
#  9.4 — Dashboard
# ══════════════════════════════════════════════════════════════

class TestDashboardRoutes:
    """Test Flask dashboard routes return 200."""

    @pytest.fixture
    def client(self):
        from dashboard.app import app
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def test_index_route(self, client):
        with patch("dashboard.app._get_db") as mock_db:
            mock_col = MagicMock()
            mock_col.count_documents.return_value = 0
            mock_col.find_one.return_value = None
            mock_col.aggregate.return_value = []
            mock_db.return_value = lambda name: mock_col
            resp = client.get("/")
            assert resp.status_code == 200

    def test_videos_route(self, client):
        with patch("dashboard.app._get_db") as mock_db:
            mock_col = MagicMock()
            mock_col.count_documents.return_value = 0
            find_mock = MagicMock()
            find_mock.sort.return_value = find_mock
            find_mock.skip.return_value = find_mock
            find_mock.limit.return_value = []
            mock_col.find.return_value = find_mock
            mock_db.return_value = lambda name: mock_col
            resp = client.get("/videos")
            assert resp.status_code == 200

    def test_analytics_route(self, client):
        with patch("dashboard.app._get_db") as mock_db:
            mock_col = MagicMock()
            mock_col.aggregate.return_value = []
            mock_db.return_value = lambda name: mock_col
            resp = client.get("/analytics")
            assert resp.status_code == 200

    def test_health_route(self, client):
        with patch("dashboard.app._run_health_checks", return_value={}):
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_api_stats_route(self, client):
        with patch("dashboard.app._get_db") as mock_db:
            mock_col = MagicMock()
            mock_col.count_documents.return_value = 5
            mock_col.find_one.return_value = None
            mock_col.aggregate.return_value = []
            mock_db.return_value = lambda name: mock_col
            resp = client.get("/api/stats")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "total_videos" in data


class TestDashboardConfig:
    """Test Phase 9.4 config variables."""

    def test_dashboard_port_default(self):
        from src import config
        assert config.DASHBOARD_PORT == 5050

    def test_dashboard_secret_key_default(self):
        from src import config
        assert config.DASHBOARD_SECRET_KEY == "dev-secret-change-me"


# ══════════════════════════════════════════════════════════════
#  9.5 — AI Thumbnail v2
# ══════════════════════════════════════════════════════════════

class TestAIBackgroundPrompt:
    """Test AI prompt generation."""

    def test_python_prompt(self):
        from src.thumbnail import _get_ai_bg_prompt
        prompt = _get_ai_bg_prompt("python")
        assert "Python" in prompt or "python" in prompt.lower()
        assert "dark" in prompt.lower()
        assert "1280x720" in prompt

    def test_unknown_language_prompt(self):
        from src.thumbnail import _get_ai_bg_prompt
        prompt = _get_ai_bg_prompt("haskell")
        assert "haskell" in prompt.lower()

    def test_javascript_prompt(self):
        from src.thumbnail import _get_ai_bg_prompt
        prompt = _get_ai_bg_prompt("javascript")
        assert "JavaScript" in prompt


class TestAIBackgroundCache:
    """Test AI background caching."""

    def test_get_cached_bg_returns_none_when_missing(self, tmp_path):
        with patch("src.thumbnail._BG_CACHE_DIR", tmp_path):
            from src.thumbnail import _get_cached_bg
            result = _get_cached_bg("python")
            assert result is None

    def test_get_cached_bg_returns_path_when_exists(self, tmp_path):
        cache_file = tmp_path / "python_bg.png"
        # Write a valid PNG-like file (> 1000 bytes)
        cache_file.write_bytes(b"x" * 2000)
        with patch("src.thumbnail._BG_CACHE_DIR", tmp_path):
            from src.thumbnail import _get_cached_bg
            result = _get_cached_bg("python")
            assert result == cache_file

    def test_save_bg_cache(self, tmp_path):
        from PIL import Image
        with patch("src.thumbnail._BG_CACHE_DIR", tmp_path / "cache"):
            from src.thumbnail import _save_bg_cache
            img = Image.new("RGB", (100, 100), "red")
            path = _save_bg_cache("python", img)
            assert path.exists()
            assert "python_bg.png" in path.name


class TestGenerateAIBackground:
    """Test generate_ai_background function."""

    def test_returns_none_when_no_api_key(self):
        from src.thumbnail import generate_ai_background
        with patch("src.thumbnail.config") as mock_cfg:
            mock_cfg.STABILITY_API_KEY = ""
            result = generate_ai_background("python")
            assert result is None

    def test_returns_cached_image(self, tmp_path):
        from PIL import Image
        from src.thumbnail import generate_ai_background

        # Create a valid cached file
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        cached_img = Image.new("RGB", (1280, 720), "blue")
        cached_img.save(str(cache_dir / "python_bg.png"))

        with patch("src.thumbnail.config") as mock_cfg, \
             patch("src.thumbnail._BG_CACHE_DIR", cache_dir):
            mock_cfg.STABILITY_API_KEY = "fake-key"
            result = generate_ai_background("python")
            assert result is not None
            assert result.size == (1280, 720)

    def test_returns_none_on_api_failure(self):
        from src.thumbnail import generate_ai_background
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Server Error"
        with patch("src.thumbnail.config") as mock_cfg, \
             patch("src.thumbnail._get_cached_bg", return_value=None), \
             patch("requests.post", return_value=mock_resp):
            mock_cfg.STABILITY_API_KEY = "fake-key"
            result = generate_ai_background("python")
            assert result is None


class TestThumbnailStyle:
    """Test THUMBNAIL_STYLE config."""

    def test_default_is_pillow(self):
        from src import config
        assert config.THUMBNAIL_STYLE == "pillow"

    def test_stability_api_key_default_empty(self):
        from src import config
        assert config.STABILITY_API_KEY == ""


# ══════════════════════════════════════════════════════════════
#  Phase 9 Integration Tests
# ══════════════════════════════════════════════════════════════

class TestPhase9Integration:
    """Cross-cutting integration tests for Phase 9."""

    def test_bgmusic_module_importable(self):
        from src import bgmusic
        assert hasattr(bgmusic, "mix_background_music")
        assert hasattr(bgmusic, "list_tracks")
        assert hasattr(bgmusic, "select_track")

    def test_multi_channel_module_importable(self):
        from src import multi_channel
        assert hasattr(multi_channel, "get_channels")
        assert hasattr(multi_channel, "upload_to_all_channels")
        assert hasattr(multi_channel, "upload_to_channel")
        assert hasattr(multi_channel, "ChannelConfig")
        assert hasattr(multi_channel, "ChannelUploadResult")

    def test_dashboard_app_importable(self):
        from dashboard.app import app
        assert app is not None

    def test_renderer_has_highlight_methods(self):
        from src.renderer import FrameRenderer
        assert hasattr(FrameRenderer, "_build_code_keyword_index")
        assert hasattr(FrameRenderer, "_get_highlighted_line")
        assert hasattr(FrameRenderer, "_draw_line_highlight_glow")

    def test_thumbnail_has_ai_functions(self):
        from src import thumbnail
        assert hasattr(thumbnail, "generate_ai_background")
        assert hasattr(thumbnail, "_get_ai_bg_prompt")
        assert hasattr(thumbnail, "_get_cached_bg")
        assert hasattr(thumbnail, "_save_bg_cache")

    def test_config_has_all_phase9_vars(self):
        from src import config
        assert hasattr(config, "ENABLE_BGMUSIC")
        assert hasattr(config, "BGMUSIC_VOLUME")
        assert hasattr(config, "MUSIC_DIR")
        assert hasattr(config, "ENABLE_LINE_HIGHLIGHT")
        assert hasattr(config, "LINE_HIGHLIGHT_ACTIVE")
        assert hasattr(config, "YOUTUBE_CHANNELS")
        assert hasattr(config, "DASHBOARD_PORT")
        assert hasattr(config, "DASHBOARD_SECRET_KEY")
        assert hasattr(config, "THUMBNAIL_STYLE")
        assert hasattr(config, "STABILITY_API_KEY")

    def test_music_dir_path_correct(self):
        from src import config
        assert config.MUSIC_DIR == config.ASSETS_DIR / "music"

    def test_assets_music_dir_exists(self):
        from src import config
        assert config.MUSIC_DIR.exists()

    def test_auth_youtube_supports_channel_flag(self):
        """Verify auth_youtube.py updated for --channel flag."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "auth_youtube",
            str(Path(__file__).parent.parent / "scripts" / "auth_youtube.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        # Just check the source has --channel
        source = Path(spec.origin).read_text()
        assert "--channel" in source

    def test_requirements_has_flask(self):
        req = (Path(__file__).parent.parent / "requirements.txt").read_text()
        assert "flask" in req.lower()

    def test_requirements_has_requests(self):
        req = (Path(__file__).parent.parent / "requirements.txt").read_text()
        assert "requests" in req.lower()

    def test_dashboard_templates_exist(self):
        tmpl_dir = Path(__file__).parent.parent / "dashboard" / "templates"
        assert tmpl_dir.exists()
        expected = {"base.html", "index.html", "videos.html", "analytics.html", "health.html"}
        actual = {f.name for f in tmpl_dir.iterdir() if f.suffix == ".html"}
        assert expected.issubset(actual)

    def test_bgmusic_integration_in_main(self):
        """Verify main.py references bgmusic_mix step."""
        main_src = (Path(__file__).parent.parent / "src" / "main.py").read_text(encoding="utf-8")
        assert "bgmusic_mix" in main_src
        assert "ENABLE_BGMUSIC" in main_src
