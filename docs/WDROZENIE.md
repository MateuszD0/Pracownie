**Status wdrożenia**

Stan początkowy: 19 października 2026. Ten dokument zostanie zaktualizowany wynikami uruchomień GitHub Actions.

- Implementacja skanera, historii, porównań, raportów i magazynu Releases jest dostępna.
- Rejestr zawiera 65 domen; ich pełna inspekcja przeglądarkowa pozostaje osobnym warunkiem odbioru.
- Inspekcja HTTP: 60 odpowiedzi 200, 5 błędów lub timeoutów; szczegóły w INSPEKCJA_DOMEN.md.
- Testy lokalne obejmują kontrolowane strony w prawdziwym Chromium oraz symulowane API GitHuba.
- Lokalny pilotaż rzeczywistych stron zatrzymał się na braku zaufania Chromium do certyfikatu proxy środowiska. TLS nie został wyłączony i magazyn zaufania nie został zmieniony.
- Pełne działanie na runnerach GitHuba, zużycie minut oraz przechowywanie wyników między rzeczywistymi uruchomieniami wymagają weryfikacji.
- Obserwacja 2–3 dni nie została jeszcze wykonana.

Brak pełnej inspekcji domen jest jawnie oznaczany w raportach. Sam HTTP 200 nie stanowi potwierdzenia odczytu cen, bestsellerów, konfiguratorów ani koszyków.
