"""Presentation of observed changes; no inferred campaign or revenue claims."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from functools import lru_cache

EMPTY = {'', 'brak', '—'}


@lru_cache(maxsize=256)
def comparison_parts(before: str, after: str, limit: int = 220) -> tuple[list[dict], list[dict]]:
    """Highlight actual changed tokens and keep the first difference in view."""
    tokens = [re.findall(r'\s+|[^\W_]+|[^\w\s]', str(value), re.UNICODE) for value in (before, after)]
    # DOM captures can contain huge repeated paragraphs. Bound the diff around
    # the first difference instead of running a quadratic matcher on all text.
    prefix = 0
    while prefix < min(len(t) for t in tokens) and tokens[0][prefix] == tokens[1][prefix]:
        prefix += 1
    windowed = []
    for side in (0, 1):
        sequence = tokens[side]
        if len(sequence) > 600:
            start = max(0, prefix - 20)
            stop = start + 600
            sequence = (['…'] if start else []) + sequence[start:stop] + (['…'] if stop < len(sequence) else [])
        windowed.append(sequence)
    tokens = windowed
    parts = [[], []]
    for op, a, b, c, d in SequenceMatcher(None, *tokens, autojunk=False).get_opcodes():
        for side, start, end in [(0, a, b), (1, c, d)]:
            parts[side].extend({'text': token, 'changed': op != 'equal'} for token in tokens[side][start:end])
    for side, value in enumerate((before, after)):
        if str(value).strip().casefold() in EMPTY:
            parts[side] = [{'text': 'Nie odnotowano w tym odczycie', 'changed': False}]
            continue
        text = ''.join(p['text'] for p in parts[side])
        if len(text) <= limit:
            continue
        changed_at, cursor = 0, 0
        for part in parts[side]:
            if part['changed'] and part['text'].strip():
                changed_at = cursor
                break
            cursor += len(part['text'])
        start = max(0, min(changed_at - 55, len(text) - limit))
        end, cursor, clipped = start + limit, 0, []
        if start:
            clipped.append({'text': '…', 'changed': False})
        for part in parts[side]:
            stop = cursor + len(part['text'])
            segment = part['text'][max(0, start - cursor):max(0, min(stop, end) - cursor)] if cursor < end and stop > start else ''
            if segment:
                clipped.append({'text': segment, 'changed': part['changed']})
            cursor = stop
        if end < len(text):
            clipped.append({'text': '…', 'changed': False})
        parts[side] = clipped
    for side in (0, 1):
        merged = []
        for part in parts[side]:
            if merged and merged[-1]['changed'] == part['changed']:
                merged[-1]['text'] += part['text']
            else:
                merged.append(dict(part))
        parts[side] = merged
    return tuple(parts)


def readout(item: dict) -> dict:
    before, after = str(item['before']), str(item['after'])
    description = item['description']
    title = re.sub(r'^(?:Dodano|Usunięto):\s*', '', description)
    title = {'Treść': 'Opis i argumenty oferty', 'Funkcjonalność': 'Opcja na stronie',
             'Wezwanie do działania': 'Przycisk / wezwanie do działania'}.get(title, title)
    note = ''
    if before.strip().casefold() in EMPTY:
        note = 'Widoczne tylko w dzisiejszym zapisie.'
    elif after.strip().casefold() in EMPTY:
        note = 'Brak w dzisiejszym zapisie nie dowodzi wycofania oferty.'
    if item['category'] == 'obraz' and description.startswith('Przesunięcie:'):
        match = re.fullmatch(r'Przesunięcie: (.+) \((.+)\)', description)
        if match:
            title = 'Układ · ' + match[1]
            before, after = 'Pozycja w poprzednim zapisie', match[2]
            note = 'Zmierzono przesunięcie; jego przyczyna nie jest ustalona.'
    left, right = comparison_parts(before, after)
    return {'title': title, 'before': left, 'after': right, 'note': note}


def digest_groups(items: list[dict]) -> list[dict]:
    """Every page and topic is represented, including several from one studio."""
    groups = {}
    for item in items:
        key = item['domain'], item['page'], item['business_bucket']
        if key not in groups:
            groups[key] = {k: item[k] for k in ('domain', 'page', 'business_bucket', 'business_type')}
            groups[key].update(id=item['id'], items=[], count=0)
        groups[key]['items'].append(item)
        groups[key]['count'] += 1
    return list(groups.values())
