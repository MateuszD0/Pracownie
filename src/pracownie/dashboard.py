"""A daily comparison readable directly on GitHub, without downloading HTML."""
from __future__ import annotations

import html
import re
from urllib.parse import quote

from .journal import safe_source
from .management import brief, build_management, business_highlights
from .presentation import when


def cell(value) -> str:
    text = html.escape(' '.join(str(value or '—').split()), quote=False).replace('\\', '\\\\')
    return re.sub(r'([|\[\]*_`])', r'\\\1', text)


def link(label: str, url: str) -> str:
    url = safe_source(url)
    return '[' + cell(label) + '](' + quote(url, safe=":/?#[]@!$&'*+,;=%") + ')' if url else '—'


def company_anchor(domain: str) -> str:
    return re.sub(r'[^a-z0-9_-]', '', domain.casefold())


def change_row(item: dict) -> str:
    label = item['business_type'] + ' · ' + item['description']
    if item.get('context'):
        label += ' · ' + item['context']
    return '| ' + ' | '.join([cell(label), cell(brief(item['before'], 240)), cell(brief(item['after'], 240)), link('Otwórz stronę', item['source'])]) + ' |'


def render_dashboard(view: dict, report_url: str, downloads: dict | None = None, previews: dict | None = None) -> str:
    downloads, previews = downloads or {}, previews or {}
    data = build_management(view)
    groups = {(row['domain'], page['page']): [item for item in data['items'] if item['domain'] == row['domain'] and item['page'] == page['page']] for row in view['rows'] for page in row['pages']}
    observed = sorted(p['observed_at'] for row in view['rows'] for p in row['pages'] if p['observed_at'])
    pages = [p for row in view['rows'] for p in row['pages']]
    complete = sum(bool(p.get('communication', {}).get('daily')) for p in pages)
    lines = ['# Dzienny dashboard pracowni', '', f"**{cell(view['comparison']['before_day'])} → {cell(view['day'])}** · strona główna i jedna zapamiętana karta projektu każdej pracowni.", '']
    if observed:
        lines += [f"Dane z odczytów: **{when(observed[0])} – {when(observed[-1])}**, czas polski.", '']
    lines += [f"Pełne porównanie komunikacji: **{complete}/{len(pages)} stron**. Brak odczytu lub częściowa historia nie oznaczają braku zmian.", '', link('Historia dni', 'https://github.com/' + report_url.split('github.com/')[-1].split('/releases/')[0] + '/blob/main/RAPORTY.md') + ' · ' + link('Pliki i pełne zrzuty', report_url), '', '## Najważniejsze różnice biznesowe', '', ' · '.join(cell(b['label']) + ': **' + (str(b['domains']) if complete or b['domains'] else '—') + '** pracowni' for b in data['business_buckets']), '', '| Pracownia / strona | Co się zmieniło | Było | Jest | Źródło |', '| --- | --- | --- | --- | --- |']
    for item in business_highlights(data['items']):
        lines += ['| ' + ' | '.join([f"[{cell(item['domain'])}](#{company_anchor(item['domain'])}) · " + ('główna' if item['page'] == 'glowna' else 'stały projekt'), cell(item['business_type'] + ' · ' + item['description']), cell(brief(item['before'], 240)), cell(brief(item['after'], 240)), link('Otwórz stronę', item['source'])]) + ' |']
    if not business_highlights(data['items']):
        lines += ['| Nie ustalono konkretnych zmian biznesowych dzień do dnia w sprawdzonym zakresie. | | | | |']
    lines += ['', '## Wszystkie pracownie', '', '| Pracownia | Strona główna | Stała karta projektu |', '| --- | --- | --- |']
    ordered = sorted(view['rows'], key=lambda row: (not any(groups[row['domain'], p['page']] for p in row['pages']), row['domain']))
    for row in ordered:
        labels = []
        for page in row['pages']:
            items = groups[row['domain'], page['page']]
            labels += [cell(f'{len(items)} różnych zmian' if items else page.get('communication', {}).get('label', 'Brak porównania'))]
        lines += [f"| [{cell(row['domain'])}](#{company_anchor(row['domain'])}) | " + ' | '.join(labels) + ' |']
    lines += ['', '## Różnice według pracowni', '', 'Kliknij nazwę pracowni w tabeli powyżej, a następnie rozwiń jej szczegóły. Tabele pokazują treści przed / po; długie teksty są skrócone do 240 znaków. Pełne treści i zrzuty są w plikach raportu.', '']
    for row in ordered:
        lines += ['### ' + cell(row['domain']), '', '<details>', '<summary>Rozwiń porównanie strony głównej i stałego projektu</summary>', '', '**Stały projekt:** ' + link(row['name'], row['url']), '']
        for page in row['pages']:
            items = groups[row['domain'], page['page']]
            lines += ['#### ' + cell(page['label']), '', link('Otwórz stronę źródłową', page['url']), '', '**Odczyty:** ' + when(page['compared_at']) + ' → ' + when(page['observed_at']) + ' (czas polski).', '']
            if items:
                lines += ['| Zmiana / miejsce | Było | Jest | Źródło |', '| --- | --- | --- | --- |', *[change_row(item) for item in items], '']
                images = list(dict.fromkeys(url for item in items for path, url in previews.items() if path in item['evidence'].values()))
                lines += [link('Podgląd zapisanej zmiany', url) for url in images]
            else:
                lines += ['**' + cell(page.get('communication', {}).get('label', 'Brak porównania')) + '**', '']
            if page.get('error_text'):
                lines += ['Powód braku odczytu: ' + cell(page['error_text']), '']
        if downloads.get('html'):
            lines += [link('Pobierz pełne porównanie HTML ze zrzutami przed / po', downloads['html']), '']
        lines += ['</details>', '']
    return '\n'.join(lines) + '\n'
