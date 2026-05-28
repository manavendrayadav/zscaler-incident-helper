"""
Semantic retrieval from Qdrant.
Embeds the query using the same model used at index time, then finds the
closest chunks using cosine similarity.
"""

from dataclasses import dataclass
from typing import Optional

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


def retrieve(
    query: str,
    top_k: int | None = None,
    product_filter: str | None = None,
) -> list[SourceChunk]:
    """
    Embed the query and return the top-k most relevant chunks from Qdrant.

    Args:
        query: The user's incident description or question.
        top_k: Number of chunks to retrieve (defaults to cfg.TOP_K).
        product_filter: Optional Zscaler product slug to restrict results
                        (e.g. "zia", "zpa", "zdx").
    """
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    top_k = top_k or cfg.TOP_K
    client = QdrantClient(host=cfg.QDRANT_HOST, port=cfg.QDRANT_PORT)

    query_vector = embed_query(query)

    search_filter = None
    if product_filter:
        search_filter = Filter(
            must=[FieldCondition(key="product", match=MatchValue(value=product_filter))]
        )

    # qdrant-client >= 1.9 uses query_points(); older versions used search()
    response = client.query_points(
        collection_name=cfg.COLLECTION_NAME,
        query=query_vector,
        limit=top_k,
        query_filter=search_filter,
        with_payload=True,
    )
    results = response.points

    chunks = []
    for hit in results:
        payload = hit.payload or {}
        chunks.append(
            SourceChunk(
                chunk_id=str(hit.id),
                text=payload.get("text", ""),
                url=payload.get("url", ""),
                title=payload.get("title", ""),
                product=payload.get("product", ""),
                section=payload.get("section", ""),
                score=round(hit.score, 4),
            )
        )

    return chunks
