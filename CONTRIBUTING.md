# Contributing

Thank you for contributing to the Zscaler RAG Incident Helper.

## Quick start

```bash
git clone <repo> && cd zscaler-incident-helper
pip install -e ".[dev]"   # runtime + pytest, ruff, mypy, pre-commit
pre-commit install
cp .env.example .env      # set GROQ_API_KEY
make up && make validate-config
```

Full local setup, test guide, VS Code debug config: **[docs/DEVELOPER_GUIDE.md §13–§17](docs/DEVELOPER_GUIDE.md#13-local-setup)**

## PR workflow

1. Branch from `develop`: `git checkout -b feature/my-feature`
2. Make changes + write tests
3. `make ci` must pass (lint + typecheck + unit tests)
4. Open PR against `develop` using the PR template
5. Update `CHANGELOG.md` under `[Unreleased]`
6. Update `docs/OPERATIONS.md` if an operational procedure changed

## Commit message format

```
feat: add qwen2-vl:7b to Ollama vision models
fix: increase Qdrant upsert timeout to 120s
docs: update LLM provider table in OPERATIONS.md
test: add unit tests for log_parser product detection
```

Types: `feat` `fix` `docs` `test` `refactor` `chore`

## Adding a new LLM provider

Full instructions: [docs/DEVELOPER_GUIDE.md — §5 API Reference and §7 ADRs](docs/DEVELOPER_GUIDE.md)

1. Create `llm/{name}_provider.py` implementing `BaseLLMProvider`
2. Register in `llm/factory.py` `_PROVIDERS`
3. Add to `.env.example`
4. Update `docs/OPERATIONS.md` §6 with privacy posture
5. Write test in `tests/unit/test_factory.py`

## PR checklist

- [ ] `make ci` passes locally
- [ ] Tests added for new functionality
- [ ] `docs/OPERATIONS.md` updated if operational procedure changed
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] `.env.example` updated if new config variables added
