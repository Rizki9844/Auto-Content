"""
Tests for src.renderer — gradient, base image, frame rendering.
"""
import numpy as np
import pytest
from unittest.mock import patch

from src import config
from src.renderer import (
    _ease_out_cubic,
    _ease_in_out,
    _hex_to_rgb,
    _lerp_color,
    FrameRenderer,
)


# ══════════════════════════════════════════════════════════════
#  UTILITY FUNCTIONS
# ══════════════════════════════════════════════════════════════

class TestEasing:
    def test_ease_out_cubic_0(self):
        assert _ease_out_cubic(0.0) == 0.0

    def test_ease_out_cubic_1(self):
        assert _ease_out_cubic(1.0) == 1.0

    def test_ease_out_cubic_clamps_negative(self):
        assert _ease_out_cubic(-0.5) == 0.0

    def test_ease_out_cubic_clamps_over(self):
        assert _ease_out_cubic(1.5) == 1.0

    def test_ease_out_cubic_midpoint(self):
        result = _ease_out_cubic(0.5)
        assert 0.0 < result < 1.0  # monotonic, between bounds
        assert result > 0.5  # ease-out is "fast then slow", so > linear at 0.5

    def test_ease_in_out_boundaries(self):
        assert _ease_in_out(0.0) == 0.0
        assert _ease_in_out(1.0) == 1.0

    def test_ease_in_out_symmetry(self):
        """Midpoint should be approximately 0.5."""
        assert abs(_ease_in_out(0.5) - 0.5) < 0.01


class TestColorUtils:
    def test_hex_to_rgb(self):
        assert _hex_to_rgb("#ff0000") == (255, 0, 0)
        assert _hex_to_rgb("#00ff00") == (0, 255, 0)
        assert _hex_to_rgb("#0000ff") == (0, 0, 255)
        assert _hex_to_rgb("#000000") == (0, 0, 0)

    def test_hex_to_rgb_no_hash(self):
        assert _hex_to_rgb("ffffff") == (255, 255, 255)

    def test_lerp_color_at_0(self):
        assert _lerp_color((0, 0, 0), (255, 255, 255), 0.0) == (0, 0, 0)

    def test_lerp_color_at_1(self):
        assert _lerp_color((0, 0, 0), (255, 255, 255), 1.0) == (255, 255, 255)

    def test_lerp_color_midpoint(self):
        r, g, b = _lerp_color((0, 0, 0), (200, 100, 50), 0.5)
        assert r == 100
        assert g == 50
        assert b == 25


# ══════════════════════════════════════════════════════════════
#  FRAME RENDERER — initialization and gradient
# ══════════════════════════════════════════════════════════════

def _make_renderer(content_type="tip", code="print('hello')", language="python",
                   code_output=None, code_before=None, title="Test #Shorts"):
    """Helper to build a FrameRenderer with fake word timestamps."""
    fake_timestamps = [
        {"text": "Test", "start_s": 0.0, "end_s": 0.5},
        {"text": "narration", "start_s": 0.5, "end_s": 1.0},
        {"text": "here.", "start_s": 1.0, "end_s": 1.5},
    ]
    return FrameRenderer(
        code=code,
        language=language,
        word_timestamps=fake_timestamps,
        duration=5.0,
        channel_name="@TestChannel",
        content_type=content_type,
        code_output=code_output,
        code_before=code_before,
        title=title,
    )


class TestFrameRendererInit:
    """Test renderer initialization and pre-computation."""

    def test_gradient_bg_shape(self):
        r = _make_renderer()
        arr = np.array(r._gradient_bg)
        assert arr.shape == (config.VIDEO_HEIGHT, config.VIDEO_WIDTH, 3)
        assert arr.dtype == np.uint8

    def test_gradient_bg_top_bottom_different(self):
        r = _make_renderer()
        arr = np.array(r._gradient_bg)
        top_row = arr[0, 0]
        bottom_row = arr[-1, 0]
        assert not np.array_equal(top_row, bottom_row)

    def test_base_image_size(self):
        r = _make_renderer()
        assert r.base.size == (config.VIDEO_WIDTH, config.VIDEO_HEIGHT)

    def test_char_data_populated(self):
        r = _make_renderer(code="x = 1\ny = 2")
        assert r.total_chars > 0
        assert len(r.char_data) == r.total_chars

    def test_char_data_format(self):
        r = _make_renderer(code="x = 1")
        ch, x, y, color = r.char_data[0]
        assert isinstance(ch, str)
        assert isinstance(x, int)
        assert isinstance(y, int)
        assert isinstance(color, str) and color.startswith("#")

    def test_total_lines(self):
        # Pygments lexers append a trailing newline, so 3 visible lines → 4 counted
        r = _make_renderer(code="a\nb\nc")
        assert r.total_lines == 4

    def test_before_after_preview_data(self):
        r = _make_renderer(
            content_type="before_after",
            code="print('after')",
            code_before="print('before')",
        )
        assert hasattr(r, 'preview_before_data')
        assert len(r.preview_before_data) > 0

    def test_output_demo_reveal_time(self):
        r = _make_renderer(
            content_type="output_demo",
            code_output="hello world",
        )
        assert hasattr(r, 'output_reveal_time')
        assert r.output_reveal_time > 0

    def test_subtitle_groups_created(self):
        r = _make_renderer()
        assert len(r.caption_groups) > 0


# ══════════════════════════════════════════════════════════════
#  FRAME RENDERING
# ══════════════════════════════════════════════════════════════

class TestFrameRendering:
    """Test actual frame output at various timestamps."""

    def test_render_frame_shape(self):
        r = _make_renderer()
        frame = r.render_frame(1.0)
        assert frame.shape == (config.VIDEO_HEIGHT, config.VIDEO_WIDTH, 3)
        assert frame.dtype == np.uint8

    def test_render_outro_frame(self):
        r = _make_renderer()
        frame = r.render_frame(r.duration - 0.5)
        assert frame.shape == (config.VIDEO_HEIGHT, config.VIDEO_WIDTH, 3)

    def test_render_code_phase_frame(self):
        r = _make_renderer()
        frame = r.render_frame(2.0)
        assert frame.shape == (config.VIDEO_HEIGHT, config.VIDEO_WIDTH, 3)

    def test_frames_differ_over_time(self):
        """Frames at different timestamps should not be identical (typing animation)."""
        r = _make_renderer(code="x = 1\ny = 2\nz = 3\nprint(x + y + z)")
        f1 = r.render_frame(0.5)
        f2 = r.render_frame(1.5)
        assert not np.array_equal(f1, f2)

    def test_output_demo_renders(self):
        r = _make_renderer(
            content_type="output_demo",
            code="print('hello')",
            code_output="hello",
        )
        frame = r.render_frame(1.0)
        assert frame.shape[0] == config.VIDEO_HEIGHT

    def test_quiz_renders(self):
        r = _make_renderer(
            content_type="quiz",
            code="print(1 + 1)",
            code_output="2",
        )
        frame = r.render_frame(1.0)
        assert frame.shape[0] == config.VIDEO_HEIGHT

    def test_before_after_renders(self):
        r = _make_renderer(
            content_type="before_after",
            code="for i, v in enumerate(lst):\n    print(i, v)",
            code_before="for i in range(len(lst)):\n    print(i, lst[i])",
        )
        frame = r.render_frame(1.0)
        assert frame.shape[0] == config.VIDEO_HEIGHT
