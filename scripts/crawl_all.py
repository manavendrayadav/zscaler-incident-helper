"""
Full-site crawler — processes pages one at a time with a fresh browser per page.

This is the most reliable approach: no concurrent tabs, no shared browser state,
no memory accumulation. Each page gets its own Playwright browser launch/close.

~8-10 seconds per page → 1,000 remaining pages ≈ 2-3 hours total.
Safe to Ctrl-C at any point and resume — manifest is written after every page.

Usage:
  python scripts/crawl_all.py                    # crawl all remaining pages
  python scripts/crawl_all.py --product zia      # only ZIA pages
  python scripts/crawl_all.py --force            # re-crawl everything
  python scripts/crawl_all.py --no-ingest        # crawl only, skip Qdrant ingest
"""

import argparse
import asyncio
import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from config import cfg
from crawler.crawler import (
    _html_to_markdown,
    _extract_title,
    _make_frontmatter,
    _url_to_slug,
    _load_manifest,
    _save_manifest,
    _needs_crawl,
)
from crawler.sitemap_parser import fetch_sitemap, SitemapEntry

console = Console(highlight=False, markup=True, emoji=False)

INGEST_EVERY = 100   # ingest into Qdrant every N successfully crawled pages


# ── Single-page crawl with fresh browser ─────────────────────────────────────

async def _crawl_one(
    url: str, product: str, lastmod: str, pw, browser
) -> Optional[dict]:
    """
    Crawl one page using a shared Playwright browser.
    Creates a fresh context+page, then closes them after use.
    Browser is reused across calls (managed by the caller).
    """
    from bs4 import BeautifulSoup

    context = None
    try:
        context = await browser.new_context()
        page = await context.new_page()
        await page.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,eot,ico}",
            lambda r: r.abort()
        )
        await page.goto(url, wait_until="networkidle", timeout=30_000)
        await page.wait_for_timeout(2_500)
        html = await page.content()
    except Exception as e:
        console.print(f"  [red]ERR[/] {url.split('/')[-1]}: {type(e).__name__}")
        return None
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass

    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.select(
            "nav, header, footer, .sidebar, .breadcrumb, "
            "script, style, noscript, [class*=nav], [class*=menu]"
        ):
            tag.decompose()
        article = (
            soup.find("article")
            or soup.find("main")
            or soup.find(class_=re.compile(r"article|content|doc|body", re.I))
            or soup.body
        )
        if not article:
            return None
        markdown = _html_to_markdown(article)
    except Exception:
        return None

    if not markdown or len(markdown) < 100:
        return None

    title      = _extract_title(markdown, url)
    slug       = _url_to_slug(url)
    file_path  = cfg.RAW_DIR / f"{slug}.md"
    crawled_at = datetime.now(timezone.utc).isoformat()

    cfg.RAW_DIR.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        _make_frontmatter(url, title, product, crawled_at) + markdown,
        encoding="utf-8",
    )

    return {
        "last_crawled":    crawled_at,
        "sitemap_lastmod": lastmod,
        "file":            f"data/raw/{file_path.name}",
        "title":           title,
        "product":         product,
        "content_hash":    hashlib.sha256(markdown.encode()).hexdigest()[:16],
        "chunk_ids":       [],
    }


BROWSER_RESTART_EVERY = 100  # restart browser after this many pages


async def _run_crawl_async(
    to_crawl: list[SitemapEntry],
    manifest: dict,
    no_ingest: bool,
) -> tuple[int, int, int]:
    """
    Single event loop for the entire crawl run.
    Uses a persistent browser that restarts every BROWSER_RESTART_EVERY pages.
    Returns (ok_count, skip_count, total_chunks).
    """
    from playwright.async_api import async_playwright

    crawled_this_run: list[str] = []
    total_chunks = 0
    ok_count     = 0
    skip_count   = 0
    page_num     = 0

    pw      = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
    )

    async def restart_browser():
        nonlocal browser
        try:
            await browser.close()
        except Exception:
            pass
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        console.print(f"  [dim]Browser restarted (memory cleanup)[/dim]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Crawling…", total=len(to_crawl))

        for entry in to_crawl:
            page_num += 1
            slug = entry.url.rstrip("/").split("/")[-1]
            progress.update(task, description=f"[{entry.product}] {slug[:50]}")

            # Restart browser every N pages to free memory
            if page_num % BROWSER_RESTART_EVERY == 0:
                await restart_browser()

            result = await _crawl_one(entry.url, entry.product, entry.lastmod, pw, browser)

            if result:
                manifest[entry.url] = result
                crawled_this_run.append(entry.url)
                ok_count += 1
            else:
                skip_count += 1

            _save_manifest(manifest)
            progress.advance(task)

            # Ingest every INGEST_EVERY successfully crawled pages
            if (not no_ingest
                    and len(crawled_this_run) % INGEST_EVERY == 0
                    and crawled_this_run):
                batch = crawled_this_run[-INGEST_EVERY:]
                progress.stop()
                console.print(
                    f"\n[bold cyan]--- Ingest {len(batch)} pages "
                    f"({ok_count}/{len(to_crawl)} crawled) ---[/]"
                )
                n = _ingest_batch(batch, manifest)
                total_chunks += n
                console.print(f"    +{n} chunks this batch\n")
                progress.start()

    # Final ingest for tail
    remainder = len(crawled_this_run) % INGEST_EVERY
    if not no_ingest and remainder:
        tail = crawled_this_run[-remainder:]
        console.print(f"\n[bold cyan]--- Final ingest: {len(tail)} pages ---[/]")
        n = _ingest_batch(tail, manifest)
        total_chunks += n
        console.print(f"    +{n} chunks\n")

    try:
        await browser.close()
        await pw.stop()
    except Exception:
        pass

    return ok_count, skip_count, total_chunks


# ── Ingest a batch of pages into Qdrant ──────────────────────────────────────

def _ingest_batch(urls: list[str], manifest: dict) -> int:
    from pipeline.chunker import chunk_files
    from pipeline.embedder import embed_chunks
    from pipeline.indexer import ensure_collection, upsert_chunks, update_manifest_chunk_ids

    ensure_collection()
    files = []
    for url in urls:
        entry = manifest.get(url)
        if entry and entry.get("file"):
            p = Path(entry["file"])
            if not p.is_absolute():
                p = Path(__file__).parent.parent / p
            if p.exists():
                files.append(p)

    if not files:
        return 0

    chunks     = chunk_files(files)
    embeddings = embed_chunks(chunks)
    point_ids  = upsert_chunks(chunks, embeddings)

    url_chunk_map: dict[str, list[str]] = defaultdict(list)
    for chunk, pid in zip(chunks, point_ids):
        url_chunk_map[chunk["metadata"]["url"]].append(pid)
    update_manifest_chunk_ids(manifest, url_chunk_map)
    return len(point_ids)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Zscaler full-site crawler (sequential)")
    parser.add_argument("--product", choices=["zia", "zpa", "zdx", "zcc", "deception"])
    parser.add_argument("--force",     action="store_true")
    parser.add_argument("--no-ingest", action="store_true")
    args = parser.parse_args()

    console.rule("[bold cyan]Zscaler Full-Site Crawl[/]")
    console.print("Fetching sitemap …")

    all_entries: list[SitemapEntry] = fetch_sitemap(filter_relevant=False, max_urls=None)
    if args.product:
        all_entries = [e for e in all_entries if e.product == args.product]

    manifest  = _load_manifest()
    to_crawl  = [e for e in all_entries if args.force or _needs_crawl(e.url, e.lastmod, manifest)]
    skipped   = len(all_entries) - len(to_crawl)

    by_product = Counter(e.product for e in all_entries)
    console.print(
        f"  Sitemap: [bold]{len(all_entries)}[/]  "
        + "  ".join(f"{p}:{c}" for p, c in sorted(by_product.items()))
    )
    console.print(f"  Already done : [green]{skipped}[/]")
    console.print(f"  To crawl     : [bold yellow]{len(to_crawl)}[/]")

    if not to_crawl:
        console.print("\n[bold green]All pages already scraped![/]")
        return

    console.print(f"  Mode: single event loop, browser restart every {BROWSER_RESTART_EVERY} pages\n")

    start_time = time.time()
    ok_count, skip_count, total_chunks = asyncio.run(
        _run_crawl_async(to_crawl, manifest, args.no_ingest)
    )

    # Reload manifest after async run (it was saved incrementally inside)
    manifest = _load_manifest()
    elapsed = round(time.time() - start_time)
    console.rule("[bold green]Done[/]")
    console.print(f"  Crawled  : [green]{ok_count}[/]  skipped: {skip_count}")
    console.print(f"  Manifest : {len([v for v in manifest.values() if v.get('file')])} / {len(all_entries)}")
    console.print(f"  Chunks   : +{total_chunks} this run")
    console.print(f"  Time     : {elapsed//60}m {elapsed%60}s")

    remaining = len({e.url for e in fetch_sitemap(filter_relevant=False)} - set(manifest.keys()))
    if remaining == 0:
        console.print("\n[bold green]ALL 1,822 PAGES SCRAPED![/]")
    else:
        console.print(f"\n[yellow]{remaining} pages still remaining — run again to continue.[/]")


if __name__ == "__main__":
    main()
