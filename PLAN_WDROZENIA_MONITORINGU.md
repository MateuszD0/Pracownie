**Specyfikacja wdrożenia: codzienny monitoring zmian sprzedażowych na stronach pracowni projektowych**

Dokument jest samodzielnym zleceniem dla modelu implementującego. Zawiera pełny zakres, decyzje domyślne, kolejność prac i warunki odbioru. Nie wymaga dostępu do wcześniejszej rozmowy.

**1. Polecenie dla wykonawcy**

Zaimplementuj i zweryfikuj narzędzie opisane poniżej w repozytorium MateuszD0/Pracownie. Korzystaj z istniejącego checkoutu, sprawdź instrukcje AGENTS.md i stan plików. Zachowaj istniejące zmiany użytkownika. Nie twórz dodatkowego worktree bez wyraźnej potrzeby zgłoszonej przez użytkownika.

Przygotuj kod, konfigurację monitorowanych domen, testy, dokumentację oraz workflow GitHub Actions. Wykonaj dostępne testy i próbne uruchomienia. Nie kończ wyłącznie na stworzeniu szkieletu ani propozycji dalszych prac.

Podejmuj zwykłe decyzje techniczne samodzielnie. Pytaj wyłącznie o rzeczy rzeczywiście blokujące realizację, których nie można ustalić przez inspekcję. Nie proś użytkownika o ponowne podanie domen ani wybieranie projektów. Raportuj ograniczenia konkretnych stron i nie ukrywaj niepełnego pokrycia.

**2. Cel i ustalone wymagania**

- Monitoruj 65 domen wymienionych na końcu dokumentu.
- Dla każdej domeny sprawdzaj stronę główną i jedną stałą kartę projektu.
- Samodzielnie wybierz projekt najlepiej uzasadniony jako bestseller.
- Nie wyszukuj codziennie nowych projektów i nie monitoruj całego katalogu.
- Skanuj codziennie, również w soboty, niedziele i święta.
- Docelowo udostępniaj raport przed 08:00 czasu Europe/Warsaw.
- Porównuj zmiany istotne dla sprzedaży, również widoczne dopiero po interakcji.
- Wyniki i komunikaty dla użytkownika przygotuj po polsku.
- Głównym wynikiem jest dzienny plik TXT oraz folder z dowodami zmian.
- Zapewnij zrzuty „przed”, „po” i wizualne wskazanie zmienionego obszaru.
- Przechowuj raporty i dowody przez 180 dni.
- Uruchamiaj całość w chmurze GitHuba, bez zależności od włączonego MacBooka.
- Docelowy koszt wynosi 0 zł. Nie wymagaj płatnego API AI, płatnych proxy ani serwera.
- Użytkownik deklaruje, że monitorowane treści są publiczne.

Zachowaj obecną widoczność repozytorium. Jeśli trzeba utworzyć nowe, przyjmij prywatne. Nie zmieniaj repozytorium na publiczne jako automatycznego sposobu rozwiązania problemu limitów.

**3. Sprawdzenie wykonalności przed pełną implementacją**

Zweryfikuj aktualne limity i możliwości konta GitHub oraz uprawnienia do repozytorium. Nie zakładaj, że dostęp do odczytu Git oznacza możliwość zapisu przez API lub uruchamiania Actions.

Punkt odniesienia z dokumentacji sprawdzonej 19 października 2026:
- GitHub Free dla prywatnych repozytoriów obejmuje 2000 minut miesięcznie i 500 MB przestrzeni na artefakty Actions; wykorzystanie współdzielą inne repozytoria konta.
- Standardowe runnery dla publicznych repozytoriów są bezpłatne, ale upublicznienie kodu i wyników jest osobną decyzją użytkownika.
- Równoległe zadania zużywają sumę czasu wszystkich runnerów, nie tylko czas od rozpoczęcia do zakończenia całego skanu.
- Harmonogram Actions może się opóźnić lub zostać pominięty. 08:00 jest celem operacyjnym, a nie gwarantowaną godziną dostarczenia.
- Artefakty Actions domyślnie wygasają po 90 dniach; maksymalna retencja zależy od widoczności repozytorium.
- Workflow harmonogramu musi znajdować się na domyślnej gałęzi.
- Publiczne repozytoria mogą mieć wyłączony harmonogram po 60 dniach braku aktywności; samo wykonywanie workflow nie powinno być traktowane jako pewne zabezpieczenie.

Uruchom pilotaż na pięciu reprezentatywnych domenach, obejmując prostą kartę, sklep z wariantami, stronę dynamiczną, konfigurator i koszyk. Wybierz je po inspekcji. Mierz czas, liczbę odwiedzonych stanów, rozmiar archiwów i błędy z rzeczywistego runnera GitHub.

Cel budżetowy: do około 40 runner-minut dziennie, czyli 1240 minut przy 31 dniach. Uwzględnij instalację, pobieranie stanu, ponowienia i publikowanie. Nie obiecuj takiego wyniku przed pomiarami. Uwzględnij także zużycie innych workflow.

Jeśli pełny zakres nie mieści się w bezpłatnym limicie, najpierw zoptymalizuj implementację. Nie ograniczaj po cichu liczby domen, interakcji ani dni skanowania. Przedstaw zmierzony niedobór i dostępne warianty. Zmiana widoczności, płatności albo przeniesienie wykonania poza GitHub wymaga decyzji użytkownika.

**4. Rejestr domen i wybór projektów**

Dla każdej domeny przygotuj konfigurację zawierającą:
- identyfikator i pierwotną domenę;
- adres strony głównej oraz końcowy adres po przekierowaniach;
- nazwę i stały adres projektu;
- datę wyboru, podstawę wyboru i adres źródła;
- identyfikatory wariantów, sekcji i scenariuszy interakcji;
- reguły ekstrakcji danych, obsługi cookies i filtracji elementów zmiennych;
- oczekiwane elementy pozwalające ocenić, czy odczyt się udał;
- obsługiwane i niedostępne elementy monitorowania.

Kolejność wyboru projektu:
1. Pierwsze miejsce w jawnym rankingu sprzedaży, jeśli istnieje.
2. Oznaczenie „bestseller” lub wyróżnienie w sekcji bestsellerów.
3. Pierwszy projekt w sekcji najpopularniejszych.
4. Wyraźnie promowany projekt na stronie głównej.

Przy równorzędnych kandydatach zastosuj powtarzalną regułę, np. kolejność w rankingu, następnie pozycję w sekcji. Zapisz dowód wyboru. Nie przedstawiaj samej ekspozycji jako potwierdzenia rzeczywistej sprzedaży.

Projekt pozostaje stały, nawet jeśli zmieni się aktualna lista bestsellerów. Jeśli karta zniknie, raportuj problem. Nie wybieraj zastępstwa automatycznie. Jeżeli domena nie ma kart projektów albo nie pozwala ustalić projektu, zachowaj ją w rejestrze, monitoruj dostępny zakres i oznacz brak.

**5. Zakres monitorowanych informacji sprzedażowych**

Porównuj wszystkie dostępne informacje z poniższych kategorii:

| Kategoria | Zakres |
| --- | --- |
| Ceny | Cena podstawowa i promocyjna, najniższa cena z 30 dni, waluta, VAT jeśli podano, ceny wariantów, dopłaty, cena końcowa. |
| Promocje | Rabaty, kody, gratisy, terminy, progi, ograniczenia, wyłączenia, warunki łączenia ofert. |
| Pakiety | Elementy zawarte w cenie, dokumentacja papierowa lub elektroniczna, liczba egzemplarzy, różnice między pakietami. |
| Dodatki i usługi | Kosztorysy, instalacje, adaptacja, zgoda na zmiany, konsultacje, materiały, usługi partnerskie i ich ceny. |
| Warunki zakupu | Dostępność, termin realizacji, dostawa, jej koszt i bezpłatne progi, płatności, raty, zwroty, gwarancje, wsparcie. |
| Funkcjonalności | Nowe lub usunięte konfiguratory, kalkulatory, personalizacja, wybór wariantu, porównanie i istotne działania zakupowe. |
| Komunikacja | Banery, nagłówki, wezwania do zakupu, eksponowane opinie, argumenty sprzedażowe i komunikaty o ograniczonej ofercie. |
| Parametry oferty | Zmiany parametrów wybranego projektu wpływające na ofertę, np. powierzchnia, wariant technologii, garaż lub wersja lustrzana. |

Raportuj dodanie, zmianę i usunięcie informacji. Dla cen podawaj starą i nową wartość, różnicę kwotową oraz procentową, jeśli cena poprzednia jest dodatnia. Porównuj ten sam wariant, tę samą walutę i tę samą podstawę ceny. Nie sumuj automatycznie wartości gratisów i rabatów w „oszczędność”, jeżeli warunki ich łączenia nie są potwierdzone.

**6. Interakcje i granice pełnego pokrycia**

Użyj prawdziwej przeglądarki z JavaScript. Dla każdej strony zdefiniuj i wykonaj scenariusze:
- przewinięcie całej strony i załadowanie elementów opóźnionych;
- otwarcie zakładek i sekcji rozwijanych;
- przejrzenie wszystkich istotnych slajdów promocyjnych;
- odczyt dostępnych pakietów, wariantów i dodatków;
- uruchomienie konfiguratora lub kalkulatora, gdy ujawnia informacje sprzedażowe;
- sprawdzenie koszyka w odizolowanej sesji, jeśli pokazuje dodatkowe koszty lub warunki.

Sprawdzaj wszystkie dostępne opcje i znane zależności między nimi. Dla konfiguratorów unikaj bezmyślnego iloczynu wszystkich kombinacji: odwzoruj reguły i dobierz scenariusze pokrywające odrębne ceny oraz warunki. Udokumentuj nieprzetestowane kombinacje. Nie nazywaj ograniczonej próbki pełnym sprawdzeniem.

Koszyk obejmuje informacje dostępne bez danych klienta, zakładania konta, wysyłania zapytania i składania zamówienia. Wprowadzanie kodu promocyjnego znalezionego na stronie jest dopuszczalne, jeśli jedynie przelicza testowy koszyk. Scenariusze zaczynaj od czystej sesji, żeby dodatki i ilości nie kumulowały się między testami.

Dla nowych przycisków lub kontrolek zapisz ich pojawienie się, etykietę i kontekst. Nie uruchamiaj dowolnego nowego działania automatycznie; jego działanie może wymagać dodania scenariusza. Rozróżniaj „pojawiła się nowa opcja” od „zweryfikowano jej działanie”.

**7. Zalecana architektura**

Wykorzystaj Python, Playwright i Chromium na standardowym runnerze Linux. Użyj bibliotek o otwartym kodzie do przetwarzania obrazów, a OCR dodaj tam, gdzie tekst znajduje się w banerach. Nie wymagaj usługi LLM do codziennej pracy.

Podziel rozwiązanie na:
- rejestr domen i adaptery stron;
- przeglądarkę oraz wykonanie scenariuszy;
- ekstrakcję danych i ocenę poprawności odczytu;
- normalizację i porównywanie;
- zapis dowodów;
- generator raportu TXT i danych JSON;
- trwały magazyn stanu i archiwum;
- harmonogram, ponowienia i sprzątanie.

Wspólny adapter może obsługiwać podobne strony, ale każda domena musi mieć zweryfikowany wynik. Sam ogólny zrzut tekstu całej strony nie wystarczy do spełnienia wymagań.

Rozdziel logikę skanowania od GitHuba, aby testy i ręczne uruchomienie działały również lokalnie. Nie buduj panelu WWW, bazy serwerowej, systemu kont, e-maili ani integracji komunikatorów: nie są wymagane.

Zależności instaluj z pliku blokady. Przypnij wersję przeglądarki i istotnych narzędzi. Zmiana wersji renderera nie może zostać błędnie opisana jako zmiana monitorowanej strony.

**8. Porównywanie i jakość danych**

Zapisuj ustrukturyzowane wartości, znormalizowany tekst, źródłowy fragment i obraz. Każda zmiana musi zawierać domenę, stronę, scenariusz, kategorię, wartości przed i po, obie daty, adres URL i ścieżki dowodów.

Ustal stałe: rozmiar okna, język pl-PL, strefę czasową, obsługę cookies, warunki zakończenia ładowania i kolejność interakcji. Wyłącz animacje, czekaj na fonty oraz obrazy i stosuj przewijanie dla treści ładowanych później.

Ignoruj identyfikatory sesji, techniczne znaczniki czasu, rotację przypadkowych rekomendacji, migające kursory i bieżące sekundy liczników. Zachowuj daty końca promocji, ceny i warunki. Filtry muszą być precyzyjne: ogólne usuwanie wszystkich liczb jest niedopuszczalne.

Wykrywaj nowe sekcje również poza dotychczas wskazanymi polami. Dopasowuj istniejące oferty po identyfikatorze lub znaczeniu etykiety, nie wyłącznie po pozycji na stronie.

Błąd odczytu, CAPTCHA, blokada, niedoładowany fragment i pusta odpowiedź nie oznaczają usunięcia oferty. Usunięcie wolno zgłosić dopiero po potwierdzeniu poprawnego załadowania właściwej sekcji. Zmianę selektorów traktuj jako możliwy błąd adaptera.

OCR i analiza obrazu mogą wskazywać zmianę wymagającą oceny. Oznacz niepewność; nie generuj pewnego opisu ceny z nieczytelnego obrazu. Po przesunięciu układu strony stosuj porównania sekcji lub wyrównanie obrazów, aby nie oznaczać całej strony jako zmienionej.

**9. Stan, daty i odporność na ponowienia**

Pierwszy poprawny odczyt tworzy punkt odniesienia, bez fikcyjnych różnic historycznych. Każdy następny porównuj z ostatnim poprawnym stanem danej strony i scenariusza, niekoniecznie z poprzednią datą kalendarzową.

Zapisuj czas rzeczywistego odczytu w UTC oraz lokalną datę raportu Europe/Warsaw. Przy przerwie w skanowaniu pokaż rzeczywisty okres porównania. Skan dzienny nie wykryje zmian, które pojawiły się i zniknęły między skanami.

Dla każdej części stosuj rozróżnialne statusy: punkt odniesienia, zmiana, bez zmian, błąd odczytu, częściowe sprawdzenie, niedostępna funkcja, wymaga oceny.

GitHub uruchamia nowe środowisko przy każdym skanie. Przed rozpoczęciem pobierz trwały stan; po zakończeniu zapisz go poza dyskiem runnera. Cache Actions traktuj wyłącznie jako przyspieszenie instalacji, nie jako jedyne źródło historii.

Aktualizuj tylko poprawnie odczytane części. Nie nadpisuj poprzedniego stanu błędem. Stan starszy niż 180 dni usuń; kolejny odczyt tworzy nowy punkt odniesienia.

Dla ponownego uruchomienia tego samego dnia:
- zachowaj punkt odniesienia sprzed tego dnia;
- nie porównuj ponownego skanu wyłącznie z wcześniejszym skanem tego samego dnia;
- utrzymuj jeden aktualny raport dzienny z datą aktualizacji;
- nie dopisuj drugi raz tych samych różnic;
- nie uruchamiaj dwóch zapisów stanu równocześnie.

Powiąż raport, dowody i stan identyfikatorem uruchomienia oraz manifestem z sumami kontrolnymi. Najpierw zapisz komplet wyników i zweryfikuj go, potem przestaw wskaźnik aktualnego stanu. Przerwany zapis nie może uszkodzić poprzedniego kompletu.

**10. Zrzuty i retencja**

Przy każdym poprawnym skanie wykonaj obrazy potrzebne do następnego porównania, także jeśli nie wykryto zmiany. Obrazy „przed” muszą pochodzić z rzeczywistego wcześniejszego skanu tego samego scenariusza.

Dla wykrytej zmiany zapisz:
- zrzut wcześniejszy;
- zrzut aktualny;
- obraz z zaznaczeniem zmienionego obszaru;
- zbliżenie sekcji, jeśli poprawia czytelność;
- pełny kontekst strony lub scenariusza.

Nie wykonuj „przed” przez ponowne odwiedzenie strony po stwierdzeniu zmiany. Nie uzależniaj utworzenia obrazu bazowego od wcześniejszego wykrycia różnicy.

Archiwizuj przez 180 dni raporty, dane zmian i ich dowody. Dodatkowo przechowuj bieżący komplet odniesienia oraz wersję potrzebną do bezpiecznego ponowienia dzisiejszego skanu. Nie archiwizuj codziennie 180 kopii identycznych pełnych zestawów bazowych.

Zmierz rozmiary plików. Dobierz kompresję zachowującą czytelność cen i drobnego tekstu. Pojedyncza sekcja rozwinięta w przeglądarce musi mieć dowód w tym właśnie stanie, nie wyłącznie zrzut zamkniętej karty.

**11. Wyniki i magazyn na GitHubie**

Użytkownik ma otrzymać strukturę:

~~~text
raporty/
├── 2026-10-20.txt
├── 2026-10-20/
│   ├── zmiany.json
│   ├── manifest.json
│   └── przyklad.pl/
│       ├── glowna/
│       │   ├── przed.png
│       │   ├── po.png
│       │   └── roznice.png
│       └── projekt/
│           └── pakiet-podstawowy/
│               ├── przed.png
│               ├── po.png
│               └── roznice.png
└── 2026-10-21.txt
~~~

Twórz pojedynczy plik TXT na dzień. Nie dopisuj wszystkich dni do jednego nieskończenie rosnącego pliku.

Proponowany magazyn: GitHub Releases z prefiksem nazw przeznaczonym wyłącznie dla tego narzędzia. Dzienne wydanie zawiera TXT do pobrania oraz ZIP zachowujący powyższy układ. Opis wydania pokazuje podsumowanie i pozwala znaleźć wyniki po dacie.

Stan odniesienia przechowuj osobno od dziennych dowodów, w wersjonowanych plikach stanu. Zachowuj niezbędne wersje do odtwarzania i ponowień, a pozostałe usuwaj po potwierdzonym zapisie. Nie dołączaj całego nowego stanu odniesienia do każdego archiwum przechowywanego przez 180 dni.

Przed wyborem magazynu potwierdź aktualne limity API i plików Releases oraz dostępne uprawnienia. Nie przedstawiaj go jako bezwarunkowo nieograniczonego magazynu. Jeśli nie nadaje się do zmierzonego obciążenia, opisz problem i zaproponuj bezpłatną alternatywę wymagającą możliwie małej konfiguracji.

Nie commituj zrzutów ani dużych archiwów do historii kodu. Nie używaj artefaktów Actions jako jedynego archiwum 180 dni. Małe pliki diagnostyczne Actions mogą mieć krótką retencję.

Sprzątanie obejmuje wyłącznie wydania i pliki utworzone przez narzędzie oraz starsze niż ustawiona retencja. Nie usuwaj wydań kodu użytkownika. Sprawdź usuwanie w trybie próbnym i testowym przed włączeniem go dla wyników.

**12. Zawartość raportu TXT**

Kolejność:
1. Data raportu, początek i koniec skanowania oraz status kompletności.
2. Liczba domen sprawdzonych w pełni, częściowo i zakończonych błędem.
3. Najważniejsze zmiany cen, promocji i zawartości oferty.
4. Szczegóły według domen, oddzielnie strona główna i karta projektu.
5. Domeny bez wykrytych zmian, wyłącznie w poprawnie sprawdzonym zakresie.
6. Błędy, brakujące scenariusze i elementy wymagające oceny.
7. Czas wykonania oraz podstawowe informacje o rozmiarze archiwum.

Każdy wpis zmiany zawiera konkretny opis, wartości przed i po, wariant, daty, adres źródła i względne ścieżki do dowodów. TXT ma być czytelny po pobraniu ZIP; JSON służy przetwarzaniu, a nie zastępuje raportu.

Przykład fikcyjny:

~~~text
DOMENA: przyklad.pl
PROJEKT: Dom Przykładowy
SCENARIUSZ: pakiet podstawowy
PORÓWNANIE: 2026-10-19 06:24 → 2026-10-20 06:22, Europe/Warsaw

CENA PROMOCYJNA:
4590 zł → 4290 zł
Spadek o 300 zł (6,54%).

DODATKI:
Kosztorys dodano do pakietu bez dopłaty.
Poprzednio widniał jako dodatek za 150 zł.

ŹRÓDŁO: https://przyklad.pl/projekt
DOWODY: 2026-10-20/przyklad.pl/projekt/pakiet-podstawowy/...
~~~

Nie powielaj tej samej zmiany w wielu miejscach podsumowania. W razie rozbieżności między ceną na karcie a ceną w koszyku pokaż obie obserwacje z kontekstem.

**13. Workflow GitHub Actions**

Zapewnij uruchomienie ręczne i harmonogram codzienny. Wstępny start: 06:17 Europe/Warsaw, do korekty po pomiarach. Użyj obsługi stref czasowych dostępnej w aktualnej składni GitHuba; jeśli nie jest dostępna, zastosuj poprawną obsługę UTC i zmiany czasu, bez podwójnego pełnego skanu dziennie.

W jednym cyklu:
1. Pobierz kod i zależności z pliku blokady.
2. Pobierz oraz sprawdź stan odniesienia.
3. Wykonaj skany z ograniczoną współbieżnością między domenami.
4. Ponów wyłącznie błędy przejściowe, z limitem i odstępem.
5. Zbuduj raport, także gdy część domen zawiodła.
6. Opublikuj i zweryfikuj wyniki oraz stan.
7. Usuń własne dane przekraczające retencję.
8. Zapisz podsumowanie przebiegu w Actions.

Skonfiguruj timeouty, blokadę współbieżnego zapisu i limity ponowień. Dodatkowe sprawdzenie poranne może wznowić nieukończony raport, lecz nie powinno powtarzać poprawnie zakończonego pełnego skanu.

Użyj wbudowanego GITHUB_TOKEN z minimalnymi uprawnieniami wymaganymi do Releases, zamiast domyślnie wymagać osobistego tokenu. Nie zapisuj tokenów w repozytorium, raportach ani logach. Sprawdź uprawnienia odczytem przed żądaniem dodatkowej konfiguracji.

Jeśli skan działa, ale część stron jest niedostępna, opublikuj raport częściowy. Jeśli sam workflow nie wystartował, nie da się zagwarantować powstania raportu tym samym mechanizmem. Nie obiecuj niezależnego alarmowania bez osobnego monitora.

Oznacz spóźniony raport rzeczywistą godziną gotowości. Nie wpisuj fikcyjnej godziny 08:00. Stałej punktualności nie można zagwarantować samym GitHub Actions.

**14. Testy i kryteria odbioru**

Testy deterministyczne na lokalnych przykładowych stronach muszą obejmować:
- zmianę ceny i obliczenie różnicy;
- pojawienie się i zakończenie promocji;
- dodanie, zmianę ceny i usunięcie dodatku;
- poprawne rozróżnienie wariantów;
- informacje dostępne po otwarciu zakładki i zmianie opcji;
- nowy baner obrazkowy i niepewny odczyt OCR;
- brak zmian oraz ignorowanie elementów dynamicznych;
- błędny odczyt, który nie usuwa poprzedniej oferty;
- odtworzenie stanu w nowym środowisku;
- ponowienie tego samego dnia bez utraty porównania;
- przerwany zapis i zachowanie poprzedniego kompletu;
- retencję przy kontrolowanej dacie i bez usuwania obcych danych;
- strefę Europe/Warsaw, zmianę czasu oraz wykonanie w weekend.

Wykonaj testy funkcjonalne w prawdziwej przeglądarce i próby z GitHub Actions. Dwa niezależne uruchomienia muszą potwierdzić zachowanie stanu między świeżymi runnerami. Jeśli nie masz uprawnień do ich uruchomienia, zakończ dostępne prace i oznacz tę walidację jako niewykonaną.

Każda z 65 domen musi wystąpić w rejestrze i raporcie. Dla każdej potwierdź działające odczyty albo podaj konkretny brak. Nie uznawaj pełnego zakresu za gotowy, jeśli wymagane scenariusze pozostają niesprawdzone.

Warunki odbioru:
- wybór projektów ma zapisane uzasadnienie;
- raport TXT i dowody można pobrać oraz powiązać z opisanymi zmianami;
- zrzuty „przed” pochodzą z poprzednich odczytów;
- awarie nie generują fikcyjnych różnic;
- powtórny skan nie gubi historii;
- zmierzono koszt czasowy i wielkość danych;
- nie wymaga się płatnych usług w wybranym wariancie;
- harmonogram i retencja są skonfigurowane;
- README opisuje obsługę, ograniczenia i sposób usunięcia danych.

Po technicznym wdrożeniu zaplanuj obserwację pierwszych 2–3 rzeczywistych dni. Jest to osobny etap potwierdzenia stabilności: nie udawaj, że został wykonany, jeśli te dni jeszcze nie upłynęły. Nie blokuj przygotowania kodu i testów czekaniem przez dobę.

**15. Etapy realizacji i przekazanie**

A. Inspekcja repozytorium, uprawnień i limitów; podstawowy projekt oraz pięć domen pilotażowych.
B. Pilotaż w chmurze; pomiar czasu, rozmiaru, dostępności i zakresu interakcji.
C. Implementacja porównywania, dowodów, trwałego stanu i raportów.
D. Rozszerzenie konfiguracji oraz adapterów na wszystkie domeny.
E. Workflow, bezpieczne publikowanie, retencja i dokumentacja.
F. Testy odbiorowe i jawna lista pozostałych ograniczeń.
G. Obserwacja pierwszych dni pracy i poprawki reguł na podstawie rzeczywistych wyników.

Na koniec podaj: co wdrożono, jakie testy faktycznie wykonano, przykładowy raport, listę pokrycia domen, zmierzone zużycie minut i miejsca, lokalizację wyników oraz dokładne czynności użytkownika, jeśli cokolwiek pozostaje zablokowane.

Nie twórz dodatkowych funkcji poza zakresem tylko dlatego, że byłyby możliwe.

**16. Pełna lista domen**

~~~text
1001studio.pl
alexanderstudio.pl
archand.pl
archdesign.pl
archdom.pl
archeton.pl
archetyp.pl
archi-projekt.com.pl
archido.pl
archipelag.pl
archstodola.pl
dobredomy.pl
dom-projekt.pl
domdlaciebie.com.pl
domenadom.pl
dominanta.pl
domoweklimaty.pl
dompasja.pl
dompp.pl
domydlanas.pl
domywstylu.pl
domyzweranda.pl
e-domy.pl
eg-domy.pl
extradom.pl
galeriadomow.pl
hbstudio.pl
hexagreen.pl
housecollection.pl
kbprojekt.pl
klimatdrewna.pl
kreatywnedomy.pl
kreodom.pl
lipinscy.pl
lk-projekt.pl
moj-dom-projekty.pl
mtmstyl.com.pl
myhome.eco
nowoczesne-projektydomow.pl
ototwojdom.pl
penthus.pl
pioroarchitekci.pl
planujdom.pl
pollio.pl
polskiedomki.pl
postawdom24.pl
praktyczneprojekty.pl
pro-arte.pl
profesjonalne-projekty-domow.pl
projektdomudo100m2.pl
projektstodola.pl
projektydomow.redcart.pl
projektygebala.com
projektyka.pl
projektyszkieletowe.pl
projektyzwizja.pl
sej-pro.pl
skahus.pl
slonecznedomy.pl
sprytnaoaza.pl
studioatrium.pl
studiokrajobrazy.pl
teaprojekt.pl
uarchitekta.pl
zbudujsamdom.pl
~~~

**17. Dokumentacja do sprawdzenia przy wdrożeniu**

- GitHub Actions — rozliczenia: https://docs.github.com/en/billing/concepts/product-billing/github-actions
- Harmonogram i ograniczenia zdarzenia schedule: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- Ograniczenia Actions: https://docs.github.com/en/actions/reference/limits
- GitHub Releases: https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
- Playwright dla Pythona: https://playwright.dev/python/docs/intro

Aktualna dokumentacja i rzeczywiste ustawienia konta mają pierwszeństwo przed liczbowymi założeniami kosztowymi tego dokumentu. Ewentualna zmiana limitów nie jest zgodą na zwiększenie budżetu użytkownika.

