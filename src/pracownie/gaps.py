"""Explain missing comparisons using observed reads, not assumed availability."""
from __future__ import annotations

from datetime import date, timedelta


def page_gap(page: dict, day: str) -> dict:
    communication = page.get('communication', {})
    reason = page.get('error_text') or communication.get('reason') or communication.get('label') or 'Brak porównywalnej pary zapisów'
    current = page.get('current_read', False)
    category = 'repair'
    status = 'Odczyt nieudany'
    action = 'Ponowić odczyt i sprawdzić przyczynę, jeśli problem się utrzyma.'
    if current:
        if communication.get('ready') and communication.get('text_only') and not page.get('compared_at'):
            category, status = 'history', 'Zapisano tekst; grafika ograniczona'
            reason = 'Brak zewnętrznej czcionki ogranicza ocenę wyglądu. Tekst zapisano poprawnie; brakuje wcześniejszego porównywalnego zapisu.'
            action = 'Porównanie tekstu możliwe po kolejnym poprawnym skanie. Ograniczenie grafiki pozostaje jawne.'
        elif page.get('data_quality') == 'partial' or communication.get('status') == 'partial':
            status = 'Odczyt częściowy'
            notes = page.get('quality_notes', [])
            reason = '; '.join(notes) if notes else reason
            action = 'Naprawić niepełny odczyt; dostępne fragmenty nie wystarczają do oceny całej strony.'
        elif not page.get('compared_at') and communication.get('ready'):
            category, status = 'history', 'Zapisano pierwszy pełny odczyt'
            reason = 'Brak wcześniejszego poprawnego zapisu tej strony.'
            action = 'Porównanie możliwe po poprawnym skanie ' + (date.fromisoformat(day) + timedelta(days=1)).isoformat() + '.'
        elif page.get('gap_days', 0) and page['gap_days'] > 1:
            category, status = 'history', 'Dzisiejszy odczyt działa; luka historii'
            reason = f"Poprzedni zapis pochodzi sprzed {page['gap_days']} dni."
            action = 'Zachowano dzisiejszy zapis. Do porównania dzień do dnia potrzebny jest kolejny poprawny skan.'
        else:
            status = 'Zapisy nieporównywalne'
            action = 'Sprawdzić zgodność adresu i zakresu odczytu; nie przypisywać różnic ofercie.'
    elif communication.get('status') == 'pending':
        status, action = 'Oczekuje na pierwszy skan', 'Włączyć stronę do najbliższego skanu.'
    elif 'karty projektu' in reason:
        status, action = 'Nie wybrano stałej karty', 'Zweryfikować pojedynczy projekt w katalogu pracowni i zapisać jego stały adres.'
    elif '403' in reason:
        status, action = 'Dostęp odrzucony przez serwis', 'Potrzebne dopuszczenie odczytu przez właściciela witryny lub inne udostępnione źródło.'
    elif 'DNS' in reason:
        status, action = 'Adres WWW nie działa', 'Zweryfikować aktualny adres pracowni; ponowienie nie odtworzy brakującej historii.'
    elif 'Przekierowanie' in reason:
        status, action = 'Adres przekierowuje do innego serwisu', 'Sprawdzić, czy serwis docelowy nadal należy do tej pracowni.'
    elif '500' in reason or '502' in reason or '503' in reason:
        status = 'Błąd serwera pracowni'
    return {'page': page['page'], 'reason': reason, 'category': category,
            'status': status, 'action': action, 'url': page.get('url', ''),
            'observed_at': page.get('observed_at')}
