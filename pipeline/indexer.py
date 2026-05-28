"""
Upsert text chunks and their embeddings into Qdrant.
Supports incremental updates: re-index only changed pages by deleting old chunk IDs
and inserting new ones. Chunk IDs are stored back into the crawl manifest.
"""

import json
import uuid
from typing import Any

import numpy as np
from rich.console import Console

from config import cfg

console = Console(highlight=False, emoji=False)


def _get_client():
    from qdrant_client import QdrantClient
    return QdrantClient(host=cfg.QDRANT_HOST, port=cfg.QDRANT_PORT)


def ensure_collection(client=None) -> None:
    """Create the Qdrant collection if it doesn't exist."""
    from qdrant_client.models import Distance, VectorParams

    client = client or _get_client()
    existing = [c.name for c in client.get_collections().collections]
    if cfg.COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=cfg.COLLECTION_NAME,
            vectors_config=VectorParams(size=cfg.EMBEDDING_DIM, distance=Distance.COSINE),
        )
        console.print(f"[green]OK[/] Created Qdrant collection: [bold]{cfg.COLLECTION_NAME}[/]")
    else:
        console.print(f"[dim]Collection '{cfg.COLLECTION_NAME}' already exists.[/dim]")


def delete_chunks_by_ids(chunk_ids: list[str], client=None) -> None:
    """Remove specific points from Qdrant (used during incremental re-index)."""
    from qdrant_client.models import PointIdsList

    if not chunk_ids:
        return
    client = client or _get_client()
    client.delete(
        collection_name=cfg.COLLECTION_NAME,
        points_selector=PointIdsList(points=chunk_ids),
    )


def upsert_chunks(
    chunks: list[dict[str, Any]],
    embeddings: np.ndarray,
    client=None,
    batch_size: int = 64,
) -> list[str]:
    """
    Upsert chunks into Qdrant. Returns list of inserted point IDs (UUIDs).
    Each chunk dict must have keys: chunk_id, text, metadata.
    """
    from qdrant_client.models import PointStruct

    client = client or _get_client()
    point_ids = []

    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i : i + batch_size]
        batch_vecs = embeddings[i : i + batch_size]

        points = []
        for chunk, vec in zip(batch_chunks, batch_vecs):
            cid = chunk["chunk_id"]
            points.append(
                PointStruct(
                    id=cid,
                    vector=vec.tolist(),
                    payload={
                        "text": chunk["text"],
                        **chunk["metadata"],
                    },
                )
            )
            point_ids.append(cid)

        client.upsert(collection_name=cfg.COLLECTION_NAME, points=points)

    return point_ids


def get_collection_stats(client=None) -> dict:
    """Return basic stats about the collection."""
    client = client or _get_client()
    try:
        info = client.get_collection(cfg.COLLECTION_NAME)
        # vectors_count was removed in qdrant-client >= 1.9; use indexed_vectors_count
        vectors = getattr(info, "indexed_vectors_count", None) or getattr(info, "vectors_count", 0) or 0
        return {
            "vectors_count": vectors,
            "points_count": info.points_count or 0,
            "status": str(info.status),
        }
    except Exception:
        return {"vectors_count": 0, "points_count": 0, "status": "not_found"}


def update_manifest_chunk_ids(manifest: dict, url_chunk_map: dict[str, list[str]]) -> None:
    """Write chunk_ids back into the crawl manifest after indexing."""
    for url, chunk_ids in url_chunk_map.items():
        if url in manifest:
            manifest[url]["chunk_ids"] = chunk_ids

    if cfg.MANIFEST_FILE.exists():
        with open(cfg.MANIFEST_FILE, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
