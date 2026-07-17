"""Read-only Vinted category scanner.

It deliberately uses conservative pagination and does not attempt to bypass
anti-bot controls. The package talks to public catalog pages/endpoints; if
Vinted responds with a block, the run stops and keeps the existing history.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS offers (
        item_id TEXT PRIMARY KEY, title TEXT NOT NULL, author TEXT, isbn TEXT,
        price REAL, currency TEXT, url TEXT, first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL, missing_runs INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active', raw_json TEXT
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,
        pages_requested INTEGER NOT NULL, items_seen INTEGER NOT NULL,
        completed INTEGER NOT NULL, error TEXT
    )""")
    db.commit()
    return db


def normalize(item: Any) -> dict[str, Any]:
    item_id = str(get(item, "id", ""))
    price = get(item, "price")
    if isinstance(price, dict):
        amount = price.get("amount") or price.get("value")
        currency = price.get("currency_code") or price.get("currency")
    else:
        amount, currency = price, get(item, "currency", "PLN")
    return {
        "item_id": item_id,
        "title": str(get(item, "title", "")).strip(),
        "author": "",
        "isbn": str(get(item, "isbn", "") or "").strip(),
        "price": float(amount) if amount not in (None, "") else None,
        "currency": currency or "PLN",
        "url": get(item, "url", "") or "",
        "raw_json": json.dumps(item, ensure_ascii=False, default=str),
    }


def scan(config: dict[str, Any]) -> tuple[int, bool, str | None]:
    category_ids = config.get("category_ids") or ([config.get("category_id")] if config.get("category_id") else [])
    if not category_ids:
        raise SystemExit("Uzupełnij category_ids w config.json na podstawie kategorii Książki na Vinted.")
    try:
        from vinted_scraper import VintedScraper
    except ImportError as exc:
        raise SystemExit("Brak vinted_scraper. Uruchom: pip install -r requirements.txt") from exc

    db = init_db(ROOT / config.get("database", "data/vinted_books.sqlite3"))
    new_ids: set[str] = set()
    started = now(); seen: set[str] = set(); error = None; completed = True
    scraper = VintedScraper(
        config.get("base_url", "https://www.vinted.pl"),
        config={"timeout": float(config.get("request_timeout_seconds", 15))},
    )
    configured_pages = config.get("page_count")
    page_limit = max(1, min(int(configured_pages if configured_pages is not None else config.get("max_pages", 32)), 32))
    pages_seen = 0
    try:
        for category_id in category_ids:
          for page in range(1, page_limit + 1):
            pages_seen += 1
            print(f"Skanuję kategorię {category_id}, stronę {page}/{page_limit}...", flush=True)
            params = {"catalog_ids": str(category_id), "page": page, "order": "newest_first"}
            items = scraper.search(params)
            if not items:
                break
            for raw in items:
                row = normalize(raw)
                if not row["item_id"]:
                    continue
                seen.add(row["item_id"])
                existing = db.execute("SELECT first_seen FROM offers WHERE item_id = ?", (row["item_id"],)).fetchone()
                first_seen = existing[0] if existing else now()
                if existing is None:
                    new_ids.add(row["item_id"])
                db.execute("""INSERT INTO offers(item_id,title,author,isbn,price,currency,url,first_seen,last_seen,missing_runs,status,raw_json)
                    VALUES(?,?,?,?,?,?,?,?,?,0,'active',?) ON CONFLICT(item_id) DO UPDATE SET
                    title=excluded.title, author=excluded.author, isbn=excluded.isbn, price=excluded.price,
                    currency=excluded.currency, url=excluded.url, last_seen=excluded.last_seen,
                    missing_runs=0, status='active', raw_json=excluded.raw_json""",
                    (row["item_id"], row["title"], row["author"], row["isbn"], row["price"], row["currency"], row["url"], first_seen, now(), row["raw_json"]))
            db.commit()
            if page < page_limit or category_id != category_ids[-1]:
                time.sleep(max(5, float(config.get("delay_seconds", 20))))
    except Exception as exc:  # preserve collected pages and stop on blocking/network errors
        completed = False; error = f"{type(exc).__name__}: {exc}"

    if completed and seen:
        db.execute("UPDATE offers SET missing_runs = missing_runs + 1, status = CASE WHEN missing_runs + 1 >= 3 THEN 'probably_unavailable' ELSE status END WHERE item_id NOT IN ({})".format(",".join("?" * len(seen))), tuple(seen))
        db.commit()
    db.execute("INSERT INTO scans(started_at,pages_requested,items_seen,completed,error) VALUES(?,?,?,?,?)", (started, pages_seen, len(seen), int(completed), error))
    db.commit()
    try:
        from alerts import send_new_opportunity_alerts
        sent = send_new_opportunity_alerts(db, new_ids, float(config.get("min_profit", 20)), int(config.get("max_alerts_per_scan", 5)))
        print(f"Telegram: wysłano {sent} alertów.", flush=True)
    except Exception as exc:
        print(f"Alert warning: {type(exc).__name__}: {exc}")
    db.close()
    return len(seen), completed, error


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ostrożny, tylko-odczytowy skan kategorii Książki na Vinted")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--watch", action="store_true", help="powtarzaj skan według scan_interval_minutes")
    args = parser.parse_args()
    config = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    while True:
        count, completed, error = scan(config)
        print(json.dumps({"items_seen": count, "completed": completed, "error": error}, ensure_ascii=False), flush=True)
        if not args.watch:
            break
        time.sleep(max(300, float(config.get("scan_interval_minutes", 60)) * 60))
