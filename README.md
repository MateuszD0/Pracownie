**Pracownie Monitor**

Codzienny monitoring strony głównej i jednej stałej karty projektu dla 65 pracowni. Narzędzie porównuje ceny, promocje, pakiety, dodatki, warunki zakupu, kontrolki sprzedażowe i wygląd stron. Wyniki po polsku trafiają do TXT oraz archiwum ze zrzutami przed/po.

Pełne wymagania: [plan wdrożenia](PLAN_WDROZENIA_MONITORINGU.md). Faktyczna dostępność domen: [inspekcja HTTP](docs/INSPEKCJA_DOMEN.md). Status walidacji: [wdrożenie](docs/WDROZENIE.md).

[Spis raportów dziennych](RAPORTY.md) · [Wybrane karty i źródła wyboru](docs/KARTY_PROJEKTOW.md).

Pierwsze pełne uruchomienia są opisane w [macierzy rzeczywistych odczytów](docs/POKRYCIE_DOMEN.md). Nie wszystkie domeny i interakcje są obecnie dostępne; raport wskazuje te braki jawnie.

Format wyniku pokazuje [syntetyczny przykład TXT](examples/raport-przykladowy.txt). Jest wygenerowany przez właściwy moduł raportów z fikcyjnych danych, bez skanowania rzeczywistej pracowni.

**Uruchomienie w GitHub Actions**

Workflow „Codzienny monitoring pracowni” działa z domyślnej gałęzi codziennie o 06:17 Europe/Warsaw, również w weekendy. Docelowa gotowość raportu to 08:00. GitHub może opóźnić lub pominąć harmonogram; nie jest to gwarancja terminu.

W zakładce Actions wybierz workflow i Run workflow:

- pilot: pięć domen, osobny stan i archiwum monitor-pilot;
- full: wszystkie 65 domen, stan i archiwum monitor.

Ponowienie tego samego dnia domyślnie naprawia brakujące odczyty. Poprawne scenariusze są odtwarzane z zatwierdzonego archiwum i zachowują rzeczywiste godziny odczytu. Zaznacz rescan, aby wykonać wszystkie odczyty ponownie. Każdego nowego dnia wszystkie domeny są odczytywane od początku.

Wbudowany GITHUB_TOKEN z uprawnieniem contents:write wystarcza do zapisywania Releases. Nie dodawaj osobistego tokenu do kodu. Workflow nie zmienia widoczności repozytorium. W publicznym repozytorium opublikowane raporty również są publiczne.

W Releases znajdziesz „Raport YYYY-MM-DD” z TXT i ZIP. ZIP zawiera folder raporty, plik dnia i podfolder dnia z dowodami. Pliki kontrolki.json pomagają dopracować adaptery. Zmiany są też dostępne maszynowo w zmiany.json, a zakres odczytu w pokrycie.json.

Plik RAPORTY.md w repozytorium jest automatycznym spisem dni z odnośnikami do TXT i ZIP. Pilotaż ma osobny indeks. Aktualizacja tego użytecznego spisu tworzy normalną aktywność repozytorium; sam publiczny harmonogram bez aktywności może zostać wyłączony przez GitHuba po 60 dniach. Indeks jest generowany, więc własne notatki zapisuj osobno.

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

config/sites.json zawiera wszystkie domeny. Projekt wybierany jest przy pierwszym poprawnym odczycie i utrwalany w stanie. Kolejność: oznaczenie bestsellera, sekcja najpopularniejszych, następnie promowany projekt. Podstawa wyboru i źródło są zapisane w wybrane-projekty.json. Ekspozycja na stronie nie dowodzi liczby sprzedaży.

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
