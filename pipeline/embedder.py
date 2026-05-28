"""
Embeddings using BAAI/bge-m3 (dense + sparse hybrid) when SPARSE_ENABLED=true,
or any sentence-transformers model for dense-only mode.

bge-m3 returns:
  dense_vecs  — (N, 1024) float32 array for semantic similarity
  lexical_weights — list[dict{token_id: weight}] for keyword/BM25-style matching
"""

from typing import Any, Union
import numpy as np
from rich.console import Console

from config import cfg

console = Console(highlight=False, emoji=False)

_model = None


def _is_bge_m3() -> bool:
    return cfg.SPARSE_ENABLED and cfg.EMBEDDING_MODEL == "BAAI/bge-m3"


def get_model():
    global _model
    if _model is None:
        if _is_bge_m3():
            from FlagEmbedding import BGEM3FlagModel
            console.print(f"[dim]Loading embedding model: {cfg.EMBEDDING_MODEL} (dense+sparse)...[/dim]")
            _model = BGEM3FlagModel(cfg.EMBEDDING_MODEL, use_fp16=True)
        else:
            from sentence_transformers import SentenceTransformer
            console.print(f"[dim]Loading embedding model: {cfg.EMBEDDING_MODEL}...[/dim]")
            _model = SentenceTransformer(cfg.EMBEDDING_MODEL)
    return _model


def embed_texts(
    texts: list[str],
    batch_size: int = 32,
    show_progress: bool = True,
) -> Union[np.ndarray, dict]:
    """
    Encode a list of strings.

    Returns:
      - Dense-only: float32 ndarray shape (N, DIM)
      - Hybrid (bge-m3): dict {"dense": ndarray (N, 1024), "sparse": list[dict{str: float}]}
    """
    model = get_model()
    if _is_bge_m3():
        out = model.encode(
            texts,
            batch_size=batch_size,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        return {
            "dense": out["dense_vecs"].astype(np.float32),
            "sparse": out["lexical_weights"],
        }
    else:
        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return embeddings.astype(np.float32)


def embed_chunks(chunks: list[dict[str, Any]], batch_size: int = 32) -> Union[np.ndarray, dict]:
    """Convenience wrapper: extract texts from chunk dicts and embed them."""
    texts = [c["text"] for c in chunks]
    return embed_texts(texts, batch_size=batch_size)


def embed_query(query: str) -> Union[list[float], dict]:
    """
    Embed a single query string.

    Returns:
      - Dense-only: list[float]
      - Hybrid (bge-m3): dict {"dense": list[float], "sparse": dict{str: float}}
    """
    result = embed_texts([query], batch_size=1, show_progress=False)
    if isinstance(result, dict):
        return {
            "dense": result["dense"][0].tolist(),
            "sparse": result["sparse"][0],
        }
    return result[0].tolist()
