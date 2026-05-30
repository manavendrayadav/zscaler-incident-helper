# ADR-003: Build an OpenAI-Compatible API Instead of a Custom Protocol

**Status:** Accepted  
**Date:** 2026-05-15  
**Deciders:** @manavendrayadav

---

## Context

The RAG system needs a chat interface for end users. Two architectural paths were available:

1. **Custom frontend** (e.g., Streamlit, React): Build and maintain a UI that talks directly to our internal API format.
2. **OpenAI-compatible API** + standard chat UI: Implement the same HTTP contract as OpenAI's chat completions API, then connect any existing OpenAI-compatible chat client.

---

## Decision

Implement the RAG API as an **OpenAI-compatible** `/v1/chat/completions` endpoint.

Connect **OpenWebUI** as the chat frontend — an open-source, Docker-native chat interface that natively supports any OpenAI-compatible backend.

This means:
- The RAG API implements `POST /v1/chat/completions` and `GET /v1/models` with the OpenAI JSON schema
- OpenWebUI connects via `OPENAI_API_BASE_URL=http://rag-api:8000/v1`
- Any tool built for OpenAI (LangChain, openai Python SDK, JavaScript openai package, curl) works immediately

---

## Consequences

**Positive:**
- **Zero frontend code.** OpenWebUI provides multi-user chat, conversation history, model switching, file upload (vision), and user management without any custom development.
- **Portability.** Any engineer on the team can use their preferred OpenAI-compatible client (Cursor, LibreChat, etc.) without configuration changes.
- **Standard SDK support.** `openai` Python SDK, `@openai/openai` npm package, LangChain's `ChatOpenAI` all work with `base_url="http://localhost:8000/v1"`.
- **Extension.** Adding streaming support, function calling, or multi-modal features in the future follows documented OpenAI API patterns.

**Negative:**
- **Custom parameters are non-standard.** RAG-specific parameters (`top_k`, `product_filter`) must be passed as `extra_body` in the SDK or handled as non-standard fields. Documented in the API reference.
- **Schema constraints.** Must maintain compatibility with the OpenAI API contract, limiting freedom to diverge.

---

## Alternatives Considered

| Alternative | Rejected because |
|-------------|-----------------|
| Streamlit frontend | Requires maintaining custom UI code; not portable; single-user without significant work |
| Custom FastAPI + React | Large engineering effort; no benefit over standard approach for this use case |
| LangServe | LangChain-specific; adds LangChain as a hard dependency; less control over prompt logic |
| REST API with custom JSON schema | No standard clients; every team member needs custom integration code |
