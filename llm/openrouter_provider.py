from openai import OpenAI

from config import cfg
from llm.base import BaseLLMProvider, LLMResponse, Message

MODELS = [
    "deepseek/deepseek-chat",
    "deepseek/deepseek-r1",
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
        model: str = "deepseek/deepseek-chat",
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
