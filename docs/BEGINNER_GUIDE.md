# Beginner's Guide to the Zscaler RAG Incident Helper

This guide is for you if any of these apply:
- You've never heard of "RAG" or "vector databases"
- You're a security engineer, not a machine-learning engineer
- You just want to understand *why* this tool gives better answers than ChatGPT
- You want to know which model to use so your internal data stays private

No prior AI or ML knowledge required. By the end of this guide you'll be able to explain the tool to a colleague in one sentence, use it confidently, and make an informed choice about data privacy.

---

## Table of Contents

1. [What does this tool do?](#1-what-does-this-tool-do)
2. [The problem it solves](#2-the-problem-it-solves)
3. [What is RAG? (Plain English)](#3-what-is-rag-plain-english)
4. [Key concepts you'll encounter](#4-key-concepts-youll-encounter)
5. [Why not just use ChatGPT?](#5-why-not-just-use-chatgpt)
6. [Your first query — a walkthrough](#6-your-first-query--a-walkthrough)
7. [Understanding the response structure](#7-understanding-the-response-structure)
8. [Privacy guide: which model should I use?](#8-privacy-guide-which-model-should-i-use)
9. [What the tool cannot do](#9-what-the-tool-cannot-do)
10. [Next steps](#10-next-steps)

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

This takes **15–30 minutes per incident**. Multiply that by the number of tickets per week.

**Why not just ask ChatGPT?**
- ChatGPT answers from its training data — which may be months or years old
- ChatGPT has no access to your specific Zscaler configuration or current documentation
- ChatGPT "hallucinates" — it confidently gives wrong answers when it doesn't know
- ChatGPT requires sending your incident details (potentially including internal data) to OpenAI's servers

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

**The open-book exam analogy:**
Think of a regular LLM (like ChatGPT) as a student taking a closed-book exam — answering purely from memory. RAG is the same student taking an open-book exam. The student can look up the relevant pages before writing the answer. The result is more accurate and verifiable.

**Why does retrieval use "vectors" instead of keyword search?**

Traditional search (like Google) finds pages that contain the exact words you typed. Vector search finds pages with similar *meaning*, even if they use different words. For example:
- Your query: "connector won't authenticate"
- A relevant doc page: "App Connector enrollment certificate validation failure"

These share no words, but a vector search finds the connection because both are about authentication failures in ZPA connectors.

---

## 4. Key concepts you'll encounter

You don't need to understand these deeply to use the tool — but knowing what they mean will help you interpret the output and tune the system if needed.

| Term | Plain English |
|------|---------------|
| **Embedding** | Converting text into a list of ~1,000 numbers that capture its meaning. Similar texts produce similar numbers. |
| **Vector database (Qdrant)** | A search engine that finds similar meaning, not just matching keywords. Holds all 13,800 doc chunks. |
| **Chunk** | A paragraph-sized piece of a documentation page (~500 words). Docs are split into chunks because the AI has a limit on how much text it can process at once. |
| **Dense search** | Finding chunks with similar overall meaning (semantic search). |
| **Sparse search** | Finding chunks with matching keywords and error codes (keyword search). |
| **Hybrid search** | Combining dense + sparse search. Used by default — better than either alone for queries with specific error codes like `AUTH_FAILED`. |
| **Re-ranking** | After the initial search returns 20 candidates, a second AI model scores each (query, chunk) pair more carefully to produce a better-ordered shortlist. |
| **LLM** | Large Language Model — the AI that writes the final answer. Examples: Groq's llama-3.3, Ollama's llama3.2. |
| **TOP_K** | How many chunks to include in the LLM's context (default: 5). More = richer context but slower response. |
| **MIN_SCORE** | The minimum relevance score for a chunk to be included (default: 0.3 on a 0–1 scale). Low-relevance chunks are discarded. |

For detailed definitions of these and all other terms, see [GLOSSARY.md](GLOSSARY.md).

---

## 5. Why not just use ChatGPT?

Here's an honest comparison:

| | ChatGPT | This Tool |
|--|---------|-----------|
| Knowledge cutoff | Training data (months/years old) | As recent as your last `make update` |
| Grounding | None — answers from training data | Every answer cites source Zscaler docs |
| Hallucination risk | High for niche topics | Low — LLM is constrained to retrieved docs |
| Internal log privacy | Your logs go to OpenAI | Ollama mode: nothing leaves your machine |
| Cost per query | ~$0.01–0.10 (GPT-4) | $0.00 (Groq free tier) or local Ollama |
| ZPA/ZIA specificity | General knowledge | 1,825 Zscaler documentation pages |
| Verifiable | No source links | Every response includes source URLs |

**When ChatGPT is still better:**
- Creative writing, summarising non-Zscaler documents
- Very recent events (past few months before your last crawl)
- Questions that require your specific tenant's configuration data

---

## 6. Your first query — a walkthrough

**Open the chat interface:** http://localhost:3000

After registering (first user becomes admin) and selecting a model, try this query:

```
ZPA App Connector shows TUNNEL_DOWN. What are the most common causes and how do I fix it?
```

Here's what happens behind the scenes:

1. Your query is converted to a 1,024-number vector (embedding)
2. Qdrant searches ~13,800 chunk vectors for the most similar ones
3. A cross-encoder model re-ranks the top 20 by relevance
4. The top 5 chunks (those scoring above 0.3) are assembled into a prompt
5. Groq's llama-3.3-70b-versatile generates a response grounded in those chunks
6. The response appears in the chat with source links at the bottom

**Expected response time:** 3–8 seconds with Groq.

---

## 7. Understanding the response structure

Every response follows this structure:

```markdown
## Root Cause Analysis
Explanation of what caused the TUNNEL_DOWN state, based on the retrieved docs.

## Step-by-Step Resolution
1. First action to take (specific Zscaler admin portal path or CLI command)
2. Second action
3. ...

## Verification Steps
How to confirm the issue is resolved.

## Prevention Tips
Configuration changes to prevent recurrence.

## References
- [Troubleshooting App Connectors](https://help.zscaler.com/zpa/troubleshooting-app-connectors)
- [ZPA Connector Requirements](https://help.zscaler.com/zpa/...)
```

> **Important:** Always verify the recommended steps against your specific Zscaler configuration before applying changes. The tool reads public Zscaler documentation; it doesn't have access to your tenant settings.

**What if the response seems wrong or generic?**

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Very short or vague response | Knowledge base still indexing | Check `make doctor` for chunk count (~13,800 when complete) |
| Response about wrong product | Query was ambiguous | Add `[product:zpa]` prefix to scope to one product |
| "I don't have information" | Topic not in knowledge base | Run `make update` to pull latest Zscaler docs |
| Response ignores your log details | Didn't trigger log-analysis mode | Paste at least 3 log lines with timestamps — triggers automatically |

---

## 8. Privacy guide: which model should I use?

**This is the most important section if you handle sensitive data.**

When you select a model in OpenWebUI, your query text is sent to that model's provider. Here's what that means:

### Groq models (`zscaler-rag/groq-*`)

- ✅ **Use for:** General Zscaler questions with no internal data
- ✅ Fast (~3–8 seconds)
- ✅ Free tier available
- ❌ **Never use for:** Internal log output, employee names, system identifiers, IP addresses
- 📍 Data goes to: Groq's US-based servers

### OpenRouter models (`zscaler-rag/openrouter-*`)

- ✅ **Use for:** General Zscaler questions, if you need a specific model not on Groq
- ❌ **Never use for:** Internal data (same as Groq)
- ⚠️ Some models on OpenRouter route to non-US providers — check the specific model

### Ollama models (`zscaler-rag/ollama-*`)

- ✅ **Use for:** Everything — especially internal logs and screenshots
- ✅ **100% private** — runs on your machine, zero data leaves your network
- ❌ Slower (~60–180 seconds per query on CPU, ~5–15 seconds with GPU)
- 📍 Data goes to: Nowhere — fully local

### Decision guide

```
Is the query content sensitive?
(contains log output, IP addresses, system names, employee data)
    │
    ├─ YES → Use an Ollama model
    │         make ollama-setup (first-time only)
    │         Select: zscaler-rag/ollama-llama3-2
    │
    └─ NO  → Use Groq for speed
              Select: zscaler-rag/groq-llama-3-3-70b-versatile
```

**For screenshots:** Always use an Ollama vision model:
```bash
make ollama-vision   # pulls llava, moondream, qwen2-vl:7b
```
Then select `zscaler-rag/ollama-qwen2-vl:7b` in OpenWebUI and attach the screenshot.

---

## 9. What the tool cannot do

Be aware of these limitations before relying on the tool for production decisions:

- **No access to your Zscaler tenant.** The tool reads public Zscaler documentation. It cannot see your specific policies, users, or configuration.
- **Knowledge cutoff.** The knowledge base is as current as your last `make update`. Run `make update` weekly to stay current.
- **The AI can be wrong.** Even with retrieved documentation, the LLM may misinterpret or incorrectly apply the information. Always verify before making configuration changes.
- **Complex multi-product issues.** If an incident spans ZIA, ZPA, and ZCC simultaneously, a single query may not capture all dimensions. Ask separate product-scoped questions.
- **No incident ticketing.** This tool answers questions — it does not create tickets, send alerts, or integrate with ITSM platforms (yet).

---

## 10. Next steps

| I want to... | Go here |
|--------------|---------|
| Start using the tool now | [QUICK_START.md](QUICK_START.md) |
| See example queries and responses | [EXAMPLES.md](EXAMPLES.md) |
| Understand the full data flow | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Configure and tune the system | [CONFIGURATION.md](CONFIGURATION.md) |
| Set up private Ollama mode | [OPERATIONS.md](OPERATIONS.md) §6 |
| Troubleshoot an issue | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |
| Look up a technical term | [GLOSSARY.md](GLOSSARY.md) |
