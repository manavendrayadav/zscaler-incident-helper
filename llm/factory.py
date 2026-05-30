"""
Provider registry — maps string names to provider classes.
All providers use the same BaseLLMProvider interface.
"""

from llm.base import BaseLLMProvider

_PROVIDERS: dict[str, type[BaseLLMProvider]] = {}


def _register():
    global _PROVIDERS
    from llm.groq_provider import GroqProvider
    from llm.ollama_provider import OllamaProvider
    from llm.openrouter_provider import OpenRouterProvider

    _PROVIDERS = {
        "groq": GroqProvider,
        "openrouter": OpenRouterProvider,
        "ollama": OllamaProvider,
    }


_register()


def get_provider(name: str) -> BaseLLMProvider:
    """Instantiate and return the named provider."""
    name = name.lower()
    if name not in _PROVIDERS:
        raise ValueError(f"Unknown provider '{name}'. Available: {list(_PROVIDERS)}")
    return _PROVIDERS[name]()


def list_providers() -> list[str]:
    return list(_PROVIDERS.keys())


def all_models() -> dict[str, list[str]]:
    """Return {provider_name: [model, ...]} for building /v1/models listing."""
    result = {}
    for name, cls in _PROVIDERS.items():
        try:
            result[name] = cls().available_models()
        except Exception:
            result[name] = []
    return result
