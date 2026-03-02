"""
Tests for Phase 4.2 — Content Scheduling.
Covers: slot calculation, scheduler CRUD, batch_pipeline, upload_queue_pipeline.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.scheduler import (
    PEAK_SLOTS_UTC, STATUS_PENDING, STATUS_DONE, STATUS_FAILED,
    next_available_slots,
)


# ──────────────────────────────────────────────────────────────
#  next_available_slots — pure logic (mock out DB)
# ──────────────────────────────────────────────────────────────
class TestNextAvailableSlots:
    def _mock_col(self, occupied=()):
        """Build a fake collection whose find() returns occupied docs."""
        col = MagicMock()
        col.find.return_value = [{"publish_at": ts} for ts in occupied]
        return col

    def test_returns_requested_count(self):
        with patch("src.scheduler._get_sched_collection", return_value=self._mock_col()):
            slots = next_available_slots(3)
        assert len(slots) == 3

    def test_all_slots_in_future(self):
        now = datetime.now(timezone.utc)
        with patch("src.scheduler._get_sched_collection", return_value=self._mock_col()):
            slots = next_available_slots(3)
        assert all(s > now for s in slots)

    def test_slots_sorted_ascending(self):
        with patch("src.scheduler._get_sched_collection", return_value=self._mock_col()):
            slots = next_available_slots(5)
        assert slots == sorted(slots)

    def test_slots_are_peak_hours(self):
        """Every slot should land on one of the defined peak hours."""
        peak_hours = {h for h, _ in PEAK_SLOTS_UTC}
        with patch("src.scheduler._get_sched_collection", return_value=self._mock_col()):
            slots = next_available_slots(6)
        for s in slots:
            assert s.hour in peak_hours, f"{s} is not a peak hour"

    def test_occupied_slots_are_skipped(self):
        """If a slot is already occupied, it should not be returned."""
        # find the next slot manually
        with patch("src.scheduler._get_sched_collection", return_value=self._mock_col()):
            first_slot = next_available_slots(1)[0]

        # Now mark that slot as occupied
        occupied_col = self._mock_col(occupied=[first_slot])
        with patch("src.scheduler._get_sched_collection", return_value=occupied_col):
            slots = next_available_slots(1)

        assert first_slot not in slots

    def test_zero_n_returns_empty(self):
        slots = next_available_slots(0)
        assert slots == []

    def test_slots_have_zero_seconds(self):
        """Peak slots should have second=0 and microsecond=0."""
        with patch("src.scheduler._get_sched_collection", return_value=self._mock_col()):
            slots = next_available_slots(3)
        for s in slots:
            assert s.second == 0
            assert s.microsecond == 0


# ──────────────────────────────────────────────────────────────
#  Scheduler CRUD — MongoDB mocked
# ──────────────────────────────────────────────────────────────
class TestSchedulerCrud:
    @pytest.fixture(autouse=True)
    def _mock_col(self):
        self.col = MagicMock()
        self.col.insert_one.return_value.inserted_id = "64aabbcc1234"
        with patch("src.scheduler._get_sched_collection", return_value=self.col):
            yield

    # ── add_to_schedule ──────────────────────────────────────
    def test_add_stores_correct_fields(self):
        from src.scheduler import add_to_schedule
        slot = datetime(2026, 3, 5, 13, 0, tzinfo=timezone.utc)
        content = {
            "title": "Python Tips",
            "script": "Hello world",
            "language": "python",
            "hashtags": ["#Python"],
            "content_type": "tip",
            "code": "print('hi')",
        }
        add_to_schedule(content, "/tmp/v.mp4", "/tmp/a.mp3", slot, 75.0)

        doc = self.col.insert_one.call_args[0][0]
        assert doc["title"] == "Python Tips"
        assert doc["status"] == STATUS_PENDING
        assert doc["publish_at"] == slot
        assert doc["video_path"] == "/tmp/v.mp4"
        assert doc["quality_score"] == 75.0

    def test_add_returns_id_string(self):
        from src.scheduler import add_to_schedule
        slot = datetime(2026, 3, 5, 13, 0, tzinfo=timezone.utc)
        doc_id = add_to_schedule({}, "/tmp/v.mp4", "/tmp/a.mp3", slot)
        assert isinstance(doc_id, str)

    # ── get_due_jobs ─────────────────────────────────────────
    def test_get_due_jobs_queries_pending_before_now(self):
        from src.scheduler import get_due_jobs
        self.col.find.return_value = []
        get_due_jobs(limit=3)
        find_filter = self.col.find.call_args[0][0]
        assert find_filter["status"] == STATUS_PENDING
        assert "$lte" in find_filter["publish_at"]

    def test_get_due_jobs_respects_limit(self):
        from src.scheduler import get_due_jobs
        self.col.find.return_value = []
        get_due_jobs(limit=2)
        assert self.col.find.call_args[1]["limit"] == 2

    # ── get_pending_count ────────────────────────────────────
    def test_get_pending_count_queries_future(self):
        from src.scheduler import get_pending_count
        self.col.count_documents.return_value = 4
        count = get_pending_count()
        assert count == 4
        query = self.col.count_documents.call_args[0][0]
        assert query["status"] == STATUS_PENDING
        assert "$gt" in query["publish_at"]

    # ── mark_job_done ────────────────────────────────────────
    def test_mark_job_done_sets_status(self):
        from bson import ObjectId
        from src.scheduler import mark_job_done
        mark_job_done(ObjectId(), {"youtube": "vid123"})
        update = self.col.update_one.call_args[0][1]
        assert update["$set"]["status"] == STATUS_DONE
        assert update["$set"]["upload_results"] == {"youtube": "vid123"}

    # ── mark_job_failed ──────────────────────────────────────
    def test_mark_job_failed_sets_status(self):
        from bson import ObjectId
        from src.scheduler import mark_job_failed
        mark_job_failed(ObjectId(), "Some error", increment_retry=False)
        update = self.col.update_one.call_args[0][1]
        assert update["$set"]["status"] == STATUS_FAILED

    def test_mark_job_failed_increments_retry(self):
        from bson import ObjectId
        from src.scheduler import mark_job_failed
        mark_job_failed(ObjectId(), "fail", increment_retry=True)
        update = self.col.update_one.call_args[0][1]
        assert update["$inc"]["retry_count"] == 1

    # ── get_schedule_summary ─────────────────────────────────
    def test_get_schedule_summary_returns_all_keys(self):
        from src.scheduler import get_schedule_summary
        self.col.count_documents.return_value = 2
        summary = get_schedule_summary()
        assert set(summary.keys()) == {
            "pending_due", "pending_future", "done_today", "failed_total"
        }


# ──────────────────────────────────────────────────────────────
#  batch_pipeline — integration-style (all services mocked)
# ──────────────────────────────────────────────────────────────
FAKE_CONTENT = {
    "title": "Go Goroutines #Shorts",
    "script": " ".join(["word"] * 45),
    "code": "\n".join([f"    line{i} = {i}" for i in range(8)]),
    "language": "go",
    "hashtags": ["#Go", "#Golang", "#Coding", "#Tips", "#Shorts"],
    "content_type": "tip",
    "expected_output": "",
    "quiz_answer": "",
    "code_before": "",
}


@pytest.fixture
def _mock_batch(monkeypatch):
    import src.config as _cfg
    monkeypatch.setattr(_cfg, "GEMINI_API_KEY", "fake")
    monkeypatch.setattr(_cfg, "MONGODB_URI", "mongodb://fake")

    fake_slot = datetime(2026, 3, 6, 13, 0, tzinfo=timezone.utc)

    with (
        patch("src.llm.generate_content", return_value=FAKE_CONTENT),
        patch("src.tts.generate_speech") as m_tts,
        patch("src.video.create_video", return_value="/tmp/v.mp4"),
        patch("src.video.verify_video", return_value={"passed": True, "checks": {}, "errors": []}),
        patch("src.db.check_code_similarity", return_value={"is_duplicate": False, "max_similarity": 0.0, "similar_to": ""}),
        patch("src.db.get_language_frequency", return_value={"suggested_avoid": [], "recent_types": []}),
        patch("src.code_runner.get_output_for_content", return_value=None),
        patch("src.scheduler.next_available_slots", return_value=[fake_slot]),
        patch("src.scheduler.add_to_schedule", return_value="abc123") as m_add,
    ):
        m_tts.return_value = ("/tmp/a.mp3", [{"text": "Hello", "start_s": 0.0, "end_s": 0.5}])
        yield {"add_to_schedule": m_add, "slot": fake_slot}


class TestBatchPipeline:
    def test_batch_queues_one_video(self, _mock_batch):
        from src.main import batch_pipeline
        queued = batch_pipeline(1)
        assert queued == 1
        _mock_batch["add_to_schedule"].assert_called_once()

    def test_batch_uses_correct_slot(self, _mock_batch):
        from src.main import batch_pipeline
        batch_pipeline(1)
        call_kwargs = _mock_batch["add_to_schedule"].call_args[1]
        assert call_kwargs["publish_at"] == _mock_batch["slot"]

    def test_batch_skips_unsafe_content(self, _mock_batch, monkeypatch):
        unsafe = FAKE_CONTENT.copy()
        unsafe["title"] = "How to make a bomb #Shorts"
        with patch("src.llm.generate_content", return_value=unsafe):
            from src.main import batch_pipeline
            queued = batch_pipeline(1)
        assert queued == 0

    def test_batch_skips_failed_video(self, _mock_batch):
        with patch("src.video.verify_video", return_value={"passed": False, "checks": {}, "errors": ["too small"]}):
            from src.main import batch_pipeline
            queued = batch_pipeline(1)
        assert queued == 0


# ──────────────────────────────────────────────────────────────
#  upload_queue_pipeline — integration-style (all services mocked)
# ──────────────────────────────────────────────────────────────
from src.uploader_base import UploadResult  # noqa: E402


@pytest.fixture
def _mock_queue(monkeypatch, tmp_path):
    import src.config as _cfg
    monkeypatch.setattr(_cfg, "GEMINI_API_KEY", "fake")
    monkeypatch.setattr(_cfg, "MONGODB_URI", "mongodb://fake")

    # Create a real temp video file so os.path.exists passes
    video_file = tmp_path / "video.mp4"
    video_file.write_bytes(b"fake")

    fake_job = {
        "_id": "job001",
        "title": "Test Short",
        "script": "test script",
        "language": "python",
        "hashtags": ["#Python"],
        "content_type": "tip",
        "video_path": str(video_file),
        "audio_path": "/tmp/fake.mp3",
        "quality_score": 80,
    }

    fake_uploader = MagicMock()
    fake_uploader.name = "youtube"
    fake_uploader.upload.return_value = UploadResult(
        platform="youtube", success=True, video_id="yt_abc", url="https://youtube.com/shorts/yt_abc"
    )

    with (
        patch("src.scheduler.get_due_jobs", return_value=[fake_job]) as m_due,
        patch("src.scheduler.mark_job_done") as m_done,
        patch("src.scheduler.mark_job_failed") as m_failed,
        patch("src.scheduler.get_schedule_summary", return_value={"pending_due": 0, "pending_future": 2, "done_today": 1, "failed_total": 0}),
        patch("src.uploader_base.get_uploaders", return_value=[fake_uploader]),
        patch("src.db.save_record", return_value="saved_id"),
        patch("src.notifier.send_notification"),
        patch("src.tts.get_audio_duration", return_value=15.0),
    ):
        yield {"due": m_due, "done": m_done, "failed": m_failed, "uploader": fake_uploader, "job": fake_job}


class TestUploadQueuePipeline:
    def test_uploads_due_job(self, _mock_queue):
        from src.main import upload_queue_pipeline
        result = upload_queue_pipeline()
        assert result == 1
        _mock_queue["uploader"].upload.assert_called_once()

    def test_marks_job_done_on_success(self, _mock_queue):
        from src.main import upload_queue_pipeline
        upload_queue_pipeline()
        _mock_queue["done"].assert_called_once_with("job001", {"youtube": "yt_abc"})

    def test_marks_job_failed_when_all_fail(self, _mock_queue):
        _mock_queue["uploader"].upload.return_value = UploadResult(
            platform="youtube", success=False, error="timeout"
        )
        from src.main import upload_queue_pipeline
        result = upload_queue_pipeline()
        assert result == 0
        _mock_queue["failed"].assert_called_once()

    def test_skips_missing_video_file(self, _mock_queue):
        _mock_queue["due"].return_value = [{**_mock_queue["job"], "video_path": "/nonexistent/video.mp4"}]
        from src.main import upload_queue_pipeline
        result = upload_queue_pipeline()
        assert result == 0
        _mock_queue["failed"].assert_called_once()

    def test_no_due_jobs_returns_zero(self, _mock_queue):
        _mock_queue["due"].return_value = []
        from src.main import upload_queue_pipeline
        result = upload_queue_pipeline()
        assert result == 0
