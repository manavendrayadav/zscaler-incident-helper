# Developer Guide

Everything developers and contributors need: how the system works internally, the full API reference, local development setup, and the reasoning behind key architectural decisions.

---

## Table of Contents

**Architecture**
1. [System overview](#1-system-overview)
2. [System components](#2-system-components)
3. [Query pipeline — step by step](#3-query-pipeline--step-by-step)
4. [Knowledge base pipeline](#4-knowledge-base-pipeline)
5. [Log analysis mode](#5-log-analysis-mode)
6. [Privacy architecture](#6-privacy-architecture)
7. [File map](#7-file-map)

**API Reference**
8. [Authentication](#8-authentication)
9. [Endpoints](#9-endpoints)
10. [Error codes](#10-error-codes)
11. [Model naming](#11-model-naming)
12. [Vision / image content](#12-vision--image-content)

**Development**
13. [Local setup](#13-local-setup)
14. [Running tests](#14-running-tests)
15. [Code quality](#15-code-quality)
16. [Test suite guide](#16-test-suite-guide)
17. [VS Code setup](#17-vs-code-setup)
18. [Pre-PR checklist](#18-pre-pr-checklist)

**Decisions**
19. [Architecture Decision Records](#19-architecture-decision-records)
20. [Roadmap](#20-roadmap)

---

## 1. System overview

The system is a **Retrieval-Augmented Generation (RAG)** pipeline: instead of answering from training data, it first retrieves the most relevant Zscaler documentation pages, then asks the AI to generate an answer grounded in those pages.

```
User query
    │
    ▼
OpenWebUI (chat UI)
    │  POST /v1/chat/completions
    ▼
RAG API (FastAPI)
    │
    ├── embed_query()    ── bge-m3 model → 1024-dim dense + sparse vectors
    │
    ├── retrieve()       ── Qdrant hybrid search (dense + sparse)
    │                       Cross-encoder re-ranking
    │                       MIN_SCORE filter
    │
    └── generate()       ── LLM (Groq / Ollama / OpenRouter)
                            RAG prompt = query + top-5 chunks
                            → structured Markdown response
```

---

## 2. System components

| Service | Container | Port | Role |
|---------|-----------|------|------|
| **OpenWebUI** | `zih-openwebui` | 3000 | Chat interface. Multi-user, conversation history, model switching. Treats the RAG API as an OpenAI-compatible backend — no code changes needed. |
| **RAG API** | `zih-api` | 8000 | Core service. FastAPI. Handles auth, routing, embedding, retrieval, generation, OpenAI-format responses. |
| **Qdrant** | `zih-qdrant` | 6333 | Vector database. ~13,800 chunk embeddings with metadata. Dense, sparse, and hybrid search. |
| **Crawl4AI** | `zih-crawl4ai` | 11235 | Headless browser crawler. Accepts URLs via HTTP, returns cleaned Markdown. Used only during knowledge base setup. |
| **Ollama** (optional) | `zih-ollama` | 11434 | Local LLM runtime. Started with `make ollama-setup` (Docker profile `local-llm`). |

### Startup dependency chain

```
Qdrant starts first (healthcheck: TCP 6333)
    ↓ healthy
RAG API starts (bge-m3 + cross-encoder load from baked image layers, ~20s)
    ↓ healthy
OpenWebUI starts (connects to RAG API at http://rag-api:8000/v1)
```

Crawl4AI starts independently — only needed for crawl operations.

---

## 3. Query pipeline — step by step

### Step 1 — HTTP request arrives

```
POST /v1/chat/completions
Authorization: Bearer zih-api
{"model": "zih/groq-llama-3-3-70b-versatile",
 "messages": [{"role": "user", "content": "ZPA tunnel down causes?"}]}
```

File: `api/main.py` — `chat_completions()`

### Step 2 — Mode detection

- Has image attachments? → `log_analysis` mode
- Text looks like a log? (timestamps + error keywords) → `log_analysis` mode
- Otherwise → `doc_search` mode

File: `api/main.py`, `rag/log_parser.py` — `is_log_content()`, `detect_product_from_logs()`

### Step 3 — Query embedding

bge-m3 generates two representations:

```python
query_embedding = {
    "dense": [0.021, -0.154, ..., 0.033],  # 1024 floats — semantic meaning
    "sparse": {"531": 0.8, "1024": 0.5}    # token_id → weight — keyword matching
}
```

File: `pipeline/embedder.py` — `embed_query()`

### Step 4 — Qdrant hybrid search

Single `query_points()` call with `Prefetch` + `FusionQuery(RRF)`:
1. Dense search: "find the 20 chunks most similar in meaning"
2. Sparse search: "find the 20 chunks with the most matching keywords"
3. RRF fusion: merge both ranked lists into a single unified ranking

File: `rag/retriever.py` — `_search_hybrid()`

### Step 5 — Cross-encoder re-ranking

Each of the 20 candidates scored as a (query, chunk) pair:

```python
scores = cross_encoder.predict([
    ("ZPA tunnel down causes?", chunk_1_text),
    ...  # all 20 candidates
])
```

Candidates sorted by score; those below `MIN_SCORE=0.3` discarded.

File: `rag/retriever.py` — `_get_reranker()`

### Step 6 — Response generation

Top-K chunks assembled into RAG prompt:

```
System: You are a senior Zscaler security engineer...

[Doc 1] Troubleshooting App Connectors — Tunnel Issues
Source: https://help.zscaler.com/zpa/...
<chunk text>

---
User question: ZPA tunnel down causes?
```

Sent to the chosen LLM provider. Response returned in OpenAI format.

File: `rag/generator.py` — `generate()`

---

## 4. Knowledge base pipeline

Runs once on setup; incrementally on `make update`.

```
Zscaler sitemap XML → sitemap_parser.py
    ↓ ~4,000 URLs with lastmod dates
Compare against crawl_manifest.json
    ↓ new/stale URLs (~1,825 first run, 0–50 weekly)
Crawl4AI REST API → data/raw/*.md (frontmatter: url, title, product)
    ↓ chunk_all_files()
~13,800 chunks (header split → recursive char split, 1,500 chars, 150 overlap)
    ↓ deterministic IDs: MD5(url|section|idx)
bge-m3 batch encode (~4h CPU, ~30min GPU)
    ↓ dense (13802 × 1024) + sparse (list of dicts)
Qdrant upsert (batch_size=32, timeout=120s)
    ↓ PointStruct: vector={"dense": [...], "sparse": SparseVector(...)}
crawl_manifest.json updated with chunk IDs
```

**Idempotency:** Deterministic chunk IDs mean re-ingesting overwrites rather than duplicates.

---

## 5. Log analysis mode

### Detection

`is_log_content(text)` → True if:
- ≥3 newlines, AND
- At least one timestamp pattern (ISO 8601, syslog, MM/DD/YYYY), OR
- ≥2 error keywords AND ≥1 Zscaler keyword

### Signal extraction (Drain3)

```
Input:  "2026-05-28T10:00:00Z ERROR connector=prod-dc1 reason=AUTH_FAILED"
Drain3: template = "ERROR connector=<*> reason=<*>"
        params   = ["prod-dc1", "AUTH_FAILED"]
Output: signals  = ["auth failed", "error", "connector"]
```

Signals used as Qdrant search query (better than raw log text).

### Product auto-detection

`detect_product_from_logs(text)` counts keyword hints:
- ZPA: `connector`, `broker`, `enrollment`, `zpa`
- ZIA: `pac-file`, `ssl inspection`, `z-tunnel`, `forwarding`
- ZDX: `zdx`, `experience score`, `zdx.net`

Highest count wins (must be ≥1 ahead of runner-up). Tie → None (no filter).

---

## 6. Privacy architecture

```
┌─────────────────────────────────────────────────────┐
│   Your machine                                      │
│   Browser → OpenWebUI → RAG API → Qdrant           │
│                           │                        │
│                           ├─→ Ollama ✓ (stays local)│
│                           ├─→ Groq   ✗ (query text  │
│                           │   → US servers)         │
│                           └─→ OpenRouter ✗ (same)   │
│                                                     │
│   data/raw/ ✓  qdrant_storage/ ✓  .env ✓           │
└─────────────────────────────────────────────────────┘
```

**Always local:** Zscaler docs, embeddings, manifest, API keys.
**Leaves machine (Groq/OpenRouter):** Query text + retrieved chunk text.
**Never leaves (Ollama):** Everything.

---

## 7. File map

```
Zscalerhelper/
├── api/
│   ├── main.py          # FastAPI: auth, routing, mode detection, response formatting
│   └── models.py        # Pydantic models for all request/response types
├── rag/
│   ├── retriever.py     # Qdrant hybrid search + cross-encoder reranking
│   ├── generator.py     # RAG prompt building + LLM provider call
│   └── log_parser.py    # is_log_content(), extract_log_signals(), detect_product()
├── pipeline/
│   ├── chunker.py       # Markdown → header split → recursive split → chunk dicts
│   ├── embedder.py      # bge-m3 or sentence-transformers encode
│   └── indexer.py       # Qdrant collection management + upsert
├── llm/
│   ├── base.py          # Abstract BaseLLMProvider, Message, LLMResponse
│   ├── factory.py       # get_provider(name) → BaseLLMProvider instance
│   ├── groq_provider.py
│   ├── openrouter_provider.py
│   └── ollama_provider.py
├── crawler/
│   ├── sitemap_parser.py  # Fetch sitemap.xml → list of (url, lastmod, product)
│   └── crawler.py         # Single-page Crawl4AI HTTP client + Markdown save
├── scripts/
│   ├── crawl_all.py     # Full sitemap crawl (single asyncio event loop)
│   ├── ingest.py        # chunk → embed → upsert + embedding cache support
│   ├── doctor.py        # Rich terminal health checker
│   └── validate_config.py  # Pre-flight config validator
├── config.py            # Config class: reads .env via python-dotenv
├── version.py           # __version__ = "1.0.0"
├── docker-compose.yml   # 5-service stack
├── Dockerfile           # python:3.12-slim + bge-m3 + cross-encoder baked in
└── Makefile             # 25 targets organised by category
```

---

## 8. Authentication

All `/v1/*` endpoints require `Authorization: Bearer <API_KEY>`. Public: `/health`, `/stats`, `/v1/status`.

```bash
curl http://localhost:8000/v1/models                               # 401
curl -H "Authorization: Bearer zih-api" http://localhost:8000/v1/models  # 200
```

Change by setting `API_KEY` in `.env`. Also update `OPENAI_API_KEY` in `docker-compose.yml` if using OpenWebUI.

---

## 9. Endpoints

### GET /health
```json
{"status": "ok", "qdrant_connected": true, "collection": "zscaler_docs", "chunks_indexed": 13802}
```

### GET /stats
```json
{"collection": "zscaler_docs", "vectors_count": 13802, "points_count": 13802, "status": "green"}
```

### GET /v1/status
Full system status: services reachability, knowledge base page counts, Qdrant points, and active config.

### GET /v1/models *(auth required)*
Returns all available model IDs in OpenAI format.

### POST /v1/chat/completions *(auth required)*

**Request:**
```json
{
  "model": "zih/groq-llama-3-3-70b-versatile",
  "messages": [{"role": "user", "content": "ZPA App Connector AUTH_FAILED"}],
  "temperature": 0.3,
  "max_tokens": 2048,
  "top_k": 5,
  "product_filter": "zpa"
}
```

| Field | Default | Notes |
|-------|---------|-------|
| `model` | — | Required. See [§11 Model naming](#11-model-naming) |
| `messages` | — | Required. Last user message used as query. Content can be string or vision array. |
| `temperature` | `0.3` | 0 = deterministic, 1 = creative |
| `max_tokens` | `2048` | Max response length |
| `top_k` | `5` | Number of doc chunks retrieved (1–20) |
| `product_filter` | `null` | `"zia"` \| `"zpa"` \| `"zdx"` \| `"deception"` |

**Response:** OpenAI `ChatCompletionResponse` format. `choices[0].message.content` contains Markdown with `## References` at the end.

**Mode detection:** image → `log_analysis`; timestamps + error keywords → `log_analysis`; else → `doc_search`. Force with `[log analysis]` prefix.

---

## 10. Error codes

| Status | Cause | Fix |
|--------|-------|-----|
| 401 | Missing/wrong API key | Add `Authorization: Bearer <key>` |
| 400 | No user message | Ensure a `{"role":"user"}` message exists |
| 503 | Qdrant retrieval failed | `make doctor` → check Qdrant |
| 502 | LLM generation failed | Check provider API key + connectivity |
| 422 | Request validation | Check request body schema |

---

## 11. Model naming

Pattern: `zscaler-rag/{provider}-{model-slug}` (`.`, `/`, `_` → `-`)

| Model ID | Provider | Notes |
|----------|----------|-------|
| `zih/groq-llama-3-3-70b-versatile` | Groq | Best quality, default |
| `zih/groq-llama-3-1-8b-instant` | Groq | Fastest |
| `zih/groq-mixtral-8x7b-32768` | Groq | Long context (32k) |
| `zih/openrouter-*` | OpenRouter | Requires key |
| `zih/ollama-llama3-2` | Ollama | Local text |
| `zih/ollama-llama3-2-vision` | Ollama | Local vision |
| `zih/ollama-llava` | Ollama | Local vision |
| `zih/ollama-qwen2-vl-7b` | Ollama | Best vision (DocVQA 93.1) |

Use `GET /v1/models` for the live authoritative list.

---

## 12. Vision / image content

Pass images as OpenAI vision content blocks. **Ollama vision models only.**

```python
import base64
from pathlib import Path
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="zscaler-rag")
b64 = base64.b64encode(Path("screenshot.png").read_bytes()).decode()

response = client.chat.completions.create(
    model="zih/ollama-qwen2-vl-7b",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "What error is shown in this screenshot?"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
        ]
    }]
)
```

Privacy: Ollama processes images locally — nothing leaves your machine.

---

## 13. Local setup

```bash
git clone https://github.com/manavendrayadav/zscaler-incident-helper.git
cd zscaler-incident-helper

python -m venv .venv
source .venv/bin/activate        # Linux/Mac
# .venv\Scripts\activate         # Windows

pip install -e ".[dev]"          # runtime + pytest, ruff, mypy, pre-commit
cp .env.example .env             # set GROQ_API_KEY at minimum
pre-commit install                # install git hooks
make up                          # start Docker stack
make validate-config             # verify connections
```

---

## 14. Running tests

```bash
make test-fast        # unit tests only (~10s, no Docker)
make test             # full suite
make test-integration # requires running stack
pytest tests/unit/ --cov=. --cov-report=html   # with coverage
```

---

## 15. Code quality

```bash
make lint        # ruff check .
make format      # ruff format .
make typecheck   # mypy . --ignore-missing-imports
make ci          # lint + typecheck + test-fast  ← run before every PR
```

---

## 16. Test suite guide

```
tests/
├── conftest.py          # Shared fixtures: mock embedder, Qdrant, LLM
├── fixtures/sample_logs.txt
└── unit/
    ├── test_api_auth.py    # Auth bypass fix; 401 on empty header
    ├── test_chunker.py     # Frontmatter, deterministic chunk IDs
    ├── test_config.py      # Env var loading, type coercion
    ├── test_factory.py     # Provider routing; deepseek must not exist
    └── test_log_parser.py  # is_log_content, extract_signals, detect_product
```

**Mocking strategy** — unit tests never load heavy models:

| Mocked | Fixture | Reason |
|--------|---------|--------|
| `pipeline.embedder.embed_query` | `mock_embed_query_hybrid` | bge-m3 takes 30s |
| `qdrant_client.QdrantClient` | `mock_qdrant_client` | No Docker needed |
| `rag.generator.generate` | `mock_generate` | No LLM API call |

**Writing a new test:**

```python
class TestMyFunction:
    def test_normal_case(self):
        result = my_function("valid input")
        assert result == "expected output"

    def test_raises_on_invalid(self):
        with pytest.raises(ValueError, match="expected error message"):
            my_function(None)
```

**Common gotchas:**

| Problem | Fix |
|---------|-----|
| `import config` fails | Add `sys.path.insert(0, str(Path(__file__).parent.parent))` |
| `QdrantClient` patch fails | Patch at `qdrant_client.QdrantClient` — it's lazily imported inside functions |
| bge-m3 loads during unit tests | Use `mock_embed_query_hybrid` fixture from conftest |

---

## 17. VS Code setup

Add `.vscode/launch.json`:

```json
{
  "configurations": [
    {
      "name": "Run RAG API (local)",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": ["api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
      "env": {"QDRANT_HOST": "localhost", "QDRANT_PORT": "6333"}
    },
    {
      "name": "Run pytest",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": ["tests/unit/", "-v"]
    }
  ]
}
```

Recommended extensions: `ms-python.python`, `ms-python.ruff`, `ms-python.mypy-type-checker`, `ms-azuretools.vscode-docker`

---

## 18. Pre-PR checklist

1. **Write tests** for new functionality
2. **`make ci`** must pass (lint + typecheck + unit tests)
3. **Update `docs/OPERATIONS.md`** if operational procedure changed
4. **Update `CHANGELOG.md`** under `[Unreleased]`
5. **Update `.env.example`** if new config variables added
6. **Test Docker build** if `Dockerfile` or `requirements.txt` changed:
   ```bash
   docker compose build rag-api && make doctor
   ```

---

## 19. Architecture Decision Records

Key decisions that should not be unknowingly reversed.

---

### ADR-001: Use BAAI/bge-m3 as Default Embedding Model

**Status:** Accepted — 2026-05-28

**Decision:** Use `BAAI/bge-m3` (MTEB 64.3, 1024-dim, dense+sparse).

**Why:** bge-m3 uniquely supports dense + sparse vectors in a single model pass. This is critical for queries containing exact error codes (`AUTH_FAILED`, `TUNNEL_DOWN`) where dense-only search misses keyword matches. MTEB 64.3 vs. 56.3 for MiniLM is a significant margin for technical queries.

**Trade-offs:** 4-hour initial ingest on CPU (vs. 30 min for MiniLM). Mitigated by: embedding cache (`--skip-embed`), one-time cost, GPU cuts to ~30 min.

**To swap:** Change `EMBEDDING_MODEL` and `EMBEDDING_DIM` in `.env`, then `make reset-db && make ingest`.

| Alternative | MTEB | Hybrid? | Rejected because |
|-------------|------|---------|-----------------|
| all-MiniLM-L6-v2 | 56.3 | No | Misses exact error codes |
| text-embedding-ada-002 | 60.5 | No | Sends all docs to OpenAI API |
| bge-large-en-v1.5 | 63.2 | No | No sparse support |

---

### ADR-002: Single-Process uvicorn (No `--workers`)

**Status:** Accepted — 2026-05-29

**Decision:** Remove `--workers` flag from uvicorn CMD. Run single-process.

**Why:** bge-m3 uses PyTorch. `uvicorn --workers N` forks a subprocess. PyTorch's internal thread pools are not fork-safe — the child process has corrupted state, causing a silent SIGBUS crash on the first embedding request. The process exits with code 0 (no Python traceback), making the bug very hard to diagnose.

**Trade-offs:** Single-process handles requests sequentially. For the expected usage (team of ~10 engineers, non-simultaneous queries), this is acceptable. For high concurrency: run multiple Docker containers behind a load balancer — never add `--workers`.

---

### ADR-003: OpenAI-Compatible API

**Status:** Accepted — 2026-05-15

**Decision:** Implement `POST /v1/chat/completions` matching the OpenAI API schema. Connect OpenWebUI as the chat frontend.

**Why:** Any tool built for OpenAI (OpenWebUI, LangChain, openai SDK) works immediately without modification. Eliminates the need to build or maintain a frontend. PR checklist, model discovery (`/v1/models`), and streaming support are all standard.

**Trade-offs:** RAG-specific params (`top_k`, `product_filter`) must be passed as non-standard fields. Future API changes must maintain OpenAI compatibility.

---

### ADR-004: Deterministic Chunk IDs

**Status:** Accepted — 2026-05-15

**Decision:** Chunk ID = `str(uuid.UUID(hashlib.md5(f"{url}|{section}|{idx}".encode()).hexdigest()))`

**Why:** Same input always produces the same ID, making `make ingest` idempotent. Re-ingesting a page upserts (overwrites) rather than duplicates. No "delete old chunks" step needed before updating a page.

**Trade-offs:** Orphaned chunks if a page is renamed or deleted (cleaned up by `make reset-db && make ingest`).

---

### ADR-005: Remove DeepSeek Provider

**Status:** Accepted — 2026-05-28

**Decision:** Delete `llm/deepseek_provider.py`. Remove from factory, models, `.env.example`.

**Why:** DeepSeek's API infrastructure is operated by a Chinese company with servers in China. This project may process internal corporate security incident data. Chinese data regulations (Data Security Law 2021) grant authorities broad data access rights. Unacceptable for a tool handling sensitive incident logs.

**Do not re-add DeepSeek** or any provider whose API routes through jurisdictions with similar data access laws.

Remaining providers: Groq (US, SOC 2), OpenRouter (US), Ollama (local-only).

---

## 20. Roadmap

Community input welcome — open a [GitHub Discussion](https://github.com/manavendrayadav/zscaler-incident-helper/discussions).

| Version | Target | Key features |
|---------|--------|-------------|
| **v1.0.0** | ✅ Released | bge-m3 hybrid, cross-encoder, log analysis, vision, Groq+OpenRouter+Ollama, 69 unit tests, CI/CD |
| **v1.1.0** | Q3 2026 | Integration tests, API rate limiting, structured logging, Qdrant backup, Prometheus metrics |
| **v1.2.0** | Q4 2026 | chonkie SDPM chunking (blocked on Python 3.14 compat), contextual compression, streaming responses |
| **v2.0.0** | 2027 | Multi-tenant collections, custom URL config, admin REST API, horizontal scaling |

**Not planned:** ITSM integration, real-time Zscaler API access, GPT-4/Claude/Gemini providers, DeepSeek.
