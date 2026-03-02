"""
Tests for src.llm — JSON repair, content validation, prompt construction.
"""
import json
import pytest
from src.llm import _repair_json, _validate_content


# ══════════════════════════════════════════════════════════════
#  _repair_json — parse and repair malformed LLM JSON
# ══════════════════════════════════════════════════════════════

class TestRepairJson:
    """Tests for the JSON repair pipeline."""

    def test_valid_json_passthrough(self):
        """Clean JSON should parse without modification."""
        raw = json.dumps({"title": "Test #Shorts", "script": "Hello", "code": "x=1", "language": "python", "hashtags": ["#A"]})
        result = _repair_json(raw)
        assert result["title"] == "Test #Shorts"

    def test_markdown_code_fence_stripped(self):
        """```json ... ``` wrappers should be removed."""
        inner = json.dumps({"title": "T", "script": "S", "code": "C", "language": "python", "hashtags": ["#X"]})
        raw = f"```json\n{inner}\n```"
        result = _repair_json(raw)
        assert result["title"] == "T"

    def test_unescaped_newlines_in_strings(self):
        """Literal newlines inside JSON string values should be escaped."""
        raw = '{"title": "Test", "script": "line one\nline two", "code": "x=1", "language": "python", "hashtags": ["#A"]}'
        result = _repair_json(raw)
        assert "line one" in result["script"]
        assert "line two" in result["script"]

    def test_truncated_json_missing_braces(self):
        """Truncated JSON with missing closing braces should be repaired."""
        raw = '{"title": "T", "script": "S", "code": "C", "language": "python", "hashtags": ["#A"]'
        result = _repair_json(raw)
        assert result["title"] == "T"

    def test_truncated_json_missing_bracket_and_brace(self):
        """Missing both ] and } should be auto-closed."""
        raw = '{"title": "T", "script": "S", "code": "C", "language": "python", "hashtags": ["#A"'
        result = _repair_json(raw)
        assert result["title"] == "T"

    def test_unescaped_tabs_in_code(self):
        """Tabs inside string values should be escaped to \\t."""
        raw = '{"title": "T", "script": "S", "code": "def f():\tx=1", "language": "python", "hashtags": ["#A"]}'
        result = _repair_json(raw)
        assert result["code"] is not None

    def test_regex_fallback_extraction(self):
        """When JSON is severely broken, regex should extract key fields."""
        # Deliberately malformed — missing comma, broken structure
        raw = '{"title": "My Title", "script": "Some script here" "code": "print(1)", "language": "python", "hashtags": ["#Tip", "#Code"]}'
        result = _repair_json(raw)
        assert result["title"] == "My Title"
        assert result["language"] == "python"

    def test_completely_invalid_raises(self):
        """Completely unrecoverable garbage should raise JSONDecodeError."""
        with pytest.raises(json.JSONDecodeError):
            _repair_json("this is not json at all")

    def test_empty_string_raises(self):
        """Empty string should raise."""
        with pytest.raises((json.JSONDecodeError, KeyError)):
            _repair_json("")


# ══════════════════════════════════════════════════════════════
#  _validate_content — field validation and normalization
# ══════════════════════════════════════════════════════════════

class TestValidateContent:
    """Tests for content validation after JSON parsing."""

    def test_valid_content_passes(self, sample_content):
        """Fully valid content should pass without raising."""
        _validate_content(sample_content)

    def test_missing_title_raises(self, sample_content):
        del sample_content["title"]
        with pytest.raises(ValueError, match="Missing fields"):
            _validate_content(sample_content)

    def test_missing_code_raises(self, sample_content):
        del sample_content["code"]
        with pytest.raises(ValueError, match="Missing fields"):
            _validate_content(sample_content)

    def test_empty_code_raises(self, sample_content):
        sample_content["code"] = "   "
        with pytest.raises(ValueError, match="Code snippet is empty"):
            _validate_content(sample_content)

    def test_script_too_short_raises(self, sample_content):
        sample_content["script"] = "Too short"
        with pytest.raises(ValueError, match="Script too short"):
            _validate_content(sample_content)

    def test_too_few_hashtags_raises(self, sample_content):
        sample_content["hashtags"] = ["#One", "#Two"]
        with pytest.raises(ValueError, match="at least 3 hashtags"):
            _validate_content(sample_content)

    def test_shorts_appended_if_missing(self, sample_content):
        sample_content["title"] = "My Cool Tip"
        _validate_content(sample_content)
        assert sample_content["title"].endswith("#Shorts")

    def test_language_normalized_lowercase(self, sample_content):
        sample_content["language"] = "  PYTHON  "
        _validate_content(sample_content)
        assert sample_content["language"] == "python"

    def test_unknown_content_type_defaults_to_tip(self, sample_content):
        sample_content["content_type"] = "unknown_type"
        _validate_content(sample_content)
        assert sample_content["content_type"] == "tip"

    def test_output_demo_gets_expected_output_default(self):
        data = {
            "title": "Test #Shorts",
            "script": " ".join(["word"] * 30),
            "code": "print(1)",
            "language": "python",
            "hashtags": ["#A", "#B", "#C"],
            "content_type": "output_demo",
        }
        _validate_content(data)
        assert "expected_output" in data

    def test_quiz_gets_quiz_answer_default(self):
        data = {
            "title": "Test #Shorts",
            "script": " ".join(["word"] * 30),
            "code": "print(1)",
            "language": "python",
            "hashtags": ["#A", "#B", "#C"],
            "content_type": "quiz",
        }
        _validate_content(data)
        assert "quiz_answer" in data

    def test_before_after_gets_code_before_default(self):
        data = {
            "title": "Test #Shorts",
            "script": " ".join(["word"] * 30),
            "code": "print(1)",
            "language": "python",
            "hashtags": ["#A", "#B", "#C"],
            "content_type": "before_after",
        }
        _validate_content(data)
        assert "code_before" in data
