# Changelog

All notable changes to this project will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

---

## [Unreleased]

## [1.0.0] — 2026-05-30

### Added
- **RAG pipeline** — full Retrieval-Augmented Generation stack over Zscaler's public documentation
  - Crawl4AI-powered sitemap crawler (1,825 pages across ZIA, ZPA, ZDX, Deception)
  - bge-m3 hybrid dense+sparse embeddings (1024-dim, MTEB 64.3) stored in Qdrant
  - Cross-encoder re-ranking (`cross-encoder/ms-marco-MiniLM-L-6-v2`) with configurable `MIN_SCORE` threshold
  - Deterministic chunk IDs (MD5) for safe re-ingest without duplicates
- **LLM providers** — OpenAI-compatible factory supporting Groq, OpenRouter, and Ollama (local/private)
- **Log analysis mode** — auto-detects pasted log content; Drain3 template mining extracts structured signals for retrieval
- **Vision/screenshot mode** — Ollama vision models (llava, moondream, qwen2-vl:7b) read error screenshots locally
- **OpenWebUI integration** — full chat interface via OpenAI-compatible `/v1/chat/completions` endpoint
- **`make doctor`** — Rich terminal health checker for all services, API keys, knowledge base, and Qdrant stats
- **`make validate-config`** — pre-flight validator for API keys, Qdrant connectivity, and embedding dimension
- **6 SOP documents** — initial-setup, daily-operations, knowledge-base, incident-investigation, llm-providers, troubleshooting
- **Incremental crawl** — `make update` crawls only pages changed since last run (via sitemap `lastmod`)
- **Embedding cache** — `scripts/ingest.py` saves embeddings to disk so a failed upsert never requires re-embedding
- **Docker-first design** — `docker compose up` starts the full stack; bge-m3 baked into image at build time

### Security
- Fixed auth bypass: empty `Authorization` header now correctly returns 401 (was silently passing)
- Removed DeepSeek provider — API routes to China, unacceptable for corporate incident logs
- CORS restricted via `ALLOWED_ORIGINS` env var (replaces hardcoded `allow_origins=["*"]`)
- Bearer token authentication on all `/v1/*` endpoints

### Fixed
- PyTorch fork-safety crash: removed `--workers 1` from uvicorn (forked subprocess corrupted bge-m3 thread pool)
- Qdrant upsert `ReadTimeout`: increased client timeout to 120s, reduced batch size to 32
- OpenWebUI connection: fixed `OPENAI_API_BASE_URLS` env var (plural form required by current OpenWebUI versions)
- Crawl memory leak: replaced per-page `asyncio.run()` loop with single event loop + browser restart every 100 pages

---

## Version History

| Version | Date | Notes |
|---------|------|-------|
| 1.0.0 | 2026-05-30 | Initial public release |
