# Skarbonka: kontekst projektu

Ten plik opisuje domenę, decyzje i format danych. Claude Code czyta go tylko wtedy, gdy potrzebuje wiedzy domenowej, a nie na starcie każdej sesji.

## Jak działa rozliczenie

- Igor robi zakupy dla domu kartą lub BLIK-iem z konta w ING i płaci wszystko z góry.
- Rozliczenie obejmuje wybrany okres (tydzień, 2 tygodnie, miesiąc lub własne daty). Kolejne zaczyna się dzień po końcu poprzedniego.
- Do rozliczenia trafiają tylko części transakcji z ING, nieoznaczone jako osobiste i nieujęte w innym rozliczeniu.
- Rodzice dostają mailem PDF (suma, wykresy kategorii, lista) i Excel do potwierdzenia, po czym zwracają 100% kwoty przelewem. Zakupy robi wyłącznie Igor.
- Statusy rozliczenia: szkic, wysłane, opłacone. Wysłane rozliczenie blokuje edycję swoich transakcji.

## Słownik

| Termin | Znaczenie |
| --- | --- |
| Transakcja | Niezmienny wiersz z banku (data, kwota, kontrahent, tytuł, numer transakcji) |
| Część (allocation) | Fragment transakcji z własną kwotą, kategorią i flagą osobiste. Suma części = kwota transakcji. Bez podziału transakcja ma jedną część |
| Osobiste | Wydatek Igora, nie trafia do rozliczenia (np. Żabka, siłownia, Booking) |
| Sprzedawca (merchant) | Znormalizowana nazwa, np. „Lidl” dla „LIDL PANEWICKA  KATOWICE  POL” |
| Reguła | Warunki (sprzedawca, fraza, kwota od–do, konto, dzień, typ) i wynik (kategoria, osobiste). Reguły wygrywają z ML i LLM |
| Rozliczenie (settlement) | Zestaw części transakcji za okres, z sumą do zwrotu i raportem |
| Import | Jeden wgrany plik CSV z metadanymi i statystykami (nowe, duplikaty, kwarantanna) |

## Format CSV z ING

Na podstawie anonimizowanego eksportu „Lista transakcji” (2026-03):

- Separator `;`, kodowanie najpewniej Windows-1250 (do potwierdzenia na oryginalnym pliku). Wspierać też UTF-8 i UTF-8 z BOM.
- Przed tabelą jest ok. 19 linii metadanych, ich liczba zależy od liczby wybranych rachunków. Zawierają m.in.: numer dokumentu, datę wygenerowania, wybrane rachunki, zakres dat (`2025-12-22 - 2026-02-21`), `Liczba transakcji: 29`, `Suma obciążeń (29): 2601,24 PLN`, `Suma uznań (0)`.
- Wiersz nagłówka: `Data transakcji; Data księgowania; Dane kontrahenta; Tytuł; Nr rachunku; Nazwa banku; Szczegóły; Nr transakcji; Kwota transakcji (waluta rachunku); Waluta; Kwota blokady/zwolnienie blokady; Waluta; Kwota płatności w walucie; Waluta; Konto`, potem puste kolumny.
- Stopka: puste linie i `Dokument ma charakter informacyjny, nie stanowi dowodu księgowego`.
- Daty `RRRR-MM-DD`. Kwota z przecinkiem dziesiętnym, obciążenia ujemne (`-83,25`).
- Numer transakcji w apostrofach: `'202605497304731334'`. To główny klucz deduplikacji.
- `Szczegóły` to typ operacji z dopełnieniem spacjami, np. `TR.KART  `. Pozostałe kody (BLIK, przelewy, uznania) do ustalenia na pełnym eksporcie.
- `Dane kontrahenta`: nazwa, ulica, miasto i kod kraju rozdzielone podwójnymi spacjami, np. ` LIDL PANEWICKA  KATOWICE  POL`, ` BKG*Booking.com Hotel  Amsterdam  N`, ` JMP S.A. BIEDRONKA 6279  KATOWICE`. Spacje na brzegach.
- `Tytuł`: np. ` Płatność kartą 21.02.2026 Nr karty 4246xx1234`.
- `Konto`: nazwa rachunku (np. `KONTO Mobi 18-26`). Jeden plik może zawierać kilka rachunków (np. Mobi i Otwarte Konto Oszczędnościowe), a przelewy między nimi są wewnętrzne.

## Stary notebook (`tracker.ipynb`), do zastąpienia

- `pd.read_csv(skiprows=20, skipfooter=3, usecols=[0,2,8], encoding='latin_1')`: sztywne liczby linii i złe kodowanie (psuje polskie znaki).
- `str.replace('POL','')` usuwa „POL” z każdego miejsca w nazwie (POLOmarket → „OMARKET”).
- Osobiste: regex `ZABKA|GYM|BOOKING` plus ręczne `drop(index=[...])`.
- Kategorie z regexów, pierwsze dopasowanie wygrywa: Zakupy spożywcze (LIDL, BIEDRONKA, CARREFOUR, AUCHAN), Sport (SKARPA, LIMBO, GYM, PREZERO), Paliwo (ORLEN, BP, SHELL), Meble (IKEA, AGATA), Jedzenie/Przekąski (ZABKA), Podróże (WIZZ, RYAN, BOOKING), Jedzenie na Uczelni (STOLOWKA, STUDENCKA, TOMASZ KULA), inaczej Inne. Uwaga: `BP` jako podciąg łapie przypadkowe nazwy.
- Excel: kolumny Data (indeks), Sklep, Kategoria, Kwota, pod spodem sumy per kategoria i `SUMA`, nazwa `rozliczenie_d.m-d.m.rrrr.xlsx`. Wykresy: kołowy udziału kategorii i słupkowy sum.
- Historyczne „etykiety” kategorii pochodzą z tych regexów, więc nie są prawdą do oceny modelu. Zbiór testowy (ok. 300 transakcji) Igor potwierdzi ręcznie.

## Startowe drzewo kategorii

| Główna | Podkategorie | Startowe reguły |
| --- | --- | --- |
| Jedzenie | Zakupy spożywcze, Przekąski, Jedzenie na uczelni, Restauracje | Lidl, Biedronka, Carrefour, Auchan → Zakupy spożywcze; Żabka → Przekąski; Stołówka Studencka, Tomasz Kula → Jedzenie na uczelni |
| Dom | Meble i wyposażenie, Chemia i higiena | IKEA, Agata → Meble i wyposażenie |
| Transport | Paliwo, Komunikacja | Orlen, BP (całe słowo), Shell → Paliwo |
| Sport | Siłownia, Aktywności | Skarpa, Limbo, Gym, Prezero |
| Podróże | Transport, Noclegi | Wizz, Ryanair → Transport; Booking → Noclegi |
| Zdrowie | Apteka, Lekarz | brak |
| Inne | brak | wszystko bez dopasowania |

Startowe reguły „osobiste”: Żabka, Gym, Booking. Drzewo jest do potwierdzenia przez Igora.

## Architektura (skrót)

- Wszystko lokalnie na Windows (Docker Desktop + WSL2). Na zewnątrz wychodzi tylko gotowy raport przez Gmail API.
- Backend: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, uv, Ruff, mypy, pytest.
- Baza: PostgreSQL 17 + pgvector (źródło prawdy). DuckDB i Polars do analityki w notebookach.
- Frontend: React + TypeScript, Vite, TanStack Query i Router, shadcn/ui, Tailwind, ECharts.
- Raporty: Jinja2 + WeasyPrint (PDF), XlsxWriter (Excel).
- Później: Celery + Redis (E2), MLflow (E2), Prometheus + Grafana (E3), serwer MCP (E4).
- LLM: Ollama natywnie na Windows (GPU RTX 2070 8 GB), kontenery łączą się przez `host.docker.internal:11434`. Kandydaci: Qwen3.5-9B (agent), Bielik 11B lub 4.5B v3 (polskie teksty), Gemma 4 E4B (kategoryzacja), BGE-M3 lub multilingual-e5 (embeddingi). Ostateczny wybór po ewaluacji na danych Igora.

## Model danych (skrót)

`accounts`, `import_batches`, `raw_rows`, `transactions` (niezmienne), `merchants`, `merchant_aliases`, `categories` (2 poziomy), `rules` (warunki w JSONB), `allocations` (części transakcji: kwota, kategoria, osobiste, źródło, pewność, rozliczenie), `settlements`, `audit_log`. Później: `forecasts`, `model_runs`, `assistant_messages`, `pending_actions`. Kwoty jako `NUMERIC(12,2)`.

## Kategoryzacja (kolejność warstw)

1. Ręczna zmiana pojedynczej transakcji.
2. Reguły Igora.
3. Pamięć sprzedawcy (stała kategoria w historii).
4. Klasyfikator ML (embedding opisu + kwota, dzień, typ, konto), kalibrowane prawdopodobieństwa.
5. Lokalny LLM dla niskiej pewności (E2).
6. Poniżej progu pewności: kolejka „do sprawdzenia”.

## Model prywatności

- Prawdziwe pliki z banku leżą tylko w `data/` (w `.gitignore`). Claude Code ma zablokowany odczyt tego katalogu.
- Claude Code pracuje wyłącznie na syntetycznych plikach w `tests/fixtures/`, generowanych w dokładnym formacie ING.
- Walidację na prawdziwych plikach Igor uruchamia sam w swoim terminalu. Komenda `inspect` wypisuje tylko statystyki (liczby, sumy, ostrzeżenia, nazwy kolumn), nigdy wierszy, i tylko takie wyjście można wkleić do Claude Code.
- W aplikacji żadnych kluczy do chmurowych LLM.

## Decyzje

| Decyzja | Powód |
| --- | --- |
| Tylko import CSV, bez agregatorów | Brak zgody na udostępnianie danych bankowych stronom trzecim |
| Transakcje niezmienne, zmiany w `allocations` | Podział paragonów, pełna historia zmian, powtarzalność rozliczeń |
| Postgres jako źródło prawdy, DuckDB do analityki | Postgres do aplikacji, DuckDB wygodny w notebookach |
| Ollama poza Dockerem | Najprostsza obsługa GPU na Windows |
| React zamiast Streamlit | Ładniejszy UI, przyszłe konta dla rodziców, nauka frontendu |
| Szkic maila zamiast automatycznej wysyłki w MVP | Kontrola nad tym, co wychodzi do rodziców |
| MVP tylko z ING | mBank wraca w etapie 2 |

## Dokumenty źródłowe (claude.ai, dla Igora)

- Pytania i odpowiedzi: https://claude.ai/artifact/Vpc42CP5j7s24JpQZ3aMCV
- Architektura i tech stack: https://claude.ai/artifact/MyGZH2Zef7krDuGxafFiek
- Wymagania (FR i NFR): https://claude.ai/artifact/6FSWZr1psum4nB3gphoW1k
