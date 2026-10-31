# Pokrycie skanu — 31 października 2026

Cel pozostaje ten sam: codziennie czytać stronę główną i tę samą kartę projektu, a następnie wskazywać zmiany oferty i komunikacji z dowodem przed/po. Ceny i grafika nie mogą zastępować brakującego porównania tekstu.

## Punkt wyjścia

Zatwierdzony raport z 31.10 obejmuje 112 pracowni i 224 oczekiwane strony. Jest 206 odczytów: 191 poprawnej jakości i 15 częściowych; 18 stron pozostaje bez odczytu. Obie strony dzień do dnia porównano u 94 pracowni. Wszystkie 112 pracowni są w zakresie skanu — liczba porównań nie jest liczbą podjętych prób.

Odczyty częściowe: Agrobisp (2 strony), DomPP (2), House Collection (2), Machoń (2), OPprojekt (1), Malachit (2), TipiTom (2), Witek (2).

Bez odczytu: ArchBB (2), Archido (2), Biryło (karta), Domy Ciekawe (2), Domy i Garaże (2), Domy z Miętą (2), Forteca Klimatyczna (karta), Horyzont (2), IMprojekty (2), LK-Projekt (2).

## Poprawki

1. **Wybór karty bez miniatury i ceny.** Rozpoznawane są nazwane linki do kart HTML z jednoznacznym kontekstem „projekt domu”. Wcześniej w ten sposób pomijano wszystkie karty Fortecy. Treść każdego kandydata nadal jest walidowana, a zapisany projekt nie zmienia się przy następnych skanach.
2. **Panel Complianz.** Skaner rozróżnia aktywny baner od ukrytej kopii szablonu i uwzględnia opóźnione podpięcie zdarzenia. TipiTom ma tryb opt-out z ukrytym przyciskiem odmowy; wywołujemy rzeczywistą akcję odmowy tego aktywnego banera. Diagnostyka potwierdziła zamknięcie panelu i odmowę zgód marketingowych, statystycznych i preferencji; pozostają tylko funkcjonalne. Panel nie jest sztucznie usuwany z DOM.
3. **Tekst i grafika oceniane osobno.** Brak arkusza Google Fonts może ograniczać grafikę przy poprawnym odczycie tekstu. Dopuszczenie tekstu wymaga przejścia kontroli cookies, wymaganych elementów i limitu DOM; dotyczy wyłącznie znanych endpointów definicji fontów. Dowolny brak CSS, plik o nazwie `myfont.css`, zasłonięta oferta i starszy odczyt bez tych kontroli nadal nie przechodzą.
4. **Oddzielna historia komunikacji.** Taki zapis tekstu otrzymuje osobną historię, wraz z datą i obrazem, bez zastępowania ostatniej poprawnej bazy cen. Powtórzenie tego samego dnia nadal porównuje do wczoraj. Archiwizacja, odtwarzanie, przebudowa raportu i retencja 180 dni uwzględniają obie historie. Dowód zmiany ceny zachowuje własną rzeczywistą datę.
5. **Mniej zbędnych ponowień.** Potwierdzony brak samego fontu pozostaje widoczny, ale nie wywołuje kolejnych automatycznych skanów tej domeny w tym samym dniu. Następnego dnia wykonywany jest zwykły odczyt. Pozostałe błędy nadal są kwalifikowane do naprawy według dotychczasowych zasad.
6. **Czytelniejsza informacja o pokryciu.** Dashboard pokazuje osobno odczytane strony, odczyty częściowe, brak odczytu i porównanie z wczoraj. Porównanie tekstu przy ograniczonej grafice ma jawne oznaczenie.
7. **Weryfikacja nie jest ofertą.** Ekran SiteGround `sgcaptcha` z HTTP 200 był wcześniej zapisany w historii TipiTom jako poprawny odczyt. Skaner odrzuca takie strony; również starszy zapis weryfikacji nie może być bazą cen, komunikacji ani odzyskiwanego odczytu. Nie rozwiązuje CAPTCHA.
8. **Odstępy i ograniczenia serwera.** Forteca po wejściu na główną stronę odrzucała szybką próbę otwarcia karty odpowiedzią 429 z czasem ponowienia 300 sekund. Dla tej pracowni ustawiono odstęp co najmniej 30 sekund między rozpoczęciami nawigacji. Jeżeli serwer nadal odmawia, wybór karty jest przerywany od razu z właściwą przyczyną; pozostałe adresy nie są kolejno próbowane, a stan kwalifikuje się do późniejszego ponowienia. Sam odstęp nie jest gwarancją uzyskania dostępu.

## Co pozostaje do zrobienia

- **Adresy pracowni:** potrzebne jest potwierdzenie aktualnych adresów Biryło, Domy Ciekawe i IMprojekty. Dotychczasowe kontrole wskazywały odpowiednio inne portfolio, brak DNS i serwis obrotu domenami. Użytkownik nie ma aktualnych adresów. Pozostają do weryfikacji — nie oznaczamy tych firm jako niemających strony i nie zastępujemy ich zgadywanymi adresami.
- **Odmowy dostępu:** Archido, Domy i Garaże, Domy z Miętą i LK-Projekt wymagają uzgodnionego dostępu lub źródła udostępnionego przez właściciela. HTTP 403 nie jest informacją „bez zmian”.
- **ArchBB:** diagnostyka 31.10 ponownie potwierdziła HTTP 500. To nie jest błąd wyboru projektu po stronie monitora.
- **Horyzont:** zwykły klient HTTP otrzymuje treść, lecz Chromium nadal zgłasza błąd protokołu dla adresów z www i bez www. Wyłączenie HTTP/2 daje pustą odpowiedź. Ewentualny dodatkowy odczyt HTTP powinien mieć osobno oznaczony zakres, bez deklarowania sprawdzenia renderowania i interakcji.
- **Brakujące style stron:** Agrobisp, House Collection, Machoń, OPprojekt i Malachit mają konkretne nierozwiązane adresy CSS. Nie wszystkie te pliki są fontami; nie wyłączamy dla nich kontroli jakości bez inspekcji ich wpływu na ofertę.
- **TipiTom:** poprawiono odczyt karty projektu. Ostatnia próba strony głównej zwróciła stronę weryfikacji dostępu, więc zachowano wcześniejszy częściowy odczyt z 31.10, z jego oryginalną godziną. Komunikat o cookies dotyczy tego wcześniejszego zapisu, a osobny wiersz ponowienia zawiera aktualny błąd. Nie potwierdzono jeszcze poprawnego odczytu obu stron w jednym skanie.
- **Forteca:** odstęp 30 sekund nie usunął HTTP 429 przy karcie. Poprawka rozpoznaje i zachowuje właściwą przyczynę oraz przerywa dalsze próby w okresie ograniczenia, ale dostęp do karty nadal nie został uzyskany.
- **Termin 08:00:** dzisiejsza pierwsza publikacja była o 08:57. Cron GitHuba wciąż bywa opóźniony; zmiana ekstraktora nie naprawia punktualności wywołań. Osobnym usprawnieniem jest zewnętrzne wywoływanie istniejącego workflow przed porannym terminem, z kontrolą świeżości i zapisem rzeczywistej publikacji.

## Weryfikacja

- Diagnostyka HTTP/przeglądarki: https://github.com/MateuszD0/Pracownie/actions/runs/41187335610
- Horyzont z bezpośrednim adresem bez www: https://github.com/MateuszD0/Pracownie/actions/runs/41187467443
- Horyzont na macOS — ten sam błąd protokołu: https://github.com/MateuszD0/Pracownie/actions/runs/41188670775
- Pełne testy pierwszego wdrożenia: https://github.com/MateuszD0/Pracownie/actions/runs/41188187241 — sukces.
- Pierwszy skan naprawczy: https://github.com/MateuszD0/Pracownie/actions/runs/41188607718 — cztery strony DomPP i Witek mają poprawny zapis tekstu przy nadal ograniczonej grafice; zachowano wszystkie 103 wcześniejsze wybory projektów i wszystkie wcześniejsze poprawne odczyty. Odczyty i pary dzienne nadal wynoszą 206/224 i 94/112. Ten skan ujawnił ograniczenie 429 Fortecy i drugi wariant panelu TipiTom, wymagające dodatkowych poprawek powyżej.
- Kontrola TipiTom po uzupełnieniu obsługi odmowy: https://github.com/MateuszD0/Pracownie/actions/runs/41189771011 — w trzech kontrolach zero widocznych paneli; `cmplz_marketing`, `cmplz_statistics`, `cmplz_preferences` mają wartość `deny`, a `cmplz_banner-status` — `dismissed`.
- Testy regresji obejmują cztery kolejne dni, ponowienie tego samego dnia, odmowę cookies, oddzielne daty dowodów cen i tekstu, archiwizację/odtworzenie oraz retencję. Brak dowolnego CSS i widoczny panel cookies nadal blokują wiarygodne porównanie.
- Nowa historia tekstu nie dopisuje odczytu z wczoraj. Gdy nie istnieje wcześniejsza porównywalna baza, dzisiejszy zapis jest pierwszym punktem odniesienia.

Wynik skanu po wdrożeniu należy oceniać na podstawie zatwierdzonego raportu; sukces testów nie jest dowodem odzyskania dostępu do zewnętrznego serwisu.

## Wynik końcowego wdrożenia

- Kod: `398ae39`; pełne CI: https://github.com/MateuszD0/Pracownie/actions/runs/41190819636 — sukces. Lokalnie: 372 testy przeszły, 1 test trybu graficznego pominięty z powodu braku Xvfb. Kontrola stylu kodu przeszła.
- Skan naprawczy: https://github.com/MateuszD0/Pracownie/actions/runs/41191250369 — sukces; zatwierdzony identyfikator `2026-10-31T100644.264445-0000-e99d11cd`.
- Raport obejmuje **112 pracowni, 206/224 odczytane strony, w tym 15 częściowych; 18 stron bez odczytu. Porównanie obu stron dzień do dnia: 94/112 pracowni.** Liczba porównań dziennych jeszcze nie wzrosła — nowe poprawne zapisy nie odtwarzają brakującej historii.
- Cztery strony DomPP i Witek mają wiarygodny zapis tekstu przy ograniczonej grafice. Karta TipiTom przeszła z odczytu częściowego do poprawnego. Weryfikacja dostępu nie zastąpiła treści oferty w historii.
- Względem zatwierdzonego raportu bezpośrednio przed końcowym skanem zachowano wszystkie **206 wcześniejszych odczytów i 103 zamrożone wybory projektów**, a liczba odczytów poprawnej jakości wzrosła ze 190 do 191. Przed tą próbą automatyczne ponowienie obniżyło jakość strony głównej OPprojekt z powodu CSS; dlatego punkt wyjścia końcowego porównania różni się od pierwszego raportu w tym dokumencie.
- Sprawdzono opublikowany `DASHBOARD.md`: pokazuje te same liczby, ograniczenie grafiki dla czterech stron i rzeczywisty zakres godzin odczytu. Późniejszych napraw nie przedstawia jako porannego skanu.

## Kolejność dalszych usprawnień

1. Zbadać wpływ brakujących CSS w pięciu pracowniach na widoczność tekstu. Ewentualne dopuszczenie komunikacji powinno wynikać z testów konkretnych stron, bez automatycznego ignorowania wszystkich błędów stylów.
2. Rozważyć osobno oznaczony odczyt HTML dla Horyzontu, jeśli nie uda się naprawić zgodności przeglądarki. Taki odczyt nie zastąpi sprawdzenia grafiki ani interakcji.
3. Doprecyzować prezentację nieudanego ponowienia obok zachowanego wcześniejszego odczytu, aby od razu było widać ostatni błąd i godzinę dostępnej treści.
4. Sprawdzić stabilność karuzel, rekomendowanych projektów i animowanych tekstów przed nadaniem ich zmianom wysokiego priorytetu. Rotacja elementu może zmieniać zapis bez zmiany oferty.
5. Zapewnić niezależne wywołanie przed 08:00 i kontrolę publikacji. Sam harmonogram GitHuba nie zapewnia punktualności.
