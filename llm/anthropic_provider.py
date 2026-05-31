import anthropic

from config import cfg
from llm.base import BaseLLMProvider, LLMResponse, Message

MODELS = [
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-haiku-3-5",
]


class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"

    def __init__(self):
        self._client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)

    def complete(
        self,
        messages: list[Message],
        model: str = "claude-haiku-3-5",
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        # Anthropic API requires the system prompt as a separate kwarg,
        # not as a message with role="system".
        system_content = " ".join(
            m.content for m in messages if m.role == "system" and isinstance(m.content, str)
        )
        user_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role != "system"
        ]

        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": user_messages,
        }
        if system_content:
            kwargs["system"] = system_content

        resp = self._client.messages.create(**kwargs)

        return LLMResponse(
            content=resp.content[0].text,
            model=resp.model,
            provider=self.name,
            prompt_tokens=resp.usage.input_tokens,
            completion_tokens=resp.usage.output_tokens,
        )

    def available_models(self) -> list[str]:
        return MODELS
