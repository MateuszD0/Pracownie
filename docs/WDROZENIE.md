**Stan wdrożenia: 20 października 2026**

Jedynym repozytorium kodu, workflow i opublikowanych raportów jest publiczne [MateuszD0/Pracownie](https://github.com/MateuszD0/Pracownie), gałąź `main`. Checkout środowiska Codex to `/workspace/Pracownie`. Produkcyjną automatyzację uruchamia GitHub Actions na standardowym runnerze Ubuntu. Nie potrzeba osobistego tokenu ani płatnego API. Raporty są publiczne, tak jak repozytorium.

[Spis raportów](../RAPORTY.md) · [Produkcja: raport dnia](https://github.com/MateuszD0/Pracownie/releases/tag/monitor-report-2026-10-20) · [Uruchomienia](https://github.com/MateuszD0/Pracownie/actions/workflows/monitor.yml)

**Zakres wiarygodnych wniosków z 20 października:** siedem porównywalnych cen pozostało bez zmian. Dla pozostałych 58 pracowni nie ustalono dziennej zmiany ceny. Spośród 125 niejednoznacznych obserwacji 121 jest obciążonych zmianą sposobu odczytu, a cztery dotyczą samych metadanych terminu ceny. Nie stanowią ustalonej listy zmian ofert ani zadań do potwierdzenia przez użytkownika. Pełny monitoring zmian sprzedażowych pozostaje niepotwierdzony; sukces publikacji i testów tego nie zastępuje.

**Potwierdzone uruchomienia**

| Przebieg | Wynik i pomiar |
| --- | --- |
| [Skan harmonogramu z 20 października](https://github.com/MateuszD0/Pracownie/actions/runs/39400837148) | Publikacja zakończona sukcesem. Raport: 61/65 stron głównych, 60/65 kart, 58 cen. Połączono 103 strony z odczytem 19–20 października, w tym 100 par zrzutów. Siedem porównywalnych par cen bez zmiany. 125 obserwacji wymaga oceny; nie są potwierdzonymi zmianami sprzedażowymi. |
| [Pełny, pierwszy skan 65 domen](https://github.com/MateuszD0/Pracownie/actions/runs/39311240448) | Publikacja TXT, ZIP i trwałego stanu zakończona. Skan: 1491,9 s; ZIP: 247,6 MB; stan: 104,3 MB. 55 domen odczytanych częściowo, 10 bez udanego odczytu. |
| [Ponowny pilotaż na świeżym runnerze](https://github.com/MateuszD0/Pracownie/actions/runs/39313438127) | Poprzedni stan i wybór projektów odtworzone z Releases. Pięć domen odczytanych częściowo, w tym karta Extradom. Skan: 133,6 s; ZIP: 14,2 MB. |
| [Pełna walidacja po korektach](https://github.com/MateuszD0/Pracownie/actions/runs/39321629811) | Zakończona publikacją. Wszystkie 65 domen podjęte, bez pominięć z powodu budżetu. Skan: 1581,8 s (26 min 22 s); ZIP: 275,8 MB; stan: 200,4 MB. 57 domen częściowo odczytanych, 8 bez udanego odczytu. |
| [Pilotaż poprawki panelu cookies WP](https://github.com/MateuszD0/Pracownie/actions/runs/39325931312) | Zakończony publikacją; skan 194,4 s, 47 plików zgodnych z manifestem. Panel cookies Extradom został zamknięty przez zapis odmowy; karta i zrzut nie są nim zasłonięte. Pozostałe ograniczenia kontrolek i zasobów są nadal raportowane. |

Archiwa sprawdzono niezależnie: 515 plików pierwszego pełnego skanu i 572 pliki po korektach zgodne z sumami SHA-256 manifestów. Odtworzony stan zawiera 466 poprawnych scenariuszy i 55 zamrożonych kart. [Macierz odczytów wszystkich domen](POKRYCIE_DOMEN.md) wskazuje konkretne braki. W pierwszym wyborze wykryto osiem kategorii, poradników lub dodatków zamiast kart. Konfiguracja zawiera jawne korekty wyłącznie tych początkowych błędów; nie porównuje się ich z nową kartą jako zmiany oferty. Poprawnie wybrane projekty pozostają stałe. 57 adresów konkretnych kart ustalono w konfiguracji; ich podstawy wyboru są jawne. Ekspozycja lub ranking popularności nie stanowią dowodu liczby sprzedaży.

**Harmonogram i koszt**

Od konfiguracji z 21 października start główny jest codziennie o 05:17 Europe/Warsaw, także w weekend; próba zapasowa jest o 06:07. Celem jest opublikowany raport w Releases przed 08:00. GitHub nie gwarantuje punktualnego startu harmonogramu. Kontrola pod wspólną blokadą zapisu sprawdza zatwierdzony manifest, obecność plików oraz brakujące odczyty: raport bez błędów przejściowych pomija ponowny skan, a brakujące odczyty kwalifikują domeny do naprawy; a przerwany upload nie blokuje próby zapasowej. Cron UTC z kontrolą strefy polskiej obsługuje czas letni i zimowy; dodatkowe wywołania sprawdzają gotowość albo podejmują próbę, jeśli raport nadal nie powstał. Ręczne naprawy nie są pomijane. Szczegóły i wyrażenia cron są w [README](../README.md).

Pełny przebieg zmieścił się w pierwotnym budżecie 30 minut skanowania. Po pomiarze zwiększono zapas do 60 minut skanu i 75 minut całego joba, uwzględniając porównania obrazów w kolejnych dniach. Instalacja i publikacja zwiększają czas całego joba. Raport zapisuje godziny odczytów, a wydanie i podsumowanie Actions podają godzinę publikacji. Publikacja po 08:00 daje ostrzeżenie w Actions; spóźnione wywołanie nadal wykonuje skan.

Standardowy runner publicznego repozytorium nie zużywa limitu 2000 minut dla prywatnych repozytoriów GitHub Free. Archiwum 180 dni korzysta z Releases. Krótkie artefakty awarii przechowywane są przez trzy dni. Pliki graficzne nie trafiają do historii Git.

**Co zostało sprawdzone**

[Pełne testy na GitHub Actions dla działającego raportu HTML](https://github.com/MateuszD0/Pracownie/actions/runs/39398206531) i lint zakończone sukcesem dla wersji 677adda. Po kolejnych poprawkach bieżący wynik jest dostępny w [workflow Testy](https://github.com/MateuszD0/Pracownie/actions/workflows/tests.yml).

- Rzeczywisty Chromium na kontrolowanych stronach: obniżka ceny 4590 → 4290 PLN, dodatki, rozwijane sekcje, zakładki, warianty, koszyk, cookies, ukryte kontrolki i powtarzające się identyfikatory DOM.
- Zachowanie poprawnego stanu po awarii HTTP, stały wybór karty, korekta początkowej kategorii bez fałszywej różnicy, powtórzenie dnia i wznowienie bez zbędnych odczytów.
- Bezpieczny zapis lokalny, sumy kontrolne archiwów, odtworzenie na nowym runnerze, transakcja publikacji, retencja 180 dni i ochrona plików użytkownika.
- Lokalna zmiana banera na długiej stronie, wizualny punkt odniesienia bez rozpoznanego tekstu i niepewny OCR oznaczany do oceny.
- Porównania strony głównej i karty z oddzielnymi datami, zachowanie różnic po ponowieniu dnia, rzeczywiste przerwy w historii oraz raport działający bez JavaScript. Plik HTML z Releases zawiera teksty przed/po i wbudowane podglądy; pełne zrzuty są w ZIP.
- Opóźnione ładowanie ustawień cookies: skaner czeka na kontrolki, potwierdza odmowę i zamknięcie panelu. Publikacja plików raportu jest niezależna od zatwierdzenia opcjonalnego środowiska Pages.

Przykład liczbowej obniżki pochodzi z kontrolowanego testu. Nie jest informacją o zmianie ceny którejkolwiek rzeczywistej pracowni.

**Granice potwierdzonego zakresu**

Raport zawiera rzeczywiste odczyty 19 i 20 października. Pierwszy poprawny odczyt każdej strony nadal tworzy jej punkt odniesienia; nie ma zrzutów sprzed uruchomienia. Zmiany parsera ograniczyły porównywalność części pól między tymi dniami, więc takie obserwacje są oznaczone do oceny. Nie potwierdzono zmian sprzedażowych w porównywalnym zakresie. Potrzebne są kolejne dni pracy bez zmiany reguł odczytu, aby ocenić stabilność alarmów i terminowość; testy syntetyczne jej nie zastępują.

Automatyczne scenariusze mają limit czasu i liczby interakcji. Zależności konfiguratorów, wszystkie kombinacje wariantów, dalsze kroki koszyka oraz niestandardowe kontrolki wymagają adapterów. Każda domena ma nadal inspection:pending, dopóki nie zostanie potwierdzony jej pełny zakres. Sam HTTP 200 ani znalezienie karty nie oznaczają pełnego sprawdzenia. W raporcie z 20 października brakuje podstawowych odczytów pięciu domen: archido.pl, domydlanas.pl i lk-projekt.pl (403), dompp.pl (timeout) oraz karty hbstudio.pl (429). Pozostałe panele cookies, brakujące zasoby i nieodtworzone scenariusze są wykazane oddzielnie w diagnostyce.

Lokalne Chromium tego środowiska nie ufa certyfikatowi proxy przy dostępie do rzeczywistych stron. Produkcyjne skany wykonuje GitHub Actions, gdzie ten problem nie występuje. TLS pozostaje włączony. Projekt konfiguracji środowiska Codex zawiera instalację zależności, instrukcję startową i listę hostów; zapis projektu ustawień nie oznacza jego opublikowania w interfejsie środowiska.

**Utrzymanie**

Najpierw czytaj podsumowanie TXT i pokrycie.json, następnie dowody konkretnej domeny. Zielony job potwierdza zapis raportu, a nie pełność wszystkich odczytów. Polecenia ręcznego ponowienia, trybu naprawczego, adapterów, retencji i zatrzymania automatyzacji opisuje [README](../README.md). Do niezależnej kontroli pobranego ZIP służy scripts/audit_report.py.

Po udanych testach kodu wysłanego na `main` automatyczna przebudowa publikuje ostatni zatwierdzony raport w nowym formacie. Nie zmienia dat odczytów i nie uruchamia dodatkowego skanu. Codzienny workflow nadal odwiedza wszystkie domeny. Pages jest osobnym zadaniem po zapisie raportu do Releases, więc ustawienia zatwierdzania Pages nie blokują skanowania. Stały adres WWW wymaga włączenia Pages przez właściciela; aktualny HTML można zawsze pobrać ze spisu raportów.
