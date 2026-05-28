"""
Build a RAG prompt from retrieved chunks and generate an incident resolution
using the chosen LLM provider.
"""

from llm.base import Message, LLMResponse
from llm.factory import get_provider
from rag.retriever import SourceChunk

SYSTEM_PROMPT = """You are a senior Zscaler security engineer with deep expertise in \
ZIA (Zscaler Internet Access), ZPA (Zscaler Private Access), ZDX, and Zscaler Client Connector. \
You help security engineering teams diagnose and resolve Zscaler-related incidents quickly and accurately.

When answering:
- Be specific — name exact Zscaler settings, menu paths, CLI commands, and log locations.
- Always base your answer on the provided documentation context.
- If the context doesn't cover the issue, say so and suggest what additional information \
  the team should gather.
- Format your response in clean Markdown."""


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


def generate(
    query: str,
    chunks: list[SourceChunk],
    provider_name: str | None = None,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> LLMResponse:
    """
    Generate a structured incident resolution.

    Args:
        query: The raw user message (incident description).
        chunks: Retrieved documentation chunks from Qdrant.
        provider_name: LLM provider ("groq", "openrouter", "deepseek", "ollama").
        model: Model name within the provider.
        temperature: Sampling temperature (lower = more deterministic).
        max_tokens: Maximum response tokens.
    """
    from config import cfg

    provider = get_provider(provider_name or cfg.DEFAULT_PROVIDER)
    model = model or cfg.DEFAULT_MODEL

    messages = [
        Message(role="system", content=SYSTEM_PROMPT),
        Message(role="user", content=_build_rag_prompt(query, chunks)),
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
