from openai import OpenAI
from config import cfg
from llm.base import BaseLLMProvider, Message, LLMResponse

MODELS = [
    "deepseek-chat",       # DeepSeek V3 — general chat
    "deepseek-reasoner",   # DeepSeek R1 — chain-of-thought reasoning
]


class DeepSeekProvider(BaseLLMProvider):
    name = "deepseek"

    def __init__(self):
        # DeepSeek exposes an OpenAI-compatible endpoint
        self._client = OpenAI(
            base_url="https://api.deepseek.com",
            api_key=cfg.DEEPSEEK_API_KEY,
        )

    def complete(
        self,
        messages: list[Message],
        model: str = "deepseek-chat",
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
