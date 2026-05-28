# Contributing to Zscaler RAG Helper

## Adding More Zscaler Pages

Edit the `PHASE1_URLS` list in `scripts/test_crawl.py`:

```python
PHASE1_URLS = [
    # (url, sitemap_lastmod, product)
    ("https://help.zscaler.com/zia/troubleshooting-ssl-inspection", "2026-05-01", "zia"),
    ...
]
```

Products: `zia`, `zpa`, `zdx`, `zcc`, `zdx`.

After adding URLs, run:
```bash
make crawl    # crawl new pages
make ingest   # index into Qdrant
```

To crawl all new/changed pages from the live sitemap automatically:
```bash
make update && make ingest
```

## Adding a New LLM Provider

1. **Create** `llm/{name}_provider.py` implementing `BaseLLMProvider`:

```python
from llm.base import BaseLLMProvider, Message, LLMResponse

class MyProvider(BaseLLMProvider):
    name = "myprovider"

    def complete(self, messages, model, temperature, max_tokens) -> LLMResponse:
        ...

    def available_models(self) -> list[str]:
        return ["model-a", "model-b"]
```

2. **Register** in `llm/factory.py` — add to the `_REGISTRY` dict:
```python
"myprovider": lambda: MyProvider(),
```

3. **Add the key** to `.env.example`:
```
MY_PROVIDER_API_KEY=your_key_here
```

4. **Read it** in `config.py`:
```python
MY_PROVIDER_API_KEY: str = os.getenv("MY_PROVIDER_API_KEY", "")
```

## Code Style

- Follow the existing `Console(highlight=False, emoji=False, markup=True)` pattern for all output (Windows cp1252 compatibility)
- Use type hints on all function signatures
- No new Python package dependencies — use what's in `requirements.txt`
- Keep scripts self-contained with `sys.path.insert(0, ...)` at the top

## Project Structure

```
scripts/        CLI entry points (crawl, ingest, doctor)
crawler/        Crawl4AI + Playwright + sitemap parser
pipeline/       Chunker, embedder, Qdrant indexer
rag/            Retriever + RAG prompt generator
llm/            LLM provider abstraction (Groq, DeepSeek, OpenRouter, Ollama)
api/            FastAPI — OpenAI-compatible endpoints
config.py       Central config loaded from .env
```

## Running the Lint Check

```bash
python -m py_compile scripts/doctor.py api/main.py
```

Or run all files:
```bash
find . -name "*.py" -not -path "./.venv/*" | xargs python -m py_compile
```
