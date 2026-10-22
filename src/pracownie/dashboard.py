"""A daily comparison readable directly on GitHub, without downloading HTML."""
from __future__ import annotations

import html
import re
from urllib.parse import quote

from .journal import safe_source
from .management import brief, build_management, business_highlights, page_finding
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
    def value(text):
        return link('Otwórz grafikę', text) if item['category'] == 'obraz' and re.fullmatch(r'https?://\S+', str(text)) else cell(brief(text, 240))

    return '| ' + ' | '.join([cell(label), value(item['before']), value(item['after']), link('Otwórz stronę', item['source'])]) + ' |'


def proof_links(evidence: dict, previews: dict) -> str:
    fields = [('fragment_przed', 'Przed'), ('fragment_po', 'Po')] if all(evidence.get(k) in previews for k in ['fragment_przed', 'fragment_po']) else [('przed', 'Przed'), ('po', 'Po')]
    return ' · '.join(link(label, previews[evidence[k]]) for k, label in fields if evidence.get(k) in previews)


def render_dashboard_documents(view: dict, report_url: str, downloads: dict | None = None, previews: dict | None = None, filename: str = 'DASHBOARD.md') -> dict[str, str]:
    downloads, previews = downloads or {}, previews or {}
    data = build_management(view)
    visual_reviews = [item for item in view['journal'] if item['daily'] and item['category'] == 'obraz' and not item.get('specific')]
    folder = filename.removesuffix('.md').lower()
    domains = {row['domain']: [item for item in data['items'] if item['domain'] == row['domain']] for row in view['rows']}
    names = {row['domain']: company_anchor(row['domain']) for row in view['rows']}
    observed = sorted(p['observed_at'] for row in view['rows'] for p in row['pages'] if p['observed_at'])
    pages = [p for row in view['rows'] for p in row['pages']]
    complete = sum(bool(p.get('communication', {}).get('daily')) for p in pages)
    complete_firms = sum(all(p.get('communication', {}).get('daily') for p in row['pages']) for row in view['rows'])
    home_complete = sum(p['page'] == 'glowna' and bool(p.get('communication', {}).get('daily')) for p in pages)
    project_complete = sum(p['page'] == 'projekt' and bool(p.get('communication', {}).get('daily')) for p in pages)
    history = 'https://github.com/' + report_url.split('github.com/')[-1].split('/releases/')[0] + '/blob/main/' + filename.replace('DASHBOARD', 'RAPORTY', 1)
    lines = ['# Dzienny dashboard pracowni', '', f"**{cell(view['comparison']['before_day'])} → {cell(view['day'])}** · strona główna i jedna zapamiętana karta projektu każdej pracowni.", '']
    if observed:
        lines += [f"Dane z odczytów: **{when(observed[0])} – {when(observed[-1])}**, czas polski.", '']
    lines += [f"**Obie strony porównane: {complete_firms}/{len(view['rows'])} pracowni.** Strony główne: {home_complete}/{len(view['rows'])} · stałe projekty: {project_complete}/{len(view['rows'])}.", '',
              f"Ustalone zmiany: **{data['metrics']['communication']} pracowni**. Zestawienie dotyczy komunikacji, promocji, dodatków i wyglądu. Rotacja polecanych projektów, adresy plików i niezgodne konteksty są w obserwacjach pomocniczych.", '']
    lines += [f"Pełne porównanie komunikacji: **{complete}/{len(pages)} stron**. Brak odczytu lub częściowa historia nie oznaczają braku zmian.", '', link('Historia dni', history) + ' · ' + link('Pliki i pełne zrzuty', report_url), '', '## Najważniejsze różnice biznesowe', '', ' · '.join(cell(b['label']) + ': **' + (str(b['domains']) if complete or b['domains'] else '—') + '** pracowni' for b in data['business_buckets']), '', '| Pracownia / strona | Co się zmieniło | Było | Jest | Źródło |', '| --- | --- | --- | --- | --- |']
    for item in business_highlights(data['items']):
        lines += ['| ' + ' | '.join([f"[{cell(item['domain'])}]({folder}/{names[item['domain']]}.md) · " + ('główna' if item['page'] == 'glowna' else 'stały projekt'), cell(item['business_type'] + ' · ' + item['description']), cell(brief(item['before'], 240)), cell(brief(item['after'], 240)), link('Otwórz stronę', item['source']) + ' ' + proof_links(item['evidence'], previews)]) + ' |']
    if not business_highlights(data['items']):
        lines += ['| Nie ustalono konkretnych zmian biznesowych dzień do dnia w sprawdzonym zakresie. | | | | |']
    lines += ['', '„Brak” oznacza brak komunikatu w danym zapisie. Zniknięcie hasła promocyjnego nie dowodzi zakończenia promocji. Porównania dotyczą zapisanej treści; dodatkowe interakcje mogą mieć niepełne pokrycie.', '']
    visual_facts = [item for item in data['items'] if item['category'] == 'obraz']
    lines += ['', '## Grafika i wygląd', '', 'Banery i zdjęcia, kolory, typografia oraz układ elementów. Zmiana zrzutu bez ustalonej przyczyny jest sygnałem do obejrzenia, a nie potwierdzeniem przebudowy strony czy nowej kampanii.', '', f"Opisane zmiany: **{len({e['domain'] for e in visual_facts})} pracowni** · różnice obrazu bez jednoznacznego opisu: **{len({e['domain'] for e in visual_reviews})} pracowni**. Jedna pracownia może występować w obu grupach.", '']
    visual_highlights, seen = [], set()
    for item in visual_facts + visual_reviews:
        if item['domain'] not in seen:
            visual_highlights.append(item)
            seen.add(item['domain'])
        if len(visual_highlights) == 6:
            break
    if visual_highlights:
        lines += ['Wybrane przykłady; wszystkie obserwacje są w porównaniach poszczególnych pracowni.', '', '| Pracownia / strona | Co wykryto | Podstawa |', '| --- | --- | --- |']
        for item in visual_highlights:
            description = item['description'] + (': ' + brief(item['before'], 95) + ' → ' + brief(item['after'], 95) if item.get('specific') else '')
            lines += ['| ' + ' | '.join([f"[{cell(item['domain'])}]({folder}/{names[item['domain']]}.md) · " + ('główna' if item['page'] == 'glowna' else 'stały projekt'), cell(description), ('Zrzuty i właściwość elementu' if item.get('specific') else 'Różnica zrzutów; przyczyna niepotwierdzona') + ' ' + proof_links(item['evidence'], previews)]) + ' |']
    else:
        lines += ['Brak wiarygodnych obserwacji zmian graficznych dzień do dnia w zapisanym zakresie.']
    lines += ['', '## Wszystkie pracownie', '', 'Kliknij pracownię, aby przeczytać jej porównanie strony głównej i stałej karty projektu. Pełne porównania są podzielone na krótkie strony, aby wyświetlały się bezpośrednio w GitHubie.', '', '| Pracownia | Strona główna | Stała karta projektu |', '| --- | --- | --- |']
    ordered = sorted(view['rows'], key=lambda row: (not domains[row['domain']], row['domain']))
    documents = {}
    for row in ordered:
        items = domains[row['domain']]
        labels = []
        for page in row['pages']:
            changes = [item for item in items if item['page'] == page['page']]
            supporting = [e for e in data['secondary'] if e['domain'] == row['domain'] and e['page'] == page['page'] and e['daily'] and e['category'] != 'ceny']
            review = any(e['domain'] == row['domain'] and e['page'] == page['page'] for e in visual_reviews)
            label = page_finding(page, changes, supporting)
            labels += [cell(label + (' · obraz do obejrzenia' if review else ''))]
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
                    supporting = [e for e in data['secondary'] if e['domain'] == row['domain'] and e['page'] == page['page'] and e['daily'] and e['category'] != 'ceny']
                    content += ['**' + cell(page_finding(page, [], supporting)) + '**', '']
                if page.get('error_text'):
                    content += ['Powód braku odczytu: ' + cell(page['error_text']), '']
                if index == 0:
                    evidence = next((e['evidence'] for e in items if e['page'] == page['page'] and proof_links(e['evidence'], previews)), page.get('evidence', {}))
                    proofs = proof_links(evidence, previews)
                    if proofs:
                        content += ['**Zapisane zrzuty — podgląd przed / po:** ' + proofs, '']
                    supporting = [e for e in data['supporting'] if e['domain'] == row['domain'] and e['page'] == page['page']]
                    if supporting:
                        reasons = list(dict.fromkeys(e['supporting_reason'] for e in supporting))
                        content += ['<details><summary>Obserwacje pomocnicze (' + str(len(supporting)) + ') — nie są ustaloną zmianą oferty</summary>', '', *['- ' + cell(reason) for reason in reasons], '', 'Przykłady z zapisów:', '']
                        for item in supporting[:3]:
                            content += ['- ' + cell(brief(item['before'], 140)) + ' → ' + cell(brief(item['after'], 140))]
                        content += ['', 'Pełna lista pozostaje w dzienniku CSV i raporcie HTML.', '', '</details>', '']
                    for item in visual_reviews:
                        if item['domain'] == row['domain'] and item['page'] == page['page']:
                            content += ['### Grafika i wygląd — różnica do obejrzenia', '', '**' + cell(item['description']) + '**', '', 'Porównanie: ' + when(item['before_at']) + ' → ' + when(item['after_at']) + ' (czas polski). Różnica zrzutów nie potwierdza sama w sobie zmiany oferty ani przebudowy strony.', '', link('Otwórz stronę', item['source']), '']
                            content += [link('Podgląd zapisanej zmiany', url) for path, url in previews.items() if path in item['evidence'].values()]
            if downloads.get('html'):
                content += [link('Zrzuty przed / po — pobierz pełne porównanie HTML', downloads['html']), '']
            content += ['Strony porównania: ' + navigation, '']
            documents[paths[index]] = '\n'.join(content) + '\n'
    documents[filename] = '\n'.join(lines) + '\n'
    return documents


def render_dashboard(view: dict, report_url: str, downloads: dict | None = None, previews: dict | None = None) -> str:
    return render_dashboard_documents(view, report_url, downloads, previews)['DASHBOARD.md']
