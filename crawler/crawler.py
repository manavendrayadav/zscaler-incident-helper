"""
Crawl Zscaler help pages via the Crawl4AI Docker REST API (http://localhost:11235).
Falls back to a native Playwright + BeautifulSoup extractor when the service is
unavailable (e.g. during local development without Docker).

Maintains data/crawl_manifest.json for incremental updates:
  - New device / no manifest  -> full crawl of all provided entries
  - make update               -> compare sitemap lastmod -> only crawl new/changed pages
"""

import asyncio
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from config import cfg
from crawler.sitemap_parser import SitemapEntry

# Force UTF-8 safe output on Windows terminals (avoids cp1252 UnicodeEncodeError)
console = Console(highlight=False, markup=True, emoji=False)


# ── Manifest helpers ─────────────────────────────────────────────────────────

def _load_manifest() -> dict:
    if cfg.MANIFEST_FILE.exists():
        return json.loads(cfg.MANIFEST_FILE.read_text(encoding="utf-8"))
    return {}


def _save_manifest(manifest: dict) -> None:
    cfg.MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    cfg.MANIFEST_FILE.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _needs_crawl(url: str, sitemap_lastmod: str, manifest: dict) -> bool:
    entry = manifest.get(url)
    if not entry:
        return True
    prev_lastmod = entry.get("sitemap_lastmod", "1970-01-01")
    return sitemap_lastmod > prev_lastmod


def _url_to_slug(url: str) -> str:
    path = re.sub(r"https?://[^/]+", "", url).strip("/")
    slug = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")
    return slug[:120]


def _extract_title(markdown: str, url: str) -> str:
    for line in markdown.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return _url_to_slug(url).replace("-", " ").title()


def _make_frontmatter(url: str, title: str, product: str, crawled_at: str) -> str:
    return f"---\nurl: {url}\ntitle: {title}\nproduct: {product}\ncrawled_at: {crawled_at}\n---\n\n"


# ── Crawl4AI REST API client ─────────────────────────────────────────────────

def _crawl4ai_available(base_url: str) -> bool:
    """Quick health-check ping against the Crawl4AI Docker service."""
    try:
        r = httpx.get(f"{base_url}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def _extract_markdown_from_result(result: dict) -> Optional[str]:
    """
    Extract markdown from a Crawl4AI result object.

    Crawl4AI Docker (latest) returns:
      result["markdown"]["raw_markdown"]   <- primary
      result["markdown"]["fit_markdown"]   <- fallback (may be empty)

    Older versions may use:
      result["markdown"]  as a plain string
      result["fit_markdown"]  as a plain string
    """
    md = result.get("markdown")

    # Nested dict (current Docker API)
    if isinstance(md, dict):
        raw = md.get("raw_markdown") or md.get("fit_markdown") or ""
        if raw and raw.strip():
            return raw.strip()

    # Plain string (older versions)
    if isinstance(md, str) and md.strip():
        return md.strip()

    # Top-level fit_markdown fallback
    fit = result.get("fit_markdown")
    if isinstance(fit, str) and fit.strip():
        return fit.strip()

    return None


def _crawl_via_crawl4ai_api(url: str, base_url: str, poll_interval: float = 2.0, timeout: float = 120.0) -> Optional[str]:
    """
    Submit a URL to the Crawl4AI Docker REST API and return the markdown content.

    Handles two response modes:
      Sync  -> POST /crawl returns {"success": True, "results": [...]} immediately
      Async -> POST /crawl returns {"task_id": "..."}, then poll GET /task/{id}
    """
    try:
        resp = httpx.post(
            f"{base_url}/crawl",
            json={
                "urls": [url],
                "crawler_params": {
                    "headless": True,
                    "verbose": False,
                    "word_count_threshold": 10,
                    "page_timeout": 60000,
                    "wait_for_network_idle": True,
                    # Wait for Zscaler's React SPA to fully hydrate
                    "delay_before_return_html": 4.0,
                    # JS: wait until the main article content appears in the DOM
                    "js_code": (
                        "await new Promise(resolve => {"
                        "  const check = () => {"
                        "    const el = document.querySelector('article, main, [class*=article], [class*=content]');"
                        "    if (el && el.innerText && el.innerText.length > 200) resolve();"
                        "    else setTimeout(check, 500);"
                        "  };"
                        "  check();"
                        "  setTimeout(resolve, 5000);"
                        "});"
                    ),
                },
            },
            timeout=90,
        )
        resp.raise_for_status()
    except Exception as e:
        console.print(f"  [yellow]Crawl4AI submit error:[/] {e}")
        return None

    data = resp.json()

    # ── Synchronous response (results returned immediately) ──
    if data.get("success") and data.get("results"):
        results = data["results"]
        result = results[0] if isinstance(results, list) else results
        markdown = _extract_markdown_from_result(result)
        if markdown:
            return markdown
        # API returned HTML only — fall back to local HTML converter
        html = result.get("html", "")
        if html:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup.select("nav, header, footer, .sidebar, .breadcrumb, script, style, noscript"):
                tag.decompose()
            article = (
                soup.find("article")
                or soup.find("main")
                or soup.find(class_=re.compile(r"article|content|doc", re.I))
                or soup.body
            )
            return _html_to_markdown(article) if article else None
        return None

    # ── Async response (task_id polling) ──
    task_id = data.get("task_id")
    if not task_id:
        console.print(f"  [yellow]Unexpected Crawl4AI response format:[/] {list(data.keys())}")
        return None

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(poll_interval)
        try:
            poll = httpx.get(f"{base_url}/task/{task_id}", timeout=15)
            poll.raise_for_status()
            result_data = poll.json()
        except Exception:
            continue

        status = result_data.get("status", "")
        if status == "completed":
            raw = result_data.get("result") or result_data.get("results")
            if isinstance(raw, list):
                raw = raw[0] if raw else {}
            markdown = _extract_markdown_from_result(raw or {})
            return markdown
        if status == "failed":
            console.print(f"  [red]Crawl4AI task failed:[/] {result_data.get('error', '')}")
            return None

    console.print(f"  [yellow]Crawl4AI timed out for:[/] {url}")
    return None


# ── Playwright fallback (Python 3.14 compatible, no lxml needed) ─────────────

async def _crawl_with_playwright(url: str) -> Optional[str]:
    """Render page with headless Chromium, extract article HTML, convert to Markdown."""
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await page.wait_for_timeout(2_500)
            html = await page.content()
        finally:
            await browser.close()

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("nav, header, footer, .sidebar, .breadcrumb, script, style, noscript"):
        tag.decompose()

    article = (
        soup.find("article")
        or soup.find("main")
        or soup.find(class_=re.compile(r"article|content|doc", re.I))
        or soup.body
    )
    return _html_to_markdown(article) if article else None


def _html_to_markdown(element) -> str:
    lines: list[str] = []

    def process(node):
        if not hasattr(node, "name") or not node.name:
            s = str(node).strip() if node else ""
            if s and len(s) > 3:
                lines.append(s)
            return
        tag = node.name.lower()
        text = node.get_text(separator=" ", strip=True)

        if tag == "h1":
            lines.append(f"\n# {text}\n")
        elif tag == "h2":
            lines.append(f"\n## {text}\n")
        elif tag == "h3":
            lines.append(f"\n### {text}\n")
        elif tag in ("h4", "h5", "h6"):
            lines.append(f"\n#### {text}\n")
        elif tag == "p":
            if text:
                lines.append(f"\n{text}\n")
        elif tag in ("ul", "ol"):
            for i, li in enumerate(node.find_all("li", recursive=False)):
                li_text = li.get_text(separator=" ", strip=True)
                prefix = f"{i + 1}." if tag == "ol" else "-"
                lines.append(f"{prefix} {li_text}")
            lines.append("")
        elif tag == "pre":
            lines.append(f"\n```\n{text}\n```\n")
        elif tag == "code" and node.parent and node.parent.name != "pre":
            lines.append(f"`{text}`")
        elif tag == "table":
            for i, row in enumerate(node.find_all("tr")):
                cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                lines.append("| " + " | ".join(cells) + " |")
                if i == 0:
                    lines.append("| " + " | ".join("---" for _ in cells) + " |")
            lines.append("")
        elif tag in ("div", "section", "article", "main", "body"):
            for child in node.children:
                process(child)
        elif tag in ("strong", "b") and text:
            lines.append(f"**{text}**")

    process(element)
    result = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", result).strip()


# ── Unified single-URL crawl ─────────────────────────────────────────────────

async def _crawl_single(url: str, product: str, sitemap_lastmod: str, use_api: bool) -> Optional[dict]:
    try:
        markdown = None

        if use_api:
            loop = asyncio.get_event_loop()
            markdown = await loop.run_in_executor(
                None, _crawl_via_crawl4ai_api, url, cfg.CRAWL4AI_BASE_URL
            )
            # Auto-fallback: if Crawl4AI returned thin content (SPA not rendered),
            # use local Playwright which handles React apps reliably on the host.
            if not markdown or len(markdown) < 300:
                console.print(f"  [dim]Crawl4AI thin ({len(markdown or '')} chars) -> Playwright fallback[/dim]")
                markdown = await _crawl_with_playwright(url)

        if not markdown:
            markdown = await _crawl_with_playwright(url)

        if not markdown or len(markdown) < 100:
            console.print(f"  [yellow]WARN thin/empty content:[/] {url}")
            return None

        title = _extract_title(markdown, url)
        crawled_at = datetime.now(timezone.utc).isoformat()
        slug = _url_to_slug(url)
        file_path = cfg.RAW_DIR / f"{slug}.md"

        content = _make_frontmatter(url, title, product, crawled_at) + markdown
        file_path.write_text(content, encoding="utf-8")

        return {
            "last_crawled": crawled_at,
            "sitemap_lastmod": sitemap_lastmod,
            "file": f"data/raw/{file_path.name}",
            "title": title,
            "product": product,
            "content_hash": hashlib.sha256(markdown.encode()).hexdigest()[:16],
            "chunk_ids": [],
        }
    except Exception as e:
        console.print(f"  [red]ERROR:[/] {url} -> {e}")
        return None


# ── Main entry point ─────────────────────────────────────────────────────────

async def crawl_urls(
    entries: list[SitemapEntry],
    force: bool = False,
    rate_limit_secs: float = 1.5,
) -> dict:
    """
    Crawl the given SitemapEntry list, skipping unchanged pages.
    Automatically uses the Crawl4AI Docker REST API when available,
    otherwise falls back to the native Playwright extractor.
    """
    manifest = _load_manifest()
    to_crawl = [e for e in entries if force or _needs_crawl(e.url, e.lastmod, manifest)]
    skipped = len(entries) - len(to_crawl)

    if skipped:
        console.print(f"  Skipping {skipped} unchanged page(s) (already in manifest)")

    if not to_crawl:
        console.print("[green]All pages are up to date -- nothing to crawl.[/green]")
        return manifest

    use_api = _crawl4ai_available(cfg.CRAWL4AI_BASE_URL)
    engine = f"Crawl4AI API @ {cfg.CRAWL4AI_BASE_URL}" if use_api else "Playwright (local fallback)"
    console.print(f"\n[bold]Engine:[/] {engine}")
    console.print(f"[bold]Pages to crawl:[/] {len(to_crawl)}\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Crawling", total=len(to_crawl))

        for i, entry in enumerate(to_crawl):
            slug = entry.url.rstrip("/").split("/")[-1]
            progress.update(task, description=f"{slug}")

            result = await _crawl_single(entry.url, entry.product, entry.lastmod, use_api)
            if result:
                manifest[entry.url] = result
                console.print(f"  [green]OK[/] {entry.url}")
            else:
                console.print(f"  [yellow]SKIP[/] {entry.url}")

            progress.advance(task)

            if i < len(to_crawl) - 1:
                await asyncio.sleep(rate_limit_secs)

    _save_manifest(manifest)
    total_saved = len([v for v in manifest.values() if v.get("file")])
    console.print(f"\n[bold green]Done.[/] {len(to_crawl)} page(s) crawled -> [cyan]data/raw/[/]")
    console.print(f"   Manifest total: {total_saved} page(s) tracked.")
    return manifest
