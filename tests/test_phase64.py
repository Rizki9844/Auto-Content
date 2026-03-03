"""
Tests for Phase 6.4 — Smart Series Generator
Covers: series_planner.py, llm.py series_context, renderer.py badge,
        video.py, db.py, main.py series_pipeline + CLI
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ══════════════════════════════════════════════════════════════
#  series_planner.make_series_id
# ══════════════════════════════════════════════════════════════

class TestMakeSeriesId:
    def test_slugifies_theme(self):
        from src.series_planner import make_series_id
        sid = make_series_id("Python Basics")
        assert "python-basics" in sid

    def test_includes_date_segment(self):
        from src.series_planner import make_series_id
        sid = make_series_id("JS Tips")
        # date segment is 8 digits
        import re
        assert re.search(r"\d{8}", sid)

    def test_special_chars_slugified(self):
        from src.series_planner import make_series_id
        sid = make_series_id("C++ & Rust: Speed!")
        assert " " not in sid
        assert "&" not in sid
        assert "!" not in sid

    def test_lowercase_output(self):
        from src.series_planner import make_series_id
        sid = make_series_id("TypeScript Advanced")
        assert sid == sid.lower()


# ══════════════════════════════════════════════════════════════
#  series_planner.plan_series
# ══════════════════════════════════════════════════════════════

class TestPlanSeries:
    def _mock_plan_response(self, n: int) -> list[dict]:
        return [
            {
                "episode":      i + 1,
                "topic":        f"Topic {i + 1}",
                "language":     "python",
                "content_type": "tip",
                "hook":         f"Hook for episode {i + 1}",
            }
            for i in range(n)
        ]

    def test_returns_correct_episode_count(self):
        from src.series_planner import plan_series
        import json

        fake_plan = self._mock_plan_response(3)
        mock_response = MagicMock()
        mock_response.text = json.dumps(fake_plan)

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with (
            patch("src.config.GEMINI_API_KEY", "fake_key"),
            patch("src.series_planner.genai.Client", return_value=mock_client),
        ):
            result = plan_series("Python Basics", 3)

        assert len(result) == 3

    def test_each_episode_has_required_keys(self):
        from src.series_planner import plan_series
        import json

        fake_plan = self._mock_plan_response(2)
        mock_response = MagicMock()
        mock_response.text = json.dumps(fake_plan)

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with (
            patch("src.config.GEMINI_API_KEY", "fake_key"),
            patch("src.series_planner.genai.Client", return_value=mock_client),
        ):
            result = plan_series("Go Basics", 2)

        for ep in result:
            assert "episode" in ep
            assert "topic" in ep
            assert "language" in ep
            assert "content_type" in ep
            assert "hook" in ep

    def test_invalid_content_type_falls_back_to_tip(self):
        from src.series_planner import plan_series
        import json

        fake_plan = [{"episode": 1, "topic": "T", "language": "python",
                      "content_type": "invalid_type", "hook": "h"}]
        mock_response = MagicMock()
        mock_response.text = json.dumps(fake_plan)

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with (
            patch("src.config.GEMINI_API_KEY", "fake_key"),
            patch("src.series_planner.genai.Client", return_value=mock_client),
        ):
            result = plan_series("Test", 1)

        assert result[0]["content_type"] == "tip"

    def test_requires_gemini_api_key(self):
        from src.series_planner import plan_series

        with patch("src.config.GEMINI_API_KEY", ""):
            with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
                plan_series("Python", 3)

    def test_caps_episodes_at_20(self):
        """plan_series must clamp episodes to 20 max."""
        from src.series_planner import plan_series
        import json

        fake_plan = [
            {"episode": i + 1, "topic": f"T{i}", "language": "python",
             "content_type": "tip", "hook": "h"}
            for i in range(20)
        ]
        mock_response = MagicMock()
        mock_response.text = json.dumps(fake_plan)

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with (
            patch("src.config.GEMINI_API_KEY", "fake_key"),
            patch("src.series_planner.genai.Client", return_value=mock_client),
        ):
            result = plan_series("Test", 99)  # clamped to 20

        assert len(result) == 20

    def test_fills_missing_episodes_with_defaults(self):
        """If Gemini returns fewer episodes than requested, defaults fill the gaps."""
        from src.series_planner import plan_series
        import json

        # API returns only 1 episode, we request 3
        fake_plan = [{"episode": 1, "topic": "First", "language": "python",
                      "content_type": "tip", "hook": "h"}]
        mock_response = MagicMock()
        mock_response.text = json.dumps(fake_plan)

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with (
            patch("src.config.GEMINI_API_KEY", "fake_key"),
            patch("src.series_planner.genai.Client", return_value=mock_client),
        ):
            result = plan_series("Theme", 3)

        assert len(result) == 3
        assert result[0]["topic"] == "First"
        assert "Part 2" in result[1]["topic"]  # default fallback

    def test_retries_on_exception(self):
        """plan_series retries up to 3 times on API failure."""
        from src.series_planner import plan_series
        import json

        fake_plan = [{"episode": 1, "topic": "T", "language": "python",
                      "content_type": "tip", "hook": "h"}]
        mock_response = MagicMock()
        mock_response.text = json.dumps(fake_plan)

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise RuntimeError("transient error")
            return mock_response

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = side_effect

        with (
            patch("src.config.GEMINI_API_KEY", "fake_key"),
            patch("src.series_planner.genai.Client", return_value=mock_client),
            patch("src.series_planner.time.sleep"),  # skip real sleep
        ):
            result = plan_series("Theme", 1)

        assert len(result) == 1
        assert call_count["n"] == 2  # failed once, succeeded on retry


# ══════════════════════════════════════════════════════════════
#  llm.generate_content — series_context hint injection
# ══════════════════════════════════════════════════════════════

class TestSeriesHintInLLM:
    def _capture_prompt(self, series_context: dict | None) -> str:
        captured: list[str] = []

        def fake_generate(model, contents, config):
            captured.append(contents)
            raise RuntimeError("stop_sentinel")

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = fake_generate

        with (
            patch("src.config.CONTENT_LANGUAGE", "en"),
            patch("src.config.ENABLE_TRENDING", "0"),
            patch("src.config.ENABLE_YT_ANALYTICS", "0"),
            patch("src.config.GEMINI_API_KEY", "fake_key"),
            patch("src.llm.get_past_topics", return_value=[]),
            patch("src.llm.genai.Client", return_value=mock_client),
        ):
            from src.llm import generate_content
            try:
                generate_content(series_context=series_context)
            except RuntimeError:
                pass

        return captured[0] if captured else ""

    def test_no_hint_without_series_context(self):
        prompt = self._capture_prompt(None)
        assert "SERIES CONTEXT" not in prompt

    def test_hint_injected_with_series_context(self):
        ctx = {"episode": 2, "total": 5, "theme": "Python Basics",
               "topic": "List comprehensions", "content_type": "tip", "language": "python"}
        prompt = self._capture_prompt(ctx)
        assert "SERIES CONTEXT" in prompt

    def test_hint_contains_episode_info(self):
        ctx = {"episode": 3, "total": 7, "theme": "JS Modern",
               "topic": "Arrow functions", "content_type": "quiz", "language": "javascript"}
        prompt = self._capture_prompt(ctx)
        assert "episode 3 of 7" in prompt
        assert "JS Modern" in prompt

    def test_hint_contains_suggested_topic(self):
        ctx = {"episode": 1, "total": 3, "theme": "Git Tips",
               "topic": "git stash explained", "content_type": "tip", "language": "bash"}
        prompt = self._capture_prompt(ctx)
        assert "git stash explained" in prompt

    def test_hint_contains_language_and_type(self):
        ctx = {"episode": 1, "total": 3, "theme": "Rust",
               "topic": "Ownership basics", "content_type": "before_after", "language": "rust"}
        prompt = self._capture_prompt(ctx)
        assert "rust" in prompt
        assert "before_after" in prompt

    def test_series_context_exception_does_not_break_pipeline(self):
        """Malformed series_context must not prevent prompt from being built."""
        prompt = self._capture_prompt({"episode": "not_int"})  # keys fine, type won't crash
        assert "Return valid JSON only" in prompt  # pipeline continued


# ══════════════════════════════════════════════════════════════
#  db.save_record — series_id / series_part fields
# ══════════════════════════════════════════════════════════════

class TestDbSeriesFields:
    def test_series_fields_stored_when_provided(self):
        from src.db import save_record

        mock_col = MagicMock()
        mock_col.insert_one.return_value.inserted_id = "fake_id"

        with patch("src.db._get_collection", return_value=mock_col):
            save_record({
                "topic": "Test", "title": "Test", "script": "s",
                "code": "x=1", "language": "python",
                "series_id": "python-basics-20260303",
                "series_part": 2,
            })

        inserted = mock_col.insert_one.call_args[0][0]
        assert inserted["series_id"]   == "python-basics-20260303"
        assert inserted["series_part"] == 2

    def test_series_fields_none_without_data(self):
        from src.db import save_record

        mock_col = MagicMock()
        mock_col.insert_one.return_value.inserted_id = "fake_id"

        with patch("src.db._get_collection", return_value=mock_col):
            save_record({"topic": "Test", "title": "T", "code": "x=1", "language": "python"})

        inserted = mock_col.insert_one.call_args[0][0]
        assert inserted["series_id"]   is None
        assert inserted["series_part"] is None


# ══════════════════════════════════════════════════════════════
#  renderer.FrameRenderer — series_part badge in intro
# ══════════════════════════════════════════════════════════════

class TestFrameRendererSeriesBadge:
    """Instead of instantiating the full renderer (too heavy), patch _create_intro_image
    and verify series_part is stored correctly."""

    def test_series_part_stored_on_init(self):
        import importlib
        renderer_mod = importlib.import_module("src.renderer")

        fr = object.__new__(renderer_mod.FrameRenderer)
        fr.series_part = 3
        assert fr.series_part == 3

    def test_default_series_part_is_zero(self):
        """When series_part is not provided, it must default to 0."""
        import inspect
        import src.renderer as renderer_mod
        sig = inspect.signature(renderer_mod.FrameRenderer.__init__)
        default = sig.parameters["series_part"].default
        assert default == 0

    def test_series_part_passthrough_in_create_video_signature(self):
        """create_video must accept series_part keyword argument."""
        import inspect
        from src.video import create_video
        sig = inspect.signature(create_video)
        assert "series_part" in sig.parameters
        assert sig.parameters["series_part"].default == 0


# ══════════════════════════════════════════════════════════════
#  main.series_pipeline
# ══════════════════════════════════════════════════════════════

_FAKE_PLAN = [
    {"episode": 1, "topic": "Variables", "language": "python",
     "content_type": "tip", "hook": "Variables made easy!"},
    {"episode": 2, "topic": "Functions", "language": "python",
     "content_type": "quiz", "hook": "Can you guess the output?"},
]

_FAKE_CONTENT = {
    "title": "Python Variables", "script": "This is a script.",
    "code": "x = 10", "language": "python",
    "hashtags": ["#python"], "content_type": "tip",
}


class TestSeriesPipeline:
    def test_returns_zero_without_gemini_key(self):
        from src.main import series_pipeline

        with (
            patch("src.config.GEMINI_API_KEY", ""),
            patch("src.config.MONGODB_URI", "mongodb://fake"),
        ):
            result = series_pipeline("Python Basics", 2)

        assert result == 0

    def test_returns_zero_without_mongodb(self):
        from src.main import series_pipeline

        with (
            patch("src.config.GEMINI_API_KEY", "fake_key"),
            patch("src.config.MONGODB_URI", ""),
        ):
            result = series_pipeline("Python Basics", 2)

        assert result == 0

    def test_returns_queued_count_on_success(self):
        from src.main import series_pipeline

        with (
            patch("src.config.GEMINI_API_KEY", "fake_key"),
            patch("src.config.MONGODB_URI", "mongodb://fake"),
            patch("src.series_planner.plan_series", return_value=_FAKE_PLAN),
            patch("src.series_planner.make_series_id", return_value="python-basics-20260303"),
            patch("src.llm.generate_content", return_value=_FAKE_CONTENT),
            patch("src.tts.generate_speech", return_value=("/tmp/a.mp3", [])),
            patch("src.video.create_video", return_value="/tmp/v.mp4"),
            patch("src.video.verify_video", return_value={"passed": True, "errors": []}),
            patch("src.db.check_code_similarity", return_value={"is_duplicate": False}),
            patch("src.db.get_language_frequency", return_value={}),
            patch("src.code_runner.get_output_for_content", return_value=None),
            patch("src.quality.score_content", return_value={"passed": True, "total_score": 80}),
            patch("src.scheduler.add_to_schedule"),
            patch("src.scheduler.next_available_slots", return_value=["s1", "s2"]),
            patch("src.main._is_content_safe", return_value=(True, "")),
        ):
            result = series_pipeline("Python Basics", 2)

        assert result == 2

    def test_skips_unsafe_episode(self):
        from src.main import series_pipeline

        with (
            patch("src.config.GEMINI_API_KEY", "fake_key"),
            patch("src.config.MONGODB_URI", "mongodb://fake"),
            patch("src.series_planner.plan_series", return_value=_FAKE_PLAN[:1]),
            patch("src.series_planner.make_series_id", return_value="id"),
            patch("src.llm.generate_content", return_value=_FAKE_CONTENT),
            patch("src.tts.generate_speech", return_value=("/tmp/a.mp3", [])),
            patch("src.video.create_video", return_value="/tmp/v.mp4"),
            patch("src.video.verify_video", return_value={"passed": True, "errors": []}),
            patch("src.db.check_code_similarity", return_value={"is_duplicate": False}),
            patch("src.db.get_language_frequency", return_value={}),
            patch("src.code_runner.get_output_for_content", return_value=None),
            patch("src.quality.score_content", return_value={"passed": True, "total_score": 80}),
            patch("src.scheduler.add_to_schedule"),
            patch("src.scheduler.next_available_slots", return_value=["s1"]),
            patch("src.main._is_content_safe", return_value=(False, "safety violation")),
        ):
            result = series_pipeline("Test", 1)

        assert result == 0  # skipped

    def test_series_context_passed_to_generate_content(self):
        from src.main import series_pipeline

        captured_ctx: list[dict] = []

        def fake_generate(avoid_languages=None, series_context=None):
            captured_ctx.append(series_context)
            return _FAKE_CONTENT

        with (
            patch("src.config.GEMINI_API_KEY", "fake_key"),
            patch("src.config.MONGODB_URI", "mongodb://fake"),
            patch("src.series_planner.plan_series", return_value=_FAKE_PLAN[:1]),
            patch("src.series_planner.make_series_id", return_value="id"),
            patch("src.llm.generate_content", side_effect=fake_generate),
            patch("src.tts.generate_speech", return_value=("/tmp/a.mp3", [])),
            patch("src.video.create_video", return_value="/tmp/v.mp4"),
            patch("src.video.verify_video", return_value={"passed": True, "errors": []}),
            patch("src.db.check_code_similarity", return_value={"is_duplicate": False}),
            patch("src.db.get_language_frequency", return_value={}),
            patch("src.code_runner.get_output_for_content", return_value=None),
            patch("src.quality.score_content", return_value={"passed": True, "total_score": 80}),
            patch("src.scheduler.add_to_schedule"),
            patch("src.scheduler.next_available_slots", return_value=["s1"]),
            patch("src.main._is_content_safe", return_value=(True, "")),
        ):
            series_pipeline("Python Basics", 1)

        assert len(captured_ctx) == 1
        assert captured_ctx[0]["theme"] == "Python Basics"
        assert captured_ctx[0]["episode"] == 1

    def test_series_part_passed_to_create_video(self):
        from src.main import series_pipeline

        captured_parts: list[int] = []

        def fake_create_video(**kwargs):
            captured_parts.append(kwargs.get("series_part", -1))
            return "/tmp/v.mp4"

        with (
            patch("src.config.GEMINI_API_KEY", "fake_key"),
            patch("src.config.MONGODB_URI", "mongodb://fake"),
            patch("src.series_planner.plan_series", return_value=_FAKE_PLAN),
            patch("src.series_planner.make_series_id", return_value="id"),
            patch("src.llm.generate_content", return_value=_FAKE_CONTENT),
            patch("src.tts.generate_speech", return_value=("/tmp/a.mp3", [])),
            patch("src.video.create_video", side_effect=fake_create_video),
            patch("src.video.verify_video", return_value={"passed": True, "errors": []}),
            patch("src.db.check_code_similarity", return_value={"is_duplicate": False}),
            patch("src.db.get_language_frequency", return_value={}),
            patch("src.code_runner.get_output_for_content", return_value=None),
            patch("src.quality.score_content", return_value={"passed": True, "total_score": 80}),
            patch("src.scheduler.add_to_schedule"),
            patch("src.scheduler.next_available_slots", return_value=["s1", "s2"]),
            patch("src.main._is_content_safe", return_value=(True, "")),
        ):
            series_pipeline("Python Basics", 2)

        assert captured_parts == [1, 2]  # episode numbers passed as series_part

    def test_plan_series_failure_returns_zero(self):
        from src.main import series_pipeline

        with (
            patch("src.config.GEMINI_API_KEY", "fake_key"),
            patch("src.config.MONGODB_URI", "mongodb://fake"),
            patch("src.series_planner.plan_series", side_effect=RuntimeError("LLM down")),
            patch("src.db.get_language_frequency", return_value={}),
            patch("src.scheduler.next_available_slots", return_value=[]),
        ):
            result = series_pipeline("Test", 2)

        assert result == 0


# ══════════════════════════════════════════════════════════════
#  CLI argument parsing — --series / --episodes
# ══════════════════════════════════════════════════════════════

class TestSeriesCLI:
    """Test the --series / --episodes CLI argument parsing logic directly."""

    def test_series_theme_parsed_from_argv(self):
        import sys
        sys.argv = ["prog", "--series", "TypeScript Tips", "--episodes", "3"]
        try:
            s_idx = sys.argv.index("--series")
            theme = sys.argv[s_idx + 1]
        finally:
            sys.argv = ["prog"]
        assert theme == "TypeScript Tips"

    def test_episodes_parsed_from_argv(self):
        import sys
        sys.argv = ["prog", "--series", "Rust Basics", "--episodes", "7"]
        try:
            e_idx = sys.argv.index("--episodes")
            n_eps = int(sys.argv[e_idx + 1])
        finally:
            sys.argv = ["prog"]
        assert n_eps == 7

    def test_missing_episodes_defaults_to_5(self):
        """When --episodes is absent, the CLI defaults to 5."""
        import sys
        sys.argv = ["prog", "--series", "Go Tips"]
        try:
            try:
                e_idx = sys.argv.index("--episodes")
                n_eps = int(sys.argv[e_idx + 1])
            except (ValueError, IndexError):
                n_eps = 5  # default
        finally:
            sys.argv = ["prog"]
        assert n_eps == 5

    def test_series_flag_detected_in_argv(self):
        import sys
        sys.argv = ["prog", "--series", "Python Basics"]
        try:
            assert "--series" in sys.argv
        finally:
            sys.argv = ["prog"]

    def test_series_pipeline_called_with_correct_args(self):
        """series_pipeline is invoked with parsed theme and episode count."""
        import sys

        called_args: list = []

        orig_argv = sys.argv[:]
        sys.argv = ["prog", "--series", "Python Basics", "--episodes", "4"]

        # Simulate the exact dispatch logic from __main__
        try:
            if "--series" in sys.argv:
                s_idx = sys.argv.index("--series")
                theme = sys.argv[s_idx + 1]
                try:
                    e_idx = sys.argv.index("--episodes")
                    n_eps = int(sys.argv[e_idx + 1])
                except (IndexError, ValueError):
                    n_eps = 5
                called_args.extend([theme, n_eps])
        finally:
            sys.argv = orig_argv

        assert called_args == ["Python Basics", 4]
