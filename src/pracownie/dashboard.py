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


def render_dashboard_documents(view: dict, report_url: str, downloads: dict | None = None, previews: dict | None = None, filename: str = 'DASHBOARD.md') -> dict[str, str]:
    downloads, previews = downloads or {}, previews or {}
    data = build_management(view)
    folder = filename.removesuffix('.md').lower()
    domains = {row['domain']: [item for item in data['items'] if item['domain'] == row['domain']] for row in view['rows']}
    names = {row['domain']: company_anchor(row['domain']) for row in view['rows']}
    observed = sorted(p['observed_at'] for row in view['rows'] for p in row['pages'] if p['observed_at'])
    pages = [p for row in view['rows'] for p in row['pages']]
    complete = sum(bool(p.get('communication', {}).get('daily')) for p in pages)
    history = 'https://github.com/' + report_url.split('github.com/')[-1].split('/releases/')[0] + '/blob/main/' + filename.replace('DASHBOARD', 'RAPORTY', 1)
    lines = ['# Dzienny dashboard pracowni', '', f"**{cell(view['comparison']['before_day'])} → {cell(view['day'])}** · strona główna i jedna zapamiętana karta projektu każdej pracowni.", '']
    if observed:
        lines += [f"Dane z odczytów: **{when(observed[0])} – {when(observed[-1])}**, czas polski.", '']
    lines += [f"Pełne porównanie komunikacji: **{complete}/{len(pages)} stron**. Brak odczytu lub częściowa historia nie oznaczają braku zmian.", '', link('Historia dni', history) + ' · ' + link('Pliki i pełne zrzuty', report_url), '', '## Najważniejsze różnice biznesowe', '', ' · '.join(cell(b['label']) + ': **' + (str(b['domains']) if complete or b['domains'] else '—') + '** pracowni' for b in data['business_buckets']), '', '| Pracownia / strona | Co się zmieniło | Było | Jest | Źródło |', '| --- | --- | --- | --- | --- |']
    for item in business_highlights(data['items']):
        lines += ['| ' + ' | '.join([f"[{cell(item['domain'])}]({folder}/{names[item['domain']]}.md) · " + ('główna' if item['page'] == 'glowna' else 'stały projekt'), cell(item['business_type'] + ' · ' + item['description']), cell(brief(item['before'], 240)), cell(brief(item['after'], 240)), link('Otwórz stronę', item['source'])]) + ' |']
    if not business_highlights(data['items']):
        lines += ['| Nie ustalono konkretnych zmian biznesowych dzień do dnia w sprawdzonym zakresie. | | | | |']
    lines += ['', '## Wszystkie pracownie', '', 'Kliknij pracownię, aby przeczytać jej porównanie strony głównej i stałej karty projektu. Pełne porównania są podzielone na krótkie strony, aby wyświetlały się bezpośrednio w GitHubie.', '', '| Pracownia | Strona główna | Stała karta projektu |', '| --- | --- | --- | --- |']
    ordered = sorted(view['rows'], key=lambda row: (not domains[row['domain']], row['domain']))
    documents = {}
    for row in ordered:
        items = domains[row['domain']]
        labels = []
        for page in row['pages']:
            changes = [item for item in items if item['page'] == page['page']]
            labels += [cell(f'{len(changes)} różnych zmian' if changes else page.get('communication', {}).get('label', 'Brak porównania'))]
        lines += [f"| [{cell(row['domain'])}]({folder}/{names[row['domain']]}.md) | " + ' | '.join(labels) + ' |']
        chunks = [items[i:i + 25] for i in range(0, len(items), 25)] or [[]]
        paths = [folder + '/' + names[row['domain']] + (f'-{i + 1}' if i else '') + '.md' for i in range(len(chunks))]
        for index, chunk in enumerate(chunks):
            navigation = ' · '.join((f'**{i + 1}**' if i == index else f'[{i + 1}]({path.rsplit("/", 1)[-1]})') for i, path in enumerate(paths))
            content = ['# ' + cell(row['domain']), '', '[← Wszystkie pracownie](../' + filename + ')', '', f"**{cell(view['comparison']['before_day'])} → {cell(view['day'])}**", '', '**Ten sam projekt:** ' + link(row['name'], row['url']), '', f"Różnice tej pracowni: **{len(items)}**. Strona **{index + 1}/{len(chunks)}** · pokazano **{len(chunk)}** wpisów.", '', 'Strony porównania: ' + navigation, '', 'Treści w tabelach są skrócone do 240 znaków. Pełne teksty i zrzuty są w plikach raportu.', '']
            for page in row['pages']:
                page_items = [item for item in chunk if item['page'] == page['page']]
                total = sum(item['page'] == page['page'] for item in items)
                content += ['## ' + cell(page['label']), '', link('Otwórz stronę źródłową', page['url']), '', '**Odczyty:** ' + when(page['compared_at']) + ' → ' + when(page['observed_at']) + ' (czas polski).', '']
                if page_items:
                    content += ['| Zmiana / miejsce | Było | Jest | Źródło |', '| --- | --- | --- | --- |', *[change_row(item) for item in page_items], '']
                    images = list(dict.fromkeys(url for item in page_items for path, url in previews.items() if path in item['evidence'].values()))
                    content += [link('Podgląd zapisanej zmiany', url) for url in images]
                elif total:
                    content += [f'Pozostałe strony tego porównania zawierają {total} różnic tej strony; użyj numerów stron powyżej.', '']
                else:
                    content += ['**' + cell(page.get('communication', {}).get('label', 'Brak porównania')) + '**', '']
                if page.get('error_text'):
                    content += ['Powód braku odczytu: ' + cell(page['error_text']), '']
            if downloads.get('html'):
                content += [link('Pobierz pełne porównanie HTML ze zrzutami przed / po', downloads['html']), '']
            content += ['Strony porównania: ' + navigation, '']
            documents[paths[index]] = '\n'.join(content) + '\n'
    documents[filename] = '\n'.join(lines) + '\n'
    return documents


def render_dashboard(view: dict, report_url: str, downloads: dict | None = None, previews: dict | None = None) -> str:
    return render_dashboard_documents(view, report_url, downloads, previews)['DASHBOARD.md']
