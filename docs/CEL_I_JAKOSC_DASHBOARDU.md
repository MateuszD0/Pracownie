# Cel i zasady dziennego dashboardu

Dashboard służy do przeglądu zmian komunikacji konkurencji: strona główna i ten sam zapamiętany projekt każdej skonfigurowanej pracowni (obecnie 112 serwisów). Ceny są dodatkiem. W głównej tabeli mają być krótki opis obserwacji, miejsce i link do porównania; pełne wartości przed/po oraz dostępne dowody pozostają w szczegółach. Nie należy utożsamiać liczby różnic DOM z liczbą zmian biznesowych.

## Co pokazujemy

1. Na górze: daty odczytów, liczba pracowni z porównaniem obu stron oraz najważniejsze różnice komunikacji/promocji/dodatków/wyglądu.
2. Wszystkie skonfigurowane pracownie: osobno strona główna i stały projekt; krótki opis wyniku zamiast samego licznika różnic.
3. Po otwarciu pracowni: tekst przed/po, źródło, daty, podglądy zrzutów, przyczyny braku danych i zwinięte obserwacje pomocnicze.
4. Surowy dziennik i pełne obrazy pozostają dostępne. Eksport CSV niesie ocenę i wyjaśnienie; obserwacji pomocniczej nie wolno przedstawiać jako nowej promocji.

„Brak” w komórce oznacza brak w danym zapisie. Nieobecność hasła promocyjnego nie dowodzi zakończenia promocji. Porównywalny odczyt podstawowy nie oznacza pełnego wykonania wszystkich dodatkowych interakcji. Braki historii, blokady i błędy nigdy nie oznaczają braku zmian.

## Weryfikacja zapisów 21 → 22 października 2026

Źródło: zatwierdzone archiwa `monitor-report-2026-10-22` i `monitor-state-v1`, zapisane migawki i kotwice poprzedniego dnia. Bez odtwarzania historycznej witryny z dzisiejszej strony.

- 65 pracowni / 130 stron podstawowych.
- 59/65 porównywalnych stron głównych; 57/65 kart projektu; 57/65 pracowni ma oba porównania.
- 123 świeże odczyty, 7 brakujących; 7 odczytów ma częściową historię/zakres. Miary te mają różne znaczenie.
- Brak odczytu: archido.pl, domydlanas.pl i lk-projekt.pl (obie strony) oraz karta hbstudio.pl. Blokady po stronie witryn pozostają ograniczeniem.

## Naprawione przyczyny błędnych wniosków

| Przypadek | Dowód i poprawka |
| --- | --- |
| e-domy.pl — rzekomo nowy pakiet 69 zł | Stały projekt to E-268a. W jego zapisanym koszyku pakiet jest identyczny w obu dniach. 23 dodania i 23 usunięcia dotyczyły E-101/E-111. Interakcje innych projektów przeniesiono do obserwacji pomocniczych, a skaner nie wybiera już innych kart przez pole „Projekt”. |
| HB Studio — FAQ jako nowy dodatek | Różne akapity przypisano do tej samej pozycji DOM. Sam indeks elementu nie wystarcza do uznania edycji tego samego komunikatu. „Dodatkowo” nie jest nazwą dodatku. |
| ExtrAdom — adres CDN jako nowa funkcjonalność | Adres pliku nie dowodzi zmiany wyglądu ani funkcji. Takie zapisy nie wchodzą do wskaźników biznesowych. |
| Dobre Domy / katalogi | Losowe linki projektów i zakładki katalogowe były liczone jako zmiany stałej karty. Oznaczono zapisane sekcje katalogowe i oddzielono je od oferty. |
| Liczniki i przesunięcia | Odliczanie, liczba oglądających, kalendarz oraz drobne przesunięcia nie są nową komunikacją sprzedażową. Oryginały pozostają w archiwum. |
| Dowody obrazowe | Zamiast sześciu pojedynczych obrazów publikowane są pary przed/po, maksymalnie 40 stron. Podglądy JPEG mają do 1000 px szerokości; pełne oryginały pozostają w ZIP. |

## Zakres sprawdzenia

Sprawdzono reguły porównania i zachowania tożsamości projektu, klasyfikację główne/pomocnicze, zgodność eksportu, obie strony każdej pracowni w tabeli, parowanie obrazów i przykładowe przejścia w HTML na komputerze i telefonie. Dane demonstracyjne w testach są odrębne od powyższych zapisów produkcyjnych. Nie weryfikowano wizualnie każdego piksela wszystkich 130 stron ani kompletności wszystkich zakładek zdalnych witryn.

## Co nadal ogranicza wnioski

- Obserwacja pojedynczej sesji może obejmować rotującą treść lub wariant strony. Oznaczenia pomocnicze nie są dowodem niezmienności witryny.
- Szczegółowe grafiki wymagają zrzutów; sam adres obrazu nie wystarcza do opisu nowej kreacji.
- Darmowy harmonogram GitHub Actions może wystartować z opóźnieniem. Kontroler i ponowienia pomagają, ale nie gwarantują publikacji o 08:00 przy opóźnieniu całej usługi.
- Poczta wymaga skonfigurowanych sekretów. Powodzenie zadania z pominiętą wysyłką nie jest potwierdzeniem dostarczenia maila.

## Układ do codziennego czytania

- Podsumowanie grupuje zmiany według pracowni, strony i tematu. Wiele tematów lub obie strony tej samej pracowni pozostają widoczne. Wiersz pokazuje jedno krótkie zdanie o reprezentatywnej obserwacji i liczbę pozostałych różnic pod linkiem. Reprezentant zachowuje własne źródło; nie łączymy niezależnie dodanego i usuniętego banera w domniemaną edycję. Dłuższe zestawienia na GitHubie mają kolejne strony; żaden temat nie znika z powodu limitu sześciu pracowni.
- Zmienione słowa są pogrubione. Skrót długiego tekstu obejmuje pierwszą różnicę, zamiast obcinać ją za niezmienionym wstępem. „Nie odnotowano w tym odczycie” opisuje zapis, nie zakończenie promocji.
- W szczegółach pracowni dostępne są datowane, rozwijane obrazy przed/po. Podgląd może obejmować tylko fragment różnicy obrazu; nie musi pokazywać wszystkich komunikatów odczytanych z karty. Pełne dane pozostają w CSV/HTML.
- Lista wszystkich skonfigurowanych pracowni i dodatkowe obserwacje obrazu są zwinięte. W HTML filtry są rozwijane, aktywny zakres pozostaje opisany, a tabela zmian na telefonie układa się pionowo.
- Identyczny nagłówek odczytany jako tekst i cecha wizualna jest jednym ustaleniem; źródłowe identyfikatory pozostają w dzienniku.

### Korekta interpretacji HexaGreen

W zapisach 21–22.10 licznik realizacji ma różne wartości nawet w obrębie tego samego odczytu tekstu i właściwości wizualnych (139/138 oraz 133/130). Dodatkowe sprawdzenie publicznego skryptu `https://hexagreen.pl/wp-content/themes/hexagreen/js/info-section-counter.js?ver=1.0.9` potwierdziło animację liczników po wejściu sekcji w ekran. Dotyczy to również licznika autorskich projektów. Wartości 18 → 17 i 139 → 133 nie są wiarygodnym dowodem zmiany wielkości oferty. Zachowujemy oryginalne odczyty jako pomocnicze; bieżącej wartości witryny nie przepisujemy wstecz do historii. Do czasu rejestrowania ustabilizowanej wartości końcowej te liczniki nie są alertami biznesowymi.

Przyciski zgód, w tym „Akceptuj wszystko”, są obserwacjami interfejsu, nie komunikacją sprzedażową. Nagłówki o projektach zawierające konkretny benefit, np. pakiet gratis, pozostają w zestawieniu biznesowym.

### Czytelniejszy skrót dnia

Trzy kolumny: pracownia i strona, co zauważono, link do sprawdzenia. Pełne cytaty pozostają na stronach pracowni, z pogrubioną różnicą. Nazwa „Zmiany oferty i komunikacji” nie sugeruje pomiaru wpływu na sprzedaż.

Krótkie etykiety bez konkretnej informacji o ofercie, przesunięcia sekcji i różny zakres długiego akapitu trafiają do rozwijanego zestawienia „Pozostałe różnice do przejrzenia”. Krótkie komunikaty o katalogu, gratisie, promocji i pakiecie pozostają w skrócie. To podział prezentacji, nie usuwanie obserwacji ani potwierdzenie przyczyny zmiany. Liczniki wszystkich różnic obejmują obie części; filtry HTML działają na obie.

W obrębie tematu pierwszeństwo ma konkretna para wartości, potem obecność w nowym zapisie, potem brak w nowym zapisie. Przy braku komunikatu widoczne jest zastrzeżenie, że nie dowodzi to wycofania oferty. Wyświetlamy daty skanów; przebudowa układu nie tworzy nowego skanu.

## Odprawa dnia — 26.10.2026

Główny widok korzysta ze wspólnych zdarzeń biznesowych: maksymalnie pięć najważniejszych na start, dalsze zdarzenia na żądanie i osobna widoczna sekcja „Ważne do sprawdzenia”. Ważność jest niezależna od pewności. Brak promocyjnego komunikatu bez rozstrzygającego sprawdzenia nie znika w technicznych obserwacjach. Same przesunięcia, rozmiary i rozpoznane zlepki cen nie są alertami odprawy.

Jednakowe warunki na głównej i karcie łączymy w jedno zdarzenie z zachowaniem miejsc i źródeł. Nagłówek może łączyć obserwację tekstową i wizualną tylko przy zgodnej treści, stronie i datach. Niezależne kampanie z innymi kodami, kwotami lub terminami pozostają oddzielne.

Raport HTML ma działające wyszukiwanie, filtry i powrót z dowodu. Eksport przenośny zawiera mały indeks i osadzone obrazy; w trybie bez JavaScript ukrywa nieaktywne kontrolki i pokazuje wszystkie zdarzenia. Główna miara obejmuje pracownie z porównaniem obu stron, a braki mają wskazane przyczyny.

Wykaz komunikatów ofert zachowuje datę ostatniego poprawnego odczytu. Nie należy utożsamiać obecności komunikatu z potwierdzoną dostępnością w koszyku. Historia zdarzeń jest gromadzona od wdrożenia odprawy; starsza historia pozostaje w dziennych wydaniach. Kolejka nierozstrzygniętych ofert jest ponawiana także bez nowej różnicy DOM. Dodatkowe sprawdzenie nie tworzy fikcyjnej zmiany dzień do dnia.

Wcześniejsze zasoby tego samego dnia nie są już kasowane przy korekcie. Retencja działa na całe dzienne wydania. Współdzielenie obrazów w stanie i widoku WWW pozostaje aktywne; pełne ZIP-y kolejnych wersji mogą powtarzać obrazy. Budżet 180 dni i dalszą deduplikację archiwów należy ocenić po tygodniu pomiarów.

Termin i status poczty są niezależne od jakości odczytu. Brak konfiguracji nie jest wysłaniem; odpowiedź SMTP nie jest potwierdzeniem obecności w skrzynce odbiorcy. Po wysyłce status dashboardu jest aktualizowany z trwałego potwierdzenia. Włączenie publicznego adresu WWW wymaga uprawnienia do GitHub Pages; wysyłka wymaga sekretów opisanych w EMAIL.md.

Do odbioru operacyjnego nadal potrzebne są: tydzień pomiaru terminowości i przeoczeń, ręczny odbiór zakresu interakcji per pracownia i naprawy trwałych blokad. Testy nie zastępują tych pomiarów.

## Współpraca — 27.10.2026

Pełną listę współpracujących wskazał użytkownik w arkuszu „Pracownie URL Ewa”. W rejestrze jest 98 partnerów: 80 z domeną i 18 bez stron WWW. Dla 33 domen istniały już adaptery, dodano pozostałe 47; 32 dotychczasowe serwisy oznaczono jako niewspółpracujące. Skan obejmuje 112 serwisów, po dwie podstawowe strony. Extradom pozostaje wykluczony.

Podział jest utrwalany w metadanych wydania, aby późniejsza zmiana współpracy nie zmieniła historycznego raportu. W Markdown obie grupy mają osobne tabele i nagłówki list. W pełnym i przenośnym HTML wspólny filtr wpływa na zmiany, dowody, kompletność i eksport. Na start widocznych jest do pięciu zdarzeń w każdej grupie. Nazwa i kod z rejestru są dostępne w wyszukiwaniu.

Firmy bez WWW są w osobnym wykazie; nie są błędami odczytu i nie zwiększają oczekiwanej liczby stron. Nowe domeny mogą zostać dopisane do bieżącego raportu z jawnym statusem oczekiwania na pierwszy skan, przez `--include-new-sites`. Pierwszy poprawny odczyt ustanawia bazę; pełne porównanie dzień do dnia wymaga kolejnego poprawnego zapisu. Nie wybieramy ponownie kart już zamrożonych dla dotychczasowych pracowni.

Odbiór publikacji grup: wydanie `2026-10-27T130226.949893-0000-format-ea8249e6`, 112 serwisów, grupy 80/32 i 18 partnerów bez WWW. Zachowane daty, dowody i wybory projektów istniejących 65 pracowni; wcześniejsze zasoby wydania dostępne. Sprawdzono opublikowany przenośny HTML: filtr grup, wyszukiwanie po kodzie pracowni i firmy bez WWW, osadzone obrazy dowodu oraz brak poziomego przepełnienia na telefonie. [Publikacja](https://github.com/MateuszD0/Pracownie/actions/runs/40508316564) i [pełny CI](https://github.com/MateuszD0/Pracownie/actions/runs/40508741599) zakończyły się powodzeniem.

[Pierwszy skan nowych 47 domen](https://github.com/MateuszD0/Pracownie/actions/runs/40509744951) uruchomiono osobno po publikacji podziału, z zachowaniem wyników pozostałych 65. Do jego zakończenia nowe serwisy mają jawny status oczekiwania; samo dodanie adresu z listy nie jest potwierdzeniem kompletnego odczytu strony ani karty.
