# Codzienny e-mail z porównaniem

Workflow „E-mail z dziennym porównaniem” uruchamia się po udanym zakończeniu
„Codzienny monitoring pracowni”. Wysyła krótkie podsumowanie dnia: najważniejsze
zmiany biznesowe, wybrane zmiany graficzne, liczbę odczytów i brakujące strony.
Wiadomość zawiera link do dashboardu oraz plików ze zrzutami, bez dużych załączników.

## Uruchomienie przez Gmail

W [sekretach Actions](https://github.com/MateuszD0/Pracownie/settings/secrets/actions)
dodaj dwa **repository secrets**:

- `REPORT_EMAIL_TO`: adres odbiorcy raportów.
- `SMTP_PASSWORD`: hasło aplikacji konta Gmail wysyłającego wiadomości.

Domyślnie nadawcą jest ten sam adres Gmail co odbiorca. Jeżeli wysyła inne konto,
dodaj również sekret `SMTP_USERNAME` z adresem tego konta. Hasło aplikacji tworzy
się w [ustawieniach konta Google](https://myaccount.google.com/apppasswords), po
włączeniu weryfikacji dwuetapowej. Zapisz je bez spacji. Nie dodawaj zwykłego hasła
do Gmaila, nie umieszczaj haseł w kodzie ani w rozmowie.

Domyślne połączenie to `smtp.gmail.com:587` z wymaganym STARTTLS i weryfikacją
certyfikatu. Inny dostawca może być wskazany zmiennymi Actions `SMTP_HOST`
i `SMTP_PORT`, przy zachowaniu STARTTLS.

Bez tych sekretów skan nadal publikuje dashboard. Workflow poczty wyświetla
jednoznaczną informację, że wysyłka wymaga konfiguracji; nie zgłasza wysłania.
Do ustawień sekretów potrzebne są osobne uprawnienia GitHuba. Sam dostęp do kodu
oraz uruchamiania Actions nie wystarcza.

## Pierwsza wysyłka i ponowienia

Po skonfigurowaniu sekretów nie trzeba potwierdzać tego w rozmowie ani uruchamiać
poczty ręcznie. Dodatkowy workflow „Automatyczne nadrabianie raportu i poczty”
sprawdza stan co godzinę, w 41. minucie. Gdy konfiguracja jest gotowa i nie ma
potwierdzenia wysłania dzisiejszego raportu, zleca wysyłkę. Ręczna wysyłka jest
również dostępna w Actions: wskaż dzień bieżącego, najnowszego raportu
(np. `2026-10-22`).

Kontroler nadrabia też brak skanu od 05:17 do 12:00 czasu polskiego: uruchamia
pełny skan z wznowieniem albo naprawia tylko wskazane brakujące domeny. Nie
uruchamia drugiego producenta podczas trwającego skanu lub przebudowy; pomija
trwałe blokady i ogranicza dodatkowe próby do dwóch dziennie. Opcjonalne Pages
oczekujące na zatwierdzenie nie blokują raportów. Samo zlecenie e-maila nie jest
potwierdzeniem wysłania — potrzebna jest odpowiedź SMTP i potwierdzenie w wydaniu.

Kontroler ma osobny harmonogram Actions, więc pomaga po pominięciu pojedynczych
porannych wywołań. Nadal korzysta z planisty GitHuba i nie gwarantuje terminu przy
pominięciu wszystkich zdarzeń cron lub awarii całej usługi. Pełna niezależność
wymagałaby planisty poza GitHubem.

Potwierdzenie wysłania jest zapisywane w wydaniu raportu. Próba zapasowa i
przebudowa raportu nie wysyłają tego samego dnia ponownie. Potwierdzenie nie zawiera
adresu odbiorcy ani danych logowania. Przy utracie odpowiedzi SMTP po nadaniu
system zatrzymuje automatyczne ponowienie, aby uniknąć duplikatu. W takiej sytuacji
sprawdź skrzynkę oraz zasoby `email-YYYY-MM-DD-pending.json` / `-sent.json`.
Usunięcie potwierdzenia `pending` pozwala na kolejną próbę i wymaga wcześniejszego
sprawdzenia, czy wiadomość dotarła.
