"""
Tests for Phase 6.3 — Multi-Language Content (Bahasa Indonesia)
Covers: config, tts voice selection, llm narration hint injection
"""
from __future__ import annotations

import importlib
import os
from unittest.mock import MagicMock, patch


# ══════════════════════════════════════════════════════════════
#  config.py — new Phase 6.3 fields
# ══════════════════════════════════════════════════════════════

class TestConfigPhase63:
    def test_content_language_default_is_en(self):
        saved = os.environ.pop("CONTENT_LANGUAGE", None)
        try:
            import src.config as cfg
            importlib.reload(cfg)
            assert cfg.CONTENT_LANGUAGE == "en"
        finally:
            if saved is not None:
                os.environ["CONTENT_LANGUAGE"] = saved
            importlib.reload(cfg)

    def test_content_language_env_override(self):
        os.environ["CONTENT_LANGUAGE"] = "id"
        try:
            import src.config as cfg
            importlib.reload(cfg)
            assert cfg.CONTENT_LANGUAGE == "id"
        finally:
            del os.environ["CONTENT_LANGUAGE"]
            importlib.reload(cfg)

    def test_tts_voice_id_default(self):
        saved = os.environ.pop("TTS_VOICE_ID", None)
        try:
            import src.config as cfg
            importlib.reload(cfg)
            assert cfg.TTS_VOICE_ID == "id-ID-GadisNeural"
        finally:
            if saved is not None:
                os.environ["TTS_VOICE_ID"] = saved
            importlib.reload(cfg)

    def test_tts_voice_id_env_override(self):
        os.environ["TTS_VOICE_ID"] = "id-ID-ArdiNeural"
        try:
            import src.config as cfg
            importlib.reload(cfg)
            assert cfg.TTS_VOICE_ID == "id-ID-ArdiNeural"
        finally:
            del os.environ["TTS_VOICE_ID"]
            importlib.reload(cfg)


# ══════════════════════════════════════════════════════════════
#  tts.generate_speech — voice auto-selection
# ══════════════════════════════════════════════════════════════

class TestTtsVoiceSelection:
    def _run_generate_speech(
        self,
        content_language: str,
        explicit_voice: str | None = None,
    ) -> str:
        """
        Calls generate_speech() with mocked asyncio.run, returning the voice
        that was passed to the async helper.
        """
        captured_voice: list[str] = []

        async def fake_async(text, voice, output_path):
            captured_voice.append(voice)
            return []

        with (
            patch("src.config.CONTENT_LANGUAGE", content_language),
            patch("src.config.TTS_VOICE", "en-US-ChristopherNeural"),
            patch("src.config.TTS_VOICE_ID", "id-ID-GadisNeural"),
            patch("src.tts._generate_speech_async", side_effect=fake_async),
            patch("src.tts.asyncio.run", side_effect=lambda coro: coro.send(None) or []),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.stat") as mock_stat,
        ):
            mock_stat.return_value.st_size = 10_000
            from src.tts import generate_speech
            try:
                generate_speech("Hello world.", voice=explicit_voice, output_path="/tmp/test.mp3")
            except Exception:
                pass
        return captured_voice[0] if captured_voice else ""

    def test_en_language_uses_en_voice(self):
        """When CONTENT_LANGUAGE=en and no explicit voice, use TTS_VOICE."""
        captured: list[str] = []

        async def fake_async(text, voice, path):
            captured.append(voice)
            return []

        import asyncio

        def fake_run(coro):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        with (
            patch("src.config.CONTENT_LANGUAGE", "en"),
            patch("src.config.TTS_VOICE", "en-US-ChristopherNeural"),
            patch("src.config.TTS_VOICE_ID", "id-ID-GadisNeural"),
            patch("src.tts._generate_speech_async", side_effect=fake_async),
            patch("src.tts.asyncio.run", side_effect=fake_run),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.stat") as mock_stat,
        ):
            mock_stat.return_value.st_size = 9_999
            from src.tts import generate_speech
            try:
                generate_speech("Some text.", voice=None, output_path="/tmp/test_en.mp3")
            except Exception:
                pass

        assert len(captured) == 1
        assert captured[0] == "en-US-ChristopherNeural"

    def test_id_language_uses_id_voice(self):
        """When CONTENT_LANGUAGE=id, voice should auto-select TTS_VOICE_ID."""
        captured: list[str] = []

        async def fake_async(text, voice, path):
            captured.append(voice)
            return []

        import asyncio

        def fake_run(coro):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        with (
            patch("src.config.CONTENT_LANGUAGE", "id"),
            patch("src.config.TTS_VOICE", "en-US-ChristopherNeural"),
            patch("src.config.TTS_VOICE_ID", "id-ID-GadisNeural"),
            patch("src.tts._generate_speech_async", side_effect=fake_async),
            patch("src.tts.asyncio.run", side_effect=fake_run),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.stat") as mock_stat,
        ):
            mock_stat.return_value.st_size = 9_999
            from src.tts import generate_speech
            try:
                generate_speech("Teks bahasa Indonesia.", voice=None, output_path="/tmp/test_id.mp3")
            except Exception:
                pass

        assert len(captured) == 1
        assert captured[0] == "id-ID-GadisNeural"

    def test_explicit_voice_overrides_language_setting(self):
        """Explicit voice parameter always wins over language auto-select."""
        captured: list[str] = []

        async def fake_async(text, voice, path):
            captured.append(voice)
            return []

        import asyncio

        def fake_run(coro):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        with (
            patch("src.config.CONTENT_LANGUAGE", "id"),
            patch("src.config.TTS_VOICE", "en-US-ChristopherNeural"),
            patch("src.config.TTS_VOICE_ID", "id-ID-GadisNeural"),
            patch("src.tts._generate_speech_async", side_effect=fake_async),
            patch("src.tts.asyncio.run", side_effect=fake_run),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.stat") as mock_stat,
        ):
            mock_stat.return_value.st_size = 9_999
            from src.tts import generate_speech
            try:
                generate_speech("Text.", voice="en-GB-RyanNeural", output_path="/tmp/ovr.mp3")
            except Exception:
                pass

        assert len(captured) == 1
        assert captured[0] == "en-GB-RyanNeural"

    def test_ardi_voice_variant_works(self):
        """TTS_VOICE_ID=id-ID-ArdiNeural (male option) is used correctly."""
        captured: list[str] = []

        async def fake_async(text, voice, path):
            captured.append(voice)
            return []

        import asyncio

        def fake_run(coro):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        with (
            patch("src.config.CONTENT_LANGUAGE", "id"),
            patch("src.config.TTS_VOICE", "en-US-ChristopherNeural"),
            patch("src.config.TTS_VOICE_ID", "id-ID-ArdiNeural"),
            patch("src.tts._generate_speech_async", side_effect=fake_async),
            patch("src.tts.asyncio.run", side_effect=fake_run),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.stat") as mock_stat,
        ):
            mock_stat.return_value.st_size = 9_999
            from src.tts import generate_speech
            try:
                generate_speech("Halo!", voice=None, output_path="/tmp/ardi.mp3")
            except Exception:
                pass

        assert len(captured) == 1
        assert captured[0] == "id-ID-ArdiNeural"


# ══════════════════════════════════════════════════════════════
#  llm.generate_content — narration_lang_hint injection
# ══════════════════════════════════════════════════════════════

class TestNarrationLangHintInLLM:
    def _capture_prompt(self, content_language: str) -> str:
        """Run generate_content; intercept contents arg; return it."""
        captured: list[str] = []

        def fake_generate(model, contents, config):
            captured.append(contents)
            raise RuntimeError("stop_sentinel")

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = fake_generate

        with (
            patch("src.config.CONTENT_LANGUAGE", content_language),
            patch("src.llm.config.CONTENT_LANGUAGE", content_language),
            patch("src.config.ENABLE_TRENDING", "0"),
            patch("src.config.ENABLE_YT_ANALYTICS", "0"),
            patch("src.config.GEMINI_API_KEY", "fake_key"),
            patch("src.llm.get_past_topics", return_value=[]),
            patch("src.llm.genai.Client", return_value=mock_client),
        ):
            from src.llm import generate_content
            try:
                generate_content()
            except RuntimeError:
                pass

        return captured[0] if captured else ""

    def test_no_hint_when_language_is_en(self):
        prompt = self._capture_prompt("en")
        assert "LANGUAGE INSTRUCTION" not in prompt
        assert "Bahasa Indonesia" not in prompt

    def test_hint_injected_when_language_is_id(self):
        prompt = self._capture_prompt("id")
        assert "LANGUAGE INSTRUCTION" in prompt
        assert "Bahasa Indonesia" in prompt

    def test_id_hint_includes_example_phrases(self):
        prompt = self._capture_prompt("id")
        assert "Tau gak sih" in prompt

    def test_id_hint_instructs_code_stays_in_english(self):
        """Instruction must say code identifiers remain in English."""
        prompt = self._capture_prompt("id")
        assert "English" in prompt

    def test_hint_does_not_appear_for_unknown_language(self):
        """Any value other than 'id' should not inject Indonesian hint."""
        prompt = self._capture_prompt("fr")
        assert "Bahasa Indonesia" not in prompt

    def test_en_content_has_normal_prompt_structure(self):
        """EN mode prompt must still contain the main generation instruction."""
        prompt = self._capture_prompt("en")
        assert "Return valid JSON only" in prompt

    def test_id_content_has_normal_prompt_structure(self):
        """ID mode prompt must still contain core generation instruction."""
        prompt = self._capture_prompt("id")
        assert "Return valid JSON only" in prompt


# ══════════════════════════════════════════════════════════════
#  Integration: CONTENT_LANGUAGE flows through both tts + llm
# ══════════════════════════════════════════════════════════════

class TestContentLanguageIntegration:
    def test_id_language_affects_both_tts_voice_and_prompt(self):
        """
        With CONTENT_LANGUAGE=id:
        - LLM prompt contains LANGUAGE INSTRUCTION
        - TTS voice resolves to ID voice
        """
        # 1. Check LLM hint
        captured_prompt: list[str] = []

        def fake_generate(model, contents, config):
            captured_prompt.append(contents)
            raise RuntimeError("stop")

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = fake_generate

        with (
            patch("src.config.CONTENT_LANGUAGE", "id"),
            patch("src.llm.config.CONTENT_LANGUAGE", "id"),
            patch("src.config.ENABLE_TRENDING", "0"),
            patch("src.config.ENABLE_YT_ANALYTICS", "0"),
            patch("src.config.GEMINI_API_KEY", "fake_key"),
            patch("src.llm.get_past_topics", return_value=[]),
            patch("src.llm.genai.Client", return_value=mock_client),
        ):
            from src.llm import generate_content
            try:
                generate_content()
            except RuntimeError:
                pass

        assert captured_prompt, "LLM should have been called"
        assert "LANGUAGE INSTRUCTION" in captured_prompt[0]

        # 2. Check TTS voice selection
        captured_voice: list[str] = []

        async def fake_async(text, voice, path):
            captured_voice.append(voice)
            return []

        import asyncio

        def fake_run(coro):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        with (
            patch("src.config.CONTENT_LANGUAGE", "id"),
            patch("src.config.TTS_VOICE", "en-US-ChristopherNeural"),
            patch("src.config.TTS_VOICE_ID", "id-ID-GadisNeural"),
            patch("src.tts._generate_speech_async", side_effect=fake_async),
            patch("src.tts.asyncio.run", side_effect=fake_run),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.stat") as mock_stat,
        ):
            mock_stat.return_value.st_size = 9_999
            from src.tts import generate_speech
            try:
                generate_speech("Halo semua!", output_path="/tmp/integ.mp3")
            except Exception:
                pass

        assert captured_voice and captured_voice[0] == "id-ID-GadisNeural"
