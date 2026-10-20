# Porównanie komunikacji pracowni

Główne pytanie raportu: co zmieniło się od wczoraj w komunikatach na stronie głównej i na tej samej karcie projektu? Cena projektu jest informacją dodatkową, a nie warunkiem porównania tych treści.

## Widok dzienny

- Wskaźniki: pracownie ze zmianą komunikacji, ze zmianą na stronie głównej i ze zmianą na karcie. Pracownia jest liczona raz w danym wskaźniku; te zbiory mogą się pokrywać.
- Tabela zmian: konkretna treść przed i po, rodzaj zmiany, obie daty, źródło oraz istniejące zrzuty. Zmiany kwot są w szczegółach.
- Tabela wszystkich 65 pracowni: osobny wynik komunikacji dla obu stron, linki i gotowość nowej bazy. Błąd lub niepełna historia nie są wynikiem „bez zmian”.
- Zakres: pełne porównania zapisanego zakresu, zgodne fragmenty ze starszego skanu, dzisiejsze odczyty oraz nowe bazy do następnego dnia. Te miary mają osobne mianowniki i nie są sumowane jako jednakowo wiarygodne porównania.

Wyszukiwanie, obserwowane pracownie, filtr strony i rodzaju zmiany dotyczą tabel oraz eksportu widocznych zmian. Wskaźniki zmian uwzględniają te filtry. Kompletność dotyczy wybranych stron, niezależnie od wybranej kategorii alertów. Pełny `dziennik-zmian.csv` zachowuje również dodatkowe informacje, w tym ceny, ogólne różnice obrazu i porównania po luce.

## Zapis źródłowy

`communication.js` zapisuje kontrakt `communication-v1` w `Snapshot.document.communication`: czas rzeczywistego odczytu, identyfikator reguł komunikacji oraz komunikaty ze wskazaniem roli, elementu i miejsca źródłowego. Są to nagłówki, treści oferty, CTA oraz komunikaty i grafiki w rozpoznanych rotatorach. Treści publicznych zakładek i rozwijanych sekcji są zbierane także w zapisanych scenariuszach interakcji. Nawigacja, stopka, zgody i zamknięte sekcje w scenariuszu podstawowym są pomijane. Rotator jest czytany jako zestaw slajdów, również nieaktywnych; obrócenie tego samego zestawu nie jest nową kampanią.

Reguły komunikacji mają osobną tożsamość od adapterów cen. Wymagana jest ta sama strona i scenariusz, zgodne reguły komunikacji, przeglądarka, rzeczywiste daty oraz dwa poprawne, nieucięte zapisy. Przeniesienie niezmienionego tekstu nie powoduje alertu. Zmiany samych kwot w zachowanym komunikacie trafiają do modułu cen. Nie używamy generatywnego API do zgadywania zmian.

„Pełne” oznacza cały monitorowany, zapisany zakres, nie gwarancję uchwycenia każdego elementu witryny. Nieznane komponenty rotatorów, personalizacja, grafika bez tekstu poza zapisanym zakresem i niezrealizowane kombinacje konfiguratorów pozostają ograniczeniem. Zrzuty są dodatkowym materiałem. Sama zmiana pikseli nie ustala nowej promocji ani redesignu.

## Uczciwa historia

Skan 19 października 2026 nie zawierał pełnej surowej historii komunikacji. Oryginalne, datowane fragmenty `tekst:*` mogą potwierdzić zgodność tych samych tekstów; nie wystarczają do ustalenia, że cała strona nie zmieniła komunikacji, ani do uznania nowo odczytanego banera za nową kampanię. Dashboard oznacza takie porównania jako częściowe. Identyczny, zweryfikowany skrót SHA-256 obrazów z obu dni pozwala dodatkowo pokazać „Zrzut bez różnic”. Dotyczy to wyłącznie uchwyconego, ewentualnie maskowanego widoku, w granicach wysokości zrzutu; nie ustala stanu wszystkich slajdów, zakładek ani komunikacji poza kadrem. Starszy parser cen nie ogranicza niezależnego kontraktu komunikacji, ale brakującego materiału źródłowego nie można odtworzyć z dzisiejszej witryny.

Pierwszy poprawny zapis rozszerzonego zakresu tworzy nową bazę. Dwa kolejne dni z takim zapisem umożliwiają pełne porównanie tego zakresu. Naprawczy skan tego samego dnia zachowuje poprzedni dzień jako bazę. Przebudowa formatu korzysta z oryginalnych plików o zgodnych datach i tożsamościach, nie odwiedza stron w przeszłości.

Harmonogram pozostaje codzienny, również w weekend: 06:17 Europe/Warsaw, z celem gotowości raportu przed 08:00. Blokady domen i opóźnienia GitHub Actions są widoczne w wyniku. Historia pozostaje przechowywana przez 180 dni.

## Reguły konkretnych stron

`communication_ignore_selectors` pomija wskazany fragment DOM w kolektorze komunikacji oraz przy wyznaczaniu sekcji rekomendacji. Reguła jest częścią tożsamości pomiaru tylko w skonfigurowanej domenie, więc nie resetuje bazy pozostałych pracowni. Dla Praktyczne Projekty wyklucza `#imHeader_imHTMLObject_04`: nagłówek wyszukiwarki zawierał „Inne projekty” i błędnie obejmował wykluczeniem całą dalszą kartę. Reguła zachowuje właściwy nagłówek projektu, jego opis i ofertę.
