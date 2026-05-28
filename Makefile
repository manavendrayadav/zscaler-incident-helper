.PHONY: setup crawl update ingest up up-infra down logs logs-crawl4ai shell reset-db doctor help

help:
	@echo ""
	@echo "  Zscaler RAG Incident Helper"
	@echo "  ─────────────────────────────────────────────────────────────"
	@echo "  make setup         Install host Python deps + Playwright browser"
	@echo "  make up            Start full Docker stack (all services)"
	@echo "  make up-infra      Start only Qdrant + Crawl4AI (for crawling)"
	@echo "  make crawl         Phase 1: crawl 5-10 Zscaler pages (initial)"
	@echo "  make update        Incremental: crawl only new/changed pages"
	@echo "  make ingest        Chunk + embed + index crawled pages into Qdrant"
	@echo "  make down          Stop all Docker services"
	@echo "  make logs          Tail rag-api logs"
	@echo "  make logs-crawl4ai Tail crawl4ai logs"
	@echo "  make shell         Open shell in rag-api container"
	@echo "  make reset-db      Wipe Qdrant volume and restart (fresh index)"
	@echo ""

setup:
	pip install qdrant-client groq openai aiofiles rich tqdm langchain-text-splitters
	playwright install chromium

up:
	docker-compose up -d
	@echo ""
	@echo "  Services starting (allow ~30s for crawl4ai to be ready)..."
	@echo "  OpenWebUI  → http://localhost:3000"
	@echo "  RAG API    → http://localhost:8000"
	@echo "  Qdrant     → http://localhost:6333"
	@echo "  Crawl4AI   → http://localhost:11235"
	@echo ""

up-infra:
	docker-compose up -d qdrant crawl4ai
	@echo "Qdrant + Crawl4AI starting. Wait ~20s then run: make crawl"

crawl:
	python scripts/test_crawl.py

update:
	python scripts/test_crawl.py --update

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
