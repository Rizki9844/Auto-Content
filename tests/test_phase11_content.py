"""
Tests for Phase 11.1: Visual UI Content Pivot.
"""
import os
import json
import pytest
from unittest.mock import patch, MagicMock
from google.genai import types

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
            "script": "Check out this smooth micro-interaction for an add-to-cart button that clicks itself! " * 4,  # > 20 words
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
    # Ensure mode is correctly activated
    assert config.CONTENT_MODE == "visual_ui"
    
    # Generate content
    content = llm.generate_content()
    
    # Assert expected fields are present and correctly mapped
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
    
    # Validate prompt
    prompt = call_args["contents"]
    assert "generate a COMPLETE, self-contained HTML page" in prompt
    
    # Validate schema
    schema = call_args["config"].response_schema
    props = schema.properties
    assert "html_code" in props
    assert "display_code" in props
    assert "ui_category" in props


def test_visual_ui_validation():
    """Test _validate_visual_ui_content validation logic."""
    # Valid data
    valid_data = {
        "title": "Cool Animation #Shorts",
        "script": "This is a very cool animation that you should definitely check out right now.", # 14 words - we need >20
        "html_code": "<div>Test</div>",
        "display_code": "div { color: red; }",
        "language": "html",
        "hashtags": ["#A", "#B", "#C"],
        "content_type": "animation",
    }
    # Fix script length to pass validation (>20 words)
    valid_data["script"] = "word " * 25
    
    # Should not raise
    llm._validate_visual_ui_content(valid_data.copy())
    
    # Test missing fields
    invalid_data = valid_data.copy()
    del invalid_data["html_code"]
    with pytest.raises(ValueError, match="Missing fields"):
        llm._validate_visual_ui_content(invalid_data)
        
    # Test short script
    invalid_data = valid_data.copy()
    invalid_data["script"] = "too short"
    with pytest.raises(ValueError, match="Script too short"):
        llm._validate_visual_ui_content(invalid_data)


def test_visual_ui_quality_scoring():
    """Test quality scoring with the new visual_ui mode range."""
    # Setup test content
    content = {
        "title": "Test Title #Shorts",
        "script": "word " * 50, # Ideal range (40-80)
        "code": "line1\nline2\nline3\nline4\nline5\nline6", # 6 lines
        "hashtags": ["#1", "#2", "#3", "#4", "#5", "#6"], # Ideal range (5-8)
        "content_type": "animation",
    }
    
    # Temporarily set to coding_tips logic
    # In coding tips, ideal is 3-10 lines, so 6 is perfect (25 pts)
    original_mode = config.CONTENT_MODE
    config.CONTENT_MODE = "coding_tips"
    result_coding = quality.score_content(content)
    assert result_coding["breakdown"]["code_lines"] == 25
    
    # Adjust to visual_ui where ideal is 5-15, so 4 lines is slightly penalized
    content["code"] = "line1\nline2\nline3\nline4" # 4 lines
    
    # In coding_tips, 4 lines is perfect
    result_coding_4lines = quality.score_content(content)
    assert result_coding_4lines["breakdown"]["code_lines"] == 25
    
    # In visual_ui, 4 lines is below minimum (5)
    config.CONTENT_MODE = "visual_ui"
    result_visual_4lines = quality.score_content(content)
    # Score should be < 25
    assert result_visual_4lines["breakdown"]["code_lines"] < 25
    assert "Code too short" in result_visual_4lines["reasons"][0]
    
    # Restore
    config.CONTENT_MODE = original_mode
