# Czytelne i potwierdzane zmiany komunikacji

Zakres zatwierdzony przez użytkownika 9.11.2026: ograniczyć przypadkowe alerty, dopracować reguły odczytu problematycznych stron i podsumować zmiany jako „było → jest → dowód”. Strona główna i jeden zapisany projekt na pracownię pozostają stałym zakresem; ceny są drugorzędne.

## Rozwiązanie

1. Zachować źródłowe obserwacje, ale oznaczać kontekst: opinie, katalog/polecane projekty, artykuły, animacja tekstu i oferta. Kontekst wynika z DOM oraz zweryfikowanych reguł danej domeny. Sama obecność słowa „dodatkowo” albo roli nagłówka nie stanowi ważnej zmiany oferty. Promocji umieszczonej w katalogu na stronie głównej nie wykluczać tylko dlatego, że jest kartą projektu.
2. Drugim, ograniczonym czasowo odczytem potwierdzać kandydatów zmian komunikacji na stronach podstawowych. Niestabilne obserwacje trafiają do szczegółów, nieudana weryfikacja do „Do sprawdzenia”. Kontrola komunikacji nie potwierdza zakończenia promocji: od tego pozostaje istniejąca weryfikacja warunków w serwisie. Odczyty powtórne nie zmieniają dziennej bazy ani wybranego projektu.
3. Wyświetlać w Markdown i HTML jedno zdarzenie kampanii z tekstem przed/po, datami, miejscami wystąpienia, ważnością i stanem sprawdzenia oraz dowodem. Domyślnie maksymalnie pięć zdarzeń w każdej grupie współpracy; zachować filtrowanie, rozwijanie oraz historię. Techniczne braki nie są zmianami oferty.
4. Uzupełnić reguły konkretnych pracowni na podstawie zachowanych źródeł i kontroli przeglądarkowej. Nie oznaczać wszystkich interakcji jako zweryfikowanych po sprawdzeniu tylko jednej zakładki. Odmowy dostępu i nieaktualne domeny pozostają jawnymi brakami.

## Odbiór

- Opinie klientów i fragmenty animowanego napisu nie pojawiają się w ważnych alertach o ofercie, lecz pozostają w dzienniku źródłowym.
- Rzeczywista zmiana rabatu, dodatku, terminu albo głównego komunikatu nie znika przez filtr.
- Ponowny odczyt potwierdza treść albo jawnie wskazuje brak potwierdzenia; błąd serwera nie staje się „bez zmian”.
- Ta sama kampania na stronie głównej i projekcie ma jeden wiersz z oboma źródłami; różne warunki nie są scalane.
- Testy obejmują kontekst, stabilność, nieudane powtórzenie, renderowanie Markdown/HTML i obsługę na telefonie. Replay raportu 9.11 potwierdza odsunięcie zidentyfikowanych przypadkowych alertów.
- Po CI uruchomić skan na GitHubie i sprawdzić opublikowane dane oraz zachowanie istniejących projektów.

## Kolejność

Kontekst źródeł i testy → potwierdzanie komunikacji → podsumowanie i profile stron → replay oraz przegląd mobilny → CI, publikacja, skan kontrolny.

Niezależne wywołanie przed 08:00 pozostaje osobnym zadaniem infrastrukturalnym. Obecny cron GitHuba nie daje gwarancji terminu; ten zakres nie deklaruje usunięcia opóźnień wywołania.
