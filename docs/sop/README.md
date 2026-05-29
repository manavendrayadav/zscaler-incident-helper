# Zscaler RAG Incident Helper — SOP Index

Standard Operating Procedures for installing, operating, and using the Zscaler RAG system.

These documents are living references. When a procedure changes (new make target, config option,
model, or fix), update the relevant SOP file in the same commit as the code change.

---

## Documents

| SOP | Audience | When to use |
|-----|----------|-------------|
| [01 — Initial Setup](01-initial-setup.md) | New team member | First-time install on a new machine |
| [02 — Daily Operations](02-daily-operations.md) | All users | Every time the system is started or checked |
| [03 — Knowledge Base Management](03-knowledge-base.md) | Maintainer | Adding pages, refreshing stale docs, re-indexing |
| [04 — Incident Investigation](04-incident-investigation.md) | Security engineer | Investigating a live Zscaler incident |
| [05 — LLM Provider Setup](05-llm-providers.md) | Maintainer | Switching providers, adding Ollama, configuring privacy mode |
| [06 — Troubleshooting](06-troubleshooting.md) | All users | Something is broken or behaving unexpectedly |

---

## Quick Reference

```
Stack ports
  OpenWebUI  http://localhost:3000   (chat UI)
  RAG API    http://localhost:8000   (OpenAI-compatible)
  Qdrant     http://localhost:6333   (vector database)
  Crawl4AI   http://localhost:11235  (headless browser crawler)
  Ollama     http://localhost:11434  (optional local LLM)

Common commands
  make up            Start everything
  make down          Stop everything
  make doctor        Health check (run first when something looks wrong)
  make validate-config  Pre-flight check before crawl/ingest
  make update        Crawl only new/changed Zscaler pages
  make ingest        Re-embed and re-index into Qdrant
  make logs          Tail rag-api logs
```

---

## Update Policy

When to update an SOP:
- A make target is added, renamed, or removed → update `02-daily-operations.md` and `03-knowledge-base.md`
- A new LLM provider or model is added → update `05-llm-providers.md`
- A new error pattern is found and fixed → add to `06-troubleshooting.md`
- A config variable is added/changed → update the relevant SOP and `.env.example`
- A privacy decision is made → update `05-llm-providers.md` privacy section

Prefix the commit message with `docs:` when updating SOPs (e.g., `docs: add qwen2-vl vision setup to SOP-05`).
