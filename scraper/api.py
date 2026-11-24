"""HTTP API so n8n (or any scheduler) can trigger runs and pull results."""
from __future__ import annotations

import csv
import io
import os
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from .core import BASE_URL, crawl
from .store import Store

app = FastAPI(title="Scraper Automation Demo", version="1.0.0")
store = Store(os.getenv("DB_PATH", "data/items.db"))
API_KEY = os.getenv("API_KEY", "")


def check_key(key: Optional[str]) -> None:
    if API_KEY and key != API_KEY:
        raise HTTPException(401, "Invalid or missing X-API-Key")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "items": len(store.items())}


@app.post("/run")
def run(max_pages: int = Query(3, ge=1, le=50), x_api_key: Optional[str] = Header(None)) -> dict:
    """Scrape, save, and return what changed in this run (ready for an n8n IF/Slack node)."""
    check_key(x_api_key)
    before = store.last_change_id()
    items, problems, pages = crawl(os.getenv("START_URL", BASE_URL), max_pages=max_pages)
    counts = store.upsert(items)
    changes = [c for c in store.changes() if c["id"] > before]
    return {"pages": pages, "scraped": len(items), "counts": counts, "problems": problems, "changes": changes}


@app.get("/items")
def items(x_api_key: Optional[str] = Header(None)) -> list:
    check_key(x_api_key)
    return store.items()


@app.get("/changes")
def changes(since: str = "", x_api_key: Optional[str] = Header(None)) -> list:
    check_key(x_api_key)
    return store.changes(since=since)


@app.get("/export.csv")
def export_csv(x_api_key: Optional[str] = Header(None)) -> StreamingResponse:
    check_key(x_api_key)
    rows = store.items()
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=items.csv"})
