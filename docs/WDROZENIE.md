**Stan wdrożenia: 19 października 2026**

Repozytorium jest publiczne. Produkcyjną automatyzację uruchamia GitHub Actions na standardowym runnerze Ubuntu. Nie potrzeba osobistego tokenu ani płatnego API. Raporty są publiczne, tak jak repozytorium.

[Spis raportów](../RAPORTY.md) · [Produkcja: raport dnia](https://github.com/MateuszD0/Pracownie/releases/tag/monitor-report-2026-10-19) · [Uruchomienia](https://github.com/MateuszD0/Pracownie/actions/workflows/monitor.yml)

**Potwierdzone uruchomienia**

| Przebieg | Wynik i pomiar |
| --- | --- |
| [Pełny, pierwszy skan 65 domen](https://github.com/MateuszD0/Pracownie/actions/runs/39311240448) | Publikacja TXT, ZIP i trwałego stanu zakończona. Skan: 1491,9 s; ZIP: 247,6 MB; stan: 104,3 MB. 55 domen odczytanych częściowo, 10 bez udanego odczytu. |
| [Ponowny pilotaż na świeżym runnerze](https://github.com/MateuszD0/Pracownie/actions/runs/39313438127) | Poprzedni stan i wybór projektów odtworzone z Releases. Pięć domen odczytanych częściowo, w tym karta Extradom. Skan: 133,6 s; ZIP: 14,2 MB. |
| [Pełna walidacja po korektach](https://github.com/MateuszD0/Pracownie/actions/runs/39321629811) | Uruchomiona z ponownym odczytem wszystkich domen. Wynik zostanie dopisany po weryfikacji archiwum. |

Archiwum pierwszego pełnego skanu sprawdzono niezależnie: 515 plików zgodnych z sumami SHA-256 manifestu. W pierwszym wyborze wykryto osiem kategorii, poradników lub dodatków zamiast kart. Konfiguracja zawiera jawne korekty wyłącznie tych początkowych błędów; nie porównuje się ich z nową kartą jako zmiany oferty. Poprawnie wybrane projekty pozostają stałe. 57 adresów konkretnych kart ustalono w konfiguracji; ich podstawy wyboru są jawne. Ekspozycja lub ranking popularności nie stanowią dowodu liczby sprzedaży.

**Harmonogram i koszt**

Skan rozpoczyna się codziennie o 06:17 Europe/Warsaw, także w weekend. Celem jest gotowy raport przed 08:00. GitHub nie gwarantuje punktualnego startu harmonogramu. Pierwszy pełny przebieg zmieścił się w budżecie 30 minut skanowania; instalacja i publikacja zwiększają czas całego joba. Raport zapisuje godziny odczytów, a wydanie i podsumowanie Actions podają godzinę publikacji.

Standardowy runner publicznego repozytorium nie zużywa limitu 2000 minut dla prywatnych repozytoriów GitHub Free. Archiwum 180 dni korzysta z Releases. Krótkie artefakty awarii przechowywane są przez trzy dni. Pliki graficzne nie trafiają do historii Git.

**Co zostało sprawdzone**

- Rzeczywisty Chromium na kontrolowanych stronach: obniżka ceny 4590 → 4290 PLN, dodatki, rozwijane sekcje, zakładki, warianty, koszyk, cookies, ukryte kontrolki i powtarzające się identyfikatory DOM.
- Zachowanie poprawnego stanu po awarii HTTP, stały wybór karty, korekta początkowej kategorii bez fałszywej różnicy, powtórzenie dnia i wznowienie bez zbędnych odczytów.
- Bezpieczny zapis lokalny, sumy kontrolne archiwów, odtworzenie na nowym runnerze, transakcja publikacji, retencja 180 dni i ochrona plików użytkownika.
- Lokalna zmiana banera na długiej stronie, wizualny punkt odniesienia bez rozpoznanego tekstu i niepewny OCR oznaczany do oceny.

Przykład liczbowej obniżki pochodzi z kontrolowanego testu. Nie jest informacją o zmianie ceny którejkolwiek rzeczywistej pracowni.

**Granice potwierdzonego zakresu**

Pierwszy dzień tworzy punkt odniesienia. Nie ma historycznych zrzutów sprzed uruchomienia. Rzeczywiste porównania dzień do dnia będą dostępne po kolejnych codziennych odczytach. Obserwacja stabilności przez 2–3 dni pozostaje do wykonania; testy powtórzeń w jednym dniu jej nie zastępują.

Automatyczne scenariusze mają limit czasu i liczby interakcji. Zależności konfiguratorów, wszystkie kombinacje wariantów, dalsze kroki koszyka oraz niestandardowe kontrolki wymagają adapterów. Każda domena ma nadal inspection:pending, dopóki nie zostanie potwierdzony jej pełny zakres. Sam HTTP 200 ani znalezienie karty nie oznaczają pełnego sprawdzenia. Błędy 403, niedostępne strony, pozostałe panele cookies, zasoby i nieodtworzone scenariusze są wykazane w raporcie.

Lokalne Chromium tego środowiska nie ufa certyfikatowi proxy przy dostępie do rzeczywistych stron. Produkcyjne skany wykonuje GitHub Actions, gdzie ten problem nie występuje. TLS pozostaje włączony. Projekt konfiguracji środowiska Codex zawiera instalację zależności, instrukcję startową i listę hostów; zapis projektu ustawień nie oznacza jego opublikowania w interfejsie środowiska.

**Utrzymanie**

Najpierw czytaj podsumowanie TXT i pokrycie.json, następnie dowody konkretnej domeny. Zielony job potwierdza zapis raportu, a nie pełność wszystkich odczytów. Polecenia ręcznego ponowienia, trybu naprawczego, adapterów, retencji i zatrzymania automatyzacji opisuje [README](../README.md). Do niezależnej kontroli pobranego ZIP służy scripts/audit_report.py.
