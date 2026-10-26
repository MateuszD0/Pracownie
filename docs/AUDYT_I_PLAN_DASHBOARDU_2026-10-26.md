# Czytelny monitoring pracowni: audyt i plan poprawy

Stan z 26 października 2026 r. To propozycja zmian i kryteriów odbioru, nie informacja o wdrożeniu nowego dashboardu.

**Główna diagnoza:** system zbiera dużo dowodów, ale nadal przekazuje odbiorcy zadanie interpretacji różnic. Potrzebna jest krótka odprawa o komunikacji konkurencji: **co się zmieniło, gdzie, jak pewne jest ustalenie i gdzie zobaczyć dowód**. Więcej wykresów ani więcej wykrytych różnic nie rozwiąże tego problemu.

Zakres pozostaje zgodny z zamówieniem: 66 pracowni, strona główna i jedna zapamiętana karta projektu, codziennie również w weekend, raport do 08:00 Europe/Warsaw, historia 180 dni. Komunikacja, promocje, kody, dodatki i istotne zmiany grafiki mają pierwszeństwo przed cenami. Nie dodajemy automatycznego wybierania nowych projektów.

## Co sprawdzono

- Aktualne `DASHBOARD.md`, szczegóły pracowni, opublikowany HTML, manifest publikacji i dane raportu 25 → 26.10.2026.
- Kod selekcji, grupowania, prezentacji, publikacji, gotowości i konfiguracji wysyłki.
- Trzy kroki odbiorcy: podsumowanie dnia → szczegóły zmiany → kompletność pracowni; dodatkowo wyszukiwanie oraz widok telefonu.
- Źródłowy raport: `2026-10-26T151141.729914-0000-cfafb6fe`; stan `main`: `ddfb0acb646509ca29a766be955ff3d4a5f7e9dc`.

Materiały: [dane kontrolne](audyt-2026-10-26/dowody.json), [notatnik z obliczeniami](audyt-2026-10-26/kontrola-raportu.ipynb), [wydanie źródłowe](https://github.com/MateuszD0/Pracownie/releases/tag/monitor-report-2026-10-26).

## 1. Najważniejsze luki

| Priorytet | Ustalenie oparte na dowodach | Skutek dla odbiorcy | Konkretna poprawa |
| --- | --- | --- | --- |
| P0 | Wewnętrzna lista zarządcza zawiera 177 obserwacji, z czego 130 sklasyfikowano jako wygląd. W podsumowaniu pojawia się m.in. przesunięcie treści o 18 px. | Liczba obserwacji i techniczne zmiany konkurują z istotnymi komunikatami. Nie oznacza to, że wszystkie 130 obserwacji jest błędnych. | Oddzielić obserwację techniczną od zdarzenia biznesowego. Do głównego widoku dopuszczać zmianę przekazu, oferty lub ekspozycji, którą da się konkretnie opisać. |
| P0 | Zniknięcie komunikatu Planujdom „WYBRANE PROJEKTY Z RABATEM -15%” trafia do zwiniętych pozostałych różnic, bo nie wykonano dodatkowego sprawdzenia dla tych zapisów. | Ważna niepewność jest mniej widoczna niż drobna zmiana układu. | Dwie niezależne cechy: ważność i pewność. Ważna, niezweryfikowana zmiana ma trafić do widocznej sekcji „Ważne do sprawdzenia” oraz kolejki weryfikacji monitora. |
| P0 | W opublikowanym przenośnym HTML wpisanie `mgprojekt.com.pl` pozostawia 66 widocznych pracowni. Eksporter usuwa skrypty, lecz zostawia pole wyszukiwania. | Użytkownik nie może szybko odnaleźć pracowni i nie wie, że kontrolka nie działa. | W statycznym eksporcie usunąć nieaktywne kontrolki. W docelowym widoku internetowym udostępnić działające wyszukiwanie i filtry; testować dokładnie publikowany plik. |
| P0 | Są jednocześnie 128 świeżych odczytów, 121 porównywalnych stron i 60 pracowni z porównaniem obu stron. 4 świeże odczyty mają jakość częściową. | Odbiorca nie wie, jak duży zakres rzeczywiście oceniono dzień do dnia. | Główna miara: „60/66 pracowni — porównano obie strony”. Obok „6 wymaga uwagi”, z przyczyną. Szczegółowe miary zachować w diagnostyce. |
| P0 | Pierwsza publikacja 26.10: 08:26:46 czasu polskiego. Workflow poczty 40347566111 ma wynik `success`, ale krok „Wyślij porównanie” jest `skipped`. | Zielony workflow nie mówi, czy raport dotarł na czas ani czy wysłano wiadomość. | Pokazywać oddzielnie: dane, publikację, termin i wysyłkę. Sprawdzać rezultat użytkowy pod publicznym adresem i potwierdzenie SMTP. |
| P1 | Jedna zapowiedź Alexander Studio ma dwa bloki zmian. Nagłówek Archand występuje w obserwacjach tekstu i wyglądu. Obecne grupowanie jest głównie według strony i kategorii. | Jedna akcja pracowni wygląda jak kilka niezależnych zmian; kilka różnych akcji może być ukrytych pod jednym reprezentatywnym zdaniem. | Zdarzenie z własnym identyfikatorem i listą dowodów. Łączyć obserwacje tej samej kampanii, zachowując osobno miejsca wystąpienia na stronie głównej i karcie. |
| P1 | Bieżące porównanie obejmuje odczyty 08:00–16:12. Kolejna publikacja usuwa wcześniejsze pliki wydania z tego samego dnia. | Poranny raport może zmienić się po południu; odnośnik do konkretnego pliku starszej wersji może przestać działać. | Zamknięta edycja poranna, oznaczone korekty i stałe odnośniki do zdarzeń. Zachować użyte dowody podczas całego okresu retencji. |
| P1 | Formalna inspekcja adapterów ma status `pending` dla 66/66 pracowni. Plik pokrycia pokazuje 64 częściowe i 2 błędy, choć porównywalnych stron jest 121. | Brakuje wiarygodnej informacji o sprawdzeniu zakładek, dodatków i scenariuszy per serwis. | Osobno oceniać odczyt podstawowy, porównanie dzień do dnia i wykonanie dodatkowych interakcji. Uzupełniać odbiór adapterów na rzeczywistych przypadkach. |

Status `pending` nie dowodzi, że dotąd niczego nie testowano. Dowodzi, że formalny rejestr odbioru nie jest utrzymany. Podobnie brak wykrytych dodatków nie dowodzi braku takich zmian w serwisach.

Wiele pożądanych zasad opisano już w [CEL_I_JAKOSC_DASHBOARDU.md](CEL_I_JAKOSC_DASHBOARDU.md). Luka procesowa to brak skutecznego sprawdzania ich w finalnie opublikowanym raporcie. Dokumentacja nadal używa też liczby 65; liczbę pracowni trzeba generować z konfiguracji.

## 2. Ocena ścieżki użytkownika

1. **Podsumowanie dnia — wymaga poprawy.** Uporządkowany wygląd, lecz brak ostrej selekcji ważności. Pierwszy ekran komputera pokazuje tylko kilka wierszy; na telefonie sam wstęp zajmuje niemal cały ekran. Liczniki nie wyjaśniają biznesowego znaczenia zmian. [Zrzut komputera](audyt-2026-10-26/01-podsumowanie.png), [zrzut telefonu](audyt-2026-10-26/04-telefon.png).
2. **Przejście do dowodu — częściowo działa.** Link „Porównaj przed / po” otwiera właściwą pracownię. Są daty i tekst przed/po. Jedna zapowiedź promocji rozpada się jednak na dwa bloki, a zrzuty wymagają kolejnych rozwinięć. [Zrzut szczegółów](audyt-2026-10-26/02-szczegoly.png).
3. **Sprawdzenie kompletności — wymaga poprawy.** Wszystkie pracownie są obecne, ale szeroka tabela miesza wyniki biznesowe, piksele i informacje o brakach. Użytkownik musi sam rozpoznać przyczynę braku porównania. W przenośnym HTML wyszukiwanie nie działa. [Zrzut listy](audyt-2026-10-26/03-kompletnosc.png).

Zrzuty przedstawiają rzeczywisty opublikowany HTML, nie projekt nowego ekranu. Treść GitHub Markdown sprawdzono z aktualnej strony, ale arkusze stylów GitHuba były niedostępne przez proxy środowiska; niestylizowany zrzut odrzucono. Nie oceniamy na jego podstawie wyglądu GitHuba. Test objął Chromium 1440×1000 i 390×844, a nie pełny audyt WCAG ani czytnik ekranu. Strona nie rozlewała całego dokumentu na telefonie; pięć kontenerów tabel miało wewnętrzne przewijanie poziome.

## 3. Proponowany ekran: odprawa o zmianach konkurencji

**Cel odbioru: w 60 sekund rozumiesz, co zasługuje na uwagę, co pozostaje niepewne i jaki zakres porównano.**

Pierwszy ekran:

> **Zmiany 25 → 26 października**  
> Porównano obie strony: **60/66 pracowni** · **6 wymaga uwagi**  
> Wydanie poranne: **08:26 — po terminie** · ostatnia korekta oznaczona osobno  
> **Najważniejsze zmiany** — najwyżej 5 zdarzeń, następnie „Pozostałe ważne zmiany”  
> **Ważne do sprawdzenia** — zawsze widoczne, jeśli istnieją nierozstrzygnięte istotne sygnały

Przykład redakcji na podstawie rzeczywistych zapisów; to nie jest nowa weryfikacja ofert:

| Pracownia / miejsce | Co się zmieniło | Status i znaczenie | Dowód |
| --- | --- | --- | --- |
| Alexander Studio · karta projektu | Pojawiła się zapowiedź promocji od **27.10**. | Potwierdzona zapowiedź; nie oznacza aktywnego rabatu 26.10. Monitor powinien sprawdzić start 27.10. | [Zapis i źródła](https://github.com/MateuszD0/Pracownie/blob/main/dashboard/alexanderstudiopl.md) |
| Planujdom · główna i karta projektu | W nowych zapisach nie ma komunikatu o rabacie **−15%**. | **Ważne do sprawdzenia.** Nie ustalono, czy promocja zakończyła się, czy zmieniło się miejsce jej komunikowania. | [Zapis i źródła](https://github.com/MateuszD0/Pracownie/blob/main/dashboard/planujdompl.md) |
| MG Projekt · główna i Amber 5 | Zebrano pierwszy poprawny zapis obu stron. | **Pierwszy odczyt.** Baza do kolejnego porównania; nie wpisywać „bez zmian”. Ten wiersz należy do sekcji kompletności. | [Zapis i źródła](https://github.com/MateuszD0/Pracownie/blob/main/dashboard/mgprojektcompl.md) |

Każdy wiersz ma jedno zdanie opisujące fakt, miejsce i etykietę pewności. Datę końca, kwotę, kod lub warunek dopisać tylko wtedy, gdy występuje w źródle. Unikać zdań typu „konkurencja zwiększa sprzedaż” — monitoring strony nie mierzy skutków sprzedażowych.

Po kliknięciu „Dowód”: jedno zdarzenie, pełny tekst **wczoraj / dziś**, daty i godziny obu zapisów, dopasowane wycinki obrazu, zaznaczona zmiana oraz dwa odnośniki: do utrwalonego dowodu i do aktualnej strony. Aktualna strona może już wyglądać inaczej niż zapis. Pełny zrzut jest opcją, nie obowiązkowym plikiem do pobrania.

Niżej tylko trzy potrzebne widoki:

- **Wszystkie pracownie:** wyszukiwarka, główna i stała karta w osobnych kolumnach, prosty status i ostatni poprawny odczyt. Braki nie są ukrywane przez filtr „zmiany”.
- **Aktywne i zapowiedziane oferty:** ostatnio potwierdzony stan, termin i data sprawdzenia. Dzięki temu dzień bez zmian nadal dostarcza kontekstu. Nie przedstawiać starego stanu jako sprawdzonego dzisiaj.
- **Historia:** wybór dnia i wcześniejszych zdarzeń danej pracowni. Odrębnie poranne wydania i późniejsze korekty.

`DASHBOARD.md` pozostaje krótkim, działającym punktem wejścia i awaryjnym skrótem. Docelowy główny interfejs to jedna statyczna aplikacja, np. GitHub Pages, z prawdziwymi filtrami i stałym adresem. Publikację należy potwierdzić próbą otwarcia publicznego adresu. Pobieranie ZIP nie może być zwykłym sposobem czytania raportu.

## 4. Jak zmienić interpretację danych

### Obserwacja a zdarzenie

Nie trzeba przepisywać skanera. Zachować migawki, zapamiętane projekty, porównania i archiwa; nad nimi dodać trwałe zdarzenia. Minimalne pola:

| Grupa | Pola |
| --- | --- |
| Tożsamość | identyfikator zdarzenia, pracownia, identyfikator kampanii jeśli ustalony, lista miejsc: główna / stała karta / warunki oferty |
| Treść | typ zmiany, zdanie podsumowania, cytaty przed/po, kod/benefit/warunki/terminy tylko ze źródeł |
| Ocena | ważność i jej konkretne uzasadnienie; osobno pewność, sposób i wynik sprawdzenia |
| Dowody | identyfikatory obserwacji, źródła, zrzuty/wycinki, daty obu zapisów, wersja reguł |
| Historia | pierwsze i ostatnie wystąpienie, edycja raportu, stan zapowiedziana/aktywna/zakończona/nieustalona, następny termin sprawdzenia |

Łączyć tylko obserwacje z dowodem wspólnej oferty lub tego samego elementu. Dwa niezależne hasła nie stają się jedną kampanią tylko dlatego, że zawierają „promocja”. Jedna kampania widoczna na dwóch stronach to jedno zdarzenie w odprawie i dwa miejsca w szczegółach. Zachować różnice lokalnych warunków, jeśli występują.

### Ważność jest niezależna od pewności

- **Ważne:** nowy lub zmieniony benefit, kod, warunek, termin, zapowiedź/koniec promocji, główny argument sprzedażowy, nowa oferta w głównym banerze, istotna zmiana wezwania do działania.
- **Do przeglądu:** konkretna zmiana komunikacji lub kreacji o mniejszym znaczeniu.
- **Techniczne:** samo przesunięcie, zmiana rozmiaru, zegar, animacja, numeracja, przypadkowy układ rotującego katalogu. Zachować w dzienniku; nie powiększać nimi liczby zmian biznesowych.

Nowa grafika nadal może być ważna: np. nowy baner eksponuje gratis albo zmienia dominujący projekt i hasło. Zmiana samego adresu pliku czy liczby pikseli nie wystarcza. Potrzebny jest porównywalny wycinek i opis tego, co w nim zmieniono. Rozpoznawanie tekstu z obrazu może uzupełniać HTML, ale wymaga dowodu i kontroli błędów.

### Brak baneru uruchamia zadanie monitora

Po zniknięciu istotnego komunikatu: powtórzyć odczyt tego miejsca, sprawdzić właściwe stany karuzeli/zakładek, odnośnik do oferty oraz znane warunki lub regulamin. Nie przeszukiwać całego Internetu. Zapisać odwiedzone adresy, cytaty, czas i wynik.

- Jest wyraźny koniec w warunkach lub nowy komunikat końcowy → „potwierdzone zakończenie”.
- Oferta nadal jest opisana w innym miejscu → „zmiana ekspozycji; oferta nadal widoczna”.
- Nie ma rozstrzygającego dowodu → „możliwe zakończenie — do sprawdzenia”, widoczne w odprawie z terminem kolejnej próby.

Kod dodatkowego sprawdzania już istnieje. Potrzebna jest jego pełna obsługa w procesie, kolejka nierozstrzygniętych zdarzeń oraz poprawna prezentacja starszych zapisów bez wyniku weryfikacji.

Nie wymagamy płatnego modelu językowego. Pierwsza wersja może działać przez jawne reguły i szablony zdań. Ewentualny model pomaga skrócić opis na podstawie dowodów; nie wymyśla warunków, zakończenia oferty ani wpływu na sprzedaż.

## 5. Proces, który odpowiada za rezultat

1. **Odbiór każdej pracowni.** Potwierdzić główną, właściwą stałą kartę, miejsca promocji/dodatków, wymagane interakcje i sensowne dowody. „Wszystko” zamienić na zapisany zakres per domena. Nowy projekt lub zmiana adaptera musi jawnie wskazywać utratę porównywalności.
2. **Poranny przebieg.** Zachować wczesny start około 04:17 czasu polskiego. Mierzyć realny czas pełnego skanu, weryfikacji i publikacji; dobierać bufor według wolniejszych przebiegów. Ponawiać brakujące lub niejednoznaczne strony, nie cały komplet bez potrzeby.
3. **Zamknięcie edycji.** Cel roboczy: publikacja do 07:50, zapas do 08:00. Najpóźniej o terminie ma być dostępny raport z jasno wskazanymi brakami. Brak jednej strony nie może blokować przeczytania pozostałych; jednocześnie nie może oznaczać kompletnego sukcesu.
4. **Kontrola wyniku.** Otworzyć opublikowany adres, sprawdzić dzień, liczbę pracowni, odnośniki do dowodów i daty obu podstaw porównania. Testować plik pobierany przez użytkownika, a nie tylko szablon przed eksportem.
5. **Dostarczenie.** Osobne stany: niewłączone, oczekuje, przyjęte przez SMTP, błąd/nieznany wynik. Przyjęcie przez SMTP nie dowodzi dotarcia do skrzynki. Pierwsze uruchomienie poczty odebrać rzeczywistą wiadomością; konfigurację przechowywać wyłącznie w sekretach. Nie oznaczać pominiętej wysyłki jako dostarczonej.
6. **Korekty.** Późniejsza naprawa ma godzinę i opis uzupełnienia. Nie zmienia po cichu podstaw porannego porównania, nie usuwa użytych dowodów i nie wysyła ponownie tego samego maila bez reguły korekt.
7. **Obsługa wyjątków.** Każda trwała luka ma przyczynę, plan naprawy i następny termin sprawdzenia. Osobno: blokada 403, częściowy odczyt, brak wczorajszego zapisu, pierwszy odczyt. Nie pokazywać wszystkich jako „brak danych”.
8. **Odbiór biznesowy.** Przez pierwszy tydzień przeglądać wszystkie ważne alerty i próbkę stron bez alertu. Oznaczać: trafne, powtórzenie, nieistotne, błędne. Użytkownik ocenia przydatność; obsługa techniczna poprawia reguły. Bez sprawdzania stron bez alertu nie zmierzymy przeoczonych promocji.

Dla obecnego dnia 6 pracowni bez kompletu porównań ma różne przyczyny: Archido i LK-Projekt — blokada/nieustalona karta; Dompp i Housecollection — częściowy odczyt oraz brak porównywalnej bazy; HB Studio — luka dla karty; MG Projekt — pierwszy poprawny zapis. To różne zadania naprawcze.

Darmowy GitHub Actions może opóźnić harmonogram. Obecny kontroler pomaga, lecz korzysta z tego samego planisty. Można poprawiać terminowość przez bufory i ponowienia, ale nie obiecywać bezwarunkowej gwarancji 08:00. Jeśli taka gwarancja jest wymagana, trzeba osobno rozstrzygnąć niezależny planer i koszty. Nie trzeba uruchamiać MacBooka dla proponowanego wariantu GitHub.

## 6. Lżejsze dowody i utrzymanie

Aktualne zasoby wydania: HTML **6,34 MB**, pakiet widoku **31,39 MB**, pełne archiwum **263,55 MB**. To rozmiary z API GitHuba, w MB dziesiętnych. Przy identycznej wielkości 180 dziennych pełnych archiwów zajęłoby około **47,4 GB** — to ekstrapolacja, nie pomiar historii ani limit planu GitHub.

- W odprawie ładować małe wycinki właściwego miejsca, dopiero po otwarciu dowodu. Pełne obrazy pobierać na żądanie.
- Identyczne obrazy przechowywać według skrótu zawartości i współdzielić pomiędzy odwołaniami; przed kasowaniem sprawdzać referencje ze wszystkich zachowanych raportów.
- Zachować tekst i warunki przez 180 dni. Kompresję obrazu oceniać pod kątem czytelności drobnego tekstu, a nie wyłącznie rozmiaru.
- Ustalić budżet magazynu i ruchu na podstawie tygodnia pomiarów. Nie dodawać pełnych binarnych archiwów do historii Git.

## 7. Kolejność realizacji i odbiór

| Etap | Zakres | Warunek odbioru |
| --- | --- | --- |
| **P0 — raport godny zaufania** | Wyszukiwarka/eksport, ważność oddzielona od pewności, widoczne ważne niewiadome, jasna kompletność, termin i faktyczna wysyłka. | Planujdom −15% jest widoczny jako nierozstrzygnięty; MG ma pierwszy zapis; zmiana 18 px nie wchodzi do odprawy bez znaczenia biznesowego; pominięty mail nie jest „wysłany”. |
| **P1 — raport do codziennej pracy** | Jedno zdarzenie z dowodami, krótka odprawa, działający publiczny widok, stan ofert, kolejka sprawdzeń, wersje i trwałe linki. | Jedna kampania ma jeden wiersz i wszystkie miejsca wystąpienia. Kliknięcie prowadzi do właściwej pary przed/po. Wczorajszy link działa także po dzisiejszej korekcie. |
| **P2 — niezawodność i koszt** | Odbiór adapterów, pomiar przeoczeń, tuning harmonogramu, kompresja/deduplikacja i kontrola retencji. | Udokumentowany zakres 66 pracowni; przyczyny wszystkich braków; działający odczyt archiwum; raport rozmiarów i terminowości. |

Regresje biznesowe obowiązkowe przed publikacją: nowa promocja, zapowiedź na jutro, nowy kod, dodatek gratis, zmiana warunków, zniknięcie baneru przy nadal aktywnej ofercie, potwierdzony koniec, rotacja karuzeli, ta sama kampania na dwóch stronach, pierwszy odczyt, częściowy odczyt i luka jednego dnia. Testować także brak wykrycia, a nie tylko prawidłowe alerty.

Testy odbiorcy: wyszukanie jednej pracowni; otwarcie konkretnego zdarzenia i dowodu; przełączenie dnia; brak wyników filtra; telefon; klawiatura i widoczny fokus. Prawidłowy wynik powinien dać się zrozumieć bez objaśniania technicznych pojęć. Osoba nieznająca implementacji w minutę wskazuje najważniejszą zmianę, jej status i zakres braków.

Proponowane cele jakości po uruchomieniu pomiaru: co najmniej 95% trafnych alertów w odprawie na ręcznie ocenionej próbie; wszystkie scenariusze krytyczne z zestawu regresji wykryte; 100% znanych braków jawnie oznaczone. Raportować liczebność próby i wyniki, nie deklarować tych wartości jako obecnego stanu. Mierzyć odsetek dni z publikacją do 08:00, czas do naprawy braków i udział ważnych nierozstrzygniętych zdarzeń. Próg terminowości ustalić po pomiarze pełnego tygodnia, w tym weekendu.

Nie dodawać teraz wykresów liczby surowych różnic, rankingu „aktywności” pracowni z tych liczników, kolejnych formatów raportu ani rozbudowanego generowania tekstów przez AI. Najpierw naprawić selekcję, dowody, kompletność i dostarczenie.

## Ślady w kodzie i granice wniosków

- [readout.py](../src/pracownie/readout.py): `readout()` ukrywa nieweryfikowane usunięcia promocji z głównego widoku; `digest_groups()` grupuje według domeny, strony i kategorii.
- [management.py](../src/pracownie/management.py): `group_changes()` oraz `build_management()`; licznik komunikacji obejmuje też obserwacje wyglądu.
- [web.py](../src/pracownie/web.py): `export_standalone()` usuwa skrypty i część kontrolek, pozostawiając pole wyszukiwania.
- [github.py](../src/pracownie/github.py): publikacja usuwa wcześniejsze zasoby tego samego dnia; ryzyko dotyczy bezpośrednich linków do tych plików.
- [email.yml](../.github/workflows/email.yml) i [workflow poczty](https://github.com/MateuszD0/Pracownie/actions/runs/40347566111): wysyłka pominięta przy niepełnej konfiguracji; nie odczytywano wartości sekretów.

To audyt jednej aktualnej publikacji i odpowiedzialnego za nią kodu. Nie zmierzono jeszcze odsetka wszystkich przeoczonych zmian ani całotygodniowej terminowości. Nie potwierdzono zakończenia promocji Planujdom. Ocena nie jest deklaracją pełnego pokrycia wszystkich interakcji ani wszystkich stron serwisów.
