"""
Generate embeddings for text chunks using a local sentence-transformers model.
No API cost — runs entirely on the host machine.
"""

from typing import Any
import numpy as np
from rich.console import Console

from config import cfg

console = Console(highlight=False, emoji=False)

_model = None  # lazy-loaded singleton


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        console.print(f"[dim]Loading embedding model: {cfg.EMBEDDING_MODEL}...[/dim]")
        _model = SentenceTransformer(cfg.EMBEDDING_MODEL)
    return _model


def embed_texts(texts: list[str], batch_size: int = 32, show_progress: bool = True) -> np.ndarray:
    """Encode a list of strings → float32 numpy array of shape (N, DIM)."""
    model = get_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=show_progress,
        normalize_embeddings=True,   # unit vectors → cosine ≡ dot product
        convert_to_numpy=True,
    )
    return embeddings.astype(np.float32)


def embed_chunks(chunks: list[dict[str, Any]], batch_size: int = 32) -> np.ndarray:
    """Convenience wrapper: extract texts from chunk dicts and embed them."""
    texts = [c["text"] for c in chunks]
    return embed_texts(texts, batch_size=batch_size)


def embed_query(query: str) -> list[float]:
    """Embed a single query string and return as a plain Python list."""
    vec = embed_texts([query], show_progress=False)[0]
    return vec.tolist()
