# Development Guide

Setup guide for contributors who want to run the project locally, write tests, and submit pull requests.

For the high-level contribution process (branching, PRs, commit messages), see [CONTRIBUTING.md](../CONTRIBUTING.md).

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.12 | Runtime (use pyenv or mise to manage versions) |
| Docker Desktop | Latest | Running the service stack locally |
| Git | Any | Version control |
| VS Code | Recommended | IDE with good Python tooling |

---

## Local setup

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/manavendrayadav/zscaler-rag.git
cd zscaler-rag

# Python 3.12 (pyenv users)
pyenv local 3.12

# Create virtual environment
python -m venv .venv
source .venv/bin/activate    # Linux/Mac
# or
.venv\Scripts\activate       # Windows PowerShell
```

### 2. Install runtime + dev dependencies

```bash
pip install -e ".[dev]"
```

This installs everything in `requirements.txt` plus dev tools: `pytest`, `pytest-cov`, `ruff`, `mypy`, `pre-commit`, `httpx`.

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env: set GROQ_API_KEY at minimum
```

### 4. Install pre-commit hooks

```bash
pre-commit install
```

This installs hooks that run automatically on every `git commit`:
- `ruff` — style check + auto-fix imports
- `ruff-format` — auto-format code
- `trailing-whitespace`, `end-of-file-fixer` — housekeeping
- `detect-private-key` — prevents accidental secret commits

### 5. Start the Docker stack

```bash
make up           # starts Qdrant, Crawl4AI, RAG API, OpenWebUI
make validate-config  # verify everything is connected
```

---

## Running tests

### Unit tests (no Docker needed, ~10 seconds)

```bash
make test-fast
# or directly:
pytest tests/unit/ -v
```

Unit tests use mocks for all external services (bge-m3, Qdrant, LLM providers). No Docker, no internet connection required.

### Full test suite

```bash
make test
# or:
pytest tests/ -v
```

### Integration tests (requires running stack)

```bash
make up              # start Docker stack first
make test-integration
# or:
pytest tests/integration/ -v -m integration
```

### Coverage report

```bash
pytest tests/unit/ --cov=. --cov-report=html --cov-omit="tests/*,scripts/*"
open htmlcov/index.html   # Linux/Mac
start htmlcov/index.html  # Windows
```

---

## Code quality

### Linting

```bash
make lint
# or:
ruff check .
```

### Auto-format

```bash
make format
# or:
ruff format .
```

### Type checking

```bash
make typecheck
# or:
mypy . --ignore-missing-imports
```

### Run all checks (before opening a PR)

```bash
make ci    # lint + typecheck + test-fast
```

---

## Understanding the test suite

### Directory structure

```
tests/
├── conftest.py          # Shared fixtures (mock embedder, Qdrant, LLM)
├── fixtures/
│   └── sample_logs.txt  # Mock ZPA log lines for log_parser tests
├── unit/
│   ├── test_api_auth.py    # auth bypass fix coverage; 401 on missing header
│   ├── test_chunker.py     # frontmatter parsing, deterministic chunk IDs
│   ├── test_config.py      # env var loading, type coercion, defaults
│   ├── test_factory.py     # provider routing, deepseek removed check
│   └── test_log_parser.py  # is_log_content, extract_signals, detect_product
└── integration/
    └── (empty — integration tests are a v1.1.0 goal)
```

### Mocking strategy

Unit tests avoid loading heavy ML models. Key mocks in `conftest.py`:

| What's mocked | Fixture | Why |
|---------------|---------|-----|
| `pipeline.embedder.embed_query` | `mock_embed_query_hybrid` | bge-m3 takes 30s to load |
| `qdrant_client.QdrantClient` | `mock_qdrant_client` | No Qdrant needed for unit tests |
| `rag.generator.generate` | `mock_generate` | No LLM API call |

### Writing a new unit test

1. Identify the function to test (e.g., `rag/log_parser.py::is_log_content`)
2. Find or create the test file (`tests/unit/test_log_parser.py`)
3. Use existing fixtures from `conftest.py` when possible
4. Mark integration tests with `@pytest.mark.integration`

**Template:**

```python
# tests/unit/test_my_module.py
import pytest
from my_module import my_function


class TestMyFunction:
    def test_normal_case(self):
        result = my_function("valid input")
        assert result == "expected output"

    def test_edge_case_empty_input(self):
        result = my_function("")
        assert result is None  # or whatever the expected behaviour is

    def test_raises_on_invalid(self):
        with pytest.raises(ValueError, match="expected error message"):
            my_function(None)
```

---

## Debugging in VS Code

Add this `launch.json` to `.vscode/`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Run RAG API (local)",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": ["api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
      "env": {
        "QDRANT_HOST": "localhost",
        "QDRANT_PORT": "6333"
      },
      "console": "integratedTerminal"
    },
    {
      "name": "Run pytest",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": ["tests/unit/", "-v"],
      "console": "integratedTerminal"
    }
  ]
}
```

> **Note:** `--reload` enables hot-reload on code changes. Requires Qdrant running via `make up-infra`.

### Recommended VS Code extensions

- `ms-python.python` — Python support
- `ms-python.ruff` — ruff inline linting
- `ms-python.mypy-type-checker` — mypy inline type checking
- `ms-azuretools.vscode-docker` — Docker container management
- `humao.rest-client` — test API calls from `.http` files

---

## Making a code change — checklist

Before opening a PR:

1. **Write tests** for new functionality
2. **Run `make ci`** — all checks must pass locally:
   ```bash
   make ci   # lint + typecheck + unit tests
   ```
3. **Update docs** if you changed behaviour:
   - `docs/OPERATIONS.md` if operational procedure changed
   - `docs/CONFIGURATION.md` if `.env` variables changed
   - `docs/API.md` if endpoints or request/response changed
   - `CHANGELOG.md` under `[Unreleased]`
4. **Update `.env.example`** if new config variables were added
5. **Test Docker build** if `Dockerfile` or `requirements.txt` changed:
   ```bash
   docker compose build rag-api
   docker compose up -d rag-api
   make doctor   # verify healthy
   ```

---

## Common gotchas

| Problem | Solution |
|---------|---------|
| `import config` fails in test | `sys.path.insert(0, str(Path(__file__).parent.parent))` at top of test file |
| `QdrantClient` patch fails | QdrantClient is lazy-imported inside functions; patch at `qdrant_client.QdrantClient` not `rag.retriever.QdrantClient` |
| `bge-m3 loads during tests` | Ensure `pipeline.embedder.get_model` is patched via `conftest.py` fixtures |
| `ruff` fails on `from __future__ import annotations` | Ensure Python 3.12 — this import is only needed for 3.9 compat |
| Pre-commit fails on large binary file | Add to `.gitignore` or increase `check-added-large-files` limit in `.pre-commit-config.yaml` |
