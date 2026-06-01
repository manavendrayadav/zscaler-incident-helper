# Zscaler RAG Incident Helper

[![CI](https://github.com/manavendrayadav/zscaler-incident-helper/actions/workflows/ci.yml/badge.svg)](https://github.com/manavendrayadav/zscaler-incident-helper/actions/workflows/ci.yml)
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
  vector store      ├── Groq        (llama-3.3-70b, free tier)
                    ├── OpenAI      (gpt-4o, gpt-4o-mini)
                    ├── Anthropic   (claude-opus, claude-sonnet, claude-haiku)
                    ├── OpenRouter  (aggregator — many models)
                    └── Ollama      (local, optional, fully private)
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
- **5 LLM providers** — Groq, OpenAI, Anthropic, OpenRouter, Ollama (swap at query time)
- **Local embeddings** — `all-MiniLM-L6-v2` via sentence-transformers, zero API cost
- **Incremental crawling** — manifest-based; only re-crawls new/changed pages
- **Per-product filtering** — scope retrieval to ZIA, ZPA, or ZDX
- **System health checker** — `make doctor` shows everything at a glance
- **One-command install** — `docker compose up -d` on any machine with Docker

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/zscaler-incident-helper
cd zscaler-incident-helper

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
| `GROQ_API_KEY` | _(optional)_ | Get free at [console.groq.com](https://console.groq.com) |
| `OPENAI_API_KEY` | _(optional)_ | [platform.openai.com](https://platform.openai.com) |
| `ANTHROPIC_API_KEY` | _(optional)_ | [console.anthropic.com](https://console.anthropic.com) |
| `OPENROUTER_API_KEY` | _(optional)_ | [openrouter.ai](https://openrouter.ai) |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Local Ollama endpoint |
| `DEFAULT_PROVIDER` | `groq` | LLM provider used when none specified |
| `DEFAULT_MODEL` | `llama-3.3-70b-versatile` | Model used when none specified |
| `QDRANT_HOST` | `qdrant` | Qdrant hostname (Docker service name) |
| `QDRANT_PORT` | `6333` | Qdrant port |
| `COLLECTION_NAME` | `zscaler_docs` | Qdrant collection name |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | Embedding model (hybrid dense+sparse) |
| `CHUNK_SIZE` | `1500` | Max characters per chunk |
| `TOP_K` | `5` | Chunks retrieved per query |
| `API_KEY` | `zih-api` | Bearer token for the RAG API |
| `CRAWL4AI_BASE_URL` | `http://crawl4ai:11235` | Crawl4AI Docker service URL |

---

## Available Models

| Provider | Models | Notes |
|---|---|---|
| **Groq** | `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `mixtral-8x7b`, `gemma2-9b` | Free tier, fast |
| **OpenAI** | `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `gpt-3.5-turbo` | Pay-per-use |
| **Anthropic** | `claude-opus-4-5`, `claude-sonnet-4-5`, `claude-haiku-3-5` | Pay-per-use |
| **OpenRouter** | `anthropic/claude-sonnet-4-5`, `openai/gpt-4o-mini`, `meta-llama/...`, and more | Pay-per-use aggregator |
| **Ollama** | `llama3.2`, `llama3.1`, `mistral`, `phi3`, `qwen2.5` | **Fully local/private** |

Model selector format in OpenWebUI: `zih/{provider}-{model-slug}`

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
  -H "Authorization: Bearer zih-api" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "zih/groq-llama-3-3-70b-versatile",
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
 qdrant       zih-qdrant    http://localhost:6333   OK
 crawl4ai     zih-crawl4ai  http://localhost:11235  OK
 rag-api      zih-api   http://localhost:8000   OK
 open-webui   open-webui        http://localhost:3000   OK

API Keys
 Provider    Key     Tested
 groq        SET     valid
 openai      SET     --
 anthropic   MISSING --
 openrouter  SET     --
 ollama      http://localhost:11434   3 model(s) pulled

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
- `make` — **built-in on Linux/macOS; Windows needs one extra step:**

  | Windows option | How |
  |----------------|-----|
  | Chocolatey | `choco install make` |
  | Git Bash | Use Git Bash terminal instead of PowerShell — `make` is included |
  | WSL2 | Run commands inside WSL2 shell — `make` is built in |

  > Can't install `make`? Use `python scripts/doctor.py` instead of `make doctor`, `docker compose up -d` instead of `make up`, etc. Full equivalents in [docs/OPERATIONS.md](docs/OPERATIONS.md).

```bash
git clone <repo>
cd zscaler-incident-helper
cp .env.example .env        # add GROQ_API_KEY
make up
make crawl && make ingest
make doctor                 # verify everything is green
```

Then visit `http://localhost:3000`.

---

## System requirements

| | Minimum | Recommended |
|--|---------|-------------|
| **RAM** | 8 GB | 16 GB |
| **CPU** | 4 cores | 8+ cores |
| **Disk** | 15 GB | 25 GB |
| **OS** | Any (Docker required) | Linux/macOS |
| **Initial setup time** | ~4h (CPU embedding) | ~30 min (GPU) |

See [docs/OPERATIONS.md §9](docs/OPERATIONS.md#9-hardware-requirements) for details and GPU setup.

---

## What success looks like

**Query:** "ZPA App Connector shows AUTH_FAILED after certificate renewal"

```markdown
## Root Cause Analysis
AUTH_FAILED after certificate renewal typically indicates the App Connector
is still presenting the old certificate. The ZPA broker rejects the stale cert.

## Step-by-Step Resolution
1. Delete the old connector in the Zscaler Admin Portal
   (Administration → App Connectors → [connector name] → Delete)
2. Re-enroll: download a fresh provisioning key and run the enrollment command
3. Restart the connector service: `sudo systemctl restart zscaler-connector`

## Verification Steps
Monitor the connector status for 2 minutes. Should change:
CONNECTOR_DOWN → CONNECTOR_UP

## References
- https://help.zscaler.com/zpa/troubleshooting-app-connectors
- https://help.zscaler.com/zpa/app-connector-enrollment
```

---

## Quick troubleshooting

| Symptom | Most likely cause | Fix |
|---------|------------------|-----|
| `make doctor` shows rag-api FAIL | Models loading (wait 30s) or stale image | `docker compose build rag-api` |
| Qdrant shows [404] in doctor | Normal — Qdrant uses gRPC health | Ignore; check container status column |
| OpenWebUI "connection refused" | rag-api not healthy yet | Wait and retry; check `make logs` |
| Responses are generic | 0 chunks in Qdrant | `make ingest` (crawl first if needed) |
| 401 on API calls | Missing `Bearer ` prefix | Use `Authorization: Bearer zih-api` |
| Groq call shows Zscaler block page | ZCC SSL inspection intercept | Use Ollama or add bypass in ZIA |

See [docs/OPERATIONS.md §7](docs/OPERATIONS.md#7-troubleshooting) for all error patterns.

---

## Documentation

| Document | Audience | Purpose |
|----------|----------|---------|
| [User Guide](docs/USER_GUIDE.md) | All users | RAG concepts, privacy guide, examples, glossary |
| [Operations Manual](docs/OPERATIONS.md) | Operators | Setup, config, knowledge base, troubleshooting, hardware |
| [Developer Guide](docs/DEVELOPER_GUIDE.md) | Developers | Architecture, API reference, dev setup, ADRs, roadmap |
| [CHANGELOG](CHANGELOG.md) | All | Release history |

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

## Support

Run `make doctor` first — it resolves 80% of issues. Then check [docs/OPERATIONS.md §7 Troubleshooting](docs/OPERATIONS.md). For bugs, open a [GitHub Issue](https://github.com/manavendrayadav/zscaler-incident-helper/issues) with the output of `make doctor`.

---

## Legal

This tool crawls publicly available Zscaler documentation (`help.zscaler.com`) for local indexing. Crawled content is stored locally and is not redistributed. Users are responsible for compliance with Zscaler's terms of service. The knowledge base is user-generated and is not included in this repository.

---

## License

MIT © 2026 Manavendra Yadav — see [LICENSE](LICENSE)
