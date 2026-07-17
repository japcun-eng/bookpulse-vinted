"""Send a diagnostic Telegram message using environment variables."""
from __future__ import annotations

import os
import urllib.parse
import urllib.request

token = os.getenv("BOOKPULSE_TELEGRAM_BOT_TOKEN")
chat_id = os.getenv("BOOKPULSE_TELEGRAM_CHAT_ID")
if not token or not chat_id:
    raise SystemExit("Brak BOOKPULSE_TELEGRAM_BOT_TOKEN lub BOOKPULSE_TELEGRAM_CHAT_ID w tym oknie PowerShell.")
payload = urllib.parse.urlencode({"chat_id": chat_id, "text": "BookPulse: test powiadomień Telegram działa."}).encode()
request = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, method="POST")
with urllib.request.urlopen(request, timeout=15) as response:
    print(response.read().decode("utf-8"))
