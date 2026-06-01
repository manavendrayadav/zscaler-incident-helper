"""
Parse the Zscaler sitemap to get URLs with their lastmod dates.
Used for incremental crawling — only fetch pages that changed since last crawl.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime

import httpx

SITEMAP_URL = "https://help.zscaler.com/sitemap.xml"

# Zscaler product prefixes we care about
PRODUCT_PREFIXES = ("zia", "zpa", "zdx", "zcc", "zcx", "deception")

# Keywords that indicate relevant troubleshooting content
RELEVANT_KEYWORDS = (
    "troubleshoot",
    "error",
    "issue",
    "problem",
    "configure",
    "configuration",
    "policy",
    "alert",
    "bypass",
    "connectivity",
    "authentication",
    "ssl",
    "dns",
    "pac",
)


@dataclass
class SitemapEntry:
    url: str
    lastmod: str        # ISO date string e.g. "2026-05-27"
    product: str        # inferred from URL: zia | zpa | zdx | ...

    def lastmod_date(self) -> datetime:
        try:
            return datetime.fromisoformat(self.lastmod)
        except ValueError:
            return datetime.min


def _infer_product(url: str) -> str:
    """Extract product slug from URL path, e.g. /zia/ → 'zia'."""
    for prefix in PRODUCT_PREFIXES:
        if f"/{prefix}/" in url or url.rstrip("/").endswith(f"/{prefix}"):
            return prefix
    return "general"


def _is_relevant(url: str) -> bool:
    slug = url.rstrip("/").split("/")[-1].lower()
    return any(kw in slug for kw in RELEVANT_KEYWORDS)


def fetch_sitemap(
    url: str = SITEMAP_URL,
    filter_relevant: bool = False,
    max_urls: int | None = None,
) -> list[SitemapEntry]:
    """
    Fetch the Zscaler sitemap and return SitemapEntry objects.

    Args:
        url: Sitemap URL (supports both index sitemaps and regular sitemaps).
        filter_relevant: If True, only return troubleshooting-related URLs.
        max_urls: Limit the number of returned entries (useful for Phase 1 testing).
    """
    ns = "http://www.sitemaps.org/schemas/sitemap/0.9"

    response = httpx.get(url, timeout=30, follow_redirects=True)
    response.raise_for_status()

    root = ET.fromstring(response.text)

    # Sitemap index — recurse into child sitemaps
    if root.tag == f"{{{ns}}}sitemapindex":
        entries = []
        for sitemap in root.findall(f"{{{ns}}}sitemap"):
            loc = sitemap.findtext(f"{{{ns}}}loc", "")
            if loc:
                entries.extend(fetch_sitemap(loc, filter_relevant=filter_relevant))
            if max_urls and len(entries) >= max_urls:
                break
        return entries[:max_urls] if max_urls else entries

    # Regular sitemap
    entries = []
    for url_el in root.findall(f"{{{ns}}}url"):
        loc = url_el.findtext(f"{{{ns}}}loc", "").strip()
        lastmod = url_el.findtext(f"{{{ns}}}lastmod", "1970-01-01").strip()

        if not loc:
            continue

        # Only include product-specific pages
        product = _infer_product(loc)
        if product == "general":
            continue

        if filter_relevant and not _is_relevant(loc):
            continue

        entries.append(SitemapEntry(url=loc, lastmod=lastmod, product=product))

    return entries[:max_urls] if max_urls else entries
