"""
Full ingestion pipeline:
  1. Load crawled Markdown files from data/raw/
  2. Chunk each file (header split -> recursive split)
  3. Embed all chunks with sentence-transformers (local, no API cost)
  4. Upsert into Qdrant with metadata
  5. Write chunk IDs back to the crawl manifest (for incremental re-indexing)

Usage:
  python scripts/ingest.py               # index all files in data/raw/
  python scripts/ingest.py --reset       # wipe collection and re-index from scratch
"""

import argparse
import json
import sys
import time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table

from config import cfg
from pipeline.chunker import chunk_all_files
from pipeline.embedder import embed_chunks
from pipeline.indexer import (
    ensure_collection,
    upsert_chunks,
    get_collection_stats,
    update_manifest_chunk_ids,
)

console = Console()


def load_manifest() -> dict:
    if cfg.MANIFEST_FILE.exists():
        return json.loads(cfg.MANIFEST_FILE.read_text(encoding="utf-8"))
    return {}


def reset_collection():
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams

    client = QdrantClient(host=cfg.QDRANT_HOST, port=cfg.QDRANT_PORT)
    existing = [c.name for c in client.get_collections().collections]
    if cfg.COLLECTION_NAME in existing:
        client.delete_collection(cfg.COLLECTION_NAME)
        console.print(f"[yellow]WARN Deleted collection:[/] {cfg.COLLECTION_NAME}")
    client.create_collection(
        collection_name=cfg.COLLECTION_NAME,
        vectors_config=VectorParams(size=cfg.EMBEDDING_DIM, distance=Distance.COSINE),
    )
    console.print(f"[green]OK Re-created collection:[/] {cfg.COLLECTION_NAME}")


def main(reset: bool = False):
    console.rule("[bold cyan]Zscaler RAG — Ingestion Pipeline[/]")

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
    console.print(f"  -> Avg chunk size: {sum(len(c['text']) for c in chunks) // len(chunks)} chars")

    # ── 3. Embed ──────────────────────────────────────────────────────────
    console.print("\n[bold]Step 2/3:[/] Generating embeddings (local, no API cost)…")
    embeddings = embed_chunks(chunks)
    if isinstance(embeddings, dict):
        shape_str = f"dense={embeddings['dense'].shape}"
    else:
        shape_str = str(embeddings.shape)
    console.print(f"  -> Embedding shape: {shape_str} ({cfg.EMBEDDING_MODEL})")

    # ── 4. Upsert into Qdrant ─────────────────────────────────────────────
    console.print("\n[bold]Step 3/3:[/] Upserting into Qdrant…")
    point_ids = upsert_chunks(chunks, embeddings)
    console.print(f"  -> Upserted {len(point_ids)} points")

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
    parser.add_argument("--reset", action="store_true", help="Wipe and re-create the Qdrant collection first")
    args = parser.parse_args()
    main(reset=args.reset)
