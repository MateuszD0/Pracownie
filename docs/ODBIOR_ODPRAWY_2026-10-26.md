# Wdrożenie odprawy dnia — 26.10.2026

Punkt wejścia: [DASHBOARD.md](../DASHBOARD.md). Otwórz „Przed / po” przy konkretnym zdarzeniu. Wyszukiwanie i filtry są w pliku „Porównanie HTML — jeden plik”, dostępnym w [wydaniu dnia](https://github.com/MateuszD0/Pracownie/releases/tag/monitor-report-2026-10-26).

## Co zmieniło się w produkcie

- Na start pięć najważniejszych zdarzeń, dalsze po rozwinięciu. Osobna widoczna sekcja „Ważne do sprawdzenia”.
- Jedno zdarzenie może mieć źródła na głównej i stałej karcie. Różne warunki oferty pozostają osobnymi zdarzeniami.
- Teksty i daty przed/po oraz podglądy zrzutów są pod jednym odnośnikiem. Przesunięcia i rozmiary nie dominują w podsumowaniu.
- Wyszukiwanie, filtry, reset i przejście do dowodu działają także w pobieranym HTML. CSV głównego widoku odpowiada wybranemu zakresowi zdarzeń.
- Rejestr komunikatów pokazuje ostatni zapis i jego datę. Historia zdarzeń i kolejka dalszych sprawdzeń są zachowywane w stanie monitora.
- Kolejne publikacje zachowują wcześniejsze pliki tego samego dnia. E-mail przypina odnośniki do wersji repozytorium użytej przy wysyłce, aby późniejsza zmiana dashboardu nie zmieniła jego dowodów.
- Odświeżenie raportu ma obsługę polskiego OCR. Jeśli OCR jest niedostępny, zachowuje wcześniej odczytany tekst wyłącznie przy identycznych skrótach SHA-256 obu wycinków. Zmieniony obraz wyklucza użycie starego opisu.

## Odbiór na rzeczywistych danych

Podstawa: skan `2026-10-26T191849.956951-0000-7b460dc3`, porównanie 25 → 26.10.2026. To wieczorna naprawa Planujdom i zmiana układu, nie nowy poranny skan wszystkich pracowni.

| Sprawdzenie | Wynik |
| --- | --- |
| Liczba pracowni | 66; wszystkie obecne w raporcie |
| Porównanie obu stron | 60/66 pracowni |
| Odprawa | 8 zdarzeń w głównej części, 1 ważny sygnał do sprawdzenia |
| Pozostałe dane przy naprawie Planujdom | Zachowane wyniki pozostałych 65 pracowni; końcowe odświeżenie porządkuje kolejność obserwacji i etykiety dwóch opisów OCR, zachowując wartości, daty, źródła i dowody |
| Wybór projektów | Cały zapis wyborów identyczny; bez zamiany kart |
| Planujdom | Oba odczyty podstawowe poprawne; wykonano dodatkowe sprawdzenie oferty |
| Historia | Wcześniejszy HTML wydania `cfafb6fe` nadal dostępny |
| Opublikowany HTML | Około 7,34 MB; działa wyszukiwanie MG Projekt i Dobre Domy, reset, przejście do dowodu Alexander Studio |
| Dowód | Oba osadzone obrazy załadowane, pełne teksty i daty widoczne |
| Telefon | Brak poziomego przepełnienia przy szerokości 390 px; brak błędów JavaScript |
| Termin | Pierwsza publikacja 08:26:46 czasu polskiego; kontroler prawidłowo zgłasza przekroczenie 08:00 |
| E-mail | Wysyłka pominięta z powodu braku konfiguracji; sukces zadania konfiguracyjnego nie jest wysłaniem wiadomości |

W Planujdom nie odczytano wcześniejszego baneru „WYBRANE PROJEKTY Z RABATEM -15%”. Dodatkowy odczyt wskazał m.in. tablicę budowy gratis, dziennik budowy gratis i bezpłatną konsultację. Nie dowodzi to, że rabat zakończono, ani że te dodatki są nowe. Zdarzenie pozostaje w kolejce do ponownego sprawdzenia.

[Testy pełnego wdrożenia](https://github.com/MateuszD0/Pracownie/actions/runs/40384234503) i [skan z publikacją](https://github.com/MateuszD0/Pracownie/actions/runs/40385191344) zakończyły się powodzeniem. Końcowe doprecyzowanie komunikatu i przypinanie odnośników mailowych ma dodatkowe testy regresji. [CI korekty](https://github.com/MateuszD0/Pracownie/actions/runs/40386853821) i [odświeżenie raportu bez skanowania](https://github.com/MateuszD0/Pracownie/actions/runs/40386898386) również zakończyły się powodzeniem.

Poprawka zachowania OCR przeszła 24 testy właściwego zakresu oraz wszystkie testy logiki w [końcowej publikacji](https://github.com/MateuszD0/Pracownie/actions/runs/40388388452). Wydanie `2026-10-26T194016.922713-0000-format-984f447a` pobrano ponownie i sprawdzono w przeglądarce: 66 pracowni, działające filtry, oba obrazy dowodu, reset i układ telefonu. Porównanie danych potwierdziło zachowanie treści obu OCR; różni się tylko kolejność obserwacji i ujednolicone etykiety tych opisów. [Pełny CI ostatniej poprawki](https://github.com/MateuszD0/Pracownie/actions/runs/40388666296) w chwili tej kontroli nadal instalował Chromium; jego wyniku nie zaliczono do ukończonych testów.

Zrzuty po publikacji: [komputer](audyt-2026-10-26/po-podsumowanie.png), [telefon](audyt-2026-10-26/po-telefon.png), [dowód przed/po](audyt-2026-10-26/po-dowod.png). Zrzuty dokumentują wydanie po skanie, przed drobnym doprecyzowaniem zdania o brakującym banerze Planujdom.

## Otwarte ograniczenia i dalsza kontrola

- Archido i LK-Projekt odmawiają odczytu kodem 403. DomPP, House Collection i MG Projekt nie mają porównywalnej bazy; karta HB Studio ma lukę we wczorajszym zapisie. Nie tworzymy brakującej historii z dzisiejszej strony.
- 537 pozycji rejestru oznacza komunikaty odczytane na stronach, nie 537 potwierdzonych aktywnych promocji.
- GitHub Pages wymaga ustawienia źródła na GitHub Actions w ustawieniach repozytorium. Próba przez dostępne połączenie zwróciła HTTP 403. Markdown i pobierany HTML działają niezależnie.
- E-mail wymaga sekretów `REPORT_EMAIL_TO` i `SMTP_PASSWORD`, zgodnie z [EMAIL.md](../EMAIL.md). Odczyt ustawień sekretów przez dostępne połączenie również zwraca HTTP 403. Hasła nie zapisujemy w repozytorium ani w rozmowie.
- Użytkownik wybrał na razie korzystanie z dashboardu. Konfiguracja poczty jest opcjonalna i nie blokuje odbioru raportu.
- Codzienny harmonogram obejmuje weekendy: główna próba 04:17, zapasowa 05:07 Europe/Warsaw. Cel publikacji pozostaje 08:00; darmowy planista GitHuba może się opóźnić.
- Przez pierwszy tydzień potrzebna jest ocena wszystkich ważnych alertów i próby stron bez alertu. Mierzymy trafność, przeoczenia, termin i rozmiar archiwów; nie deklarujemy z góry osiągnięcia 95% trafności.
- Formalny odbiór wszystkich interakcji w 66 serwisach pozostaje osobną pracą. Działające testy i odczyty podstawowe nie potwierdzają wykonania każdej zakładki i opcji oferty.
- Pełne ZIP-y kolejnych wydań mogą powtarzać obrazy. Podglądy są lekkie, lecz dalsza deduplikacja pełnych archiwów i budżet 180 dni wymagają pomiaru eksploatacyjnego.
