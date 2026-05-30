# API Reference

The Zscaler RAG API is fully **OpenAI-compatible** — any client that works with OpenAI's chat completions API works here without modification. It also adds RAG-specific extensions (`top_k`, `product_filter`).

**Base URL:** `http://localhost:8000`  
**Authentication:** `Authorization: Bearer <API_KEY>` (default key: `zscaler-rag`)

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [Endpoints](#2-endpoints)
   - [GET /health](#get-health)
   - [GET /stats](#get-stats)
   - [GET /v1/status](#get-v1status)
   - [GET /v1/models](#get-v1models)
   - [POST /v1/chat/completions](#post-v1chatcompletions)
3. [Error codes](#3-error-codes)
4. [Model naming convention](#4-model-naming-convention)
5. [Code examples](#5-code-examples)
6. [Vision / image content](#6-vision--image-content)

---

## 1. Authentication

All `/v1/*` endpoints require authentication. Public endpoints (`/health`, `/stats`, `/v1/status`) do not.

```http
Authorization: Bearer zscaler-rag
```

Change the API key by setting `API_KEY` in `.env`. Update `docker-compose.yml` `OPENAI_API_KEY` to match if using OpenWebUI.

**Example:**

```bash
# Returns 401 — missing auth
curl http://localhost:8000/v1/models

# Returns 200 — correct auth
curl -H "Authorization: Bearer zscaler-rag" http://localhost:8000/v1/models
```

---

## 2. Endpoints

---

### GET /health

Public endpoint. Returns service health and Qdrant connectivity.

**Response:**

```json
{
  "status": "ok",
  "qdrant_connected": true,
  "collection": "zscaler_docs",
  "chunks_indexed": 13802
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"ok"` or `"degraded: <error>"` |
| `qdrant_connected` | boolean | Whether Qdrant is reachable |
| `collection` | string | Collection name (from `COLLECTION_NAME` env var) |
| `chunks_indexed` | integer | Number of vector points in the collection |

**Used by:** Docker health check, `make doctor`

---

### GET /stats

Public endpoint. Raw Qdrant collection statistics.

**Response:**

```json
{
  "collection": "zscaler_docs",
  "vectors_count": 13802,
  "points_count": 13802,
  "status": "green"
}
```

---

### GET /v1/status

Public endpoint. Comprehensive system status including knowledge base and config.

**Response:**

```json
{
  "services": {
    "qdrant": true,
    "crawl4ai": true
  },
  "knowledge_base": {
    "pages_crawled": 1825,
    "pages_indexed": 1825,
    "pages_stale": 0,
    "by_product": {
      "zia": 841,
      "zpa": 530,
      "zdx": 133,
      "deception": 321
    }
  },
  "qdrant": {
    "points": 13802,
    "status": "green"
  },
  "config": {
    "embedding_model": "BAAI/bge-m3",
    "chunk_size": 1500,
    "top_k": 5
  }
}
```

---

### GET /v1/models

**Auth required.** Returns all available models in OpenAI format.

**Response:**

```json
{
  "object": "list",
  "data": [
    {
      "id": "zscaler-rag/groq-llama-3-3-70b-versatile",
      "object": "model",
      "created": 1748600000,
      "owned_by": "zscaler-rag"
    },
    {
      "id": "zscaler-rag/groq-llama-3-1-8b-instant",
      ...
    },
    {
      "id": "zscaler-rag/ollama-llama3-2",
      ...
    }
  ]
}
```

Use this endpoint to discover available models programmatically.

---

### POST /v1/chat/completions

**Auth required.** Main RAG endpoint — processes a query, retrieves relevant Zscaler docs, and generates a grounded response.

#### Request body

```json
{
  "model": "zscaler-rag/groq-llama-3-3-70b-versatile",
  "messages": [
    {"role": "user", "content": "ZPA App Connector shows AUTH_FAILED"}
  ],
  "temperature": 0.3,
  "max_tokens": 2048,
  "top_k": 5,
  "product_filter": "zpa"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `model` | string | ✅ | — | Model ID (see [naming convention](#4-model-naming-convention)) |
| `messages` | array | ✅ | — | Chat history. Last user message is used as the query. |
| `messages[].role` | string | ✅ | — | `"user"` or `"assistant"` |
| `messages[].content` | string \| array | ✅ | — | Text string, or [vision content array](#6-vision--image-content) |
| `temperature` | float | ❌ | `0.3` | Response creativity. `0` = deterministic, `1` = creative. |
| `max_tokens` | integer | ❌ | `2048` | Maximum response length in tokens |
| `top_k` | integer | ❌ | `5` | RAG-specific: number of doc chunks to retrieve (1–20) |
| `product_filter` | string \| null | ❌ | `null` | Restrict retrieval to one product: `"zia"`, `"zpa"`, `"zdx"`, `"deception"` |

#### Response

```json
{
  "id": "chatcmpl-a1b2c3d4e5f6g7h8",
  "object": "chat.completion",
  "created": 1748600000,
  "model": "zscaler-rag/groq-llama-3-3-70b-versatile",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "## Root Cause Analysis\n\nAUTH_FAILED on ZPA App Connector typically..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 1842,
    "completion_tokens": 387,
    "total_tokens": 2229
  }
}
```

| Field | Description |
|-------|-------------|
| `choices[0].message.content` | The full response in Markdown. Includes `## References` section at the end with source URLs. |
| `choices[0].finish_reason` | `"stop"` = normal completion, `"length"` = hit `max_tokens` |
| `usage.prompt_tokens` | Tokens in the RAG prompt (query + retrieved chunks + system prompt) |

#### Automatic mode detection

The API automatically detects which mode to use:

| Condition | Mode | System prompt used |
|-----------|------|------------------|
| Has image content blocks | `log_analysis` | `LOG_ANALYSIS_SYSTEM_PROMPT` |
| Text contains timestamps + error keywords | `log_analysis` | `LOG_ANALYSIS_SYSTEM_PROMPT` |
| All other queries | `doc_search` | `SYSTEM_PROMPT` |

Force log analysis mode by prefixing your message with `[log analysis]`.

---

## 3. Error codes

| HTTP status | Cause | Fix |
|-------------|-------|-----|
| `401` | Missing or wrong API key | Add `Authorization: Bearer <API_KEY>` header |
| `400` | No user message in messages array | Ensure at least one `{"role": "user"}` message |
| `503` | Qdrant retrieval failed | Check if Qdrant is running: `make doctor` |
| `502` | LLM generation failed | Check provider API key; verify Groq/Ollama is reachable |
| `422` | Validation error | Check request body against schema above |

**Error response format:**

```json
{
  "detail": "LLM generation failed (groq/llama-3.3-70b-versatile): Connection error"
}
```

---

## 4. Model naming convention

All model IDs follow this pattern:

```
zscaler-rag/{provider}-{model-slug}
```

The slug is the model name with `.`, `/`, and `_` replaced by `-`.

**All available models:**

| Model ID | Provider | Model | Notes |
|----------|----------|-------|-------|
| `zscaler-rag/groq-llama-3-3-70b-versatile` | Groq | llama-3.3-70b-versatile | Best quality, default |
| `zscaler-rag/groq-llama-3-1-8b-instant` | Groq | llama-3.1-8b-instant | Fastest |
| `zscaler-rag/groq-mixtral-8x7b-32768` | Groq | mixtral-8x7b-32768 | Long context (32k) |
| `zscaler-rag/groq-gemma2-9b-it` | Groq | gemma2-9b-it | Google Gemma2 |
| `zscaler-rag/openrouter-*` | OpenRouter | Various | Requires OpenRouter key |
| `zscaler-rag/ollama-llama3-2` | Ollama | llama3.2:3b | Local, private |
| `zscaler-rag/ollama-llama3-1` | Ollama | llama3.1:8b | Local, private |
| `zscaler-rag/ollama-mistral` | Ollama | mistral:7b | Local, private |
| `zscaler-rag/ollama-llama3-2-vision` | Ollama | llama3.2-vision | Vision + local |
| `zscaler-rag/ollama-llava` | Ollama | llava:7b | Vision + local |
| `zscaler-rag/ollama-moondream` | Ollama | moondream:1.8b | Vision + local, lightweight |
| `zscaler-rag/ollama-qwen2-vl-7b` | Ollama | qwen2-vl:7b | Best vision + local |

Use `GET /v1/models` for the authoritative live list.

---

## 5. Code examples

### Python — using `openai` SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="zscaler-rag",
)

response = client.chat.completions.create(
    model="zscaler-rag/groq-llama-3-3-70b-versatile",
    messages=[
        {
            "role": "user",
            "content": "ZPA App Connector shows TUNNEL_DOWN. Common causes?"
        }
    ],
    temperature=0.3,
    max_tokens=1024,
    extra_body={
        "top_k": 5,
        "product_filter": "zpa"
    }
)

print(response.choices[0].message.content)
```

### Python — using `requests`

```python
import requests

response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    headers={"Authorization": "Bearer zscaler-rag"},
    json={
        "model": "zscaler-rag/groq-llama-3-3-70b-versatile",
        "messages": [
            {"role": "user", "content": "ZIA SSL bypass for Microsoft 365?"}
        ],
        "top_k": 5
    },
    timeout=30
)

data = response.json()
print(data["choices"][0]["message"]["content"])
```

### JavaScript / Node.js — using `openai` npm package

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://localhost:8000/v1",
  apiKey: "zscaler-rag",
});

const response = await client.chat.completions.create({
  model: "zscaler-rag/groq-llama-3-3-70b-versatile",
  messages: [
    { role: "user", content: "ZPA App Connector AUTH_FAILED troubleshooting" }
  ],
  temperature: 0.3,
});

console.log(response.choices[0].message.content);
```

### cURL

```bash
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer zscaler-rag" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "zscaler-rag/groq-llama-3-3-70b-versatile",
    "messages": [{"role": "user", "content": "ZIA PAC file syntax for split tunneling"}],
    "top_k": 5,
    "product_filter": "zia"
  }' | python -m json.tool
```

---

## 6. Vision / image content

For screenshot analysis, pass the image as an OpenAI vision content block. **Only works with Ollama vision models.**

```python
import base64
from pathlib import Path

# Read and encode screenshot
image_bytes = Path("screenshot.png").read_bytes()
b64 = base64.b64encode(image_bytes).decode()

response = client.chat.completions.create(
    model="zscaler-rag/ollama-qwen2-vl-7b",  # must be a vision model
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "What error is shown in this screenshot?"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{b64}"
                    }
                }
            ]
        }
    ]
)
```

**Privacy note:** When using Ollama vision models, the image is processed locally and never leaves your machine. Do not send screenshots to Groq or OpenRouter models.

**Vision-capable model IDs:**
- `zscaler-rag/ollama-llama3-2-vision`
- `zscaler-rag/ollama-llava`
- `zscaler-rag/ollama-moondream`
- `zscaler-rag/ollama-qwen2-vl-7b` (recommended: best text-in-image accuracy)
