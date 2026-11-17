# Naprawa odczytów i priorytet cen — 17 listopada 2026

## Problem i zakres

Raport poranny: 175/224 odczytanych stron, 49 bez odczytu, pełne porównanie obu stron w 81/112 pracowni; tabela problemów zawierała 56 stron. Wiele działających witryn miało błąd „Pusta lub niekompletna strona”. Ceny były zbierane, lecz wykluczane z podsumowania komunikacji, co nie odpowiada aktualnemu priorytetowi użytkownika: ceny, kody, konkretne rabaty.

## Zmiany

- Oczekiwanie na rzeczywistą treść po DOMContentLoaded, maksymalnie 5 sekund. Pusty dokument z poprawnym kodem HTTP jest przejściowym błędem i podlega ponowieniu w nowym kontekście. Pustych zapisów i stron blokady nie zapisuje się jako poprawnej bazy.
- Próby zakończone błędem zapisują czas, adres, numer próby i szczegóły w `bledy-odczytu.json` w archiwum danej strony. Udane ponowienie nie usuwa dowodu wcześniejszego błędu.
- Domy dla nas: rzeczywisty przycisk zamknięcia okna `#spu-37605 .spu-close` przed obsługą cookies. Najpierw zachowywane są zrzut, tekst i adresy grafik z okna; nie usuwa się HTML ani nie klika przez zasłaniającą warstwę. Grafiki dostępne są w sekcji finansowej z datą; kwot i kodów z obrazu nie zastępuje się domysłem. Nowy zakres tej domeny otrzymuje osobną sygnaturę porównania.
- Na górze Markdown i HTML: zmiany cen tego samego projektu, różnica kwoty i procentowa oraz aktualne kody i konkretne rabaty. Pełna tabela świeżych cen i warunków jest pod linkiem `dashboard/ceny-i-rabaty.md`. Zapisane ceny częściowe, starsze i nieporównywalne nie stają się dzienną zmianą ceny. Bieżąca obecność komunikatu rabatowego nie jest nową kampanią.
- Diagnostyka może teraz wykonać pełny odczyt produkcyjnym skanerem (`probe_scan`), bez zmiany stanu ani wybranego projektu.

## Potwierdzone źródła problemów

- [Pierwsza diagnostyka](https://github.com/MateuszD0/Pracownie/actions/runs/44054099576): 1001studio, Artinex i Agrobisp zwracają czytelną treść; ArchBB HTTP 500.
- [Kontrola kolejnych witryn](https://github.com/MateuszD0/Pracownie/actions/runs/44054748953): kilkanaście domen z porannym błędem pustej strony odpowiada HTTP 200 i zwraca pełny tekst. ArchBB po HTTPS ma również niezgodny certyfikat. Arkusz `https://www.agrobisp.pl/styl/styl.css` zwraca HTTP 403 zarówno po HTTP, jak i HTTPS; nie pominięto tej usterki w ocenie jakości.
- [Próby skanerem produkcyjnym](https://github.com/MateuszD0/Pracownie/actions/runs/44055709548): poprawne odczyty 1001studio, Artinex, Domato i Domidea. W Domy dla nas log kliknięcia jednoznacznie wskazał, że `.spu-bg` zasłania przycisk cookies. HTML serwisu potwierdził rzeczywisty przycisk `.spu-close` i grafikę `black_week_2026_600x645.jpg`.

Zmiany nie rozwiązują awarii serwerów zewnętrznych, brakujących domen ani blokad dostępu. Zachowano stałe projekty i jasne rozróżnienie odczytu, jakości oraz dostępności porównania z wczoraj.

## Weryfikacja opublikowanego skanu

[Skan kontrolny](https://github.com/MateuszD0/Pracownie/actions/runs/44058302852) zakończył się powodzeniem. Zatwierdzony odczyt `2026-11-17T094707.191766-0000-c8b9daf8`: 201/224 stron zamiast 175, pełne porównanie obu stron 92/112 zamiast 81. Odzyskano 26 wcześniej nieodczytanych stron; tabela problemów zmalała z 56 do 34. Zachowano wszystkie dotychczas wybrane projekty i daty/jakość odczytów pracowni spoza zakresu naprawy.

W archiwum potwierdzono dwa zrzuty okna Domy dla nas, jego metadane w obu odczytach oraz 12 dzienników nieudanych prób. Świeże odczyty obu stron Domy dla nas są poprawne. Cena może być odczytana poprawnie, choć pełne porównanie komunikacji nadal wymaga zgodnego zapisu z wczoraj; nie dorobiono brakującej historii.

Sekcja finansowa zawiera 70 świeżych jednoznacznych cen, 69 par dzień do dnia oraz 40 komunikatów z konkretnym rabatem/kodem. Obecność tych komunikatów nie oznacza 40 nowych promocji. Kod E-domy `KUPTANIEJ` zachowano dosłownie wraz z cytatem o rabacie 10% i źródłem.

W końcowej kontroli wykryto pominiętą flagę `priceSpecification.valueAddedTaxIncluded="false"` w schemacie Domidea. Kwota 4593,50 jest ceną netto; widoczna na stronie kwota 5650 jest ceną brutto. Parser zachowuje odtąd jawne oznaczenia netto/brutto. Starsze pola i raporty są uzupełniane wyłącznie z zachowanego schematu tego samego odczytu, identyfikatora, kwoty i waluty; nie zakłada się stawki VAT, nie przelicza kwot i nie przenosi dzisiejszej flagi na wczorajszy zapis bez dowodu. Taka korekta metadanych nie jest zmianą oferty.

## Wynik końcowy

Po dodatkowym automatycznym ponowieniu i [końcowej publikacji](https://github.com/MateuszD0/Pracownie/actions/runs/44061656670) zweryfikowano edycję `2026-11-17T100918.576078-0000-format-ed1a02d3`:

| Miara | Przed naprawą | Wynik końcowy |
| --- | --- | --- |
| Odczytane strony | 175/224 | 204/224 |
| Pełne porównanie obu stron pracowni | 81/112 | 94/112 |
| Strony w tabeli problemów | 56 | 30 |
| Jednoznaczne świeże ceny | 65 | 72 |
| Porównywalne pary cen dzień do dnia | 64 | 71 |

Odzyskano 29 wcześniej nieodczytanych stron. Obie strony 1001studio i Domy dla nas mają jakość `ok`. Zachowano wybrane projekty oraz odczyty spoza kolejnych zakresów naprawy. W archiwum są dwa zrzuty okna Domy dla nas i dziewięć dzienników nieudanych prób z ostatniej edycji. Pierwsza publikacja dnia pozostaje o 06:12 czasu polskiego; uzupełnienia wykonano później.

Sprawdzono rzeczywiste pliki GitHuba `DASHBOARD.md` i `dashboard/ceny-i-rabaty.md`: zawierają kod `KUPTANIEJ`, datowane źródła rabatów, grafikę z okna oraz cenę Domidea `4 593,50 zł netto + VAT` i odpowiadającą jej wczorajszą cenę netto. Kwoty zachowano bez przeliczenia. Do porównania nie włączono cen o różnym lub niepotwierdzonym oznaczeniu VAT. Wszystkie [testy finalnej wersji](https://github.com/MateuszD0/Pracownie/actions/runs/44061180073) przeszły pomyślnie. Dodatkowe testy VAT i dotychczasowej obsługi cen: 56 zaliczonych; kontrola mobilna i komputerowa: brak błędów JavaScript i poziomego rozsuwania dokumentu.

Pozostaje 20 stron bez odczytu, 12 odczytów częściowych i 18 pracowni bez pełnego dziennego porównania. To różne miary. Wśród potwierdzonych zewnętrznych przyczyn są HTTP 500 w ArchBB, odmowa pobrania CSS w Agrobisp, blokady dostępu oraz nieaktualne adresy. Nie oznaczono ich jako poprawnych i nie uzupełniono brakującej historii domysłem.
