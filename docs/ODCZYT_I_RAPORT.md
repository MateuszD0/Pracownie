# Czytanie raportu ofert

Otwórz dzień w [spisie raportów](../RAPORTY.md). Wydanie GitHub zawiera podsumowanie obu stron i tabelę cen. Do filtrowania i oglądania dowodów wybierz **Raport HTML ze zrzutami**, rozpakuj `*-widok.zip` i otwórz `YYYY-MM-DD/index.html`. To gotowy raport, a nie szablon z kodu. Treść i rozwijane sekcje działają także przy wyłączonych skryptach. CSV jest przeznaczony do arkusza; TXT zawiera różnice obu stron według domen.

## Co oznaczają liczby

- **Odczyt stron głównych / kart**: skaner uzyskał i zweryfikował treść konkretnej strony. Ograniczenia zasobów i interakcji pozostają widoczne w szczegółach.
- **Ceny ustalone**: udało się przypisać kwotę lub zakres do wybranego projektu. To osobna miara od samego otwarcia karty.
- **Porównywalne pary cen**: istnieją dwa poprawne odczyty tej samej pozycji, waluty, jednostki i sposobu oznaczenia podatku. Pierwszy odczyt nowego pola nie daje jeszcze różnicy dzień do dnia.
- **Zmiany ofert**: potwierdzone różnice danych sprzedażowych. Zmieniony obraz oraz niepewne obserwacje mają osobne oznaczenia.

„—” oznacza brak danych. Cena 0 zł, brak zmian i brak odczytu to różne sytuacje.

Gwiazdka przy cenie oznacza odczyt dokładnego pola projektu przy częściowym załadowaniu strony. Kwota wymaga potwierdzenia; nie służy do potwierdzania wzrostu ani spadku ceny.

## Która cena trafia do tabeli

Pierwszeństwo ma sprawdzone pole zakupu przypisane do domeny, następnie metadane ceny produktu i dopasowane dane JSON-LD. Widoczne ceny są używane przy jednoznacznym przypisaniu do karty. Kilka wariantów może dać zakres; system nie wybiera najtańszej liczby ze wszystkich elementów strony.

Cena regularna, najniższa z 30 dni, dodatki, projekty polecane i koszt budowy nie zastępują ceny wybranego projektu. Kwoty netto i ceny za lokal są opisane. Podatku nie przelicza się na podstawie założonej stawki VAT. Bez jednoznacznej podstawy cena pozostaje nieustalona.

CSV używa separatora `;`, przecinka dziesiętnego i kodowania UTF-8 z BOM. Zawiera także granice zakresu ceny, jednostkę, oznaczenie podatku oraz daty obserwacji.

## Porównanie i obrazy

„Poprzednio” oznacza ostatni poprawny odczyt sprzed dnia raportu. Daty są dostępne w szczegółach oraz CSV. Przy awarii poprzedni poprawny stan pozostaje zachowany; nie staje się nowym odczytem dzisiejszym.

Główna część HTML pokazuje osobno **stronę główną** i **kartę projektu** każdej pracowni, z rzeczywistymi datami i zmienionymi fragmentami. Porównanie z wczoraj ma odstęp jednego dnia w strefie Europe/Warsaw. Starsza baza jest wyraźnie oznaczona jako luka w historii. Brak aktualnego odczytu, pierwszy odczyt i brak zmian mają różne statusy. Opcje ujawnione po interakcji zachowują nazwę scenariusza oraz własne daty.

Jeśli nie uda się ponowienie odczytu w tym samym dniu, raport zachowuje wcześniejszy poprawny odczyt z tego dnia wraz z jego rzeczywistą godziną. Pokazuje również błąd ponowienia. Funkcja nie przenosi wczorajszej ceny do kolumny dzisiejszej.

Pierwszy poprawny skan zapisuje bazę. Zrzut „przed” pochodzi z rzeczywiście zachowanego poprzedniego skanu. Gdy zmieni się cena, tekst lub obraz, raport dołącza dowody przed/po. Sama różnica obrazu wymaga oceny: może być spowodowana reklamą, karuzelą lub układem strony.

Zmiana sposobu odczytu nie stanowi dowodu zmiany oferty. Nowo odczytywane pola dostają punkt odniesienia; nie odtwarza się brakujących cen historycznych z dzisiejszej witryny. Stabilne ceny JSON-LD o tej samej tożsamości produktu mogą być porównane mimo zmiany obsługi przeglądarki.

Różnice pól, które istnieją zarówno przed, jak i po zmianie reguł odczytu, pozostają widoczne w sekcji **Różnice do potwierdzenia** wraz z tekstem i przyczyną niepewności. Nowe lub znikające klucze parsera są w diagnostyce. Nie są automatycznie uznawane za zmiany na witrynie. Widoczna data promocji jest monitorowana; automatycznie zmieniana data `priceValidUntil` z metadanych wymaga potwierdzenia w widocznej ofercie.

Monitorowane są ceny, promocje, dodatki, pakiety, warunki zakupu, funkcjonalności, parametry oraz pozostałe rozpoznane fragmenty widocznej treści. Nieoznaczone słowami sprzedażowymi teksty zapisuje się jako „Treść strony”. Pierwszy odczyt nowej kategorii tworzy bazę porównania.

## Ograniczenia odczytu

Skan najpierw sprawdza strony główne i karty wszystkich domen, a potem dodatkowe interakcje. Ukryte pola wyboru są obsługiwane przez ich widoczne etykiety; powtórzone przyciski koszyka i nawigacja katalogu nie mnożą prób zakupowych.

Automatyczne interakcje obejmują rozpoznane zakładki, rozwinięcia i pojedyncze opcje. Wszystkie zależne kombinacje konfiguratora wymagają adaptera danej witryny. Ograniczenia czasu, liczby prób i nieobsłużone kontrolki są raportowane; poprawne otwarcie karty nie oznacza pełnego sprawdzenia konfiguratora.

| Wynik | Znaczenie |
| --- | --- |
| 403 | Witryna odmawia dostępu ze skanera. |
| 429 | Witryna ogranicza dostęp lub częstotliwość odczytów. |
| Brak ceny | Nie uzyskano jednoznacznej ceny projektu; nie wstawiono zera ani ceny dodatku. |
| Nieukończone interakcje | Podstawowy odczyt i dodatkowe próby są oceniane osobno. |
| Pierwszy odczyt | Brakuje porównywalnej wcześniejszej obserwacji. |

Szczegółowe komunikaty i pełny zakres prób znajdują się w `diagnostyka.txt` i `pokrycie.json`. Surowe obserwacje są w `zmiany.json`; dane widoku w `oferty.json`. Manifest zawiera sumy kontrolne wszystkich wygenerowanych plików.
