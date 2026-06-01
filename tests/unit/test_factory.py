"""
Unit tests for llm/factory.py

Tests provider routing, error handling, and model listing.
No network calls — all provider constructors are mocked.
"""

from unittest.mock import patch

import pytest


class TestGetProvider:
    def test_groq_provider_returned(self):
        """get_provider("groq") returns a GroqProvider instance."""
        from llm.factory import get_provider
        from llm.groq_provider import GroqProvider

        with patch("llm.groq_provider.GroqProvider.__init__", return_value=None):
            provider = get_provider("groq")
            assert isinstance(provider, GroqProvider)

    def test_openrouter_provider_returned(self):
        from llm.factory import get_provider
        from llm.openrouter_provider import OpenRouterProvider

        with patch("llm.openrouter_provider.OpenRouterProvider.__init__", return_value=None):
            provider = get_provider("openrouter")
            assert isinstance(provider, OpenRouterProvider)

    def test_openai_provider_returned(self):
        from llm.factory import get_provider
        from llm.openai_provider import OpenAIProvider

        with patch("llm.openai_provider.OpenAIProvider.__init__", return_value=None):
            provider = get_provider("openai")
            assert isinstance(provider, OpenAIProvider)

    def test_anthropic_provider_returned(self):
        from llm.factory import get_provider
        from llm.anthropic_provider import AnthropicProvider

        with patch("llm.anthropic_provider.AnthropicProvider.__init__", return_value=None):
            provider = get_provider("anthropic")
            assert isinstance(provider, AnthropicProvider)

    def test_ollama_provider_returned(self):
        from llm.factory import get_provider
        from llm.ollama_provider import OllamaProvider

        with patch("llm.ollama_provider.OllamaProvider.__init__", return_value=None):
            provider = get_provider("ollama")
            assert isinstance(provider, OllamaProvider)

    def test_unknown_provider_raises_value_error(self):
        from llm.factory import get_provider

        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("deepseek")  # removed in Phase 5

    def test_unknown_provider_raises_for_random_name(self):
        from llm.factory import get_provider

        with pytest.raises(ValueError):
            get_provider("nonexistent_provider_xyz")


class TestListProviders:
    def test_returns_list(self):
        from llm.factory import list_providers

        result = list_providers()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_contains_expected_providers(self):
        from llm.factory import list_providers

        providers = list_providers()
        assert "groq" in providers
        assert "openrouter" in providers
        assert "openai" in providers
        assert "anthropic" in providers
        assert "ollama" in providers

    def test_deepseek_not_in_providers(self):
        """DeepSeek was removed in Phase 5 — must not appear."""
        from llm.factory import list_providers

        providers = list_providers()
        assert "deepseek" not in providers

    def test_five_providers_registered(self):
        """Exactly 5 providers: groq, openrouter, openai, anthropic, ollama."""
        from llm.factory import list_providers

        providers = list_providers()
        assert len(providers) == 5


class TestAllModels:
    def test_returns_dict(self):
        from llm.factory import all_models

        result = all_models()
        assert isinstance(result, dict)

    def test_groq_has_models(self):
        from llm.factory import all_models

        models = all_models()
        assert "groq" in models
        assert len(models["groq"]) > 0

    def test_openai_has_models(self):
        from llm.factory import all_models

        models = all_models()
        assert "openai" in models
        assert "gpt-4o-mini" in models["openai"]

    def test_anthropic_has_models(self):
        from llm.factory import all_models

        models = all_models()
        assert "anthropic" in models
        assert any("claude" in m for m in models["anthropic"])

    def test_openrouter_has_no_deepseek(self):
        """DeepSeek models must not appear in OpenRouter list (routes to China)."""
        from llm.factory import all_models

        models = all_models()
        openrouter_models = models.get("openrouter", [])
        assert not any("deepseek" in m.lower() for m in openrouter_models)

    def test_ollama_has_vision_models(self):
        from llm.factory import all_models

        models = all_models()
        assert "ollama" in models
        ollama_models = models["ollama"]
        vision_models = [m for m in ollama_models if "vision" in m.lower() or "vl" in m.lower()]
        assert len(vision_models) > 0
