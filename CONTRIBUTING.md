# Contributing to Zscaler RAG Incident Helper

Thank you for contributing! This document covers local setup, the PR workflow, and how to extend the project.

---

## Table of Contents

1. [Local Development Setup](#1-local-development-setup)
2. [PR Workflow](#2-pr-workflow)
3. [Commit Message Format](#3-commit-message-format)
4. [Adding Zscaler Documentation Pages](#4-adding-zscaler-documentation-pages)
5. [Adding a New LLM Provider](#5-adding-a-new-llm-provider)
6. [Running Tests](#6-running-tests)
7. [Code Style](#7-code-style)
8. [Project Structure](#8-project-structure)

---

## 1. Local Development Setup

```bash
git clone <repo-url> Zscalerhelper
cd Zscalerhelper
cp .env.example .env              # fill in at least GROQ_API_KEY
pip install -e ".[dev]"           # runtime + dev deps (pytest, ruff, mypy, pre-commit)
pre-commit install                # hooks run on every git commit
make up                           # start Docker stack
make validate-config              # confirm everything is wired up
```

After that, run `make ci` to confirm your environment is clean:

```bash
make ci    # lint + typecheck + unit tests — all must pass
```

---

## 2. PR Workflow

1. **Branch** from `develop` (not `main`):
   ```bash
   git checkout develop
   git pull
   git checkout -b feature/my-feature
   ```

2. **Make your changes**, write or update tests

3. **Run CI locally** before pushing:
   ```bash
   make ci
   ```

4. **Open PR** against `develop` using the PR template
   - Fill in the Summary, Type of change, Checklist, and Test plan
   - Update `CHANGELOG.md` under `[Unreleased]`
   - Update `docs/OPERATIONS.md` if any operational procedure changed

5. **Review**: at least one maintainer approval required before merge

6. **Releases**: PRs are periodically batch-merged from `develop` → `main` and tagged

---

## 3. Commit Message Format

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <short description>

[optional body]
```

Types:
- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation only
- `test:` — adding or fixing tests
- `refactor:` — code restructure without behaviour change
- `chore:` — dependency updates, CI changes, tooling

Examples:
```
feat: add qwen2-vl:7b to Ollama vision models
fix: increase Qdrant upsert timeout to 120s
docs: update LLM provider table in OPERATIONS.md
test: add unit tests for log_parser product detection
```

---

## 4. Adding Zscaler Documentation Pages

The sitemap crawler (`scripts/crawl_all.py`) handles all 1,825+ pages automatically.
For targeted additions:

1. Edit the `PHASE1_URLS` list in `scripts/test_crawl.py`:
   ```python
   PHASE1_URLS = [
       # (url, sitemap_lastmod, product)
       ("https://help.zscaler.com/zia/my-new-page", "2026-06-01", "zia"),
   ]
   ```
   Products: `zia`, `zpa`, `zdx`, `deception`, `zcc`

2. Crawl and index the new pages:
   ```bash
   make crawl    # crawl test URLs
   make ingest   # index into Qdrant
   ```

For incremental updates (new/changed pages from live sitemap):
```bash
make update && make ingest
```

---

## 5. Adding a New LLM Provider

1. **Create** `llm/{name}_provider.py` implementing `BaseLLMProvider`:

   ```python
   from llm.base import BaseLLMProvider, Message, LLMResponse

   class MyProvider(BaseLLMProvider):
       name = "myprovider"
       DEFAULT_MODELS = ["model-a", "model-b"]

       def __init__(self, model: str | None = None):
           self._model = model or self.DEFAULT_MODELS[0]

       def complete(
           self, messages: list[Message], model: str, temperature: float, max_tokens: int
       ) -> LLMResponse:
           ...

       def available_models(self) -> list[str]:
           return self.DEFAULT_MODELS
   ```

2. **Register** in `llm/factory.py`:
   ```python
   from llm.myprovider_provider import MyProvider
   _PROVIDERS["myprovider"] = MyProvider
   ```

3. **Add the key** to `.env.example` with a comment explaining the provider's privacy posture

4. **Read the key** in `config.py`:
   ```python
   MY_PROVIDER_API_KEY: str = os.getenv("MY_PROVIDER_API_KEY", "")
   ```

5. **Update** `docs/OPERATIONS.md` §6 with:
   - Where data goes (which country/cloud)
   - Available models table
   - Any privacy caveats

6. **Write a test** in `tests/unit/test_factory.py`

---

## 6. Running Tests

```bash
make test-fast        # unit tests only — no Docker needed, fast (~10s)
make test             # full suite including integration tests (requires running stack)
make test-integration # integration tests only
```

**Unit tests** (`tests/unit/`) use mocks — no ML models or external services needed.
**Integration tests** (`tests/integration/`) require `make up` to be running.

To run a single test file:
```bash
pytest tests/unit/test_log_parser.py -v
```

---

## 7. Code Style

- **Formatter**: `ruff format` (double quotes, 100-char line length)
- **Linter**: `ruff check` (E, F, I, UP, B, SIM, C4 rules)
- **Type hints**: required on all public function signatures
- **Console output**: use `Console(highlight=False, emoji=False, markup=True)` for Windows cp1252 compatibility
- **No new dependencies** without discussion — use what's in `requirements.txt`
- **Scripts**: keep self-contained with `sys.path.insert(0, ...)` at the top

Run all checks:
```bash
make lint         # style check
make format       # auto-fix formatting
make typecheck    # mypy type check
```

Pre-commit hooks run `ruff` automatically on every `git commit`.

---

## 8. Project Structure

```
api/            FastAPI — OpenAI-compatible /v1/ endpoints
crawler/        Crawl4AI + Playwright + sitemap parser
pipeline/       Chunker → bge-m3 embedder → Qdrant indexer
rag/            Hybrid retriever + cross-encoder + RAG generator + log parser
llm/            Provider factory + Groq / OpenRouter / Ollama implementations
scripts/        CLI tools: crawl_all, ingest, doctor, validate_config
tests/          pytest suite: unit/ (fast) + integration/ (Docker)
docs/           OPERATIONS.md — single-file operations manual
config.py       Central config loaded from .env via python-dotenv
```
