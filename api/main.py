"""
OpenAI-compatible FastAPI service for Zscaler RAG.
OpenWebUI connects to /v1/chat/completions exactly as it would to the OpenAI API.

Model naming convention:  zih/{provider}-{model-slug}
  e.g.  zih/groq-llama3-70b
        zih/openrouter-claude-3-5-sonnet
        zih/ollama-llama3
"""

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("zih.api")

from api.models import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ConfigStatus,
    HealthResponse,
    KnowledgeBaseStatus,
    ModelCard,
    ModelListResponse,
    QdrantStatus,
    ServicesStatus,
    StatsResponse,
    StatusResponse,
    UsageInfo,
)
from config import cfg
from llm.factory import all_models, list_providers
from pipeline.indexer import get_collection_stats
from rag.generator import format_sources_footer, generate
from rag.retriever import retrieve

# ── startup ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Security warnings ─────────────────────────────────────────────────────
    if cfg.API_KEY == "zih-api":
        logger.warning(
            "⚠️  API_KEY is set to the default 'zih-api'. "
            "Change it in .env before sharing access with a team. "
            "See docs/OPERATIONS.md §8 Configuration Reference."
        )

    # ── Pre-warm embedding model & validate dimension ─────────────────────────
    import pipeline.embedder as _embedder
    _embedder.get_model()
    # Validate that the loaded model's output dimension matches EMBEDDING_DIM.
    # A mismatch would cause silent wrong retrieval; catch it at startup instead.
    test_vec = _embedder.embed_query("startup-dimension-check")
    actual_dim = len(test_vec["dense"] if isinstance(test_vec, dict) else test_vec)
    if actual_dim != cfg.EMBEDDING_DIM:
        raise RuntimeError(
            f"Embedding dimension mismatch: model outputs {actual_dim}d "
            f"but EMBEDDING_DIM={cfg.EMBEDDING_DIM}. "
            f"Update EMBEDDING_DIM in .env and run make reset-db && make ingest."
        )

    yield


app = FastAPI(
    title="Zscaler RAG API",
    description="OpenAI-compatible RAG API for Zscaler incident resolution",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── auth ─────────────────────────────────────────────────────────────────────

def verify_api_key(authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "").strip()
    if not token or token != cfg.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── helpers ──────────────────────────────────────────────────────────────────

def _parse_model_id(model_id: str) -> tuple[str, str]:
    """
    Parse "zih/groq-llama3-70b" → ("groq", "llama-3.3-70b-versatile").
    Falls back to configured defaults if parsing fails.
    """
    # Strip prefix — support both current "zih/" and legacy "zscaler-rag/" for
    # backward compatibility with saved OpenWebUI conversations from before the rename
    model_id = model_id.replace("zih/", "").replace("zscaler-rag/", "")

    providers = list_providers()
    for provider in providers:
        if model_id.startswith(provider + "-") or model_id == provider:
            model_slug = model_id[len(provider) + 1:] if "-" in model_id[len(provider):] else ""
            # Map short slug back to full model name
            model_name = _slug_to_model(provider, model_slug) if model_slug else cfg.DEFAULT_MODEL
            return provider, model_name

    return cfg.DEFAULT_PROVIDER, cfg.DEFAULT_MODEL


def _slug_to_model(provider: str, slug: str) -> str:
    """Convert a URL-safe slug like 'llama3-70b' back to 'llama-3.3-70b-versatile'."""
    try:
        models = all_models().get(provider, [])
        # Exact match first
        if slug in models:
            return slug
        # Try replacing hyphens with dots / partial match
        for m in models:
            if slug.replace("-", "") in m.replace("-", "").replace(".", ""):
                return m
    except Exception:
        pass
    return slug  # return as-is if no match


def _extract_last_user_message(messages) -> tuple[str, list]:
    """
    Extract the most recent user message from the chat history.

    Returns:
        (text_content, image_blocks) where image_blocks is a list of
        OpenAI vision image_url content blocks (may be empty).
    """
    for msg in reversed(messages):
        if msg.role == "user":
            if isinstance(msg.content, str):
                return msg.content, []
            # OpenAI vision format: list of content blocks
            text = " ".join(
                b.get("text", "") for b in msg.content if b.get("type") == "text"
            )
            images = [b for b in msg.content if b.get("type") == "image_url"]
            return text, images
    return "", []


# ── routes ───────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
def health():
    try:
        stats = get_collection_stats()
        qdrant_ok = stats["status"] != "not_found" or stats["points_count"] >= 0
        return HealthResponse(
            status="ok",
            qdrant_connected=qdrant_ok,
            collection=cfg.COLLECTION_NAME,
            chunks_indexed=stats.get("points_count", 0),
        )
    except Exception as e:
        return HealthResponse(
            status=f"degraded: {e}",
            qdrant_connected=False,
            collection=cfg.COLLECTION_NAME,
            chunks_indexed=0,
        )


@app.get("/stats", response_model=StatsResponse)
def stats():
    s = get_collection_stats()
    return StatsResponse(collection=cfg.COLLECTION_NAME, **s)


@app.get("/v1/status", response_model=StatusResponse)
def status():
    """Comprehensive system status — services, knowledge base, Qdrant, config."""

    def _ping(url: str) -> bool:
        try:
            r = httpx.get(url, timeout=3.0, follow_redirects=True)
            return r.status_code < 500
        except Exception:
            return False

    # Service reachability
    qdrant_ok = _ping(f"http://{cfg.QDRANT_HOST}:{cfg.QDRANT_PORT}/health")
    crawl4ai_ok = _ping(f"{cfg.CRAWL4AI_BASE_URL}/health")

    # Qdrant collection stats
    qdrant_stats = get_collection_stats()

    # Manifest analysis
    pages_crawled = 0
    pages_indexed = 0
    pages_stale = 0
    by_product: dict[str, int] = {}

    if cfg.MANIFEST_FILE.exists():
        manifest = json.loads(cfg.MANIFEST_FILE.read_text(encoding="utf-8"))
        for entry in manifest.values():
            pages_crawled += 1
            product = entry.get("product", "unknown")
            by_product[product] = by_product.get(product, 0) + 1
            if entry.get("chunk_ids"):
                pages_indexed += 1
            last_crawled = entry.get("last_crawled", "")
            sitemap_lastmod = entry.get("sitemap_lastmod", "")
            if sitemap_lastmod and last_crawled:
                if sitemap_lastmod[:10] > last_crawled[:10]:
                    pages_stale += 1

    return StatusResponse(
        services=ServicesStatus(qdrant=qdrant_ok, crawl4ai=crawl4ai_ok),
        knowledge_base=KnowledgeBaseStatus(
            pages_crawled=pages_crawled,
            pages_indexed=pages_indexed,
            pages_stale=pages_stale,
            by_product=by_product,
        ),
        qdrant=QdrantStatus(
            points=qdrant_stats.get("points_count", 0),
            status=qdrant_stats.get("status", "unknown"),
        ),
        config=ConfigStatus(
            embedding_model=cfg.EMBEDDING_MODEL,
            chunk_size=cfg.CHUNK_SIZE,
            top_k=cfg.TOP_K,
        ),
    )


@app.get("/v1/models", response_model=ModelListResponse)
def list_models(_=Depends(verify_api_key)):
    """Return all available model IDs in OpenAI format for OpenWebUI to discover."""
    cards = []
    ts = int(time.time())
    for provider, models in all_models().items():
        for model in models:
            slug = model.replace(".", "-").replace("/", "-").replace("_", "-")
            cards.append(
                ModelCard(id=f"zih/{provider}-{slug}", created=ts)
            )
    return ModelListResponse(data=cards)


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
def chat_completions(req: ChatCompletionRequest, _=Depends(verify_api_key)):
    """
    Main RAG endpoint.
    1. Extract the latest user message.
    2. Retrieve top-k relevant Zscaler doc chunks from Qdrant.
    3. Call the chosen LLM with a RAG-augmented prompt.
    4. Return an OpenAI-format response with sources appended.
    """
    from rag.log_parser import detect_product_from_logs, extract_log_signals, is_log_content

    # Streaming is not yet implemented — reject early rather than silently ignoring
    if req.stream:
        raise HTTPException(
            status_code=501,
            detail="Streaming responses (stream=true) are not yet supported. Set stream=false.",
        )

    query, images = _extract_last_user_message(req.messages)
    if not query and not images:
        raise HTTPException(status_code=400, detail="No user message found in messages array")

    provider_name, model_name = _parse_model_id(req.model)

    # ── Mode detection ────────────────────────────────────────────────────────
    if images:
        # Screenshot or image attached → vision log analysis (Ollama-only for privacy)
        mode = "log_analysis"
        retrieval_query = query or "zscaler error log troubleshooting"
    elif is_log_content(query):
        # Pasted text log → log analysis mode; extract concise search signals
        mode = "log_analysis"
        retrieval_query = extract_log_signals(query)
        if not req.product_filter:
            req.product_filter = detect_product_from_logs(query)
    else:
        # Normal question → standard doc_search mode (unchanged behaviour)
        mode = "doc_search"
        retrieval_query = query

    # Retrieve
    try:
        chunks = retrieve(retrieval_query, top_k=req.top_k, product_filter=req.product_filter)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Qdrant retrieval failed: {e}. Is Qdrant running and indexed?",
        )

    prompt_tokens = 0
    completion_tokens = 0

    if not chunks and mode == "doc_search":
        answer = (
            "No relevant Zscaler documentation found for this query. "
            "The knowledge base may not yet contain information about this topic. "
            "Try running `make crawl && make ingest` to index more pages, "
            "or describe your issue with different keywords."
        )
        sources_footer = ""
    else:
        # Generate — pass mode + images so the right system prompt and vision content are used
        try:
            llm_resp = generate(
                query=query,
                chunks=chunks,
                provider_name=provider_name,
                model=model_name,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                mode=mode,
                original_images=images or None,
            )
            answer = llm_resp.content
            sources_footer = format_sources_footer(chunks)
            prompt_tokens = llm_resp.prompt_tokens
            completion_tokens = llm_resp.completion_tokens
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"LLM generation failed ({provider_name}/{model_name}): {e}",
            )

    full_answer = answer + sources_footer

    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:16]}",
        created=int(time.time()),
        model=req.model,
        choices=[
            ChatCompletionChoice(
                message={"role": "assistant", "content": full_answer}
            )
        ],
        usage=UsageInfo(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )
