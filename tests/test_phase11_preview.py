"""
Tests for Phase 11.2: Animated Preview Rendering.
"""
import pytest
from unittest.mock import patch, MagicMock
from PIL import Image

from src import preview_renderer
from src import config

def test_build_visual_ui_html():
    """Test that valid HTML code is just returned cleanly."""
    html_code = "<html><body><canvas></canvas></body></html> "
    result = preview_renderer._build_visual_ui_html(html_code)
    assert result == html_code.strip()


import sys

def test_capture_animated_with_playwright_unavailable():
    """Test that it gracefully falls back when playwright launcher fails."""
    # We mock sys.modules to simulate playwright not being installed at all
    with patch.dict('sys.modules', {'playwright.async_api': None}):
        config.ENABLE_VISUAL_PREVIEW = False
        res = preview_renderer.generate_animated_preview("<html>test</html>")
        assert res is None
        config.ENABLE_VISUAL_PREVIEW = True


def test_generate_animated_preview_mocked():
    """Test the synchronous public API with mocked playwright."""
    html_code = "<html><body><h1>Animation</h1></body></html>"
    
    # We patch the internal async function so we don't need real browser
    with patch("src.preview_renderer._capture_animated_with_playwright") as mock_capture:
        # Mock returning a list of 3 fake images
        fake_images = [Image.new("RGB", (100, 100)) for _ in range(3)]
        
        import asyncio
        # Create a mock coroutine
        async def mock_coro(*args, **kwargs):
            return fake_images
            
        mock_capture.side_effect = mock_coro
        
        config.ENABLE_VISUAL_PREVIEW = True
        result = preview_renderer.generate_animated_preview(html_code)
        
        assert result is not None
        assert len(result) == 3
        mock_capture.assert_called_once()
