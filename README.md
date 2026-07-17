# BookPulse — lokalne MVP

BookPulse analizuje migawki ofert książek i wskazuje pozycje o wysokim prawdopodobieństwie szybkiej sprzedaży oraz atrakcyjnej marży.

## Uruchomienie

Wymagany jest Python 3.10+.

```powershell
python app.py
```

Następnie otwórz `http://127.0.0.1:8765`.

Panel demonstracyjny korzysta z `data/listings.csv`. Skaner Vinted jest osobnym, ostrożnym modułem odczytowym i zapisuje historię do SQLite. Nie loguje się do konta, nie kupuje, nie omija blokad ani CAPTCHA.

## Skanowanie kategorii Książki na Vinted

1. Zainstaluj zależność: `pip install -r requirements.txt`.
2. `config.json` zawiera początkowy zestaw kategorii książkowych Vinted: beletrystyka, literatura faktu, literatura klasyczna, młodzieżowa, dziecięca oraz komiksy/manga.
3. `page_count: null` oznacza skanowanie kolejnych stron aż do końca kategorii, z limitem `max_pages: 32`; `delay_seconds` pozostaw na minimum 20.
4. Uruchom: `python vinted_scan.py`.

Tryb ciągły: `python vinted_scan.py --watch`. Domyślnie powtarza skan co godzinę; zatrzymasz go przez `Ctrl+C`.

## Alerty Telegram

Alerty są domyślnie wyłączone. Aby je włączyć, ustaw zmienne środowiskowe przed uruchomieniem skanera:

```powershell
$env:BOOKPULSE_TELEGRAM_BOT_TOKEN = "token_od_BotFather"
$env:BOOKPULSE_TELEGRAM_CHAT_ID = "twoj_chat_id"
```

Token nie trafia do repozytorium. Alert powstaje tylko dla nowej oferty, która jest poniżej wyliczonego limitu zakupu i daje co najmniej `min_profit` zł.

Skaner zatrzymuje się przy błędzie sieciowym lub odpowiedzi blokującej. Zniknięcie oferty jest oznaczane jako `probably_unavailable` dopiero po trzech pełnych, udanych skanach; nie jest to pewne potwierdzenie sprzedaży.

## Format danych wejściowych

Kolumny CSV:

`source,id,title,author,isbn,price,condition,url,first_seen,last_seen,status`

Daty muszą mieć format ISO, np. `2026-07-17T09:30:00+02:00`. `status` przyjmuje `active`, `sold`, `removed` albo `expired`.

Przykładowe dane znajdują się w `data/listings.csv`.

## Co mierzy MVP

- tempo znikania oferty,
- udział ofert znikających w ciągu 24 godzin,
- medianę ceny ofert,
- szacowaną marżę względem ceny zakupu,
- poziom pewności, że zniknięcie oznacza sprzedaż.

Wynik jest heurystyką. Zniknięcie oferty może oznaczać również usunięcie lub wygaśnięcie, dlatego system pokazuje pewność zamiast twierdzić, że zna faktyczną sprzedaż.
