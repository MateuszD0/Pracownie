"""Explicit changes to the terms of the same named extra on a frozen project card."""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal

from .extract import MONEY, amount, page_identity
from .journal import capture_day, safe_source
from .model import Change, Snapshot
from .offers import price_delta

# Match a whole, short item label. Keeping qualifiers in the identity prevents
# pairing a free basic estimate with a separately priced investor's estimate.
_ITEM = re.compile(
    r'kosztorys(?: budowlany| inwestorski| uproszczony| szczegółowy)?|'
    r'przedmiar(?: robót)?|zestawienie materiałów(?: budowlanych)?|'
    r'dziennik budowy|tablica (?:budowy|informacyjna)|'
    r'zgoda na (?:wprowadzenie )?zmian(?:y)?|konsultacj[ae] (?:z architektem|architektoniczn[ae])|'
    r'adaptacja projektu|projekt (?:garażu|instalacji (?:sanitarnej|sanitarnych|elektrycznej|grzewczej))|'
    r'(?:dodatkowy )?egzemplarz (?:projektu|dokumentacji)(?: architektoniczn[a-ząćęłńóśźż-]+)?|'
    r'(?:wersja|dokumentacja) (?:elektroniczna|papierowa)(?: projektu)?|'
    r'pakiet (?:instalacji|energooszczędny|instalacyjny|dodatków|premium|standard|plus)',
    re.I,
)
_INCLUDED = re.compile(r'gratis|bez dopłaty|bezpłatn[aye]|za darmo|w cenie(?: projektu| pakietu)?|wliczon[aye] w cenę(?: projektu)?', re.I)
_UNAVAILABLE = re.compile(r'niedostępn[aye]|wycofan[aye](?: z oferty)?|poza ofertą|brak w ofercie', re.I)
_PAID = re.compile(r'(?:dodatkowo |osobno )?płatn[aye]|za (?:dodatkową )?opłatą|za dopłatą', re.I)


def _state(text: str) -> str:
    if _INCLUDED.fullmatch(text):
        return 'included'
    if _UNAVAILABLE.fullmatch(text):
        return 'unavailable'
    if _PAID.fullmatch(text):
        return 'paid'
    # A standalone charge is unambiguous. A discount, minimum purchase or
    # conditional sentence involving money cannot match this grammar.
    charge = re.sub(r'^(?:za |dopłata\s*[:+]?\s*|cena\s*:\s*)', '', text, flags=re.I)
    charge = re.sub(r' (?:brutto|netto(?: \+ VAT)?)$', '', charge, flags=re.I)
    match = MONEY.fullmatch(charge)
    if match and (value := amount(match[1], displayed=True)) is not None:
        return 'paid' if Decimal(value) else 'included'
    return ''


def _explicit_item(text: str, label: str) -> tuple[str, str] | None:
    quote = ' '.join(text.split()).strip(' .!')
    item = _ITEM.match(quote)
    if item:
        remainder = quote[item.end():]
        if remainder[:1].isalnum():
            return None
        terms = re.sub(r'^\s*(?::\s*|[–—-]\s+)?', '', remainder)
        name = item[0]
    elif _ITEM.fullmatch(label):
        # Some structured fields keep the name outside the value.
        name, terms = label, quote
    else:
        return None
    state = _state(terms)
    return (name, state) if state else None


def mark_package_context(before: Snapshot | None, after: Snapshot, changes: list[Change]) -> None:
    """Keep evidence that the two captures used the same named tab/option."""
    if (not before or after.page != 'projekt' or after.scenario == 'podstawowy' or not changes
            or before.key != after.key or page_identity(before.url) != page_identity(after.url)
            or before.quality != 'ok' or after.quality != 'ok'):
        return
    old, new = (s.document.get('payload', {}) for s in (before, after))
    label = new.get('scenario_label')
    if not label or label != old.get('scenario_label') or 'variant' not in new or new['variant'] != old.get('variant'):
        return
    for change in changes:
        if (change.kind == 'changed' and change.before_at == before.observed_at and change.after_at == after.observed_at
                and _explicit_item(change.before or '', change.label) and _explicit_item(change.after or '', change.label)):
            change.details['package_context'] = label


def _same_price(row: dict, day: str, previous_day: str, paired: set[str]) -> str:
    from .presentation import money

    previous = row.get('previous') or {}
    current = row.get('current') or {}
    if (row['domain'] not in paired or row.get('delta') is None or Decimal(row['delta']) != 0
            or previous.get('quality') != 'ok' or current.get('quality') != 'ok'
            or capture_day(previous.get('observed_at')) != previous_day
            or capture_day(current.get('observed_at')) != day):
        return ''
    delta, _ = price_delta(previous, current)
    return money(current) if delta is not None and Decimal(delta) == 0 else ''


def package_changes(view: dict) -> list[dict]:
    """Return one dated observation for each distinct, explicit change in inclusion."""
    day = view['day']
    previous_day = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    paired = set(view.get('comparison', {}).get('price_domains', []))
    rows = {r['domain']: r for r in view['rows'] if r.get('project_selected') and safe_source(r.get('url', ''))}
    changes = {}
    ambiguous = set()
    for event in view.get('journal', []):
        row = rows.get(event['domain'])
        if (not row or event.get('page') != 'projekt' or not event.get('daily') or event.get('unmatched')
                or event.get('category') not in {'dodatki', 'pakiety', 'promocje', 'komunikacja'}
                or event.get('supporting_reason') or event.get('communication_check', {}).get('status') in {'unstable', 'unverified'}
                or event.get('commercial_check', {}).get('status') in {'unstable', 'unverified', 'other_offers', 'probably_ended', 'still_present', 'scheduled', 'expired'}
                or capture_day(event.get('before_at')) != previous_day or capture_day(event.get('after_at')) != day):
            continue
        scenario = event.get('scenario')
        if scenario == 'podstawowy':
            if not any(p.get('page') == 'projekt' and p.get('daily') and p.get('data_quality') == 'ok' for p in row.get('pages', [])):
                continue
        elif not event.get('package_context'):
            continue
        source = safe_source(event.get('source', ''))
        if not source or page_identity(source) != page_identity(row['url']):
            continue
        label = (event.get('item_label') or event.get('description', '')).strip()
        before = _explicit_item(event['before'], label)
        after = _explicit_item(event['after'], label)
        if not before or not after or before[0].casefold() != after[0].casefold() or before[1] == after[1]:
            continue
        key = (row['domain'], scenario, after[0].casefold())
        if key in changes:
            # A card may quote several configurations of the same extra.
            # Conflicting quotes require inspection of the source.
            existing = changes[key]
            if (existing['before'].casefold(), existing['after'].casefold()) != (event['before'].casefold(), event['after'].casefold()):
                ambiguous.add(key)
            continue
        changes[key] = {
            'domain': row['domain'], 'project': row['name'], 'name': after[0], 'before_state': before[1],
            'after_state': after[1], 'before': event['before'], 'after': event['after'],
            'before_at': event['before_at'], 'after_at': event['after_at'], 'source': source,
            'evidence': event.get('evidence', {}), 'observation_id': event['id'],
            'context': event.get('package_context', ''), 'scenario': scenario,
            'unchanged_price': _same_price(row, day, previous_day, paired),
        }
    return [entry for key, entry in changes.items() if key not in ambiguous]
