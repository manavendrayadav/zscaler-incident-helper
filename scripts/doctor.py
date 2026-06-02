"""
Zscaler RAG — System Doctor

Checks all services, API keys, knowledge base, and Qdrant health.
Prints a Rich terminal report and exits with code 0 (all OK), 1 (warnings), or 2 (failures).

Usage:
  python scripts/doctor.py
  make doctor
"""

import json
import os
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# ── Bootstrap ────────────────────────────────────────────────────────────────

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env")

# ── Constants ─────────────────────────────────────────────────────────────────

RAG_API_URL = "http://localhost:8000"
QDRANT_URL = "http://localhost:6333"
CRAWL4AI_URL = "http://localhost:11235"
OPENWEBUI_URL = "http://localhost:3000"
MANIFEST_FILE = Path(__file__).parent.parent / "data" / "crawl_manifest.json"
RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
COLLECTION = os.getenv("COLLECTION_NAME", "zscaler_docs")

console = Console(highlight=False, emoji=False, markup=True)

PASS = "[bold green]OK[/]"
WARN = "[bold yellow]WARN[/]"
FAIL = "[bold red]FAIL[/]"
SKIP = "[dim]--[/]"


# ── Check functions ──────────────────────────────────────────────────────────


def check_docker_containers() -> dict[str, bool]:
    """Return {service_name: is_running} for all known containers."""
    name_map = {
        "zih-qdrant": "qdrant",
        "zih-crawl4ai": "crawl4ai",
        "zih-api": "rag-api",
        "zih-openwebui": "open-webui",
    }
    result = dict.fromkeys(name_map.values(), False)
    try:
        proc = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        running = set(proc.stdout.strip().splitlines())
        for container, service in name_map.items():
            if container in running:
                result[service] = True
    except FileNotFoundError:
        pass  # Docker not installed
    except Exception:
        pass
    return result


def check_http(url: str, timeout: float = 4.0) -> tuple[bool, str]:
    """Return (reachable, status_or_error)."""
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True)
        return r.status_code < 500, str(r.status_code)
    except httpx.ConnectError:
        return False, "connection refused"
    except httpx.TimeoutException:
        return False, "timeout"
    except Exception as e:
        return False, str(e)[:40]


def check_api_keys() -> dict[str, str]:
    """Return {provider: 'SET'|'MISSING'} for each cloud LLM provider."""
    return {
        "groq": "SET" if os.getenv("GROQ_API_KEY") else "MISSING",
        "openrouter": "SET" if os.getenv("OPENROUTER_API_KEY") else "MISSING",
        "openai": "SET" if os.getenv("OPENAI_API_KEY") else "MISSING",
        "anthropic": "SET" if os.getenv("ANTHROPIC_API_KEY") else "MISSING",
    }


def test_groq_key() -> tuple[bool, str]:
    """Do a minimal live test of the Groq API key. Returns (valid, message)."""
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return False, "not set"
    try:
        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 3,
            },
            timeout=8.0,
        )
        if resp.status_code == 200:
            return True, "valid"
        if resp.status_code == 401:
            return False, "invalid key"
        if resp.status_code == 429:
            return True, "rate limited (key valid)"
        return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)[:30]


def test_ollama() -> tuple[str, bool, str]:
    """
    Check whether Ollama is reachable and has models pulled.
    Returns (base_url, reachable, message).
    """
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=4.0)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            if models:
                return base_url, True, f"{len(models)} model(s) pulled"
            return base_url, True, "running — no models pulled yet"
        return base_url, False, f"HTTP {resp.status_code}"
    except httpx.ConnectError:
        return base_url, False, "offline"
    except Exception as e:
        return base_url, False, str(e)[:35]


def analyze_manifest() -> dict:
    """Analyse crawl_manifest.json and data/raw/."""
    if not MANIFEST_FILE.exists():
        return {"missing": True}

    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    total = len(manifest)
    indexed = sum(1 for v in manifest.values() if v.get("chunk_ids"))
    stale = 0
    by_product: Counter = Counter()

    for entry in manifest.values():
        product = entry.get("product", "unknown")
        by_product[product] += 1
        lc = entry.get("last_crawled", "")
        lm = entry.get("sitemap_lastmod", "")
        if lm and lc and lm[:10] > lc[:10]:
            stale += 1

    raw_files = len(list(RAW_DIR.glob("*.md"))) if RAW_DIR.exists() else 0

    return {
        "missing": False,
        "total": total,
        "indexed": indexed,
        "not_indexed": total - indexed,
        "stale": stale,
        "by_product": dict(by_product),
        "raw_files": raw_files,
        "file_mismatch": raw_files != total,
    }


def get_qdrant_product_counts() -> dict[str, int]:
    """Scroll Qdrant collection and count chunks by product."""
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(host="localhost", port=int(os.getenv("QDRANT_PORT", "6333")), check_compatibility=False)
        counts: Counter = Counter()
        offset = None
        while True:
            points, next_offset = client.scroll(
                collection_name=COLLECTION,
                limit=500,
                offset=offset,
                with_payload=["product"],
                with_vectors=False,
            )
            for p in points:
                product = (p.payload or {}).get("product", "unknown")
                counts[product] += 1
            if next_offset is None:
                break
            offset = next_offset
        return dict(counts)
    except Exception:
        return {}


# ── Rendering helpers ────────────────────────────────────────────────────────


def _status_cell(ok: bool, warn: bool = False) -> str:
    if ok:
        return PASS
    return WARN if warn else FAIL


def render_services(containers: dict[str, bool], http: dict[str, tuple[bool, str]]) -> Panel:
    t = Table(box=None, padding=(0, 1), show_header=True, header_style="bold")
    t.add_column("Service", style="cyan", min_width=12)
    t.add_column("Container", min_width=10)
    t.add_column("HTTP", min_width=24)
    t.add_column("Status", min_width=8)

    rows = [
        ("qdrant", "zih-qdrant", f"{QDRANT_URL}/health", False),
        ("crawl4ai", "zih-crawl4ai", f"{CRAWL4AI_URL}/health", True),  # optional
        ("rag-api", "zih-api", f"{RAG_API_URL}/health", False),
        ("open-webui", "zih-openwebui", OPENWEBUI_URL, True),  # optional
    ]

    for service, container, url, optional in rows:
        c_ok = containers.get(service, False)
        h_ok, h_msg = http.get(service, (False, "?"))
        overall_ok = c_ok and h_ok
        cell = _status_cell(overall_ok, warn=optional)
        t.add_row(service, container, f"{url} [{h_msg}]", cell)

    return Panel(t, title="[bold]Services[/]", border_style="blue")


def render_keys(
    keys: dict[str, str],
    groq_valid: bool,
    groq_msg: str,
    ollama_url: str,
    ollama_ok: bool,
    ollama_msg: str,
) -> Panel:
    t = Table(box=None, padding=(0, 1), show_header=True, header_style="bold")
    t.add_column("Provider", style="cyan", min_width=12)
    t.add_column("Key / URL", min_width=28)
    t.add_column("Tested", min_width=28)

    for provider, key_status in keys.items():
        if key_status == "MISSING":
            key_cell = f"[yellow]{key_status}[/]"
            tested_cell = SKIP
        else:
            key_cell = f"[green]{key_status}[/]"
            if provider == "groq":
                tested_cell = f"[green]{groq_msg}[/]" if groq_valid else f"[red]{groq_msg}[/]"
            else:
                tested_cell = SKIP + " (not tested)"
        t.add_row(provider, key_cell, tested_cell)

    # Ollama — URL-based, no API key
    url_cell = f"[dim]{ollama_url}[/]"
    tested_cell = f"[green]{ollama_msg}[/]" if ollama_ok else f"[yellow]{ollama_msg}[/]"
    t.add_row("ollama", url_cell, tested_cell)

    return Panel(t, title="[bold]API Keys[/]", border_style="blue")


def render_knowledge_base(stats: dict) -> Panel:
    if stats.get("missing"):
        return Panel(
            "[red]data/crawl_manifest.json not found.[/]\n"
            "Run [bold cyan]make crawl[/] to start crawling.",
            title="[bold]Knowledge Base[/]",
            border_style="red",
        )

    total = stats["total"]
    indexed = stats["indexed"]
    stale = stats["stale"]
    raw_files = stats["raw_files"]
    by_product = stats["by_product"]
    mismatch = stats["file_mismatch"]

    product_str = "  ".join(f"[cyan]{p.upper()}[/]: {c}" for p, c in sorted(by_product.items()))

    lines = [
        f"Pages crawled : [bold]{total}[/]     {product_str}",
        f"Pages indexed : [bold]{indexed}[/]"
        + ("" if indexed == total else f"  [yellow]({total - indexed} not yet ingested)[/]"),
        f"Pages stale   : [bold]{stale}[/]" + ("  [yellow](run make update)[/]" if stale else ""),
        f"Raw .md files : [bold]{raw_files}[/]"
        + ("  [yellow](mismatch with manifest)[/]" if mismatch else ""),
    ]

    color = "green" if (indexed == total and stale == 0 and not mismatch) else "yellow"
    return Panel("\n".join(lines), title="[bold]Knowledge Base[/]", border_style=color)


def render_qdrant(http_ok: bool, product_counts: dict) -> Panel:
    if not http_ok:
        return Panel("[red]Qdrant is unreachable.[/]", title="[bold]Qdrant[/]", border_style="red")

    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(host="localhost", port=int(os.getenv("QDRANT_PORT", "6333")), check_compatibility=False)
        info = client.get_collection(COLLECTION)
        points = info.points_count or 0
        status = str(info.status)
    except Exception as e:
        return Panel(
            f"[red]Error reading collection: {e}[/]", title="[bold]Qdrant[/]", border_style="red"
        )

    product_str = (
        "  ".join(f"[cyan]{p.upper()}[/]: {c}" for p, c in sorted(product_counts.items()))
        if product_counts
        else "[dim]run doctor again after ingest[/]"
    )

    color = "green" if status == "CollectionStatus.Green" or "green" in status.lower() else "yellow"
    lines = [
        f"Collection : [bold]{COLLECTION}[/]   Status: [bold]{status}[/]",
        f"Chunks     : [bold]{points}[/]   {product_str}",
    ]
    return Panel("\n".join(lines), title="[bold]Qdrant[/]", border_style=color)


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    console.print()
    console.print(
        Panel(
            f"[bold white]Zscaler RAG  —  System Doctor[/]\n[dim]{now}[/]",
            border_style="bold blue",
        )
    )
    console.print()

    # ── Gather all data ──────────────────────────────────────────────────────
    console.print("[dim]Checking services...[/]")
    containers = check_docker_containers()

    http_results: dict[str, tuple[bool, str]] = {}
    for service, url in [
        ("qdrant", f"{QDRANT_URL}/health"),
        ("crawl4ai", f"{CRAWL4AI_URL}/health"),
        ("rag-api", f"{RAG_API_URL}/health"),
        ("open-webui", OPENWEBUI_URL),
    ]:
        http_results[service] = check_http(url)

    console.print("[dim]Checking API keys...[/]")
    keys = check_api_keys()
    groq_valid, groq_msg = test_groq_key()
    ollama_url, ollama_ok, ollama_msg = test_ollama()

    console.print("[dim]Analysing knowledge base...[/]")
    kb_stats = analyze_manifest()

    console.print("[dim]Querying Qdrant chunk distribution...[/]")
    product_counts = get_qdrant_product_counts()

    # ── Render panels ────────────────────────────────────────────────────────
    console.print()
    console.print(render_services(containers, http_results))
    console.print(render_keys(keys, groq_valid, groq_msg, ollama_url, ollama_ok, ollama_msg))
    console.print(render_knowledge_base(kb_stats))
    qdrant_http_ok, _ = http_results.get("qdrant", (False, ""))
    console.print(render_qdrant(qdrant_http_ok, product_counts))

    # ── Summary ──────────────────────────────────────────────────────────────
    failures = 0
    warnings = 0

    # Critical failures
    if not containers.get("qdrant") or not http_results.get("qdrant", (False,))[0]:
        failures += 1
    if not containers.get("rag-api") or not http_results.get("rag-api", (False,))[0]:
        failures += 1
    if kb_stats.get("missing"):
        failures += 1

    # Warnings
    if not containers.get("crawl4ai") or not http_results.get("crawl4ai", (False,))[0]:
        warnings += 1
    if not containers.get("open-webui") or not http_results.get("open-webui", (False,))[0]:
        warnings += 1
    if keys.get("groq") == "MISSING" or not groq_valid:
        warnings += 1
    if keys.get("openrouter") == "MISSING":
        warnings += 1
    if keys.get("openai") == "MISSING":
        warnings += 1
    if keys.get("anthropic") == "MISSING":
        warnings += 1
    if not ollama_ok:
        warnings += 1
    if not kb_stats.get("missing"):
        if kb_stats.get("stale", 0) > 0:
            warnings += 1
        if kb_stats.get("not_indexed", 0) > 0:
            warnings += 1
        if kb_stats.get("file_mismatch"):
            warnings += 1

    total_checks = 13  # 3 failure paths + 10 warning paths
    passes = total_checks - failures - warnings

    if failures:
        result_style = "bold red"
        result_label = "DEGRADED"
        exit_code = 2
    elif warnings:
        result_style = "bold yellow"
        result_label = "OK WITH WARNINGS"
        exit_code = 1
    else:
        result_style = "bold green"
        result_label = "ALL SYSTEMS GO"
        exit_code = 0

    console.print()
    console.print(
        Panel(
            f"[{result_style}]{result_label}[/]  "
            f"[green]{passes} passed[/]  "
            f"[yellow]{warnings} warnings[/]  "
            f"[red]{failures} failures[/]",
            border_style=result_style,
        )
    )
    console.print()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
