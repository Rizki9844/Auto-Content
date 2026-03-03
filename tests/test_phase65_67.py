"""
Tests for Phase 6.5 / 6.6 / 6.7 — Prompt A/B Testing, Content Templates,
Voice & Tone Variety.

Covers:
    Phase 6.5 — Prompt A/B Testing:
        - resolve_prompt_variant() returns A, B, or auto-rotates
        - get_system_prompt() returns correct prompt
        - generate_content() attaches prompt_variant to output

    Phase 6.6 — Content Templates Library:
        - _load_templates() loads JSON from templates/ directory
        - pick_template() filters by language/type, 30% probability
        - build_template_hint() builds prompt block
        - Template files are valid JSON arrays

    Phase 6.7 — Voice & Tone Variety:
        - resolve_tone() returns valid tone or auto-rotates
        - get_tone_hint() builds narrator tone block
        - generate_content() attaches narrator_tone to output

    Integration:
        - db.save_record() persists new fields
        - analytics report includes A/B section
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ══════════════════════════════════════════════════════════════
#  Phase 6.5 — Prompt A/B Testing
# ══════════════════════════════════════════════════════════════

class TestResolvePromptVariant:
    """Tests for resolve_prompt_variant()."""

    def test_variant_a_explicit(self, monkeypatch):
        monkeypatch.setenv("PROMPT_VARIANT", "A")
        from src import config
        importlib_reload(config)
        from src.llm import resolve_prompt_variant
        assert resolve_prompt_variant() == "A"

    def test_variant_b_explicit(self, monkeypatch):
        monkeypatch.setenv("PROMPT_VARIANT", "B")
        from src import config
        importlib_reload(config)
        from src.llm import resolve_prompt_variant
        assert resolve_prompt_variant() == "B"

    def test_variant_auto_odd_day(self, monkeypatch):
        monkeypatch.setenv("PROMPT_VARIANT", "auto")
        from src import config
        importlib_reload(config)
        from src.llm import resolve_prompt_variant
        # Mock datetime to return odd day
        mock_dt = MagicMock()
        mock_dt.now.return_value = datetime(2025, 1, 1, tzinfo=timezone.utc)  # day=1 (odd)
        with patch("src.llm.datetime", mock_dt):
            assert resolve_prompt_variant() == "A"

    def test_variant_auto_even_day(self, monkeypatch):
        monkeypatch.setenv("PROMPT_VARIANT", "auto")
        from src import config
        importlib_reload(config)
        from src.llm import resolve_prompt_variant
        mock_dt = MagicMock()
        mock_dt.now.return_value = datetime(2025, 1, 2, tzinfo=timezone.utc)  # day=2 (even)
        with patch("src.llm.datetime", mock_dt):
            assert resolve_prompt_variant() == "B"

    def test_variant_invalid_defaults_to_a(self, monkeypatch):
        monkeypatch.setenv("PROMPT_VARIANT", "Z")
        from src import config
        importlib_reload(config)
        from src.llm import resolve_prompt_variant
        assert resolve_prompt_variant() == "A"

    def test_variant_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("PROMPT_VARIANT", "b")
        from src import config
        importlib_reload(config)
        from src.llm import resolve_prompt_variant
        assert resolve_prompt_variant() == "B"


class TestGetSystemPrompt:
    """Tests for get_system_prompt()."""

    def test_variant_a(self):
        from src.llm import get_system_prompt, SYSTEM_PROMPT
        assert get_system_prompt("A") == SYSTEM_PROMPT

    def test_variant_b(self):
        from src.llm import get_system_prompt, SYSTEM_PROMPT_B
        assert get_system_prompt("B") == SYSTEM_PROMPT_B

    def test_variant_b_content_differs(self):
        from src.llm import get_system_prompt
        assert get_system_prompt("A") != get_system_prompt("B")


class TestSystemPromptB:
    """Verify SYSTEM_PROMPT_B has required structure."""

    def test_prompt_b_exists_and_non_empty(self):
        from src.llm import SYSTEM_PROMPT_B
        assert len(SYSTEM_PROMPT_B) > 200

    def test_prompt_b_mentions_json(self):
        from src.llm import SYSTEM_PROMPT_B
        assert "json" in SYSTEM_PROMPT_B.lower() or "JSON" in SYSTEM_PROMPT_B


# ══════════════════════════════════════════════════════════════
#  Phase 6.7 — Voice & Tone Variety
# ══════════════════════════════════════════════════════════════

class TestResolveTone:
    """Tests for resolve_tone()."""

    @pytest.mark.parametrize("tone", ["energetic", "calm", "curious", "dramatic"])
    def test_explicit_tones(self, monkeypatch, tone):
        monkeypatch.setenv("NARRATOR_TONE", tone)
        from src import config
        importlib_reload(config)
        from src.llm import resolve_tone
        assert resolve_tone() == tone

    def test_auto_rotation(self, monkeypatch):
        monkeypatch.setenv("NARRATOR_TONE", "auto")
        from src import config
        importlib_reload(config)
        from src.llm import resolve_tone, _TONE_ROTATION_ORDER
        # Mock day-of-year 1 → index 1
        mock_dt = MagicMock()
        mock_now = datetime(2025, 1, 2, tzinfo=timezone.utc)  # day_of_year=2
        mock_dt.now.return_value = mock_now
        with patch("src.llm.datetime", mock_dt):
            result = resolve_tone()
            expected_idx = mock_now.timetuple().tm_yday % len(_TONE_ROTATION_ORDER)
            assert result == _TONE_ROTATION_ORDER[expected_idx]

    def test_auto_different_days_different_tones(self, monkeypatch):
        monkeypatch.setenv("NARRATOR_TONE", "auto")
        from src import config
        importlib_reload(config)
        from src.llm import resolve_tone, _TONE_ROTATION_ORDER
        tones_seen = set()
        for day in range(1, 5):
            mock_dt = MagicMock()
            mock_dt.now.return_value = datetime(2025, 1, day, tzinfo=timezone.utc)
            with patch("src.llm.datetime", mock_dt):
                tones_seen.add(resolve_tone())
        assert len(tones_seen) == len(_TONE_ROTATION_ORDER)

    def test_invalid_tone_defaults_to_energetic(self, monkeypatch):
        monkeypatch.setenv("NARRATOR_TONE", "angry")
        from src import config
        importlib_reload(config)
        from src.llm import resolve_tone
        assert resolve_tone() == "energetic"

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("NARRATOR_TONE", "CALM")
        from src import config
        importlib_reload(config)
        from src.llm import resolve_tone
        assert resolve_tone() == "calm"


class TestGetToneHint:
    """Tests for get_tone_hint()."""

    def test_returns_block_with_marker(self):
        from src.llm import get_tone_hint
        result = get_tone_hint("energetic")
        assert "══ NARRATOR TONE ══" in result

    def test_contains_instruction(self):
        from src.llm import get_tone_hint
        result = get_tone_hint("calm")
        assert "calm" in result.lower() or "wise" in result.lower()

    def test_fallback_for_unknown(self):
        from src.llm import get_tone_hint
        result = get_tone_hint("nonexistent")
        assert "══ NARRATOR TONE ══" in result

    @pytest.mark.parametrize("tone", ["energetic", "calm", "curious", "dramatic"])
    def test_all_tones_produce_output(self, tone):
        from src.llm import get_tone_hint
        result = get_tone_hint(tone)
        assert len(result) > 50
        assert "NARRATOR TONE" in result


class TestToneInstructions:
    """Verify _TONE_INSTRUCTIONS structure."""

    def test_has_four_tones(self):
        from src.llm import _TONE_INSTRUCTIONS
        assert len(_TONE_INSTRUCTIONS) == 4
        assert set(_TONE_INSTRUCTIONS.keys()) == {"energetic", "calm", "curious", "dramatic"}

    def test_all_instructions_non_empty(self):
        from src.llm import _TONE_INSTRUCTIONS
        for tone, instruction in _TONE_INSTRUCTIONS.items():
            assert len(instruction) > 20, f"Tone '{tone}' instruction too short"


# ══════════════════════════════════════════════════════════════
#  Phase 6.6 — Content Templates Library
# ══════════════════════════════════════════════════════════════

class TestLoadTemplates:
    """Tests for _load_templates()."""

    def test_loads_from_real_dir(self):
        import src.llm as llm_mod
        llm_mod._TEMPLATES = None  # clear cache
        templates = llm_mod._load_templates()
        assert isinstance(templates, list)
        assert len(templates) >= 40  # 20 python + 20 js + 10 git = 50

    def test_caching(self):
        import src.llm as llm_mod
        llm_mod._TEMPLATES = None
        first = llm_mod._load_templates()
        second = llm_mod._load_templates()
        assert first is second  # same object = cached

    def test_empty_dir(self, tmp_path, monkeypatch):
        import src.llm as llm_mod
        llm_mod._TEMPLATES = None
        monkeypatch.setattr("src.config.ROOT_DIR", tmp_path)
        (tmp_path / "templates").mkdir()
        result = llm_mod._load_templates()
        assert result == []
        llm_mod._TEMPLATES = None  # cleanup

    def test_missing_dir(self, tmp_path, monkeypatch):
        import src.llm as llm_mod
        llm_mod._TEMPLATES = None
        monkeypatch.setattr("src.config.ROOT_DIR", tmp_path)
        # no templates/ directory
        result = llm_mod._load_templates()
        assert result == []
        llm_mod._TEMPLATES = None

    def test_malformed_json_skipped(self, tmp_path, monkeypatch):
        import src.llm as llm_mod
        llm_mod._TEMPLATES = None
        monkeypatch.setattr("src.config.ROOT_DIR", tmp_path)
        tdir = tmp_path / "templates"
        tdir.mkdir()
        (tdir / "bad.json").write_text("{invalid json", encoding="utf-8")
        (tdir / "good.json").write_text('[{"topic": "Test", "language": "Python"}]', encoding="utf-8")
        result = llm_mod._load_templates()
        assert len(result) == 1
        assert result[0]["topic"] == "Test"
        llm_mod._TEMPLATES = None


class TestPickTemplate:
    """Tests for pick_template()."""

    def test_returns_dict_or_none(self):
        import src.llm as llm_mod
        llm_mod._TEMPLATES = None
        # Run multiple times — should always be dict or None
        for _ in range(20):
            result = llm_mod.pick_template()
            assert result is None or isinstance(result, dict)

    def test_probability_roughly_30_percent(self):
        import src.llm as llm_mod
        llm_mod._TEMPLATES = None
        llm_mod._load_templates()
        hits = sum(1 for _ in range(200) if llm_mod.pick_template() is not None)
        # Expect ~30% = ~60 hits; allow wide range for randomness
        assert 10 < hits < 120, f"Expected ~60 hits, got {hits}"

    def test_avoids_languages(self):
        import src.llm as llm_mod
        llm_mod._TEMPLATES = None
        llm_mod._load_templates()
        for _ in range(50):
            result = llm_mod.pick_template(avoid_languages=["Python", "JavaScript", "TypeScript"])
            if result:
                assert result["language"].lower() not in {"python", "javascript", "typescript"}

    def test_empty_templates_returns_none(self, tmp_path, monkeypatch):
        import src.llm as llm_mod
        llm_mod._TEMPLATES = None
        monkeypatch.setattr("src.config.ROOT_DIR", tmp_path)
        assert llm_mod.pick_template() is None
        llm_mod._TEMPLATES = None

    def test_recent_types_diversity(self):
        import src.llm as llm_mod
        llm_mod._TEMPLATES = None
        llm_mod._load_templates()
        # When recent types are all "tip", prefer non-tip if available
        for _ in range(50):
            result = llm_mod.pick_template(
                avoid_languages=[],
                recent_types=["tip", "tip", "tip"],
            )
            # Can't guarantee non-tip (Git is all tip), but should not crash
            if result:
                assert "topic" in result


class TestBuildTemplateHint:
    """Tests for build_template_hint()."""

    def test_contains_marker(self):
        from src.llm import build_template_hint
        template = {"topic": "Test Topic", "hook": "Great hook", "language": "Python"}
        result = build_template_hint(template)
        assert "══ TEMPLATE INSPIRATION" in result

    def test_includes_fields(self):
        from src.llm import build_template_hint
        template = {
            "topic": "Walrus Op",
            "hook": "Write cleaner code",
            "language": "Python",
            "content_type": "tip",
            "category": "syntax",
            "code_skeleton": "x := value",
        }
        result = build_template_hint(template)
        assert "Walrus Op" in result
        assert "Write cleaner code" in result
        assert "Python" in result
        assert "tip" in result
        assert "syntax" in result
        assert "x := value" in result

    def test_missing_fields_graceful(self):
        from src.llm import build_template_hint
        result = build_template_hint({})
        assert "TEMPLATE INSPIRATION" in result
        assert "MUST modify" in result

    def test_no_copy_warning(self):
        from src.llm import build_template_hint
        result = build_template_hint({"topic": "X"})
        assert "do NOT copy verbatim" in result


class TestTemplateFiles:
    """Validate the actual template JSON files."""

    @pytest.mark.parametrize("filename,min_count", [
        ("python_tips.json", 20),
        ("js_patterns.json", 20),
        ("git_tricks.json", 10),
    ])
    def test_json_file_valid(self, filename, min_count):
        path = Path(__file__).parent.parent / "templates" / filename
        assert path.exists(), f"{filename} not found"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) >= min_count

    @pytest.mark.parametrize("filename", [
        "python_tips.json",
        "js_patterns.json",
        "git_tricks.json",
    ])
    def test_template_required_fields(self, filename):
        path = Path(__file__).parent.parent / "templates" / filename
        data = json.loads(path.read_text(encoding="utf-8"))
        required = {"topic", "hook", "language", "content_type"}
        for i, tpl in enumerate(data):
            for field in required:
                assert field in tpl, f"{filename}[{i}] missing '{field}'"
                assert tpl[field], f"{filename}[{i}].{field} is empty"


# ══════════════════════════════════════════════════════════════
#  Integration: generate_content() metadata
# ══════════════════════════════════════════════════════════════

class TestGenerateContentMetadata:
    """Test that generate_content() attaches Phase 6.5/6.6/6.7 fields."""

    _MOCK_RESPONSE = json.dumps({
        "title": "Python Walrus Operator",
        "script": "Here is an amazing tip about the walrus operator in Python. "
                  "It lets you assign and check a value in a single expression. "
                  "This is super useful in while loops and list comprehensions. "
                  "Let me show you how it works in just a few lines.",
        "code": "if (n := len(data)) > 10:\n    print(f'Too many: {n}')",
        "language": "Python",
        "hashtags": ["#Python", "#CodingTips", "#Shorts", "#Dev", "#Programming"],
        "content_type": "tip",
        "expected_output": "",
        "quiz_answer": "",
        "code_before": "",
    })

    def _make_mock_client(self):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = self._MOCK_RESPONSE
        mock_client.models.generate_content.return_value = mock_resp
        return mock_client

    def test_content_has_variant_and_tone(self, monkeypatch):
        monkeypatch.setenv("PROMPT_VARIANT", "A")
        monkeypatch.setenv("NARRATOR_TONE", "calm")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        from src import config
        importlib_reload(config)
        import src.llm as llm_mod
        llm_mod._TEMPLATES = None  # reset

        mock_client = self._make_mock_client()
        with patch("src.llm.genai") as mock_genai, \
             patch("src.llm.get_past_topics", return_value=[]), \
             patch("src.llm.pick_template", return_value=None), \
             patch("src.db.get_language_frequency", return_value={"recent_types": []}), \
             patch("time.sleep"):
            mock_genai.Client.return_value = mock_client
            result = llm_mod.generate_content()

        assert result["prompt_variant"] == "A"
        assert result["narrator_tone"] == "calm"

    def test_content_has_variant_b(self, monkeypatch):
        monkeypatch.setenv("PROMPT_VARIANT", "B")
        monkeypatch.setenv("NARRATOR_TONE", "dramatic")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        from src import config
        importlib_reload(config)
        import src.llm as llm_mod
        llm_mod._TEMPLATES = None

        mock_client = self._make_mock_client()
        with patch("src.llm.genai") as mock_genai, \
             patch("src.llm.get_past_topics", return_value=[]), \
             patch("src.llm.pick_template", return_value=None), \
             patch("src.db.get_language_frequency", return_value={"recent_types": []}), \
             patch("time.sleep"):
            mock_genai.Client.return_value = mock_client
            result = llm_mod.generate_content()

        assert result["prompt_variant"] == "B"
        assert result["narrator_tone"] == "dramatic"

    def test_template_used_when_selected(self, monkeypatch):
        monkeypatch.setenv("PROMPT_VARIANT", "A")
        monkeypatch.setenv("NARRATOR_TONE", "energetic")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        from src import config
        importlib_reload(config)
        import src.llm as llm_mod
        llm_mod._TEMPLATES = None

        mock_client = self._make_mock_client()
        fake_template = {"topic": "Walrus Op", "language": "Python", "content_type": "tip"}
        with patch("src.llm.genai") as mock_genai, \
             patch("src.llm.get_past_topics", return_value=[]), \
             patch("src.llm.pick_template", return_value=fake_template), \
             patch("src.db.get_language_frequency", return_value={"recent_types": []}), \
             patch("time.sleep"):
            mock_genai.Client.return_value = mock_client
            result = llm_mod.generate_content()

        assert result.get("template_used") == "Walrus Op"

    def test_no_template_used_key_when_none(self, monkeypatch):
        monkeypatch.setenv("PROMPT_VARIANT", "A")
        monkeypatch.setenv("NARRATOR_TONE", "calm")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        from src import config
        importlib_reload(config)
        import src.llm as llm_mod
        llm_mod._TEMPLATES = None

        mock_client = self._make_mock_client()
        with patch("src.llm.genai") as mock_genai, \
             patch("src.llm.get_past_topics", return_value=[]), \
             patch("src.llm.pick_template", return_value=None), \
             patch("src.db.get_language_frequency", return_value={"recent_types": []}), \
             patch("time.sleep"):
            mock_genai.Client.return_value = mock_client
            result = llm_mod.generate_content()

        assert "template_used" not in result


# ══════════════════════════════════════════════════════════════
#  Integration: db.save_record() persists new fields
# ══════════════════════════════════════════════════════════════

class TestDBSaveNewFields:
    """Verify save_record() includes prompt_variant, narrator_tone, template_used."""

    def test_record_has_new_fields(self):
        from unittest.mock import MagicMock
        mock_col = MagicMock()
        mock_col.insert_one.return_value = MagicMock(inserted_id="abc123")

        with patch("src.db._get_collection", return_value=mock_col):
            from src.db import save_record
            data = {
                "title": "Test",
                "script": "Script text",
                "code": "print(1)",
                "language": "Python",
                "prompt_variant": "B",
                "narrator_tone": "curious",
                "template_used": "Walrus Op",
            }
            save_record(data)

        call_args = mock_col.insert_one.call_args[0][0]
        assert call_args["prompt_variant"] == "B"
        assert call_args["narrator_tone"] == "curious"
        assert call_args["template_used"] == "Walrus Op"

    def test_record_none_when_not_provided(self):
        from unittest.mock import MagicMock
        mock_col = MagicMock()
        mock_col.insert_one.return_value = MagicMock(inserted_id="abc123")

        with patch("src.db._get_collection", return_value=mock_col):
            from src.db import save_record
            save_record({"title": "T", "script": "S", "code": "C", "language": "L"})

        call_args = mock_col.insert_one.call_args[0][0]
        assert call_args["prompt_variant"] is None
        assert call_args["narrator_tone"] is None
        assert call_args["template_used"] is None


# ══════════════════════════════════════════════════════════════
#  Integration: analytics report has A/B section
# ══════════════════════════════════════════════════════════════

class TestAnalyticsABSection:
    """Verify generate_report() includes Section 9 (A/B + Tone)."""

    def _mock_col(self, variant_data=None, tone_data=None):
        """Create mock collection that returns variant/tone aggregation data."""
        mock_col = MagicMock()

        def fake_aggregate(pipeline):
            # Detect which pipeline by checking the match filter
            match_filter = pipeline[0].get("$match", {})
            if "prompt_variant" in match_filter:
                return variant_data or []
            if "narrator_tone" in match_filter:
                return tone_data or []
            return []

        mock_col.aggregate.side_effect = fake_aggregate
        mock_col.count_documents.return_value = 0
        mock_col.find.return_value = MagicMock(
            sort=MagicMock(return_value=MagicMock(limit=MagicMock(return_value=[])))
        )
        return mock_col

    def test_report_contains_ab_section_header(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://fake")
        from src import config
        importlib_reload(config)
        # Mock all MongoDB calls
        with patch("src.analytics._get_history_col") as mock_hist:
            mock_col = self._mock_col(
                variant_data=[
                    {"_id": "A", "count": 10, "avg_quality": 78.5},
                    {"_id": "B", "count": 8, "avg_quality": 82.0},
                ],
                tone_data=[
                    {"_id": "energetic", "count": 5, "avg_quality": 80.0},
                    {"_id": "calm", "count": 3, "avg_quality": 75.0},
                ],
            )
            mock_hist.return_value = mock_col

            from src.analytics import generate_report
            # Patch all data-fetching functions to return empty/defaults
            with patch("src.analytics.get_summary", return_value={
                "total": 18, "success": 18, "failed": 0,
                "success_rate": 100, "avg_quality_score": 80, "avg_duration_seconds": 30,
            }), patch("src.analytics.get_weekly_counts", return_value={}), \
               patch("src.analytics.get_monthly_counts", return_value={}), \
               patch("src.analytics.get_language_distribution", return_value={}), \
               patch("src.analytics.get_content_type_distribution", return_value={}), \
               patch("src.analytics.get_latency_trend", return_value={}), \
               patch("src.analytics.get_queue_status", return_value={}):
                report = generate_report()

        assert "9. Prompt A/B & Tone Performance" in report

    def test_report_with_no_ab_data(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://fake")
        from src import config
        importlib_reload(config)
        with patch("src.analytics._get_history_col") as mock_hist:
            mock_col = self._mock_col()
            mock_hist.return_value = mock_col
            from src.analytics import generate_report
            with patch("src.analytics.get_summary", return_value={
                "total": 0, "success": 0, "failed": 0,
                "success_rate": 0, "avg_quality_score": 0, "avg_duration_seconds": 0,
            }), patch("src.analytics.get_weekly_counts", return_value={}), \
               patch("src.analytics.get_monthly_counts", return_value={}), \
               patch("src.analytics.get_language_distribution", return_value={}), \
               patch("src.analytics.get_content_type_distribution", return_value={}), \
               patch("src.analytics.get_latency_trend", return_value={}), \
               patch("src.analytics.get_queue_status", return_value={}):
                report = generate_report()

        assert "No A/B variant data yet" in report
        assert "No tone data yet" in report


# ══════════════════════════════════════════════════════════════
#  Config: New env vars
# ══════════════════════════════════════════════════════════════

class TestConfigNewVars:
    """Verify config module exposes PROMPT_VARIANT and NARRATOR_TONE."""

    def test_prompt_variant_default(self, monkeypatch):
        monkeypatch.setenv("PROMPT_VARIANT", "A")
        from src import config
        importlib_reload(config)
        assert config.PROMPT_VARIANT == "A"

    def test_narrator_tone_default(self, monkeypatch):
        monkeypatch.setenv("NARRATOR_TONE", "energetic")
        from src import config
        importlib_reload(config)
        assert config.NARRATOR_TONE == "energetic"

    def test_prompt_variant_env(self, monkeypatch):
        monkeypatch.setenv("PROMPT_VARIANT", "B")
        from src import config
        importlib_reload(config)
        assert config.PROMPT_VARIANT == "B"

    def test_narrator_tone_env(self, monkeypatch):
        monkeypatch.setenv("NARRATOR_TONE", "dramatic")
        from src import config
        importlib_reload(config)
        assert config.NARRATOR_TONE == "dramatic"


# ══════════════════════════════════════════════════════════════
#  GitHub Actions workflow has new env vars
# ══════════════════════════════════════════════════════════════

class TestWorkflowEnvVars:
    """Verify generate.yml contains PROMPT_VARIANT and NARRATOR_TONE."""

    def test_workflow_has_prompt_variant(self):
        wf = Path(__file__).parent.parent / ".github" / "workflows" / "generate.yml"
        content = wf.read_text(encoding="utf-8")
        assert "PROMPT_VARIANT" in content

    def test_workflow_has_narrator_tone(self):
        wf = Path(__file__).parent.parent / ".github" / "workflows" / "generate.yml"
        content = wf.read_text(encoding="utf-8")
        assert "NARRATOR_TONE" in content


# ══════════════════════════════════════════════════════════════
#  Helper
# ══════════════════════════════════════════════════════════════

def importlib_reload(module):
    """Reload a module to pick up env changes."""
    import importlib
    importlib.reload(module)
