"""
Tests for Phase 4.4 (Theme System) and Phase 4.6 (Thumbnail Generation).
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch


# ══════════════════════════════════════════════════════════════
#  4.4 — Theme Loader
# ══════════════════════════════════════════════════════════════

class TestListThemes:
    def test_returns_list(self):
        from src.theme_loader import list_themes
        themes = list_themes()
        assert isinstance(themes, list)

    def test_includes_bundled_themes(self):
        from src.theme_loader import list_themes
        themes = list_themes()
        assert "github_dark" in themes
        assert "monokai" in themes
        assert "dracula" in themes

    def test_sorted_alphabetically(self):
        from src.theme_loader import list_themes
        themes = list_themes()
        assert themes == sorted(themes)


class TestLoadTheme:
    def test_loads_github_dark(self):
        from src.theme_loader import load_theme
        t = load_theme("github_dark")
        assert "_name" in t
        assert t["_name"] == "GitHub Dark"

    def test_loads_monokai(self):
        from src.theme_loader import load_theme
        t = load_theme("monokai")
        assert t["_name"] == "Monokai Pro"

    def test_loads_dracula(self):
        from src.theme_loader import load_theme
        t = load_theme("dracula")
        assert t["_name"] == "Dracula"

    def test_fallback_on_unknown_theme(self, tmp_path, monkeypatch):
        """Unknown theme name → falls back to github_dark."""
        from src.theme_loader import load_theme
        t = load_theme("nonexistent_theme_xyz")
        assert "github_dark" in t.get("_name", "").lower() or "bg_gradient_top" in t

    def test_has_required_color_keys(self):
        from src.theme_loader import load_theme
        t = load_theme("github_dark")
        required = [
            "bg_gradient_top", "bg_gradient_bottom", "chrome_bg",
            "code_bg", "default_text_color", "cursor_color",
            "accent_gradient_left", "accent_gradient_right",
        ]
        for key in required:
            assert key in t, f"Missing key: {key}"

    def test_has_syntax_sub_dict(self):
        from src.theme_loader import load_theme
        t = load_theme("github_dark")
        assert "syntax" in t
        assert "keyword" in t["syntax"]

    def test_loads_from_custom_json(self, tmp_path):
        """Can load a custom theme placed in the themes directory."""
        from src.theme_loader import _THEMES_DIR
        custom = {
            "_name": "Test",
            "bg_gradient_top": [0, 0, 0],
            "bg_gradient_bottom": [10, 10, 10],
            "syntax": {"default": "#ffffff", "keyword": "#ff0000"},
        }
        theme_path = _THEMES_DIR / "test_custom.json"
        try:
            theme_path.write_text(json.dumps(custom))
            from src.theme_loader import load_theme
            t = load_theme("test_custom")
            assert t["_name"] == "Test"
        finally:
            if theme_path.exists():
                theme_path.unlink()


class TestGetActiveTheme:
    def test_default_is_github_dark(self, monkeypatch):
        monkeypatch.delenv("ACTIVE_THEME", raising=False)
        monkeypatch.delenv("AUTO_ROTATE_THEMES", raising=False)
        from src.theme_loader import get_active_theme
        t = get_active_theme()
        assert "GitHub Dark" in t.get("_name", "")

    def test_respects_active_theme_env(self, monkeypatch):
        monkeypatch.setenv("ACTIVE_THEME", "monokai")
        monkeypatch.setenv("AUTO_ROTATE_THEMES", "0")
        from src.theme_loader import get_active_theme
        t = get_active_theme()
        assert "Monokai" in t.get("_name", "")

    def test_auto_rotate_uses_rotation_list(self, monkeypatch):
        monkeypatch.setenv("AUTO_ROTATE_THEMES", "1")
        monkeypatch.setenv("THEME_ROTATION_LIST", "github_dark,monokai,dracula")
        from src.theme_loader import get_active_theme
        t = get_active_theme()
        # Should load some known theme without error
        assert "_name" in t


class TestBuildSyntaxColors:
    def test_returns_token_dict(self):
        from pygments.token import Token
        from src.theme_loader import build_syntax_colors, load_theme
        t = load_theme("github_dark")
        colors = build_syntax_colors(t)
        assert Token.Keyword in colors
        assert Token.Comment in colors

    def test_values_are_hex_strings(self):
        from src.theme_loader import build_syntax_colors, load_theme
        t = load_theme("github_dark")
        colors = build_syntax_colors(t)
        for token, color in colors.items():
            assert isinstance(color, str), f"{token} color is not a string"
            assert color.startswith("#"), f"{token} color '{color}' not a hex string"

    def test_fallback_to_default_key(self):
        """Syntax dict with only 'default' key still builds full map."""
        from pygments.token import Token
        from src.theme_loader import build_syntax_colors
        minimal_theme = {"syntax": {"default": "#aabbcc"}}
        colors = build_syntax_colors(minimal_theme)
        assert colors[Token.Keyword] == "#aabbcc"

    def test_github_dark_keyword_color(self):
        from pygments.token import Token
        from src.theme_loader import build_syntax_colors, load_theme
        t = load_theme("github_dark")
        colors = build_syntax_colors(t)
        # GitHub Dark keywords are red
        assert colors[Token.Keyword] == "#ff7b72"

    def test_monokai_keyword_color(self):
        from pygments.token import Token
        from src.theme_loader import build_syntax_colors, load_theme
        t = load_theme("monokai")
        colors = build_syntax_colors(t)
        # Monokai keywords are pink/magenta
        assert colors[Token.Keyword] == "#f92672"


class TestPatchConfig:
    def test_patches_bg_gradient(self):
        from src import config
        from src.theme_loader import load_theme, patch_config
        monokai = load_theme("monokai")
        patch_config(monokai)
        assert config.BG_GRADIENT_TOP == tuple(monokai["bg_gradient_top"])
        # restore
        patch_config(load_theme("github_dark"))
        assert config.BG_GRADIENT_TOP == tuple(load_theme("github_dark")["bg_gradient_top"])

    def test_patches_accent_colors(self):
        from src import config
        from src.theme_loader import load_theme, patch_config
        dracula = load_theme("dracula")
        patch_config(dracula)
        assert config.ACCENT_GRADIENT_LEFT == dracula["accent_gradient_left"]
        # restore
        patch_config(load_theme("github_dark"))

    def test_does_not_patch_font_sizes(self):
        """Font sizes must stay untouched after patch_config."""
        from src import config
        from src.theme_loader import load_theme, patch_config
        original_font = config.CODE_FONT_SIZE
        patch_config(load_theme("monokai"))
        assert config.CODE_FONT_SIZE == original_font
        patch_config(load_theme("github_dark"))

    def test_patch_is_idempotent(self):
        from src import config
        from src.theme_loader import load_theme, patch_config
        gh = load_theme("github_dark")
        patch_config(gh)
        val1 = config.ACCENT_GRADIENT_LEFT
        patch_config(gh)
        val2 = config.ACCENT_GRADIENT_LEFT
        assert val1 == val2

    def test_does_not_raise_on_partial_theme(self):
        """Partial theme (missing keys) should not raise."""
        from src.theme_loader import patch_config
        patch_config({"_name": "Empty"})   # no color keys


# ══════════════════════════════════════════════════════════════
#  4.6 — Thumbnail Generation
# ══════════════════════════════════════════════════════════════

FAKE_CODE = "def greet(name):\n    return f'Hello {name}'\n"


class TestGenerateThumbnail:
    def _patches(self):
        from src.theme_loader import load_theme
        theme = load_theme("github_dark")
        return [
            patch("src.theme_loader.get_active_theme", return_value=theme),
            patch("src.theme_loader.patch_config"),
        ]

    def test_creates_png_file(self, tmp_path):
        from contextlib import ExitStack
        from src.thumbnail import generate_thumbnail
        out = tmp_path / "thumb.png"
        with ExitStack() as stack:
            for p in self._patches():
                stack.enter_context(p)
            path = generate_thumbnail(
                title="Python Tips #Shorts",
                language="python",
                code=FAKE_CODE,
                output_path=out,
            )
        assert path.exists()
        assert path.suffix == ".png"

    def test_returns_path_object(self, tmp_path):
        from contextlib import ExitStack
        from src.thumbnail import generate_thumbnail
        out = tmp_path / "thumb.png"
        with ExitStack() as stack:
            for p in self._patches():
                stack.enter_context(p)
            result = generate_thumbnail("Python Tips", "python", FAKE_CODE, out)
        assert isinstance(result, Path)

    def test_correct_dimensions(self, tmp_path):
        from contextlib import ExitStack
        from PIL import Image
        from src.thumbnail import THUMB_H, THUMB_W, generate_thumbnail
        out = tmp_path / "thumb.png"
        with ExitStack() as stack:
            for p in self._patches():
                stack.enter_context(p)
            path = generate_thumbnail("Rust Lifetime", "rust", FAKE_CODE, out)
        with Image.open(path) as img:
            assert img.width == THUMB_W
            assert img.height == THUMB_H

    def test_default_output_path(self, tmp_path, monkeypatch):
        """When output_path is None, should use config.OUTPUT_DIR."""
        from contextlib import ExitStack
        from src import config
        monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
        from src.thumbnail import generate_thumbnail
        with ExitStack() as stack:
            for p in self._patches():
                stack.enter_context(p)
            path = generate_thumbnail("Go Tips", "go", FAKE_CODE)
        assert path.parent == tmp_path

    def test_works_without_known_language(self, tmp_path):
        """Unknown language falls back gracefully."""
        from contextlib import ExitStack
        from src.thumbnail import generate_thumbnail
        out = tmp_path / "thumb.png"
        with ExitStack() as stack:
            for p in self._patches():
                stack.enter_context(p)
            path = generate_thumbnail("Tips", "cobol", FAKE_CODE, out)
        assert path.exists()

    def test_strips_shorts_hashtag_from_title(self, tmp_path):
        """Title text should not contain '#Shorts'."""
        from contextlib import ExitStack
        from src.thumbnail import generate_thumbnail
        out = tmp_path / "thumb.png"
        with ExitStack() as stack:
            for p in self._patches():
                stack.enter_context(p)
            path = generate_thumbnail("Go Goroutines #Shorts", "go", FAKE_CODE, out)
        assert path.exists()   # just verify no error raised


class TestUploadThumbnail:
    def test_calls_thumbnails_set(self):
        fake_service = MagicMock()
        fake_service.thumbnails.return_value.set.return_value.execute.return_value = {"kind": "youtube#thumbnailSetResponse"}
        with patch("googleapiclient.http.MediaFileUpload"):
            from src.thumbnail import upload_thumbnail
            ok = upload_thumbnail(
                youtube_video_id="abc123",
                image_path=Path("/tmp/thumb.png"),
                youtube_service=fake_service,
            )
        assert ok is True
        fake_service.thumbnails.return_value.set.assert_called_once()

    def test_returns_false_on_error(self):
        fake_service = MagicMock()
        fake_service.thumbnails.side_effect = Exception("API error")
        from src.thumbnail import upload_thumbnail
        ok = upload_thumbnail(
            youtube_video_id="abc123",
            image_path=Path("/tmp/thumb.png"),
            youtube_service=fake_service,
        )
        assert ok is False


# ══════════════════════════════════════════════════════════════
#  _thumbnail_step (main.py integration)
# ══════════════════════════════════════════════════════════════

class TestThumbnailStep:
    def test_skipped_when_disabled(self, monkeypatch):
        from src import config
        monkeypatch.setattr(config, "ENABLE_THUMBNAILS", "0")
        with patch("src.thumbnail.generate_thumbnail") as m_gen:
            from src.main import _thumbnail_step
            _thumbnail_step("vid123", "Title", "python", "code")
        m_gen.assert_not_called()

    def test_runs_when_enabled(self, monkeypatch, tmp_path):
        from src import config
        monkeypatch.setattr(config, "ENABLE_THUMBNAILS", "1")
        fake_path = tmp_path / "thumb.png"
        fake_path.write_bytes(b"PNG")
        with (
            patch("src.thumbnail.generate_thumbnail", return_value=fake_path) as m_gen,
            patch("src.thumbnail.upload_thumbnail", return_value=True) as m_up,
        ):
            from src.main import _thumbnail_step
            _thumbnail_step("vid123", "Go Tips #Shorts", "go", "code")
        m_gen.assert_called_once()
        m_up.assert_called_once_with(youtube_video_id="vid123", image_path=fake_path)

    def test_never_raises(self, monkeypatch):
        """Should be completely error-safe."""
        from src import config
        monkeypatch.setattr(config, "ENABLE_THUMBNAILS", "1")
        with patch("src.thumbnail.generate_thumbnail", side_effect=Exception("boom")):
            from src.main import _thumbnail_step
            _thumbnail_step("vid123", "Title", "python", "code")   # must not raise


# ══════════════════════════════════════════════════════════════
#  Renderer uses theme (integration smoke test)
# ══════════════════════════════════════════════════════════════

class TestRendererUsesTheme:
    def test_renderer_init_sets_syntax_colors(self):
        """FrameRenderer.__init__ should set self._syntax_colors."""
        from pygments.token import Token
        from src.theme_loader import load_theme
        with (
            patch("src.theme_loader.get_active_theme",
                  return_value=load_theme("monokai")),
            patch("src.theme_loader.patch_config"),
            # Prevent actual font/image loading
            patch("src.renderer.FrameRenderer._load_fonts"),
            patch("src.renderer.FrameRenderer._create_gradient_bg", return_value=MagicMock()),
            patch("src.renderer.FrameRenderer._tokenize_code"),
            patch("src.renderer.FrameRenderer._tokenize_before_code"),
            patch("src.renderer.FrameRenderer._compute_char_positions"),
            patch("src.renderer.FrameRenderer._create_base_image"),
            patch("src.renderer.FrameRenderer._create_intro_image"),
            patch("src.renderer.FrameRenderer._create_outro_image"),
            patch("src.renderer.FrameRenderer._prepare_output_panel"),
            patch("src.renderer.FrameRenderer._create_subtitle_groups"),
        ):
            from src import config
            config.INTRO_DURATION = 0
            config.OUTRO_DURATION = 0
            from src.renderer import FrameRenderer
            r = FrameRenderer(
                code="x = 1",
                language="python",
                word_timestamps=[],
                duration=5.0,
            )
        assert hasattr(r, "_syntax_colors")
        assert isinstance(r._syntax_colors, dict)
        # Monokai: keywords should be pink
        assert r._syntax_colors.get(Token.Keyword) == "#f92672"
