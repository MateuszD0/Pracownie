# Weryfikacja zmian monitoringu — 9 listopada 2026

Cel: czytelne zmiany komunikacji i oferty, z dowodem, na stronie głównej i tej samej karcie projektu każdej pracowni. Specyfikacja: [zakres wdrożenia](superpowers/specs/2026-11-09-monitoring-design.md).

## Wyniki kontroli danych

Porównano zapis sprzed wdrożenia (`2026-11-09T111746.700531-0000-3db36a14`) ze [skanem kontrolnym](https://github.com/MateuszD0/Pracownie/actions/runs/42640101099) o identyfikatorze `2026-11-09T150246.416503-0000-46a33537`.

| Kontrola | Wynik |
| --- | --- |
| Pracownie / podstawowe pozycje stron | 112 / 224, bez duplikatów |
| Stałe projekty | Wszystkie dotychczasowe adresy zachowane |
| Odczyty poza ośmioma naprawianymi domenami | Zachowane daty i jakość |
| Dzisiejsze odczyty | 206, w tym 16 częściowych; bez odczytu 18 |
| Pełne porównanie obu stron dzień do dnia | 95/112 pracowni |
| Powtórna kontrola komunikacji | 83 potwierdzone obserwacje tekstu, 22 niestabilne |
| Dokumenty kontroli / dodatkowe zrzuty | 4 dokumenty / 5 zrzutów w archiwum |
| Główne zdarzenia po poprawkach | 8, wszystkie z potwierdzeniem ponownym odczytem; brak wysokiego priorytetu |

83 potwierdzenia dotyczą fragmentów źródłowych, nie 83 osobnych zdarzeń biznesowych. Nie są pomiarem trafności ani kompletności wykrywania zmian. Skan kontrolny objął HexaGreen, Planujdom, Kowalscy, Artinex, Ecodomy, Domenadom, E-domy i Archetyp; pozostałe wyniki tego dnia zostały zachowane.

Na niezmienionych danych sprzed skanu replay ograniczył główne podsumowanie z 51 do 10 zdarzeń oraz wysokie priorytety z 47 do 0, zachowując wszystkie 1210 obserwacji źródłowych. Kolejny rzeczywisty odczyt dał 8 zdarzeń. Nie należy interpretować różnicy 51→8 jako zmiany aktywności pracowni: zmieniły się klasyfikacja i czas odczytu.

## Kontrole techniczne i prezentacji

- Nowa tabela: pracownia/miejsce, było, jest, ważność/weryfikacja, dowód. Daty i pełne teksty są dostępne w szczegółach, z podziałem na obie grupy współpracy.
- Kontrola przeglądarkowa szerokości 390 i 1280 px: brak poziomego przewijania i błędów JavaScript. Testy obejmują filtrowanie, reset, podział współpracy, rozwijanie i odnośniki do dowodów.
- Sprawdzona rzeczywista para publicznych zrzutów Domenadom: HTTP 200, 800×524 px, 44 074 i 49 134 bajty. Są to podglądy; pełne obrazy pozostają w archiwum.
- Testy chronią przed fałszywym potwierdzeniem zniknięcia starego tekstu, gdy nadal występuje w animacji, oraz przed ponownym wprowadzeniem niestabilnego tekstu przez drugi moduł analizy.
- Przebudowa zachowuje wynik weryfikacji i jego zrzut tylko dla tej samej obserwacji, adresu i dat.
- Historyczna kolejka zachowuje wpisy źródłowe. Po dopasowaniu aktualnego dowodu kontekstu oznacza jako pomocnicze dawną opinię HexaGreen i przycisk zgody Kowalskich (46→44 otwarte wpisy). Brak dopasowania, inny adres albo sama niestabilność nie zamykają rzeczywistego sygnału ofertowego.

Końcowe [pełne testy GitHuba](https://github.com/MateuszD0/Pracownie/actions/runs/42644131988) oraz [publikacja](https://github.com/MateuszD0/Pracownie/actions/runs/42644237633) zakończyły się pomyślnie. Zweryfikowano zatwierdzony raport `2026-11-09T152653.795323-0000-format-0e3baf3d` oraz rzeczywisty plik `DASHBOARD.md`: osiem potwierdzonych zdarzeń, zero bieżących zdarzeń w sekcji „Do sprawdzenia”, 44 otwarte historyczne wpisy kolejki i zachowane wszystkie 224 podstawowe pozycje stron. Powtórna publikacja układu nie zmieniła dat odczytów ani wyników dodatkowej kontroli.

Pięć dodatkowych zrzutów potwierdzających zajmuje łącznie 3 859 102 bajty. Całe archiwum raportu ma 370 242 911 bajtów; lekkie podglądy nie oznaczają równie małego pełnego archiwum.

## Ograniczenia pozostające po wdrożeniu

17 pracowni nadal nie ma pełnego porównania obu stron. Blokady dostępu, niepełne zasoby i nieaktualne adresy pozostają opisane jako braki; nie oznaczają braku zmian. Reguły kontekstu dla wybranych sekcji nie potwierdzają pełnego pokrycia wszystkich interakcji 112 serwisów.

To wdrożenie poprawia interpretację i prezentację danych. Nie rozwiązuje opóźnień wywoływania cron przez GitHub. Pierwsza publikacja 9 listopada nastąpiła o 11:12 czasu polskiego; odczyty kontrolne po 16:00 nie są porannym skanem ani realizacją terminu 08:00.
