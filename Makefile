.PHONY: setup uninstall clean crawl crawl-all crawl-gpu update ingest up up-infra down logs logs-crawl4ai shell reset-db doctor ollama-setup ollama-vision validate-config lint format typecheck test test-fast test-integration ci pre-commit preflight help

help:
	@echo ""
	@echo "  Zscaler Incident Helper"
	@echo "  ─────────────────────────────────────────────────────────────"
	@echo "  Infrastructure"
	@echo "  make setup            Install host Python deps + Playwright browser"
	@echo "  make uninstall        Remove Python deps and Playwright browser (reverses setup)"
	@echo "  make clean            Wipe Docker volumes, crawled data, and caches (destructive)"
	@echo "  make up               Start full Docker stack (all services)"
	@echo "  make up-infra         Start only Qdrant + Crawl4AI (for crawling)"
	@echo "  make down             Stop all Docker services"
	@echo "  make logs             Tail rag-api logs"
	@echo "  make logs-crawl4ai    Tail crawl4ai logs"
	@echo "  make shell            Open shell in rag-api container"
	@echo "  make reset-db         Wipe Qdrant volume and restart (fresh index)"
	@echo ""
	@echo "  Knowledge base"
	@echo "  make crawl            Crawl Zscaler docs — saves markdown only, no embedding (CPU safe)"
	@echo "  make ingest           Embed + index all crawled pages into Qdrant (run after crawl)"
	@echo "  make crawl-all        Full pipeline: crawl then ingest sequentially (CPU safe)"
	@echo "  make crawl-gpu        Crawl + inline ingest every 100 pages (GPU machines only)"
	@echo "  make update           Incremental crawl of new/changed pages only (no embedding)"
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
	pip install -r requirements.txt
	python -m playwright install chromium
	python -m playwright install-deps chromium

uninstall:
	python -m playwright uninstall chromium
	pip uninstall -r requirements.txt -y
	@echo ""
	@echo "  Python deps and Playwright browser removed."
	@echo "  Run 'make clean' to also wipe crawled data, caches, and Docker volumes."
	@echo ""

clean:
	docker compose down -v
	python -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ['data/raw', '.mypy_cache', '.pytest_cache', '.ruff_cache']]"
	python -c "import pathlib; [p.unlink(missing_ok=True) for p in [*pathlib.Path('data').glob('*.log'), *pathlib.Path('data').glob('embeddings_cache*'), pathlib.Path('data/crawl_manifest.json')]]"
	@echo ""
	@echo "  Docker volumes, crawled data, and caches removed."
	@echo ""

up:
	@python -c "import subprocess,sys; r=subprocess.run(['docker','info'],capture_output=True); sys.exit(0) if r.returncode==0 else (print('ERROR: Docker is not running. Open Docker Desktop and wait for the whale icon to be steady, then retry.') or sys.exit(1))"
	@echo "Starting Qdrant first (health check takes 30-60s)..."
	docker compose up -d qdrant
	@echo "Waiting for Qdrant to be healthy..."
	python scripts/wait_healthy.py zih-qdrant 120
	@echo "Starting remaining services..."
	docker compose up -d
	@echo ""
	@echo "  Services started. Run 'make logs' and wait for 'Application startup complete.'"
	@echo "  OpenWebUI  → http://localhost:3000"
	@echo "  RAG API    → http://localhost:8000"
	@echo "  Qdrant     → http://localhost:6333"
	@echo "  Crawl4AI   → http://localhost:11235"
	@echo ""

up-infra:
	docker compose up -d qdrant crawl4ai
	@echo "Qdrant + Crawl4AI starting. Wait ~20s then run: make crawl"

# Crawl only — saves markdown files to data/raw/, no embedding.
# Safe on all hardware (CPU or GPU). Run `make ingest` after crawl finishes.
crawl:
	python scripts/crawl_all.py --no-ingest

# Full pipeline for CPU machines: crawl all pages then embed+index in one clean run.
# Keeps the two heavy steps separate so long CPU embedding doesn't timeout Qdrant.
crawl-all:
	python scripts/crawl_all.py --no-ingest
	python scripts/ingest.py

# Crawl + inline ingest every 100 pages.
# Only use this on GPU machines where bge-m3 embedding takes <2 min/batch.
# On CPU (~40 min/batch) the long embedding blocks the connection and causes 408 errors.
crawl-gpu:
	python scripts/crawl_all.py

# Incremental update — crawl new/changed pages only (skips unchanged via manifest).
update:
	python scripts/crawl_all.py --no-ingest

ingest:
	python scripts/ingest.py

down:
	docker compose down

logs:
	docker compose logs -f rag-api

logs-crawl4ai:
	docker compose logs -f crawl4ai

shell:
	docker compose exec rag-api bash

reset-db:
	docker compose down -v
	docker compose up -d qdrant
	@echo "Qdrant volume wiped. Run 'make ingest' to re-index."

doctor:
	python scripts/doctor.py

ollama-setup:
	docker compose --profile local-llm up -d ollama
	@echo "Waiting 10s for Ollama to start..."
	@python -c "import time; time.sleep(10)"
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
	@python scripts/check_staged.py
	@echo ""
	@echo "=== CI checks (lint + typecheck + tests) ==="
	$(MAKE) ci
	@echo ""
	@echo "Pre-flight PASSED. Safe to push."
