# Naprawa odczytów — 28 października 2026

Cel: porównywać stronę główną i jedną stałą kartę projektu każdej pracowni, bez oznaczania brakujących danych jako braku zmian.

## Stan przed naprawą

Dzisiejszy raport miał 224 oczekiwane strony (112 pracowni). Odczytano 191 stron, z czego 12 częściowo; 179 miało poprawną jakość. Pełną parę zapisów komunikacji z 27 i 28 października miały obie strony 84 pracowni. Dla 28 pracowni brakowało przynajmniej jednego porównania. To różne miary: dzisiejszy odczyt nie zastępuje wczorajszego zapisu.

## Usunięte przyczyny po stronie monitora

- Wybór pierwszego projektu uwzględnia katalogi i rankingi dostępne w menu. Wcześniej zbierano wyłącznie linki z treści oferty, więc m.in. katalog MJS i PARTERO pozostawał nieodczytany. Maksymalnie dwa katalogi i osiem kandydatów; zapamiętany projekt pozostaje stały.
- Stary zapis strony głównej bez linków do katalogów nie jest ponownie używany do naprawy brakującego pierwszego wyboru.
- Poprawiono docelowe serwisy HOMEKONCEPT i Architeki. Przekierowania zweryfikowano na runnerze; BudujDom zachowuje również kontakt biuro@architeka.pl. Identyfikatory pracowni i ich grupy współpracy pozostają stałe.
- Zapisano zweryfikowane adresy kart dla MJS, PARTERO, OPprojekt, OPUS, Machoń, Domek.net.pl, Agrobisp i Witek. Karta portfolio Witek i wizualna karta Domek mają sprawdzany dokładny URL i widoczną nazwę. Agrobisp ma ogólny H1 na wszystkich podstronach, więc sprawdzany jest symbol projektu i obecność pola „Symbol projektu”. Nie deklarujemy bestsellera bez publicznych danych.
- Katalog Gut Architektura jest w sklepie, a katalog NANOstudio w dziale Architektura; dodano te źródła wyboru. Dla Archiportal dodano zamknięcie zidentyfikowanego panelu cookies.
- Linki do koszyka, kategorii i banerów nie są kandydatami na kartę. Strona „szukaj” z terminami projektowymi w nawigacji nie przechodzi walidacji produktu. Diagnostyka pokazuje treść przyczyny odrzucenia karty.
- Raport rozdziela pierwszy poprawny odczyt, lukę historii, odczyt częściowy, blokadę serwisu i brak wybranego projektu. Odczyt częściowy nie jest już nazywany pierwszym poprawnym zapisem. W tabeli podano stan i następny krok; długie zestawienia mają dalsze strony, by nie przekroczyć limitu renderowania GitHuba. HTML sprawdzono przy szerokościach 1280 i 390 px.
- Odświeżenie układu sprawdza aktywne skany przed wejściem do wspólnej kolejki publikacji. Podczas prac GitHub zastąpił oczekujący skan odświeżeniem, mimo `cancel-in-progress: false`. Nowe sprawdzenie w rzeczywistym uruchomieniu odłożyło odświeżenie i pozostawiło skan w kolejce.

## Dowody i weryfikacja

- Diagnostyka stron na GitHubie: https://github.com/MateuszD0/Pracownie/actions/runs/40661946101
- Diagnostyka katalogów: https://github.com/MateuszD0/Pracownie/actions/runs/40662708953
- Sprawdzenie adresów i kart graficznych: https://github.com/MateuszD0/Pracownie/actions/runs/40663774085
- Pełne testy i lint końcowej wersji: https://github.com/MateuszD0/Pracownie/actions/runs/40664800140 — sukces. Zestaw zawiera 341 testów.
- Sprawdzenie pierwszeństwa skanu: https://github.com/MateuszD0/Pracownie/actions/runs/40665572491 — admission zakończone; przebudowa pominięta przy aktywnym skanie.
- Skan naprawczy 28 pracowni: https://github.com/MateuszD0/Pracownie/actions/runs/40664850285

## Wynik po publikacji

Końcowy raport `2026-10-28T095229.885546-0000-15b0445d` został zatwierdzony i opublikowany. Odczytano **206/224 strony** (wcześniej 191): **191 poprawnie**, **15 częściowo**, **18 bez odczytu**. Odzyskano 15 odczytów; liczba odczytów poprawnej jakości wzrosła o 12, z 179 do 191. Nie utracono żadnego wcześniejszego poprawnego odczytu. Wszystkie wcześniej zapisane adresy wybranych projektów pozostały takie same.

Pełne porównanie obu stron dzień do dnia nadal obejmuje **84/112 pracowni**. To nie licznik działających stron: nowe poprawne zapisy potrzebują kolejnego dnia. Tabela rozdziela 14 stron z odczytem działającym, ale bez właściwej historii, od 33 stron wymagających naprawy odczytu (15 częściowych i 18 brakujących). Naprawa nie dopisała fikcyjnych zapisów z 27 października.

Ostatnia korekta dotyczyła adresu Witek: serwer przekierowuje `index-g56.html` do `index-g56`. Po zapisaniu rzeczywistego adresu karta została odczytana; brak fontu nadal ogranicza jakość wizualną.

- Końcowy skan i publikacja: https://github.com/MateuszD0/Pracownie/actions/runs/40667139463 — sukces.
- Testy końcowej konfiguracji: https://github.com/MateuszD0/Pracownie/actions/runs/40667118677 — sukces.
- Bieżący dashboard: https://github.com/MateuszD0/Pracownie/blob/main/DASHBOARD.md

## Ograniczenia potwierdzone diagnostyką

- archido.pl, domyigaraze.pl i lk-projekt.pl zwracają weryfikację dostępu/403; domyzmieta.pl zwraca 403 Forbidden. Nie zmieniono odmowy dostępu w poprawny odczyt.
- archbb.pl zwraca HTTP 500; domyciekawe.pl nie rozwiązuje się w DNS. horyzont.com powoduje błąd protokołu w Chromium także dla bezpośrednich adresów HTTPS.
- birylo.pl pokazuje portfolio artystyczne „Przemo Biryło”, a improjekty.pl przekierowuje do serwisu obrotu domenami. Potrzebne są aktualne adresy właściwych pracowni; nie zastąpiono ich odgadniętymi domenami.
- Braki arkuszy stylów w kilku serwisach i panel cookies TipiTom mogą nadal ograniczać zakres. Nie wyłączono kontroli jakości tylko po to, by zwiększyć licznik.
- Nowo odzyskane strony potrzebują następnego poprawnego zapisu, aby uzyskać porównanie dzień do dnia. Nie można dopisać danych z wczoraj, których skaner nie zapisał. Extradom pozostaje wykluczony, a 18 partnerów bez WWW nie jest skanowanych.
