"""
Phase 1 crawler — crawl 5–10 hardcoded Zscaler troubleshooting pages.

Usage:
  python scripts/test_crawl.py           # initial crawl (skips unchanged)
  python scripts/test_crawl.py --force   # force re-crawl all
  python scripts/test_crawl.py --update  # incremental (only new/changed pages via sitemap)

After running, execute:  python scripts/ingest.py
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console

from crawler.crawler import crawl_urls
from crawler.sitemap_parser import SitemapEntry

console = Console()

# ── Phase 1 hardcoded URLs ───────────────────────────────────────────────────
# These are representative troubleshooting pages across ZIA and ZPA.
# Verified to exist in the sitemap (4,103 total URLs at help.zscaler.com).

PHASE1_URLS = [
    # ZIA — Zscaler Internet Access
    ("https://help.zscaler.com/zia/troubleshooting-ad-ldap-synchronization-errors", "2026-04-29", "zia"),
    ("https://help.zscaler.com/zia/executive-insights-app-errors-and-troubleshooting", "2026-04-29", "zia"),
    # ZPA — Zscaler Private Access
    ("https://help.zscaler.com/zpa/troubleshooting-app-connectors", "2026-04-29", "zpa"),
    ("https://help.zscaler.com/zpa/troubleshooting-private-cloud-controllers", "2026-04-29", "zpa"),
    ("https://help.zscaler.com/zpa/troubleshooting-private-service-edges", "2026-04-29", "zpa"),
    ("https://help.zscaler.com/zpa/troubleshooting-oauth-enrollment-private-access-images", "2026-04-29", "zpa"),
    ("https://help.zscaler.com/zpa/troubleshooting-manager-software-os-updates", "2026-05-04", "zpa"),
    # Troubleshooting Runbooks — cross-product
    ("https://help.zscaler.com/troubleshooting-runbooks/zia-traffic-forwarding-troubleshooting-runbook", "2026-01-10", "zia"),
    ("https://help.zscaler.com/troubleshooting-runbooks/zia-performance-troubleshooting-runbook", "2026-04-12", "zia"),
    ("https://help.zscaler.com/troubleshooting-runbooks/zia-security-policies-troubleshooting-runbook", "2026-03-04", "zia"),
]


def make_entries(url_list: list[tuple[str, str, str]]) -> list[SitemapEntry]:
    return [SitemapEntry(url=u, lastmod=lm, product=p) for u, lm, p in url_list]


async def run(force: bool, use_sitemap: bool):
    if use_sitemap:
        console.print("[bold]Incremental mode:[/] fetching sitemap for new/changed pages…")
        from crawler.sitemap_parser import fetch_sitemap
        entries = fetch_sitemap(filter_relevant=True, max_urls=20)
        if not entries:
            console.print("[yellow]No entries found via sitemap. Falling back to hardcoded URLs.[/]")
            entries = make_entries(PHASE1_URLS)
    else:
        console.print(
            f"[bold]Phase 1 crawl:[/] {len(PHASE1_URLS)} hardcoded Zscaler pages."
        )
        entries = make_entries(PHASE1_URLS)

    manifest = await crawl_urls(entries, force=force)

    crawled = sum(1 for e in manifest.values() if e.get("chunk_ids") is not None or e.get("file"))
    console.print(f"\n[bold green]Manifest updated.[/] {crawled} page(s) tracked.")
    console.print("\nNext step: [bold cyan]python scripts/ingest.py[/]")


def main():
    parser = argparse.ArgumentParser(description="Zscaler Phase 1 crawler")
    parser.add_argument("--force", action="store_true", help="Re-crawl all pages regardless of manifest")
    parser.add_argument("--update", action="store_true", help="Incremental: use sitemap to find new/changed pages")
    args = parser.parse_args()

    asyncio.run(run(force=args.force, use_sitemap=args.update))


if __name__ == "__main__":
    main()
