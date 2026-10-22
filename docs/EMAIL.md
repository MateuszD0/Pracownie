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

Po skonfigurowaniu sekretów uruchom workflow ręcznie w Actions, wskazując dzień
istniejącego raportu (np. `2026-10-22`). Kolejne dni są wysyłane po publikacji skanu.
Poczta nie jest uruchamiana, jeżeli sam harmonogram GitHuba nie dostarczy zdarzenia
skanu. To powiadomienie po publikacji, a nie niezależny planista gwarantujący 08:00.

Potwierdzenie wysłania jest zapisywane w wydaniu raportu. Próba zapasowa i
przebudowa raportu nie wysyłają tego samego dnia ponownie. Potwierdzenie nie zawiera
adresu odbiorcy ani danych logowania. Przy utracie odpowiedzi SMTP po nadaniu
system zatrzymuje automatyczne ponowienie, aby uniknąć duplikatu. W takiej sytuacji
sprawdź skrzynkę oraz zasoby `email-YYYY-MM-DD-pending.json` / `-sent.json`.
Usunięcie potwierdzenia `pending` pozwala na kolejną próbę i wymaga wcześniejszego
sprawdzenia, czy wiadomość dotarła.
