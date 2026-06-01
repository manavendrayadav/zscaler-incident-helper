"""
Semantic retrieval from Qdrant with cross-encoder re-ranking.

Pipeline:
  1. Embed query (dense vector, or dense+sparse for bge-m3 hybrid)
  2. Fetch top-N candidates from Qdrant (4× top_k, max 20)
     - Hybrid: prefetch dense + sparse, merge with RRF fusion
     - Dense-only: standard cosine search
  3. Re-rank with cross-encoder (ms-marco-MiniLM-L-6-v2)
  4. Filter out chunks below cfg.MIN_SCORE
  5. Return top_k results
"""

from dataclasses import dataclass

from config import cfg
from pipeline.embedder import embed_query


@dataclass
class SourceChunk:
    chunk_id: str
    text: str
    url: str
    title: str
    product: str
    section: str
    score: float  # cosine similarity, 0–1


_reranker = None
_qdrant_client = None


def _get_qdrant_client():
    """Return a module-level cached QdrantClient (avoids new connection pool per query)."""
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        _qdrant_client = QdrantClient(host=cfg.QDRANT_HOST, port=cfg.QDRANT_PORT, timeout=30)
    return _qdrant_client


def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _reranker


def _hits_to_chunks(hits) -> list[SourceChunk]:
    chunks = []
    for hit in hits:
        payload = hit.payload or {}
        chunks.append(SourceChunk(
            chunk_id=str(hit.id),
            text=payload.get("text", ""),
            url=payload.get("url", ""),
            title=payload.get("title", ""),
            product=payload.get("product", ""),
            section=payload.get("section", ""),
            score=round(hit.score, 4),
        ))
    return chunks


def _search_dense(client, query_vector: list[float], limit: int, search_filter) -> list[SourceChunk]:
    response = client.query_points(
        collection_name=cfg.COLLECTION_NAME,
        query=query_vector,
        limit=limit,
        query_filter=search_filter,
        with_payload=True,
    )
    return _hits_to_chunks(response.points)


def _search_hybrid(client, query: dict, limit: int, search_filter) -> list[SourceChunk]:
    """Dense + sparse with RRF fusion via Qdrant's native hybrid search."""
    from qdrant_client.models import Fusion, FusionQuery, Prefetch, SparseVector

    dense_vec = query["dense"]
    sparse_w = query["sparse"]
    indices = [int(k) for k in sparse_w]
    values = [float(v) for v in sparse_w.values()]

    response = client.query_points(
        collection_name=cfg.COLLECTION_NAME,
        prefetch=[
            Prefetch(query=dense_vec, using="dense", limit=limit),
            Prefetch(query=SparseVector(indices=indices, values=values), using="sparse", limit=limit),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=limit,
        query_filter=search_filter,
        with_payload=True,
    )
    return _hits_to_chunks(response.points)


def retrieve(
    query: str,
    top_k: int | None = None,
    product_filter: str | None = None,
) -> list[SourceChunk]:
    """
    Embed the query, fetch candidates from Qdrant, re-rank, and return top_k.

    Args:
        query: The user's incident description or question.
        top_k: Number of chunks to return (defaults to cfg.TOP_K).
        product_filter: Optional Zscaler product slug to restrict results
                        (e.g. "zia", "zpa", "zdx").
    """
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    top_k = top_k or cfg.TOP_K
    query_embedding = embed_query(query)
    client = _get_qdrant_client()

    search_filter = None
    if product_filter:
        search_filter = Filter(
            must=[FieldCondition(key="product", match=MatchValue(value=product_filter))]
        )

    candidate_limit = min(top_k * 4, 20)

    if isinstance(query_embedding, dict):
        candidates = _search_hybrid(client, query_embedding, candidate_limit, search_filter)
    else:
        candidates = _search_dense(client, query_embedding, candidate_limit, search_filter)

    if not candidates:
        return []

    # Re-rank with cross-encoder if we have more candidates than needed
    if len(candidates) > top_k:
        reranker = _get_reranker()
        ce_scores = reranker.predict([(query, c.text) for c in candidates])
        ranked = sorted(zip(ce_scores, candidates), key=lambda x: -x[0])
        candidates = [c for _, c in ranked]

    # Apply minimum relevance threshold (on original Qdrant cosine scores)
    candidates = [c for c in candidates if c.score >= cfg.MIN_SCORE]

    return candidates[:top_k]
