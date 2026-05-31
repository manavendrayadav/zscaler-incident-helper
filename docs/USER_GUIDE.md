# User Guide

Everything you need to use the Zscaler RAG Incident Helper effectively — from first-time setup to advanced query patterns. No prior AI or ML knowledge required.

---

## Table of Contents

**Getting Started**
1. [What does this tool do?](#1-what-does-this-tool-do)
2. [The problem it solves](#2-the-problem-it-solves)
3. [What is RAG? (Plain English)](#3-what-is-rag-plain-english)
4. [Key concepts](#4-key-concepts)
5. [Why not just use ChatGPT?](#5-why-not-just-use-chatgpt)
6. [Your first query — a walkthrough](#6-your-first-query--a-walkthrough)
7. [Understanding the response structure](#7-understanding-the-response-structure)

**Privacy**
8. [Which model should I use?](#8-which-model-should-i-use)

**Examples**
9. [Example 1 — ZPA App Connector issue](#9-example-1--zpa-app-connector-issue)
10. [Example 2 — Pasting a log dump](#10-example-2--pasting-a-log-dump)
11. [Example 3 — Product-scoped query](#11-example-3--product-scoped-query)
12. [Example 4 — API call from Python](#12-example-4--api-call-from-python)
13. [Example 5 — Screenshot with Ollama](#13-example-5--screenshot-with-ollama)
14. [Query pattern guide](#14-query-pattern-guide)
15. [What a good response looks like](#15-what-a-good-response-looks-like)

**Limitations**
16. [What the tool cannot do](#16-what-the-tool-cannot-do)

**Reference**
17. [Glossary](#17-glossary)

---

## 1. What does this tool do?

**One sentence:** A self-hosted AI assistant that reads the latest Zscaler documentation before answering your incident questions — giving you grounded, citable answers instead of guesswork.

When you ask "ZPA App Connector shows AUTH_FAILED — what should I check?", the tool:

1. Searches ~13,800 segments of official Zscaler documentation for the most relevant passages
2. Sends those passages to an AI model along with your question
3. Returns a structured resolution with the specific Zscaler settings, commands, and steps that apply — including links to the exact documentation pages used

---

## 2. The problem it solves

During a Zscaler incident, engineers typically:

1. Open a browser and search `help.zscaler.com`
2. Read through 3–5 pages trying to find the relevant information
3. Piece together a resolution from multiple sources
4. Hope the documentation they found isn't outdated

This takes **15–30 minutes per incident**.

This tool crawls the **live Zscaler documentation** on your schedule and grounds every answer in those actual pages. Every response includes the source URLs so you can verify before applying.

---

## 3. What is RAG? (Plain English)

**RAG** stands for **Retrieval-Augmented Generation**. It has three steps:

```
Your question
     │
     ▼
┌─────────────┐     ┌──────────────────────────────────┐
│  RETRIEVE   │────▶│  Find the most relevant pages    │
│             │     │  from 13,800 Zscaler doc chunks  │
└─────────────┘     └──────────────────────────────────┘
     │
     ▼
┌─────────────┐     ┌──────────────────────────────────┐
│  AUGMENT    │────▶│  Combine your question with the  │
│             │     │  retrieved documentation pages   │
└─────────────┘     └──────────────────────────────────┘
     │
     ▼
┌─────────────┐     ┌──────────────────────────────────┐
│  GENERATE   │────▶│  AI writes a structured answer   │
│             │     │  grounded in the retrieved docs  │
└─────────────┘     └──────────────────────────────────┘
     │
     ▼
Structured response with source citations
```

**The open-book exam analogy:** Think of a regular LLM (like ChatGPT) as a student taking a closed-book exam. RAG is the same student taking an open-book exam — they look up the relevant pages before writing the answer. The result is more accurate and verifiable.

**Why vectors instead of keyword search?** Traditional search finds pages containing the exact words you typed. Vector search finds pages with similar *meaning*, even if they use different words. Your query "connector won't authenticate" finds the page "App Connector enrollment certificate validation failure" — same concept, different words.

---

## 4. Key concepts

| Term | Plain English |
|------|---------------|
| **Embedding** | Converting text into a list of ~1,000 numbers that capture its meaning. Similar texts produce similar numbers. |
| **Vector database (Qdrant)** | A search engine that finds similar meaning, not just matching keywords. Holds all 13,800 doc chunks. |
| **Chunk** | A paragraph-sized piece of a documentation page (~500 words). Docs are split into chunks because the AI has a token limit. |
| **Dense search** | Finding chunks with similar overall meaning (semantic search). |
| **Sparse search** | Finding chunks with matching keywords and error codes (keyword search). |
| **Hybrid search** | Combining dense + sparse search. Used by default — better for exact error codes like `AUTH_FAILED`. |
| **Re-ranking** | A second AI pass that scores each (query, chunk) pair more carefully to produce a better shortlist. |
| **LLM** | Large Language Model — the AI that writes the final answer (Groq, Ollama, etc.). |
| **TOP_K** | How many chunks to include in the LLM's context (default: 5). More = richer context but slower. |
| **MIN_SCORE** | Minimum relevance score for a chunk to be included (default: 0.3). Low-relevance chunks are discarded. |

Full definitions with code references: [§17 Glossary](#17-glossary)

---

## 5. Why not just use ChatGPT?

| | ChatGPT | This Tool |
|--|---------|-----------|
| Knowledge cutoff | Training data (months/years old) | As recent as your last `make update` |
| Grounding | None — answers from training data | Every answer cites source Zscaler docs |
| Hallucination risk | High for niche topics | Low — LLM is constrained to retrieved docs |
| Internal log privacy | Your logs go to OpenAI | Ollama mode: nothing leaves your machine |
| Cost per query | ~$0.01–0.10 (GPT-4) | $0.00 (Groq free tier) or local Ollama |
| ZPA/ZIA specificity | General knowledge | 1,825 Zscaler documentation pages |
| Verifiable | No source links | Every response includes source URLs |

**When ChatGPT is still better:** creative writing, non-Zscaler documents, questions requiring your specific tenant configuration.

---

## 6. Your first query — a walkthrough

**Open the chat interface:** http://localhost:3000

Register an account (first user becomes admin), select a model, then try:

```
ZPA App Connector shows TUNNEL_DOWN. What are the most common causes and how do I fix it?
```

What happens behind the scenes:
1. Your query is converted to a 1,024-number vector (embedding)
2. Qdrant searches ~13,800 chunk vectors for the most similar ones
3. A cross-encoder model re-ranks the top 20 by relevance
4. The top 5 chunks (scoring above 0.3) are assembled into a prompt
5. The LLM generates a response grounded in those chunks
6. The response appears with source links at the bottom

**Expected response time:** 3–8 seconds with Groq.

---

## 7. Understanding the response structure

Every response follows this structure:

```markdown
## Root Cause Analysis
What caused the issue, based on the retrieved docs.

## Step-by-Step Resolution
1. First action (specific Zscaler admin portal path or CLI command)
2. Second action...

## Verification Steps
How to confirm the fix worked.

## Prevention Tips
Configuration changes to prevent recurrence.

## References
- https://help.zscaler.com/zpa/troubleshooting-app-connectors
```

> **Important:** Always verify recommended steps against your specific Zscaler configuration before applying. The tool reads public documentation; it cannot access your tenant settings.

**If the response seems wrong or generic:**

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Very short or vague | Knowledge base still indexing | Check `make doctor` for chunk count (~13,800 when complete) |
| Wrong product context | Ambiguous query | Add `[product:zpa]` prefix |
| "I don't have information" | Topic not in KB | Run `make update` to pull latest docs |
| Ignores your log details | Log mode not triggered | Paste 3+ log lines with timestamps |

---

## 8. Which model should I use?

**This is the most important section if you handle sensitive data.**

When you select a model, your query text is sent to that model's provider.

### Groq (`zih/groq-*`)
- ✅ Use for: General Zscaler questions with no internal data
- ✅ Fast (~3–8 seconds), free tier
- ❌ **Never use for:** Internal log output, employee names, system identifiers
- 📍 Data goes to: Groq's US-based servers

### OpenRouter (`zih/openrouter-*`)
- ✅ Use for: General questions when you need a specific model not on Groq
- ❌ **Never use for:** Internal data
- ⚠️ Some models route to non-US providers — check the specific model

### Ollama (`zih/ollama-*`)
- ✅ **100% private** — runs on your machine, zero data leaves your network
- ✅ Use for: Everything, especially internal logs and screenshots
- ❌ Slower (~60–180s on CPU, ~5–15s with GPU)
- 📍 Data goes to: Nowhere — fully local

### Decision guide

```
Is the query content sensitive?
(contains log output, IP addresses, system names, employee data)
    │
    ├─ YES → Use Ollama:  make ollama-setup
    │         Select: zih/ollama-llama3-2
    │
    └─ NO  → Use Groq:
              Select: zih/groq-llama-3-3-70b-versatile
```

**For screenshots:** Always use an Ollama vision model (`make ollama-vision`, then select `zih/ollama-qwen2-vl:7b`).

---

## 9. Example 1 — ZPA App Connector issue

**Mode:** Doc search | **Model:** Groq | **Privacy:** Safe (no internal data)

### Query
```
ZPA App Connector shows CONNECTOR_DOWN in the admin portal. The connector was working
yesterday. What are the most likely causes and resolution steps?
```

### What happens internally
1. Query embedded into 1,024-dim vector
2. Qdrant hybrid search finds 20 most relevant ZPA troubleshooting chunks
3. Cross-encoder re-ranks by CONNECTOR_DOWN relevance
4. Top 5 chunks above MIN_SCORE=0.3 sent to LLM
5. Response generated in ~4 seconds

### Sample response (truncated)
```markdown
## Root Cause Analysis
CONNECTOR_DOWN typically indicates the App Connector has lost its connection to the
Zscaler Private Access broker. Common causes include:

1. **Network connectivity issues** — Host cannot reach *.zscalerone.net or *.zscaler.net
2. **Expired enrollment certificate** — Check expiry in Administration > Connectors
3. **Firewall blocking outbound traffic** — ZPA requires TCP 443; UDP 9000 for Z-Tunnel 2.0
4. **Resource exhaustion** — High CPU or memory on the connector host

## Step-by-Step Resolution
1. Check connector logs: `sudo journalctl -u zscaler-connector --since "1 hour ago"`
2. Test outbound: `curl -v https://gateway.zscalerone.net`
3. Check certificate expiry in the Admin Portal

## References
- https://help.zscaler.com/zpa/troubleshooting-app-connectors
```

---

## 10. Example 2 — Pasting a log dump

**Mode:** Log analysis (auto-detected) | **Model:** Ollama | **Privacy:** Use Ollama for real logs

### Query — paste directly into chat
```
2026-05-28T10:00:00Z ERROR connector=prod-dc1 reason=AUTH_FAILED tunnel_id=abc123
2026-05-28T10:00:01Z WARN  broker=us-west-1 status=UNREACHABLE retries=3
2026-05-28T10:00:05Z ERROR connector=prod-dc1 reason=CERT_ERROR cert_subject=*.internal.corp
2026-05-28T10:00:10Z FATAL tunnel=T-4421 state=TUNNEL_DOWN duration=320s
```

### What happens internally
1. System detects timestamps + error keywords → switches to **log-analysis mode**
2. Drain3 extracts signals: `AUTH_FAILED`, `CERT_ERROR`, `TUNNEL_DOWN`, `connector`, `broker`
3. Signals used as Qdrant search query
4. Product auto-detected as `zpa` (connector + broker + tunnel keywords)
5. LLM prompted for "Identified Events + Root Cause + Resolution"

### Sample response (truncated)
```markdown
## Identified Events
| Timestamp | Severity | Event | Details |
|-----------|----------|-------|---------|
| 10:00:00Z | ERROR | Auth failure | connector=prod-dc1 |
| 10:00:05Z | ERROR | Certificate error | *.internal.corp (internal CA) |
| 10:00:10Z | FATAL | Tunnel down | T-4421 for 320s |

## Root Cause
CERT_ERROR for *.internal.corp → App Connector not trusting your internal CA →
AUTH_FAILED → broker UNREACHABLE → TUNNEL_DOWN

## Step-by-Step Resolution
1. Export internal root CA certificate (PEM format)
2. Add CA cert to the App Connector's trusted store
   ...
## References
- https://help.zscaler.com/zpa/configuring-custom-certificate-authority
```

> **Note:** Prefix your message with `[log analysis]` to force log mode if auto-detection doesn't trigger.

---

## 11. Example 3 — Product-scoped query

### Without product filter (may mix results)
```
SSL inspection causing authentication failures
```

### With product filter (better precision)
```
[product:zia] SSL inspection causing SAML authentication failures for Okta users
```

**What the prefix does:** Restricts Qdrant retrieval to chunks tagged `product=zia`. Prevents ZPA and ZDX content from diluting results.

**Equivalent via API:**
```json
{
  "model": "zih/groq-llama-3-3-70b-versatile",
  "messages": [{"role": "user", "content": "SSL inspection causing SAML auth failures"}],
  "product_filter": "zia"
}
```

**Valid values:** `zia`, `zpa`, `zdx`, `deception`

---

## 12. Example 4 — API call from Python

### Using `openai` SDK (recommended)
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="zscaler-rag",
)

response = client.chat.completions.create(
    model="zih/groq-llama-3-3-70b-versatile",
    messages=[{"role": "user", "content": "ZPA App Connector AUTH_FAILED causes?"}],
    temperature=0.3,
    extra_body={"top_k": 5, "product_filter": "zpa"}
)
print(response.choices[0].message.content)
```

### Using `requests`
```python
import requests
response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    headers={"Authorization": "Bearer zih-api"},
    json={"model": "zih/groq-llama-3-3-70b-versatile",
          "messages": [{"role": "user", "content": "ZIA SSL bypass for M365?"}],
          "top_k": 5},
    timeout=30
)
print(response.json()["choices"][0]["message"]["content"])
```

### cURL
```bash
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer zih-api" \
  -H "Content-Type: application/json" \
  -d '{"model":"zih/groq-llama-3-3-70b-versatile",
       "messages":[{"role":"user","content":"ZIA PAC file for split tunneling"}],
       "top_k":5}' | python -m json.tool
```

For complete API documentation (all endpoints, error codes, vision format): see [DEVELOPER_GUIDE.md — §5 API Reference](DEVELOPER_GUIDE.md#5-api-reference).

---

## 13. Example 5 — Screenshot with Ollama

**Prerequisite:** `make ollama-vision` (pulls qwen2-vl:7b, llava, moondream)

1. Select model: `zih/ollama-qwen2-vl:7b`
2. Click the **paperclip** icon
3. Attach your screenshot
4. Ask: "What error is shown and what does it mean?"

The vision model reads text from the screenshot, the RAG system retrieves relevant documentation, and the response correlates both.

> **Privacy:** The screenshot never leaves your machine when using Ollama.

---

## 14. Query pattern guide

### Works well
| Pattern | Example | Why |
|---------|---------|-----|
| Exact error code | `AUTH_FAILED connector error` | Hybrid search finds exact match via sparse vectors |
| Product + component | `ZPA App Connector enrollment fails` | Product keywords improve precision |
| Symptom description | `TUNNEL_DOWN after 5 minutes` | Semantic search finds related concepts |
| Product-scoped | `[product:zia] SSL bypass for Zoom` | Eliminates irrelevant product chunks |
| Context included | `Using GRE tunnel, traffic forwarding to ZIA` | More context = better chunk matching |

### Works less well
| Pattern | Problem | Fix |
|---------|---------|-----|
| `connector not working` | Too vague | Specify: `ZPA App Connector` |
| Pasting 500 log lines | Drain3 extracts ≤15 signals | Paste only the 5–10 most recent error lines |
| `ZIA and ZPA both have issues` | Diluted retrieval | Ask as two separate product-scoped queries |
| Feature announced last week | May not be in KB | Run `make update` then retry |

---

## 15. What a good response looks like

✅ References specific Zscaler menu paths — "Navigate to Administration > App Connectors > Certificates"
✅ Includes exact CLI commands — `sudo systemctl restart zscaler-connector`
✅ Lists numbered steps — actionable, not vague
✅ Cites 2–5 source URLs — from `help.zscaler.com`
✅ Acknowledges uncertainty — "This depends on your specific tunnel type"

❌ Very short and generic ("Check the logs and contact Zscaler support")
❌ No source URLs
❌ Wrong product context
❌ Steps requiring tenant configuration access

**If you get a low-quality response:**
1. `make doctor` — verify ~13,800 chunks in Qdrant
2. Add product prefix: `[product:zpa]`
3. Include the exact error code
4. `make update` if the issue may be recent
5. Rephrase using Zscaler's own terminology

---

## 16. What the tool cannot do

- **No access to your Zscaler tenant.** Reads public documentation only.
- **Knowledge cutoff.** Run `make update` weekly to stay current.
- **The AI can be wrong.** Always verify before applying configuration changes.
- **Complex multi-product issues.** Ask separate product-scoped questions.
- **No incident ticketing.** Answers questions; does not integrate with ITSM platforms.

---

## 17. Glossary

Alphabetical reference for every technical term. If a term isn't here, open a [GitHub Issue](https://github.com/manavendrayadav/zscaler-incident-helper/issues).

---

**BAAI/bge-m3** — An open-source text embedding model by the Beijing Academy of AI. "bge-m3" = Multi-lingual, Multi-functionality, Multi-granularity. The default embedding model: supports dense + sparse vectors simultaneously (MTEB score: 64.3), significantly better than lighter models for exact error codes and Zscaler terminology.
*Where it appears:* `config.py` (`EMBEDDING_MODEL`), `pipeline/embedder.py`

**Bearer token** — HTTP authentication credential: `Authorization: Bearer <key>`. The "Bearer" prefix is required. Default token is `zscaler-rag`; change before team deployment.
*Where it appears:* `api/main.py`, all `/v1/*` endpoints

---

**Chunk** — A paragraph-sized segment of a Zscaler documentation page (~1,500 characters / ~500 tokens). Basic retrieval unit stored in Qdrant. The system holds ~13,800 chunks from 1,825 pages.
*Where it appears:* `pipeline/chunker.py`, `config.py` (`CHUNK_SIZE`, `CHUNK_OVERLAP`)

**Chunk ID** — Deterministic identifier: MD5 hash of `url|section|chunk_index`. Re-ingesting the same page always produces the same IDs, enabling safe upsert (no duplicates).
*Where it appears:* `pipeline/chunker.py`

**Chunk overlap** — Characters shared between consecutive chunks (default: 150 of 1,500 = 10%). Prevents context loss at chunk boundaries.
*Where it appears:* `config.py` (`CHUNK_OVERLAP=150`)

**Collection** — Qdrant's equivalent of a database table. `zscaler_docs` holds all ~13,800 embeddings with metadata.
*Where it appears:* `pipeline/indexer.py`, `config.py` (`COLLECTION_NAME`)

**Context window** — Maximum tokens an LLM can process per request. Groq's llama-3.3-70b has a 128k token window.

**Cosine similarity** — Similarity measure between two vectors (0 = different, 1 = identical). Chunks above `MIN_SCORE` (default 0.3) are considered relevant.
*Where it appears:* `pipeline/indexer.py` (`Distance.COSINE`)

**Cross-encoder (re-ranker)** — Neural network that scores (query, document) pairs for re-ranking. Model: `cross-encoder/ms-marco-MiniLM-L-6-v2` (~90 MB). More accurate than vector similarity but slower.
*Where it appears:* `rag/retriever.py`, baked into Docker image

---

**Dense vector** — A list of 1,024 floats representing semantic meaning. Texts with similar meaning have close vectors. Generated by bge-m3.
*Contrast with:* Sparse vector
*Where it appears:* `pipeline/embedder.py`, Qdrant `"dense"` index

**Docker profile** — Docker Compose feature for optional services. Ollama has profile `local-llm` — starts only with `--profile local-llm`. Keeps default `make up` fast.
*Where it appears:* `docker-compose.yml`

**Drain3** — Python library for mining log templates. Clusters log lines by template (e.g., `ERROR connector=<*> reason=<*>`) and extracts structured parameters. Used in log-analysis mode.
*Where it appears:* `rag/log_parser.py`, `requirements.txt`

---

**Embedding** — Converting text into a dense vector. The resulting vector captures semantic meaning, enabling similarity search without keyword matching.
*Where it appears:* `pipeline/embedder.py`

**Embedding cache** — Binary file (`data/embeddings_cache.npz`) saving computed embeddings after the 4-hour bge-m3 computation. Allows resuming with `python scripts/ingest.py --skip-embed` if upsert fails.
*Where it appears:* `scripts/ingest.py`

---

**Hybrid search** — Retrieval combining dense semantic search + sparse keyword search, merged via RRF. Better than either alone: dense finds conceptual matches, sparse finds exact error codes.
*Where it appears:* `rag/retriever.py` (`_search_hybrid`)

---

**Ingest** — Full pipeline: load `.md` files → chunk → embed with bge-m3 → upsert to Qdrant → update manifest. Run with `make ingest`.
*Where it appears:* `scripts/ingest.py`

---

**LLM (Large Language Model)** — AI that generates text responses. In this project: the final step that receives query + retrieved chunks and writes the structured answer.
*Providers:* Groq, OpenRouter, Ollama

**Log analysis mode** — Automatic mode triggered by multi-line text with timestamps + error keywords. Uses Drain3 to extract signals and prompts for "Identified Events + Root Cause + Resolution."
*Where it appears:* `api/main.py`, `rag/log_parser.py`

---

**Manifest file** (`data/crawl_manifest.json`) — JSON tracking crawl state per URL: last crawl timestamp, sitemap lastmod, Qdrant chunk IDs. Gitignored; regenerated by fresh crawl.

**MIN_SCORE** — Minimum cosine score (0–1) for a chunk to be included (default: 0.3). Lower = broader recall; higher = stricter precision.
*Where it appears:* `config.py`, `rag/retriever.py`

---

**Ollama** — Open-source local LLM runtime. Nothing leaves your machine. Required for internal logs, screenshots, or sensitive data.
*Where it appears:* `llm/ollama_provider.py`, `docker-compose.yml` (profile: `local-llm`)

**OpenAI-compatible API** — HTTP API matching OpenAI's `POST /v1/chat/completions` format. Means any OpenAI client (OpenWebUI, SDK, curl) connects without modification.
*Where it appears:* `api/main.py`

---

**Product filter** — Optional `product_filter` API parameter restricting retrieval to one product. Values: `zia`, `zpa`, `zdx`, `deception`. Also set via `[product:zpa]` prefix.
*Where it appears:* `api/models.py`, `rag/retriever.py`

---

**Qdrant** — Open-source vector database written in Rust. Stores ~13,800 chunk embeddings. HTTP on port 6333, gRPC on port 6334.
*Homepage:* https://qdrant.tech
*Where it appears:* `docker-compose.yml`, `pipeline/indexer.py`, `rag/retriever.py`

---

**RAG (Retrieval-Augmented Generation)** — Retrieves relevant documents before generating an answer, grounding the response in actual documentation and reducing hallucination.
*Analogy:* Open-book exam — the AI reads the relevant pages before answering.

**Re-ranking** — Second-pass scoring using cross-encoder model. Fetches top-20 from Qdrant, scores each (query, chunk) pair, returns top-K above MIN_SCORE.
*Where it appears:* `rag/retriever.py` (`_get_reranker`)

**RRF (Reciprocal Rank Fusion)** — Merges dense + sparse ranked lists: score = Σ `1/(k + rank)`. Handles different score scales gracefully.
*Where it appears:* `rag/retriever.py` (`FusionQuery(fusion=Fusion.RRF)`)

---

**Sentence-transformers** — Python library for text embeddings. Used for dense-only mode and for the CrossEncoder re-ranker.
*Where it appears:* `pipeline/embedder.py`, `rag/retriever.py`

**Sparse vector** — Dict of `{token_id: weight}` for BM25-style keyword matching. Captures exact error codes and product names. Combined with dense vectors in hybrid search.
*Contrast with:* Dense vector
*Where it appears:* `pipeline/embedder.py`, Qdrant `"sparse"` index

---

**TOP_K** — Number of chunks retrieved per query (default: 5). More = richer context but slower; risk of noise at high values.
*Where it appears:* `config.py`, API field `top_k`

**Token** — Basic LLM text unit (~0.75 words / 4 characters). A 1,500-char chunk ≈ 375–500 tokens. `max_tokens=2048` limits response length.

---

**Upsert** — Insert if new, update if exists (by chunk ID). Re-ingesting a page overwrites without duplicating.
*Where it appears:* `pipeline/indexer.py`

---

**Vector** — List of numbers representing text. Dense = 1,024 floats; sparse = token→weight dict. Mathematically close vectors = semantically similar text.

**Vector database** — Database optimised for similarity search rather than exact value matching. Qdrant is the vector database used in this project.

---

**ZCC (Zscaler Client Connector)** — Endpoint agent installed on user devices. Routes traffic through Zscaler's cloud. Source of log data for incident investigation.

**ZDX (Zscaler Digital Experience)** — Digital experience monitoring: latency, packet loss, experience scores.

**ZIA (Zscaler Internet Access)** — Secure web gateway: SSL inspection, policy enforcement, threat prevention.

**ZPA (Zscaler Private Access)** — Zero-trust network access: secure access to internal apps without VPN. Uses App Connectors and Brokers.
