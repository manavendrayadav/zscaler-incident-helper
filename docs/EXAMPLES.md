# Examples and Query Patterns

Real examples showing how to use the Zscaler RAG Incident Helper effectively.
Each example shows the query, what the system does with it, and what a good response looks like.

---

## Table of Contents

1. [Example 1 — ZPA App Connector issue](#example-1--zpa-app-connector-issue)
2. [Example 2 — Pasting a ZIA log dump](#example-2--pasting-a-zia-log-dump)
3. [Example 3 — Product-scoped query](#example-3--product-scoped-query)
4. [Example 4 — API call from Python](#example-4--api-call-from-python)
5. [Example 5 — Screenshot analysis with Ollama](#example-5--screenshot-analysis-with-ollama)
6. [Query pattern guide](#query-pattern-guide)
7. [What a good response looks like](#what-a-good-response-looks-like)

---

## Example 1 — ZPA App Connector issue

**Mode:** Doc search  
**Model:** `zscaler-rag/groq-llama-3-3-70b-versatile`  
**Privacy:** Safe for Groq (no internal data in query)

### Query

```
ZPA App Connector shows CONNECTOR_DOWN in the admin portal. The connector was working
yesterday. What are the most likely causes and resolution steps?
```

### What happens internally

1. The query is embedded into a 1,024-dimensional vector
2. Qdrant hybrid search (dense + sparse) finds the 20 most relevant chunks from ZPA troubleshooting pages
3. Cross-encoder scores each (query, chunk) pair — promotes chunks about "CONNECTOR_DOWN" and "connectivity"
4. Top 5 chunks above MIN_SCORE=0.3 are assembled into the LLM prompt
5. Response generated in ~4 seconds

### Sample response (truncated)

```markdown
## Root Cause Analysis
CONNECTOR_DOWN typically indicates the App Connector has lost its connection to the
Zscaler Private Access broker. Common causes include:

1. **Network connectivity issues** — The connector host cannot reach Zscaler's
   cloud endpoints (typically *.zscalerone.net or *.zscaler.net)
2. **Expired enrollment certificate** — App Connector certificates are valid for
   a limited period. Check expiry in Administration > Connectors
3. **Firewall blocking outbound traffic** — ZPA requires TCP 443 to Zscaler
   cloud endpoints. UDP 9000 is required for Z-Tunnel 2.0
4. **Resource exhaustion** — High CPU or memory on the connector host

## Step-by-Step Resolution

### 1. Check connector logs
```bash
# On the connector host (Linux)
sudo journalctl -u zscaler-connector --since "1 hour ago"
# Look for: AUTH_FAILED, TUNNEL_DOWN, connection refused
```

### 2. Verify network connectivity
Test outbound access from the connector host:
```bash
curl -v https://gateway.zscalerone.net
# Expected: HTTP 200 or 302 (not connection refused)
```

### 3. Check certificate expiry
In the Zscaler Admin Portal:
- Navigate to **Administration > App Connectors**
- Find your connector and check the **Certificate Expiry** column
- If expired: delete and re-enroll the connector

## Verification Steps
After applying the fix:
1. Monitor the connector status in the Admin Portal for 2 minutes
2. The status should change from CONNECTOR_DOWN → CONNECTOR_UP
3. Test a ZPA application access from an end user device

## References
- https://help.zscaler.com/zpa/troubleshooting-app-connectors
- https://help.zscaler.com/zpa/app-connector-requirements
```

---

## Example 2 — Pasting a ZIA log dump

**Mode:** Log analysis (auto-detected)  
**Model:** `zscaler-rag/ollama-llama3-2` ← **Use Ollama for real internal logs**  
**Privacy:** Switch to Ollama before pasting real logs

### Query (paste this directly into chat)

```
2026-05-28T10:00:00Z ERROR connector=prod-dc1 reason=AUTH_FAILED tunnel_id=abc123
2026-05-28T10:00:01Z WARN  broker=us-west-1 status=UNREACHABLE retries=3
2026-05-28T10:00:05Z ERROR connector=prod-dc1 reason=CERT_ERROR cert_subject=*.internal.corp
2026-05-28T10:00:10Z FATAL tunnel=T-4421 state=TUNNEL_DOWN duration=320s
```

### What happens internally

1. The system detects timestamps + error keywords → switches to **log-analysis mode**
2. Drain3 extracts structured signals: `AUTH_FAILED`, `CERT_ERROR`, `TUNNEL_DOWN`, `connector`, `broker`
3. These signals are used as the Qdrant search query (instead of the raw log text)
4. Product detection identifies `zpa` (connector + broker + tunnel keywords)
5. A different system prompt is used: "Identify events, root cause, resolution"

### Sample response (truncated)

```markdown
## Identified Events

| Timestamp | Severity | Event | Details |
|-----------|----------|-------|---------|
| 10:00:00Z | ERROR | Authentication failure | connector=prod-dc1, tunnel_id=abc123 |
| 10:00:01Z | WARN  | Broker unreachable | broker=us-west-1, retries exhausted (3) |
| 10:00:05Z | ERROR | Certificate error | Subject: *.internal.corp (likely internal CA) |
| 10:00:10Z | FATAL | Tunnel down | T-4421 down for 320 seconds |

## Root Cause

The sequence shows a cascading failure beginning with certificate validation:

1. The `CERT_ERROR` for `*.internal.corp` suggests the connector cannot validate
   certificates signed by your internal CA
2. This causes `AUTH_FAILED` — the connector cannot authenticate to the ZPA broker
3. The broker becomes `UNREACHABLE` as the authentication fails repeatedly
4. The tunnel enters `TUNNEL_DOWN` state after exhausting reconnection attempts

**Most likely cause:** Your ZPA App Connector is not configured to trust your
internal Certificate Authority. This is required when your organization uses
an internal PKI for application certificates.

## Step-by-Step Resolution

1. Export your internal root CA certificate (PEM format)
2. Add the CA cert to the App Connector's trusted store:
   ...

## References
- https://help.zscaler.com/zpa/configuring-custom-certificate-authority
```

> **Note:** The `[log analysis]` prefix forces log mode if auto-detection doesn't trigger.

---

## Example 3 — Product-scoped query

**Mode:** Doc search with product filter  
**Model:** Any

### Without product filter

```
SSL inspection causing authentication failures
```

This retrieves chunks from ZIA, ZPA, and ZDX — potentially unfocused.

### With product filter (better precision)

```
[product:zia] SSL inspection causing SAML authentication failures for Okta users
```

**What the prefix does:** Restricts Qdrant retrieval to chunks tagged `product=zia`. Prevents ZPA and ZDX content from diluting the results.

**Equivalent via API:**

```json
{
  "model": "zscaler-rag/groq-llama-3-3-70b-versatile",
  "messages": [{"role": "user", "content": "SSL inspection causing SAML auth failures"}],
  "product_filter": "zia"
}
```

**Valid product filter values:** `zia`, `zpa`, `zdx`, `deception`

---

## Example 4 — API call from Python

For integrating the RAG system into scripts, CI pipelines, or other tools.

### Using the `openai` Python SDK (recommended)

```python
from openai import OpenAI

# Point to your local RAG API instead of OpenAI
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="zscaler-rag",  # matches API_KEY in .env
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
        "top_k": 5,              # number of doc chunks to retrieve
        "product_filter": "zpa"  # scope to ZPA only
    }
)

print(response.choices[0].message.content)
```

### Using `requests` directly (no SDK needed)

```python
import requests

url = "http://localhost:8000/v1/chat/completions"
headers = {
    "Authorization": "Bearer zscaler-rag",
    "Content-Type": "application/json"
}
payload = {
    "model": "zscaler-rag/groq-llama-3-3-70b-versatile",
    "messages": [
        {"role": "user", "content": "ZIA SSL inspection bypass for Microsoft 365?"}
    ],
    "temperature": 0.3,
    "top_k": 5
}

response = requests.post(url, headers=headers, json=payload, timeout=30)
data = response.json()
answer = data["choices"][0]["message"]["content"]
print(answer)
```

### Using cURL

```bash
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer zscaler-rag" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "zscaler-rag/groq-llama-3-3-70b-versatile",
    "messages": [{"role": "user", "content": "ZIA PAC file syntax for office network"}],
    "top_k": 5
  }' | python -m json.tool
```

### List available models

```bash
curl -H "Authorization: Bearer zscaler-rag" http://localhost:8000/v1/models
```

---

## Example 5 — Screenshot analysis with Ollama

For analysing screenshots of error dialogs, dashboard alerts, or log viewers.

**Prerequisite:** `make ollama-vision` (pulls qwen2-vl:7b, llava, moondream)

### In OpenWebUI

1. Select model: `zscaler-rag/ollama-qwen2-vl:7b`
2. Click the **paperclip** (📎) icon
3. Attach your screenshot
4. Type a question (or just send — the system will analyse automatically)

**Example question with screenshot:**

```
What error is shown in this screenshot and what does it mean?
```

**What happens:**

1. The vision model reads text from the screenshot
2. Extracted text is used to search the Zscaler knowledge base
3. Response correlates screenshot content with relevant documentation

> **Privacy:** Ollama runs locally — the screenshot never leaves your machine.

---

## Query Pattern Guide

### Patterns that work well

| Pattern | Example | Why it works |
|---------|---------|--------------|
| Include the exact error code | `AUTH_FAILED connector error` | Hybrid search finds exact code match via sparse vectors |
| Name the Zscaler product | `ZPA App Connector enrollment fails` | Product keywords improve retrieval precision |
| Describe the symptom | `TUNNEL_DOWN after 5 minutes connectivity` | Semantic search finds related concepts |
| Use `[product:xxx]` for scoped queries | `[product:zia] SSL bypass for Zoom` | Eliminates irrelevant product chunks |
| Include context | `Using GRE tunnel, traffic forwarding to ZIA` | More context = better chunk matching |

### Patterns that don't work as well

| Pattern | Example | Problem | Fix |
|---------|---------|---------|-----|
| Too vague | `connector not working` | Low retrieval precision | Specify product: `ZPA App Connector` |
| Very long logs | Pasting 500 log lines | Drain3 only extracts 15 signals | Paste only the 5–10 most recent error lines |
| Mixed products | `ZIA and ZPA both have issues` | Diluted retrieval | Ask as two separate product-scoped queries |
| Future features | `ZPA feature announced last week` | May not be in knowledge base | Run `make update` then retry |

---

## What a Good Response Looks Like

A high-quality response has these characteristics:

✅ **References specific Zscaler menu paths** — e.g., "Navigate to Administration > App Connectors > Certificates"  
✅ **Includes exact CLI commands** — `sudo systemctl restart zscaler-connector`  
✅ **Lists numbered steps** — actionable, not vague  
✅ **Cites 2–5 source URLs** — from `help.zscaler.com`  
✅ **Acknowledges what it doesn't know** — "This depends on your specific tunnel type"

A low-quality response:

❌ Very short and generic ("Check the logs and contact Zscaler support")  
❌ No source URLs  
❌ Describes a different product than you asked about  
❌ Lists steps that require access to your tenant configuration

**If you get a low-quality response:**

1. Check `make doctor` — verify Qdrant has ~13,800 chunks
2. Add the product prefix: `[product:zpa]`
3. Include the specific error code in your query
4. Run `make update` if the issue may be recent
5. Rephrase using Zscaler's own terminology (check help.zscaler.com for the canonical term)
