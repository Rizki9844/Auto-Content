"""
Tests for Phase 11.5: Resolution Upgrade (Optional 4K).
Ensures that the pipeline correctly scales the layout constants
when VIDEO_RESOLUTION is set to 4k.
"""
import importlib


def test_config_resolution_scaling(monkeypatch):
    """Test that all layout constants scale up by 2x when in 4K mode."""
    import src.config as config
    
    # Store 1080p defaults for comparison
    w_1080 = config.VIDEO_WIDTH
    h_1080 = config.VIDEO_HEIGHT
    code_font_1080 = config.CODE_FONT_SIZE
    padding_1080 = config.PADDING
    
    # Force 4K mode and reload config
    monkeypatch.setenv("VIDEO_RESOLUTION", "4k")
    importlib.reload(config)
    
    try:
        assert config.SCALE == 2
        assert config.VIDEO_WIDTH == w_1080 * 2
        assert config.VIDEO_HEIGHT == h_1080 * 2
        assert config.CODE_FONT_SIZE == code_font_1080 * 2
        assert config.PADDING == padding_1080 * 2
    finally:
        # Restore configuration back to default for other tests
        monkeypatch.delenv("VIDEO_RESOLUTION", raising=False)
        importlib.reload(config)
