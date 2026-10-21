# Code review — 21 października 2026

Sprawdzona wersja `main`: `7a33a198f7c4b5b5aeac75bc5c4ea4a909f8fa6f`.
Kod skanera i raportu: commit `455cafd`. Zakres: harmonogram, wznowienia,
utrwalenie historii, porównania graficzne, publikacja i koszt przetwarzania.
Poniższe pozycje są ustaleniami review i rekomendacjami do wdrożenia.

## Najważniejsze ustalenia

### 1. P1 — raport z błędami blokuje automatyczną próbę naprawczą

Źródła: [schedule.py](../src/pracownie/schedule.py#L29),
[cli.py](../src/pracownie/cli.py#L150),
[github.py](../src/pracownie/github.py#L226).

CLI publikuje raport przed sprawdzeniem, czy wszystkie domeny zakończyły się
błędem. Kontrola harmonogramu uznaje samą obecność zatwierdzonego raportu i jego
plików za wystarczającą do pominięcia kolejnego skanu. Nie ocenia udanych odczytów.

Reprodukcja z lokalnym MockTransport GitHuba: strona główna i karta projektu
zwracają HTTP 503; raport zostaje opublikowany; wywołanie kontrolne na
22.10.2026 o 06:07 zwraca `run_scan=false`. Nie wykonywano żadnych zapisów w
prawdziwym GitHubie podczas tej reprodukcji.

**Skutek:** próba zapasowa pomaga przy braku publikacji, ale może pominąć nawet
raport bez jednego udanego odczytu. Dotyczy również częściowych braków danych.

**Naprawa:** oddzielić dostępność raportu od gotowości danych. Zapisywać w
manifeście liczbę świeżych odczytów podstawowych oraz strony z błędami
przejściowymi. Próba zapasowa powinna zachować poprawne wyniki i ponowić
timeouty, 429 i 5xx, z uwzględnieniem Retry-After. Trwałe blokady 403 pokazywać
jawnie, bez bezwarunkowego wielokrotnego ponawiania.

### 2. P2 — przestawienie obrazów może ukryć zmianę ich rozmiaru

Źródło: [observations.py](../src/pracownie/observations.py#L114).

Po dopasowaniu obrazu pod innym selektorem ustawiane jest `moved_image=True`.
Warunek w linii 158 wyłącza wtedy całe porównanie prostokąta, obejmujące również
szerokość i wysokość.

Reprodukcja: dwa te same obrazy zamieniają miejsca i zwiększają rozmiar z
300 × 200 do 600 × 400 px. Wynik: pusta lista `facts` oraz opis o kolejności lub
aktywnym slajdzie. Różnica zrzutów pozostaje widoczna, ale konkretna zmiana
rozmiaru nie trafia do opisanych zmian.

**Naprawa:** po dopasowaniu obrazu zawsze porównywać rozmiar i styl; osobno
oceniać położenie i rotację. Samo wystąpienie tych samych adresów grafik nie
dowodzi, że zmienił się wyłącznie aktywny slajd.

### 3. P2 — ograniczenie zakresu grafiki nie jest widoczne w wyniku

Źródła: [visuals.js](../src/pracownie/visuals.js#L31),
[observations.py](../src/pracownie/observations.py#L226).

Kolektor kończy zapis po 100 elementach. Opis zmian zachowuje pierwsze 20 faktów.
Nie zapisuje znacznika ucięcia ani liczby pominiętych elementów lub zmian.
Reprodukcja: 25 zmienionych kolorów daje 20 faktów bez informacji o pozostałych.
W zapisanej bazie z 21.10 trzy strony osiągają limit 100 elementów:
kbprojekt.pl, projektdomudo100m2.pl i uarchitekta.pl — strony główne. Osiągnięcie
limitu nie dowodzi samo w sobie, ile elementów pominięto; obecny zapis tego nie
rozstrzyga.

**Naprawa:** zapisywać zakres, wersję kolektora, `truncated`, liczbę elementów
i liczbę faktów. Skracać widok, zachowując pełny dostępny wynik w danych.
Przy zmianie zakresu kolektora nie uznawać brakującego elementu za usuniętą
grafikę bez zgodnej bazy porównawczej.

### 4. P2 — powtarzalne właściwości mogą otrzymać ten sam identyfikator wpisu

Źródło: [journal.py](../src/pracownie/journal.py#L48).

Identyfikator nie uwzględnia elementu źródłowego ani scenariusza. Dwa elementy
opisane jako „treść strony”, z takim samym odziedziczonym kolorem przed i po,
tworzą dwa wpisy z tym samym `id`. Reprodukcja: dwa identyczne fakty dają dwa
wiersze i jeden unikalny identyfikator.

**Skutek:** pełny dziennik HTML może mieć powtórzone kotwice; liczba obserwacji
po grupowaniu może zostać zaniżona. W sprawdzonym dzisiejszym raporcie nie
stwierdzono takich kolizji — błąd potwierdzono na kontrolowanym przykładzie.

**Naprawa:** nadać obserwacji tożsamość obejmującą element, scenariusz i daty,
a grupowanie tych samych zmian biznesowych wykonywać oddzielnie. Dokładne
duplikaty jednego odczytu usuwać przed nadaniem identyfikatorów.

### 5. P2 — pomiar terminu publikacji wyprzedza gotowość dashboardu

Źródła: [github.py](../src/pracownie/github.py#L316),
[cli.py](../src/pracownie/cli.py#L158).

`published_at` jest pobierane przed aktualizacją wydania, zapisem dokumentów
dashboardu i przesłaniem końcowego manifestu. CLI używa tego wcześniejszego czasu
do oceny, czy raport był gotowy na 08:00.

**Skutek:** rozpoczęcie publikacji przed 08:00 i zakończenie po 08:00 może zostać
opisane jako dotrzymanie terminu. To ustalenie z kolejności wywołań w kodzie;
nie jest twierdzeniem, że dzisiejszy raport miał taką sytuację graniczną.

**Naprawa:** mierzyć gotowość po udanym zapisie dashboardu i końcowego manifestu.
Oddzielić czas skanu, rozpoczęcie publikacji i faktyczną gotowość raportu.

## Optymalizacje po naprawie błędów

1. **Oddzielić szybki raport podstawowy od kosztownych interakcji.** Ostatni
   pełny skan zakończył odczyty podstawowe po około 4 min 21 s, cały skan po
   17 min 19 s. Zachować checkpoint po stronach głównych i stałych kartach;
   następnie uzupełniać zakładki i opcje z wyraźnym statusem zakresu.
2. **Zmniejszyć liczbę kopii danych i obrazów.** Ten sam skan zapisał około
   298 MB obrazów bieżącego stanu i 418 MB plików PNG dowodów, przed kompresją.
   Publikacja tworzy dodatkowo archiwum źródłowe, archiwum widoku i samodzielny
   HTML. Rozważyć współdzielenie obrazów po skrócie, zapis pełnych zrzutów
   podstawowych oraz fragmentów dla interakcji, zachowując dowody każdej zmiany.
   Przy retencji 180 dni monitorować wielkość archiwów i zapas do limitu
   rozpakowanego stanu 1,5 GB.
3. **Ustalić priorytet biznesowy drobnych zmian.** „Jutro” → „dzisiaj” i drobne
   przesunięcie kafelka powinny pozostawać dostępne w szczegółach. Najwyżej
   pokazywać nowy przekaz, kampanię, dodatek, warunek oferty i istotny baner.
4. **Dodać kontrolę gotowości przed 08:00.** Oddzielny lekki krok powinien
   sygnalizować brak świeżego raportu lub brak podstawowych odczytów. Sam sukces
   procesu albo obecność plików nie wystarcza. Ograniczyć dublujące się terminy
   cron wynikające z obsługi czasu letniego, zachowując obsługę Europe/Warsaw.

## Jutro: czwartek, 22 października 2026

| Czas Europe/Warsaw | Zgodne z kodem zachowanie |
| --- | --- |
| 05:17, czyli 03:17 UTC | Pierwsze planowane wywołanie pełnego skanu 65 domen. |
| 06:07, czyli 04:07 UTC | Próba zapasowa, jeśli nie ma zatwierdzonego raportu; czeka na wspólną blokadę, jeśli poprzednia praca nadal trwa. |
| 06:17 i 07:07 | Dodatkowe wywołania wynikające z obsługi obu przesunięć UTC; również pomijane po zatwierdzeniu raportu. |
| Przed 08:00 | Cel gotowości raportu. GitHub Actions może opóźnić cron; obecny kod nie daje gwarancji terminu. |

Zakres obejmuje stronę główną i ten sam zapamiętany projekt każdej pracowni,
również w weekendy. Oczekiwane porównanie: 21 → 22 października. Brak dzisiejszego
odczytu danej strony oznacza jutro lukę lub bazę, a nie pełne porównanie dzień
do dnia. Nowe pola rozmiaru/grubości pisma i wyglądu przycisków nie występują
w dzisiejszej zapisanej bazie: pierwszy zapis będzie najwcześniej 22.10,
a porównanie tych nowych właściwości najwcześniej 23.10 po dwóch udanych skanach.

Nowy harmonogram wdrożono 21.10 o 08:49:20 czasu polskiego, po planowanych
porannych terminach. Jutro będzie jego pierwsze rzeczywiste uruchomienie
o nowych godzinach. W publicznej historii potwierdzono wcześniejsze uruchomienie
typu `schedule` 20.10; nie stanowi ono testu nowego harmonogramu.

## Wykonane sprawdzenia

- Lokalny `main` jest zgodny z `origin/main` w sprawdzonym commicie.
- 13 testów harmonogramu i workflow przeszło; obejmują weekendy, zmianę czasu,
  kolejkę publikacji i datę 22.10.2026. Dodatkowo zasymulowano cztery jutrzejsze
  wywołania z rzeczywistych wyrażeń cron.
- Cztery kontrolowane reprodukcje potwierdziły ustalenia 1–4.
- [Testy wdrożonego kodu](https://github.com/MateuszD0/Pracownie/actions/runs/39607530509): sukces.
- [Ostatnia publikacja dashboardu](https://github.com/MateuszD0/Pracownie/actions/runs/39608012473): sukces.
- [Ostatni udany pełny przebieg](https://github.com/MateuszD0/Pracownie/actions/runs/39562829866): 20 min 12 s łącznie z przygotowaniem i publikacją.
- [Historia automatycznych wywołań](https://github.com/MateuszD0/Pracownie/actions/workflows/monitor.yml?query=event%3Aschedule).

Wniosek: konfiguracja przewiduje jutrzejszy skan i ma zapas czasu względem
ostatniego udanego przebiegu. Najpilniejszą poprawką przed poleganiem na próbie
zapasowej jest ustalenie nr 1. Zielone testy nie eliminują potwierdzonych luk.
