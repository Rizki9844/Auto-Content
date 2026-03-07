"""
Tests for Phase 11.4: Content Intelligence & Optimization.
Ensures that the LLM pipeline can fetch and inject top performing
past videos into the prompt for self-improvement.
"""
from unittest.mock import patch, MagicMock

from src import config
from src.llm import generate_content
from src.db import get_top_performing_topics


def test_get_top_performing_topics_mocked():
    """Test that the DB function structurally returns records."""
    mock_collection = MagicMock()
    mock_collection.find.return_value.sort.return_value.limit.return_value = [
        {"title": "Epic Top UI", "script": "Wow", "code": "<div></div>"}
    ]
    
    with patch("src.db._get_collection", return_value=mock_collection):
        results = get_top_performing_topics(limit=1, content_mode="visual_ui")
        assert len(results) == 1
        assert results[0]["title"] == "Epic Top UI"


@patch("src.llm.genai.Client")
@patch("src.llm.get_past_topics", return_value=[])
@patch("src.db.get_top_performing_topics")
def test_llm_incorporates_performance_hint(
    mock_get_top, mock_get_past, mock_client_class, monkeypatch
):
    """Test that top performers are injected into the prompt when analytics are enabled."""
    monkeypatch.setattr(config, "ENABLE_YT_ANALYTICS", "1")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "dummy_key")
    
    mock_get_top.return_value = [
        {"title": "Awesome Neon Button", "script": "Here is a glowing button", "code": "<button></button>"}
    ]
    
    mock_client_instance = mock_client_class.return_value
    mock_response = MagicMock()
    mock_response.text = '''{
        "content_type": "creative_ui",
        "ui_category": "Button",
        "title": "Neon Button #Shorts",
        "script": "Check this out! This is a really really really really really really really really really really really long script to make sure it passes the validation step which requires at least twenty words to be present in the script.",
        "html_code": "<button>Cool</button>",
        "display_code": "<button>",
        "language": "html",
        "hashtags": ["#WebDev", "#CSS", "#Design"]
    }'''
    mock_client_instance.models.generate_content.return_value = mock_response
    
    result = generate_content()
    
    mock_get_top.assert_called_once()
    
    call_args = mock_client_instance.models.generate_content.call_args
    prompt_used = call_args.kwargs["contents"]
    
    assert "Awesome Neon Button" in prompt_used
    assert "TOP PERFORMING EXAMPLES" in prompt_used
    assert result["title"] == "Neon Button #Shorts"
