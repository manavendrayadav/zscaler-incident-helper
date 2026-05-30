# Architecture Overview

How the Zscaler RAG Incident Helper works internally. No ML background assumed.

---

## Table of Contents

1. [30-second overview](#1-30-second-overview)
2. [System components](#2-system-components)
3. [Query pipeline — step by step](#3-query-pipeline--step-by-step)
4. [Knowledge base pipeline](#4-knowledge-base-pipeline)
5. [Log analysis mode](#5-log-analysis-mode)
6. [Privacy architecture](#6-privacy-architecture)
7. [Key design decisions](#7-key-design-decisions)
8. [File map](#8-file-map)

---

## 1. 30-second overview

The system is a **Retrieval-Augmented Generation (RAG)** pipeline: instead of asking an AI to answer from its training data, it first retrieves the most relevant Zscaler documentation pages, then asks the AI to generate an answer grounded in those pages.

```
User query
    │
    ▼
OpenWebUI (chat UI)
    │  POST /v1/chat/completions
    ▼
RAG API (FastAPI)
    │
    ├── embed_query()    ── bge-m3 model → 1024-dim vector
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
| **OpenWebUI** | `zscaler-openwebui` | 3000 | Chat interface. Multi-user, conversation history, model switching. No code changes needed — it treats the RAG API as an OpenAI-compatible backend. |
| **RAG API** | `zscaler-rag-api` | 8000 | The core service. FastAPI application. Handles query routing, embedding, retrieval, generation, and OpenAI-format response formatting. |
| **Qdrant** | `zscaler-qdrant` | 6333 | Vector database. Stores ~13,800 chunk embeddings with metadata. Responds to dense search, sparse search, and hybrid search queries. |
| **Crawl4AI** | `zscaler-crawl4ai` | 11235 | Headless browser crawler service. Accepts URLs via HTTP, returns cleaned Markdown content using Playwright. Used only during knowledge base setup. |
| **Ollama** (optional) | `zscaler-ollama` | 11434 | Local LLM runtime. Runs text and vision models on your machine. Required for private/offline mode. Started separately via `make ollama-setup`. |

### Startup dependency chain

```
Qdrant starts first (healthcheck: TCP 6333 responds)
    ↓ healthy
RAG API starts (bge-m3 and cross-encoder load from baked image layers, ~20s)
    ↓ healthy
OpenWebUI starts (connects to RAG API at http://rag-api:8000/v1)
```

Crawl4AI starts independently (only needed for crawl operations, not for queries).

---

## 3. Query pipeline — step by step

This is what happens when a user sends a message in OpenWebUI.

### Step 1 — HTTP request arrives

```
POST /v1/chat/completions
Authorization: Bearer zscaler-rag
{
  "model": "zscaler-rag/groq-llama-3-3-70b-versatile",
  "messages": [{"role": "user", "content": "ZPA tunnel down causes?"}]
}
```

File: `api/main.py` — `chat_completions()` function

### Step 2 — Mode detection

The API examines the last user message:
- **Has image attachments?** → `log_analysis` mode (vision)
- **Text looks like a log?** (timestamps + error keywords) → `log_analysis` mode
- **Otherwise** → `doc_search` mode

File: `api/main.py`, `rag/log_parser.py` — `is_log_content()`, `detect_product_from_logs()`

### Step 3 — Query embedding

The query text is passed to `embed_query()`. The bge-m3 model generates:
- A **dense vector**: list of 1,024 floats representing semantic meaning
- A **sparse vector**: dict of `{token_id: weight}` pairs for keyword matching

```python
# Simplified
query_embedding = {
    "dense": [0.021, -0.154, ..., 0.033],  # 1024 numbers
    "sparse": {"531": 0.8, "1024": 0.5}    # token → weight
}
```

File: `pipeline/embedder.py` — `embed_query()`

### Step 4 — Qdrant hybrid search

The retriever sends both dense and sparse vectors to Qdrant in a single `query_points()` call with `Prefetch` + `FusionQuery(RRF)`:

1. Dense search: "find the 20 chunks most similar in meaning"
2. Sparse search: "find the 20 chunks with the most matching keywords"
3. RRF fusion: merge both ranked lists into a single unified ranking

Returns up to 20 candidate chunks with their scores and metadata (URL, product, section, text).

File: `rag/retriever.py` — `_search_hybrid()`

### Step 5 — Cross-encoder re-ranking

Each of the 20 candidates is scored by the cross-encoder model as a (query, chunk) pair. This is more accurate than vector similarity alone but requires processing each pair individually.

```python
scores = cross_encoder.predict([
    ("ZPA tunnel down causes?", chunk_1_text),
    ("ZPA tunnel down causes?", chunk_2_text),
    ...  # all 20 candidates
])
```

Candidates are sorted by cross-encoder score. Those below `MIN_SCORE=0.3` are discarded.

File: `rag/retriever.py` — `_get_reranker()`

### Step 6 — Response generation

The top-K chunks (default 5) are formatted as context and combined with the user query into a RAG prompt:

```
System: You are a senior Zscaler security engineer...

Context (most relevant documentation):
[Doc 1] Troubleshooting App Connectors — Tunnel Issues
Source: https://help.zscaler.com/zpa/troubleshooting-app-connectors
...text of chunk 1...

---

[Doc 2] ...

---

User question: ZPA tunnel down causes?
```

The prompt is sent to the chosen LLM provider (Groq, OpenRouter, or Ollama). The response is returned in OpenAI format.

File: `rag/generator.py` — `generate()`

### Step 7 — Response formatting

The answer is returned as an OpenAI-format `ChatCompletionResponse`. A "References" footer listing source URLs is appended to the answer text.

---

## 4. Knowledge base pipeline

This runs once during initial setup and weekly for updates. It is completely separate from the query pipeline.

```
Zscaler sitemap XML (https://help.zscaler.com/sitemap.xml)
    │ parsed by sitemap_parser.py
    ▼
List of ~4,000 URLs with lastmod dates
    │ compared against crawl_manifest.json
    ▼
New / stale URLs (~1,825 on first run, 0-50 on weekly update)
    │ crawled by crawl_all.py → Crawl4AI REST API
    ▼
data/raw/*.md  (Markdown with YAML frontmatter: url, title, product)
    │ loaded by chunk_all_files()
    ▼
~13,800 chunks  (header split → recursive character split, 1,500 chars, 150 overlap)
    │ deterministic IDs: MD5(url|section|idx)
    ▼
bge-m3 batch encode  (~4h on CPU, ~30min on GPU)
    │ returns dense (13802 × 1024) + sparse (list of dicts)
    ▼
Qdrant upsert  (batch_size=32, timeout=120s)
    │ PointStruct: vector={"dense": [...], "sparse": SparseVector(...)}
    ▼
crawl_manifest.json updated with chunk IDs
```

**Key property — idempotency:** Because chunk IDs are deterministic (`MD5(url|section|idx)`), running `make ingest` multiple times on the same files produces exactly the same Qdrant points. Re-ingesting a page overwrites (upserts) rather than duplicates its points.

---

## 5. Log analysis mode

When a user pastes raw log text (or attaches an image), the system switches to log-analysis mode.

### Detection

`is_log_content(text)` returns `True` if:
- The text has ≥3 newlines, AND
- Contains at least one timestamp pattern (ISO 8601, syslog, MM/DD/YYYY), OR
- Contains ≥2 error keywords (`ERROR`, `FAILED`, `TIMEOUT`, etc.) AND ≥1 Zscaler keyword

### Signal extraction

Instead of embedding the raw log text as the query, Drain3 extracts structured signals:

```
Input:  "2026-05-28T10:00:00Z ERROR connector=prod-dc1 reason=AUTH_FAILED"
Drain3: template = "ERROR connector=<*> reason=<*>"
        params   = ["prod-dc1", "AUTH_FAILED"]
Output: signals = ["auth failed", "error", "connector"]
```

These signals produce better Qdrant retrieval than the raw log text.

### Product auto-detection

`detect_product_from_logs(text)` counts keyword hits:
- ZPA hints: `connector`, `broker`, `enrollment`, `zpa`, ...
- ZIA hints: `pac-file`, `ssl inspection`, `z-tunnel`, `forwarding`, ...
- ZDX hints: `zdx`, `experience score`, `zdx.net`

The product with the most hits (by at least 1 point) wins. If tied: returns `None` (no filter).

### Response prompt

Log-analysis mode uses `LOG_ANALYSIS_SYSTEM_PROMPT` instead of the standard `SYSTEM_PROMPT`. This prompt instructs the LLM to structure its response as: Identified Events → Root Cause → Resolution → Verification.

---

## 6. Privacy architecture

The following diagram shows which data flows touch external services:

```
┌─────────────────────────────────────────────────────┐
│   Your machine                                      │
│                                                     │
│   Browser → OpenWebUI → RAG API → Qdrant           │
│                           │                        │
│                           ├─→ Ollama ✓ (stays local)│
│                           │                        │
│                           ├─→ Groq API ✗ (query text│
│                           │   leaves to US servers) │
│                           │                        │
│                           └─→ OpenRouter ✗ (same)   │
│                                                     │
│   data/raw/ ✓              Stays local              │
│   qdrant_storage/ ✓        Stays local              │
│   .env ✓                   Stays local (gitignored) │
└─────────────────────────────────────────────────────┘
```

**What always stays local:**
- Zscaler documentation (crawled Markdown, `data/raw/`)
- Vector embeddings (Qdrant volume)
- Crawl manifest (page metadata)
- Your API keys (`.env` file)

**What leaves your machine when using Groq/OpenRouter:**
- The query text from the user message
- The retrieved chunk text (included in the prompt)

**What never leaves your machine when using Ollama:**
- Everything — 100% local inference

---

## 7. Key design decisions

### Single-process uvicorn (no `--workers`)

bge-m3 uses PyTorch internally. uvicorn's `--workers N` flag spawns worker subprocesses by forking the master process. PyTorch's internal thread pools are not fork-safe — after forking, the child process has corrupted thread state, causing silent crashes when the first embedding request arrives.

Running in single-process mode (no `--workers`) avoids the fork entirely. The single process handles all requests sequentially, which is sufficient for the expected load profile (batch queries, not high concurrency).

*See: `ADR-002-single-process-uvicorn.md`*

### bge-m3 over all-MiniLM-L6-v2

bge-m3 (MTEB 64.3) significantly outperforms MiniLM (MTEB 56.3) on retrieval benchmarks, especially for queries containing specific error codes, product names, and CLI commands — the core use case for this project. The 4-hour initial embedding cost is acceptable as a one-time setup cost.

*See: `ADR-001-embedding-model.md`*

### OpenAI-compatible API

Building the RAG API to the OpenAI chat completions format means any tool built for OpenAI (OpenWebUI, LangChain, openai Python SDK) works immediately without modification. This eliminates the need to build or maintain a frontend.

*See: `ADR-003-openai-compatible-api.md`*

### Deterministic chunk IDs

Using `MD5(url|section|chunk_index)` as the chunk ID makes the ingest pipeline idempotent — re-ingesting a page overwrites rather than duplicates. This eliminates the need for a "delete old chunks" step before re-ingesting and makes weekly incremental updates safe.

*See: `ADR-004-deterministic-chunk-ids.md`*

### DeepSeek removed

DeepSeek's API routes traffic through servers located in China, making it unsuitable for a tool that may process internal corporate incident data. All remaining providers (Groq, OpenRouter, Ollama) are US-based or local-only.

*See: `ADR-005-no-deepseek.md`*

---

## 8. File map

```
Zscalerhelper/
│
├── api/
│   ├── main.py          # FastAPI app: auth, routing, mode detection, response formatting
│   └── models.py        # Pydantic models for all request/response types
│
├── rag/
│   ├── retriever.py     # Qdrant hybrid search + cross-encoder reranking
│   ├── generator.py     # RAG prompt building + LLM provider call
│   └── log_parser.py    # is_log_content(), extract_log_signals(), detect_product()
│
├── pipeline/
│   ├── chunker.py       # Markdown → header split → recursive split → chunk dicts
│   ├── embedder.py      # bge-m3 or sentence-transformers encode
│   └── indexer.py       # Qdrant collection management + upsert
│
├── llm/
│   ├── base.py          # Abstract BaseLLMProvider, Message, LLMResponse
│   ├── factory.py       # get_provider(name) → BaseLLMProvider instance
│   ├── groq_provider.py     # Groq API (llama, mixtral, gemma)
│   ├── openrouter_provider.py  # OpenRouter aggregator API
│   └── ollama_provider.py  # Local Ollama runtime + vision models
│
├── crawler/
│   ├── sitemap_parser.py  # Fetch sitemap.xml → list of (url, lastmod, product)
│   └── crawler.py         # Single-page Crawl4AI HTTP client + Markdown save
│
├── scripts/
│   ├── crawl_all.py     # Full sitemap crawl with single asyncio event loop
│   ├── ingest.py        # Full pipeline: chunk → embed → upsert + cache support
│   ├── doctor.py        # Rich terminal health checker
│   └── validate_config.py  # Pre-flight config validator
│
├── config.py            # Config class: reads .env via python-dotenv
├── version.py           # __version__ = "1.0.0"
├── docker-compose.yml   # 5-service stack
├── Dockerfile           # python:3.12-slim + bge-m3 + cross-encoder baked in
└── Makefile             # 25 targets organised by category
```
