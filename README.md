**Pracownie Monitor**

## [Otwórz dashboard — czytaj tutaj](DASHBOARD.md)

Dashboard otwiera się bezpośrednio w GitHubie, bez pobierania i rozpakowywania plików. Najpierw pokazuje najważniejsze zmiany biznesowe, dalej wszystkie pracownie i osobne porównania strony głównej oraz stałego projektu. Aktualizuje się po codziennym skanie. Pliki HTML, CSV, TXT i zrzuty są materiałami dodatkowymi.

Główny wynik to **dashboard komunikacji 66 pracowni**: konkretne zmiany na stronie głównej oraz stałej karcie projektu. Nagłówki, banery, CTA, argumenty oferty, promocje, dodatki i opisane zmiany wyglądu mają tekst przed/po, źródło i zrzuty. Ceny są informacją dodatkową w rozwijanych szczegółach. Widoczna tabela obejmuje wszystkie pracownie, również z niepełnym porównaniem lub błędem. [Zasady pomiaru komunikacji](docs/KOMUNIKACJA.md).

Trzy główne wskaźniki liczą pracownie ze zmianą komunikacji łącznie, na stronie głównej i na karcie projektu. Zakres porównania tych treści jest liczony niezależnie od cen. Wyszukiwanie i filtry obejmują wskaźniki, tabelę oraz eksport widocznych zmian; pełny CSV zawiera również ceny i pomocnicze obserwacje.

Raport zaczyna się od wniosków i zakresu, któremu można ufać. Liczba zapisanych par stron lub zrzutów nie oznacza liczby ustalonych zmian. Problemy zmienionego sposobu odczytu i samych metadanych pozostają w szczegółach technicznych; ich wyjaśnienie jest zadaniem monitora. Użytkownik nie ma potwierdzać błędów narzędzia.

Wspólne repozytorium kodu i automatyzacji to [MateuszD0/Pracownie](https://github.com/MateuszD0/Pracownie), gałąź `main`. Środowisko chmurowe Codex korzysta z checkoutu `/workspace/Pracownie`. Raporty oraz trwały stan są przechowywane w Releases tego samego repozytorium; lokalne katalogi robocze nie są osobnym wdrożeniem.

Pełne wymagania: [plan wdrożenia](PLAN_WDROZENIA_MONITORINGU.md). Faktyczna dostępność domen: [inspekcja HTTP](docs/INSPEKCJA_DOMEN.md). Status walidacji: [wdrożenie](docs/WDROZENIE.md).

[Spis raportów dziennych](RAPORTY.md) · [Wybrane karty i źródła wyboru](docs/KARTY_PROJEKTOW.md).

[Jak czytać ceny, różnice i brakujące dane](docs/ODCZYT_I_RAPORT.md).

Pierwsze pełne uruchomienia są opisane w [macierzy rzeczywistych odczytów](docs/POKRYCIE_DOMEN.md). Nie wszystkie domeny i interakcje są obecnie dostępne; raport wskazuje te braki jawnie.

Format wyniku pokazuje [syntetyczny przykład TXT](examples/raport-przykladowy.txt). Jest wygenerowany przez właściwy moduł raportów z fikcyjnych danych, bez skanowania rzeczywistej pracowni.

**Uruchomienie w GitHub Actions**

Workflow „Codzienny monitoring pracowni” ma start główny codziennie o **04:17 Europe/Warsaw** i próbę zapasową o **05:07**, również w weekendy. Cel to **opublikowany raport przed 08:00 czasu polskiego**, nie start skanu o ósmej. Próba zapasowa sprawdza zatwierdzony manifest, pliki i świeżość odczytów podstawowych. Ponawia domeny z brakami lub błędami przejściowymi, zachowując poprawne odczyty; trwałe blokady pozostają jawnie opisane. Jeśli nie ma zakresu do ponowienia, pomija skan i instalację przeglądarki. Osobna kontrola o **07:50** zgłasza w Actions brakujące lub częściowe dane. Samo istnienie wydania po przerwanym przesyłaniu nie oznacza sukcesu.

Cron używa UTC (`17 2,3 * * *` i `7 3,4 * * *`), a moduł `pracownie.schedule` stosuje `Europe/Warsaw`. Dzięki temu obie polskie godziny startu działają także po zmianie czasu. Dodatkowe wywołania wynikające z dwóch przesunięć UTC są pomijane przed właściwą porą albo po sprawdzeniu gotowego raportu; jeżeli raport nadal nie powstał, mogą podjąć kolejną próbę. Kontrola działa pod tą samą blokadą co skan i przebudowa raportu, więc oczekujące ponowienie widzi wynik poprzednika. Ręczne skany i naprawy pozostają dostępne niezależnie od tej kontroli.

Kontroler naprawczy ma dodatkowe wywołania co 20 minut w porannym oknie UTC 02:00–07:59 (kontrola stosuje datę i porę Europe/Warsaw). Po zakończeniu skanu, przebudowy lub kontroli gotowości uruchamia się również przez zdarzenie `workflow_run`. Jeżeli wcześniejsza kontrola ustąpiła aktywnej publikacji, jej zakończenie wywołuje ponowną ocenę bez czekania na kolejny cron. Kontroler nie uruchamia równoległych producentów i zachowuje limit dwóch automatycznych napraw dziennie.

Kontrola „Kontrola raportu — dane i termin 08:00” rozdziela dostępność raportu, kompletność odczytów i termin publikacji. Uruchamia się także po zakończeniu skanu lub przebudowy, od 07:50 czasu polskiego. W podsumowaniu Actions podaje link do dashboardu, faktyczną godzinę kontroli oraz listę brakujących i częściowych stron. Dostępny raport z lukami nadal wymaga uwagi — sam sukces zadania skanowania nie oznacza 132 poprawnych odczytów. Termin jest liczony z potwierdzenia publikacji, a nie zakończenia przeglądania stron; przebudowa tego samego dnia zachowuje pierwszą potwierdzoną godzinę.

Naprawa obejmuje także odczyty częściowe, również w starszych manifestach. Przerwane pobranie CSS nie obniża jakości, jeśli ten sam styl został ostatecznie załadowany w przeglądarce; brakujące aktywne style nadal ograniczają jakość porównania. Przy przejściowej stronie weryfikacji skaner czeka do 10 sekund na normalne przekierowanie, bez rozwiązywania CAPTCHA. Trwała odmowa HTTP 403 pozostaje jawnym brakiem odczytu. Workflow diagnostyczny pozwala porównać dostęp HTTP i przeglądarki dla wskazanych domen na rzeczywistym runnerze GitHuba.

Animacje są zatrzymywane po obsłudze cookies: niektóre bannery potrzebują zakończenia animacji do zamknięcia. Dla `domydlanas.pl` skaner przedstawia się jako `PracownieMonitor` z publicznym adresem repozytorium i obsługuje sprawdzony przycisk „Kontynuuj”. Stała karta to N55-G2, wyróżniona w katalogu; nie przypisujemy jej niepotwierdzonego statusu bestsellera. Ustawienia identyfikacji i cookies są ograniczone do tej domeny.

GitHub może opóźnić lub pominąć wywołania harmonogramu; wcześniejszy start i ponowienie dają zapas, ale nie gwarantują terminu. Opóźniony skan nadal rusza, zamiast tracić cały dzień. Podsumowanie Actions podaje rzeczywistą godzinę publikacji i ostrzega, jeśli przekroczono 08:00. Termin dotyczy raportu w Releases; opcjonalne Pages ma osobny etap publikacji.

W zakładce Actions wybierz workflow i Run workflow:

- pilot: pięć domen, osobny stan i archiwum monitor-pilot;
- full: wszystkie 66 domen, stan i archiwum monitor.

Ponowienie tego samego dnia domyślnie naprawia brakujące odczyty. Poprawne scenariusze są odtwarzane z zatwierdzonego archiwum i zachowują rzeczywiste godziny odczytu. Zaznacz rescan, aby wykonać wszystkie odczyty ponownie. Każdego nowego dnia wszystkie domeny są odczytywane od początku.

Pole `repair_domains` pozwala naprawić wskazane domeny bez ponownego skanowania pozostałych. Wymaga wyłączonego `rescan` i istniejącego raportu z tego samego dnia. Pozostałe wyniki zachowują swoje rzeczywiste godziny oraz wszystkie wcześniejsze błędy; pełny raport nadal obejmuje 66 domen. Lokalnie odpowiada temu `--resume --repair-domains domena.pl,druga.pl`. Do istniejącego raportu można też dopisać nową pracownię, jeśli dodano ją do konfiguracji i jawnie wskazano w `repair_domains`; wcześniejsze odczyty zachowują swoje daty i błędy. Usunięcie domen z raportu lub niewskazane rozszerzenie zakresu jest odrzucane.

Workflow „Odśwież układ raportu bez skanowania” przebudowuje ostatni zatwierdzony raport z zachowanych danych i obrazów. Pozwala zmienić format oraz odzyskać poprawny odczyt z tego samego dnia po nieudanym ponowieniu. Zachowuje daty obserwacji i błędy; nie odwiedza ponownie witryn.

Po wysłaniu kodu na `main` i udanych testach GitHub automatycznie uruchamia tę przebudowę. Aktualizuje pliki raportu w Releases oraz spis dni. Zwykła zmiana kodu nie jest nowym skanem (wyjątek: świadomie oznaczony commit `[scan]`, opisany w dokumentacji tabeli): daty danych nadal odpowiadają rzeczywistym wizytom na stronach. Testy z pull requestów nie uruchamiają publikacji.

Wbudowany GITHUB_TOKEN z uprawnieniem contents:write wystarcza do zapisywania Releases. Nie dodawaj osobistego tokenu do kodu. Workflow nie zmienia widoczności repozytorium. W publicznym repozytorium opublikowane raporty również są publiczne.

Otwórz dzień w [spisie raportów](RAPORTY.md). Strona wydania pokazuje dzienną tabelę zmian z linkami do źródeł i dowodów oraz podsumowanie cen bez pobierania archiwum. Dostępne są krótki TXT, CSV do arkusza, osobna diagnostyka i ZIP ze zrzutami.

W wydaniu wybierz **Porównanie HTML — jeden plik**. Teksty przed/po, podświetlone różnice i wbudowane podglądy obrazów są widoczne bez skryptów i osobnych plików. Dowody w dziennej tabeli pokazują zmieniony fragment przed/po; pełne zrzuty są w **Raporcie HTML ze zrzutami** (`*-widok.zip`). Po rozpakowaniu ZIP otwórz `YYYY-MM-DD/index.html`, aby używać wyszukiwania, filtrów i pełnych obrazów. Każda domena ma osobne sekcje strony głównej i projektu z datami, statusem oraz tekstami przed/po. Odnośnik „Zobacz przed/po” otwiera dowód odpowiadający zmianie. Podstawowe porównania są zapisane w HTML, więc zablokowanie skryptów nie usuwa treści.

Na górze są KPI, sześć kategorii biznesowych i krótka tabela konkretnych różnic „Było / Jest” — maksymalnie sześć pracowni, jedna najważniejsza pozycja na pracownię. Promocje i dodatki mają pierwszeństwo; pojedyncze etykiety nawigacji nie trafiają do tego skrótu. Dalej jest zwięzły przegląd wszystkich 66 pracowni. „Porównaj obie strony” rozwija stronę główną i tę samą zapamiętaną kartę projektu, z pełnymi tekstami, datami i zrzutami przed / po. Powtórzenia identycznego komunikatu w zakładkach są zgrupowane, a pełny dziennik źródłowy pozostaje w rozwijanym archiwum. Kompletność pomiaru i diagnostyka mają osobne szczegóły. KPI liczą pracownie, raz na kategorię, wyłącznie z potwierdzonych porównań dzień do dnia. Wyszukiwanie, wybór strony i rodzaju zmiany dotyczą tabeli, liczników i jej eksportu. Obserwowane pracownie są zapamiętywane lokalnie w przeglądarce; wersja HTML bez skryptów zachowuje wszystkie dane i rozwijane sekcje, bez filtrów. Niepewne zapisy zachowujemy do weryfikacji działania monitora. Starszy skan z 19 października zawierał wybrane teksty, bez pełnego zestawu komunikatów. Zgodne fragmenty można policzyć, ale nie potwierdzają one braku zmian na całej stronie. Rozszerzony zapis `communication-v1` tworzy bazę do kolejnych porównań i nie odtwarza brakującej historii. Siedem porównywalnych cen z 19–20 października nie określa zakresu monitorowania komunikacji.

Widok zawiera lżejsze zrzuty JPEG. Pełne archiwum zachowuje bezstratne zrzuty WebP (PNG, gdy jest mniejszy lub obraz przekracza limit WebP), obrazy różnic i dane: `raporty/YYYY-MM-DD/index.html`, `oferty.csv`, `oferty.json`, `podsumowanie.md`, `zmiany.json`, `pokrycie.json` i `diagnostyka.txt`. Plik `_report_template.html` w kodzie jest wyłącznie szablonem; otwieraj wygenerowany `index.html`.

Opcjonalny stały adres WWW wymaga jednorazowego ustawienia **Settings → Pages → Build and deployment → Source: GitHub Actions** przez właściciela repozytorium. Po włączeniu kolejne pełne skany i przebudowy raportu automatycznie publikują najnowszy dzień w Pages. Historia 180 dni pozostaje w Releases; Pages przechowuje bieżący widok. Wyłączone Pages nie blokuje skanów ani publikacji HTML w wydaniach.

Publikacja Pages jest osobnym zadaniem po zapisaniu raportu. Ewentualne zatwierdzenie środowiska `github-pages` lub awaria publikacji strony nie wstrzymuje skanu ani zapisu wyników w Releases.

Cena projektu jest wybierana z konkretnego pola zakupu lub danych produktu. Cena regularna, najniższa z 30 dni, dodatki i koszt budowy nie są ceną aktualną. Kwoty netto i ceny za lokal mają odpowiednie oznaczenia; zakresy wariantów nie są przedstawiane jako pojedyncza cena. Różnica kwot wymaga tego samego źródła pola, waluty, podatku i jednostki. Zmiana parsera ustanawia nowy odczyt dla zmienionych pól i nie jest sama w sobie zmianą oferty.

Plik RAPORTY.md w repozytorium jest automatycznym spisem dni z odnośnikami do TXT i ZIP. Pilotaż ma osobny indeks. Aktualizacja tego użytecznego spisu tworzy normalną aktywność repozytorium; sam publiczny harmonogram bez aktywności może zostać wyłączony przez GitHuba po 60 dniach. Indeks jest generowany, więc własne notatki zapisuj osobno.

Opis wydania w Releases zawiera skrót: do 20 zmian komunikacji i 20 dodatkowych obserwacji, przegląd pracowni oraz linki do wszystkich plików. Cały opis ma limit 60 000 bajtów UTF-8 i najwyżej sześć podglądów obrazów. Ogranicza to rozmiar strony wydania i zabezpiecza publikację przed limitem GitHuba; pełne HTML, TXT, CSV i archiwum zachowują wszystkie wpisy oraz zrzuty. Skrócenie opisu jest jawnie oznaczone.

Pierwszy poprawny skan tworzy punkt odniesienia. Obrazy „przed” pojawią się dopiero w porównaniach z rzeczywiście zapisanym wcześniejszym stanem. Ponowne uruchomienie tego samego dnia porównuje do stanu sprzed tego dnia. Skany zakończone błędem nie zastępują poprawnej historii.

**Limity i koszt**

Używane są standardowe runnery Ubuntu, jedna maszyna i ograniczona współbieżność przeglądarki. Skan ma budżet 60 minut, a cały job 75 minut; raport wyraźnie pokazuje domeny pominięte z powodu czasu. Zapas zwiększono po pełnym pomiarze 26 min 22 s, aby uwzględnić porównania obrazów w kolejnych dniach. Codzienna praca nie wymaga płatnego API.

Standardowe runnery publicznego repozytorium są bezpłatne zgodnie z aktualnymi zasadami GitHuba. Przy prywatnym GitHub Free należy uwzględnić 2000 minut miesięcznie współdzielonych z innymi workflow. Zmierz pełny przebieg przed przyjęciem, że zmieści się w limicie. Równoległe joby sumują zużycie minut; ten projekt używa jednego joba skanującego.

Archiwum korzysta z Releases, nie z długoterminowych artefaktów Actions. Nie traktuj Releases jako bezwarunkowo nieograniczonego magazynu: aktualne limity plików i API nadal obowiązują. Pojedynczy plik większy niż 2 GiB jest odrzucany. Krótkie artefakty diagnostyczne Actions są zachowywane trzy dni i również zużywają limit miejsca.

**Uruchomienie lokalne / środowisko programistyczne**

Wymagane: Python 3.12+, uv 0.12.23, Chromium Playwright. OCR jest opcjonalne; na Ubuntu pakiety tesseract-ocr i tesseract-ocr-pol zapewniają język polski. macOS: odpowiednie pakiety Tesseract można zainstalować przez Homebrew, ale do pracy codziennej MacBook nie jest potrzebny.

~~~sh
uv sync --frozen
uv run playwright install --with-deps chromium
uv run pracownie doctor
uv run pracownie run --scope pilot
uv run pracownie verify --output raporty/pilot
~~~

W środowisku z istniejącym systemowym Chromium można wybrać binarną przeglądarkę:

~~~sh
MONITOR_BROWSER_EXECUTABLE=/usr/bin/chromium uv run pracownie run --scope pilot
~~~

Wersja przeglądarki jest zapisywana w stanie. Po jej zmianie porównanie obrazu jest oznaczane jako wymagające oceny; ceny i tekst nadal są porównywane. Do porównań produkcyjnych używaj przypiętej wersji Playwright z pliku uv.lock.

Środowisko z proxy musi zapewniać prawidłowe zaufanie do jego certyfikatu w przeglądarce. Narzędzie nie wyłącza TLS i nie importuje samodzielnie certyfikatów. HTTP i Chromium mogą korzystać z różnych magazynów zaufania. W razie błędu certyfikatu raport zawiera błąd, a poprzedni stan pozostaje zachowany.

Lokalne katalogi .monitor i raporty są ignorowane przez Git. Stan pilotażu ma oddzielny podkatalog. Przy własnych eksperymentach wybieraj osobny --state-dir i --output. Argument --day służy testom i kontrolowanym odtworzeniom; normalny skan sam ustala datę warszawską.

Lokalny tryb naprawczy włącza --resume. Wznawiane są wyłącznie poprawne odczyty znanych scenariuszy tego samego dnia, powiązane z utrwalonym stanem. Błędy, brak punktu odniesienia, inne zakresy domen i nowe jawne scenariusze wymagają ponownego sprawdzenia. Przy odtwarzaniu z GitHuba weryfikowane są powiązanie z uruchomieniem oraz sumy kontrolne plików.

Zapis i odtworzenie z GitHuba poza Actions wymagają dostępnego GITHUB_TOKEN lub GH_TOKEN z właściwym zakresem:

~~~sh
uv run pracownie doctor --github
uv run pracownie run --github --scope pilot
~~~

Przy skanowaniu podzbioru domen z publikacją podaj inny --namespace, aby nie zastąpić pełnego raportu.

**Konfiguracja domen i adapterów**

config/sites.json zawiera wszystkie domeny. Projekt wybierany jest przy pierwszym poprawnym odczycie i utrwalany w stanie. Kolejne skany używają tego samego adresu także wtedy, gdy pracownia promuje już inny bestseller; zmiana projektu wymaga jawnej migracji punktu odniesienia. Kolejność: oznaczenie bestsellera, sekcja najpopularniejszych, następnie promowany projekt. Podstawa wyboru i źródło są zapisane w wybrane-projekty.json. Ekspozycja na stronie nie dowodzi liczby sprzedaży.

inspection:pending oznacza niepotwierdzone pełne pokrycie. Ustawienie verified wymaga ręcznej inspekcji danych, scenariuszy i dowodów danej domeny. Sam HTTP 200 lub automatyczne znalezienie karty nie wystarcza. Narzędzie nadal raportuje limity i błędy także przy verified.

Najważniejsze pola:

- home_url, project_url, project_name: adresy i opcjonalny jawny wybór projektu;
- selection: podstawa ręcznego wyboru i źródło;
- product_url_pattern: regex zawężający wykrywanie kart; nie wpisuj tu wyrażenia pasującego do całych kategorii;
- discovery_links: sprawdzone strony rankingu, używane jedynie przy początkowym wyborze;
- allowed_hosts: dodatkowe, jawnie sprawdzone hosty przekierowań;
- required: wymagane widoczne selektory dla glowna i projekt;
- masks: selektory elementów pomijanych w odczycie i obrazach, np. konkretny dynamiczny licznik;
- ignore_patterns: precyzyjne regexy tekstu zmiennego; nie usuwaj wszystkich liczb;
- field_selectors: stabilne pola adaptera, w tym ceny;
- scenarios: powtarzalne interakcje z określoną stroną.

Przykład adaptera (selektory są przykładowe, nie przypisane do rzeczywistej domeny):

~~~json
{
  "domain": "przyklad.pl",
  "home_url": "https://przyklad.pl",
  "project_url": "https://przyklad.pl/projekt/dom-a",
  "project_name": "Dom A",
  "inspection": "pending",
  "required": {"projekt": ["h1", "#cena"]},
  "field_selectors": [
    {"key": "cena-podstawowa", "selector": "#cena", "label": "Cena projektu", "category": "ceny", "currency": "PLN"}
  ],
  "scenarios": [
    {
      "id": "pakiet-plus",
      "label": "Pakiet rozszerzony",
      "page": "projekt",
      "actions": [
        {"action": "click", "selector": "#zakladka-pakiety"},
        {"action": "select", "selector": "#pakiet", "value": "plus"},
        {"action": "wait_for", "selector": "#cena-plus"}
      ],
      "required": ["#cena-plus"]
    }
  ]
}
~~~

Obsługiwane działania: click, select, check, fill, wait_for i goto. Wartości fill muszą być niesekretne, np. przykładowy metraż kalkulatora. Nie umieszczaj danych klientów w konfiguracji. Wymagany field_selector bez wartości przerywa odczyt scenariusza; optional:true pozwala na brak rzeczywiście opcjonalnego pola.

Automatycznie wykonywane są rozpoznane zakładki, rozwijane sekcje, opcje, checkboxy dodatków i próba dodania do koszyka. Nowe kontrolki ujawnione w sekcji mogą tworzyć dalsze scenariusze. Limit zabezpieczający przed niekończącym się skanem jest jawnie raportowany. Kombinacje wariantów, pełne karuzele i etapy koszyka wymagają adapterów. Pełne pokrycie nie jest deklarowane na podstawie pojedynczych wyborów.

Koszyk używa osobnej sesji. Narzędzie nie ma scenariuszy składania zamówienia, danych klienta ani wysyłania zapytań. Dodatkowy guard blokuje rozpoznane końcowe przyciski. Nie dodawaj do konfiguracji działań finalizujących transakcję.

**Trwały stan i awarie**

Stan zawiera aktualne poprawne scenariusze, punkt odniesienia sprzed dnia raportu i wybór projektów. Obrazy mają nazwy z SHA-256. Lokalny zapis używa plików tymczasowych, fsync, atomowej podmiany i blokady procesu. Archiwa są sprawdzane pod kątem sum kontrolnych, niedozwolonych ścieżek i dowiązań.

Zdalnie są dwa rodzaje wydań: monitor-report-YYYY-MM-DD i monitor-state-v1. Stan jest zatwierdzany przez manifest przesłany jako ostatni, po sprawdzeniu zapisu raportu i archiwum stanu. Zachowywane są dwie ostatnie zatwierdzone wersje. Niedokończony upload nie zastępuje poprawnej historii.

Raport częściowy jest użytecznym wynikiem, lecz nie oznacza gotowości pełnego zakresu. Jeśli wszystkie domeny zakończą się błędem, CLI zwraca kod 2 po zapisaniu raportu. Błąd infrastruktury lub publikacji zwraca 1. Pozostałe przebiegi zwracają 0, a ich kompletność trzeba odczytać z pokrycie.json i podsumowania.

OCR jest wskazówką do oceny obrazu. Nie jest automatycznie uznawane za potwierdzoną cenę. Zmiana układu lub wyrenderowania strony może wymagać sprawdzenia przez człowieka. Brak poprzedniej sekcji jest zgłaszany do oceny i nie oznacza od razu usunięcia oferty.

**Retencja i usunięcie danych**

Raporty i dowody są zachowywane przez 180 dni. Niezmienione obrazy służące jedynie jako bieżący stan odniesienia nie są kopiowane do każdego dziennego archiwum. Poprzednie stany starsze niż retencja wygasają; kolejny odczyt tworzy nowy punkt odniesienia.

Sprzątanie zdalne dotyczy wyłącznie datowanych wydań danego namespace ze znacznikiem właściciela monitora. Nie usuwa innych wydań użytkownika. Najpierw można wyświetlić plan:

~~~sh
uv run pracownie cleanup --namespace monitor
uv run pracownie cleanup --namespace monitor --apply
~~~

Aby całkowicie zakończyć monitoring, wyłącz workflow w Actions. Własne wydania raportów i wydanie stanu można następnie usunąć w Releases; lokalnie usuń odpowiednie katalogi .monitor i raporty. Samo wyłączenie harmonogramu nie usuwa archiwum.

**Testy**

~~~sh
uv sync --frozen
uv run playwright install --with-deps chromium
uv run ruff check .
uv run pytest -q
~~~

Testy obejmują prawdziwą przeglądarkę na lokalnej stronie, ceny, gratisy, zakładki, warianty, zagnieżdżone opcje, awarię sklepu, ponowienie tego samego dnia, wizualne dowody, archiwum i odtworzenie w nowym katalogu. Mock API GitHuba sprawdza również przerwany commit oraz ochronę obcych wydań przed sprzątaniem.

Po uruchomieniu produkcyjnym potrzebna jest obserwacja 2–3 rzeczywistych dni, aby ocenić fałszywe alarmy i terminowość. Wyników tej obserwacji nie zastępują testy syntetyczne.

Zapis podstawowych stron tworzy checkpoint przed interakcjami. Zwykła awaria dalszego przetwarzania pozwala opublikować wynik częściowy; awaryjny artefakt Actions z raportem i stanem jest przechowywany 3 dni. Szczegóły napraw i pomiar kompresji: [review](docs/CODE_REVIEW_2026-10-21.md).

Codzienny e-mail z podsumowaniem i linkami wymaga konfiguracji dwóch sekretów Gmail. Instrukcja: [wysyłka e-mail](docs/EMAIL.md). Bez konfiguracji raport pozostaje dostępny w dashboardzie; system nie zgłasza wysłania wiadomości.

Osobny kontroler co godzinę nadrabia brakujące poranne skany i niewysłany e-mail. Po dodaniu sekretów Gmail podejmie wysyłkę automatycznie; nie wymaga potwierdzenia w rozmowie. Nie dubluje trwających zadań i ogranicza dodatkowe naprawy do dwóch dziennie.
