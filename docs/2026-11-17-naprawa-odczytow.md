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
