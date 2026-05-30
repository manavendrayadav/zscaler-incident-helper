# ADR-001: Use BAAI/bge-m3 as the Default Embedding Model

**Status:** Accepted  
**Date:** 2026-05-28  
**Deciders:** @manavendrayadav

---

## Context

The system requires a text embedding model to convert Zscaler documentation chunks and user queries into vectors for semantic search. The choice of embedding model directly determines retrieval quality for the system's primary use case: finding relevant documentation for specific Zscaler error codes, component names, and troubleshooting steps.

Candidate models were evaluated for:
1. Retrieval quality (MTEB benchmark score)
2. Support for keyword-aware (hybrid) search
3. Memory requirements
4. Inference speed on CPU

---

## Decision

Use `BAAI/bge-m3` as the default embedding model.

**Key specifications:**
- MTEB retrieval score: **64.3** (vs. 56.3 for all-MiniLM-L6-v2)
- Vector dimensions: **1024** (dense)
- Supports **dense + sparse** vectors simultaneously via `FlagEmbedding.BGEM3FlagModel`
- Model size: ~2.7 GB on disk, ~2.5 GB in RAM (FP16)
- CPU inference time for full ingest: ~4 hours (13,800 chunks at batch_size=32)

---

## Consequences

**Positive:**
- Hybrid search (dense + sparse) is uniquely supported by bge-m3 in a single model pass. This is critical for queries containing exact error codes like `AUTH_FAILED`, `TUNNEL_DOWN`, `ZS-1234` where dense-only search often misses exact keyword matches.
- MTEB score 64.3 vs 56.3 is a significant margin for niche technical queries.
- FlagEmbedding provides a clean Python API consistent with sentence-transformers.

**Negative:**
- Initial ingest takes ~4 hours on CPU (vs. ~30 minutes for MiniLM). Mitigated by: embedding cache (`--skip-embed`), one-time cost, GPU cuts to ~30 minutes.
- Model is ~2.7 GB on disk and ~2.5 GB in RAM. Mitigated by: baking into Docker image at build time, acceptable on 8+ GB machines.
- Changing the model requires full re-ingest (`make reset-db && make ingest`).

---

## Alternatives Considered

| Model | MTEB | RAM | Hybrid? | Rejected because |
|-------|------|-----|---------|-----------------|
| `all-MiniLM-L6-v2` | 56.3 | 0.5 GB | No | Lower quality; no sparse support; misses exact error codes |
| `all-mpnet-base-v2` | 57.0 | 0.8 GB | No | Marginal quality improvement over MiniLM; no sparse support |
| `text-embedding-ada-002` (OpenAI) | 60.5 | 0 (API) | No | Requires sending all docs to OpenAI API; privacy concern; ongoing cost |
| `BAAI/bge-large-en-v1.5` | 63.2 | 1.5 GB | No | Slightly lower MTEB than bge-m3; no sparse support |

---

## Configuration

bge-m3 can be swapped for a lighter model by changing `.env`:
```ini
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIM=384
SPARSE_ENABLED=false
```
Requires `make reset-db && make ingest` to rebuild the collection.
