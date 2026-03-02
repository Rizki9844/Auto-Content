"""
Tests for Phase 4.3 — Analytics Dashboard.
All MongoDB calls are mocked.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


# ──────────────────────────────────────────────────────────────
#  _bar helper
# ──────────────────────────────────────────────────────────────
class TestBarHelper:
    def test_full_bar(self):
        from src.analytics import _bar
        assert _bar(10, 10, width=5) == "█████"

    def test_half_bar(self):
        from src.analytics import _bar
        assert _bar(5, 10, width=10) == "█████"

    def test_zero_value(self):
        from src.analytics import _bar
        assert _bar(0, 10) == ""

    def test_zero_max(self):
        from src.analytics import _bar
        assert _bar(5, 0) == ""

    def test_proportional(self):
        from src.analytics import _bar
        bar = _bar(1, 4, width=4)
        assert len(bar) == 1


# ──────────────────────────────────────────────────────────────
#  _week_label & _month_label
# ──────────────────────────────────────────────────────────────
class TestLabels:
    def test_week_label_format(self):
        from src.analytics import _week_label
        dt = datetime(2026, 3, 2, tzinfo=timezone.utc)
        label = _week_label(dt)
        assert label.startswith("2026-W")
        assert len(label) == len("2026-W09")

    def test_month_label_format(self):
        from src.analytics import _month_label
        dt = datetime(2026, 3, 2, tzinfo=timezone.utc)
        assert _month_label(dt) == "2026-03"


# ──────────────────────────────────────────────────────────────
#  get_summary
# ──────────────────────────────────────────────────────────────
class TestGetSummary:
    def _make_col(self, total=10, success=8, failed=2):
        col = MagicMock()
        col.count_documents.side_effect = lambda q: {
            (): total,
            ("status", "success"): success,
            ("status", "failed"): failed,
        }.get(tuple(q.get("status", {}).values()) if "status" in q else (), total)

        def _count(q):
            st = q.get("status")
            if st == "success":
                return success
            if st == "failed":
                return failed
            return total

        col.count_documents.side_effect = _count
        col.aggregate.return_value = iter([
            {"avg_quality": 80.0, "avg_duration": 45.0}
        ])
        return col

    def test_summary_has_required_keys(self):
        col = self._make_col()
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import get_summary
            s = get_summary()
        assert set(s.keys()) >= {
            "total", "success", "failed", "success_rate",
            "avg_quality_score", "avg_duration_seconds", "skipped",
        }

    def test_success_rate_calculation(self):
        col = self._make_col(total=10, success=8, failed=2)
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import get_summary
            s = get_summary()
        assert s["success_rate"] == 80.0

    def test_perfect_success_rate(self):
        col = self._make_col(total=5, success=5, failed=0)
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import get_summary
            s = get_summary()
        assert s["success_rate"] == 100.0

    def test_zero_total_no_division_error(self):
        col = self._make_col(total=0, success=0, failed=0)
        col.aggregate.return_value = iter([])
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import get_summary
            s = get_summary()
        assert s["success_rate"] == 0.0

    def test_avg_quality_from_aggregate(self):
        col = self._make_col()
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import get_summary
            s = get_summary()
        assert s["avg_quality_score"] == 80.0

    def test_graceful_on_db_error(self):
        col = MagicMock()
        col.count_documents.side_effect = Exception("DB down")
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import get_summary
            s = get_summary()
        assert s["total"] == 0


# ──────────────────────────────────────────────────────────────
#  get_weekly_counts
# ──────────────────────────────────────────────────────────────
class TestGetWeeklyCounts:
    def test_returns_n_weeks(self):
        col = MagicMock()
        col.find.return_value = iter([])
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import get_weekly_counts
            result = get_weekly_counts(4)
        assert len(result) == 4

    def test_keys_are_iso_week_format(self):
        col = MagicMock()
        col.find.return_value = iter([])
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import get_weekly_counts
            result = get_weekly_counts(3)
        for key in result:
            assert key.startswith("20")
            assert "-W" in key

    def test_counts_docs_in_correct_week(self):
        now = datetime.now(timezone.utc)
        col = MagicMock()
        col.find.return_value = iter([{"created_at": now}])
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import _week_label, get_weekly_counts
            result = get_weekly_counts(4)
        current_week = _week_label(now)
        assert result.get(current_week, 0) == 1

    def test_graceful_on_error(self):
        col = MagicMock()
        col.find.side_effect = Exception("DB down")
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import get_weekly_counts
            result = get_weekly_counts(4)
        assert result == {}


# ──────────────────────────────────────────────────────────────
#  get_monthly_counts
# ──────────────────────────────────────────────────────────────
class TestGetMonthlyCounts:
    def test_returns_n_months(self):
        col = MagicMock()
        col.aggregate.return_value = iter([])
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import get_monthly_counts
            result = get_monthly_counts(6)
        assert len(result) == 6

    def test_keys_are_month_format(self):
        col = MagicMock()
        col.aggregate.return_value = iter([])
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import get_monthly_counts
            result = get_monthly_counts(3)
        for key in result:
            parts = key.split("-")
            assert len(parts) == 2
            assert len(parts[1]) == 2

    def test_merges_aggregation_data(self):
        now = datetime.now(timezone.utc)
        col = MagicMock()
        col.aggregate.return_value = iter([
            {"_id": {"year": now.year, "month": now.month}, "count": 7}
        ])
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import get_monthly_counts
            result = get_monthly_counts(2)
        current_month = f"{now.year}-{now.month:02d}"
        assert result.get(current_month) == 7


# ──────────────────────────────────────────────────────────────
#  get_language_distribution
# ──────────────────────────────────────────────────────────────
class TestGetLanguageDistribution:
    def test_sorted_descending(self):
        col = MagicMock()
        col.aggregate.return_value = iter([
            {"_id": "python", "count": 10},
            {"_id": "go",     "count": 5},
            {"_id": "rust",   "count": 2},
        ])
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import get_language_distribution
            result = get_language_distribution()
        counts = list(result.values())
        assert counts == sorted(counts, reverse=True)

    def test_returns_language_keys(self):
        col = MagicMock()
        col.aggregate.return_value = iter([
            {"_id": "python", "count": 3},
        ])
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import get_language_distribution
            result = get_language_distribution()
        assert "python" in result


# ──────────────────────────────────────────────────────────────
#  get_content_type_distribution
# ──────────────────────────────────────────────────────────────
class TestGetContentTypeDistribution:
    def test_returns_type_keys(self):
        col = MagicMock()
        col.aggregate.return_value = iter([
            {"_id": "tip", "count": 8},
            {"_id": "quiz", "count": 4},
        ])
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import get_content_type_distribution
            result = get_content_type_distribution()
        assert "tip" in result
        assert result["tip"] == 8

    def test_sorted_descending(self):
        col = MagicMock()
        col.aggregate.return_value = iter([
            {"_id": "tip", "count": 8},
            {"_id": "quiz", "count": 4},
            {"_id": "before_after", "count": 2},
        ])
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import get_content_type_distribution
            result = get_content_type_distribution()
        counts = list(result.values())
        assert counts == sorted(counts, reverse=True)


# ──────────────────────────────────────────────────────────────
#  get_latency_trend
# ──────────────────────────────────────────────────────────────
class TestGetLatencyTrend:
    def _make_col(self, docs):
        col = MagicMock()
        col.find.return_value.sort.return_value.limit.return_value = iter(docs)
        return col

    def test_averages_correctly(self):
        docs = [
            {"metrics": {"total_latency_ms": 10000, "gemini_latency_ms": 3000}},
            {"metrics": {"total_latency_ms": 20000, "gemini_latency_ms": 5000}},
        ]
        col = self._make_col(docs)
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import get_latency_trend
            result = get_latency_trend()
        assert result["total_ms"] == 15000.0
        assert result["gemini_ms"] == 4000.0

    def test_missing_fields_excluded(self):
        docs = [
            {"metrics": {"total_latency_ms": 5000}},
        ]
        col = self._make_col(docs)
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import get_latency_trend
            result = get_latency_trend()
        assert "total_ms" in result
        assert "tts_ms" not in result

    def test_empty_returns_empty(self):
        col = self._make_col([])
        with patch("src.analytics._get_history_col", return_value=col):
            from src.analytics import get_latency_trend
            result = get_latency_trend()
        assert result == {}


# ──────────────────────────────────────────────────────────────
#  get_queue_status
# ──────────────────────────────────────────────────────────────
class TestGetQueueStatus:
    def test_delegates_to_scheduler(self):
        fake = {"pending_due": 1, "pending_future": 3,
                "done_today": 2, "failed_total": 0}
        with patch("src.analytics.get_schedule_summary", return_value=fake,
                   create=True):
            with patch("src.scheduler.get_schedule_summary", return_value=fake):
                from src.analytics import get_queue_status
                result = get_queue_status()
        assert result == fake

    def test_graceful_on_error(self):
        with patch("src.scheduler.get_schedule_summary",
                   side_effect=Exception("unavailable")):
            from src.analytics import get_queue_status
            result = get_queue_status()
        assert isinstance(result, dict)


# ──────────────────────────────────────────────────────────────
#  generate_report
# ──────────────────────────────────────────────────────────────
class TestGenerateReport:
    @staticmethod
    def _patch_all():
        """Patch all data-fetching functions to return minimal valid data."""
        return [
            patch("src.analytics.get_summary", return_value={
                "total": 10, "success": 8, "failed": 2, "skipped": 0,
                "success_rate": 80.0, "avg_quality_score": 75.0,
                "avg_duration_seconds": 42.0,
            }),
            patch("src.analytics.get_weekly_counts", return_value={"2026-W09": 3}),
            patch("src.analytics.get_monthly_counts", return_value={"2026-03": 8}),
            patch("src.analytics.get_language_distribution",
                  return_value={"python": 5, "go": 3}),
            patch("src.analytics.get_content_type_distribution",
                  return_value={"tip": 6, "quiz": 2}),
            patch("src.analytics.get_latency_trend",
                  return_value={"total_ms": 12000.0, "gemini_ms": 4000.0}),
            patch("src.analytics.get_queue_status",
                  return_value={"pending_due": 0, "pending_future": 2,
                                "done_today": 1, "failed_total": 0}),
        ]

    def test_returns_string(self):
        from contextlib import ExitStack
        from src.analytics import generate_report
        with ExitStack() as stack:
            for p in self._patch_all():
                stack.enter_context(p)
            report = generate_report()
        assert isinstance(report, str)
        assert len(report) > 100

    def test_contains_all_sections(self):
        from contextlib import ExitStack
        from src.analytics import generate_report
        with ExitStack() as stack:
            for p in self._patch_all():
                stack.enter_context(p)
            report = generate_report()
        for header in [
            "# 📊 Auto-Content Pipeline",
            "## 1. Summary",
            "## 2. Weekly Output",
            "## 3. Monthly Output",
            "## 4. Language Distribution",
            "## 5. Content Type Distribution",
            "## 6. Average Pipeline Latency",
            "## 7. Schedule Queue",
        ]:
            assert header in report, f"Missing section: {header!r}"

    def test_contains_success_rate(self):
        from contextlib import ExitStack
        from src.analytics import generate_report
        with ExitStack() as stack:
            for p in self._patch_all():
                stack.enter_context(p)
            report = generate_report()
        assert "80.0%" in report

    def test_contains_language_names(self):
        from contextlib import ExitStack
        from src.analytics import generate_report
        with ExitStack() as stack:
            for p in self._patch_all():
                stack.enter_context(p)
            report = generate_report()
        assert "python" in report
        assert "go" in report


# ──────────────────────────────────────────────────────────────
#  save_report
# ──────────────────────────────────────────────────────────────
class TestSaveReport:
    def test_creates_file(self, tmp_path):
        with patch("src.analytics.generate_report", return_value="# Test Report"):
            from src.analytics import save_report
            path = save_report(output_dir=tmp_path)
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "# Test Report"

    def test_filename_has_date(self, tmp_path):
        with patch("src.analytics.generate_report", return_value="# Test"):
            from src.analytics import save_report
            path = save_report(output_dir=tmp_path)
        assert "report_" in path.name
        assert path.suffix == ".md"


# ──────────────────────────────────────────────────────────────
#  analytics_pipeline (main.py integration)
# ──────────────────────────────────────────────────────────────
class TestAnalyticsPipeline:
    def test_prints_report_and_returns_0(self, capsys):
        with patch("src.analytics.generate_report", return_value="# Report"):
            from src.main import analytics_pipeline
            rc = analytics_pipeline(save=False)
        captured = capsys.readouterr()
        assert rc == 0
        assert "# Report" in captured.out

    def test_save_flag_calls_save_report(self, tmp_path):
        with (
            patch("src.analytics.generate_report", return_value="# R"),
            patch("src.analytics.save_report", return_value=tmp_path / "r.md") as m_save,
        ):
            from src.main import analytics_pipeline
            analytics_pipeline(save=True)
        m_save.assert_called_once()

    def test_returns_1_on_error(self):
        with patch("src.analytics.generate_report", side_effect=Exception("fail")):
            from src.main import analytics_pipeline
            rc = analytics_pipeline(save=False)
        assert rc == 1
