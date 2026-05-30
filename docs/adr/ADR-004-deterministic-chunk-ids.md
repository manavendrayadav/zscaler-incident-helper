# ADR-004: Use Deterministic MD5 Chunk IDs for Idempotent Ingest

**Status:** Accepted  
**Date:** 2026-05-15  
**Deciders:** @manavendrayadav

---

## Context

The knowledge base ingestion pipeline must handle two scenarios safely:

1. **Initial ingest:** Insert all ~13,800 chunks from 1,825 pages.
2. **Incremental update:** Re-ingest a subset of pages that have changed since the last crawl.

The question is how to identify chunks so that re-ingesting doesn't create duplicates.

---

## Decision

Use a **deterministic chunk ID**: `str(uuid.UUID(hashlib.md5(f"{url}|{section}|{idx}".encode()).hexdigest()))`

Where:
- `url` = the source page URL
- `section` = the header breadcrumb path within the document
- `idx` = the sequential chunk index within that section

This produces a UUID-formatted string that is:
- **Deterministic:** Same input always produces the same ID
- **Unique per chunk:** Different (url, section, idx) produce different IDs
- **Stable across re-ingests:** Re-ingesting a page produces the same IDs

The Qdrant upsert operation (insert or update based on ID) means re-running ingest on existing pages overwrites them rather than creating duplicates.

---

## Consequences

**Positive:**
- `make ingest` is **idempotent** — can be run multiple times safely.
- Incremental updates can re-ingest only changed pages without touching others.
- No "delete old chunks" step needed before updating a page — the upsert handles it.
- Old chunks from deleted pages remain in Qdrant until `make reset-db && make ingest`.

**Negative:**
- If a page's structure changes (different sections, different number of chunks), old IDs for the page remain as orphan points in Qdrant until the next full reset. In practice, this is acceptable — Qdrant's retrieval handles extra points gracefully and the wrong chunks would score low.
- Moving a page to a new URL produces new IDs and leaves the old ones orphaned. Requires `make reset-db && make ingest` to clean up.

---

## Alternatives Considered

| Alternative | Rejected because |
|-------------|-----------------|
| Random UUID per ingest run | Simple but creates duplicates on every re-ingest |
| Hash of chunk text | Two identical text chunks from different pages would collide; text-based dedup is incorrect |
| URL-only hash | Multiple chunks per page need distinct IDs |
| Qdrant payload-based dedup (filter before upsert) | Expensive — requires searching before inserting; defeats the upsert optimization |
