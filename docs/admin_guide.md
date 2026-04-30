# Instrukcja obsługi — Atrio FM Chatbot

Przewodnik dla administratora. Napisany z perspektywy osoby widzącej tylko interfejs webowy — bez wiedzy technicznej.

**Wersje tego samego przewodnika**

- **Ten plik (Markdown)** — wygodny do edycji i na GitHubie.
- **[admin_guide.html](admin_guide.html)** — ta sama treść w interaktywnej stronie (zakładki jak w Canvasie); otwórz w przeglądarce (podwójne kliknięcie lub przeciągnij plik do okna Chrome/Firefox).
- **Aplikacja (frontend)** — po zalogowaniu: **`/help`** — skrócony przewodnik **po angielsku** z tego samego menu co Chat (link „Help”).
- **Canvas w Cursorze** (`~/.cursor/projects/.../canvases/admin-guide.canvas.tsx`) — żywy panel obok chatu w IDE. Zostaje na Twoim dysku wraz z projektem Cursor; **nie jest automatycznie w repozytorium Git** — jeśli chcesz go mieć na innym komputerze, skopiuj ten plik lub używaj HTML / MD z repo.

---

## Spis treści

1. [Przegląd systemu](#1-przegląd-systemu)
2. [Chat z botem](#2-chat-z-botem)
3. [Dashboard — zarządzanie ticketami](#3-dashboard--zarządzanie-ticketami)
4. [Luki wiedzy (Knowledge Gaps)](#4-luki-wiedzy-knowledge-gaps)
5. [Dokumenty — baza wiedzy bota](#5-dokumenty--baza-wiedzy-bota)
6. [Training Review](#6-training-review)
7. [Training Quality — analiza i poprawa bota](#7-training-quality--analiza-i-poprawa-bota)

---

## 1. Przegląd systemu

Atrio FM Chatbot to narzędzie do zarządzania budynkiem (Facility Management). System składa się z trzech głównych części dostępnych dla admina:

| Część | Opis |
|-------|------|
| **Chat z botem** | Bot odpowiada na pytania o budynek i automatycznie tworzy zlecenia serwisowe (tickety) gdy wykryje usterkę. |
| **Panel admina** | Zarządzanie ticketami, użytkownikami, dokumentami wiedzy i lukami w wiedzy bota. |
| **Panel jakości** | Analiza błędów bota, ocena jakości odpowiedzi i możliwość poprawiania zachowania systemu. |

### Mapa systemu

| URL / Zakładka | Do czego służy | Kto ma dostęp |
|----------------|----------------|---------------|
| `/chat` | Rozmowa z botem FM | Każdy zalogowany |
| `/dashboard` | Lista i zarządzanie ticketami | Każdy zalogowany |
| `/admin` → Tickets | Notatki serwisowe, korekty klasyfikacji | Tylko admin |
| `/admin` → Knowledge Gaps | Pytania bez odpowiedzi do uzupełnienia | Tylko admin |
| `/admin` → Users | Zarządzanie kontami | Tylko admin |
| `/admin` → Documents | Edycja bazy wiedzy bota | Tylko admin |
| `/admin/training` | Przegląd przykładów do treningu | Tylko admin |
| `/admin/training-quality` | Analiza błędów i poprawa promptów | Tylko admin |

> **Pierwsze logowanie:** Zaloguj się pod adresem `/admin/login`. Domyślna nazwa użytkownika to `admin`. Hasło zostało ustawione przez osobę techniczną w konfiguracji systemu.

> **Ważne — co robić codziennie:** Sprawdzaj Knowledge Gaps (luki wiedzy) — to są pytania na które bot nie znalazł odpowiedzi. Każda luka to sygnał, że baza wiedzy wymaga uzupełnienia.

---

## 2. Chat z botem

**URL:** `/chat`

Chat to interfejs rozmowy z botem FM. Bot odpowiada na pytania o budynek, klasyfikuje zgłoszenia i automatycznie tworzy tickety serwisowe.

### Jak prowadzić rozmowę

1. Otwórz `/chat` w lewym menu.
2. Wpisz pytanie lub opis problemu w pole tekstowe na dole.
3. Wciśnij Enter lub kliknij Wyślij.
4. Bot odpowie w czasie rzeczywistym — tekst pojawia się stopniowo.
5. Pod odpowiedzią zobaczysz: kategorię, priorytet i czy został utworzony ticket.

### Kiedy bot tworzy ticket

**Tworzy ticket gdy:**
- Problem wymaga interwencji technika
- Coś jest zepsute lub nie działa
- Problem dotyczy elektryki, hydrauliki, HVAC, wind
- Wykryje słowa: awaria, uszkodzenie, nie działa, przeciek

**Nie tworzy ticketu gdy:**
- Pytanie jest informacyjne (godziny, zasady)
- Pytanie dotyczy statusu istniejącego zgłoszenia
- Ogólne pytanie o procedury
- Podziękowanie lub potwierdzenie

### Priorytety ticketów

| Priorytet | Kiedy | Przykład |
|-----------|-------|---------|
| **URGENT** | Bezpośrednie zagrożenie życia lub bezpieczeństwa | Pożar, wyciek gazu, aktywny alarm, zalanie |
| **HIGH** | Poważna usterka wymagająca naprawy tego dnia | Brak ogrzewania zimą, klimatyzacja w serwerowni |
| **NORMAL** | Usterka uciążliwa ale nie krytyczna | Przepalona żarówka, zacięte drzwi |
| **LOW** | Drobna niedogodność | Prośba o wymianę mebla |

### Przykłady użycia

**Przykład 1 — zgłoszenie usterki:**
> Wpisz: *"W toalecie damskiej na 3 piętrze ciągle kapie woda z kranu. Kapie od wczoraj."*
>
> Bot odpowie: Klasyfikacja Plumbing / NORMAL / Ticket #123 utworzony.

**Przykład 2 — pytanie informacyjne:**
> Wpisz: *"Do której godziny jest otwarty budynek w weekendy?"*
>
> Bot odpowie z informacją z dokumentacji. Brak ticketu — to pytanie informacyjne.

**Przykład 3 — pilna awaria:**
> Wpisz: *"Na korytarzu 2p widać dym i czuć spalony plastik przy gniazdku!"*
>
> Bot odpowie: Klasyfikacja Electrical / URGENT / Ticket #124 + instrukcja bezpieczeństwa.

### Przycisk "Create ticket anyway"

Jeśli bot odpowiedział bez tworzenia ticketu, a uważasz że powinien — pod odpowiedzią pojawi się przycisk **"Create ticket anyway"**. Kliknij go aby ręcznie zgłosić zlecenie serwisowe.

### Nowy wątek

Przycisk **"New Chat"** w bocznym menu czyści historię i zaczyna nową rozmowę. Używaj go gdy zmieniasz temat rozmowy — bot pamięta kontekst poprzednich wiadomości (ostatnie 60).

### Czego NIE robić

- Nie traktuj odpowiedzi bota jako jedynego działania — zawsze sprawdź czy ticket dotarł do technika.
- Nie wysyłaj wielokrotnie tego samego pytania — bot pamięta kontekst i może to zaburzyć rozmowę.
- Nie używaj chatu do eskalacji awarii — w razie URGENT dzwoń bezpośrednio na linię awaryjną.

> **Limit zapytań:** System pozwala na maks. 30 wiadomości na minutę per użytkownik. Jeśli dostaniesz błąd "Too Many Requests" — odczekaj chwilę.

---

## 3. Dashboard — zarządzanie ticketami

**URL:** `/dashboard`

Dashboard to pełna lista ticketów serwisowych. Jako admin widzisz wszystkie tickety wszystkich użytkowników. Zwykły użytkownik widzi tylko swoje.

### Filtrowanie

1. Otwórz `/dashboard`.
2. Użyj filtrów na górze: Kategoria, Priorytet, Status.
3. Filtry działają razem — możesz np. wybrać URGENT + Open.

### Zmiana statusu ticketu

1. Kliknij na ticket w tabeli.
2. W oknie szczegółów zmień status z listy.
3. Zapisz — zmiana jest natychmiastowa.

### Stany ticketu

| Status | Znaczenie | Kiedy ustawić |
|--------|-----------|---------------|
| **Open** | Nowe zgłoszenie, nikt nie zaczął | Domyślny przy tworzeniu |
| **In Progress** | Technik pracuje nad problemem | Gdy wyślesz zadanie do technika |
| **Resolved** | Problem rozwiązany | Gdy technik potwierdził naprawę |

### Notatki serwisowe (Resolution Notes)

W panelu admina (`/admin` → Tickets) przy każdym tickecie możesz dodawać notatki operacyjne:

1. Wejdź w `/admin`, znajdź ticket w sekcji Ticket Operations.
2. Kliknij **Add Resolution Note**.
3. Wypełnij: opis pracy, użyte części, koszt, czas (minuty).
4. Zapisz — notatka zostaje dołączona do ticketu.

### Korekta klasyfikacji

Jeśli bot źle sklasyfikował ticket (np. HVAC zamiast Plumbing):

1. W `/admin` → Ticket Operations znajdź ticket.
2. Kliknij **Classification Override**.
3. Wybierz pole do zmiany: `category`, `priority` lub `department`.
4. Wpisz poprawną wartość i zatwierdź.
5. Zmiana zapisuje się w historii korekt i aktualizuje dane treningowe bota.

### Eksport CSV

Przycisk **"Export CSV"** na dashboardzie pobiera widoczne tickety jako plik arkusza kalkulacyjnego. Filtry są uwzględniane — eksportujesz tylko to co widzisz na ekranie.

### Czego NIE robić

- Nie ustawiaj statusu Resolved jeśli nie masz potwierdzenia od technika — to zaburza statystyki.
- Nie ignoruj ticketów URGENT — powinny być obsłużone w ciągu godzin.
- Nie usuwaj ticketów ręcznie — system nie ma przycisku usuń, to celowe (historia).

---

## 4. Luki wiedzy (Knowledge Gaps)

**URL:** `/admin` → zakładka **Knowledge Gaps**

Knowledge Gaps to lista pytań, na które bot nie znalazł odpowiedzi w dokumentacji budynku. Każda luka to sygnał, że baza wiedzy wymaga uzupełnienia.

> **Dlaczego to ważne:** Jeśli bot nie zna odpowiedzi na pytanie, zwykle odpowiada ogólnikowo lub mówi że nie ma informacji. Uzupełniając luki wiedzy bezpośrednio poprawiasz jakość odpowiedzi dla wszystkich użytkowników.

### Jak przeglądać luki

1. Wejdź w `/admin` i kliknij zakładkę **Knowledge Gaps**.
2. Domyślnie widoczne są nowe luki (status: `new`).
3. Kliknij w lukę żeby zobaczyć szczegóły: pełne pytanie, data, powiązany ticket.
4. Zmień status na `reviewed` jeśli przeglądasz ale jeszcze nie uzupełniasz.

### Jak uzupełnić lukę

1. Kliknij w lukę lub otwórz `/admin/gaps/:id`.
2. W polu **"Doc name"** wpisz nazwę pliku, np. `godziny_otwarcia.md`.
3. W polu **"Content"** wpisz treść odpowiedzi **po angielsku** (bot działa w języku angielskim).
4. Wybierz tryb: **append** doda do istniejącego pliku, **overwrite** zastąpi cały plik.
5. Zaznacz **"Auto-reindex"** żeby bot od razu widział nową wiedzę.
6. Kliknij **Resolve Gap** — plik zapisany, luka oznaczona jako resolved.

### Przykłady uzupełniania luk

**Przykład 1 — godziny otwarcia:**

Pytanie użytkownika: *"What time does the building close on Saturdays?"*

Doc name: `building_hours.md`

Content (po angielsku):
```
## Building Opening Hours

Monday–Friday: 7:00 AM – 10:00 PM
Saturday: 8:00 AM – 6:00 PM
Sunday: Closed

Security desk is always staffed 24/7.
```

Tryb: `append`

---

**Przykład 2 — parkowanie dla gości:**

Pytanie użytkownika: *"Where can visitors park?"*

Doc name: `07_parking_transport.md`

Content:
```
## Visitor Parking

Visitor parking is available in Level B1. Visitors must register at reception.
Maximum 4 hours. Barrier code available from the reception desk.
```

Tryb: `append` (doda na koniec istniejącego pliku o parkowaniu)

### Statusy luk

| Status | Znaczenie |
|--------|-----------|
| `new` | Świeża luka, nikt jeszcze nie reagował |
| `reviewed` | Admin widział, jeszcze nie uzupełnił |
| `resolved` | Uzupełnione — bot już zna odpowiedź |

### Czego NIE robić

- Nie pisz treści po polsku — bot operuje w języku angielskim.
- Nie używaj trybu `overwrite` jeśli nie jesteś pewien co jest w pliku — możesz usunąć istniejącą wiedzę.
- Nie zapomnij zaznaczyć **Auto-reindex** — bez tego bot nie zobaczy nowej treści mimo że plik jest zapisany.
- Nie twórz wielu małych plików dla jednego tematu — lepiej appendować do istniejącego pliku.

---

## 5. Dokumenty — baza wiedzy bota

**URL:** `/admin` → zakładka **Documents**

Dokumenty to baza wiedzy bota. Pliki Markdown z katalogu `docs_fm/` są indeksowane i używane przez bota do odpowiadania na pytania.

### Istniejące dokumenty

| Plik | Temat |
|------|-------|
| `01_building_general_info.md` | Ogólne informacje o budynku |
| `02_hvac_systems.md` | Klimatyzacja i wentylacja |
| `03_electrical_systems.md` | Systemy elektryczne |
| `04_plumbing_water.md` | Hydraulika i woda |
| `05_fire_safety_emergency.md` | Pożar i nagłe sytuacje |
| `06_security_access.md` | Ochrona i dostęp |
| `07_parking_transport.md` | Parking i transport |
| `08_it_network.md` | IT i sieć |
| `09_elevators.md` | Windy |
| `10_cleaning_waste.md` | Sprzątanie i odpady |
| `11_meeting_rooms_spaces.md` | Sale konferencyjne |
| `12_building_rules_policies.md` | Regulaminy i zasady |

### Edycja istniejącego dokumentu

1. Kliknij na nazwę pliku w liście dokumentów.
2. Pojawi się edytor tekstu z obecną treścią.
3. Edytuj treść (format Markdown: `# Nagłówek`, `## Podsekcja`, `- lista`).
4. Kliknij **Save**.
5. Po zapisaniu kliknij **Reindex** żeby bot zobaczył zmiany.

### Dodanie nowego dokumentu

1. Kliknij **New Document**.
2. Wpisz nazwę pliku z rozszerzeniem `.md` (np. `catering_rules.md`).
3. Wpisz treść w języku angielskim — używaj nagłówków Markdown.
4. Zapisz, potem kliknij **Reindex**.

### Upload gotowego pliku

1. Kliknij **Upload**.
2. Wybierz plik z dysku: `.txt`, `.md`, `.csv`, `.pdf` lub `.docx`.
3. Opcja **Overwrite** — nadpisuje jeśli plik o tej nazwie już istnieje.
4. Opcja **Auto-reindex** — od razu indeksuje po wgraniu.
5. PDF i DOCX są automatycznie konwertowane na tekst.

### Reindeksowanie

**Po każdej zmianie w dokumentach musisz kliknąć Reindex.** To przebudowuje bazę wektorową — bez tego bot nadal używa starej wiedzy.

> Reindeksowanie trwa kilkanaście do kilkudziesięciu sekund. Poczekaj na potwierdzenie z liczbą zaindeksowanych chunków.

### Czego NIE robić

- Nie usuwaj pliku bez upewnienia się, że jego treść nie jest jedynym źródłem wiedzy na ten temat.
- Nie zapomnij o **Reindex** po każdej zmianie — to najczęstszy błąd.
- Nie wgrywaj bardzo dużych plików (ponad kilka MB) — mogą spowolnić indeksowanie.
- Nie pisz treści po polsku — bot pracuje po angielsku.

---

## 6. Training Review

**URL:** `/admin/training`

Training Review to panel do przeglądania przykładów treningowych. Każda rozmowa z botem i każdy przeprowadzony test generuje rekord — to dane do przyszłego ulepszenia modelu.

> **Po co to robić?** Zatwierdzanie i poprawianie przykładów buduje zestaw danych wysokiej jakości. Nie musisz robić tego codziennie — raz na tydzień wystarczy.

### Filtry przykładów

| Filtr | Co pokazuje | Kiedy przeglądać |
|-------|-------------|-----------------|
| `pending` | Nowe, niezatwierdzone — bot mógł się mylić | Priorytetowo — zawierają błędy do poprawy |
| `approved` | Zatwierdzone poprawne odpowiedzi | Gdy chcesz sprawdzić co zostało zaakceptowane |
| `edited` | Ręcznie poprawione przez admina | Gdy chcesz zobaczyć historię korekt |
| `rejected` | Odrzucone błędne przykłady | Rzadko — kontrola archiwum |

### Jak przeglądać przykłady

1. Wejdź w `/admin/training`.
2. Ustaw filtr na `pending` — to są przykłady wymagające uwagi.
3. Kliknij w przykład lub użyj strzałek `←` `→` na klawiaturze żeby nawigować.
4. Sprawdź: **Input** (pytanie użytkownika), **Actual** (co bot odpowiedział), **Ideal** (co powinien).
5. Sprawdź **Human Notes** — opis błędu np. `category expected=Plumbing actual=HVAC`.
6. Zdecyduj: Approve, Edit lub Reject.

### Skróty klawiaturowe

| Klawisz | Akcja |
|---------|-------|
| `←` | Poprzedni przykład |
| `→` | Następny przykład |
| `A` | Approve (zatwierdź) |
| `R` | Reject (odrzuć) |

### Kiedy Approve, Edit, Reject?

| Akcja | Kiedy użyć |
|-------|-----------|
| **Approve** | Bot odpowiedział dobrze — kategoria, priorytet i treść są poprawne |
| **Edit** | Bot się mylił — popraw `ideal_output` ręcznie i zapisz |
| **Reject** | Przykład nie nadaje się do treningu — pytanie bez sensu lub niejednoznaczne |

### Eksport danych

- **Export NDJSON** — pełny eksport approved + edited
- **Export V1 JSONL (train)** — format gotowy do fine-tuningu
- **Export CSV** — arkusz do przeglądania w Excelu
- **Build V1 Files** — generuje wszystkie pliki treningowe w folderze `data/`

### Czego NIE robić

- Nie zatwierdzaj przykładów na ślepo — sprawdź czy kategoria i priorytet są poprawne.
- Nie edytuj przykładów gdy nie jesteś pewien co jest poprawną odpowiedzią.
- Nie odrzucaj wszystkich `pending` en masse — część może być poprawna.

---

## 7. Training Quality — analiza i poprawa bota

**URL:** `/admin/training-quality`

Training Quality to zaawansowany panel do analizy błędów bota i poprawy jego zachowania. Pozwala bez wiedzy technicznej poprawiać instrukcje bota na podstawie danych z błędnych odpowiedzi.

> **Jak to działa w skrócie:** System analizuje błędy bota, grupuje je według typu, a potem AI sugeruje konkretną poprawkę do instrukcji. Ty zatwierdzasz lub edytujesz sugestię — i bot od razu działa lepiej.

### Sekcja 1: Mismatch Groups (Grupy błędów)

Tabela z pogrupowanymi błędami bota — bez użycia AI, tylko na podstawie zarejestrowanych danych.

| Typ błędu | Co oznacza | Przykład |
|-----------|-----------|---------|
| `category_mismatch` | Bot sklasyfikował do złej kategorii | Kondensacja → HVAC zamiast Plumbing |
| `priority_mismatch` | Bot przypisał zły priorytet | Gaśnica → URGENT zamiast HIGH |
| `ticket_mismatch` | Ticket nie powinien / powinien zostać utworzony | Żaluzje → bot nie stworzył ticketu |
| `response_tokens` | Bot pominął kluczowe informacje | Pytanie o godziny → bot nie podał godzin |

### Sekcja 2: Eval Runs (Testy jakości)

Możesz uruchomić pełny automatyczny test bota na ~80 sprawdzonych pytaniach testowych.

1. Kliknij **Run Eval**.
2. Bot odpowie na ~80 pytań z zestawu testowego. To trwa 2–5 minut.
3. Status zmienia się: `running` → `done`.
4. Wyniki pokazują dokładność: ogólną, kategorii, priorytetu, ticketów.
5. Porównuj wyniki przed i po zmianach.

> **Tylko jeden eval naraz:** Jeśli klikniesz Run Eval gdy już trwa — dostaniesz błąd. Poczekaj na zakończenie poprzedniego.

### Sekcja 3: Suggested Fixes (Sugestie AI)

Analizator AI przegląda grupy błędów i proponuje konkretne poprawki do instrukcji bota.

1. Kliknij **Analyze Pending**.
2. AI analizuje błędy — to zajmuje kilkanaście sekund.
3. Pojawią się sugestie per typ błędu: konkretny tekst do dodania do instrukcji bota.
4. Przeczytaj sugestię. Jeśli jest sensowna — kliknij **Apply**.
5. Jeśli chcesz zmodyfikować — kliknij **Edit** w modalu przed zatwierdzeniem.

> **Cache analizy:** Wyniki analizy są przechowywane przez 24 godziny. Baner na górze informuje kiedy ostatnio była wygenerowana analiza. Limit: 1 analiza per 5 minut.

### Sekcja 4: Active Overrides (Aktywne poprawki)

Lista aktywnych zmian w instrukcjach bota. Każda zatwierdzona sugestia pojawia się tutaj i wpływa na odpowiedzi bota w czasie rzeczywistym.

| Kolumna | Co oznacza |
|---------|-----------|
| Error type | Typ błędu który poprawka adresuje |
| Approved change | Tekst dodany do instrukcji bota |
| Baseline accuracy | Dokładność PRZED zastosowaniem poprawki |
| After accuracy | Dokładność PO zastosowaniu poprawki |
| Delta | Zmiana w % — pozytywna to poprawa |
| Rollback | Cofa poprawkę — bot wraca do poprzedniego stanu |

### Przykład pełnego workflow

1. Zauważasz w Mismatch Groups: 12 przypadków `category_mismatch` (kondensacja → HVAC zamiast Plumbing).
2. Klikasz **Run Eval** — zapisujesz bazowy wynik (np. 78% accuracy).
3. Klikasz **Analyze Pending** — AI sugeruje: *"Condensation, moisture and water drips → always Plumbing. HVAC is only for air temperature and ventilation."*
4. Sugestia jest sensowna — klikasz **Apply**, potwierdzasz w modalu.
5. Bot natychmiast dostaje nową instrukcję.
6. Po kilku dniach klikasz **Run Eval** ponownie — sprawdzasz czy accuracy wzrosła.
7. Jeśli accuracy spadła — klikasz **Rollback** przy tej poprawce.

### Limity i ograniczenia

| Ograniczenie | Wartość | Co zrobić gdy osiągniesz |
|--------------|---------|--------------------------|
| Maks. aktywnych overrides | 5 | Rollback starych zanim dodasz nową |
| Analiza per czas | 1 na 5 minut | Poczekaj — wynik z cache jest nadal aktualny |
| Baseline wymagany przed Apply | Max 24h stary | Uruchom Run Eval |
| Min. confidence bez edycji | 0.5 (50%) | Edytuj sugestię ręcznie zanim zatwierdź |

### Czego NIE robić

- Nie aplikuj sugestii jeśli jej nie rozumiesz — przeczytaj co dokładnie zostanie dodane do instrukcji bota.
- Nie ignoruj delta accuracy — jeśli po override accuracy spada, zrób Rollback.
- Nie akumuluj 5 overrides bez sprawdzenia ich wpływu — to utrudnia diagnozowanie problemów.
- Nie uruchamiaj Eval w godzinach szczytu użycia — eval zużywa limit API i może spowolnić chat dla użytkowników.

---

*Ostatnia aktualizacja: kwiecień 2026*
