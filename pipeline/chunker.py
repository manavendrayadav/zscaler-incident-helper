"""
Split crawled Markdown files into overlapping chunks suitable for embedding.
Stage 1: split on Markdown headers to preserve document structure.
Stage 2: recursively split large sections to stay within embedding token limits.
"""

import hashlib
import uuid
from pathlib import Path
from typing import Any

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from config import cfg

HEADERS_TO_SPLIT = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
    ("####", "h4"),
]


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Strip YAML frontmatter and return (metadata dict, body markdown)."""
    if not text.startswith("---"):
        return {}, text

    end = text.find("---", 3)
    if end == -1:
        return {}, text

    fm_block = text[3:end].strip()
    body = text[end + 3:].strip()

    meta: dict[str, str] = {}
    for line in fm_block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()

    return meta, body


def chunk_markdown_file(file_path: Path) -> list[dict[str, Any]]:
    """
    Chunk one crawled markdown file into overlapping text pieces.

    Returns a list of chunk dicts:
        {
            "chunk_id": str,  # unique UUID
            "text": str,
            "metadata": {
                "url": str, "title": str, "product": str,
                "section": str, "source_file": str,
            }
        }
    """
    raw = file_path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(raw)

    url = meta.get("url", "")
    title = meta.get("title", file_path.stem)
    product = meta.get("product", "general")

    # Stage 1 — split on markdown headers
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT,
        strip_headers=False,
    )
    header_docs = md_splitter.split_text(body)

    # Stage 2 — recursively split sections that are still too large
    recursive_splitter = RecursiveCharacterTextSplitter(
        chunk_size=cfg.CHUNK_SIZE,
        chunk_overlap=cfg.CHUNK_OVERLAP,
        length_function=len,
    )

    chunks = []
    for doc in header_docs:
        text = doc.page_content.strip()
        if not text:
            continue

        # Derive section label from header metadata injected by LangChain
        section_parts = [
            doc.metadata.get("h1", ""),
            doc.metadata.get("h2", ""),
            doc.metadata.get("h3", ""),
            doc.metadata.get("h4", ""),
        ]
        section = " › ".join(p for p in section_parts if p) or title

        sub_chunks = recursive_splitter.split_text(text)
        for idx, sub in enumerate(sub_chunks):
            sub = sub.strip()
            if len(sub) < 80:   # skip tiny fragments
                continue
            # Deterministic ID: same URL+section+position always maps to the same
            # Qdrant point, so re-ingesting a page overwrites rather than duplicates.
            det_id = str(uuid.UUID(hashlib.md5(
                f"{url}|{section}|{idx}".encode()
            ).hexdigest()))
            chunks.append(
                {
                    "chunk_id": det_id,
                    "text": sub,
                    "metadata": {
                        "url": url,
                        "title": title,
                        "product": product,
                        "section": section,
                        "source_file": str(file_path.name),
                    },
                }
            )

    return chunks


def chunk_files(files: list[Path]) -> list[dict[str, Any]]:
    """Chunk a specific list of .md files (used for batch ingest during crawl)."""
    all_chunks = []
    for f in files:
        if f.exists():
            all_chunks.extend(chunk_markdown_file(f))
    return all_chunks


def chunk_all_files(raw_dir: Path | None = None) -> list[dict[str, Any]]:
    """Chunk every .md file in the raw directory."""
    raw_dir = raw_dir or cfg.RAW_DIR
    md_files = sorted(raw_dir.glob("*.md"))

    if not md_files:
        raise FileNotFoundError(f"No .md files found in {raw_dir}. Run 'make crawl' first.")

    all_chunks = []
    for f in md_files:
        file_chunks = chunk_markdown_file(f)
        all_chunks.extend(file_chunks)

    return all_chunks
