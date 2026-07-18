from __future__ import annotations

import csv
import json
import statistics
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
DATA_FILE = ROOT / "data" / "listings.csv"
PORT = 8765


def parse_date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_listings() -> list[dict]:
    history = ROOT / "data" / "vinted_books.sqlite3"
    if history.exists():
        db = sqlite3.connect(history)
        db.row_factory = sqlite3.Row
        rows = []
        for row in db.execute("SELECT * FROM offers"):
            item = dict(row)
            item["source"] = "Vinted"
            item["first_seen_dt"] = parse_date(item["first_seen"])
            item["last_seen_dt"] = parse_date(item["last_seen"])
            item["duration_hours"] = max(0, (item["last_seen_dt"] - item["first_seen_dt"]).total_seconds() / 3600)
            rows.append(item)
        db.close()
        return rows
    with DATA_FILE.open(encoding="utf-8-sig", newline="") as stream:
        rows = []
        for row in csv.DictReader(stream):
            row["price"] = float(row["price"])
            row["first_seen_dt"] = parse_date(row["first_seen"])
            row["last_seen_dt"] = parse_date(row["last_seen"])
            row["duration_hours"] = max(0, (row["last_seen_dt"] - row["first_seen_dt"]).total_seconds() / 3600)
            rows.append(row)
        return rows


def analyse(rows: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        key = row["isbn"].strip() or f"{row['title'].strip().lower()}|{row['author'].strip().lower()}"
        groups.setdefault(key, []).append(row)

    result = []
    for key, offers in groups.items():
        prices = [x["price"] for x in offers]
        observed = [x for x in offers if x["status"] != "active"]
        fast = [x for x in observed if x["duration_hours"] <= 24 and x["status"] in {"sold", "probably_unavailable"}]
        confirmed = sum(x["status"] == "sold" for x in observed)
        ambiguous = sum(x["status"] in {"removed", "expired", "probably_unavailable"} for x in observed)
        sell_through = len(fast) / len(observed) if observed else 0
        median_price = statistics.median(prices)
        recommended_buy = max(0, median_price * 0.55 - 8)
        expected_profit = max(0, median_price - recommended_buy - 8)
        confidence = confirmed / (confirmed + ambiguous) if confirmed + ambiguous else 0.25
        score = round(100 * (0.55 * sell_through + 0.25 * min(expected_profit / 50, 1) + 0.20 * confidence), 1)
        exemplar = min(offers, key=lambda x: x["price"])
        result.append({
            "key": key,
            "title": exemplar["title"], "author": exemplar["author"], "isbn": exemplar["isbn"],
            "offer_count": len(offers), "observed_count": len(observed), "fast_sales": len(fast),
            "occurrences": len(offers),
            "sell_through_24h": round(sell_through * 100, 1), "median_price": round(median_price, 2),
            "recommended_buy": round(recommended_buy, 2), "expected_profit": round(expected_profit, 2),
            "confidence": round(confidence * 100, 1), "score": score, "example_url": exemplar["url"],
            "first_seen": exemplar["first_seen"],
            "last_seen": exemplar["last_seen"],
            "last_seen_is_disappearance": exemplar["status"] != "active",
        })
    return sorted(result, key=lambda x: x["score"], reverse=True)


HTML = """<!doctype html><html lang='pl'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>BookPulse</title><style>
body{font:15px system-ui,sans-serif;background:#f5f7fb;color:#172033;margin:0}main{max-width:1100px;margin:0 auto;padding:36px 20px}h1{margin:0 0 5px;font-size:32px}.sub{color:#62708a;margin-bottom:28px}.cards{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:24px}.card{background:white;border:1px solid #e1e6ef;border-radius:12px;padding:16px 20px;min-width:170px}.num{font-size:25px;font-weight:700}.label{color:#68758b;font-size:12px;text-transform:uppercase;letter-spacing:.05em}.tabs{display:flex;gap:8px;margin:8px 0 14px}.tab{border:1px solid #d5dce8;background:#fff;color:#516078;border-radius:8px;padding:9px 14px;cursor:pointer}.tab.active{background:#3659b8;color:#fff;border-color:#3659b8}.search{width:100%;box-sizing:border-box;border:1px solid #d5dce8;border-radius:8px;padding:12px 14px;margin:0 0 14px;font-size:15px;background:white}table{background:white;border-collapse:collapse;width:100%;border:1px solid #e1e6ef;border-radius:12px;overflow:hidden}th,td{text-align:left;padding:13px 12px;border-bottom:1px solid #edf0f5}th{font-size:12px;color:#65728a;text-transform:uppercase;background:#fafbfe}tr:last-child td{border:0}.pill{font-weight:700;color:#146c43}.muted{color:#6d7890;font-size:12px}.empty{text-align:center;padding:35px;color:#68758b}a{color:#3659b8}
</style></head><body><main><h1>BookPulse</h1><div class='sub'>Ranking książek na podstawie historii ofert — lokalne MVP</div>
<div class='cards'><div class='card'><div class='label'>Oferty</div><div class='num' id='offers'>—</div></div><div class='card'><div class='label'>Tytuły</div><div class='num' id='titles'>—</div></div><div class='card'><div class='label'>Sprzedaże &lt;24 h</div><div class='num' id='fast'>—</div></div></div>
<div class='tabs'><button class='tab active' id='rankingTab'>Ranking opłacalności</button><button class='tab' id='topTab'>Top 50 — najszybsza sprzedaż</button></div>
<input class='search' id='search' type='search' placeholder='Szukaj w bazie: tytuł, autor lub ISBN...'>
<table><thead><tr><th>Ranking / książka</th><th>Wystąpienia</th><th>Wystawiono</th><th>Zniknęła</th><th>Sprzedaż &lt;24 h</th><th>Mediana</th><th>Max zakup</th><th>Zysk</th><th>Pewność</th></tr></thead><tbody id='rows'></tbody></table>
<p class='muted'>To estymacja: zniknięcie oferty nie zawsze oznacza sprzedaż. Ceny nie uwzględniają jeszcze podatków ani indywidualnych kosztów operacyjnych.</p></main><script>
let data;let top=false;function render(items){const query=document.querySelector('#search').value.trim().toLowerCase();const filtered=query?items.filter(x=>`${x.title} ${x.author||''} ${x.isbn||''}`.toLowerCase().includes(query)):items;document.querySelector('#rows').innerHTML=filtered.map((x,i)=>`<tr><td><b>${i+1}. ${x.title}</b><br><span class='muted'>${x.author||'Nieznany autor'} · ${x.isbn||'brak ISBN'}</span></td><td>${x.occurrences}</td><td>${formatDate(x.first_seen)}</td><td>${x.last_seen_is_disappearance?formatDate(x.last_seen):'<span class="muted">nadal aktywna</span>'}</td><td>${x.sell_through_24h}%</td><td>${x.median_price.toFixed(2)} zł</td><td>${x.recommended_buy.toFixed(2)} zł</td><td class='pill'>${x.expected_profit.toFixed(2)} zł</td><td>${x.confidence}%</td></tr>`).join('')||`<tr><td colspan='9' class='empty'>Brak wyników wyszukiwania</td></tr>`}function setTab(isTop){top=isTop;document.querySelector('#rankingTab').classList.toggle('active',!top);document.querySelector('#topTab').classList.toggle('active',top);render(top?data.top50:data.items)}document.querySelector('#rankingTab').onclick=()=>setTab(false);document.querySelector('#topTab').onclick=()=>setTab(true);document.querySelector('#search').oninput=()=>render(top?data.top50:data.items);fetch('/api/summary').then(r=>r.json()).then(d=>{data=d;document.querySelector('#offers').textContent=d.offers;document.querySelector('#titles').textContent=d.titles;document.querySelector('#fast').textContent=d.fast_sales;render(d.items)})
function formatDate(value){if(!value)return'—';const d=new Date(value);return isNaN(d)?value:d.toLocaleString('pl-PL',{dateStyle:'short',timeStyle:'short'})}
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            body = HTML.encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
        elif path == "/api/summary":
            rows = load_listings(); items = analyse(rows)
            top50 = sorted(items, key=lambda x: (x["sell_through_24h"], x["fast_sales"], x["confidence"], x["score"]), reverse=True)[:50]
            body = json.dumps({"offers": len(rows), "titles": len(items), "fast_sales": sum(x["fast_sales"] for x in items), "items": items, "top50": top50}, ensure_ascii=False).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
        else:
            self.send_error(404); return
        self.send_header("Content-Length", str(len(body))); self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # The browser closed or refreshed the local page while the response was sent.
            pass

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    print(f"BookPulse działa pod http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
