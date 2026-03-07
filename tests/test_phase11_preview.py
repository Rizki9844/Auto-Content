"""
Tests for Phase 11.2: Animated Preview Rendering.
"""
from unittest.mock import patch
from PIL import Image

from src import preview_renderer
from src import config


def test_build_visual_ui_html():
    """Test that valid HTML code is just returned cleanly."""
    html_code = "<html><body><canvas></canvas></body></html> "
    result = preview_renderer._build_visual_ui_html(html_code)
    assert result == html_code.strip()


def test_capture_animated_with_playwright_unavailable():
    """Test that it gracefully falls back when playwright launcher fails."""
    with patch.dict('sys.modules', {'playwright.async_api': None}):
        config.ENABLE_VISUAL_PREVIEW = False
        res = preview_renderer.generate_animated_preview("<html>test</html>")
        assert res is None
        config.ENABLE_VISUAL_PREVIEW = True


def test_generate_animated_preview_mocked():
    """Test the synchronous public API with mocked playwright."""
    html_code = "<html><body><h1>Animation</h1></body></html>"
    
    with patch("src.preview_renderer._capture_animated_with_playwright") as mock_capture:
        fake_images = [Image.new("RGB", (100, 100)) for _ in range(3)]
        
        async def mock_coro(*args, **kwargs):
            return fake_images
            
        mock_capture.side_effect = mock_coro
        
        config.ENABLE_VISUAL_PREVIEW = True
        result = preview_renderer.generate_animated_preview(html_code)
        
        assert result is not None
        assert len(result) == 3
        mock_capture.assert_called_once()
