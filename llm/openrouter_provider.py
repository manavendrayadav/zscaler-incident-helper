from openai import OpenAI

from config import cfg
from llm.base import BaseLLMProvider, LLMResponse, Message

# Note: DeepSeek models are intentionally excluded from this list.
# Even via OpenRouter, requests ultimately route to DeepSeek's servers in China —
# unacceptable for a tool that processes internal corporate incident data.
# See docs/DEVELOPER_GUIDE.md ADR-005 for the full rationale.
MODELS = [
    "anthropic/claude-sonnet-4-5",
    "openai/gpt-4o-mini",
    "meta-llama/llama-3.3-70b-instruct",
    "google/gemini-flash-1.5",
    "mistralai/mistral-nemo",
]


class OpenRouterProvider(BaseLLMProvider):
    name = "openrouter"

    def __init__(self):
        self._client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=cfg.OPENROUTER_API_KEY,
        )

    def complete(
        self,
        messages: list[Message],
        model: str = "meta-llama/llama-3.3-70b-instruct",
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        resp = self._client.chat.completions.create(
            model=model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return LLMResponse(
            content=resp.choices[0].message.content,
            model=model,
            provider=self.name,
            prompt_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            completion_tokens=resp.usage.completion_tokens if resp.usage else 0,
        )

    def available_models(self) -> list[str]:
        return MODELS
