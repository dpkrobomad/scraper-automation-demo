"""Polite, resilient scraper for books.toscrape.com (a public sandbox built for scraping practice).

Resilience features:
- retries with exponential backoff on network errors and 429/5xx
- delay between requests and an honest User-Agent
- several fallback selectors per field, so a small layout change doesn't break the run
- validation: a record missing required fields is reported, not silently saved
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, asdict
from typing import Callable, Iterator, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

log = logging.getLogger("scraper")

BASE_URL = "https://books.toscrape.com/"
USER_AGENT = "scraper-automation-demo/1.0 (+https://github.com/dpkrobomad)"
RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


@dataclass
class Item:
    url: str
    title: str
    price_gbp: float
    in_stock: bool
    rating: Optional[int]

    def dict(self) -> dict:
        return asdict(self)


class Fetcher:
    def __init__(self, delay: float = 0.5, retries: int = 3, client: Optional[httpx.Client] = None):
        self.delay = delay
        self.retries = retries
        self.client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True)
        self._last = 0.0

    def get(self, url: str) -> str:
        for attempt in range(1, self.retries + 1):
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.client.get(url)
                if r.status_code == 429 or r.status_code >= 500:
                    raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
                r.raise_for_status()
                r.encoding = "utf-8"
                return r.text
            except httpx.HTTPError as e:
                if attempt == self.retries:
                    raise
                backoff = 2 ** attempt
                log.warning("Fetch failed (%s), retry %d in %ss: %s", e, attempt, backoff, url)
                time.sleep(backoff)
        raise RuntimeError("unreachable")


def _first(node: Tag, selectors: List[str]) -> Optional[Tag]:
    for sel in selectors:
        found = node.select_one(sel)
        if found is not None:
            return found
    return None


def parse_price(text: str) -> Optional[float]:
    m = re.search(r"(\d+(?:[.,]\d{1,2})?)", text.replace(",", ""))
    return float(m.group(1)) if m else None


def parse_listing(html: str, page_url: str) -> tuple:
    """Return (items, problems, next_page_url)."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("article.product_pod") or soup.select("li article") or soup.select("[class*=product]")
    items: List[Item] = []
    problems: List[str] = []
    for card in cards:
        link = _first(card, ["h3 a", "a[title]", "a"])
        price = _first(card, ["p.price_color", ".price", "[class*=price]"])
        stock = _first(card, ["p.instock", ".availability", "[class*=stock]"])
        rating = _first(card, ["p.star-rating", "[class*=rating]"])
        title = (link.get("title") or link.get_text(strip=True)) if link else None
        price_val = parse_price(price.get_text()) if price else None
        if not (link and title and price_val is not None):
            problems.append(f"Skipped a card on {page_url}: missing title or price")
            continue
        stars = None
        if rating:
            stars = next((RATINGS[c] for c in rating.get("class", []) if c in RATINGS), None)
        items.append(Item(
            url=urljoin(page_url, link["href"]),
            title=title.strip(),
            price_gbp=price_val,
            in_stock=bool(stock and "in stock" in stock.get_text().lower()),
            rating=stars,
        ))
    nxt = _first(soup, ["li.next a", "a[rel=next]"])
    return items, problems, (urljoin(page_url, nxt["href"]) if nxt else None)


def crawl(start_url: str = BASE_URL, max_pages: int = 3, fetch: Optional[Callable[[str], str]] = None) -> tuple:
    """Follow pagination up to max_pages. Return (items, problems, pages_crawled)."""
    fetch = fetch or Fetcher().get
    url: Optional[str] = start_url
    items: List[Item] = []
    problems: List[str] = []
    pages = 0
    while url and pages < max_pages:
        page_items, page_problems, url = parse_listing(fetch(url), url)
        items += page_items
        problems += page_problems
        pages += 1
        log.info("Page %d: %d items", pages, len(page_items))
    return items, problems, pages
