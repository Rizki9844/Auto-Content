"""
Tests for Phase 11.3: Video Layout Redesign.
Ensures that the renderer doesn't crash when using gradient text,
multi-frame previews, or visual_ui specific overlays.
"""
import pytest
from PIL import Image

from src import config
from src.renderer import FrameRenderer

@pytest.fixture
def override_content_mode():
    """Temporarily set CONTENT_MODE to visual_ui."""
    original_mode = config.CONTENT_MODE
    config.CONTENT_MODE = "visual_ui"
    yield
    config.CONTENT_MODE = original_mode


def test_renderer_with_visual_ui_layout(override_content_mode):
    """Test FrameRenderer with a list of preview images and visual_ui content."""
    
    code = "<div>Test</div>"
    word_ts = [{"text": "Hello", "start_s": 0.0, "end_s": 1.0}]
    duration = 5.0
    
    # 3 dummy frames
    frames = [
        Image.new("RGB", (400, 300), color=(255, 0, 0)),
        Image.new("RGB", (400, 300), color=(0, 255, 0)),
        Image.new("RGB", (400, 300), color=(0, 0, 255)),
    ]
    
    renderer = FrameRenderer(
        code=code,
        language="html",
        word_timestamps=word_ts,
        duration=duration,
        content_type="animation",
        title="Epic Animation #Shorts",
        preview_image=frames,
    )
    
    # Render at t=0.0 (intro - should test _draw_wrapped_text_gradient)
    frame_0 = renderer.render_frame(0.0)
    assert frame_0.shape == (config.VIDEO_HEIGHT, config.VIDEO_WIDTH, 3)
    
    # Render at t=2.0 (main code - should test animated preview pasting)
    frame_2 = renderer.render_frame(2.0)
    assert frame_2.shape == (config.VIDEO_HEIGHT, config.VIDEO_WIDTH, 3)
    
    # Render at t=4.5 (CTA overlay - should test visual_ui text "SOURCE")
    frame_cta = renderer.render_frame(4.5)
    assert frame_cta.shape == (config.VIDEO_HEIGHT, config.VIDEO_WIDTH, 3)
    
    # Render at t=4.9 (Outro card - should test "New UI designs every day!")
    frame_outro = renderer.render_frame(4.9)
    assert frame_outro.shape == (config.VIDEO_HEIGHT, config.VIDEO_WIDTH, 3)
