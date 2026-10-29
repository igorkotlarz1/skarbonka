# Plan sesji: MVP (tylko ING)

Jedna sesja = jedno zadanie, ok. 2–3 h. Każdą zaczynasz od `/clear` i komendy `/start-sesji N`, kończysz komendą `/koniec-sesji`. Prompty poniżej możesz wkleić zamiast `/start-sesji`, jeśli wolisz.

Model: domyślnie Sonnet. Opus tylko tam, gdzie zaznaczono (projektowanie schematu, ML). Zmiana modelu: `/model`.

---

## S0. Przygotowanie (bez Claude Code)

- Załóż prywatne repo na GitHubie i sklonuj je w WSL2, np. `~/code/skarbonka` (w systemie plików WSL, nie na `C:`, bo Docker działa wtedy dużo szybciej).
- Skopiuj do repo pliki z paczki: `CLAUDE.md`, `.gitignore`, `docs/`, `.claude/`.
- Zainstaluj: Docker Desktop (backend WSL2), uv, Node.js LTS, Ollama dla Windows, Claude Code w WSL.
- Utwórz katalog `data/` i wrzuć tam prawdziwe CSV z ING. Sprawdź `git status`: `data/` nie może się pojawić.
- Pierwszy commit: `chore: project docs and Claude Code setup`.

## S1. Szkielet repozytorium

Wymagania: NFR-11, NFR-14, NFR-15.

> Przeczytaj CLAUDE.md. Zadanie: postaw szkielet backendu w `backend/` (uv, FastAPI z endpointem `/health`, ustawienia przez pydantic-settings i `.env`, Ruff, mypy strict, pytest), `docker-compose.yml` z Postgresem 17 + pgvector i wolumenem, Alembic skonfigurowany pod SQLAlchemy 2, pre-commit (ruff, mypy, blokada plików CSV/XLSX poza `backend/tests/fixtures/`) oraz workflow GitHub Actions (lint, typy, testy). Bez modeli domenowych. Najpierw krótki plan.

Gotowe, gdy: `docker compose up -d db` działa, `uv run pytest` zielone, CI zielone na GitHubie.

## S2. Generator syntetycznych plików ING

Wymagania: NFR-18 (częściowo), podstawa testów parsera. Claude Code nie widzi Twoich plików, więc najpierw buduje generator w dokładnym formacie ING.

> Na podstawie sekcji „Format CSV z ING” w docs/context.md napisz generator syntetycznych eksportów ING w `backend/src/skarbonka/importers/synthetic_ing.py`: metadane z liczbą i sumą transakcji, nagłówek, wiersze (karta, BLIK, przelew wychodzący i przychodzący, zwrot), stopka, kodowanie Windows-1250 lub UTF-8, opcjonalnie dwa rachunki. Realistyczni sprzedawcy z Katowic i Gliwic, sezonowość. Wygeneruj 4 fixtures do `backend/tests/fixtures/ing/` (zwykły, dwa konta, UTF-8 z BOM, uszkodzony wiersz). Najpierw plan.

Gotowe, gdy: fixtures istnieją, a Ty porównasz je wzrokowo z prawdziwym plikiem w swoim edytorze (bez pokazywania go Claude Code).

## S3. Parser ING

Wymagania: FR-02 do FR-11.

> Napisz parser ING w `backend/src/skarbonka/importers/ing.py` jako czyste funkcje: wykrycie kodowania i separatora, znalezienie nagłówka po nazwach kolumn, odczyt metadanych, czyszczenie pól (apostrofy, spacje, kwoty z przecinkiem jako Decimal, daty, typ operacji), kwarantanna wierszy z niezgodną liczbą kolumn, walidacja liczby i sumy z metadanymi. Wynik jako modele Pydantic. Testy najpierw, na fixtures z S2. Dodaj komendę CLI `uv run skarbonka inspect <plik>`, która wypisuje tylko statystyki (liczba wierszy, suma, zakres dat, typy operacji z liczebnością, ostrzeżenia), nigdy wierszy.

Gotowe, gdy: testy zielone, a Ty uruchomisz `inspect` na prawdziwym pliku **w swoim terminalu** (nie przez `!` w Claude Code) i liczby zgadzają się z bankiem. Wynik `inspect` możesz wkleić Claude Code.

## S4. Schemat bazy i import do bazy (Opus)

Wymagania: FR-01, FR-09, FR-10, FR-14, FR-16, NFR-04, NFR-05.

> Zaprojektuj modele SQLAlchemy i pierwszą migrację Alembic dla: accounts, import_batches, raw_rows, transactions, merchants, merchant_aliases, categories, rules, allocations, settlements, audit_log (opis w docs/context.md, „Model danych”). Potem serwis importu: plik → parser → deduplikacja po numerze transakcji lub odcisku → zapis transakcji z jedną częścią (allocation) → statystyki importu. Endpoint `POST /imports` (wiele plików) i `GET /imports`. Testy integracyjne na Postgresie z Dockera. Najpierw plan i schemat do akceptacji.

Gotowe, gdy: podwójny import fixture daje 0 duplikatów, a historia importów pokazuje liczby.

## S5. Sprzedawcy i silnik reguł

Wymagania: FR-21, FR-30 do FR-34, FR-13.

> Dodaj normalizację sprzedawcy (rozbicie pola kontrahenta na nazwę, miasto i kraj, usunięcie kodu kraju tylko na końcu, prefiksów typu „BKG*” i numerów sklepów) oraz silnik reguł z priorytetami (warunki w JSONB: sprzedawca, fraza jako całe słowo lub regex, kwota od–do, konto, dzień tygodnia, typ; wynik: kategoria i/lub osobiste). Seed startowych kategorii i reguł z docs/context.md. Endpoint podglądu reguły na historii. Wykrywanie przelewów między własnymi rachunkami. Testy, w tym przypadek „POLOmarket”.

Gotowe, gdy: warianty Lidla, Biedronki i Auchan z fixtures trafiają do jednego sprzedawcy, a reguły z notebooka działają.

## S6. Klasyfikator ML (Opus)

Wymagania: FR-35 do FR-37.

> Zbuduj klasyfikator kategorii i flagi osobiste w `backend/src/skarbonka/categorization/`: embedding opisu (sentence-transformers, model wielojęzyczny z docs/context.md, działający na CPU) + cechy (kwota, dzień tygodnia, typ, konto), regresja logistyczna z kalibracją. Skrypt treningu i ewaluacji (macro-F1, dokładność per kategoria, porównanie z regułami z notebooka) uruchamiany lokalnie, zapis modelu do `models/` (w .gitignore). Pipeline kategoryzacji: ręczne > reguły > pamięć sprzedawcy > ML > kolejka do sprawdzenia. Na fixtures z S2.

Gotowe, gdy: trening i ewaluację uruchomisz sam na prawdziwych danych, a do Claude Code wkleisz tylko metryki.

## S7. Frontend: szkielet i lista transakcji

Wymagania: FR-20, FR-23, FR-24, NFR-17.

> Postaw `frontend/` (Vite, React, TypeScript strict, TanStack Query i Router, shadcn/ui, Tailwind, tryb jasny i ciemny, UI po polsku). Pierwszy ekran: lista transakcji z filtrami (okres, kategoria, sprzedawca, osobiste, do sprawdzenia, tekst), przełącznik osobiste przy wierszu, zaznaczanie wielu i zbiorcza zmiana kategorii. Potrzebne endpointy dopisz w backendzie. Najpierw plan ekranów.

Gotowe, gdy: przeglądasz transakcje z fixtures i oznaczasz osobiste.

## S8. Przegląd i podział paragonów

Wymagania: FR-25, FR-26, FR-28, FR-29.

> Dodaj kolejkę „do sprawdzenia” ze skrótami klawiszowymi (kategoria, osobiste, następna) i okno podziału transakcji na części (kwota, kategoria, osobiste; suma części musi równać się kwocie). Każda zmiana do audit_log. Propozycja „zrobić z tego regułę?” po ręcznej poprawce.

Gotowe, gdy: przegląd tygodnia z fixtures zajmuje kilka minut bez myszki.

## S9. Rozliczenia

Wymagania: FR-50 do FR-53, FR-58.

> Dodaj rozliczenia: utworzenie za okres (domyślnie od dnia po ostatnim), tylko części z ING, nieosobiste i nieujęte w innym rozliczeniu; podgląd z sumą, sumami per kategoria i porównaniem z poprzednim okresem; statusy szkic, wysłane, opłacone; blokada transakcji po wysłaniu; dopasowanie przelewu zwrotnego. Testy na sumach co do grosza. Ekran w UI.

Gotowe, gdy: suma rozliczenia z fixtures zgadza się z obliczeniem ręcznym.

## S10. Raport PDF i Excel

Wymagania: FR-54, FR-55.

> Wygeneruj raport rozliczenia: PDF (Jinja2 + WeasyPrint w kontenerze) z sumą do zwrotu, wykresem kołowym i słupkowym kategorii, listą i porównaniem z poprzednim okresem, oraz Excel w układzie ze starego notebooka (Data, Sklep, Kategoria, Kwota, sumy per kategoria, SUMA, nazwa `rozliczenie_d.m-d.m.rrrr.xlsx`) z formatowaniem walutowym. Pobieranie z UI.

Gotowe, gdy: PDF poprawnie otwiera się na telefonie, polskie znaki są poprawne.

## S11. Szkic w Gmailu

Wymagania: FR-56, FR-57.

> Dodaj integrację z Gmail API (OAuth, token zapisany lokalnie poza repo) tworzącą szkic z PDF i Excelem w załącznikach oraz treścią z szablonu. Instrukcja konfiguracji projektu w Google Cloud w `docs/gmail.md`. Odbiorcy i szablon w ustawieniach.

Gotowe, gdy: szkic pojawia się w Twoim Gmailu.

## S12. Prosty dashboard

Wymagania: FR-70 do FR-72.

> Dodaj dashboard: przełącznik widoku (Rozliczenia, Moje wydatki), wykres kołowy i słupkowy kategorii dla okresu (ECharts), kafelki (suma, zmiana do poprzedniego okresu, do sprawdzenia, kwota czekająca na zwrot). Klik w kategorię filtruje listę transakcji.

## S13. Odbiór MVP

Wymagania: kryteria „Kiedy MVP jest gotowe”, NFR-12, NFR-13.

> Przejdź listę kryteriów MVP z docs/goals.md: uzupełnij brakujące testy (pokrycie parsera i rozliczeń co najmniej 90%), test regresji „suma jak w starym notebooku” na fixture, README z instrukcją uruchomienia. Wypisz, co jeszcze nie spełnia kryteriów.

Gotowe, gdy: robisz pierwsze prawdziwe rozliczenie bez notebooka.
