from openai import OpenAI
from config import cfg
from llm.base import BaseLLMProvider, Message, LLMResponse

DEFAULT_MODELS = [
    "llama3.2",
    "llama3.1",
    "mistral",
    "phi3",
    "gemma2",
    "qwen2.5",
    # Vision-capable models — pull with: make ollama-vision
    "llama3.2-vision",   # reads screenshots + attached images
    "llava",             # classic vision model (7B / 13B)
    "moondream",         # lightweight vision (2B, fast on CPU)
    "qwen2-vl:7b",       # best-in-class vision for reading text in screenshots
]


class OllamaProvider(BaseLLMProvider):
    name = "ollama"

    def __init__(self):
        # Ollama's OpenAI-compatible API
        base_url = cfg.OLLAMA_BASE_URL.rstrip("/") + "/v1"
        self._client = OpenAI(base_url=base_url, api_key="ollama")

    def complete(
        self,
        messages: list[Message],
        model: str = "llama3.2",
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
        return DEFAULT_MODELS
