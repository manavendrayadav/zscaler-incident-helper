from groq import Groq

from config import cfg
from llm.base import BaseLLMProvider, LLMResponse, Message

MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
]


class GroqProvider(BaseLLMProvider):
    name = "groq"

    def __init__(self):
        self._client = Groq(api_key=cfg.GROQ_API_KEY)

    def complete(
        self,
        messages: list[Message],
        model: str = "llama-3.3-70b-versatile",
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
            prompt_tokens=resp.usage.prompt_tokens,
            completion_tokens=resp.usage.completion_tokens,
        )

    @classmethod
    def available_models(cls) -> list[str]:
        return MODELS
