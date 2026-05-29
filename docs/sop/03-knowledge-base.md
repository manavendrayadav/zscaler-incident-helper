# SOP-03 — Knowledge Base Management

**Audience:** Maintainer responsible for keeping the knowledge base current.
**When:** Weekly check; after Zscaler releases major documentation updates; after changing the embedding model.

---

## Overview

The knowledge base is built from Zscaler's public help site (`help.zscaler.com`). The pipeline is:

```
Zscaler Sitemap → Crawl4AI → data/raw/*.md → Chunker → bge-m3 embedder → Qdrant
```

State is tracked in `data/crawl_manifest.json` — a per-URL record of last crawl time,
sitemap lastmod date, and which Qdrant chunk IDs belong to each page.

---

## 1. Check current state

```bash
make doctor
```

Look at the Knowledge Base panel:

```
Pages crawled : 1825   ZIA: 841  ZDX: 133  ZPA: 530  ...
Pages indexed : 1825
Pages stale   : 0
```

- **Pages stale > 0** — sitemap shows newer content than what was crawled; run `make update`
- **Pages indexed < Pages crawled** — some pages were crawled but not ingested; run `make ingest`
- **Raw .md files mismatch** — a file exists on disk without a manifest entry (benign, can add manually)

---

## 2. Incremental update (weekly routine)

Crawls only pages whose `sitemap_lastmod` is newer than `last_crawled` in the manifest.
Much faster than a full crawl (usually 0–50 pages).

```bash
make update     # crawl changed pages only
make ingest     # re-embed changed pages and update Qdrant
```

The ingest is idempotent — deterministic chunk IDs (MD5 of `url|section|idx`) mean
re-indexing a page simply overwrites its existing Qdrant points, no duplicates.

---

## 3. Full crawl (initial setup or after reset)

```bash
make crawl-all
```

Crawls all ~1,825 pages from the Zscaler sitemap. Runs in a single asyncio event loop
with a browser restart every 100 pages to prevent memory leaks. Includes auto-ingest.

Expected runtime: 2–4 hours total (crawl ≈ 30–60 min, embedding ≈ 3–4 hours on CPU).

To run crawl and ingest separately (e.g. to inspect raw files before indexing):

```bash
python scripts/crawl_all.py --no-ingest   # crawl only
make ingest                                # then ingest separately
```

---

## 4. Wipe and re-index from scratch

Do this when:
- The embedding model changes (e.g. switching from MiniLM to bge-m3)
- Qdrant collection becomes corrupted
- A large batch of pages needs to be replaced cleanly

```bash
make reset-db   # wipes the qdrant_storage Docker volume
make ingest     # re-embeds all data/raw/*.md files
```

Warning: `make reset-db` is destructive — it runs `docker-compose down -v` which
removes the Qdrant volume. The raw `.md` files in `data/raw/` are preserved
(they are a bind mount, not a Docker volume).

---

## 5. Embedding model change

If you change `EMBEDDING_MODEL` or `EMBEDDING_DIM` in `.env`, you must rebuild the collection:

```bash
# 1. Update .env
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIM=1024
SPARSE_ENABLED=true

# 2. Validate
make validate-config

# 3. Wipe old collection and re-ingest (uses new model automatically)
make reset-db
make ingest
```

The current model is `BAAI/bge-m3` (1024-dim, hybrid dense+sparse, MTEB 64.3).
Downgrading to `all-MiniLM-L6-v2` (384-dim) is possible but will reduce retrieval
quality for exact error-code queries (e.g. AUTH_FAILED, TUNNEL_DOWN).

---

## 6. Chunk IDs and deduplication

Chunk IDs are deterministic: `MD5(url + "|" + section_header + "|" + chunk_index)`.

This means:
- Re-ingesting a page replaces its existing Qdrant points via upsert — no duplicates
- Moving or renaming a page produces new IDs and leaves the old ones orphaned
- Orphaned chunks should be cleaned up with `make reset-db` + `make ingest`

---

## 7. Product tagging

Each chunk carries a `product` metadata field (`zia`, `zpa`, `zdx`, `deception`, or `unknown`)
inferred from the URL path. This enables product-scoped filtering in queries.

Current distribution (as of last full crawl):

| Product | Pages | Chunks |
|---------|-------|--------|
| ZIA | ~841 | ~6,500 |
| ZPA | ~530 | ~4,100 |
| ZDX | ~133 | ~1,000 |
| DECEPTION | ~321 | ~2,200 |

To query with a product filter in OpenWebUI, prefix the message:
> `[product:zpa] App Connector showing TUNNEL_DOWN`

Or use the API directly:

```json
{
  "model": "zscaler-rag/groq-llama-3-3-70b-versatile",
  "messages": [{"role": "user", "content": "App Connector TUNNEL_DOWN"}],
  "product_filter": "zpa"
}
```

---

## 8. Manifest file

`data/crawl_manifest.json` is gitignored (it contains crawl timestamps and Qdrant IDs that
change every run). It lives on disk and persists across Docker restarts because `data/` is
a bind mount.

If the manifest is lost (e.g. machine wipe), run `make crawl-all` to rebuild it from scratch.
