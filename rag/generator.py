"""
Build a RAG prompt from retrieved chunks and generate an incident resolution
using the chosen LLM provider.

Two modes:
  doc_search   — user asked a question; respond with structured resolution
  log_analysis — user pasted logs or attached a screenshot; identify events + correlate with docs
"""

from typing import Optional

from llm.base import Message, LLMResponse
from llm.factory import get_provider
from rag.retriever import SourceChunk

# ── System prompts ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior Zscaler security engineer with deep expertise in \
ZIA (Zscaler Internet Access), ZPA (Zscaler Private Access), ZDX, and Zscaler Client Connector. \
You help security engineering teams diagnose and resolve Zscaler-related incidents quickly and accurately.

When answering:
- Be specific — name exact Zscaler settings, menu paths, CLI commands, and log locations.
- Always base your answer on the provided documentation context.
- If the context doesn't cover the issue, say so and suggest what additional information \
  the team should gather.
- Format your response in clean Markdown."""

LOG_ANALYSIS_SYSTEM_PROMPT = """You are a senior Zscaler security engineer analyzing \
incident logs and error screenshots for a security team.

You will receive:
1. The raw log output or screenshot provided by the engineer
2. Relevant Zscaler documentation retrieved from the knowledge base

Your job:
- Read the logs/screenshot carefully and identify every error, warning, and anomaly
- Correlate findings with the provided documentation
- Explain what each event means in plain language
- Provide actionable resolution steps

Be specific: reference exact Zscaler settings, menu paths, CLI commands, connector names, \
tunnel IDs, and error codes from the logs.
Format your response in clean Markdown."""


# ── Prompt builders ───────────────────────────────────────────────────────────

def _format_context(chunks: list[SourceChunk]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"[Doc {i}] {chunk.title} — {chunk.section}\n"
            f"Source: {chunk.url}\n"
            f"Relevance score: {chunk.score}\n\n"
            f"{chunk.text}"
        )
    return "\n\n---\n\n".join(parts)


def _build_rag_prompt(query: str, chunks: list[SourceChunk]) -> str:
    context = _format_context(chunks)
    return f"""## Retrieved Zscaler Documentation Context

{context}

---

## Incident / Query

{query}

---

Based **only** on the documentation above, provide:

### Root Cause Analysis
Identify the most likely cause(s) based on the described symptoms.

### Step-by-Step Resolution
Number each step. Be specific — include exact menu paths, CLI commands, or API calls.

### Verification Steps
How to confirm the issue is resolved.

### Prevention Tips
How to avoid this issue in the future.

### References
List each documentation source used (title + URL)."""


def _build_log_analysis_prompt(query: str, chunks: list[SourceChunk]) -> str:
    context = _format_context(chunks) if chunks else "(No documentation context retrieved)"
    return f"""## Relevant Zscaler Documentation

{context}

---

## Log / Screenshot Input

{query}

---

Analyze the logs/screenshot above using the documentation context and provide:

### Identified Events
List each error, warning, or anomaly with its timestamp (if present) and a plain-English explanation.

### Root Cause
What is the underlying issue causing these events?

### Step-by-Step Resolution
Numbered steps to resolve the issue. Reference exact Zscaler settings, menu paths, and commands.

### Verification Steps
How to confirm the issue is resolved after applying the fix.

### References
Documentation sources used (title + URL)."""


# ── Main generate function ────────────────────────────────────────────────────

def generate(
    query: str,
    chunks: list[SourceChunk],
    provider_name: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    mode: str = "doc_search",
    original_images: Optional[list] = None,
) -> LLMResponse:
    """
    Generate a structured incident resolution or log analysis.

    Args:
        query:           The user's text (question or log content).
        chunks:          Retrieved documentation chunks from Qdrant.
        provider_name:   LLM provider ("groq", "openrouter", "deepseek", "ollama").
        model:           Model name within the provider.
        temperature:     Sampling temperature (lower = more deterministic).
        max_tokens:      Maximum response tokens.
        mode:            "doc_search" (default) or "log_analysis".
        original_images: List of image_url content blocks from a vision message.
                         If set, they are appended to the user message so a
                         vision-capable model can see the screenshot.
    """
    from config import cfg

    provider    = get_provider(provider_name or cfg.DEFAULT_PROVIDER)
    model       = model or cfg.DEFAULT_MODEL
    system_prompt = LOG_ANALYSIS_SYSTEM_PROMPT if mode == "log_analysis" else SYSTEM_PROMPT

    # Build the RAG-augmented prompt text
    prompt_text = (
        _build_log_analysis_prompt(query, chunks)
        if mode == "log_analysis"
        else _build_rag_prompt(query, chunks)
    )

    # Vision: combine text prompt + original image blocks into a list content
    if original_images:
        user_content: list | str = [{"type": "text", "text": prompt_text}] + original_images
    else:
        user_content = prompt_text

    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user",   content=user_content),
    ]

    return provider.complete(messages, model=model, temperature=temperature, max_tokens=max_tokens)


def format_sources_footer(chunks: list[SourceChunk]) -> str:
    """Build a collapsible source reference block appended to every response."""
    if not chunks:
        return ""
    lines = ["\n\n---\n\n**Sources retrieved:**\n"]
    seen_urls = set()
    for c in chunks:
        if c.url not in seen_urls:
            lines.append(f"- [{c.title}]({c.url}) — score: `{c.score}`")
            seen_urls.add(c.url)
    return "\n".join(lines)
