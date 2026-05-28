"""
Pydantic models for the OpenAI-compatible FastAPI endpoints.
OpenWebUI (and any OpenAI SDK client) connects to these endpoints without modification.
"""

from typing import Any, Literal, Optional
from pydantic import BaseModel


# ── OpenAI-compatible request/response ──────────────────────────────────────

class ChatMessageRequest(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "zscaler-rag/groq-llama3-70b"
    messages: list[ChatMessageRequest]
    temperature: float = 0.3
    max_tokens: int = 2048
    stream: bool = False
    # Custom RAG parameters — passed as extra fields by advanced users
    top_k: int = 5
    product_filter: Optional[str] = None  # "zia" | "zpa" | "zdx" | None


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: dict[str, str]
    finish_reason: str = "stop"


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: UsageInfo


# ── /v1/models ───────────────────────────────────────────────────────────────

class ModelCard(BaseModel):
    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = "zscaler-rag"


class ModelListResponse(BaseModel):
    object: str = "list"
    data: list[ModelCard]


# ── Internal / health ────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    qdrant_connected: bool
    collection: str
    chunks_indexed: int


class StatsResponse(BaseModel):
    collection: str
    vectors_count: int
    points_count: int
    status: str


# ── /v1/status ───────────────────────────────────────────────────────────────

class ServicesStatus(BaseModel):
    qdrant: bool
    crawl4ai: bool


class KnowledgeBaseStatus(BaseModel):
    pages_crawled: int
    pages_indexed: int
    pages_stale: int
    by_product: dict[str, int]


class QdrantStatus(BaseModel):
    points: int
    status: str


class ConfigStatus(BaseModel):
    embedding_model: str
    chunk_size: int
    top_k: int


class StatusResponse(BaseModel):
    services: ServicesStatus
    knowledge_base: KnowledgeBaseStatus
    qdrant: QdrantStatus
    config: ConfigStatus
