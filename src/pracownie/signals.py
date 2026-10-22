"""Separate business evidence from capture, catalogue and identity observations.

Nothing is deleted: supporting observations remain in the journal. These rules
govern what can be asserted in the executive summary, not what was captured.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import urldefrag


def normalized(value) -> str:
    return ' '.join(str(value or '').split()).casefold()


def values(item: dict) -> list[str]:
    return [str(item.get(k) or '').strip() for k in ('before', 'after')
            if normalized(item.get(k)) not in {'', 'brak', '—'}]


def supporting_reason(item: dict) -> str:
    texts = values(item)
    description = item.get('description', '')
    if item.get('supporting_reason'):
        return item['supporting_reason']
    # Verified theme script: /wp-content/themes/hexagreen/js/info-section-counter.js.
    # It animates these headline numbers. Archived text and visual measurements
    # from the same capture even disagree (139 vs 138; 133 vs 130).
    # Do not infer the end value from a historical mid-animation observation.
    if item.get('domain') == 'hexagreen.pl' and texts and all(
        re.fullmatch(r'\d+\+ (?:autorskich projektów domów|realizacji #domyHexaGreen)', t) for t in texts
    ) and item['category'] in {'komunikacja', 'tresc', 'obraz'}:
        return 'Animowany licznik na stronie; odczyt w trakcie animacji nie potwierdza zmiany liczby projektów ani realizacji.'
    selected = re.search(r'(?:^| / )Projekt:\s*:?\s*([^/]+)', item.get('context', ''), re.I)
    if selected and normalized(selected[1]) not in normalized(item.get('project', '')):
        return 'Interakcja wybrała inny projekt niż zapamiętana karta; poza zakresem porównania tej oferty.'
    if item.get('communication_asset') or 'Źródło grafiki' in description or description.startswith(('Dodana grafika:', 'Usunięta grafika:')):
        return 'Zmiana adresu lub zestawu plików; nie ustalono zmiany wyglądu grafiki.'
    if item['category'] == 'obraz':
        if description == 'Rozmiar: treść strony':
            return 'Zmiana wymiarów całego dokumentu; nie wskazuje, który element projektu graficznego zmieniono.'
        if not item.get('specific'):
            return 'Różnica zrzutów; brak ustalonej przyczyny.'
        if description.startswith('Przesunięcie:'):
            distances = [int(n) for n in re.findall(r'(\d+) px (?:w dół|w górę|w lewo|w prawo)', description)]
            if distances and max(distances) < 40:
                return 'Drobne przesunięcie układu; nie ustalono zmiany komunikacji.'
    if 'ue_push_dialog' in item.get('source', ''):
        return 'Okno powiadomień mogło pojawić się zależnie od sesji.'
    if texts and all(normalized(t) in {'odrzucać', 'odrzuć', 'dostosuj', 'akceptuj', 'akceptuj wszystko', 'zaakceptuj wszystko', 'akceptuj wszystkie', 'zaakceptuj wszystkie'} for t in texts):
        return 'Kontrolka zgód lub ustawień sesji; nie zmiana komunikacji oferty.'
    offer_claim = any(re.search(r'\brabat|\bgratis|\bpakiet|\bdodat|\bpromocj|\bw cenie\b|\bbezpłat', t, re.I) for t in texts)
    if texts and not offer_claim and all(re.match(r'(?i)^(?:projekt\b|projekty dom|więcej informacji o projekcie|domy z |dom z |dom bez |nasza stodoła)', t) for t in texts) and item['category'] in {'komunikacja', 'funkcje', 'tresc'}:
        return 'Zmiana prezentowanych projektów lub linków; nie potwierdza zmiany oferty stałego projektu.'
    if texts and all(re.search(r'\d\s*m[²2]', t) for t in texts) and item.get('communication_role') in {'banner', 'heading', 'cta'}:
        return 'Zmiana pozycji lub parametrów w prezentowanym katalogu; nie ustalono zmiany stałego projektu.'
    if texts and all(re.fullmatch(r'(?:mój )?koszyk(?: \d+)?|zamówienie|rzuty|przekroje', t, re.I) for t in texts):
        return 'Różnica podstawowej kontrolki interfejsu; nie ustalono nowej funkcjonalności.'
    if description == 'Opis grafiki':
        return 'Inny podpis grafiki w zapisie; nie ustalono zmiany jej wyglądu.'
    if texts and all(re.fullmatch(r'(?:poniedziałek|wtorek|środa|czwartek|piątek|sobota|niedziela),? \d{1,2} \w+ \d{4},? (?:\[licznik\]|[\d :]+)', t, re.I) for t in texts):
        return 'Automatyczna aktualizacja kalendarza lub zegara.'
    if texts and all(re.fullmatch(r'[\d\s.,]+\s*(?:zł|pln)(?:\s+najniższa cena)?', t, re.I) for t in texts):
        return 'Sam zapis kwoty; ceny są w szczegółach.'
    if len(texts) == 2:
        relative = [re.sub(r'\b(dzisiaj|dziś|jutro|wczoraj)\b', '<dzień>', normalized(t)) for t in texts]
        if relative[0] == relative[1]:
            return 'Automatyczna zmiana względnego określenia dnia.'
        if description == 'Treść' and SequenceMatcher(None, *texts, autojunk=False).ratio() < .45:
            return 'Różne fragmenty treści; nie ustalono, że dotyczą tego samego komunikatu.'
    if item.get('unmatched') and item.get('communication_role') == 'text':
        return 'Fragment pojawił się tylko w jednym zapisie; brak dopasowanego miejsca przed / po.'
    return ''


def classify(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    # The same control text moving between field/context keys is not a new
    # promotion. Require the same page URL, category and exact normalized value.
    movements = {}
    for item in entries:
        if item['category'] not in {'funkcje', 'komunikacja'}:
            continue
        before, after = normalized(item.get('before')), normalized(item.get('after'))
        empty = {'', 'brak', '—'}
        if (before in empty) == (after in empty):
            continue
        key = (item['domain'], item['page'], item['category'],
               urldefrag(item.get('source', ''))[0], after if before in empty else before)
        movements.setdefault(key, {'added': [], 'removed': []})['added' if before in empty else 'removed'].append(item['id'])
    moved = {id for group in movements.values() if group['added'] and group['removed']
             for ids in group.values() for id in ids}
    primary, supporting = [], []
    for original in entries:
        item = dict(original)
        reason = supporting_reason(item) or ('Ten sam tekst dodano i usunięto przy innym kluczu lub kontekście formularza; nie potwierdzono zmiany oferty.'
                  if item['id'] in moved else '')
        if reason:
            item['supporting_reason'] = reason
            supporting.append(item)
        else:
            primary.append(item)
    return primary, supporting


def summary(item: dict, limit: int = 145) -> str:
    """A readable finding, never a claim about revenue or a campaign's cause."""
    before, after = str(item['before']), str(item['after'])
    desc = item['description']
    if item['category'] == 'obraz':
        text = f'{desc}: {before} → {after}'
    elif before == 'brak':
        text = 'Dodano komunikat: „' + after + '”'
    elif after == 'brak':
        text = 'Nie ma w bieżącym zapisie: „' + before + '”'
    else:
        text = '„' + before + '” → „' + after + '”'
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def implication(item: dict) -> str:
    return {
        'promotions': 'Zmieniła się komunikacja promocji; zapis nie dowodzi zmiany całej oferty.',
        'extras': 'Zmieniła się informacja o dodatkach lub pakiecie projektu.',
        'terms': 'Zmieniła się informacja o warunkach zakupu lub realizacji.',
        'functions': 'Zmieniła się opisana opcja lub działanie na stronie.',
        'design': 'Zmieniła się zmierzona właściwość wyglądu; porównaj zapisane widoki.',
    }.get(item.get('business_bucket'), 'Zmienił się tekst widoczny dla klienta w zapisanym zakresie.')
