"""
Integration test — dry-run the entire pipeline with all external services mocked.
Verifies step sequencing, error handling, and data flow without network access.
Updated for Phase 3 (quality scoring, video verification, error classification, etc.).
"""
import pytest
from unittest.mock import patch, MagicMock


FAKE_CONTENT = {
    "title": "Python Walrus Operator #Shorts",
    "script": (
        "Did you know Python has a walrus operator? The colon-equals operator lets you "
        "assign and test a value in a single expression. It's perfect for while loops, "
        "list comprehensions, and conditional checks. No more separate assignment lines — "
        "just clean, compact code. Here's a quick example to level up your Python game."
    ),
    "code": "if (n := len([1,2,3])) > 2:\n    print(f'List has {n} items')",
    "language": "python",
    "hashtags": ["#Python", "#WalrusOperator", "#CodingTips", "#Programming", "#Shorts"],
    "content_type": "output_demo",
    "expected_output": "List has 3 items",
    "quiz_answer": "",
    "code_before": "",
}


@pytest.fixture
def _mock_pipeline(monkeypatch):
    """Patch all external services so the pipeline can run in a vacuum."""
    # Config reads env vars at import time — patch the already-loaded attributes
    import src.config as _cfg
    monkeypatch.setattr(_cfg, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(_cfg, "MONGODB_URI", "mongodb+srv://fake")

    with (
        patch("src.llm.generate_content", return_value=FAKE_CONTENT) as m_gen,
        patch("src.tts.generate_speech") as m_tts,
        patch("src.video.create_video") as m_video,
        patch("src.video.verify_video") as m_verify,
        patch("src.uploader_youtube.upload_to_youtube") as m_upload,
        patch("src.db.save_record") as m_save,
        patch("src.db.get_pending_uploads", return_value=[]) as m_pending,
        patch("src.db.check_code_similarity") as m_sim,
        patch("src.db.get_language_frequency") as m_lang_freq,
        patch("src.code_runner.get_output_for_content") as m_code,
        patch("src.notifier.send_notification") as m_notify,
        patch("src.tts.get_audio_duration", return_value=12.5),
        patch("src.main._cleanup_output_dir"),
    ):
        # TTS returns a fake path + timestamps
        m_tts.return_value = (
            "/tmp/fake_audio.mp3",
            [{"text": "Test", "start_s": 0.0, "end_s": 0.5}],
        )
        m_video.return_value = "/tmp/fake_video.mp4"
        m_verify.return_value = {"passed": True, "checks": {}, "errors": []}
        m_upload.return_value = "dQw4w9WgXcQ"
        m_save.return_value = "64a1b2c3d4e5f678901234ab"
        m_code.return_value = "List has 3 items"
        m_sim.return_value = {"is_duplicate": False, "max_similarity": 0.1, "similar_to": ""}
        m_lang_freq.return_value = {
            "counts": {"python": 3, "javascript": 2},
            "overused": [],
            "suggested_avoid": [],
            "recent_types": ["tip", "quiz"],
        }

        yield {
            "generate": m_gen,
            "tts": m_tts,
            "video": m_video,
            "verify": m_verify,
            "upload": m_upload,
            "save": m_save,
            "pending": m_pending,
            "similarity": m_sim,
            "lang_freq": m_lang_freq,
            "code": m_code,
            "notify": m_notify,
        }


@pytest.mark.integration
class TestPipelineDryRun:
    """Full pipeline execution with mocked services."""

    def test_success_run(self, _mock_pipeline):
        """Pipeline should complete without errors when everything works."""
        from src.main import main

        # Should NOT raise
        main()

        # Verify call sequence
        _mock_pipeline["generate"].assert_called_once()
        _mock_pipeline["tts"].assert_called_once()
        _mock_pipeline["video"].assert_called_once()
        _mock_pipeline["verify"].assert_called_once()
        _mock_pipeline["upload"].assert_called_once()
        _mock_pipeline["save"].assert_called_once()
        _mock_pipeline["notify"].assert_called_once()

    def test_save_record_receives_youtube_id(self, _mock_pipeline):
        from src.main import main
        main()

        save_args = _mock_pipeline["save"].call_args[0][0]
        assert save_args["youtube_id"] == "dQw4w9WgXcQ"
        assert save_args["status"] == "success"

    def test_notification_on_success(self, _mock_pipeline):
        from src.main import main
        main()

        _mock_pipeline["notify"].assert_called_once()
        call_kwargs = _mock_pipeline["notify"].call_args[1]
        assert call_kwargs["status"] == "success"

    def test_content_safety_blocks_unsafe(self, _mock_pipeline):
        """If generated content is unsafe, pipeline should sys.exit(1)."""
        unsafe_content = FAKE_CONTENT.copy()
        unsafe_content["title"] = "How to make a bomb tutorial #Shorts"
        _mock_pipeline["generate"].return_value = unsafe_content

        from src.main import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    def test_missing_gemini_key_exits(self, _mock_pipeline, monkeypatch):
        """Missing GEMINI_API_KEY should exit immediately."""
        import src.config as _cfg
        monkeypatch.setattr(_cfg, "GEMINI_API_KEY", "")

        from src.main import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    def test_missing_mongodb_uri_exits(self, _mock_pipeline, monkeypatch):
        import src.config as _cfg
        monkeypatch.setattr(_cfg, "GEMINI_API_KEY", "fake-key")
        monkeypatch.setattr(_cfg, "MONGODB_URI", "")

        from src.main import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    def test_generation_failure_saves_error(self, _mock_pipeline):
        _mock_pipeline["generate"].side_effect = RuntimeError("API quota exceeded")

        from src.main import main
        with pytest.raises(SystemExit):
            main()

        # Failure should still be saved to MongoDB
        _mock_pipeline["save"].assert_called_once()
        save_args = _mock_pipeline["save"].call_args[0][0]
        assert save_args["status"] == "failed"
        assert "quota" in save_args["error_message"].lower()
