# Quick Start

Get from zero to your first AI-assisted Zscaler incident response in under 10 minutes.
No prior knowledge of RAG, vector databases, or embeddings required.

> **New to RAG or AI?** Read [BEGINNER_GUIDE.md](BEGINNER_GUIDE.md) first — it explains what this tool does and why it works.

---

## Prerequisites

- [ ] Docker Desktop installed and running
- [ ] Git installed
- [ ] A Groq API key (free at [console.groq.com](https://console.groq.com))
- [ ] 10 GB free disk space, 8 GB RAM minimum

---

## Step 1 — Clone and configure (2 min)

```bash
git clone https://github.com/manavendrayadav/zscaler-rag.git
cd zscaler-rag
cp .env.example .env
```

Open `.env` and set your Groq API key:

```ini
GROQ_API_KEY=gsk_your_key_here
```

Leave all other values at their defaults.

---

## Step 2 — Validate and start (2 min)

```bash
make validate-config   # check API key, Docker connectivity
make up                # start Qdrant, Crawl4AI, RAG API, OpenWebUI
```

Wait ~30 seconds, then verify everything is green:

```bash
make doctor
```

Expected output: `ALL SYSTEMS GO  12 passed  0 failures`

> **Qdrant shows [404]?** That's normal — Qdrant's health endpoint uses gRPC, not HTTP. If the container shows OK, it's healthy.

---

## Step 3 — Build the knowledge base (~4 hours, runs in background)

```bash
make crawl-all
```

This crawls all 1,825 Zscaler help pages and indexes them. The process:
- Crawl: ~1 hour
- Embedding: ~3–4 hours on CPU (runs in background — close your terminal, it continues)
- You can use the system immediately; results improve as indexing completes

Monitor progress:

```bash
# Windows PowerShell
Get-Content $env:TEMP\ingest_run.log -Tail 3

# Linux/Mac
tail -f /tmp/ingest.log
```

---

## Step 4 — Open the chat interface

Navigate to **http://localhost:3000**

1. Register an account (first account becomes admin)
2. Select model: `zscaler-rag/groq-llama-3-3-70b-versatile`
3. Ask your first question

---

## First query

```
ZPA App Connector shows TUNNEL_DOWN. What are the most common causes and how do I fix it?
```

**Expected response structure:**
- `## Root Cause Analysis` — what caused TUNNEL_DOWN
- `## Step-by-Step Resolution` — commands to run
- `## Verification Steps` — confirm the fix worked
- `## References` — links to the specific Zscaler help pages used

> **No results or generic answers?** The knowledge base may still be indexing. Check `make doctor` for chunk count — it should reach ~13,800 when complete.

---

## Quick API test (optional)

Confirm the API is working without opening a browser:

```bash
# Should return 401 (auth required)
curl http://localhost:8000/v1/models

# Should return model list
curl -H "Authorization: Bearer zscaler-rag" http://localhost:8000/v1/models
```

---

## What's next

| If you want to... | Go to |
|-------------------|-------|
| Understand how RAG works | [BEGINNER_GUIDE.md](BEGINNER_GUIDE.md) |
| Analyse internal logs privately | [BEGINNER_GUIDE.md#privacy](BEGINNER_GUIDE.md) → enable Ollama |
| Tune retrieval quality | [CONFIGURATION.md](CONFIGURATION.md) |
| Integrate via the API | [API.md](API.md) |
| See example queries and responses | [EXAMPLES.md](EXAMPLES.md) |
| Troubleshoot setup issues | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |
| Check hardware requirements | [HARDWARE_REQUIREMENTS.md](HARDWARE_REQUIREMENTS.md) |
