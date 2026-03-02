"""
Tests for src.main — CredentialFilter, content safety, JSON logging, health check.
"""
import json
import logging
import pytest
from src.main import CredentialFilter, _is_content_safe, _JsonFormatter, _health_check


# ══════════════════════════════════════════════════════════════
#  CREDENTIAL FILTER
# ══════════════════════════════════════════════════════════════

class TestCredentialFilter:
    """Ensure secrets are redacted from log output."""

    @pytest.fixture
    def _filter(self):
        return CredentialFilter()

    def _make_record(self, msg: str):
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg=msg, args=None, exc_info=None,
        )
        return record

    def test_mongodb_uri_redacted(self, _filter):
        record = self._make_record("Connecting to mongodb+srv://user:SuperSecret123@cluster.mongodb.net")
        _filter.filter(record)
        assert "SuperSecret123" not in record.msg
        assert "REDACTED" in record.msg

    def test_gemini_api_key_redacted(self, _filter):
        record = self._make_record("Using key AIzaSyD_fake_key_1234567890abcdefghijklm")
        _filter.filter(record)
        assert "AIzaSyD" not in record.msg
        assert "REDACTED" in record.msg

    def test_oauth_token_redacted(self, _filter):
        record = self._make_record("Token ya29.a0ARrdaM-fake-oauth-token-value")
        _filter.filter(record)
        assert "ya29" not in record.msg
        assert "REDACTED" in record.msg

    def test_refresh_token_redacted(self, _filter):
        record = self._make_record("Refresh 1//0dNgoAB_fake_refresh_token_value")
        _filter.filter(record)
        assert "1//0dNgoAB" not in record.msg
        assert "REDACTED" in record.msg

    def test_normal_message_unchanged(self, _filter):
        record = self._make_record("Pipeline started successfully at 12:00")
        _filter.filter(record)
        assert record.msg == "Pipeline started successfully at 12:00"

    def test_args_set_to_none(self, _filter):
        record = self._make_record("debug info")
        _filter.filter(record)
        assert record.args is None

    def test_filter_returns_true(self, _filter):
        """Filter should never suppress records (always returns True)."""
        record = self._make_record("test")
        assert _filter.filter(record) is True

    def test_multiple_secrets_in_one_line(self, _filter):
        msg = "mongo=mongodb+srv://u:SECRET@c.net key=AIzaSyD_0123456789abcdefghijklmnopqrstuv"
        record = self._make_record(msg)
        _filter.filter(record)
        assert "SECRET" not in record.msg
        assert "AIzaSyD" not in record.msg


# ══════════════════════════════════════════════════════════════
#  CONTENT SAFETY FILTER
# ══════════════════════════════════════════════════════════════

class TestContentSafety:
    """Test keyword-based content safety filtering."""

    def test_safe_content_passes(self, sample_content):
        safe, reason = _is_content_safe(sample_content)
        assert safe
        assert reason == ""

    def test_blocked_violence_keyword(self):
        # "kill" alone is NOT blocked (too common in programming: kill -9, kill process)
        # "murder" is never a legitimate coding term
        content = {
            "title": "How to murder someone tutorial #Shorts",
            "script": "Learn how to murder in this tutorial",
            "code": "x = 1",
            "code_before": "",
            "expected_output": "",
        }
        safe, reason = _is_content_safe(content)
        assert not safe
        assert "murder" in reason

    def test_kill_process_is_NOT_blocked(self):
        """kill -9 / kill a process is legitimate coding content — must NOT be blocked."""
        content = {
            "title": "How to Kill a Process in Bash #Shorts",
            "script": "Use kill -9 to forcefully terminate a process in Linux.",
            "code": "kill -9 $(lsof -t -i:8080)",
            "code_before": "",
            "expected_output": "",
        }
        safe, _ = _is_content_safe(content)
        assert safe

    def test_blocked_hate_speech(self):
        content = {
            "title": "Test #Shorts",
            "script": "Something with racist content",
            "code": "x = 1",
            "code_before": "",
            "expected_output": "",
        }
        safe, reason = _is_content_safe(content)
        assert not safe

    def test_blocked_explicit(self):
        content = {
            "title": "Test #Shorts",
            "script": "nsfw content here",
            "code": "",
            "code_before": "",
            "expected_output": "",
        }
        safe, reason = _is_content_safe(content)
        assert not safe

    def test_blocked_hacking(self):
        content = {
            "title": "Test #Shorts",
            "script": "how to ddos a server",
            "code": "",
            "code_before": "",
            "expected_output": "",
        }
        safe, reason = _is_content_safe(content)
        assert not safe

    def test_blocked_keyword_in_code(self):
        """Keywords in code should also trigger."""
        content = {
            "title": "Test #Shorts",
            "script": "Clean script",
            "code": "# ransomware demo",
            "code_before": "",
            "expected_output": "",
        }
        safe, reason = _is_content_safe(content)
        assert not safe

    def test_blocked_keyword_in_expected_output(self):
        content = {
            "title": "Test #Shorts",
            "script": "Clean",
            "code": "x=1",
            "code_before": "",
            "expected_output": "keylogger activated",
        }
        safe, reason = _is_content_safe(content)
        assert not safe

    def test_safe_with_missing_optional_fields(self):
        """Fields that are missing should default to empty (not crash)."""
        content = {
            "title": "Safe Title #Shorts",
            "script": "A safe and normal script",
            "code": "print(42)",
        }
        safe, reason = _is_content_safe(content)
        assert safe

    def test_case_insensitive(self):
        content = {
            "title": "Test #Shorts",
            "script": "NSFW content",
            "code": "",
            "code_before": "",
            "expected_output": "",
        }
        safe, _ = _is_content_safe(content)
        assert not safe


# ══════════════════════════════════════════════════════════════
#  JSON FORMATTER  (Task 2.4)
# ══════════════════════════════════════════════════════════════

class TestJsonFormatter:
    """Validate structured JSON log output."""

    @pytest.fixture
    def _fmt(self):
        return _JsonFormatter()

    def _make_record(self, msg: str):
        return logging.LogRecord(
            name="pipeline", level=logging.INFO, pathname="", lineno=0,
            msg=msg, args=None, exc_info=None,
        )

    def test_output_is_valid_json(self, _fmt):
        record = self._make_record("hello world")
        output = _fmt.format(record)
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_required_fields(self, _fmt):
        record = self._make_record("test")
        data = json.loads(_fmt.format(record))
        assert "timestamp" in data
        assert "level" in data
        assert "module" in data
        assert "message" in data

    def test_level_matches_record(self, _fmt):
        record = self._make_record("warning test")
        record.levelname = "WARNING"
        data = json.loads(_fmt.format(record))
        assert data["level"] == "WARNING"

    def test_module_matches_logger_name(self, _fmt):
        record = self._make_record("test")
        data = json.loads(_fmt.format(record))
        assert data["module"] == "pipeline"

    def test_message_preserved(self, _fmt):
        record = self._make_record("pipeline started OK")
        data = json.loads(_fmt.format(record))
        assert data["message"] == "pipeline started OK"


# ══════════════════════════════════════════════════════════════
#  HEALTH CHECK  (Task 2.7)
# ══════════════════════════════════════════════════════════════

class TestHealthCheck:
    """Smoke-test the health check without real services."""

    def test_returns_int(self, monkeypatch):
        """Health check always returns an integer exit code."""
        import src.config as _cfg
        monkeypatch.setattr(_cfg, "GEMINI_API_KEY", "")
        monkeypatch.setattr(_cfg, "MONGODB_URI", "")
        result = _health_check()
        assert isinstance(result, int)

    def test_unhealthy_when_no_creds(self, monkeypatch):
        """Without any credentials, health check should return 1."""
        import src.config as _cfg
        monkeypatch.setattr(_cfg, "GEMINI_API_KEY", "")
        monkeypatch.setattr(_cfg, "MONGODB_URI", "")
        monkeypatch.setattr(_cfg, "YOUTUBE_CLIENT_ID", "")
        monkeypatch.setattr(_cfg, "YOUTUBE_CLIENT_SECRET", "")
        monkeypatch.setattr(_cfg, "YOUTUBE_REFRESH_TOKEN", "")
        assert _health_check() == 1
