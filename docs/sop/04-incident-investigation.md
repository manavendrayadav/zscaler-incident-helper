# SOP-04 — Incident Investigation

**Audience:** Security engineer responding to a Zscaler-related incident.
**When:** A ticket is raised for ZIA, ZPA, ZDX, or Zscaler Client Connector issues.

---

## Privacy rule (mandatory)

**Internal logs and screenshots must only be sent to Ollama (local).**
Never paste raw logs or attach screenshots when using a Groq or OpenRouter model —
those providers send your data to external APIs.

Use cloud models (groq, openrouter) only for general Zscaler questions where
no internal data is present in the query.

See [SOP-05 — LLM Provider Setup](05-llm-providers.md) to enable Ollama.

---

## Mode 1: General question (no internal data)

Use when you need to understand a Zscaler feature, error code, or configuration option.

1. Open `http://localhost:3000`
2. Select a cloud model (e.g. `zscaler-rag/groq-llama-3-3-70b-versatile`)
3. Ask your question in plain English

The RAG system automatically retrieves the top-5 most relevant documentation chunks
and passes them to the LLM along with your question.

**Good query patterns:**

```
ZPA App Connector shows CONNECTOR_DOWN — what are common causes?

How do I configure SSL inspection bypass for Office 365 in ZIA?

ZDX digital experience score dropped below 50 for all users in EU — how do I diagnose?

What ZIA policy settings cause AUTH_FAILED for SAML users?
```

**Expected response structure:**
- ## Root Cause Analysis
- ## Step-by-Step Resolution
- ## Verification Steps
- ## Prevention Tips
- ## References (source URLs from the knowledge base)

---

## Mode 2: Log analysis (paste raw logs)

Use when you have log output from Zscaler Client Connector, App Connector, or NSS.

**Privacy requirement:** Switch to an Ollama model first.

1. In OpenWebUI, select `zscaler-rag/ollama-llama3-2` (or any `ollama-*` model)
2. Paste the raw log block directly into the chat

The system auto-detects log content (timestamps + error keywords) and switches to
log-analysis mode, which:
- Extracts error codes and Zscaler component keywords using Drain3 template mining
- Uses those signals to retrieve relevant documentation
- Returns a structured analysis with identified events, root cause, and resolution steps

**Example log paste:**

```
2026-05-28T10:00:00Z ERROR connector=prod-dc1 reason=AUTH_FAILED tunnel_id=abc123
2026-05-28T10:00:01Z WARN  broker=us-west-1 status=UNREACHABLE retries=3
2026-05-28T10:00:05Z ERROR connector=prod-dc1 reason=CERT_ERROR cert_subject=*.internal.corp
2026-05-28T10:00:10Z FATAL tunnel=T-4421 state=TUNNEL_DOWN duration=320s
```

The response will include:
- ## Identified Events (each log line explained)
- ## Root Cause
- ## Step-by-Step Resolution
- ## Verification Steps
- ## References

---

## Mode 3: Screenshot / image analysis (full privacy)

Use when you have a screenshot of an error dialog, dashboard alert, or log viewer.

**Requirements:**
- Ollama must be running with a vision-capable model
- Recommended: `qwen2-vl:7b` (best text-in-image accuracy, DocVQA 93.1)
- Alternative: `llava` or `moondream` (smaller, faster, less accurate)

Enable vision models: `make ollama-vision`

1. In OpenWebUI, select `zscaler-rag/ollama-qwen2-vl:7b`
2. Click the paperclip icon and attach your screenshot
3. Type your question, or just send the image — the system will analyse it automatically

The vision model reads text from the screenshot, the RAG system retrieves relevant
documentation, and the response correlates both.

---

## Product-scoped queries

If you know the product causing the issue, add a filter to improve retrieval precision:

```
[product:zpa] App Connector enrollment failing — certificate error
[product:zia] SSL inspection breaking Slack calls
[product:zdx] Experience score degraded — EU users only
```

Or via the API:

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer zscaler-rag" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "zscaler-rag/groq-llama-3-3-70b-versatile",
    "messages": [{"role": "user", "content": "App Connector TUNNEL_DOWN"}],
    "product_filter": "zpa",
    "top_k": 8
  }'
```

---

## Retrieval quality tips

| Situation | Tip |
|-----------|-----|
| Response lacks detail | Increase `top_k` in the API call (default 5, max ~20) |
| Wrong product context | Use `[product:zpa]` prefix or `product_filter` API field |
| Error code not found | Include the full code (e.g. `ZS-1234`, `AUTH_FAILED`) — hybrid search handles exact tokens |
| Very long log | Paste only the most recent 50–100 lines — Drain3 extracts the key signals |
| Screenshot too complex | Crop to the error area before attaching |

---

## Citing sources

Every response ends with a ## References section listing source URLs from
`help.zscaler.com`. Use these to:
- Validate the AI's recommendation before applying it
- Link in your incident ticket
- Identify where to look if the response doesn't fully cover the issue

The retrieval score for each source is shown in the API response payload under
`choices[0].message.sources`.

---

## Escalation

If the RAG system cannot find relevant documentation:

1. Check `make doctor` — verify chunks > 0 in Qdrant
2. Try rephrasing with more specific Zscaler terminology
3. Check if the issue relates to a very new Zscaler feature — run `make update` to pull
   the latest documentation
4. Escalate to Zscaler Support with the log snippets and the RAG system's analysis
   as additional context
