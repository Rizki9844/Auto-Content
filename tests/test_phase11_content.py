"""
Tests for Phase 11.1: Visual UI Content Pivot.
"""
import json

import pytest
from unittest.mock import patch, MagicMock

from src import config
from src import llm
from src import quality


@pytest.fixture
def mock_gemini():
    """Mock Gemini API response and DB calls for visual_ui mode."""
    with patch("src.llm.genai.Client") as mock_client, patch("src.llm.get_past_topics") as mock_db:
        mock_db.return_value = []
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance
        
        mock_response = MagicMock()
        # Mock successful JSON response matching the new schema
        mock_response.text = json.dumps({
            "title": "Animated Add to Cart Button #Shorts",
            "script": "Check out this smooth micro-interaction for an add-to-cart button that clicks itself! " * 4,
            "html_code": "<html><body><button id='btn' class='cart'>Cart</button><script>setInterval(()=>document.getElementById('btn').classList.toggle('clicked'), 1500)</script></body></html>",
            "display_code": ".cart { transition: all 0.3s; }\n.cart.clicked { transform: scale(0.9); }",
            "language": "html",
            "hashtags": ["#WebDev", "#CSS", "#Frontend"],
            "content_type": "interactive_component",
            "ui_category": "Micro-Interaction"
        })
        mock_instance.models.generate_content.return_value = mock_response
        yield mock_instance

@pytest.fixture
def override_content_mode():
    """Temporarily set CONTENT_MODE to visual_ui and mock API key."""
    original_mode = config.CONTENT_MODE
    original_key = config.GEMINI_API_KEY
    config.CONTENT_MODE = "visual_ui"
    config.GEMINI_API_KEY = "dummy_test_key"
    yield
    config.CONTENT_MODE = original_mode
    config.GEMINI_API_KEY = original_key


def test_visual_ui_content_generation(mock_gemini, override_content_mode):
    """Test that generate_content works correctly with CONTENT_MODE=visual_ui."""
    assert config.CONTENT_MODE == "visual_ui"
    
    content = llm.generate_content()
    
    assert content["title"] == "Animated Add to Cart Button #Shorts"
    assert "html_code" in content
    assert content["html_code"].startswith("<html>")
    assert "display_code" in content
    
    # Assert backward-compatibility mapping
    assert content["code"] == content["display_code"]
    assert content["language"] == "html"
    assert content["content_mode"] == "visual_ui"
    
    # Check that Gemini was called with the correct schema
    mock_gemini.models.generate_content.assert_called_once()
    call_args = mock_gemini.models.generate_content.call_args[1]
    
    prompt = call_args["contents"]
    assert "generate a COMPLETE, self-contained HTML page" in prompt
    
    schema = call_args["config"].response_schema
    props = schema.properties
    assert "html_code" in props
    assert "display_code" in props
    assert "ui_category" in props


def test_visual_ui_validation():
    """Test _validate_visual_ui_content validation logic."""
    valid_data = {
        "title": "Cool Animation #Shorts",
        "script": "word " * 25,
        "html_code": "<div>Test</div>",
        "display_code": "div { color: red; }",
        "language": "html",
        "hashtags": ["#A", "#B", "#C"],
        "content_type": "animation",
    }
    
    # Should not raise
    llm._validate_visual_ui_content(valid_data.copy())
    
    # Test missing hard-required fields (html_code)
    invalid_data = valid_data.copy()
    del invalid_data["html_code"]
    with pytest.raises(ValueError, match="Missing fields"):
        llm._validate_visual_ui_content(invalid_data)
        
    # Test short script
    invalid_data = valid_data.copy()
    invalid_data["script"] = "too short"
    with pytest.raises(ValueError, match="Script too short"):
        llm._validate_visual_ui_content(invalid_data)

    # Test that missing display_code gets auto-extracted (no error)
    data_no_display = valid_data.copy()
    del data_no_display["display_code"]
    llm._validate_visual_ui_content(data_no_display)
    assert data_no_display["display_code"]  # Should be auto-populated

    # Test that missing hashtags gets auto-populated (no error)
    data_no_tags = valid_data.copy()
    del data_no_tags["hashtags"]
    llm._validate_visual_ui_content(data_no_tags)
    assert len(data_no_tags["hashtags"]) >= 3


def test_visual_ui_quality_scoring():
    """Test quality scoring with the new visual_ui mode range."""
    content = {
        "title": "Test Title #Shorts",
        "script": "word " * 50,
        "code": "line1\nline2\nline3\nline4\nline5\nline6",
        "hashtags": ["#1", "#2", "#3", "#4", "#5", "#6"],
        "content_type": "animation",
    }
    
    original_mode = config.CONTENT_MODE
    config.CONTENT_MODE = "coding_tips"
    result_coding = quality.score_content(content)
    assert result_coding["breakdown"]["code_lines"] == 25
    
    content["code"] = "line1\nline2\nline3\nline4"
    
    result_coding_4lines = quality.score_content(content)
    assert result_coding_4lines["breakdown"]["code_lines"] == 25
    
    config.CONTENT_MODE = "visual_ui"
    result_visual_4lines = quality.score_content(content)
    assert result_visual_4lines["breakdown"]["code_lines"] < 25
    assert "Code too short" in result_visual_4lines["reasons"][0]
    
    config.CONTENT_MODE = original_mode

