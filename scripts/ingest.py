"""
Full ingestion pipeline:
  1. Load crawled Markdown files from data/raw/
  2. Chunk each file (header split -> recursive split)
  3. Embed all chunks with sentence-transformers (local, no API cost)
     Embeddings are cached to data/embeddings_cache.npz so a failed upsert
     never requires re-running the 4-hour bge-m3 computation.
  4. Upsert into Qdrant with metadata
  5. Write chunk IDs back to the crawl manifest (for incremental re-indexing)

Usage:
  python scripts/ingest.py               # index all files in data/raw/
  python scripts/ingest.py --reset       # wipe collection and re-index from scratch
  python scripts/ingest.py --skip-embed  # skip embedding, use cached embeddings
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from rich.console import Console
from rich.table import Table

from config import cfg
from pipeline.chunker import chunk_all_files
from pipeline.embedder import embed_chunks
from pipeline.indexer import (
    check_qdrant_reachable,
    ensure_collection,
    get_collection_stats,
    update_manifest_chunk_ids,
    upsert_chunks,
)

console = Console()

EMBED_CACHE = cfg.RAW_DIR.parent / "embeddings_cache.npz"


def load_manifest() -> dict:
    if cfg.MANIFEST_FILE.exists():
        return json.loads(cfg.MANIFEST_FILE.read_text(encoding="utf-8"))
    return {}


def reset_collection():
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams

    client = QdrantClient(host=cfg.QDRANT_HOST, port=cfg.QDRANT_PORT, timeout=120)
    existing = [c.name for c in client.get_collections().collections]
    if cfg.COLLECTION_NAME in existing:
        client.delete_collection(cfg.COLLECTION_NAME)
        console.print(f"[yellow]WARN Deleted collection:[/] {cfg.COLLECTION_NAME}")
    client.create_collection(
        collection_name=cfg.COLLECTION_NAME,
        vectors_config=VectorParams(size=cfg.EMBEDDING_DIM, distance=Distance.COSINE),
    )
    console.print(f"[green]OK Re-created collection:[/] {cfg.COLLECTION_NAME}")


def _save_embed_cache(chunks: list, embeddings) -> None:
    """Save embeddings to disk so a failed upsert doesn't require re-embedding."""
    try:
        chunk_ids = [c["chunk_id"] for c in chunks]
        if isinstance(embeddings, dict):
            np.savez_compressed(
                EMBED_CACHE,
                dense=embeddings["dense"],
                chunk_ids=chunk_ids,
                mode=["hybrid"],
            )
            # Sparse weights can't go into npz directly — save as json sidecar
            sparse_path = EMBED_CACHE.with_suffix(".sparse.json")
            import json as _json

            # Convert numpy float32 → Python float before JSON dump (float32 is not JSON serializable)
            sparse_path.write_text(
                _json.dumps([{k: float(v) for k, v in row.items()} for row in embeddings["sparse"]]),
                encoding="utf-8",
            )
        else:
            np.savez_compressed(EMBED_CACHE, dense=embeddings, chunk_ids=chunk_ids, mode=["dense"])
        console.print(f"  [dim]Embedding cache saved → {EMBED_CACHE}[/dim]")
    except Exception as e:
        console.print(f"  [yellow]WARN Could not save embedding cache: {e}[/yellow]")


def _load_embed_cache(chunks: list):
    """
    Load cached embeddings if available and chunk IDs match.
    Returns (embeddings, hit) where hit=True if cache was valid.
    """
    if not EMBED_CACHE.exists():
        return None, False
    try:
        data = np.load(EMBED_CACHE, allow_pickle=False)
        cached_ids = list(data["chunk_ids"])
        current_ids = [c["chunk_id"] for c in chunks]
        if cached_ids != current_ids:
            console.print(
                "  [yellow]Embedding cache chunk IDs don't match — re-embedding.[/yellow]"
            )
            return None, False
        mode = str(data["mode"][0])
        if mode == "hybrid":
            sparse_path = EMBED_CACHE.with_suffix(".sparse.json")
            if not sparse_path.exists():
                return None, False
            import json as _json

            sparse = _json.loads(sparse_path.read_text(encoding="utf-8"))
            return {"dense": data["dense"], "sparse": sparse}, True
        else:
            return data["dense"], True
    except Exception as e:
        console.print(f"  [yellow]Could not load embedding cache: {e}[/yellow]")
        return None, False


def main(reset: bool = False, skip_embed: bool = False):
    console.rule("[bold cyan]Zscaler RAG — Ingestion Pipeline[/]")

    # ── 0. Pre-flight: Qdrant must be reachable before we do anything ─────
    check_qdrant_reachable()

    # ── 1. Qdrant setup ───────────────────────────────────────────────────
    if reset:
        reset_collection()
    else:
        ensure_collection()

    # ── 2. Load and chunk all crawled markdown files ──────────────────────
    console.print("\n[bold]Step 1/3:[/] Loading and chunking crawled pages…")
    t0 = time.time()

    try:
        chunks = chunk_all_files()
    except FileNotFoundError as e:
        console.print(f"[red]FAIL {e}[/red]")
        sys.exit(1)

    console.print(f"  -> {len(chunks)} chunks from {len(list(cfg.RAW_DIR.glob('*.md')))} files")
    console.print(
        f"  -> Avg chunk size: {sum(len(c['text']) for c in chunks) // len(chunks)} chars"
    )

    # ── 3. Embed ──────────────────────────────────────────────────────────
    console.print("\n[bold]Step 2/3:[/] Generating embeddings (local, no API cost)…")

    embeddings = None
    if skip_embed:
        embeddings, hit = _load_embed_cache(chunks)
        if hit:
            console.print("  [green]Using cached embeddings (--skip-embed)[/green]")
        else:
            console.print("  [yellow]Cache miss — running full embedding[/yellow]")

    if embeddings is None:
        # Try loading cache automatically before running expensive embedding
        embeddings, hit = _load_embed_cache(chunks)
        if hit:
            console.print(
                "  [green]Loaded embeddings from cache (skipping ~4h computation)[/green]"
            )
        else:
            embeddings = embed_chunks(chunks)
            _save_embed_cache(chunks, embeddings)

    if isinstance(embeddings, dict):
        shape_str = f"dense={embeddings['dense'].shape}"
    else:
        shape_str = str(embeddings.shape)
    console.print(f"  -> Embedding shape: {shape_str} ({cfg.EMBEDDING_MODEL})")

    # ── 4. Upsert into Qdrant ─────────────────────────────────────────────
    console.print("\n[bold]Step 3/3:[/] Upserting into Qdrant…")
    point_ids = upsert_chunks(chunks, embeddings)
    console.print(f"  -> Upserted {len(point_ids)} points")

    # Delete cache after successful upsert (no longer needed)
    try:
        if EMBED_CACHE.exists():
            EMBED_CACHE.unlink()
        sparse_path = EMBED_CACHE.with_suffix(".sparse.json")
        if sparse_path.exists():
            sparse_path.unlink()
    except Exception:
        pass

    # ── 5. Update manifest with chunk IDs ─────────────────────────────────
    url_chunk_map: dict[str, list[str]] = defaultdict(list)
    for chunk, pid in zip(chunks, point_ids):
        url_chunk_map[chunk["metadata"]["url"]].append(pid)

    manifest = load_manifest()
    update_manifest_chunk_ids(manifest, url_chunk_map)

    elapsed = round(time.time() - t0, 1)

    # ── Summary table ─────────────────────────────────────────────────────
    stats = get_collection_stats()
    table = Table(title="Ingestion Summary", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Files processed", str(len(list(cfg.RAW_DIR.glob("*.md")))))
    table.add_row("Chunks created", str(len(chunks)))
    table.add_row("Vectors in Qdrant", str(stats.get("points_count", len(point_ids))))
    table.add_row("Embedding model", cfg.EMBEDDING_MODEL)
    table.add_row("Embedding dim", str(cfg.EMBEDDING_DIM))
    table.add_row("Elapsed", f"{elapsed}s")
    console.print(table)

    console.print(
        "\n[bold green]OK Ingestion complete![/] "
        "Start the API with [cyan]docker-compose up -d rag-api[/] "
        "and open [cyan]http://localhost:3000[/] in OpenWebUI."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest crawled Zscaler docs into Qdrant")
    parser.add_argument(
        "--reset", action="store_true", help="Wipe and re-create the Qdrant collection first"
    )
    parser.add_argument(
        "--skip-embed", action="store_true", help="Skip embedding step, use cached embeddings"
    )
    args = parser.parse_args()
    main(reset=args.reset, skip_embed=args.skip_embed)
