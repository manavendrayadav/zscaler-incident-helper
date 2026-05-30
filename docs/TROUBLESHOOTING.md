# Troubleshooting Guide

**Always run `make doctor` first** — it identifies 80% of issues instantly with a single command.

```bash
make doctor
```

---

## Table of Contents

1. [Docker and service issues](#1-docker-and-service-issues)
2. [Query and retrieval issues](#2-query-and-retrieval-issues)
3. [Authentication issues](#3-authentication-issues)
4. [Ingest issues](#4-ingest-issues)
5. [Crawl issues](#5-crawl-issues)
6. [Configuration issues](#6-configuration-issues)
7. [Windows-specific issues](#7-windows-specific-issues)
8. [Corporate proxy / Zscaler ZCC interference](#8-corporate-proxy--zscaler-zcc-interference)

---

## 1. Docker and service issues

### rag-api shows FAIL or unhealthy

**Symptoms:** `make doctor` shows rag-api as FAIL or DEGRADED.

**Step 1 — Check logs:**
```bash
make logs
# Watch for: "Application startup complete."
```

**Step 2 — If startup complete never appears after 2 minutes:**
```bash
docker compose logs rag-api --tail=50
```

Look for these specific errors:

| Error message | Cause | Fix |
|---------------|-------|-----|
| `ModuleNotFoundError: No module named 'FlagEmbedding'` | Stale Docker image | `docker compose build rag-api && docker compose up -d rag-api` |
| `ConnectionRefusedError` connecting to Qdrant | Qdrant not ready yet | Wait 30s, then `docker compose restart rag-api` |
| `AssertionError` or `SIGBUS` in worker | PyTorch fork issue (old image) | Ensure `--workers` flag is NOT in CMD: `docker compose exec rag-api cat /proc/1/cmdline` |
| Python traceback | Code/config error | Read the full traceback; check `make validate-config` |

---

### Qdrant health endpoint shows [404]

**Symptom:** `make doctor` shows Qdrant HTTP as `[404]`.

**This is normal and expected.** Qdrant's `/health` HTTP endpoint returns 404 (it uses gRPC health protocol). The container status column in `make doctor` is what matters.

Confirm Qdrant is healthy via the dashboard:
```
http://localhost:6333/dashboard
```

---

### crawl4ai shows WARN

**Symptom:** `make doctor` shows crawl4ai as WARN.

Crawl4AI takes 30–60 seconds to initialise Playwright on container start.

```bash
# Wait 60s after `make up`, then re-run
make doctor

# If still failing:
make logs-crawl4ai
docker compose restart crawl4ai
```

---

### OpenWebUI shows "connection refused" or blank page

**Symptom:** Browser at http://localhost:3000 shows connection refused or blank.

**Check:** OpenWebUI depends on rag-api being healthy. rag-api depends on Qdrant.

```bash
make doctor          # check all service statuses
make logs            # wait for "Application startup complete."
```

**If rag-api is healthy but OpenWebUI still fails:**
```bash
docker exec zscaler-openwebui env | grep OPENAI
# Expected: OPENAI_API_BASE_URL=http://rag-api:8000/v1
```

If the URL is wrong or missing, check `docker-compose.yml` and restart:
```bash
docker compose up -d openwebui
```

---

### Container restarts in a loop

**Symptom:** `docker ps` shows a container restarting repeatedly.

```bash
docker inspect <container-name> --format "{{.State.ExitCode}} {{.State.OOMKilled}}"
```

| Exit code | OOMKilled | Cause |
|-----------|-----------|-------|
| 0 | false | Process exited cleanly (uvicorn bug, see PyTorch fix) |
| 137 | true | Out of memory — increase Docker Desktop RAM |
| 1 | false | Application error — check logs |

For OOM: increase Docker Desktop memory limit (Settings → Resources → Memory).

---

## 2. Query and retrieval issues

### Responses are generic or not Zscaler-specific

**Symptom:** Responses read like generic ChatGPT advice, not specific to Zscaler.

**Step 1 — Check chunk count:**
```bash
curl -s http://localhost:6333/collections/zscaler_docs | python -m json.tool | grep points_count
```

If `0`: run `make ingest`. If crawl hasn't run yet: `make crawl-all`.

**Step 2 — If chunks > 0 but still generic:**

Lower `MIN_SCORE` temporarily:
```ini
# .env
MIN_SCORE=0.1   # default 0.3
```
```bash
docker compose restart rag-api
```

**Step 3 — Improve query specificity:**
- Add product prefix: `[product:zpa] your query`
- Include the exact error code: `AUTH_FAILED`, `TUNNEL_DOWN`
- Use Zscaler's own terminology (check help.zscaler.com for exact terms)

---

### "I don't have information about that" response

**Causes:**
1. Knowledge base doesn't cover the topic
2. `MIN_SCORE` is too high (no chunks pass the threshold)
3. Knowledge base is stale (topic was added after your last crawl)

**Fixes:**
```bash
make update   # pull new/changed pages
make ingest   # re-index
```

---

### Log paste not triggering log-analysis mode

**Symptom:** You paste log lines but the response treats it as a general question.

Auto-detection requires:
- ≥3 newlines in the text, AND
- At least one timestamp (ISO, syslog, or MM/DD/YYYY format) OR 2+ error keywords

**Fix:** Prefix your message with `[log analysis]` to force the mode:
```
[log analysis]
2026-05-28T10:00:00Z ERROR connector=prod-dc1 reason=AUTH_FAILED
...
```

---

### Vision model returns "I cannot see the image" or ignores screenshot

**Symptom:** Ollama vision model doesn't describe the image content.

**Check:** Only these models support vision input:
- `ollama-llama3-2-vision`
- `ollama-llava`
- `ollama-moondream`
- `ollama-qwen2-vl:7b`

Groq and OpenRouter models do not accept image attachments. Switch to an Ollama vision model.

**Check Ollama is running:**
```bash
make doctor   # Ollama row should show running + models pulled
```

---

### Response quality drops after update

**Symptom:** Answers were better before running `make update && make ingest`.

This can happen if the updated Zscaler documentation pages have changed structure. The deterministic chunk IDs ensure no duplication, but new page layouts may produce different chunks.

**Investigate:** Run `make doctor` to confirm chunk count is consistent (~13,800). If significantly different (±500), the sitemap structure may have changed — review `data/raw/` sample files.

---

## 3. Authentication issues

### API call returns `{"detail": "Invalid API key"}`

**Step 1 — Check header format:**
```bash
# Correct
curl -H "Authorization: Bearer zscaler-rag" http://localhost:8000/v1/models

# Wrong — missing "Bearer " prefix
curl -H "Authorization: zscaler-rag" http://localhost:8000/v1/models
```

**Step 2 — Confirm the key:**
```bash
grep API_KEY .env
# Must match the key you're using in the Authorization header
```

**Step 3 — Restart if you changed `API_KEY` in `.env`:**
```bash
docker compose restart rag-api
```

---

### OpenWebUI says "Invalid API Key" after changing the key

When you change `API_KEY` in `.env`, you must also update the key in `docker-compose.yml`:

```yaml
openwebui:
  environment:
    - OPENAI_API_KEY=your_new_key   # ← must match API_KEY in .env
```

Then restart both:
```bash
docker compose up -d rag-api openwebui
```

---

## 4. Ingest issues

### Ingest crashes with `ReadTimeout`

**Symptom:** `scripts/ingest.py` fails with `httpcore.ReadTimeout` during Step 3/3 (Upserting into Qdrant).

**Cause:** Default Qdrant client timeout (5s) is too short for large batch upserts.

**Fix:** The indexer now uses `timeout=120`. Ensure you're on the latest version:
```bash
git pull
python scripts/ingest.py
```

If still timing out, verify Qdrant is healthy:
```bash
curl http://localhost:6333/collections/zscaler_docs
```

---

### Ingest takes too long / appears stuck

bge-m3 on CPU takes ~50 seconds per batch of 32 chunks. For 13,800 chunks (432 batches), expect **3.5–4 hours total**. This is expected and normal.

Monitor real progress:
```powershell
# Windows PowerShell
Get-Content $env:TEMP\ingest_run.log -Tail 3
```

**If truly stuck (no output for >10 minutes):**
```powershell
# Check memory usage
Get-Process python | Select-Object Id, WorkingSet
```

If WorkingSet > 8 GB, the machine is swapping. Close other applications.

---

### Ingest crashed mid-way after Step 2 (embedding) completed

If the process was killed after embeddings were computed but before Qdrant upsert, the embeddings are saved in `data/embeddings_cache.npz`. Skip the 4-hour computation:

```bash
python scripts/ingest.py --skip-embed
```

---

### Qdrant shows fewer chunks than expected after ingest

`indexed_vectors_count` is a **lagging metric** — it only counts fully-optimised segments. `points_count` is authoritative.

```bash
curl -s http://localhost:6333/collections/zscaler_docs | python -m json.tool
```

Check `points_count`, not `indexed_vectors_count`. The gap closes within a few minutes as Qdrant builds HNSW indexes in the background.

---

## 5. Crawl issues

### Crawl4AI takes too long or hangs

Crawl4AI processes 3 pages concurrently by default. Normal rate: ~8–10 seconds per page. For 1,825 pages: **60–90 minutes**.

If it appears hung (no progress for >5 minutes):
```bash
make logs-crawl4ai
docker compose restart crawl4ai
# Then resume: python scripts/crawl_all.py  (skips already-crawled pages via manifest)
```

---

### Chromium processes accumulate (OOM during crawl)

**Symptom:** Memory usage grows steadily; system becomes unresponsive.

This was fixed in `scripts/crawl_all.py` — the fix runs a single asyncio event loop with browser restarts every 100 pages.

Confirm you're on the fixed version:
```bash
git log --oneline -3 scripts/crawl_all.py
```

If old processes remain from a previous run:
```powershell
# Windows — kill orphan chromium processes
Get-Process chromium -ErrorAction SilentlyContinue | Stop-Process -Force
```

---

### Crawl returns empty Markdown for some pages

Some Zscaler pages are JavaScript-heavy and may render empty on slow connections. The crawler retries once automatically.

Test a specific URL:
```bash
python -c "
from crawler.crawler import crawl_one_page
import asyncio
asyncio.run(crawl_one_page('https://help.zscaler.com/zia/troubleshooting-ssl-inspection'))
"
```

---

## 6. Configuration issues

### `EMBEDDING_DIM mismatch`

```
FAIL  BAAI/bge-m3: model outputs dim=1024 but EMBEDDING_DIM=384
```

`.env` still has `EMBEDDING_DIM=384` (MiniLM value). Fix:
```ini
EMBEDDING_DIM=1024
```
Then: `make validate-config` to confirm, then `make reset-db && make ingest` to rebuild.

---

### `ALLOWED_ORIGINS wildcard`

```
FAIL  ALLOWED_ORIGINS: wildcard '*' — restrict to specific origins
```

Fix:
```ini
ALLOWED_ORIGINS=http://localhost:3000
```
Then: `docker compose restart rag-api`

---

## 7. Windows-specific issues

### Docker Desktop uses too much memory

```
# %USERPROFILE%\.wslconfig
[wsl2]
memory=12GB
```

Restart Docker Desktop after saving.

### Port already in use

If another service is using port 3000 or 8000:
```powershell
# Find what's using a port
netstat -ano | findstr :3000
```

Either stop the conflicting service or change the port in `docker-compose.yml`.

---

## 8. Corporate proxy / Zscaler ZCC interference

**Symptom:** Docker containers can't reach external APIs (Groq, HuggingFace). You see HTML error pages in responses (Zscaler block page content).

**Cause:** Zscaler Client Connector on your host machine intercepts HTTPS from Docker containers. The container doesn't trust the Zscaler root CA, so SSL inspection breaks the connection.

**Option 1 — Use Ollama only (recommended for privacy)**
```bash
make ollama-setup
```
No external calls; immune to ZCC interference.

**Option 2 — Add Zscaler root CA to Docker image**

Export the Zscaler CA cert from the Windows certificate store and inject it at build time. See [SECURITY.md](../SECURITY.md) for guidance.

**Option 3 — Add bypass rule in Zscaler**

If you have ZIA admin access, add `api.groq.com` to the SSL inspection bypass list. Contact your Zscaler administrator.
