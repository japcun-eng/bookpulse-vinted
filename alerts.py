"""Optional Telegram alerts. Disabled unless both environment variables exist."""
from __future__ import annotations

import os
import statistics
import urllib.parse
import urllib.request


def send_new_opportunity_alerts(db, new_ids: set[str], min_profit: float = 20, max_alerts: int = 5) -> int:
    token = os.getenv("BOOKPULSE_TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("BOOKPULSE_TELEGRAM_CHAT_ID")
    if not token or not chat_id or not new_ids:
        return 0
    db.execute("CREATE TABLE IF NOT EXISTS alerts_sent (item_id TEXT PRIMARY KEY, sent_at TEXT NOT NULL)")
    sent = 0
    for item_id in new_ids:
        if db.execute("SELECT 1 FROM alerts_sent WHERE item_id=?", (item_id,)).fetchone():
            continue
        item = db.execute("SELECT * FROM offers WHERE item_id=? AND status='active'", (item_id,)).fetchone()
        if not item or item["price"] is None:
            continue
        key = item["isbn"] or item["title"].strip().lower()
        prices = [r[0] for r in db.execute("SELECT price FROM offers WHERE (isbn=? OR (isbn='' AND lower(title)=?)) AND price IS NOT NULL", (item["isbn"], item["title"].strip().lower()))]
        if len(prices) < 2:
            continue
        resale = statistics.median(prices)
        buy_limit = max(0, resale * 0.55 - 8)
        profit = resale - float(item["price"]) - 8
        if float(item["price"]) > buy_limit or profit < min_profit:
            continue
        text = (f"BookPulse — okazja na Vinted\\n{item['title']}\\n"
                f"Cena: {item['price']} zł | typowa cena: {resale:.2f} zł\\n"
                f"Szacowany zysk: {profit:.2f} zł\\n{item['url']}")
        payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
        request = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, method="POST")
        with urllib.request.urlopen(request, timeout=10):
            pass
        db.execute("INSERT INTO alerts_sent(item_id,sent_at) VALUES(?,datetime('now'))", (item_id,))
        sent += 1
        if sent >= max_alerts:
            break
    db.commit()
    return sent
