# Skarbonka: cele projektu

> Local-first AI do rozliczania domowych wydatków. Wszystkie modele działają lokalnie, żadne dane finansowe nie trafiają do chmury.

## Problem

Robię zakupy dla domu i rozliczam się z nich z rodzicami: płacę wszystko z góry, a raz na tydzień, dwa tygodnie albo miesiąc wysyłam im PDF z podsumowaniem i Excel z listą wydatków, a oni zwracają mi 100% kwoty. Dziś robię to w notebooku Jupyter (`tracker.ipynb`), który wymaga ręcznego czyszczenia CSV z ING, ręcznego usuwania transakcji osobistych po indeksach i kategoryzuje wydatki regexami.

## Cele produktowe

1. **Rozliczenie bez bólu.** Od pliku CSV z ING do szkicu maila z PDF i Excelem w kilka minut, bez ręcznego czyszczenia i bez edytowania kodu.
2. **Kategorie, którym można ufać.** Reguły, ML i lokalny LLM przypisują kategorie z poziomem pewności. Ja tylko przeglądam to, co niepewne, a system uczy się z moich poprawek.
3. **Osobiste osobno.** Jedno kliknięcie oznacza transakcję (lub jej część po podziale paragonu) jako osobistą, więc nie trafia do rozliczenia.
4. **Wgląd w wydatki.** Dashboard z udziałem kategorii, trendami z kilku lat i prognozą na kolejny miesiąc z przedziałami niepewności.
5. **Asystent.** Pytam po polsku o swoje wydatki, a asystent odpowiada na podstawie danych i potrafi wykonać zadania (np. przekategoryzować, przygotować rozliczenie) po moim zatwierdzeniu.

## Cele nauki

- Konteneryzacja całego systemu (Docker Compose) na Windows z WSL2.
- Lokalne LLM na RTX 2070 8 GB: Ollama, wybór i ewaluacja modeli, structured output, tool calling.
- MCP, agent z narzędziami, text-to-SQL z bezpiecznymi uprawnieniami.
- Kolejki zadań (Celery + Redis), monitoring (Prometheus + Grafana), MLflow.
- Frontend w React + TypeScript (pierwszy raz, z pomocą Claude Code).
- Prognozowanie szeregów czasowych z przedziałami konformalnymi i uzgadnianiem hierarchii.

## Cele portfolio

- Publiczne repozytorium z danymi wyłącznie syntetycznymi, trybem demo i zielonym CI.
- README z diagramem architektury, zrzutami ekranu i wynikami ewaluacji modeli (kategoryzacja, prognozy, asystent).
- Projekt, który pokazuje warsztat Data Scientisty (metryki, kalibracja, testy wsteczne) i inżyniera (testy, migracje, kontenery).

## Mierniki sukcesu MVP

- Import pliku z ING bez ręcznej ingerencji, liczba i suma transakcji zgodne z podsumowaniem banku.
- Ponowny import tego samego okresu dodaje 0 duplikatów.
- Klasyfikator lepszy od regexów z notebooka na zbiorze testowym przejrzanym przeze mnie.
- Przegląd tygodnia lub miesiąca zajmuje mniej niż 5 minut.
- Suma rozliczenia zgodna z obliczeniem ręcznym co do grosza.
- PDF i Excel trafiają jako szkic do Gmaila.
- Całość startuje komendą `docker compose up`.

## Etapy

| Etap | Zakres |
| --- | --- |
| MVP | Import i czyszczenie CSV z ING, deduplikacja, sprzedawcy, reguły, klasyfikator ML, przegląd z podziałem paragonów i flagą osobiste, rozliczenie, PDF + Excel, szkic w Gmailu, prosty dashboard |
| E2 Inteligencja | Warstwa LLM w kategoryzacji, Celery + Redis, ponowny trening z poprawek, MLflow i sekcja analityczna, obserwowany folder, import mBanku |
| E3 Analityka | Trendy, anomalie, prognozy per kategoria, cechy zewnętrzne, testy wsteczne, Grafana |
| E4 Asystent | Serwer MCP, agent z text-to-SQL, akcje z zatwierdzaniem, podsumowanie do maila, głos |
| E5 Portfolio i rodzice | Generator danych do demo, README, publiczne repo, logowanie z rolą rodzica, Tailscale, kopie zapasowe na Raspberry Pi, skan paragonów |

## Czego nie robimy

- Połączeń z API banków ani agregatorów PSD2 (decyzja: tylko CSV, żadnych wycieków).
- Chmurowych modeli LLM w aplikacji (OpenAI, Anthropic i inne).
- Aplikacji mobilnej (na razie tylko web na komputerze).
- Obsługi wielu walut poza kwotą w PLN podaną przez bank.
- mBanku w MVP (wraca w etapie 2).
