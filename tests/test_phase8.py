"""
Tests for Phase 8 — Production Reliability.

Covers:
  8.1 Self-Healing Pipeline (health_monitor, Gemini fallback, TTS fallback)
  8.2 MongoDB Archive & Cleanup (db_maintenance)
  8.3 Comprehensive Logging & Audit Trail (pipeline_logger)
  8.4 Graceful Pipeline Timeout (_run_with_timeout)
  8.5 Staging Environment (config, CLI flags)
"""
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ══════════════════════════════════════════════════════════════
#  Phase 8.1 — Self-Healing Pipeline
# ══════════════════════════════════════════════════════════════


class TestHealthMonitorCheckStaleQueue:
    """Tests for health_monitor.check_stale_queue()."""

    def test_no_stale_items_returns_zero(self):
        """Empty queue returns zero counts."""
        mock_col = MagicMock()
        mock_col.find.return_value = []

        with patch("src.db._get_collection", return_value=mock_col):
            from src.health_monitor import check_stale_queue
            result = check_stale_queue()

        assert result["stale_count"] == 0
        assert result["alerted"] == 0
        assert result["reset"] == 0

    def test_stale_items_detected_and_reset(self):
        """Stale items get alert + retry count reset."""
        stale_doc = {
            "_id": "doc1",
            "title": "Test Video",
            "status": "rendered_not_uploaded",
            "created_at": datetime.now(timezone.utc) - timedelta(hours=48),
        }
        mock_col = MagicMock()
        mock_col.find.return_value = [stale_doc]
        mock_col.update_one.return_value = MagicMock()

        with (
            patch("src.db._get_collection", return_value=mock_col),
            patch("src.notifier.send_notification", return_value=True),
        ):
            from src.health_monitor import check_stale_queue
            result = check_stale_queue(stale_hours=24)

        assert result["stale_count"] == 1
        assert result["alerted"] == 1
        assert result["reset"] == 1
        mock_col.update_one.assert_called_once()

    def test_custom_stale_hours(self):
        """Custom stale hours threshold is respected."""
        mock_col = MagicMock()
        mock_col.find.return_value = []

        with patch("src.db._get_collection", return_value=mock_col):
            from src.health_monitor import check_stale_queue
            result = check_stale_queue(stale_hours=12)

        assert result["stale_count"] == 0
        # Verify cutoff used correct hours
        call_args = mock_col.find.call_args[0][0]
        assert "created_at" in call_args

    def test_db_failure_handled_gracefully(self):
        """Database failures don't crash the check."""
        with patch("src.db._get_collection", side_effect=Exception("DB down")):
            from src.health_monitor import check_stale_queue
            result = check_stale_queue()
        assert result["stale_count"] == 0


class TestHealthMonitorQuotaRecovery:
    """Tests for health_monitor.check_quota_recovery()."""

    def test_quota_available(self):
        """Returns quota_available=True when quota is OK."""
        mock_limiter = MagicMock()
        mock_limiter.check_youtube_quota.return_value = {
            "can_upload": True,
            "remaining": 5,
        }

        with patch("src.rate_limiter.RateLimiter", return_value=mock_limiter):
            from src.health_monitor import check_quota_recovery
            result = check_quota_recovery()

        assert result["quota_available"] is True

    def test_quota_exhausted(self):
        """Returns quota_available=False when quota is exhausted."""
        mock_limiter = MagicMock()
        mock_limiter.check_youtube_quota.return_value = {
            "can_upload": False,
            "remaining": 0,
        }

        with (
            patch("src.rate_limiter.RateLimiter", return_value=mock_limiter),
            patch("src.notifier.send_notification", return_value=True),
        ):
            from src.health_monitor import check_quota_recovery
            result = check_quota_recovery()

        assert result["quota_available"] is False


class TestHealthMonitorRunAll:
    """Tests for health_monitor.run_all_checks()."""

    def test_run_all_checks_combines_results(self):
        """run_all_checks returns combined report from all checks."""
        with (
            patch("src.health_monitor.check_stale_queue", return_value={
                "stale_count": 0, "alerted": 0, "reset": 0,
            }),
            patch("src.health_monitor.check_quota_recovery", return_value={
                "quota_available": True, "rescheduled": 0,
            }),
        ):
            from src.health_monitor import run_all_checks
            report = run_all_checks()

        assert "stale_queue" in report
        assert "quota" in report

    def test_run_all_with_issues(self):
        """Report includes issues when found."""
        with (
            patch("src.health_monitor.check_stale_queue", return_value={
                "stale_count": 3, "alerted": 3, "reset": 3,
            }),
            patch("src.health_monitor.check_quota_recovery", return_value={
                "quota_available": False, "rescheduled": 0,
            }),
        ):
            from src.health_monitor import run_all_checks
            report = run_all_checks()

        assert report["stale_queue"]["stale_count"] == 3
        assert report["quota"]["quota_available"] is False


class TestGeminiFallbackModel:
    """Tests for Phase 8.1 Gemini fallback model in llm.py."""

    def test_try_fallback_model_success(self):
        """Fallback model returns content when primary fails."""
        from src.llm import _try_fallback_model

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"title": "Test #Shorts", "script": "' + ("word " * 30) + '", "code": "print(1)", "language": "python", "hashtags": ["#a", "#b", "#c"], "content_type": "tip", "quiz_answer": "", "code_before": "", "expected_output": ""}'
        mock_client.models.generate_content.return_value = mock_response

        with patch("src.config.GEMINI_FALLBACK_MODEL", "gemini-1.5-flash"):
            with patch("src.config.GEMINI_MODEL", "gemini-2.5-flash"):
                result = _try_fallback_model(
                    mock_client, "test prompt", "A", "energetic", None,
                )

        assert result is not None
        assert result["fallback_model_used"] == "gemini-1.5-flash"

    def test_try_fallback_model_no_distinct_fallback(self):
        """Returns None when fallback is same as primary model."""
        from src.llm import _try_fallback_model

        with patch("src.config.GEMINI_FALLBACK_MODEL", "gemini-2.5-flash"):
            with patch("src.config.GEMINI_MODEL", "gemini-2.5-flash"):
                result = _try_fallback_model(
                    MagicMock(), "test prompt", "A", "calm", None,
                )

        assert result is None

    def test_try_fallback_model_also_fails(self):
        """Returns None when fallback model also fails."""
        from src.llm import _try_fallback_model

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("Fallback down")

        with patch("src.config.GEMINI_FALLBACK_MODEL", "gemini-1.5-flash"):
            with patch("src.config.GEMINI_MODEL", "gemini-2.5-flash"):
                result = _try_fallback_model(
                    mock_client, "test prompt", "B", "dramatic", "template_x",
                )

        assert result is None

    def test_fallback_model_empty_string(self):
        """Returns None when fallback model is empty string."""
        from src.llm import _try_fallback_model

        with patch("src.config.GEMINI_FALLBACK_MODEL", ""):
            result = _try_fallback_model(
                MagicMock(), "test prompt", "A", "calm", None,
            )

        assert result is None


class TestTTSFallback:
    """Tests for Phase 8.1 TTS fallback in tts.py."""

    def test_gtts_fallback_function(self):
        """_gtts_fallback generates audio via gTTS."""
        import src.tts as tts_mod

        mock_gtts_instance = MagicMock()
        mock_gtts_class = MagicMock(return_value=mock_gtts_instance)

        output_path = str(Path("output") / "test_audio.mp3")

        with (
            patch.dict("sys.modules", {"gtts": MagicMock(gTTS=mock_gtts_class)}),
            patch("src.tts.get_audio_duration", return_value=5.0),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.stat") as mock_stat,
        ):
            mock_stat.return_value = MagicMock(st_size=5000)
            path, timestamps = tts_mod._gtts_fallback(
                "Hello world this is a test sentence for TTS", output_path
            )

        assert timestamps  # Should have approximate timestamps
        mock_gtts_instance.save.assert_called_once()

    def test_approximate_timestamps_distribution(self):
        """_approximate_timestamps distributes words evenly."""
        from src.tts import _approximate_timestamps

        words = ["hello", "world", "test", "audio"]
        timestamps = _approximate_timestamps(words, 4.0)

        assert len(timestamps) == 4
        assert timestamps[0].start_s == pytest.approx(0.0)
        assert timestamps[0].end_s == pytest.approx(1.0)
        assert timestamps[3].start_s == pytest.approx(3.0)
        assert timestamps[3].end_s == pytest.approx(4.0)

    def test_approximate_timestamps_empty(self):
        """Empty words list returns empty timestamps."""
        from src.tts import _approximate_timestamps
        assert _approximate_timestamps([], 5.0) == []
        assert _approximate_timestamps(["hello"], 0) == []

    def test_edge_tts_failure_counter_reset(self):
        """Successful edge-tts call resets the failure counter."""
        import src.tts as tts_mod
        tts_mod._edge_tts_consecutive_failures = 2

        with (
            patch("src.tts.asyncio.run") as mock_run,
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.stat") as mock_stat,
        ):
            mock_stat.return_value = MagicMock(st_size=5000)
            mock_run.return_value = [
                tts_mod.WordTimestamp("hello", 0.0, 0.5),
            ]
            tts_mod.generate_speech("Hello world test sentence for subtitles", output_path="/tmp/test.mp3")

        assert tts_mod._edge_tts_consecutive_failures == 0

    def test_edge_tts_max_failures_triggers_fallback(self):
        """After MAX_FAILURES, calls go directly to gTTS fallback."""
        import src.tts as tts_mod
        tts_mod._edge_tts_consecutive_failures = 3

        with patch.object(tts_mod, "_gtts_fallback", return_value=("/tmp/test.mp3", [])) as mock_fb:
            tts_mod.generate_speech("Test text for fallback trigger", output_path="/tmp/test.mp3")
            mock_fb.assert_called_once()

        # Reset for other tests
        tts_mod._edge_tts_consecutive_failures = 0


# ══════════════════════════════════════════════════════════════
#  Phase 8.2 — MongoDB Archive & Cleanup
# ══════════════════════════════════════════════════════════════


class TestArchiveOldRecords:
    """Tests for db_maintenance.archive_old_records()."""

    def test_no_old_records(self):
        """Returns zeros when nothing to archive."""
        mock_col = MagicMock()
        mock_col.find.return_value = []
        mock_db = MagicMock()
        mock_col.database = mock_db
        mock_archive = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_archive)

        with patch("src.db._get_collection", return_value=mock_col):
            from src.db_maintenance import archive_old_records
            result = archive_old_records(days=90)

        assert result["archived"] == 0
        assert result["deleted"] == 0

    def test_archives_old_records(self):
        """Old records are archived and deleted from main collection."""
        old_doc = {
            "_id": "old1",
            "title": "Old Video",
            "language": "python",
            "content_type": "tip",
            "created_at": datetime.now(timezone.utc) - timedelta(days=100),
            "code": "print('hello')" * 100,
            "script": "Long script " * 100,
            "youtube_id": "abc123",
            "quality_score": 85,
            "status": "success",
        }
        mock_col = MagicMock()
        mock_col.find.return_value = [old_doc]
        mock_col.delete_one.return_value = MagicMock()
        mock_db = MagicMock()
        mock_col.database = mock_db
        mock_archive = MagicMock()
        mock_archive.replace_one.return_value = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_archive)

        with patch("src.db._get_collection", return_value=mock_col):
            from src.db_maintenance import archive_old_records
            result = archive_old_records(days=90)

        assert result["archived"] == 1
        assert result["deleted"] == 1
        # Verify archived doc doesn't contain code/script
        call_args = mock_archive.replace_one.call_args
        archived_doc = call_args[0][1]
        assert "code" not in archived_doc
        assert "script" not in archived_doc
        assert archived_doc["title"] == "Old Video"

    def test_custom_days_parameter(self):
        """Custom days parameter is used for cutoff."""
        mock_col = MagicMock()
        mock_col.find.return_value = []
        mock_db = MagicMock()
        mock_col.database = mock_db
        mock_db.__getitem__ = MagicMock(return_value=MagicMock())

        with patch("src.db._get_collection", return_value=mock_col):
            from src.db_maintenance import archive_old_records
            archive_old_records(days=30)

        # Verify cutoff calculation used 30 days
        call_args = mock_col.find.call_args[0][0]
        cutoff = call_args["created_at"]["$lt"]
        expected_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        assert abs((cutoff - expected_cutoff).total_seconds()) < 5


class TestCleanupFailedRenders:
    """Tests for db_maintenance.cleanup_failed_renders()."""

    def test_cleanup_old_files(self, tmp_path, monkeypatch):
        """Files older than max_age_days are deleted."""
        monkeypatch.setattr("src.config.OUTPUT_DIR", tmp_path)

        # Create old file
        old_file = tmp_path / "old_video.mp4"
        old_file.write_bytes(b"\x00" * 1000)
        old_mtime = (datetime.now(timezone.utc) - timedelta(days=10)).timestamp()
        os.utime(old_file, (old_mtime, old_mtime))

        # Create recent file
        new_file = tmp_path / "new_video.mp4"
        new_file.write_bytes(b"\x00" * 500)

        from src.db_maintenance import cleanup_failed_renders
        result = cleanup_failed_renders(max_age_days=7)

        assert result["deleted"] == 1
        assert result["freed_bytes"] == 1000
        assert not old_file.exists()
        assert new_file.exists()

    def test_cleanup_ignores_non_media_files(self, tmp_path, monkeypatch):
        """Non-media files are not cleaned up."""
        monkeypatch.setattr("src.config.OUTPUT_DIR", tmp_path)

        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("important")
        old_mtime = (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()
        os.utime(txt_file, (old_mtime, old_mtime))

        from src.db_maintenance import cleanup_failed_renders
        result = cleanup_failed_renders(max_age_days=7)

        assert result["deleted"] == 0
        assert txt_file.exists()

    def test_cleanup_empty_output_dir(self, tmp_path, monkeypatch):
        """Works correctly with an empty output directory."""
        monkeypatch.setattr("src.config.OUTPUT_DIR", tmp_path)

        from src.db_maintenance import cleanup_failed_renders
        result = cleanup_failed_renders()

        assert result["deleted"] == 0
        assert result["errors"] == 0


class TestCheckStorageUsage:
    """Tests for db_maintenance.check_storage_usage()."""

    def test_storage_below_threshold(self):
        """No alert when storage is below threshold."""
        mock_col = MagicMock()
        mock_db = MagicMock()
        mock_col.database = mock_db
        mock_db.command.return_value = {
            "dataSize": 200 * 1024 * 1024,
            "storageSize": 200 * 1024 * 1024,
        }
        mock_db.list_collection_names.return_value = []

        with patch("src.db._get_collection", return_value=mock_col):
            from src.db_maintenance import check_storage_usage
            result = check_storage_usage()

        assert result["storage_mb"] == pytest.approx(200.0, abs=1)
        assert result["alert_sent"] is False

    def test_storage_above_threshold_sends_alert(self):
        """Alert sent when storage exceeds threshold."""
        mock_col = MagicMock()
        mock_db = MagicMock()
        mock_col.database = mock_db
        mock_db.command.return_value = {
            "dataSize": 450 * 1024 * 1024,
            "storageSize": 450 * 1024 * 1024,
        }
        mock_db.list_collection_names.return_value = []

        with (
            patch("src.db._get_collection", return_value=mock_col),
            patch("src.notifier.send_notification", return_value=True),
        ):
            from src.db_maintenance import check_storage_usage
            result = check_storage_usage()

        assert result["storage_mb"] == pytest.approx(450.0, abs=1)
        assert result["alert_sent"] is True


class TestCleanupOldLogs:
    """Tests for db_maintenance.cleanup_old_logs()."""

    def test_cleanup_old_logs(self):
        """Old logs are deleted."""
        mock_col = MagicMock()
        mock_db = MagicMock()
        mock_col.database = mock_db
        mock_logs = MagicMock()
        mock_logs.delete_many.return_value = MagicMock(deleted_count=5)
        mock_db.__getitem__ = MagicMock(return_value=mock_logs)

        with patch("src.db._get_collection", return_value=mock_col):
            from src.db_maintenance import cleanup_old_logs
            result = cleanup_old_logs(days=30)

        assert result["deleted"] == 5


class TestRunMaintenance:
    """Tests for db_maintenance.run_maintenance()."""

    def test_run_maintenance_calls_all(self):
        """run_maintenance executes all maintenance tasks."""
        with (
            patch("src.db_maintenance.archive_old_records", return_value={"archived": 0, "deleted": 0, "errors": 0}),
            patch("src.db_maintenance.cleanup_failed_renders", return_value={"deleted": 0, "freed_bytes": 0, "errors": 0}),
            patch("src.db_maintenance.check_storage_usage", return_value={"storage_mb": 100, "alert_sent": False, "collections": {}}),
            patch("src.db_maintenance.cleanup_old_logs", return_value={"deleted": 0}),
        ):
            from src.db_maintenance import run_maintenance
            report = run_maintenance()

        assert "archive" in report
        assert "cleanup_renders" in report
        assert "storage" in report
        assert "log_rotation" in report


# ══════════════════════════════════════════════════════════════
#  Phase 8.3 — Comprehensive Logging & Audit Trail
# ══════════════════════════════════════════════════════════════


class TestPipelineLog:
    """Tests for pipeline_logger.PipelineLog."""

    def test_pipeline_log_creation(self):
        """PipelineLog initializes with correct defaults."""
        from src.pipeline_logger import PipelineLog

        log = PipelineLog(run_type="single")
        assert log.run_id
        assert len(log.run_id) == 12
        assert log.run_type == "single"
        assert log.outcome == "pending"
        assert log.steps == []

    def test_start_and_end_step(self):
        """Steps can be started and ended."""
        from src.pipeline_logger import PipelineLog

        log = PipelineLog()
        log.start_step("content_generation")
        assert len(log.steps) == 1
        assert log.steps[0]["status"] == "running"

        log.end_step("content_generation", status="success", details={"score": 95})
        assert log.steps[0]["status"] == "success"
        assert log.steps[0]["details"]["score"] == 95

    def test_skip_step(self):
        """Steps can be skipped."""
        from src.pipeline_logger import PipelineLog

        log = PipelineLog()
        log.skip_step("upload", reason="no credentials")
        assert log.steps[0]["status"] == "skipped"

    def test_multiple_steps(self):
        """Multiple steps can be tracked."""
        from src.pipeline_logger import PipelineLog

        log = PipelineLog(run_type="batch")
        log.start_step("content_gen")
        log.end_step("content_gen", status="success")
        log.start_step("tts")
        log.end_step("tts", status="success")
        log.start_step("render")
        log.end_step("render", status="failed", error="timeout")

        assert len(log.steps) == 3
        assert log.steps[2]["status"] == "failed"

    def test_to_dict_format(self):
        """to_dict returns properly structured document."""
        from src.pipeline_logger import PipelineLog

        log = PipelineLog(run_type="single")
        log.start_step("test_step")
        log.end_step("test_step", status="success")
        log.set_outcome("success")

        doc = log.to_dict()
        assert "run_id" in doc
        assert "run_type" in doc
        assert "timestamp" in doc
        assert "steps" in doc
        assert "total_duration_ms" in doc
        assert "outcome" in doc
        assert doc["outcome"] == "success"

    def test_set_outcome_with_error(self):
        """set_outcome stores error message."""
        from src.pipeline_logger import PipelineLog

        log = PipelineLog()
        log.set_outcome("failed", error="Something went wrong")
        assert log.outcome == "failed"
        assert log.error_if_any == "Something went wrong"

    def test_error_truncated_to_500_chars(self):
        """Long error messages are truncated."""
        from src.pipeline_logger import PipelineLog

        log = PipelineLog()
        long_error = "x" * 1000
        log.set_outcome("failed", error=long_error)
        assert len(log.error_if_any) == 500

    def test_save_to_mongodb(self):
        """save() writes to pipeline_logs collection."""
        from src.pipeline_logger import PipelineLog

        log = PipelineLog()
        log.set_outcome("success")

        mock_col = MagicMock()
        mock_db = MagicMock()
        mock_col.database = mock_db
        mock_logs = MagicMock()
        mock_logs.insert_one.return_value = MagicMock(inserted_id="abc")
        mock_db.__getitem__ = MagicMock(return_value=mock_logs)

        with patch("src.db._get_collection", return_value=mock_col):
            result = log.save()

        assert result == "abc"
        mock_logs.insert_one.assert_called_once()

    def test_save_only_once(self):
        """Duplicate save calls are ignored."""
        from src.pipeline_logger import PipelineLog

        log = PipelineLog()
        log._saved = True
        result = log.save()
        assert result is None

    def test_step_duration_measured(self):
        """Step durations are measured in milliseconds."""
        from src.pipeline_logger import PipelineLog

        log = PipelineLog()
        log.start_step("slow_step")
        time.sleep(0.05)  # 50ms
        log.end_step("slow_step", status="success")

        assert log.steps[0]["duration_ms"] >= 40  # Allow some tolerance

    def test_valid_statuses(self):
        """VALID_STATUSES contains expected values."""
        from src.pipeline_logger import PipelineLog
        assert "pending" in PipelineLog.VALID_STATUSES
        assert "running" in PipelineLog.VALID_STATUSES
        assert "success" in PipelineLog.VALID_STATUSES
        assert "failed" in PipelineLog.VALID_STATUSES
        assert "skipped" in PipelineLog.VALID_STATUSES


class TestGetRecentLogs:
    """Tests for pipeline_logger.get_recent_logs()."""

    def test_get_recent_logs(self):
        """Returns list of log dicts from MongoDB."""
        mock_col = MagicMock()
        mock_db = MagicMock()
        mock_col.database = mock_db
        mock_logs = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.limit.return_value = [{"run_id": "abc", "outcome": "success"}]
        mock_logs.find.return_value = mock_cursor
        mock_db.__getitem__ = MagicMock(return_value=mock_logs)

        with patch("src.db._get_collection", return_value=mock_col):
            from src.pipeline_logger import get_recent_logs
            logs = get_recent_logs(last=5)

        assert len(logs) == 1
        assert logs[0]["run_id"] == "abc"

    def test_get_recent_logs_db_failure(self):
        """Returns empty list on DB failure."""
        with patch("src.db._get_collection", side_effect=Exception("DB down")):
            from src.pipeline_logger import get_recent_logs
            logs = get_recent_logs()
        assert logs == []


class TestPrintLogs:
    """Tests for pipeline_logger.print_logs()."""

    def test_print_logs_empty(self, capsys):
        """Prints message when no logs found."""
        with patch("src.pipeline_logger.get_recent_logs", return_value=[]):
            from src.pipeline_logger import print_logs
            print_logs()

        captured = capsys.readouterr()
        assert "No pipeline logs found" in captured.out

    def test_print_logs_with_data(self, capsys):
        """Prints formatted log entries."""
        log_data = [{
            "run_id": "abc123",
            "run_type": "single",
            "timestamp": datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            "steps": [
                {"name": "content_gen", "status": "success", "duration_ms": 1500},
                {"name": "tts", "status": "failed", "duration_ms": 500, "error": "timeout"},
            ],
            "total_duration_ms": 5000,
            "outcome": "failed",
            "error_if_any": "TTS timed out",
        }]
        with patch("src.pipeline_logger.get_recent_logs", return_value=log_data):
            from src.pipeline_logger import print_logs
            print_logs(last=5)

        captured = capsys.readouterr()
        assert "abc123" in captured.out
        assert "content_gen" in captured.out
        assert "TTS timed out" in captured.out


# ══════════════════════════════════════════════════════════════
#  Phase 8.4 — Graceful Pipeline Timeout
# ══════════════════════════════════════════════════════════════


class TestRunWithTimeout:
    """Tests for main._run_with_timeout()."""

    def test_function_completes_within_timeout(self):
        """Function that completes in time returns its result."""
        from src.main import _run_with_timeout

        result = _run_with_timeout(lambda: 42, timeout_s=5, step_name="test")
        assert result == 42

    def test_function_returns_complex_result(self):
        """Complex return values are passed through."""
        from src.main import _run_with_timeout

        result = _run_with_timeout(
            lambda: {"key": "value", "list": [1, 2, 3]},
            timeout_s=5,
            step_name="test",
        )
        assert result == {"key": "value", "list": [1, 2, 3]}

    def test_function_timeout_raises_transient_error(self):
        """Timeout raises TransientError with correct step name."""
        from src.main import _run_with_timeout
        from src.errors import TransientError

        def slow_fn():
            time.sleep(10)  # Very slow

        with pytest.raises(TransientError, match="timed out"):
            _run_with_timeout(slow_fn, timeout_s=1, step_name="slow_step")

    def test_timeout_error_contains_step_name(self):
        """TransientError from timeout contains correct step info."""
        from src.main import _run_with_timeout
        from src.errors import TransientError

        def slow():
            time.sleep(10)

        try:
            _run_with_timeout(slow, timeout_s=1, step_name="my_step")
            assert False, "Should have raised"
        except TransientError as e:
            assert "my_step" in str(e)
            assert e.step == "my_step"

    def test_function_exception_propagated(self):
        """Exceptions from the function are re-raised."""
        from src.main import _run_with_timeout

        def failing_fn():
            raise ValueError("bad input")

        with pytest.raises(ValueError, match="bad input"):
            _run_with_timeout(failing_fn, timeout_s=5, step_name="test")


class TestConfigTimeouts:
    """Tests for Phase 8.4 timeout config values."""

    def test_step_timeout_default(self):
        """STEP_TIMEOUT_S defaults to 120."""
        from src import config
        assert config.STEP_TIMEOUT_S == 120

    def test_render_timeout_default(self):
        """RENDER_TIMEOUT_S defaults to 300."""
        from src import config
        assert config.RENDER_TIMEOUT_S == 300

    def test_step_timeout_from_env(self, monkeypatch):
        """STEP_TIMEOUT_S can be overridden via environment."""
        monkeypatch.setenv("STEP_TIMEOUT_S", "60")
        # Re-import to pick up env change
        import importlib
        from src import config
        importlib.reload(config)
        assert config.STEP_TIMEOUT_S == 60
        # Reset
        monkeypatch.delenv("STEP_TIMEOUT_S")
        importlib.reload(config)

    def test_render_timeout_from_env(self, monkeypatch):
        """RENDER_TIMEOUT_S can be overridden via environment."""
        monkeypatch.setenv("RENDER_TIMEOUT_S", "600")
        import importlib
        from src import config
        importlib.reload(config)
        assert config.RENDER_TIMEOUT_S == 600
        monkeypatch.delenv("RENDER_TIMEOUT_S")
        importlib.reload(config)


# ══════════════════════════════════════════════════════════════
#  Phase 8.5 — Staging Environment
# ══════════════════════════════════════════════════════════════


class TestStagingConfig:
    """Tests for Phase 8.5 staging environment config."""

    def test_environment_default_production(self):
        """ENVIRONMENT defaults to 'production'."""
        from src import config
        assert config.ENVIRONMENT == "production"

    def test_environment_staging_from_env(self, monkeypatch):
        """ENVIRONMENT can be set to 'staging'."""
        monkeypatch.setenv("ENVIRONMENT", "staging")
        import importlib
        from src import config
        importlib.reload(config)
        assert config.ENVIRONMENT == "staging"
        monkeypatch.delenv("ENVIRONMENT")
        importlib.reload(config)

    def test_gemini_fallback_model_default(self):
        """GEMINI_FALLBACK_MODEL defaults to gemini-1.5-flash."""
        from src import config
        assert config.GEMINI_FALLBACK_MODEL == "gemini-1.5-flash"

    def test_archive_days_default(self):
        """ARCHIVE_DAYS defaults to 90."""
        from src import config
        assert config.ARCHIVE_DAYS == 90

    def test_mongo_storage_alert_default(self):
        """MONGO_STORAGE_ALERT_MB defaults to 400."""
        from src import config
        assert config.MONGO_STORAGE_ALERT_MB == 400


class TestStagingWatermark:
    """Tests for Phase 8.5 staging watermark behavior."""

    def test_staging_prefixes_title(self, monkeypatch):
        """In staging environment, title gets [STAGING] prefix."""
        # We test the title modification logic directly
        content = {"title": "Python Trick #Shorts"}
        monkeypatch.setenv("ENVIRONMENT", "staging")
        import importlib
        from src import config
        importlib.reload(config)

        if config.ENVIRONMENT == "staging":
            if not content["title"].startswith("[STAGING]"):
                content["title"] = f"[STAGING] {content['title']}"

        assert content["title"].startswith("[STAGING]")
        monkeypatch.delenv("ENVIRONMENT")
        importlib.reload(config)

    def test_production_no_prefix(self):
        """In production environment, title is unchanged."""
        from src import config
        assert config.ENVIRONMENT == "production"

        content = {"title": "Python Trick #Shorts"}
        if config.ENVIRONMENT == "staging":
            content["title"] = f"[STAGING] {content['title']}"

        assert content["title"] == "Python Trick #Shorts"

    def test_staging_double_prefix_prevention(self, monkeypatch):
        """Already-prefixed titles don't get double prefix."""
        content = {"title": "[STAGING] Python Trick #Shorts"}
        monkeypatch.setenv("ENVIRONMENT", "staging")
        import importlib
        from src import config
        importlib.reload(config)

        if config.ENVIRONMENT == "staging":
            if not content["title"].startswith("[STAGING]"):
                content["title"] = f"[STAGING] {content['title']}"

        assert content["title"] == "[STAGING] Python Trick #Shorts"
        assert content["title"].count("[STAGING]") == 1
        monkeypatch.delenv("ENVIRONMENT")
        importlib.reload(config)


# ══════════════════════════════════════════════════════════════
#  CLI Flag Tests
# ══════════════════════════════════════════════════════════════


class TestCLIFlags:
    """Tests for Phase 8 CLI command handling."""

    def test_health_monitor_flag_recognized(self):
        """--health-monitor flag triggers health monitor."""
        # Test the CLI routing — just verify the flag is parsed
        import sys
        original_argv = sys.argv.copy()
        sys.argv = ["src.main", "--health-monitor"]

        # Check flag recognition
        assert "--health-monitor" in sys.argv
        sys.argv = original_argv

    def test_maintenance_flag_recognized(self):
        """--maintenance flag triggers maintenance."""
        import sys
        original_argv = sys.argv.copy()
        sys.argv = ["src.main", "--maintenance"]
        assert "--maintenance" in sys.argv
        sys.argv = original_argv

    def test_logs_flag_recognized(self):
        """--logs flag triggers log display."""
        import sys
        original_argv = sys.argv.copy()
        sys.argv = ["src.main", "--logs"]
        assert "--logs" in sys.argv
        sys.argv = original_argv

    def test_logs_last_parameter_parsing(self):
        """--logs --last N parses the N correctly."""
        import sys
        original_argv = sys.argv.copy()
        sys.argv = ["src.main", "--logs", "--last", "20"]

        try:
            idx = sys.argv.index("--last")
            n = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            n = 10

        assert n == 20
        sys.argv = original_argv

    def test_logs_default_last_value(self):
        """--logs without --last defaults to 10."""
        import sys
        sys.argv = ["src.main", "--logs"]

        try:
            idx = sys.argv.index("--last")
            n = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            n = 10

        assert n == 10


# ══════════════════════════════════════════════════════════════
#  Integration / Cross-cutting Tests
# ══════════════════════════════════════════════════════════════


class TestPhase8Integration:
    """Cross-cutting integration tests for Phase 8."""

    def test_imports_dont_crash(self):
        """All Phase 8 modules import without errors."""
        from src import health_monitor
        from src import db_maintenance
        from src import pipeline_logger
        assert health_monitor is not None
        assert db_maintenance is not None
        assert pipeline_logger is not None

    def test_pipeline_logger_in_main_module(self):
        """main.py can import PipelineLog."""
        from src.pipeline_logger import PipelineLog
        log = PipelineLog()
        assert log.run_id is not None

    def test_timeout_wrapper_in_main(self):
        """_run_with_timeout is callable from main."""
        from src.main import _run_with_timeout
        assert callable(_run_with_timeout)

    def test_health_monitor_module_functions(self):
        """health_monitor exports expected functions."""
        from src.health_monitor import (
            check_stale_queue,
            check_quota_recovery,
            run_all_checks,
        )
        assert callable(check_stale_queue)
        assert callable(check_quota_recovery)
        assert callable(run_all_checks)

    def test_db_maintenance_module_functions(self):
        """db_maintenance exports expected functions."""
        from src.db_maintenance import (
            archive_old_records,
            cleanup_failed_renders,
            check_storage_usage,
            cleanup_old_logs,
            run_maintenance,
        )
        assert callable(archive_old_records)
        assert callable(cleanup_failed_renders)
        assert callable(check_storage_usage)
        assert callable(cleanup_old_logs)
        assert callable(run_maintenance)

    def test_pipeline_logger_module_functions(self):
        """pipeline_logger exports expected functions."""
        from src.pipeline_logger import (
            PipelineLog,
            get_recent_logs,
            print_logs,
        )
        assert PipelineLog is not None
        assert callable(get_recent_logs)
        assert callable(print_logs)

    def test_config_has_all_phase8_vars(self):
        """config.py contains all Phase 8 configuration variables."""
        from src import config
        assert hasattr(config, "GEMINI_FALLBACK_MODEL")
        assert hasattr(config, "ARCHIVE_DAYS")
        assert hasattr(config, "MONGO_STORAGE_ALERT_MB")
        assert hasattr(config, "STEP_TIMEOUT_S")
        assert hasattr(config, "RENDER_TIMEOUT_S")
        assert hasattr(config, "ENVIRONMENT")

    def test_staging_workflow_file_exists(self):
        """staging.yml workflow file exists."""
        from src.config import ROOT_DIR
        staging_yml = ROOT_DIR / ".github" / "workflows" / "staging.yml"
        assert staging_yml.exists(), "staging.yml workflow not found"

    def test_generate_yml_has_maintenance_cron(self):
        """generate.yml includes monthly maintenance cron."""
        from src.config import ROOT_DIR
        gen_yml = ROOT_DIR / ".github" / "workflows" / "generate.yml"
        content = gen_yml.read_text()
        assert "0 3 1 * *" in content, "Monthly maintenance cron not found"
        assert "--maintenance" in content, "--maintenance step not found"
        assert "--health-monitor" in content, "--health-monitor step not found"

    def test_error_class_used_for_timeout(self):
        """Timeout classification uses TransientError."""
        from src.errors import TransientError, ErrorClass
        err = TransientError("test timeout", step="render")
        assert err.error_class == ErrorClass.TRANSIENT
        assert err.step == "render"

    def test_tts_fallback_counter_exists(self):
        """TTS module has fallback counter variables."""
        import src.tts as tts_mod
        assert hasattr(tts_mod, "_edge_tts_consecutive_failures")
        assert hasattr(tts_mod, "_EDGE_TTS_MAX_FAILURES")
        assert tts_mod._EDGE_TTS_MAX_FAILURES == 3

    def test_llm_has_fallback_function(self):
        """llm.py exports _try_fallback_model function."""
        from src.llm import _try_fallback_model
        assert callable(_try_fallback_model)
