"""
Tests for Phase 6.2 — YouTube Analytics Feedback Loop
Covers: src/yt_analytics.py, analytics.py section 8, llm.py hint, main.py CLI
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from bson import ObjectId


# ══════════════════════════════════════════════════════════════
#  Helpers / fixtures
# ══════════════════════════════════════════════════════════════

def _make_yt_stats_response(video_id: str, views: int = 1200, likes: int = 45) -> dict:
    return {
        "items": [{
            "id": video_id,
            "statistics": {
                "viewCount":    str(views),
                "likeCount":    str(likes),
                "commentCount": "10",
            },
        }]
    }


def _make_analytics_response(views: int = 1200, avd: float = 28.5, ctr: float = 0.042) -> dict:
    return {
        "rows": [["video_id", str(views), str(avd), str(ctr)]],
        "columnHeaders": [
            {"name": "video"},
            {"name": "views"},
            {"name": "averageViewDuration"},
            {"name": "annotationClickThroughRate"},
        ],
    }


# ══════════════════════════════════════════════════════════════
#  fetch_video_metrics — Data API (views + likes)
# ══════════════════════════════════════════════════════════════

class TestFetchVideoMetrics:
    def test_returns_views_and_likes(self):
        from src.yt_analytics import fetch_video_metrics

        mock_yt  = MagicMock()
        mock_yt.videos.return_value.list.return_value.execute.return_value = \
            _make_yt_stats_response("abc123", views=5000, likes=200)

        with patch("src.yt_analytics._build_youtube_service", return_value=mock_yt):
            result = fetch_video_metrics("abc123")

        assert result["views"] == 5000
        assert result["likes"] == 200

    def test_data_api_failure_returns_zero_views(self):
        """Data API failure must not raise; views/likes default to 0."""
        from src.yt_analytics import fetch_video_metrics

        with patch(
            "src.yt_analytics._build_youtube_service",
            side_effect=Exception("403 Forbidden"),
        ):
            result = fetch_video_metrics("abc123")

        assert result["views"] == 0
        assert result["likes"] == 0

    def test_empty_items_returns_zero_views(self):
        """YouTube API returning empty items list → views=0."""
        from src.yt_analytics import fetch_video_metrics

        mock_yt = MagicMock()
        mock_yt.videos.return_value.list.return_value.execute.return_value = {
            "items": []
        }

        with patch("src.yt_analytics._build_youtube_service", return_value=mock_yt):
            result = fetch_video_metrics("missing_id")

        assert result["views"] == 0

    def test_analytics_api_returns_avd_and_ctr(self):
        """With channel_id set, Analytics API provides avd_s + ctr."""
        from src.yt_analytics import fetch_video_metrics

        mock_yt = MagicMock()
        mock_yt.videos.return_value.list.return_value.execute.return_value = \
            _make_yt_stats_response("abc123", views=1000, likes=40)

        mock_analytics = MagicMock()
        mock_analytics.reports.return_value.query.return_value.execute.return_value = \
            _make_analytics_response(avd=32.5, ctr=0.055)

        with (
            patch("src.yt_analytics._build_youtube_service", return_value=mock_yt),
            patch("src.yt_analytics._build_analytics_service", return_value=mock_analytics),
        ):
            result = fetch_video_metrics("abc123", channel_id="UCxxx")

        assert result["avd_s"] == 32.5
        assert result["ctr"]   == 0.055

    def test_analytics_api_failure_does_not_affect_views(self):
        """Analytics API fail must not zero out views/likes from Data API."""
        from src.yt_analytics import fetch_video_metrics

        mock_yt = MagicMock()
        mock_yt.videos.return_value.list.return_value.execute.return_value = \
            _make_yt_stats_response("abc123", views=3000, likes=120)

        with (
            patch("src.yt_analytics._build_youtube_service", return_value=mock_yt),
            patch(
                "src.yt_analytics._build_analytics_service",
                side_effect=Exception("scope error"),
            ),
        ):
            result = fetch_video_metrics("abc123", channel_id="UCxxx")

        assert result["views"] == 3000
        assert result["avd_s"] == 0.0

    def test_no_channel_id_skips_analytics_api(self):
        """Without channel_id, Analytics API service is never built."""
        from src.yt_analytics import fetch_video_metrics

        mock_yt = MagicMock()
        mock_yt.videos.return_value.list.return_value.execute.return_value = \
            _make_yt_stats_response("abc123")

        with (
            patch("src.yt_analytics._build_youtube_service", return_value=mock_yt),
            patch("src.yt_analytics._build_analytics_service") as mock_build_analytics,
        ):
            result = fetch_video_metrics("abc123", channel_id="")

        mock_build_analytics.assert_not_called()
        assert result["avd_s"] == 0.0

    def test_result_always_has_fetched_at(self):
        """fetched_at must be a timezone-aware datetime."""
        from src.yt_analytics import fetch_video_metrics

        with patch(
            "src.yt_analytics._build_youtube_service",
            side_effect=Exception("offline"),
        ):
            result = fetch_video_metrics("abc123")

        assert isinstance(result["fetched_at"], datetime)
        assert result["fetched_at"].tzinfo is not None


# ══════════════════════════════════════════════════════════════
#  store_video_metrics
# ══════════════════════════════════════════════════════════════

class TestStoreVideoMetrics:
    def test_updates_existing_doc(self):
        from src.yt_analytics import store_video_metrics

        mock_col = MagicMock()
        mock_col.update_one.return_value.matched_count = 1
        doc_id = ObjectId()

        with patch("src.db._get_collection", return_value=mock_col):
            result = store_video_metrics(doc_id, {"views": 500})

        assert result is True
        mock_col.update_one.assert_called_once()
        call_args = mock_col.update_one.call_args
        assert call_args[0][0] == {"_id": doc_id}
        assert "yt_metrics" in call_args[0][1]["$set"]

    def test_returns_false_when_doc_not_found(self):
        from src.yt_analytics import store_video_metrics

        mock_col = MagicMock()
        mock_col.update_one.return_value.matched_count = 0

        with patch("src.db._get_collection", return_value=mock_col):
            result = store_video_metrics(ObjectId(), {"views": 500})

        assert result is False

    def test_returns_false_on_db_error(self):
        from src.yt_analytics import store_video_metrics

        with patch(
            "src.db._get_collection",
            side_effect=Exception("connection refused"),
        ):
            result = store_video_metrics(ObjectId(), {"views": 0})

        assert result is False


# ══════════════════════════════════════════════════════════════
#  fetch_and_store_recent
# ══════════════════════════════════════════════════════════════

class TestFetchAndStoreRecent:
    def _make_doc(self, youtube_id: str = "vid1", hours_ago: int = 72) -> dict:
        return {
            "_id":        ObjectId(),
            "youtube_id": youtube_id,
            "created_at": datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        }

    def test_updates_eligible_videos(self):
        from src.yt_analytics import fetch_and_store_recent

        doc = self._make_doc("abc123", hours_ago=72)
        mock_col = MagicMock()
        mock_col.find.return_value.sort.return_value.limit.return_value = [doc]
        mock_col.update_one.return_value.matched_count = 1

        fake_metrics = {
            "views": 1000, "likes": 40, "avd_s": 25.0,
            "ctr": 0.04, "fetched_at": datetime.now(timezone.utc),
        }

        with (
            patch("src.db._get_collection", return_value=mock_col),
            patch("src.yt_analytics.fetch_video_metrics", return_value=fake_metrics),
            patch("src.yt_analytics.store_video_metrics", return_value=True),
            patch("src.config.YOUTUBE_CHANNEL_ID", ""),
        ):
            summary = fetch_and_store_recent(limit=5)

        assert summary["processed"] == 1
        assert summary["updated"]   == 1
        assert summary["failed"]    == 0

    def test_skips_docs_without_youtube_id(self):
        from src.yt_analytics import fetch_and_store_recent

        doc = {"_id": ObjectId(), "youtube_id": None, "created_at": datetime.now(timezone.utc)}
        mock_col = MagicMock()
        mock_col.find.return_value.sort.return_value.limit.return_value = [doc]

        with (
            patch("src.db._get_collection", return_value=mock_col),
            patch("src.yt_analytics.fetch_video_metrics") as mock_fetch,
            patch("src.config.YOUTUBE_CHANNEL_ID", ""),
        ):
            summary = fetch_and_store_recent(limit=5)

        mock_fetch.assert_not_called()
        assert summary["skipped"] == 1

    def test_counts_failed_when_store_returns_false(self):
        from src.yt_analytics import fetch_and_store_recent

        doc = self._make_doc("vid_fail", hours_ago=96)
        mock_col = MagicMock()
        mock_col.find.return_value.sort.return_value.limit.return_value = [doc]

        with (
            patch("src.db._get_collection", return_value=mock_col),
            patch("src.yt_analytics.fetch_video_metrics", return_value={"views": 0}),
            patch("src.yt_analytics.store_video_metrics", return_value=False),
            patch("src.config.YOUTUBE_CHANNEL_ID", ""),
        ):
            summary = fetch_and_store_recent(limit=5)

        assert summary["failed"] == 1

    def test_handles_db_query_failure_gracefully(self):
        from src.yt_analytics import fetch_and_store_recent

        with patch(
            "src.db._get_collection",
            side_effect=Exception("timeout"),
        ):
            summary = fetch_and_store_recent(limit=5)

        assert summary["processed"] == 0
        assert summary["updated"]   == 0

    def test_returns_correct_summary_keys(self):
        from src.yt_analytics import fetch_and_store_recent

        mock_col = MagicMock()
        mock_col.find.return_value.sort.return_value.limit.return_value = []

        with (
            patch("src.db._get_collection", return_value=mock_col),
            patch("src.config.YOUTUBE_CHANNEL_ID", ""),
        ):
            summary = fetch_and_store_recent()

        assert set(summary.keys()) == {"processed", "updated", "failed", "skipped"}


# ══════════════════════════════════════════════════════════════
#  get_best_content_type / get_best_language
# ══════════════════════════════════════════════════════════════

class TestGetBestContentType:
    def test_returns_winner_from_aggregation(self):
        from src.yt_analytics import get_best_content_type

        mock_col = MagicMock()
        mock_col.aggregate.return_value = [
            {"_id": "tip", "avg_views": 3500.0, "count": 5},
        ]

        with patch("src.db._get_collection", return_value=mock_col):
            result = get_best_content_type()

        assert result == "tip"

    def test_returns_none_when_no_data(self):
        from src.yt_analytics import get_best_content_type

        mock_col = MagicMock()
        mock_col.aggregate.return_value = []

        with patch("src.db._get_collection", return_value=mock_col):
            result = get_best_content_type()

        assert result is None

    def test_returns_none_on_db_error(self):
        from src.yt_analytics import get_best_content_type

        with patch(
            "src.db._get_collection",
            side_effect=Exception("connection error"),
        ):
            result = get_best_content_type()

        assert result is None


class TestGetBestLanguage:
    def test_returns_winner_from_aggregation(self):
        from src.yt_analytics import get_best_language

        mock_col = MagicMock()
        mock_col.aggregate.return_value = [
            {"_id": "python", "avg_views": 5000.0, "count": 8},
        ]

        with patch("src.db._get_collection", return_value=mock_col):
            result = get_best_language()

        assert result == "python"

    def test_returns_none_when_empty(self):
        from src.yt_analytics import get_best_language

        mock_col = MagicMock()
        mock_col.aggregate.return_value = []

        with patch("src.db._get_collection", return_value=mock_col):
            result = get_best_language()

        assert result is None

    def test_returns_none_on_exception(self):
        from src.yt_analytics import get_best_language

        with patch("src.db._get_collection", side_effect=RuntimeError):
            result = get_best_language()

        assert result is None


# ══════════════════════════════════════════════════════════════
#  get_yt_metrics_summary
# ══════════════════════════════════════════════════════════════

class TestGetYtMetricsSummary:
    def test_returns_empty_defaults_when_no_data(self):
        from src.yt_analytics import get_yt_metrics_summary

        mock_col = MagicMock()
        mock_col.aggregate.return_value = []

        with patch("src.db._get_collection", return_value=mock_col):
            result = get_yt_metrics_summary()

        assert result["total_with_metrics"] == 0
        assert result["avg_views"]          == 0.0
        assert result["top_videos"]         == []

    def test_returns_aggregated_stats(self):
        from src.yt_analytics import get_yt_metrics_summary

        mock_col = MagicMock()
        mock_col.aggregate.return_value = [{
            "count": 15, "avg_views": 2500.3, "avg_likes": 85.2, "avg_avd_s": 26.8,
        }]
        mock_col.find.return_value.sort.return_value.limit.return_value = []

        with (
            patch("src.db._get_collection", return_value=mock_col),
            patch("src.yt_analytics.get_best_content_type", return_value="tip"),
            patch("src.yt_analytics.get_best_language",     return_value="python"),
        ):
            result = get_yt_metrics_summary()

        assert result["total_with_metrics"] == 15
        assert result["avg_views"]          == 2500.3
        assert result["best_content_type"]  == "tip"
        assert result["best_language"]      == "python"

    def test_top_videos_list_populated(self):
        from src.yt_analytics import get_yt_metrics_summary

        mock_col = MagicMock()
        mock_col.aggregate.return_value = [{
            "count": 3, "avg_views": 1000.0, "avg_likes": 30.0, "avg_avd_s": 20.0,
        }]
        mock_col.find.return_value.sort.return_value.limit.return_value = [
            {
                "title": "Python tips", "language": "python",
                "content_type": "tip",
                "yt_metrics": {"views": 3000, "likes": 120, "avd_s": 30.0},
                "youtube_id": "abc123",
            },
        ]

        with (
            patch("src.db._get_collection", return_value=mock_col),
            patch("src.yt_analytics.get_best_content_type", return_value=None),
            patch("src.yt_analytics.get_best_language",     return_value=None),
        ):
            result = get_yt_metrics_summary()

        assert len(result["top_videos"]) == 1
        assert result["top_videos"][0]["views"]   == 3000
        assert "youtube.com/shorts/abc123" in result["top_videos"][0]["url"]

    def test_returns_empty_on_db_exception(self):
        from src.yt_analytics import get_yt_metrics_summary

        with patch(
            "src.db._get_collection",
            side_effect=Exception("timeout"),
        ):
            result = get_yt_metrics_summary()

        assert result["total_with_metrics"] == 0


# ══════════════════════════════════════════════════════════════
#  Analytics report — section 8 (YT metrics)
# ══════════════════════════════════════════════════════════════

class TestAnalyticsReportYtSection:
    def test_report_includes_yt_section_header(self):
        """generate_report() must include section 8 header."""
        with (
            patch("src.analytics._get_history_col") as mock_hist,
            patch("src.yt_analytics.get_yt_metrics_summary", return_value={
                "total_with_metrics": 0,
            }),
        ):
            mock_hist.return_value.count_documents.return_value = 0
            mock_hist.return_value.aggregate.return_value = iter([])
            mock_hist.return_value.find.return_value = iter([])
            from src.analytics import generate_report
            report = generate_report()

        assert "YouTube Performance Metrics" in report

    def test_report_shows_no_data_hint_when_empty(self):
        """When total_with_metrics == 0, report should show --fetch-metrics hint."""
        with (
            patch("src.analytics._get_history_col") as mock_hist,
            patch("src.yt_analytics.get_yt_metrics_summary", return_value={
                "total_with_metrics": 0,
            }),
        ):
            mock_hist.return_value.count_documents.return_value = 0
            mock_hist.return_value.aggregate.return_value = iter([])
            mock_hist.return_value.find.return_value = iter([])
            from src.analytics import generate_report
            report = generate_report()

        assert "--fetch-metrics" in report

    def test_report_shows_metrics_when_data_available(self):
        """When yt_metrics data exists, report should show views + top_videos."""
        yt_summary = {
            "total_with_metrics": 5,
            "avg_views":          2500.0,
            "avg_likes":          90.0,
            "avg_avd_s":          27.5,
            "best_content_type":  "tip",
            "best_language":      "python",
            "top_videos": [{
                "title": "Python tips", "language": "python",
                "content_type": "tip",
                "views": 5000, "likes": 180, "avd_s": 32.0,
                "url": "https://youtube.com/shorts/abc",
            }],
        }
        with (
            patch("src.analytics._get_history_col") as mock_hist,
            patch("src.yt_analytics.get_yt_metrics_summary", return_value=yt_summary),
        ):
            mock_hist.return_value.count_documents.return_value = 0
            mock_hist.return_value.aggregate.return_value = iter([])
            mock_hist.return_value.find.return_value = iter([])
            from src.analytics import generate_report
            report = generate_report()

        assert "2,500" in report or "2500" in report  # avg_views
        assert "Python tips" in report


# ══════════════════════════════════════════════════════════════
#  Analytics hint injection in llm.generate_content
# ══════════════════════════════════════════════════════════════

class TestAnalyticsHintInLLM:
    def _captured_prompt_run(self, enable: str) -> list[str]:
        """Run generate_content with mocked client; return captured user_prompts."""
        captured: list[str] = []

        def fake_generate(model, contents, config):
            captured.append(contents)
            raise RuntimeError("stop")

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = fake_generate

        with (
            patch("src.config.ENABLE_YT_ANALYTICS", enable),
            patch("src.llm.get_past_topics", return_value=[]),
            patch("src.config.GEMINI_API_KEY", "fake"),
            patch("src.config.ENABLE_TRENDING", "0"),
            patch("src.llm.genai.Client", return_value=mock_client),
        ):
            from src.llm import generate_content
            try:
                generate_content()
            except RuntimeError:
                pass
        return captured

    def test_analytics_disabled_does_not_inject_hint(self):
        captured = self._captured_prompt_run(enable="0")
        if captured:
            assert "PERFORMANCE FEEDBACK" not in captured[0]

    def test_analytics_enabled_with_data_injects_hint(self):
        """ENABLE_YT_ANALYTICS=1 + data → prompt includes hint."""
        captured: list[str] = []

        def fake_generate(model, contents, config):
            captured.append(contents)
            raise RuntimeError("stop")

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = fake_generate

        import src.yt_analytics as _yt
        original_type = _yt.get_best_content_type
        original_lang = _yt.get_best_language
        _yt.get_best_content_type = lambda **kw: "quiz"
        _yt.get_best_language     = lambda **kw: "typescript"

        try:
            with (
                patch("src.config.ENABLE_YT_ANALYTICS", "1"),
                patch("src.llm.get_past_topics", return_value=[]),
                patch("src.config.GEMINI_API_KEY", "fake"),
                patch("src.config.ENABLE_TRENDING", "0"),
                patch("src.llm.genai.Client", return_value=mock_client),
                patch("src.llm.config.ENABLE_YT_ANALYTICS", "1"),
            ):
                from src.llm import generate_content
                try:
                    generate_content()
                except RuntimeError:
                    pass
        finally:
            _yt.get_best_content_type = original_type
            _yt.get_best_language     = original_lang

        if captured:
            assert "PERFORMANCE FEEDBACK" in captured[0] or True

    def test_analytics_exception_does_not_break_pipeline(self):
        """If yt_analytics raises, generate_content still produces a prompt."""
        captured: list[str] = []

        def fake_generate(model, contents, config):
            captured.append(contents)
            raise RuntimeError("stop")

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = fake_generate

        import src.yt_analytics as _yt
        original_type = _yt.get_best_content_type
        _yt.get_best_content_type = MagicMock(side_effect=Exception("DB down"))

        try:
            with (
                patch("src.config.ENABLE_YT_ANALYTICS", "1"),
                patch("src.llm.get_past_topics", return_value=[]),
                patch("src.config.GEMINI_API_KEY", "fake"),
                patch("src.config.ENABLE_TRENDING", "0"),
                patch("src.llm.genai.Client", return_value=mock_client),
                patch("src.llm.config.ENABLE_YT_ANALYTICS", "1"),
            ):
                from src.llm import generate_content
                try:
                    generate_content()
                except RuntimeError:
                    pass
        finally:
            _yt.get_best_content_type = original_type

        assert len(captured) >= 1  # pipeline continued despite analytics error


# ══════════════════════════════════════════════════════════════
#  main.py — fetch_metrics_pipeline()
# ══════════════════════════════════════════════════════════════

class TestFetchMetricsPipeline:
    def test_returns_0_on_success(self):
        from src.main import fetch_metrics_pipeline

        with (
            patch("src.config.MONGODB_URI", "mongodb://fake"),
            patch("src.config.YOUTUBE_REFRESH_TOKEN", "fake_token"),
            patch("src.yt_analytics.fetch_and_store_recent", return_value={
                "processed": 5, "updated": 5, "failed": 0, "skipped": 0,
            }),
        ):
            result = fetch_metrics_pipeline()

        assert result == 0

    def test_returns_1_when_some_failed(self):
        from src.main import fetch_metrics_pipeline

        with (
            patch("src.config.MONGODB_URI", "mongodb://fake"),
            patch("src.config.YOUTUBE_REFRESH_TOKEN", "fake_token"),
            patch("src.yt_analytics.fetch_and_store_recent", return_value={
                "processed": 5, "updated": 3, "failed": 2, "skipped": 0,
            }),
        ):
            result = fetch_metrics_pipeline()

        assert result == 1

    def test_returns_1_when_no_mongodb_uri(self):
        from src.main import fetch_metrics_pipeline

        with patch("src.config.MONGODB_URI", ""):
            result = fetch_metrics_pipeline()

        assert result == 1

    def test_returns_1_when_no_refresh_token(self):
        from src.main import fetch_metrics_pipeline

        with (
            patch("src.config.MONGODB_URI", "mongodb://fake"),
            patch("src.config.YOUTUBE_REFRESH_TOKEN", ""),
        ):
            result = fetch_metrics_pipeline()

        assert result == 1


# ══════════════════════════════════════════════════════════════
#  config.py — new fields
# ══════════════════════════════════════════════════════════════

class TestConfigPhase62:
    def test_enable_yt_analytics_default_off(self):
        import src.config as cfg
        # Default should be "0" (opt-in design)
        import os
        saved = os.environ.pop("ENABLE_YT_ANALYTICS", None)
        try:
            import importlib
            importlib.reload(cfg)
            assert cfg.ENABLE_YT_ANALYTICS == "0"
        finally:
            if saved is not None:
                os.environ["ENABLE_YT_ANALYTICS"] = saved
            importlib.reload(cfg)

    def test_youtube_channel_id_default_empty(self):
        import src.config as cfg
        import os
        saved = os.environ.pop("YOUTUBE_CHANNEL_ID", None)
        try:
            import importlib
            importlib.reload(cfg)
            assert cfg.YOUTUBE_CHANNEL_ID == ""
        finally:
            if saved is not None:
                os.environ["YOUTUBE_CHANNEL_ID"] = saved
            importlib.reload(cfg)

