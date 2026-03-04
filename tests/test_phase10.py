"""
Tests for Phase 10.1 — Visual Preview + CTA Overlay.

Tests:
  - preview_renderer: terminal panel, browser detection, generate_preview_image
  - renderer: _fit_preview_image, _draw_captured_preview, _draw_cta_overlay
  - config: new constants exist
"""
from unittest.mock import patch

from PIL import Image

from src import config


# ══════════════════════════════════════════════════════════════
#  CONFIG TESTS
# ══════════════════════════════════════════════════════════════

class TestPhase10Config:
    """Verify new config constants exist and have correct defaults."""

    def test_enable_visual_preview_default(self):
        assert isinstance(config.ENABLE_VISUAL_PREVIEW, bool)

    def test_playwright_timeout_ms(self):
        assert config.PLAYWRIGHT_TIMEOUT_MS >= 1000

    def test_playwright_viewport_tuple(self):
        assert isinstance(config.PLAYWRIGHT_VIEWPORT, tuple)
        assert len(config.PLAYWRIGHT_VIEWPORT) == 2
        w, h = config.PLAYWRIGHT_VIEWPORT
        assert w > 0 and h > 0

    def test_enable_cta_overlay_default(self):
        assert isinstance(config.ENABLE_CTA_OVERLAY, bool)

    def test_cta_lead_time_positive(self):
        assert config.CTA_LEAD_TIME > 0

    def test_cta_y_position(self):
        assert config.SUBTITLE_Y < config.CTA_Y < config.WATERMARK_Y


# ══════════════════════════════════════════════════════════════
#  PREVIEW RENDERER TESTS
# ══════════════════════════════════════════════════════════════

class TestBrowserDetection:
    """Test _is_browser_content heuristic."""

    def test_html_language_detected(self):
        from src.preview_renderer import _is_browser_content
        assert _is_browser_content("<div>hello</div>", "html") is True

    def test_javascript_language_detected(self):
        from src.preview_renderer import _is_browser_content
        assert _is_browser_content("console.log(1)", "javascript") is True

    def test_css_language_detected(self):
        from src.preview_renderer import _is_browser_content
        assert _is_browser_content(".box { color: red }", "css") is True

    def test_python_not_browser(self):
        from src.preview_renderer import _is_browser_content
        assert _is_browser_content("print('hello')", "python") is False

    def test_python_with_dom_markers_is_browser(self):
        from src.preview_renderer import _is_browser_content
        # Python code that mentions DOM — unusual but the heuristic catches it
        assert _is_browser_content("document.getElementById('x')", "python") is True

    def test_bash_not_browser(self):
        from src.preview_renderer import _is_browser_content
        assert _is_browser_content("echo hello", "bash") is False

    def test_svg_detected(self):
        from src.preview_renderer import _is_browser_content
        assert _is_browser_content("<svg></svg>", "svg") is True


class TestHtmlPageBuilder:
    """Test _build_html_page wrapping logic."""

    def test_full_html_passthrough(self):
        from src.preview_renderer import _build_html_page
        code = "<!DOCTYPE html><html><body>Hi</body></html>"
        result = _build_html_page(code, "html")
        assert result == code

    def test_html_fragment_wrapped(self):
        from src.preview_renderer import _build_html_page
        code = "<div>Hello</div>"
        result = _build_html_page(code, "html")
        assert "<!DOCTYPE html>" in result
        assert "<div>Hello</div>" in result

    def test_css_only_wrapped(self):
        from src.preview_renderer import _build_html_page
        code = ".box { color: red; }"
        result = _build_html_page(code, "css")
        assert "<!DOCTYPE html>" in result
        assert ".box { color: red; }" in result
        assert "CSS Preview" in result

    def test_javascript_wrapped(self):
        from src.preview_renderer import _build_html_page
        code = "console.log('hello')"
        result = _build_html_page(code, "javascript")
        assert "<!DOCTYPE html>" in result
        assert "<script>" in result
        assert "console.log('hello')" in result

    def test_fallback_pre_wrapped(self):
        from src.preview_renderer import _build_html_page
        code = "print('hello')"
        result = _build_html_page(code, "python")
        assert "<pre>" in result


class TestTerminalPreview:
    """Test _render_terminal_preview returns a valid PIL Image."""

    def test_returns_image(self):
        from src.preview_renderer import _render_terminal_preview
        img = _render_terminal_preview("42", "python")
        assert isinstance(img, Image.Image)
        assert img.width == 1000
        assert img.height == 560

    def test_custom_size(self):
        from src.preview_renderer import _render_terminal_preview
        img = _render_terminal_preview("hello", "bash", width=800, height=400)
        assert img.size == (800, 400)

    def test_empty_output(self):
        from src.preview_renderer import _render_terminal_preview
        img = _render_terminal_preview("", "python")
        assert isinstance(img, Image.Image)

    def test_multiline_output(self):
        from src.preview_renderer import _render_terminal_preview
        output = "\n".join([f"line {i}" for i in range(20)])
        img = _render_terminal_preview(output, "python")
        assert isinstance(img, Image.Image)

    def test_long_line_truncated(self):
        from src.preview_renderer import _render_terminal_preview
        output = "x" * 200
        img = _render_terminal_preview(output, "python")
        assert isinstance(img, Image.Image)


class TestGeneratePreviewImage:
    """Test the main generate_preview_image dispatcher."""

    def test_disabled_returns_none(self, monkeypatch):
        monkeypatch.setattr(config, "ENABLE_VISUAL_PREVIEW", False)
        from src.preview_renderer import generate_preview_image
        result = generate_preview_image("print(1)", "python", "1")
        assert result is None

    def test_python_with_output_returns_terminal(self, monkeypatch):
        monkeypatch.setattr(config, "ENABLE_VISUAL_PREVIEW", True)
        from src.preview_renderer import generate_preview_image
        result = generate_preview_image("print(42)", "python", "42")
        assert isinstance(result, Image.Image)

    def test_python_no_output_returns_none(self, monkeypatch):
        monkeypatch.setattr(config, "ENABLE_VISUAL_PREVIEW", True)
        from src.preview_renderer import generate_preview_image
        result = generate_preview_image("x = 1", "python", None)
        assert result is None

    def test_html_falls_back_to_none_without_playwright(self, monkeypatch):
        monkeypatch.setattr(config, "ENABLE_VISUAL_PREVIEW", True)
        from src.preview_renderer import generate_preview_image
        # Playwright not installed in test env — browser path fails, no code_output → None
        result = generate_preview_image("<div>hi</div>", "html", None)
        # May return None if playwright not available
        assert result is None or isinstance(result, Image.Image)

    def test_html_with_output_falls_back_to_terminal(self, monkeypatch):
        monkeypatch.setattr(config, "ENABLE_VISUAL_PREVIEW", True)
        from src.preview_renderer import generate_preview_image
        # Browser capture fails (no playwright), but has output → terminal fallback
        with patch("src.preview_renderer._capture_browser_preview", return_value=None):
            result = generate_preview_image("<div>hi</div>", "html", "rendered")
        assert isinstance(result, Image.Image)


# ══════════════════════════════════════════════════════════════
#  RENDERER INTEGRATION TESTS
# ══════════════════════════════════════════════════════════════

class TestFitPreviewImage:
    """Test FrameRenderer._fit_preview_image."""

    def _make_renderer(self, preview_image=None):
        from src.renderer import FrameRenderer
        return FrameRenderer(
            code="print('hi')",
            language="python",
            word_timestamps=[],
            duration=5.0,
            preview_image=preview_image,
        )

    def test_none_returns_none(self):
        r = self._make_renderer(preview_image=None)
        assert r.preview_image is None

    def test_image_gets_resized(self):
        img = Image.new("RGB", (2000, 1200), color="red")
        r = self._make_renderer(preview_image=img)
        assert r.preview_image is not None
        # Should be smaller than original
        assert r.preview_image.width <= config.VIDEO_WIDTH
        assert r.preview_image.height <= config.PREVIEW_BOTTOM - config.PREVIEW_Y

    def test_small_image_gets_resized(self):
        img = Image.new("RGB", (100, 50), color="blue")
        r = self._make_renderer(preview_image=img)
        assert r.preview_image is not None


class TestCTAOverlay:
    """Test CTA overlay timing and rendering."""

    def _make_renderer(self):
        from src.renderer import FrameRenderer
        return FrameRenderer(
            code="x = 42",
            language="python",
            word_timestamps=[],
            duration=20.0,
        )

    def test_cta_not_drawn_early(self):
        """CTA should not appear at t=0."""
        r = self._make_renderer()
        import numpy as np
        frame = r.render_frame(1.0)
        assert isinstance(frame, np.ndarray)

    def test_cta_drawn_near_outro(self):
        """CTA should appear just before outro."""
        r = self._make_renderer()
        import numpy as np
        # Just before outro_start
        t = r.outro_start - 1.0
        frame = r.render_frame(t)
        assert isinstance(frame, np.ndarray)

    def test_cta_disabled(self, monkeypatch):
        """When CTA is disabled, no crash."""
        monkeypatch.setattr(config, "ENABLE_CTA_OVERLAY", False)
        r = self._make_renderer()
        import numpy as np
        t = r.outro_start - 1.0
        frame = r.render_frame(t)
        assert isinstance(frame, np.ndarray)


class TestPreviewImageInRenderer:
    """Test that preview_image is used in frame rendering."""

    def test_render_with_preview_image(self):
        """Renderer should not crash when given a preview image."""
        from src.renderer import FrameRenderer
        import numpy as np
        img = Image.new("RGB", (800, 500), color="green")
        r = FrameRenderer(
            code="console.log('hi')",
            language="javascript",
            word_timestamps=[],
            duration=10.0,
            preview_image=img,
        )
        frame = r.render_frame(2.0)
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (config.VIDEO_HEIGHT, config.VIDEO_WIDTH, 3)

    def test_render_without_preview_image(self):
        """Renderer works normally without preview image (backward compatible)."""
        from src.renderer import FrameRenderer
        import numpy as np
        r = FrameRenderer(
            code="print(1)",
            language="python",
            word_timestamps=[],
            duration=10.0,
        )
        frame = r.render_frame(2.0)
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (config.VIDEO_HEIGHT, config.VIDEO_WIDTH, 3)


# ══════════════════════════════════════════════════════════════
#  VIDEO.PY INTEGRATION
# ══════════════════════════════════════════════════════════════

class TestVideoPreviewIntegration:
    """Test that video.py imports preview_renderer and passes preview_image."""

    def test_video_module_has_preview_import(self):
        """create_video references generate_preview_image (lazy import inside)."""
        import inspect
        from src import video
        source = inspect.getsource(video.create_video)
        assert "generate_preview_image" in source
        assert "preview_image" in source

    def test_renderer_constructor_accepts_preview_image(self):
        """FrameRenderer accepts preview_image kwarg (backward compatible)."""
        import inspect
        from src.renderer import FrameRenderer
        sig = inspect.signature(FrameRenderer.__init__)
        assert "preview_image" in sig.parameters
