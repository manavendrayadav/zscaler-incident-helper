# Zscaler RAG Incident Helper

[![CI](https://github.com/manavendrayadav/zscaler-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/manavendrayadav/zscaler-rag/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/docker-compose-2496ED)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688)
![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000)

A **self-hosted, portable RAG system** for Zscaler incident resolution. Describe an incident in plain English — get back structured Root Cause Analysis, Step-by-Step Resolution, Verification Steps, and source links, all grounded in real Zscaler documentation.

Built for security engineering teams who are tired of manually searching `help.zscaler.com` during incidents.

---

## Architecture

```
Engineer types incident description
           |
           v
  OpenWebUI  (:3000)          ← team-ready chat UI, conversation history
           |
           v  OpenAI-compatible API
  RAG API  (:8000)            ← FastAPI, handles retrieval + generation
      |              |
      v              v
  Qdrant (:6333)    LLM Providers
  vector store      ├── Groq   (llama-3.3-70b, free tier)
                    ├── DeepSeek
                    ├── OpenRouter
                    └── Ollama (local, optional)
      ^
      |  embed + upsert
  Ingest Pipeline
      ^
      |  crawl → markdown
  Crawl4AI (:11235) + Playwright fallback
      ^
      |
  Zscaler Sitemap (4,103 help pages)
```

---

## Features

- **OpenAI-compatible API** — drop-in for any OpenAI SDK client or UI
- **4 LLM providers** — Groq, DeepSeek, OpenRouter, Ollama (swap at query time)
- **Local embeddings** — `all-MiniLM-L6-v2` via sentence-transformers, zero API cost
- **Incremental crawling** — manifest-based; only re-crawls new/changed pages
- **Per-product filtering** — scope retrieval to ZIA, ZPA, or ZDX
- **System health checker** — `make doctor` shows everything at a glance
- **One-command install** — `docker compose up -d` on any machine with Docker

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/zscaler-rag-helper
cd zscaler-rag-helper

# 2. Configure — add at minimum GROQ_API_KEY (free at console.groq.com)
cp .env.example .env

# 3. Start all Docker services
make up

# 4. Crawl Zscaler docs + index into Qdrant
make crawl
make ingest

# 5. Open the chat UI
open http://localhost:3000   # or visit manually
```

Sign up on first visit (first user becomes admin) → Settings → Connections → verify `http://rag-api:8000/v1` is listed → select a `zscaler-rag/` model → start chatting.

**Check everything is healthy:**
```bash
make doctor
```

---

## Configuration (`.env`)

Copy `.env.example` to `.env` and fill in your values.

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | _(required)_ | Get free at [console.groq.com](https://console.groq.com) |
| `OPENROUTER_API_KEY` | _(optional)_ | [openrouter.ai](https://openrouter.ai) |
| `DEEPSEEK_API_KEY` | _(optional)_ | [platform.deepseek.com](https://platform.deepseek.com) |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Local Ollama endpoint |
| `DEFAULT_PROVIDER` | `groq` | LLM provider used when none specified |
| `DEFAULT_MODEL` | `llama-3.3-70b-versatile` | Model used when none specified |
| `QDRANT_HOST` | `qdrant` | Qdrant hostname (Docker service name) |
| `QDRANT_PORT` | `6333` | Qdrant port |
| `COLLECTION_NAME` | `zscaler_docs` | Qdrant collection name |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | sentence-transformers model |
| `CHUNK_SIZE` | `1500` | Max characters per chunk |
| `TOP_K` | `5` | Chunks retrieved per query |
| `API_KEY` | `zscaler-rag` | Bearer token for the RAG API |
| `CRAWL4AI_BASE_URL` | `http://crawl4ai:11235` | Crawl4AI Docker service URL |

---

## Available Models

| Provider | Models | Notes |
|---|---|---|
| **Groq** | `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `mixtral-8x7b`, `gemma2-9b` | Free tier, ~500 tok/s |
| **DeepSeek** | `deepseek-chat`, `deepseek-reasoner` | ~$0.14/M input tokens |
| **OpenRouter** | `deepseek/deepseek-chat`, `anthropic/claude-sonnet-4-5`, `openai/gpt-4o-mini`, and more | Pay-per-use |
| **Ollama** | `llama3.2`, `llama3.1`, `mistral`, `phi3`, `qwen2.5` | Local, private, needs GPU |

Model selector format in OpenWebUI: `zscaler-rag/{provider}-{model-slug}`

---

## API Reference

Base URL: `http://localhost:8000`

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | No | Qdrant connectivity + chunk count |
| `GET` | `/stats` | No | Collection vector counts |
| `GET` | `/v1/status` | No | Full system status (services, KB, config) |
| `GET` | `/v1/models` | Bearer | List all available RAG models |
| `POST` | `/v1/chat/completions` | Bearer | RAG query — OpenAI-compatible |

**Example query:**
```bash
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer zscaler-rag" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "zscaler-rag/groq-llama-3-3-70b-versatile",
    "messages": [{"role": "user", "content": "ZPA App Connector is not connecting"}]
  }'
```

**Optional RAG parameters** (extra fields on the request body):
- `top_k` (int, default 5) — number of chunks to retrieve
- `product_filter` (string) — `"zia"`, `"zpa"`, or `"zdx"` to scope results

---

## make doctor

Run `make doctor` (or `python scripts/doctor.py`) to get a full system health report:

```
╭─────────────────────────────────────────╮
│  Zscaler RAG  —  System Doctor          │
│  2026-05-28 10:00 UTC                   │
╰─────────────────────────────────────────╯

Services
 Service      Container         HTTP                    Status
 qdrant       zscaler-qdrant    http://localhost:6333   OK
 crawl4ai     zscaler-crawl4ai  http://localhost:11235  OK
 rag-api      zscaler-rag-api   http://localhost:8000   OK
 open-webui   open-webui        http://localhost:3000   OK

API Keys
 Provider    Key     Tested
 groq        SET     valid
 openrouter  SET     --
 deepseek    MISSING --

Knowledge Base
 Pages crawled : 28     ZIA: 10  ZPA: 17  ZDX: 1
 Pages indexed : 28
 Pages stale   : 0
 Raw .md files : 28

Qdrant
 Collection : zscaler_docs   Status: green
 Chunks     : 178   ZIA: 52  ZPA: 118  ZDX: 8

╭────────────────────────────────────────────────╮
│  OK WITH WARNINGS  9 passed  1 warning  0 fail │
╰────────────────────────────────────────────────╯
```

Exit codes: `0` = all OK, `1` = warnings only, `2` = failures.

---

## Scaling to More Pages

The initial setup crawls ~10–20 representative troubleshooting pages. To expand:

```bash
# Incremental: only crawl new/changed pages from the live sitemap
make update
make ingest

# Full reset: wipe and re-index everything
make reset-db
make crawl
make ingest
```

The Zscaler sitemap contains **4,103 pages** across ZIA, ZPA, ZDX, and ZCC. The crawler filters for `troubleshoot`, `error`, `configure`, and `runbook` keywords by default. Edit `crawler/sitemap_parser.py` to change the filter.

---

## Makefile Targets

| Target | Description |
|---|---|
| `make setup` | Install host Python deps + Playwright browser |
| `make up` | Start full Docker stack |
| `make up-infra` | Start only Qdrant + Crawl4AI |
| `make crawl` | Initial crawl of hardcoded Phase 1 URLs |
| `make update` | Incremental crawl (new/changed pages from sitemap) |
| `make ingest` | Chunk + embed + index into Qdrant |
| `make doctor` | System health check |
| `make down` | Stop all services |
| `make reset-db` | Wipe Qdrant volume (fresh start) |
| `make logs` | Tail rag-api container logs |
| `make shell` | Shell into rag-api container |

---

## Team Installation

Each team member needs:
- Docker Desktop (any OS)
- A Groq API key (free)

```bash
git clone <repo>
cd zscaler-rag-helper
cp .env.example .env        # add GROQ_API_KEY
make up
make crawl && make ingest
make doctor                 # verify everything is green
```

Then visit `http://localhost:3000`.

---

## Operations Manual

The full SOP — initial setup, daily operations, incident investigation, LLM provider configuration, and troubleshooting — is in a single document:

**[docs/OPERATIONS.md](docs/OPERATIONS.md)**

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add pages, providers, and submit PRs.

Before your first PR:
```bash
pip install -e ".[dev]"   # installs dev deps (pytest, ruff, mypy, pre-commit)
pre-commit install         # install hooks
make ci                    # lint + typecheck + tests — must pass before PR
```

---

## Security

For vulnerability reports and data privacy guidance, see [SECURITY.md](SECURITY.md).

---

## License

MIT © 2026 Manav Yadav — see [LICENSE](LICENSE)
