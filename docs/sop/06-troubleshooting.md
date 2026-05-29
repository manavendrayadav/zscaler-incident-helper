# SOP-06 — Troubleshooting

**Audience:** All users.
**When:** Something isn't working as expected.

Always run `make doctor` first — it surfaces 80% of issues instantly.

---

## Service issues

### rag-api shows FAIL in doctor

**Most common cause:** The container is still loading the bge-m3 embedding model on first start.
bge-m3 is ~1.5 GB and takes 5–10 minutes to download on a cold start.

```bash
make logs   # watch for "Application startup complete."
```

If startup complete is not appearing after 15 minutes:

```bash
docker compose logs rag-api --tail=50
```

Look for:
- `ModuleNotFoundError: No module named 'FlagEmbedding'` → image is stale; rebuild:
  ```bash
  docker compose build rag-api && docker compose up -d rag-api
  ```
- `ConnectionRefusedError` to Qdrant → Qdrant container isn't healthy yet; wait and retry
- Any Python traceback → check the error, likely a config mismatch

### Qdrant health endpoint returns 404

The Qdrant `/health` endpoint returns `404` by design when accessed via HTTP (it uses gRPC health).
This is cosmetic — the doctor displays `[404]` in the HTTP column but the container
status column will show OK if the container is running. The service is healthy.

Confirm by checking the Qdrant dashboard directly:
```
http://localhost:6333/dashboard
```

### crawl4ai shows WARN

Crawl4AI takes 30–60 seconds to initialise its Playwright browser on container start.
Wait a minute after `make up` and re-run `make doctor`.

If it persists:
```bash
make logs-crawl4ai
docker compose restart crawl4ai
```

### OpenWebUI shows "connection refused" or blank page

OpenWebUI depends on rag-api being healthy. If rag-api isn't up yet:
```bash
make logs   # wait for "Application startup complete."
```

If rag-api is healthy but OpenWebUI still can't connect, the OpenAI API URL may be
misconfigured inside the container. Check:
```bash
docker exec zscaler-openwebui env | grep OPENAI
# Expected: OPENAI_API_BASE_URL=http://rag-api:8000/v1
```

---

## Query / retrieval issues

### Responses are generic or not Zscaler-specific

Likely cause: Qdrant has 0 chunks, or retrieval scored nothing above the MIN_SCORE threshold.

```bash
# Check chunk count
curl -s http://localhost:6333/collections/zscaler_docs | python -m json.tool | grep points_count
```

If 0: run `make ingest` to re-index.

If > 0 but responses still generic: lower the MIN_SCORE in `.env` temporarily:
```ini
MIN_SCORE=0.1   # default 0.3 — lower accepts lower-confidence matches
```
Restart rag-api after changing: `docker compose restart rag-api`

### "I don't have information about that" response

The knowledge base may not cover the specific topic. Try:
1. Running `make update` to pull the latest Zscaler documentation
2. Rephrasing with different Zscaler terminology
3. Checking if the topic exists at `help.zscaler.com` directly

### Log paste not triggering log-analysis mode

The auto-detection requires at least 3 newlines AND (a timestamp OR 2+ error keywords).
If your log block is short or format is unusual, prepend:
```
[log analysis]
<paste your logs here>
```

The `[log analysis]` prefix forces log mode regardless of content detection.

### Vision model returns "I cannot see the image"

The model may not support vision. Confirm you selected a vision-capable model:
- `ollama-llama3-2-vision`
- `ollama-llava`
- `ollama-moondream`
- `ollama-qwen2-vl:7b`

Groq and OpenRouter models do not accept image attachments — switch to an Ollama vision model.

---

## Ingest issues

### `scripts/ingest.py` crashes with `AttributeError: 'dict' object has no attribute 'shape'`

This was fixed in commit `383fc46`. Pull the latest code.

### Ingest takes too long / appears hung

bge-m3 embedding on CPU takes ~50 seconds per batch of 32 chunks.
For 13,800 chunks (432 batches), expect ~3.5–4 hours total.

Monitor progress:
```powershell
# Windows PowerShell
Get-Content $env:TEMP\ingest_run.log -Tail 3
```

If the process appears truly hung (no output for > 10 minutes), check memory:
```powershell
Get-Process python | Select-Object Id, WorkingSet
```
If WorkingSet is > 8 GB, the machine may be swapping — close other applications.

### Ingest completes but Qdrant shows fewer chunks than expected

Qdrant's `indexed_vectors_count` is a lagging metric — it only counts segments that
have been fully indexed (HNSW built). `points_count` is authoritative.

```bash
curl -s http://localhost:6333/collections/zscaler_docs | python -m json.tool
# Check both points_count AND indexed_vectors_count
```

The gap closes within a few minutes as Qdrant optimises segments in the background.

### Duplicate chunks in Qdrant

Chunk IDs are deterministic (MD5 hash of URL + section + index). Re-running ingest
is safe — it upserts (overwrites) existing points. Duplicates should not occur.

If you suspect duplicates from an old random-UUID ingest:
```bash
make reset-db   # wipe and re-ingest with deterministic IDs
make ingest
```

---

## Authentication issues

### API call returns `{"detail": "Invalid API key"}`

Check the Authorization header format:
```bash
# Correct
curl -H "Authorization: Bearer zscaler-rag" http://localhost:8000/v1/models

# Wrong — missing "Bearer "
curl -H "Authorization: zscaler-rag" http://localhost:8000/v1/models
```

Also confirm the key matches `API_KEY` in `.env`:
```bash
grep API_KEY .env
```

### Call without Authorization header succeeds (should return 401)

This was the auth bypass bug fixed in Phase 5A (commit `383fc46`). Verify the fix:
```python
# In api/main.py, line ~72:
if not token or token != cfg.API_KEY:   # correct
if token and token != cfg.API_KEY:      # old, broken
```

If you see the old version, pull the latest code and rebuild: `docker compose build rag-api`.

---

## Crawl issues

### crawl_all.py crashes with OOM / Chromium processes accumulate

The old per-page `asyncio.run()` loop leaked Chromium instances. This was fixed in
`scripts/crawl_all.py` — the fix uses a single `asyncio.run(_run_crawl_async(...))` call
with browser restarts every 100 pages.

Confirm you are on the fixed version (commit `383fc46`):
```bash
git log --oneline -5 scripts/crawl_all.py
```

If processes accumulate from a previous run:
```powershell
# Windows — kill all orphan chromium processes
Get-Process chromium -ErrorAction SilentlyContinue | Stop-Process -Force
```

### Crawl returns empty markdown for some pages

Crawl4AI uses a headless Playwright browser. JavaScript-heavy pages may render
an empty body if the JS takes too long. The crawler automatically retries once.

If a specific page consistently fails:
```bash
python -c "
from crawler.crawler import crawl_one_page
import asyncio
asyncio.run(crawl_one_page('https://help.zscaler.com/zia/troubleshooting-ssl-inspection'))
"
```
Check the output for errors.

---

## Config issues

### EMBEDDING_DIM mismatch

```
FAIL  BAAI/bge-m3: model outputs dim=1024 but EMBEDDING_DIM=384 — update config
```

`.env` still has the old MiniLM dimension. Fix:
```ini
EMBEDDING_DIM=1024
```

Then run `make validate-config` to confirm, then `make reset-db && make ingest` to rebuild.

### ALLOWED_ORIGINS wildcard

```
FAIL  ALLOWED_ORIGINS: wildcard '*' — restrict to specific origins
```

Fix in `.env`:
```ini
ALLOWED_ORIGINS=http://localhost:3000
# Or for team deployment:
ALLOWED_ORIGINS=http://your-openwebui-host:3000
```

Restart rag-api: `docker compose restart rag-api`
