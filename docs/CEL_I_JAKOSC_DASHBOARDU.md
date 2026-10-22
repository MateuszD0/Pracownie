# Cel i zasady dziennego dashboardu

Dashboard służy do przeglądu zmian komunikacji konkurencji: strona główna i ten sam zapamiętany projekt każdej z 65 pracowni. Ceny są dodatkiem. W głównej tabeli mają być treść zmiany, wartości przed/po, miejsce i zapisany dowód. Nie należy utożsamiać liczby różnic DOM z liczbą zmian biznesowych.

## Co pokazujemy

1. Na górze: daty odczytów, liczba pracowni z porównaniem obu stron oraz najważniejsze różnice komunikacji/promocji/dodatków/wyglądu.
2. Wszystkie 65 pracowni: osobno strona główna i stały projekt; krótki opis wyniku zamiast samego licznika różnic.
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

- Podsumowanie grupuje zmiany według pracowni, strony i tematu. Wiele tematów lub obie strony tej samej pracowni pozostają widoczne. Wiersz pokazuje do trzech par tekstów i liczbę dalszych zmian pod linkiem. Dłuższe zestawienia na GitHubie mają kolejne strony; żaden temat nie znika z powodu limitu sześciu pracowni.
- Zmienione słowa są pogrubione. Skrót długiego tekstu obejmuje pierwszą różnicę, zamiast obcinać ją za niezmienionym wstępem. „Nie odnotowano w tym odczycie” opisuje zapis, nie zakończenie promocji.
- W szczegółach pracowni dostępne są datowane, rozwijane obrazy przed/po. Podgląd może obejmować tylko fragment różnicy obrazu; nie musi pokazywać wszystkich komunikatów odczytanych z karty. Pełne dane pozostają w CSV/HTML.
- Lista wszystkich 65 pracowni i dodatkowe obserwacje obrazu są zwinięte. W HTML filtry są rozwijane, aktywny zakres pozostaje opisany, a tabela zmian na telefonie układa się pionowo.
- Identyczny nagłówek odczytany jako tekst i cecha wizualna jest jednym ustaleniem; źródłowe identyfikatory pozostają w dzienniku.

### Korekta interpretacji HexaGreen

W zapisach 21–22.10 licznik realizacji ma różne wartości nawet w obrębie tego samego odczytu tekstu i właściwości wizualnych (139/138 oraz 133/130). Dodatkowe sprawdzenie publicznego skryptu `https://hexagreen.pl/wp-content/themes/hexagreen/js/info-section-counter.js?ver=1.0.9` potwierdziło animację liczników po wejściu sekcji w ekran. Dotyczy to również licznika autorskich projektów. Wartości 18 → 17 i 139 → 133 nie są wiarygodnym dowodem zmiany wielkości oferty. Zachowujemy oryginalne odczyty jako pomocnicze; bieżącej wartości witryny nie przepisujemy wstecz do historii. Do czasu rejestrowania ustabilizowanej wartości końcowej te liczniki nie są alertami biznesowymi.

Przyciski zgód, w tym „Akceptuj wszystko”, są obserwacjami interfejsu, nie komunikacją sprzedażową. Nagłówki o projektach zawierające konkretny benefit, np. pakiet gratis, pozostają w zestawieniu biznesowym.
