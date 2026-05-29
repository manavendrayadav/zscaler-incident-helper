# SOP-01 — Initial Setup

**Audience:** New team member setting up the system for the first time.
**Time required:** 15 minutes hands-on, ~4 hours background (bge-m3 embedding on CPU).
**Prerequisites:** Docker Desktop installed, Git, Python 3.11+.

---

## 1. Clone and configure

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

---

## 2. Validate the configuration

```bash
make validate-config
```

Expected: all PASS or WARN (warnings are advisory). No FAIL lines.

If Qdrant FAIL appears: Docker is not running. Start Docker Desktop first.

---

## 3. Start the Docker stack

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

Wait 30–60 seconds for Crawl4AI to finish initialising its Playwright browser. Check with:

```bash
make doctor
```

All four services should show OK before proceeding.

---

## 4. Crawl the Zscaler knowledge base

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

Expected runtime: 2–4 hours. You can monitor progress:

```bash
# In a separate terminal:
Get-Content $env:TEMP\ingest_run2.log -Wait -Tail 5   # Windows PowerShell
# or
tail -f /tmp/ingest.log                               # Linux/Mac
```

When finished: `make doctor` should show ~13,800 chunks in Qdrant.

---

## 5. Open OpenWebUI

1. Navigate to `http://localhost:3000`
2. Register the first account — this account becomes admin
3. OpenWebUI is already pre-configured to talk to the RAG API (via `docker-compose.yml`
   environment variables). No manual connection setup needed.
4. In the model selector, choose any `zscaler-rag/groq-*` model to start
5. Ask a Zscaler question to verify end-to-end operation

Example test query:
> "ZPA App Connector shows TUNNEL_DOWN. What are the most common causes and how do I fix it?"

Expected: structured Markdown response with ## Root Cause, ## Resolution Steps, ## References sections.

---

## 6. Optional: Enable Ollama (local / private LLM)

Required if you will analyse **internal Zscaler logs or screenshots** — cloud providers must not
receive this data. See [SOP-05 — LLM Provider Setup](05-llm-providers.md) for full instructions.

Quick start:

```bash
make ollama-setup        # Starts Ollama container + pulls llama3.2 + llama3.2-vision
make ollama-vision       # Optional: also pull llava, moondream, qwen2-vl:7b
```

---

## 7. Verify health

```bash
make doctor
```

A fully healthy first-time setup shows:

```
Services   qdrant OK  crawl4ai OK  rag-api OK  open-webui OK
API Keys   groq: valid
Qdrant     13802 chunks  ZIA:841  ZPA:530  ZDX:133  DECEPTION:321  ...
Result:    ALL SYSTEMS GO
```

---

## Troubleshooting first-run issues

| Symptom | Fix |
|---------|-----|
| `make doctor` shows rag-api FAIL on first start | rag-api downloads bge-m3 (~1.5 GB) on first run — wait 5–10 min, then re-run |
| Qdrant shows 0 chunks after `make crawl-all` | Ingest may still be running; check log file |
| OpenWebUI shows "connection refused" | rag-api health check hasn't passed yet; wait and retry |
| Groq key shows WARN in validate-config | Check the key at console.groq.com — may be expired or rate-limited |

For all other issues, see [SOP-06 — Troubleshooting](06-troubleshooting.md).
