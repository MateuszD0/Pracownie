# Co jeszcze poprawić w monitoringu pracowni

Poranny raport ma pomagać odpowiedzieć na trzy pytania. Która pracownia zmieniła ofertę lub sposób jej przedstawienia? Czego dotyczy zmiana na stronie głównej albo na tej samej karcie projektu? Czy dowód wystarcza do rozmowy z partnerem lub do porównania własnej oferty?

## Trzy ustalenia z przeglądu

1. **Kod może pozostać ten sam, choć baner przekazuje inną obietnicę.** 20 listopada SEJ-PRO komunikowało obniżkę o 600 zł i kolejne 500 zł z kodem BLACK500. Dzień później pokazało jeden komunikat o oszczędności „nawet o 1100 zł” z tym samym kodem. W skrócie dnia można przeczytać obie wersje i sprawdzić dowód. Wniosek dotyczy sposobu prezentacji rabatu. Potwierdzenie zasad jego naliczania wymaga regulaminu albo wyraźnie opisanych warunków. [Dowód z 21 listopada](https://github.com/MateuszD0/Pracownie/blob/d72fec5b7de49bc9b80418517935b8e4cf89d44d/dashboard/zdarzenia-sej-propl.md#zdarzenie-acf68e0d8fe339b7)
2. **Kwota na karcie może oznaczać rabat.** Dla Archiportal wcześniejszy parser uznał element `-200 zł` za cenę zakupu. Dla projektu Dawid na KupProjekt odczytał `4,400zł` jako 4,40 zł. Poprawka rozpoznaje kwotę rabatu i separator tysięcy w widocznym tekście. Przebudowa weryfikuje wcześniejszą cenę względem zapisanej karty i czasu odczytu. [Tabela sprzed korekty](https://github.com/MateuszD0/Pracownie/blob/d72fec5b7de49bc9b80418517935b8e4cf89d44d/dashboard/ceny-i-rabaty.md)
3. **Niektóre alerty powstawały co dzień bez zmiany korzyści dla klienta.** W Domowych Klimatach baner dalej obiecywał 500 zł rabatu, a zmieniło się odliczanie. Porównanie pomija tykanie licznika i wykrywa zmianę kwoty, kodu lub daty zapisanej w tekście. Sama etykieta „% PROMOCJA” albo „CENA PROMOCYJNA” uzasadnia sprawdzenie szczegółów. [Raport sprzed korekty](https://github.com/MateuszD0/Pracownie/blob/d72fec5b7de49bc9b80418517935b8e4cf89d44d/DASHBOARD.md)

## Następne usprawnienia, w kolejności

| Kolejność | Co dobudować | Po czym poznać, że pomaga |
| --- | --- | --- |
| 1 | **Sprawdzenie tożsamości i przedmiotu oferty.** Oznaczyć domeny o niepotwierdzonej tożsamości i odróżniać cenę dokumentacji od ceny budowy domu. Zacząć od Biryło, gdzie wcześniejsza kontrola wskazała portfolio artystyczne, oraz od wariantów ofert zawierających wykonawstwo. | W każdej cenie użytej we wniosku można wskazać pracownię, ten sam projekt, przedmiot sprzedaży oraz oryginalne pole cenowe. [Ustalenia o domenach](../NAPRAWA_ODCZYTOW_2026-10-28.md) |
| 2 | **Oddzielić zmianę zasad promocji od zmiany hasła reklamowego.** Powiązać kod, wartość, próg zakupu, projekty objęte rabatem i termin z datowanym fragmentem regulaminu. Zachować osobny wpis o zmianie samego banera. | Dla zmian takich jak BLACK500 można odpowiedzieć, czy zmieniły się zasady zakupu, albo wskazać warunek, którego jeszcze nie potwierdzono. |
| 3 | **Mierzyć użyteczność alertów i przeoczenia.** Co tydzień ocenić małą próbę alertów partnerów i ręcznie sprawdzić kilka porównywalnych stron bez alertu. W analizowanym wydaniu odnotowano 0 ocen na 1523 zapisane alerty. | Widać liczbę ocenionych przypadków, które kategorie generują zbędne powiadomienia i jakie zmiany pominięto. [Jak zapisać ocenę](../OCENA_ALERTOW.md) |

**Termin dostarczenia.** Główny skan i dotychczasowe ponowienia zależą od harmonogramu GitHub Actions. Rozszerzenie okna odzyskania brakującego raportu do 21:00 zwiększa szansę zebrania danych tego samego dnia. Jeśli punktualność o 09:00 decyduje o przydatności raportu, następnym krokiem jest osobny harmonogram z uprawnieniem do uruchomienia workflow i sprawdzenie rzeczywistych godzin startu przez kilka dni. [Historia uruchomień](https://github.com/MateuszD0/Pracownie/actions/workflows/monitor.yml)
