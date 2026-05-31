from openai import OpenAI

from config import cfg
from llm.base import BaseLLMProvider, LLMResponse, Message

MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-3.5-turbo",
]


class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def __init__(self):
        self._client = OpenAI(api_key=cfg.OPENAI_API_KEY)

    def complete(
        self,
        messages: list[Message],
        model: str = "gpt-4o-mini",
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
            model=resp.model,
            provider=self.name,
            prompt_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            completion_tokens=resp.usage.completion_tokens if resp.usage else 0,
        )

    def available_models(self) -> list[str]:
        return MODELS
