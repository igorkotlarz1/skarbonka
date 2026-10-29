# Jak pracować z Claude Code w tym projekcie

## Prywatność: najważniejsza zasada

Claude Code działa w chmurze Anthropic: wszystko, co przeczyta (pliki, wynik komend), trafia do modelu. Dlatego:

- Prawdziwe CSV leżą tylko w `data/` (w `.gitignore`).
- `.claude/settings.json` blokuje odczyt `data/`, a hook `.claude/hooks/block_raw_data.py` blokuje każde narzędzie (Bash, Read, Grep, Glob, Edit, Write), którego argumenty wskazują `data/`. Grep i Glob dodatkowo pomijają pliki z `.gitignore`.
- Komendy na prawdziwych danych (`uv run skarbonka inspect data/...`, trening modelu) uruchamiasz w **osobnym terminalu**, nie przez `!` w Claude Code, bo wynik `!` trafia do rozmowy. Wklejasz tylko statystyki.
- Hook wymaga `python3`, więc uruchamiaj Claude Code w WSL2 (tam, gdzie leży repo).

Sprawdzenie, że ochrona działa: w Claude Code wpisz „pokaż pierwszą linię pliku z katalogu data”. Powinieneś zobaczyć komunikat „Blocked: data/ holds real bank exports…”. Komenda `/hooks` pokazuje, że hook jest aktywny.

## Rytm sesji

1. `/clear` (świeży kontekst, zero kosztu starej rozmowy).
2. `/start-sesji N`: Claude czyta tylko ostatni wpis z `docs/progress.md` i sekcję SN z `docs/plan-sesji.md`, proponuje plan i czeka.
3. Akceptujesz plan albo poprawiasz go jednym zdaniem.
4. Praca w małych krokach: test, kod, test. Gdy Claude idzie w złą stronę, od razu `Esc`, a `Esc Esc` (lub `/rewind`) cofa do wcześniejszego punktu.
5. `/koniec-sesji`: testy, lint, wpis do dziennika, propozycja commita. Commitujesz.

## Oszczędzanie tokenów

| Nawyk | Dlaczego |
| --- | --- |
| `/clear` między sesjami i niepowiązanymi zadaniami | Każda wiadomość wysyła całą dotychczasową rozmowę |
| `/rename` przed `/clear`, potem `/resume` | Możesz wrócić do starej sesji, nie trzymając jej otwartej |
| Po dłuższej przerwie raczej nowa sesja niż kontynuacja | Pierwsza wiadomość po przerwie przetwarza cały kontekst od nowa (wygasa cache) |
| Plan mode (`Shift+Tab`) na start zadania | Tańsze niż poprawianie kodu napisanego w złą stronę |
| Sonnet domyślnie, Opus tylko w S4 i S6 (`/model`) | Sonnet wystarcza do większości kodu i jest tańszy |
| Niższy `/effort` przy prostych zadaniach | Mniej tokenów myślenia |
| Konkretne prompty z nazwami plików | Claude nie przeszukuje całego repo |
| Testy pojedynczego pliku z `-q` | Krótkie wyjście, mniej kontekstu |
| `/compact` z instrukcją, gdy sesja się wydłuża | Np. `/compact zostaw zadanie, zmienione pliki i błędy testów` |
| `/usage` i `/context` co jakiś czas | Widzisz, co zjada limit i kontekst |
| Wyłącz nieużywane serwery MCP (`/mcp`) | Każdy dodaje coś do kontekstu |
| Bez subagentów i zespołów agentów w tym projekcie | Każdy agent to osobny kontekst i osobne koszty |
| CLAUDE.md krótki (ok. 60 linii) | Ładuje się przy każdej sesji. Wiedza domenowa leży w `docs/context.md` i jest czytana tylko w razie potrzeby |

## Skille

Skill to folder z plikiem `SKILL.md`. Claude zna tylko jego opis, a pełną treść ładuje dopiero przy użyciu, więc nie kosztuje dużo, dopóki go nie wywołasz. Wywołujesz go ręcznie przez `/nazwa` albo Claude sam po niego sięga, gdy pasuje do zadania (chyba że skill ma `disable-model-invocation: true`, jak nasze dwa).

Gdzie leżą: projektowe w `.claude/skills/<nazwa>/SKILL.md` (w repo), osobiste w `~/.claude/skills/`, z wtyczek instalowanych przez `/plugin`. Pełna lista: wpisz `/` w Claude Code.

### Nasze skille projektowe (w paczce)

| Skill | Kiedy |
| --- | --- |
| `/start-sesji N` | Początek każdej sesji z planu |
| `/koniec-sesji` | Koniec każdej sesji |

### Wbudowane, które się przydadzą

| Skill | Kiedy w tym projekcie |
| --- | --- |
| `/code-review` | Przed scaleniem większej zmiany, szczególnie parsera i rozliczeń |
| `/simplify` | Po skończonej funkcji, żeby uprościć kod bez szukania błędów |
| `/security-review` | Przed upublicznieniem repo (E5) i po dodaniu Gmail API oraz text-to-SQL (E4) |
| `/debug` | Gdy coś nie działa i przyczyna nie jest oczywista |
| `/fewer-permission-prompts` | Po kilku sesjach: dopisuje bezpieczne komendy do listy dozwolonych |

`/init` pomijamy, bo `CLAUDE.md` już jest.

### Z wtyczek (opcjonalnie)

- `skill-creator` (`/plugin install skill-creator@claude-plugins-official`): pomaga pisać własne skille. Przyda się w E2 do skilla „nowy bank” przy dodawaniu mBanku.
- Pozostałe przeglądasz komendą `/plugin`. Instaluj tylko to, czego naprawdę używasz, bo opis każdego skilla jest w kontekście przy każdej wiadomości. `/skill-doctor` pokazuje, które skille są kosztowne lub nieużywane.

### Własne skille na później

- `nowa-migracja`: schemat zmiany modelu, migracja Alembic, test migracji w górę i w dół.
- `nowy-bank` (E2): checklista dodania parsera banku (generator fixtures, parser, `inspect`, testy).
- `ewaluacja-modelu` (E2/E3): uruchom ewaluację, zapisz do MLflow, porównaj z aktywnym modelem.
