# Roadmap

Planned features and improvements. Listed versions are targets, not commitments.

Community input welcome — open a [GitHub Discussion](https://github.com/manavendrayadav/zscaler-rag/discussions) to propose features or vote on priorities.

---

## v1.0.0 — Initial Public Release (current)

- ✅ bge-m3 hybrid dense+sparse embeddings (MTEB 64.3)
- ✅ Cross-encoder re-ranking with configurable MIN_SCORE threshold
- ✅ Log analysis mode with Drain3 template mining
- ✅ Vision/screenshot support via Ollama vision models
- ✅ OpenAI-compatible API with product filter and top_k extensions
- ✅ `make doctor` health checker
- ✅ `make validate-config` pre-flight validator
- ✅ 3 LLM providers: Groq, OpenRouter, Ollama
- ✅ 69 unit tests, CI/CD with GitHub Actions
- ✅ Comprehensive documentation (Beginner Guide, Glossary, Architecture, API)

---

## v1.1.0 — Stability & Observability

**Target:** Q3 2026

- [ ] Integration tests covering the full RAG pipeline against a real Docker stack
- [ ] API rate limiting (per-IP or per-token) to prevent abuse on shared deployments
- [ ] Structured logging (JSON) for the rag-api container — easier integration with log aggregators
- [ ] Qdrant collection backup/restore script (`scripts/backup_qdrant.py`)
- [ ] Prometheus metrics endpoint (`/metrics`) for Qdrant query latency and chunk count
- [ ] Scheduled weekly crawl via Docker Compose cron container

---

## v1.2.0 — Retrieval Quality Improvements

**Target:** Q4 2026

- [ ] **chonkie SDPM chunking** — Semantic Document Paragraph Model chunking for better chunk boundaries. Currently blocked by Python 3.14 incompatibility with the `tokie` Rust extension. Will be added when compatibility is confirmed.
- [ ] **Contextual compression** — Ask the LLM to extract only the relevant sentence(s) from each retrieved chunk before assembling the final prompt. Reduces noise from partially-relevant chunks.
- [ ] **Query expansion** — Automatically generate 2–3 query variants to improve sparse retrieval recall for misspelled error codes
- [ ] **Streaming responses** — Server-Sent Events for incremental response delivery (currently returns full response at once)

---

## v2.0.0 — Multi-Tenant and Scale

**Target:** 2027 (pending community demand)

- [ ] **Multi-tenant collections** — Different teams can have isolated knowledge bases with separate Qdrant collections
- [ ] **Custom URL configuration** — Add documentation from non-Zscaler sources (e.g., internal runbooks, Confluence pages) without modifying Python code
- [ ] **Admin REST API** — Endpoints to manage the knowledge base (add URLs, re-index, view stats) without SSH/CLI access
- [ ] **Horizontal scaling** — Guide for running multiple rag-api instances behind Nginx load balancer (bge-m3 process isolation)
- [ ] **Web-based admin UI** — Manage knowledge base and configuration from a browser

---

## Not Planned

These are explicitly out of scope:

- **ITSM integration** (ServiceNow, Jira) — out of scope; use the API to build your own integration
- **Real-time Zscaler API access** — this tool reads public documentation, not live tenant data
- **GPT-4 / Claude / Gemini as providers** — these require sending data to third-party US AI companies; evaluate carefully for your data classification
- **Re-adding DeepSeek** — see [ADR-005](adr/ADR-005-no-deepseek.md)
