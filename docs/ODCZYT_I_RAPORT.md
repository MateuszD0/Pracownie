# Czytanie raportu ofert

Otwórz dzień w [spisie raportów](../RAPORTY.md). Wydanie GitHub zawiera podsumowanie i tabelę cen. Do filtrowania i oglądania dowodów rozpakuj ZIP i otwórz `raporty/YYYY-MM-DD/index.html`. CSV jest przeznaczony do arkusza; TXT to krótki przegląd dnia.

## Co oznaczają liczby

- **Odczyt stron głównych / kart**: skaner uzyskał i zweryfikował treść konkretnej strony. Ograniczenia zasobów i interakcji pozostają widoczne w szczegółach.
- **Ceny ustalone**: udało się przypisać kwotę lub zakres do wybranego projektu. To osobna miara od samego otwarcia karty.
- **Porównywalne pary cen**: istnieją dwa poprawne odczyty tej samej pozycji, waluty, jednostki i sposobu oznaczenia podatku. Pierwszy odczyt nowego pola nie daje jeszcze różnicy dzień do dnia.
- **Zmiany ofert**: potwierdzone różnice danych sprzedażowych. Zmieniony obraz oraz niepewne obserwacje mają osobne oznaczenia.

„—” oznacza brak danych. Cena 0 zł, brak zmian i brak odczytu to różne sytuacje.

## Która cena trafia do tabeli

Pierwszeństwo ma sprawdzone pole zakupu przypisane do domeny, następnie metadane ceny produktu i dopasowane dane JSON-LD. Widoczne ceny są używane przy jednoznacznym przypisaniu do karty. Kilka wariantów może dać zakres; system nie wybiera najtańszej liczby ze wszystkich elementów strony.

Cena regularna, najniższa z 30 dni, dodatki, projekty polecane i koszt budowy nie zastępują ceny wybranego projektu. Kwoty netto i ceny za lokal są opisane. Podatku nie przelicza się na podstawie założonej stawki VAT. Bez jednoznacznej podstawy cena pozostaje nieustalona.

CSV używa separatora `;`, przecinka dziesiętnego i kodowania UTF-8 z BOM. Zawiera także granice zakresu ceny, jednostkę, oznaczenie podatku oraz daty obserwacji.

## Porównanie i obrazy

„Poprzednio” oznacza ostatni poprawny odczyt sprzed dnia raportu. Daty są dostępne w szczegółach oraz CSV. Przy awarii poprzedni poprawny stan pozostaje zachowany; nie staje się nowym odczytem dzisiejszym.

Pierwszy poprawny skan zapisuje bazę. Zrzut „przed” pochodzi z rzeczywiście zachowanego poprzedniego skanu. Gdy zmieni się cena, tekst lub obraz, raport dołącza dowody przed/po. Sama różnica obrazu wymaga oceny: może być spowodowana reklamą, karuzelą lub układem strony.

Zmiana sposobu odczytu nie stanowi dowodu zmiany oferty. Nowo odczytywane pola dostają punkt odniesienia; nie odtwarza się brakujących cen historycznych z dzisiejszej witryny. Stabilne ceny JSON-LD o tej samej tożsamości produktu mogą być porównane mimo zmiany obsługi przeglądarki.

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
