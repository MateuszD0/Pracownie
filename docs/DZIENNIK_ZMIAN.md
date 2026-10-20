# Dzienna tabela zmian

Wynikiem jest lista zmian, z kolumnami: dzień, pracownia, strona główna lub stała karta projektu, rodzaj zmiany, co się zmieniło, było, jest, źródło i dowód przed/po. Dashboard HTML, opis wydania GitHub i TXT zaczynają się od podsumowania zarządczego i konkretnych zmian dzień do dnia. `dziennik-zmian.csv` zachowuje pełną listę, w tym pomocnicze różnice obrazu i porównania po luce. Przycisk eksportu w interaktywnym HTML pobiera tylko widoczne wiersze priorytetowej tabeli. Dotychczasowy `oferty.csv` pozostaje zestawieniem cen.

## Wybór rozwiązania

| Możliwość | Zaleta | Ograniczenie |
| --- | --- | --- |
| Osobne adaptery każdej domeny | Dokładne wskazanie ceny, pakietu i sekcji | Wymagają utrzymania po zmianach stron |
| Analiza obrazów przez model AI | Opis znaczenia zmian grafiki | Koszt API i ryzyko nadinterpretacji |
| Odczyt danych i porównanie obrazu | Darmowe reguły, konkretne wartości i dowody | Nie odgaduje znaczenia każdej zmiany obrazu |

Wdrożono trzeci wariant. Nie wymaga klucza ani płatnego API. Zmiana obrazu jest odróżniona od ustalonej zmiany oferty. Nie wnioskujemy o obniżce ceny z samego zrzutu.

## Co jest porównywane

- Ceny, promocje, dodatki, pakiety, warunki, funkcje i widoczna treść: odpowiadające sobie pola z dwóch poprawnych odczytów. Potwierdzone różnice mają stare i nowe wartości.
- Wygląd: obraz strony oraz właściwości widocznych elementów: źródło grafiki, tło, kolor tekstu, krój pisma, rozmiar i położenie. Dla zmienionego obrazu zapisujemy fragment przed/po oraz oznaczone porównanie. Metadane wyglądu obejmują do 100 widocznych elementów.
- OCR, gdy jest dostępne, dodaje pomocniczy tekst wyłącznie do zmiany obrazu. Nie tworzy potwierdzonej ceny ani promocji. Błędne obrazy/style i widoczne zgody cookies wykluczają automatyczne ustalenie zmiany wyglądu.
- Link do źródła wykorzystuje kotwicę sekcji lub widoczny tekst, jeśli można go dokładnie powiązać z odczytem. W pozostałych przypadkach prowadzi do monitorowanej strony. Dowód pokazuje zapisany fragment.
- Luka w historii jest jawnie oznaczona. Starszy odczyt nie udaje wczorajszego.

Niejednoznaczne odczyty i awarie nie trafiają do głównej tabeli zmian. Pozostają w diagnostyce i danych źródłowych. Brak ustalonej zmiany nie oznacza braku zmian w nieodczytanym zakresie.

## Stabilne porównania i odtwarzanie

Wersja przeglądarki nie jest wersją reguł sprzedażowych. Nowe skany zapisują jawny kontrakt `sales-v2` oraz podpis adaptera. Zmiana samych zrzutów lub prezentacji raportu nie wyłącza porównywania pól oferty.

Sprawdzona migracja `e6517d8 → d55a24c` dodała wyłącznie wcześniej pomijany zwykły tekst. Istniejące pola sprzedażowe obu wersji są zgodne; nowe zwykłe teksty tworzą własny punkt odniesienia. Nie rozszerzamy tej zgodności na nieznane starsze wersje.

`odczyt.json` i trwały stan zachowują publiczne dane wejściowe, rzeczywistą datę, wersję kolektora oraz właściwości wyglądu. Gdy oba odczyty mają tę samą wersję danych źródłowych i konfigurację adaptera, można przeliczyć je wspólnymi regułami bez ponownego odwiedzania historycznej strony. Przekroczenie limitu danych źródłowych jest raportowane; zachowane pola i obraz pozostają dostępne.

Przy zmianie znaczenia pól należy zmienić kontrakt i dodać test migracji. Zmiana zakresu samego kolektora wymaga zmiany `raw_schema`; nie wolno uznawać starych danych za zgodne bez sprawdzenia. Plik `visuals.js` jest oddzielony od kolektora pól, żeby poprawki metadanych grafiki nie resetowały porównań cen.

## Uruchomienie po wdrożeniu

Ręczny pełny skan z `rescan` w Actions zbiera nowy punkt odniesienia tego samego dnia. Zachowuje porównanie do stanu sprzed dnia i rzeczywiste daty.

Commit wdrożeniowy na `main` z oznaczeniem `[scan]` może uruchomić taki skan po sukcesie workflow `Testy`. Dotyczy wyłącznie zaufanego zdarzenia `push` tego repozytorium; pull requesty nie uruchamiają publikacji ani skanu. Zwykłe wdrożenia bez oznaczenia tylko przebudowują raport. Codzienny harmonogram pozostaje bez zmian.

Oznaczenie `[scan] [repair:domena.pl,druga.pl]` uruchamia naprawę wskazanych domen w istniejącym raporcie tego samego dnia. Pozostałe dane i ich rzeczywiste daty zostają zachowane. Lista jest sprawdzana przez konfigurację monitora. Skan i przebudowa uruchomione po testach używają dokładnie sprawdzonego commita.

Skan i przebudowa mają wspólną blokadę zapisu stanu. Opcjonalna publikacja Pages ma oddzielną blokadę i nie wstrzymuje kolejnych skanów.

## Dashboard zarządczy

- Trzy główne wskaźniki liczą **pracownie** ze zmianą komunikacji: łącznie, na stronie głównej i na karcie projektu. Pracownia jest liczona raz w danym wskaźniku; zakres to pary z wczoraj i dnia raportu. Ceny są informacją dodatkową. [Zasady komunikacji](KOMUNIKACJA.md).
- Zakres komunikacji ma niezależne liczniki dla obu stron: pełne porównanie zapisanego zakresu, zgodne fragmenty ze starszego skanu, dzisiejszy odczyt i gotowość nowej bazy. Porównywalne ceny nie ograniczają komunikacji. Stary poprawny odczyt nie zwiększa licznika dzisiejszych odczytów.
- W tabeli głównej są komunikaty, nagłówki, promocje, dodatki, CTA i warunki; ceny są w szczegółach. Sam zmieniony zrzut, bez rozpoznanego faktu dotyczącego elementu strony, pozostaje w rozwijanym archiwum. Nie ustala przebudowy strony ani nowej promocji.
- Wszystkie pracownie pozostają w widocznej tabeli komunikacji, osobno dla obu stron. Tabela dostępności wyjaśnia braki. Szczegóły, ceny, niepewne odczyty i duże obrazy są domyślnie zwinięte.
- Filtry domeny, rodzaju i strony ograniczają główną tabelę, KPI oraz eksport widocznych wierszy. Pokrycie danych opisuje wybrane pracownie/strony, niezależnie od kategorii zmiany. Lista obserwowanych jest preferencją lokalną w przeglądarce; nie zmienia zakresu codziennego skanu.
- Historia dni prowadzi do rzeczywistych raportów w `RAPORTY.md`. Nie generujemy wykresów 7/30 dni ani zer za brakujące odczyty bez odpowiedniej historii.
- Odpowiedź 429 wstrzymuje następne próby danej domeny zgodnie z `Retry-After` (liczba sekund lub data HTTP). Długie przerwy nie są skracane, aby zmieścić skan. Odpowiedzi 403 pozostają jawnym brakiem dostępu.
