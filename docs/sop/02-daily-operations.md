# SOP-02 — Daily Operations

**Audience:** All users of the system.
**When:** Any time you start a shift, resume after a machine restart, or notice odd behaviour.

---

## Starting the stack

```bash
cd Zscalerhelper
make up
```

Docker restarts all containers in the correct dependency order. Allow 30–60 seconds before
querying — OpenWebUI only becomes available after rag-api passes its health check,
which itself waits for Qdrant.

---

## Health check (run first if anything looks wrong)

```bash
make doctor
```

Reads and displays:

- **Services** — container running + HTTP endpoint reachable for each service
- **API Keys** — Groq tested live; OpenRouter and Ollama checked for reachability
- **Knowledge Base** — page count, index coverage, stale pages, file/manifest consistency
- **Qdrant** — chunk count and product distribution

Interpreting results:

| Result | Meaning | Action |
|--------|---------|--------|
| ALL SYSTEMS GO | Everything healthy | None |
| OK WITH WARNINGS | Minor issues (e.g. Ollama offline, pages stale) | Review warnings, proceed |
| DEGRADED | Critical service down (qdrant, rag-api) | See SOP-06 before querying |

---

## Stopping the stack

```bash
make down
```

This stops all containers. Volumes (Qdrant data, OpenWebUI history) are preserved. A subsequent
`make up` resumes from where you left off with no data loss.

---

## Checking logs

```bash
make logs            # Tail rag-api logs (query requests, errors, model loading)
make logs-crawl4ai   # Tail crawl4ai logs (page crawl status)
```

Exit with Ctrl+C. Logs are also accessible in Docker Desktop.

---

## Quick API smoke test

Verify auth and basic retrieval are working without opening OpenWebUI:

```bash
# Should return 401 (empty auth)
curl -s http://localhost:8000/v1/models

# Should return model list (valid auth)
curl -s -H "Authorization: Bearer zscaler-rag" http://localhost:8000/v1/models

# Test a full RAG query
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer zscaler-rag" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "zscaler-rag/groq-llama-3-3-70b-versatile",
    "messages": [{"role": "user", "content": "ZPA tunnel down causes"}]
  }' | python -m json.tool
```

---

## Updating the knowledge base (routine)

When Zscaler releases documentation updates, run an incremental crawl:

```bash
make update      # Crawls only pages changed since last crawl (compares sitemap lastmod)
make ingest      # Re-embeds and re-indexes any updated pages
```

Full re-index is not needed unless the embedding model changes. See
[SOP-03 — Knowledge Base Management](03-knowledge-base.md) for details.

---

## Normal operating metrics

After a healthy full ingest, expect:

| Metric | Value |
|--------|-------|
| Qdrant chunks | ~13,800 |
| Pages indexed | ~1,825 |
| rag-api startup time | ~20s (models baked into image, no runtime download) |
| Query latency (Groq) | 3–8 seconds end-to-end |
| Query latency (Ollama CPU) | 60–180 seconds depending on model size |
| Knowledge base products | ZIA ~840, ZPA ~530, ZDX ~130, DECEPTION ~320 |

---

## Multi-user notes

OpenWebUI supports multiple accounts. Each user has their own conversation history.
The underlying RAG API is shared — there is no per-user rate limiting by default.

If the team grows, consider:
- Changing `API_KEY` in `.env` from the default `zscaler-rag` to a stronger value
- Setting `ALLOWED_ORIGINS` to only the machine running OpenWebUI
- Running `make validate-config` after any `.env` change to catch mismatches
