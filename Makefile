.PHONY: setup crawl crawl-all update ingest up up-infra down logs logs-crawl4ai shell reset-db doctor ollama-setup ollama-vision validate-config lint format typecheck test test-fast test-integration ci pre-commit preflight help

help:
	@echo ""
	@echo "  Zscaler Incident Helper"
	@echo "  ─────────────────────────────────────────────────────────────"
	@echo "  Infrastructure"
	@echo "  make setup            Install host Python deps + Playwright browser"
	@echo "  make up               Start full Docker stack (all services)"
	@echo "  make up-infra         Start only Qdrant + Crawl4AI (for crawling)"
	@echo "  make down             Stop all Docker services"
	@echo "  make logs             Tail rag-api logs"
	@echo "  make logs-crawl4ai    Tail crawl4ai logs"
	@echo "  make shell            Open shell in rag-api container"
	@echo "  make reset-db         Wipe Qdrant volume and restart (fresh index)"
	@echo ""
	@echo "  Knowledge base"
	@echo "  make crawl            Crawl Zscaler docs (skips unchanged pages — safe to run anytime)"
	@echo "  make crawl-all        Same as make crawl + auto-ingest after crawl"
	@echo "  make update           Same as make crawl (crawl_all.py is always incremental)"
	@echo "  make ingest           Chunk + embed + index crawled pages into Qdrant"
	@echo ""
	@echo "  Ollama (local/private LLM)"
	@echo "  make ollama-setup     Start Ollama + pull llama3.2 + llama3.2-vision"
	@echo "  make ollama-vision    Pull additional vision models (llava, moondream, qwen2-vl)"
	@echo ""
	@echo "  Health & validation"
	@echo "  make doctor           Rich terminal health check of the full stack"
	@echo "  make validate-config  Pre-flight check: API keys, Qdrant, embedding dim"
	@echo ""
	@echo "  Development"
	@echo "  make lint             Check code style (ruff)"
	@echo "  make format           Auto-format code (ruff format)"
	@echo "  make typecheck        Type-check with mypy"
	@echo "  make test             Run full test suite"
	@echo "  make test-fast        Run unit tests only (no Docker needed)"
	@echo "  make test-integration Run integration tests (requires running stack)"
	@echo "  make ci               Run lint + typecheck + tests (full local CI)"
	@echo "  make pre-commit       Run all pre-commit hooks on all files"
	@echo ""
	@echo "  Release"
	@echo "  make preflight        Run before every git push: staged-file check + full CI"
	@echo ""

setup:
	pip install qdrant-client groq openai aiofiles rich tqdm langchain-text-splitters
	playwright install chromium

up:
	@echo "Starting Qdrant first (health check takes 30-60s)..."
	docker-compose up -d qdrant
	@echo "Waiting for Qdrant to be healthy..."
	python scripts/wait_healthy.py zih-qdrant 120
	@echo "Starting remaining services..."
	docker-compose up -d
	@echo ""
	@echo "  Services started. Run 'make logs' and wait for 'Application startup complete.'"
	@echo "  OpenWebUI  → http://localhost:3000"
	@echo "  RAG API    → http://localhost:8000"
	@echo "  Qdrant     → http://localhost:6333"
	@echo "  Crawl4AI   → http://localhost:11235"
	@echo ""

up-infra:
	docker-compose up -d qdrant crawl4ai
	@echo "Qdrant + Crawl4AI starting. Wait ~20s then run: make crawl"

# crawl and update both use crawl_all.py — it always skips unchanged pages via the manifest.
# There is no separate "initial vs incremental" distinction needed.
crawl:
	python scripts/crawl_all.py

crawl-all:
	python scripts/crawl_all.py

update:
	python scripts/crawl_all.py

ingest:
	python scripts/ingest.py

down:
	docker-compose down

logs:
	docker-compose logs -f rag-api

logs-crawl4ai:
	docker-compose logs -f crawl4ai

shell:
	docker-compose exec rag-api bash

reset-db:
	docker-compose down -v
	docker-compose up -d qdrant
	@echo "Qdrant volume wiped. Run 'make ingest' to re-index."

doctor:
	python scripts/doctor.py

ollama-setup:
	docker compose --profile local-llm up -d ollama
	@echo "Waiting 10s for Ollama to start..."
	@sleep 10
	docker exec zih-ollama ollama pull llama3.2
	docker exec zih-ollama ollama pull llama3.2-vision
	@echo ""
	@echo "Ollama ready with text + vision models."
	@echo "In OpenWebUI, select: zih/ollama-llama3-2-vision"
	@echo "Attach a screenshot and ask: What is the error in this log?"
	@echo ""

ollama-vision:
	docker exec zih-ollama ollama pull llava
	docker exec zih-ollama ollama pull moondream
	docker exec zih-ollama ollama pull qwen2-vl:7b
	@echo ""
	@echo "Vision models ready: llava, moondream, qwen2-vl:7b"
	@echo "qwen2-vl:7b is recommended for reading text in screenshots (DocVQA 93.1)."
	@echo ""

validate-config:
	python scripts/validate_config.py

# ── Development ───────────────────────────────────────────────────────────────

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy . --ignore-missing-imports

test:
	pytest tests/ -v

test-fast:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v -m integration

ci: lint typecheck test-fast

pre-commit:
	pre-commit run --all-files

# ── Release ───────────────────────────────────────────────────────────────────

preflight:
	@echo "=== Staged file safety check ==="
	@git diff --staged --name-only | grep -iE "\.env$$|\.key$$|secret|^data/" \
		&& echo "WARNING: Potentially sensitive file staged — review before pushing!" \
		|| echo "OK — no sensitive files detected."
	@echo ""
	@echo "=== CI checks (lint + typecheck + tests) ==="
	$(MAKE) ci
	@echo ""
	@echo "Pre-flight PASSED. Safe to push."
