"""CLI: python -m scraper --pages 3 --csv out.csv"""
import argparse
import csv
import logging

from .core import BASE_URL, crawl
from .store import Store

p = argparse.ArgumentParser(description="Scrape books.toscrape.com and track price/stock changes.")
p.add_argument("--url", default=BASE_URL)
p.add_argument("--pages", type=int, default=3)
p.add_argument("--db", default="data/items.db")
p.add_argument("--csv", help="also export all items to this CSV file")
args = p.parse_args()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
items, problems, pages = crawl(args.url, max_pages=args.pages)
store = Store(args.db)
counts = store.upsert(items)
print(f"Crawled {pages} pages, {len(items)} items: {counts}")
for msg in problems:
    print("WARN", msg)
if args.csv:
    rows = store.items()
    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows to {args.csv}")
