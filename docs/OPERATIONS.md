# Zscaler RAG — Operations Manual

> **Single-document SOP** for installing, operating, and using the Zscaler RAG Incident Helper.
> When a procedure changes, update this file in the same commit as the code change.
> Commit prefix: `docs:` (e.g. `docs: add GPU setup step to §6 Ollama`).

---

## Table of Contents

1. [Quick Reference](#1-quick-reference)
2. [Initial Setup](#2-initial-setup)
3. [Daily Operations](#3-daily-operations)
4. [Knowledge Base Management](#4-knowledge-base-management)
5. [Incident Investigation Guide](#5-incident-investigation-guide)
6. [LLM Provider Configuration](#6-llm-provider-configuration)
7. [Troubleshooting](#7-troubleshooting)
8. [Configuration Reference](#8-configuration-reference)
9. [Hardware Requirements](#9-hardware-requirements)

---

## 1. Quick Reference

### Stack ports

| Service | URL | Role |
|---------|-----|------|
| OpenWebUI | http://localhost:3000 | Chat interface |
| RAG API | http://localhost:8000 | OpenAI-compatible query endpoint |
| Qdrant | http://localhost:6333 | Vector database |
| Crawl4AI | http://localhost:11235 | Headless browser crawler |
| Ollama | http://localhost:11434 | Optional local LLM |

### Common commands

> **Windows users:** run these in Git Bash, WSL2, or PowerShell after `choco install make`.
> See [§2 Initial Setup — `make` platform setup](#make--platform-setup) for details.

```bash
make up               # Start everything
make down             # Stop everything
make doctor           # Health check (run first when something looks wrong)
make validate-config  # Pre-flight check before crawl/ingest
make update           # Crawl only new/changed Zscaler pages
make ingest           # Re-embed and re-index into Qdrant
make logs             # Tail rag-api logs
make help             # Show all available targets
```

### Update policy

When to update this document:
- A `make` target is added, renamed, or removed → update §3 and §4
- A new LLM provider or model is added → update §6
- A new error pattern is found and fixed → add to §7
- A config variable is added/changed → update the relevant section and `.env.example`
- A privacy decision is made → update §5 and §6

---

## 2. Initial Setup

**Audience:** New team member setting up the system for the first time.
**Time required:** 15 minutes hands-on, ~4 hours background (bge-m3 embedding on CPU).

**Prerequisites:**

| Requirement | Version | Notes |
|-------------|---------|-------|
| Docker Desktop | Latest | Required for all services |
| Git | Any | |
| Python | 3.11+ | For running scripts on the host |
| `make` | Any | **See platform notes below** |

### `make` — platform setup

All project commands use `make` (e.g. `make up`, `make doctor`). It works out of the box on Linux and macOS but needs one extra step on Windows.

**Linux / macOS**
`make` is pre-installed. No action needed.

**Windows (PowerShell) — choose one option:**

| Option | Command | Notes |
|--------|---------|-------|
| **Chocolatey** (recommended) | `choco install make` | Install Chocolatey first: https://chocolatey.org/install |
| **Scoop** | `scoop install make` | Install Scoop first: https://scoop.sh |
| **Git Bash** | *(no install needed)* | Open Git Bash instead of PowerShell — `make` is bundled with Git for Windows |
| **WSL2** | *(no install needed)* | Run commands inside the WSL2 shell (`wsl`) — `make` is built into every Linux distro |

> **Quickest option if you have Git installed:** right-click the project folder → "Git Bash Here" and run all commands from there.

**If you cannot install `make`**, every target has a direct equivalent:

| `make` command | Direct command |
|----------------|----------------|
| `make up` | `docker compose up -d qdrant` then `docker compose up -d` |
| `make down` | `docker compose down` |
| `make doctor` | `python scripts/doctor.py` |
| `make logs` | `docker compose logs -f rag-api` |
| `make ingest` | `python scripts/ingest.py` |
| `make update` | `python scripts/test_crawl.py --update` |
| `make validate-config` | `python scripts/validate_config.py` |
| `make test-fast` | `pytest tests/unit/ -v` |
| `make lint` | `ruff check .` |

---

### 2.1 Clone and configure

```bash
git clone <repo-url> Zscalerhelper
cd Zscalerhelper
cp .env.example .env
```

Edit `.env` and fill in the keys you will use:

```ini
# Minimum: one LLM provider
GROQ_API_KEY=gsk_...           # free tier, fast — recommended for text queries
OPENROUTER_API_KEY=sk-or-...   # optional, wider model selection

# Leave OLLAMA_BASE_URL as default if you plan to use Ollama locally
OLLAMA_BASE_URL=http://localhost:11434
```

Leave all other values at their defaults for first-time setup.

### 2.2 Validate the configuration

```bash
make validate-config
```

Expected: all PASS or WARN (warnings are advisory). No FAIL lines.

If Qdrant FAIL appears: Docker is not running. Start Docker Desktop first.

### 2.3 Start the Docker stack

```bash
make up
```

This starts four services:

| Service | Container | Port | Role |
|---------|-----------|------|------|
| Qdrant | zscaler-qdrant | 6333 | Vector database |
| Crawl4AI | zscaler-crawl4ai | 11235 | Headless browser crawler |
| RAG API | zscaler-rag-api | 8000 | OpenAI-compatible query endpoint |
| OpenWebUI | zscaler-openwebui | 3000 | Chat interface |

Wait 30–60 seconds for all services to initialise. Check with:

```bash
make doctor
```

All four services should show OK before proceeding.

> **Note on cold starts:** bge-m3 and the cross-encoder are baked into the rag-api Docker
> image at build time, so the container starts healthy in ~20 seconds. No runtime downloads.
> If you ever rebuild the image (`docker compose build rag-api`), the models are re-cached
> into the new image layer automatically.

### 2.4 Crawl the Zscaler knowledge base

The knowledge base covers ZIA, ZPA, and ZDX troubleshooting and configuration pages
from `help.zscaler.com`. The full crawl covers ~1,825 pages and runs in batches.

```bash
make crawl-all
```

This runs `scripts/crawl_all.py`, which:
1. Parses the Zscaler sitemap for all troubleshooting/configuration URLs
2. Crawls each page via Crawl4AI (headless browser, respects rate limits)
3. Saves Markdown files to `data/raw/`
4. Auto-ingests in batches (chunk → embed → index into Qdrant)

Expected runtime: 2–4 hours. Monitor progress:

```bash
# Windows PowerShell
Get-Content $env:TEMP\ingest_run.log -Tail 3
# Linux/Mac
tail -f /tmp/ingest.log
```

When finished: `make doctor` should show ~13,800 chunks in Qdrant.

> **Safe to close Claude Code or the terminal** — the ingest runs as a detached background
> process. If it fails mid-way, resume with `python scripts/ingest.py --skip-embed`
> (uses cached embeddings, skips the 4-hour computation).

### 2.5 Open OpenWebUI

1. Navigate to `http://localhost:3000`
2. Register the first account — this account becomes admin
3. OpenWebUI is pre-configured to talk to the RAG API via `docker-compose.yml`
4. In the model selector, choose any `zscaler-rag/groq-*` model
5. Send a test query to verify end-to-end operation

**Test query:**
> "ZPA App Connector shows TUNNEL_DOWN. What are the most common causes and how do I fix it?"

**Expected:** structured Markdown response with `## Root Cause`, `## Resolution Steps`, `## References`.

### 2.6 Optional: Enable Ollama (local / private LLM)

Required if you will analyse **internal Zscaler logs or screenshots** — cloud providers must
not receive this data. See [§6 LLM Provider Configuration](#6-llm-provider-configuration).

```bash
make ollama-setup        # Starts Ollama container + pulls llama3.2 + llama3.2-vision
make ollama-vision       # Optional: also pull llava, moondream, qwen2-vl:7b
```

### 2.7 Verify health

```bash
make doctor
```

A fully healthy first-time setup shows:

```
Services   qdrant OK  crawl4ai OK  rag-api OK  open-webui OK
API Keys   groq: valid
Qdrant     13802 chunks  ZIA:841  ZPA:530  ZDX:133  DECEPTION:321
Result:    ALL SYSTEMS GO
```

**Common first-run issues:**

| Symptom | Fix |
|---------|-----|
| `make doctor` shows rag-api FAIL | Wait 30s and re-run — models are loading |
| Qdrant shows 0 chunks after `make crawl-all` | Ingest may still be running; check log file |
| OpenWebUI shows "connection refused" | rag-api health check hasn't passed yet; wait and retry |
| Groq key shows WARN in validate-config | Check key at console.groq.com — may be expired |

---

## 3. Daily Operations

**Audience:** All users.
**When:** Any time you start a shift, resume after a machine restart, or notice odd behaviour.

### 3.1 Starting the stack

```bash
cd Zscalerhelper
make up
```

Docker starts containers in dependency order: Qdrant → rag-api → OpenWebUI.
Allow 30–60 seconds for all services to become healthy.

> **After a machine restart or Docker Desktop restart**, use the two-step start instead
> of `make up` directly. Qdrant's health check takes 30–60 seconds to pass; if rag-api
> starts before that, Docker marks the dependency as failed and the whole stack won't come up.
>
> ```bash
> docker compose up -d qdrant          # start Qdrant first
> docker ps                             # wait until zscaler-qdrant shows (healthy)
> docker compose up -d                  # then start everything else
> ```
>
> Once you see `Application startup complete.` in `make logs`, everything is ready.

### 3.2 Health check

```bash
make doctor
```

| Result | Meaning | Action |
|--------|---------|--------|
| ALL SYSTEMS GO | Everything healthy | None |
| OK WITH WARNINGS | Minor issues (e.g. Ollama offline, pages stale) | Review warnings, proceed |
| DEGRADED | Critical service down (qdrant, rag-api) | See [§7 Troubleshooting](#7-troubleshooting) |

### 3.3 Stopping the stack

```bash
make down
```

Volumes (Qdrant data, OpenWebUI history) are preserved. `make up` resumes from where
you left off with no data loss.

### 3.4 Checking logs

```bash
make logs            # Tail rag-api logs (query requests, errors, model loading)
make logs-crawl4ai   # Tail crawl4ai logs (page crawl status)
```

Exit with Ctrl+C.

### 3.5 API smoke test

```bash
# Should return 401 (empty auth)
curl -s http://localhost:8000/v1/models

# Should return model list (valid auth)
curl -s -H "Authorization: Bearer zscaler-rag" http://localhost:8000/v1/models

# Full RAG query
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer zscaler-rag" \
  -H "Content-Type: application/json" \
  -d '{"model":"zscaler-rag/groq-llama-3-3-70b-versatile",
       "messages":[{"role":"user","content":"ZPA tunnel down causes"}]}' \
  | python -m json.tool
```

### 3.6 Normal operating metrics

| Metric | Value |
|--------|-------|
| Qdrant chunks | ~13,800 |
| Pages indexed | ~1,825 |
| rag-api startup time | ~20s (models baked into image) |
| Query latency (Groq) | 3–8 seconds end-to-end |
| Query latency (Ollama CPU) | 60–180 seconds |
| Knowledge base products | ZIA ~840, ZPA ~530, ZDX ~130, DECEPTION ~320 |

### 3.7 Multi-user notes

OpenWebUI supports multiple accounts. Each user has their own conversation history.
The underlying RAG API is shared — no per-user rate limiting by default.

For team deployment:
- Change `API_KEY` in `.env` from the default `zscaler-rag` to a strong random value
- Set `ALLOWED_ORIGINS` to only the machine running OpenWebUI
- Run `make validate-config` after any `.env` change

---

## 4. Knowledge Base Management

**Audience:** Maintainer responsible for keeping the knowledge base current.
**When:** Weekly check; after Zscaler releases major documentation updates; after changing the embedding model.

### 4.1 Check current state

```bash
make doctor
```

Look at the Knowledge Base panel:

```
Pages crawled : 1825   ZIA: 841  ZDX: 133  ZPA: 530
Pages indexed : 1825
Pages stale   : 0
```

- **Pages stale > 0** → sitemap shows newer content; run `make update`
- **Pages indexed < Pages crawled** → some pages not yet ingested; run `make ingest`
- **Raw .md files mismatch** → file exists without manifest entry (benign)

### 4.2 Incremental update (weekly routine)

```bash
make update     # crawl changed pages only (compares sitemap lastmod)
make ingest     # re-embed changed pages, update Qdrant
```

The ingest is idempotent — deterministic chunk IDs (MD5 of `url|section|idx`) mean
re-indexing a page simply overwrites existing Qdrant points. No duplicates.

### 4.3 Full crawl (initial setup or after reset)

```bash
make crawl-all
```

Crawls all ~1,825 pages from the Zscaler sitemap. Includes auto-ingest.
Expected runtime: 2–4 hours total (crawl ≈ 30–60 min, embedding ≈ 3–4 hours on CPU).

To run crawl and ingest separately:

```bash
python scripts/crawl_all.py --no-ingest   # crawl only
make ingest                                # then ingest separately
```

### 4.4 Wipe and re-index from scratch

Do this when the embedding model changes or Qdrant becomes corrupted:

```bash
make reset-db   # wipes the qdrant_storage Docker volume
make ingest     # re-embeds all data/raw/*.md files
```

> **Warning:** `make reset-db` removes the Qdrant volume. Raw `.md` files in `data/raw/`
> are preserved (bind mount, not a Docker volume).

### 4.5 Embedding model change

```bash
# 1. Update .env
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIM=1024
SPARSE_ENABLED=true

# 2. Validate
make validate-config

# 3. Wipe and re-ingest
make reset-db
make ingest
```

The current model is `BAAI/bge-m3` (1024-dim, hybrid dense+sparse, MTEB 64.3).

### 4.6 Chunk IDs and deduplication

Chunk IDs are deterministic: `MD5(url + "|" + section_header + "|" + chunk_index)`.

- Re-ingesting a page **overwrites** its Qdrant points — no duplicates
- Renaming/moving a page creates new IDs; old ones become orphaned
- Clean up orphans with `make reset-db && make ingest`

### 4.7 Product tagging

Each chunk carries a `product` field (`zia`, `zpa`, `zdx`, `deception`, `unknown`).

To query with a product filter in OpenWebUI:
```
[product:zpa] App Connector showing TUNNEL_DOWN
```

Or via the API:
```json
{
  "model": "zscaler-rag/groq-llama-3-3-70b-versatile",
  "messages": [{"role": "user", "content": "App Connector TUNNEL_DOWN"}],
  "product_filter": "zpa"
}
```

---

## 5. Incident Investigation Guide

**Audience:** Security engineer responding to a Zscaler-related incident.

### ⚠️ Privacy Rule (Mandatory)

**Internal logs and screenshots must only be sent to Ollama (local).**

| Data type | Safe provider | Unsafe providers |
|-----------|--------------|-----------------|
| General Zscaler questions | Groq, OpenRouter, Ollama | — |
| Internal log output | **Ollama only** | Groq, OpenRouter |
| Error screenshots | **Ollama only** | Groq, OpenRouter |
| Employee/system identifiers | **Ollama only** | Groq, OpenRouter |

See [§6.3 Ollama Setup](#63-ollama-localprivate-llm) to enable Ollama before handling internal data.

### 5.1 Mode 1: General question (no internal data)

1. Open `http://localhost:3000`
2. Select a cloud model (e.g. `zscaler-rag/groq-llama-3-3-70b-versatile`)
3. Ask your question in plain English

**Good query patterns:**
```
ZPA App Connector shows CONNECTOR_DOWN — what are common causes?
How do I configure SSL inspection bypass for Office 365 in ZIA?
ZDX digital experience score dropped below 50 for all EU users — how do I diagnose?
What ZIA policy settings cause AUTH_FAILED for SAML users?
```

**Expected response structure:**
- `## Root Cause Analysis`
- `## Step-by-Step Resolution`
- `## Verification Steps`
- `## Prevention Tips`
- `## References` (source URLs from the knowledge base)

### 5.2 Mode 2: Log analysis (paste raw logs)

**Privacy requirement:** Switch to an Ollama model first.

1. In OpenWebUI, select `zscaler-rag/ollama-llama3-2` (or any `ollama-*` model)
2. Paste the raw log block directly into the chat

The system auto-detects log content and switches to log-analysis mode, which:
- Extracts error codes and Zscaler component keywords using Drain3 template mining
- Retrieves relevant documentation based on extracted signals
- Returns a structured analysis with identified events, root cause, and resolution steps

**Example log paste:**
```
2026-05-28T10:00:00Z ERROR connector=prod-dc1 reason=AUTH_FAILED tunnel_id=abc123
2026-05-28T10:00:01Z WARN  broker=us-west-1 status=UNREACHABLE retries=3
2026-05-28T10:00:05Z ERROR connector=prod-dc1 reason=CERT_ERROR cert_subject=*.internal.corp
2026-05-28T10:00:10Z FATAL tunnel=T-4421 state=TUNNEL_DOWN duration=320s
```

If auto-detection doesn't trigger, prepend `[log analysis]` to force log mode.

### 5.3 Mode 3: Screenshot / image analysis (full privacy)

**Requirements:**
- Ollama must be running with a vision-capable model
- Recommended: `qwen2-vl:7b` (DocVQA 93.1, best text-in-image accuracy)

```bash
make ollama-vision   # pulls llava, moondream, qwen2-vl:7b
```

1. In OpenWebUI, select `zscaler-rag/ollama-qwen2-vl:7b`
2. Click the paperclip icon and attach your screenshot
3. Type your question, or send the image — the system analyses it automatically

### 5.4 Retrieval quality tips

| Situation | Tip |
|-----------|-----|
| Response lacks detail | Increase `top_k` in the API call (default 5, max ~20) |
| Wrong product context | Use `[product:zpa]` prefix or `product_filter` API field |
| Error code not found | Include the full code (e.g. `AUTH_FAILED`) — hybrid search handles exact tokens |
| Very long log | Paste only the most recent 50–100 lines |
| Screenshot too complex | Crop to the error area before attaching |

### 5.5 Escalation

If the RAG system cannot find relevant documentation:

1. Check `make doctor` — verify chunks > 0 in Qdrant
2. Try rephrasing with more specific Zscaler terminology
3. Run `make update` to pull the latest documentation
4. Escalate to Zscaler Support with the log snippets and the RAG analysis as context

---

## 6. LLM Provider Configuration

**Audience:** Maintainer configuring or switching LLM providers.

### 6.1 Provider overview

| Provider | Where data goes | Use for | Requires |
|----------|-----------------|---------|----------|
| Groq | Groq cloud (US) | Fast text queries, no internal data | `GROQ_API_KEY` |
| OpenRouter | OpenRouter cloud (US) | Wider model selection | `OPENROUTER_API_KEY` |
| Ollama | **Local machine only** | Internal logs, screenshots, privacy mode | Docker + GPU optional |

### 6.2 Groq (default text provider)

```ini
# .env
GROQ_API_KEY=gsk_...
DEFAULT_PROVIDER=groq
DEFAULT_MODEL=llama-3.3-70b-versatile
```

| OpenWebUI model ID | Groq model | Notes |
|--------------------|------------|-------|
| `zscaler-rag/groq-llama-3-3-70b-versatile` | llama-3.3-70b-versatile | Best quality, default |
| `zscaler-rag/groq-llama-3-1-8b-instant` | llama-3.1-8b-instant | Fastest |
| `zscaler-rag/groq-mixtral-8x7b-32768` | mixtral-8x7b-32768 | Long context (32k tokens) |
| `zscaler-rag/groq-gemma2-9b-it` | gemma2-9b-it | Google Gemma2 |

Get your key at `console.groq.com` — free tier is sufficient for team use.

### 6.3 Ollama (local / private LLM)

Ollama runs models entirely on your machine. **Nothing leaves your network.**
Required for log analysis and screenshot investigation.

**First-time setup:**
```bash
make ollama-setup        # Starts container + pulls llama3.2 + llama3.2-vision
make ollama-vision       # Optional: pull llava, moondream, qwen2-vl:7b
```

**Available models:**

| OpenWebUI model ID | Model | Type | RAM |
|--------------------|-------|------|-----|
| `zscaler-rag/ollama-llama3-2` | llama3.2:3b | Text | 4 GB |
| `zscaler-rag/ollama-llama3-1` | llama3.1:8b | Text | 6 GB |
| `zscaler-rag/ollama-mistral` | mistral:7b | Text | 6 GB |
| `zscaler-rag/ollama-llama3-2-vision` | llama3.2-vision | Vision | 8 GB |
| `zscaler-rag/ollama-llava` | llava:7b | Vision | 6 GB |
| `zscaler-rag/ollama-moondream` | moondream:1.8b | Vision | 2 GB |
| `zscaler-rag/ollama-qwen2-vl:7b` | qwen2-vl:7b | Vision | 8 GB |

**GPU acceleration (optional but recommended for vision models):**

Without GPU: expect 60–180s per response with vision models.
With GPU: expect 5–15s per response.

To enable NVIDIA GPU:

1. Install NVIDIA Container Toolkit on the host
2. In `docker-compose.yml`, uncomment the `deploy` block under the `ollama` service:
   ```yaml
   deploy:
     resources:
       reservations:
         devices:
           - driver: nvidia
             count: 1
             capabilities: [gpu]
   ```
3. Restart Ollama: `docker compose --profile local-llm up -d ollama`
4. Verify: `docker exec zscaler-ollama nvidia-smi`

### 6.4 Changing the default provider/model

```ini
# .env
DEFAULT_PROVIDER=ollama       # groq | openrouter | ollama
DEFAULT_MODEL=llama3.2
```

```bash
docker compose restart rag-api   # apply changes
```

### 6.5 Adding a new provider

1. Create `llm/{name}_provider.py` implementing `BaseLLMProvider` from `llm/base.py`
2. Register in `llm/factory.py` `_PROVIDERS` dict
3. Add models to `DEFAULT_MODELS` in the new provider class
4. Update §6 of this document with the provider's privacy posture and model table
5. Add entry to `.env.example` with a `# optional` comment
6. Write test in `tests/unit/test_factory.py`

---

## 7. Troubleshooting

**Always run `make doctor` first** — it surfaces 80% of issues instantly.

### 7.1 Service issues

**`make up` fails with "dependency failed to start: container zscaler-qdrant is unhealthy"**

This happens after a machine restart or Docker Desktop restart. Qdrant needs 30–60 seconds
to pass its health check; `make up` starts rag-api too quickly before Qdrant is ready.

Fix — start in two steps:
```bash
docker compose up -d qdrant          # start Qdrant first
docker ps                             # wait until zscaler-qdrant shows (healthy)
docker compose up -d                  # then start everything else
```

---

**rag-api shows FAIL in doctor**

bge-m3 and the cross-encoder are baked into the Docker image — rag-api should be healthy
within ~20 seconds of `make up`. If it still shows FAIL:

```bash
make logs   # watch for "Application startup complete."
docker compose logs rag-api --tail=50
```

Look for:
- `ModuleNotFoundError: No module named 'FlagEmbedding'` → stale image; rebuild:
  ```bash
  docker compose build rag-api && docker compose up -d rag-api
  ```
- `ConnectionRefusedError` to Qdrant → Qdrant not healthy yet; wait and retry

---

**Qdrant health endpoint returns [404]**

This is cosmetic — Qdrant's `/health` endpoint uses gRPC, not HTTP. The `[404]` in
`make doctor` is normal. If the container status shows OK, Qdrant is healthy.

Confirm via the dashboard: `http://localhost:6333/dashboard`

---

**crawl4ai shows WARN**

Crawl4AI takes 30–60 seconds to initialise its Playwright browser on start. Wait and re-run.

```bash
make logs-crawl4ai
docker compose restart crawl4ai
```

---

**OpenWebUI shows "connection refused" or blank page**

```bash
make logs   # wait for "Application startup complete."
docker exec zscaler-openwebui env | grep OPENAI
# Expected: OPENAI_API_BASE_URL=http://rag-api:8000/v1
```

### 7.2 Query / retrieval issues

**Responses are generic or not Zscaler-specific**

```bash
curl -s http://localhost:6333/collections/zscaler_docs \
  | python -m json.tool | grep points_count
```

If 0: run `make ingest`. If > 0 but still generic, lower `MIN_SCORE` in `.env` (default 0.3):
```ini
MIN_SCORE=0.1
```
Then `docker compose restart rag-api`.

---

**Log paste not triggering log-analysis mode**

Auto-detection requires ≥3 newlines AND (a timestamp OR 2+ error keywords).
Force log mode by prepending `[log analysis]` to your message.

---

**Vision model returns "I cannot see the image"**

Only these models support vision:
`ollama-llama3-2-vision`, `ollama-llava`, `ollama-moondream`, `ollama-qwen2-vl:7b`

Groq and OpenRouter models do not accept image attachments.

### 7.3 Ingest issues

**Ingest takes too long / appears hung**

bge-m3 on CPU: ~50s per batch of 32 chunks × 432 batches = ~4 hours total.

```powershell
# Windows
Get-Content $env:TEMP\ingest_run.log -Tail 3
Get-Process python | Select-Object Id, WorkingSet
```

If the process was killed mid-way after Step 2 (embedding) completed:
```bash
python scripts/ingest.py --skip-embed   # uses cached embeddings, goes straight to upsert
```

---

**Qdrant shows fewer chunks than expected after ingest**

`indexed_vectors_count` is a lagging metric — HNSW indexing runs in background.
Use `points_count` instead:

```bash
curl -s http://localhost:6333/collections/zscaler_docs | python -m json.tool
```

### 7.4 Authentication issues

**`{"detail": "Invalid API key"}`**

```bash
# Correct format
curl -H "Authorization: Bearer zscaler-rag" http://localhost:8000/v1/models

# Check your current key
grep API_KEY .env
```

---

**Unauthenticated request succeeds (should return 401)**

Verify `api/main.py` has:
```python
if not token or token != cfg.API_KEY:   # correct
```
Not the old broken form: `if token and token != cfg.API_KEY`

### 7.5 Crawl issues

**crawl_all.py causes OOM / Chromium processes accumulate**

The fix is in `scripts/crawl_all.py` (single `asyncio.run()` loop with browser restart
every 100 pages). Kill orphan processes:

```powershell
# Windows
Get-Process chromium -ErrorAction SilentlyContinue | Stop-Process -Force
```

### 7.6 Config issues

**EMBEDDING_DIM mismatch**

```
FAIL  BAAI/bge-m3: model outputs dim=1024 but EMBEDDING_DIM=384
```

Fix `.env`: `EMBEDDING_DIM=1024`, then `make validate-config`, then `make reset-db && make ingest`.

---

**ALLOWED_ORIGINS wildcard**

```
FAIL  ALLOWED_ORIGINS: wildcard '*'
```

Fix `.env`:
```ini
ALLOWED_ORIGINS=http://localhost:3000
```
Then `docker compose restart rag-api`.

---

## 8. Configuration Reference

All configuration is via the `.env` file. Copy `.env.example` to `.env` before editing.
Run `make validate-config` after any change.

### LLM Provider Keys

| Variable | Default | Notes |
|----------|---------|-------|
| `GROQ_API_KEY` | — | console.groq.com; free tier; US servers — never for internal data |
| `OPENROUTER_API_KEY` | — | openrouter.ai; pay-per-use; US servers — never for internal data |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Change to `http://ollama:11434` inside Docker |
| `DEFAULT_PROVIDER` | `groq` | `groq` \| `openrouter` \| `ollama` |
| `DEFAULT_MODEL` | `llama-3.3-70b-versatile` | Must match a model the default provider supports |

### Qdrant Connection

| Variable | Default | Notes |
|----------|---------|-------|
| `QDRANT_HOST` | `localhost` | Use `qdrant` inside Docker (auto-set by docker-compose) |
| `QDRANT_PORT` | `6333` | HTTP port; don't change unless you remapped it |
| `COLLECTION_NAME` | `zscaler_docs` | Change for multiple isolated knowledge bases |

### Embedding Parameters *(requires re-ingest on change)*

| Variable | Default | Notes |
|----------|---------|-------|
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | MTEB 64.3; change to `all-MiniLM-L6-v2` for faster setup |
| `EMBEDDING_DIM` | `1024` | **Must match model**: bge-m3=1024, MiniLM=384 |
| `SPARSE_ENABLED` | `true` | Enables hybrid search; disable for dense-only (faster, less precise) |

### RAG Tuning *(no re-ingest needed)*

| Variable | Default | Effect |
|----------|---------|--------|
| `TOP_K` | `5` | Chunks retrieved per query (1–20). Higher = richer context, slower |
| `CHUNK_SIZE` | `1500` | Max chars per chunk (~500 tokens). Change requires re-ingest |
| `CHUNK_OVERLAP` | `150` | Overlap between chunks (10% of CHUNK_SIZE). Change requires re-ingest |
| `MIN_SCORE` | `0.3` | Min cross-encoder score to include a chunk. Lower = broader recall |

### API Security

| Variable | Default | Notes |
|----------|---------|-------|
| `API_KEY` | `zscaler-rag` | **Change before team deployment.** Also update `OPENAI_API_KEY` in docker-compose.yml |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | Never use `*`. Comma-separated list for multiple UIs |

### Scenario Presets

**Fast setup, lower quality (developer testing):**
```ini
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIM=384
SPARSE_ENABLED=false
TOP_K=3
MIN_SCORE=0.2
```

**Maximum quality (with GPU):**
```ini
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIM=1024
SPARSE_ENABLED=true
TOP_K=8
MIN_SCORE=0.3
```

**Privacy-first (Ollama only):**
```ini
GROQ_API_KEY=
OPENROUTER_API_KEY=
DEFAULT_PROVIDER=ollama
DEFAULT_MODEL=llama3.2
```

**Low-memory machine (8 GB RAM):**
```ini
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIM=384
SPARSE_ENABLED=false
```

---

## 9. Hardware Requirements

### Quick sizing guide

| Use case | RAM | CPU | Disk |
|----------|-----|-----|------|
| Groq only (no Ollama) | 8 GB | 4 cores | 15 GB |
| Ollama text models | 16 GB | 8 cores | 25 GB |
| Ollama vision (qwen2-vl:7b) | 24 GB | 8 cores | 40 GB |
| GPU acceleration | 16 GB + 8 GB VRAM | 4 cores | 40 GB |

### RAM breakdown

| Service | Idle | Peak |
|---------|------|------|
| rag-api (bge-m3) | 2.5 GB | 3.5 GB |
| Qdrant | 0.5 GB | 1 GB |
| OpenWebUI | 0.3 GB | 0.5 GB |
| Ollama llama3.2:3b | 4 GB | 4 GB |
| Ollama qwen2-vl:7b | 8 GB | 8 GB |

### Disk breakdown

| Component | Size |
|-----------|------|
| Docker images (all) | ~10 GB |
| Crawled Markdown (`data/raw/`) | ~500 MB |
| Qdrant vectors | ~2 GB |
| Ollama models (optional) | 2–8 GB each |

### Setup time

| Step | CPU (min) | GPU |
|------|-----------|-----|
| `docker compose up` (first run) | 5–10 min | 5–10 min |
| `make crawl-all` | 60–90 min | 60–90 min |
| `make ingest` | **3–4 hours** | ~30 min |
| rag-api startup (subsequent) | ~20s | ~20s |
| Per-query latency (Groq) | 3–8s | 3–8s |
| Per-query latency (Ollama) | 60–180s | 5–15s |

### Windows / WSL2 notes

Docker Desktop on Windows defaults to 50% of physical RAM. Increase if running Ollama:

```ini
# %USERPROFILE%\.wslconfig
[wsl2]
memory=12GB
processors=8
```

Restart Docker Desktop after changing.

### GPU acceleration (NVIDIA)

1. Install NVIDIA Container Toolkit
2. Uncomment the `deploy` block in `docker-compose.yml` under `ollama`
3. Restart: `docker compose --profile local-llm up -d ollama`
4. Verify: `docker exec zscaler-ollama nvidia-smi`

Note: bge-m3 embedding runs on CPU regardless of GPU availability.

### Network requirements

| Destination | When needed |
|-------------|------------|
| `hub.docker.com`, `ghcr.io` | First `make up` only |
| `help.zscaler.com` | `make crawl-all` and `make update` |
| `api.groq.com` | Every Groq query |
| `huggingface.co` | First `docker compose build rag-api` |

Ollama queries use no outbound connections.
