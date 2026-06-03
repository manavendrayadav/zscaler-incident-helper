"""
Upsert text chunks and their embeddings into Qdrant.
Supports both dense-only and hybrid (dense+sparse) collections.
Chunk IDs are deterministic (MD5 of url|section|idx) — safe to upsert repeatedly.
"""

import json
import time
from typing import Any, Union

import numpy as np
from rich.console import Console

from config import cfg

console = Console(highlight=False, emoji=False)


def _get_client():
    from qdrant_client import QdrantClient

    # timeout=120s: default 5s is too short for large batch upserts (13k+ vectors)
    return QdrantClient(host=cfg.QDRANT_HOST, port=cfg.QDRANT_PORT, timeout=120)


def ensure_collection(client=None) -> None:
    """Create the Qdrant collection if it doesn't exist."""
    from qdrant_client.models import Distance, VectorParams

    client = client or _get_client()
    existing = [c.name for c in client.get_collections().collections]
    if cfg.COLLECTION_NAME not in existing:
        if cfg.SPARSE_ENABLED:
            from qdrant_client.models import SparseIndexParams, SparseVectorParams

            client.create_collection(
                collection_name=cfg.COLLECTION_NAME,
                vectors_config={
                    "dense": VectorParams(size=cfg.EMBEDDING_DIM, distance=Distance.COSINE),
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams(index=SparseIndexParams()),
                },
            )
            console.print(
                f"[green]OK[/] Created hybrid collection: [bold]{cfg.COLLECTION_NAME}[/] (dense={cfg.EMBEDDING_DIM}d + sparse)"
            )
        else:
            client.create_collection(
                collection_name=cfg.COLLECTION_NAME,
                vectors_config=VectorParams(size=cfg.EMBEDDING_DIM, distance=Distance.COSINE),
            )
            console.print(
                f"[green]OK[/] Created collection: [bold]{cfg.COLLECTION_NAME}[/] (dense={cfg.EMBEDDING_DIM}d)"
            )
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


def _upsert_with_retry(
    client,
    collection_name: str,
    points,
    retries: int = 3,
    delay: float = 5.0,
) -> None:
    """Upsert with retry + fresh connection on failure (handles stale connections after long CPU embedding)."""
    for attempt in range(retries):
        try:
            client.upsert(collection_name=collection_name, points=points)
            return
        except Exception as e:
            if attempt < retries - 1:
                console.print(
                    f"  [yellow]Upsert attempt {attempt + 1} failed ({e}), "
                    f"retrying in {delay}s with fresh connection…[/yellow]"
                )
                time.sleep(delay)
                client = _get_client()  # fresh connection avoids stale HTTP state
            else:
                raise


def upsert_chunks(
    chunks: list[dict[str, Any]],
    embeddings: Union[np.ndarray, dict],
    client=None,
    batch_size: int = 32,  # 32 keeps each HTTP call well under timeout; was 64
) -> list[str]:
    """
    Upsert chunks into Qdrant. Accepts dense-only (ndarray) or hybrid (dict) embeddings.
    Returns list of inserted point IDs.
    """
    from qdrant_client.models import PointStruct

    is_hybrid = isinstance(embeddings, dict)
    if is_hybrid:
        dense_vecs = embeddings["dense"]  # (N, DIM)
        sparse_vecs = embeddings["sparse"]  # list of N dicts {token_id: weight}
    else:
        dense_vecs = embeddings
        sparse_vecs = None

    client = client or _get_client()
    point_ids = []

    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i : i + batch_size]
        batch_dense = dense_vecs[i : i + batch_size]
        batch_sparse = sparse_vecs[i : i + batch_size] if sparse_vecs is not None else None

        points = []
        for j, (chunk, vec) in enumerate(zip(batch_chunks, batch_dense)):
            cid = chunk["chunk_id"]
            payload = {"text": chunk["text"], **chunk["metadata"]}

            if is_hybrid and batch_sparse is not None:
                from qdrant_client.models import SparseVector

                sw = batch_sparse[j]  # {token_id_str: weight}
                indices = [int(k) for k in sw]
                values = [float(v) for v in sw.values()]
                points.append(
                    PointStruct(
                        id=cid,
                        vector={
                            "dense": vec.tolist(),
                            "sparse": SparseVector(indices=indices, values=values),
                        },
                        payload=payload,
                    )
                )
            else:
                points.append(PointStruct(id=cid, vector=vec.tolist(), payload=payload))

            point_ids.append(cid)

        _upsert_with_retry(client, cfg.COLLECTION_NAME, points)

    return point_ids


def get_collection_stats(client=None) -> dict:
    """Return basic stats about the collection."""
    client = client or _get_client()
    try:
        info = client.get_collection(cfg.COLLECTION_NAME)
        vectors = (
            getattr(info, "indexed_vectors_count", None) or getattr(info, "vectors_count", 0) or 0
        )
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
