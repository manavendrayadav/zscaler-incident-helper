# Configuration Guide

Every configuration option explained: what it controls, when to change it, and what happens at the extremes.

All configuration is via the `.env` file in the project root. Copy `.env.example` to `.env` before editing.

```bash
cp .env.example .env
make validate-config   # verify your settings before running
```

---

## Table of Contents

1. [LLM Provider Keys](#1-llm-provider-keys)
2. [Default Provider & Model](#2-default-provider--model)
3. [Qdrant Connection](#3-qdrant-connection)
4. [Embedding Parameters](#4-embedding-parameters)
5. [RAG Tuning](#5-rag-tuning)
6. [Crawl4AI](#6-crawl4ai)
7. [API Security](#7-api-security)
8. [Scenario Presets](#8-scenario-presets)
9. [Validation](#9-validation)

---

## 1. LLM Provider Keys

### `GROQ_API_KEY`

```ini
GROQ_API_KEY=gsk_...
```

**What it does:** Authenticates requests to Groq's inference API.  
**Where to get it:** https://console.groq.com → API Keys → Create API Key  
**Free tier:** Yes — generous limits for typical team use (~14,400 requests/day)  
**Data privacy:** Your query text is sent to Groq's US-based servers. Never set this for queries containing internal logs or sensitive data.  
**If not set:** Groq provider is unavailable. Set `DEFAULT_PROVIDER=ollama` if using Ollama only.

---

### `OPENROUTER_API_KEY`

```ini
OPENROUTER_API_KEY=sk-or-...
```

**What it does:** Authenticates requests to OpenRouter, which routes to many LLM providers.  
**Where to get it:** https://openrouter.ai → Keys  
**Free tier:** Some models are free; others are pay-per-use.  
**Data privacy:** Query text goes to OpenRouter (US), then to the underlying model provider. Avoid for sensitive data.  
**If not set:** OpenRouter provider is unavailable (warning only — not a failure).

---

### `OLLAMA_BASE_URL`

```ini
OLLAMA_BASE_URL=http://localhost:11434    # when running outside Docker
# or
OLLAMA_BASE_URL=http://ollama:11434       # when running inside Docker stack
```

**What it does:** The URL where Ollama is listening.  
**Default:** `http://localhost:11434`  
**Change when:**
- Running Ollama inside Docker (use `http://ollama:11434`)
- Ollama is on a different machine (use the remote IP)

**Data privacy:** All inference is local. Nothing leaves your machine. Required for internal log analysis and screenshot queries.  
**If not set or unreachable:** Ollama provider is unavailable (warning, not failure — if other providers are configured).

---

## 2. Default Provider & Model

### `DEFAULT_PROVIDER`

```ini
DEFAULT_PROVIDER=groq   # groq | openrouter | ollama
```

**What it does:** The provider used when a model is not explicitly selected in OpenWebUI.  
**Change when:** You want Ollama as the default for privacy reasons.

### `DEFAULT_MODEL`

```ini
DEFAULT_MODEL=llama-3.3-70b-versatile
```

**What it does:** The model name passed to the default provider.  
**Must match:** A model that the chosen `DEFAULT_PROVIDER` supports.

| Provider | Recommended default model |
|----------|--------------------------|
| groq | `llama-3.3-70b-versatile` |
| openrouter | `meta-llama/llama-3.3-70b-instruct` |
| ollama | `llama3.2` |

---

## 3. Qdrant Connection

### `QDRANT_HOST`

```ini
QDRANT_HOST=localhost     # when running scripts on host machine
# or
QDRANT_HOST=qdrant        # when inside Docker (Docker DNS resolves service names)
```

**Change when:** The Docker stack sets `QDRANT_HOST=qdrant` automatically via `docker-compose.yml`.

### `QDRANT_PORT`

```ini
QDRANT_PORT=6333
```

**Default:** 6333 (HTTP). Do not change unless you remapped the port in `docker-compose.yml`.

### `COLLECTION_NAME`

```ini
COLLECTION_NAME=zscaler_docs
```

**Change when:** You want multiple knowledge bases (e.g., `zscaler_docs_test` for testing). Each collection is independent.

---

## 4. Embedding Parameters

These parameters have the **highest impact on retrieval quality and performance**. Changing them requires rebuilding the Qdrant collection (`make reset-db && make ingest`).

### `EMBEDDING_MODEL`

```ini
EMBEDDING_MODEL=BAAI/bge-m3   # default: best quality
```

**What it does:** The model that converts text to vector embeddings. Affects search quality for the entire knowledge base.

| Model | MTEB Score | RAM | Embedding time | Best for |
|-------|-----------|-----|----------------|---------|
| `BAAI/bge-m3` | 64.3 | ~2.5 GB | ~4 hours (CPU) | Best quality; supports hybrid search |
| `all-MiniLM-L6-v2` | 56.3 | ~0.5 GB | ~30 min (CPU) | Fast setup; lower accuracy for error codes |

**After changing:** Run `make validate-config` to confirm `EMBEDDING_DIM` matches, then `make reset-db && make ingest`.

---

### `EMBEDDING_DIM`

```ini
EMBEDDING_DIM=1024   # for BAAI/bge-m3
# or
EMBEDDING_DIM=384    # for all-MiniLM-L6-v2
```

**Critical:** This MUST match the actual output dimension of `EMBEDDING_MODEL`. Mismatch causes Qdrant upsert to fail.  
`make validate-config` checks this automatically.

| Model | Correct EMBEDDING_DIM |
|-------|----------------------|
| `BAAI/bge-m3` | 1024 |
| `all-MiniLM-L6-v2` | 384 |
| `all-mpnet-base-v2` | 768 |

---

### `SPARSE_ENABLED`

```ini
SPARSE_ENABLED=true   # default: hybrid dense+sparse search
```

**What it does:** Enables bge-m3's sparse vector output for hybrid search (dense + sparse + RRF fusion).

| Setting | Effect |
|---------|--------|
| `true` | Best recall for error codes, Zscaler-specific terms, and exact keyword matches |
| `false` | Dense-only search; faster but misses exact error code matches |

**When to disable:** Rarely. Only if you need faster query latency and can accept lower precision for keyword-heavy queries. Requires `EMBEDDING_MODEL=BAAI/bge-m3` to have any effect.

---

## 5. RAG Tuning

These parameters affect retrieval quality and response latency. Can be changed without rebuilding the knowledge base.

### `TOP_K`

```ini
TOP_K=5   # default: 5 chunks sent to LLM
```

**What it does:** Number of document chunks included in the LLM's context after retrieval and re-ranking.

| Value | Effect | Tradeoff |
|-------|--------|---------|
| 3 | Fast, focused | May miss relevant context |
| 5 | Balanced (default) | Good for most queries |
| 8 | Thorough | Slower; risk of noisy context |
| 15+ | Maximum context | Very slow; LLM may get confused by tangential information |

**When to increase:** Complex multi-step troubleshooting where context from multiple doc sections is needed.  
**When to decrease:** Simple factual queries; improving response speed.

---

### `CHUNK_SIZE`

```ini
CHUNK_SIZE=1500   # characters per chunk (~500 tokens)
```

**What it does:** Maximum character length of each document chunk. Smaller chunks = more precise retrieval, less context per chunk.

| Value | Effect |
|-------|--------|
| 500 | Very granular — good precision, but may miss context |
| 1500 | Default — good balance for paragraph-length content |
| 3000 | Large chunks — more context per chunk, but less precise retrieval |

**Changing this requires** a full re-ingest (`make reset-db && make ingest`).

---

### `CHUNK_OVERLAP`

```ini
CHUNK_OVERLAP=150   # characters of overlap between consecutive chunks
```

**What it does:** How many characters at the end of one chunk are repeated at the start of the next. Prevents important sentences from being split between chunks.

**Rule of thumb:** 10% of `CHUNK_SIZE`. With `CHUNK_SIZE=1500`, use `CHUNK_OVERLAP=150`.

---

### `MIN_SCORE`

```ini
MIN_SCORE=0.3   # minimum relevance score (0-1) to include a chunk
```

**What it does:** After re-ranking, chunks with a cross-encoder score below this threshold are discarded before being sent to the LLM.

| Value | Effect |
|-------|--------|
| 0.1 | Very permissive — includes tangentially relevant chunks |
| 0.3 | Default — good balance |
| 0.5 | Strict — only highly relevant chunks included |
| 0.7 | Very strict — may return no results for rare topics |

**When to lower:** If you frequently get "I don't have information about that" responses.  
**When to raise:** If responses include off-topic information.

After changing: restart the API (`docker compose restart rag-api`).

---

## 6. Crawl4AI

### `CRAWL4AI_BASE_URL`

```ini
CRAWL4AI_BASE_URL=http://localhost:11235   # running on host
# or
CRAWL4AI_BASE_URL=http://crawl4ai:11235    # inside Docker (set automatically)
```

This is set automatically by `docker-compose.yml`. Only change if you've remapped the Crawl4AI port.

---

## 7. API Security

### `API_KEY`

```ini
API_KEY=zscaler-rag   # default — change before team deployment
```

**What it does:** The Bearer token required to authenticate all `/v1/*` API calls.  
**Security warning:** The default `zscaler-rag` is public knowledge. **Change this** before sharing the URL with a team.

```bash
# Generate a random key (Linux/Mac)
openssl rand -hex 32

# Then set in .env:
API_KEY=your_generated_key_here

# Also update docker-compose.yml (OpenWebUI needs the same key):
# OPENAI_API_KEY=your_generated_key_here
```

After changing, restart the rag-api: `docker compose restart rag-api`

---

### `ALLOWED_ORIGINS`

```ini
ALLOWED_ORIGINS=http://localhost:3000   # default: localhost only
```

**What it does:** Controls which browser origins can make CORS requests to the RAG API. Prevents cross-site request forgery from other websites.

```ini
# Single origin (default)
ALLOWED_ORIGINS=http://localhost:3000

# Multiple origins (comma-separated)
ALLOWED_ORIGINS=http://localhost:3000,https://openwebui.mycompany.com

# Never use wildcard in production:
ALLOWED_ORIGINS=*   # ← DANGEROUS — any website can call your API
```

`make validate-config` fails if `ALLOWED_ORIGINS=*`.

---

## 8. Scenario Presets

### Fast startup, lower quality (developer testing)

```ini
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIM=384
SPARSE_ENABLED=false
TOP_K=3
MIN_SCORE=0.2
```
Trade-off: Ingest takes ~30 min vs. 4 hours. Retrieval quality is lower for exact error codes.

### Maximum quality (production, with GPU)

```ini
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIM=1024
SPARSE_ENABLED=true
TOP_K=8
MIN_SCORE=0.3
```
Requires GPU for reasonable Ollama response times.

### Privacy-first (Ollama only, no cloud)

```ini
GROQ_API_KEY=                                 # leave empty
OPENROUTER_API_KEY=                           # leave empty
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_PROVIDER=ollama
DEFAULT_MODEL=llama3.2
```
Run `make ollama-setup` first.

### Low-memory machine (8 GB RAM)

```ini
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIM=384
SPARSE_ENABLED=false
TOP_K=5
```
Reduces rag-api RAM from ~2.5 GB (bge-m3) to ~0.5 GB (MiniLM).

---

## 9. Validation

Always run after changing `.env`:

```bash
make validate-config
```

What it checks:

| Check | PASS condition | FAIL action required |
|-------|---------------|---------------------|
| `GROQ_API_KEY` | Authenticated (HTTP 200 from Groq) | Update key at console.groq.com |
| `OLLAMA_BASE_URL` | Ollama responds to `/api/tags` | Check if Ollama container is running |
| Qdrant connectivity | HTTP 200 from `:6333/health` | Check if Qdrant container is running |
| Embedding dimension | `EMBEDDING_DIM` == actual model output dim | Update `EMBEDDING_DIM` to match model |
| `API_KEY` | Not default `"zscaler-rag"` | Change before team deployment (WARN, not FAIL) |
| `ALLOWED_ORIGINS` | Does not contain `"*"` | Restrict to specific origins (FAIL if wildcard) |
