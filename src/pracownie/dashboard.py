"""A daily comparison readable directly on GitHub, without downloading HTML."""
from __future__ import annotations

import html
import re
from urllib.parse import quote

from .journal import safe_source
from .management import brief, build_management, page_finding
from .presentation import when
from .readout import digest_groups


def cell(value) -> str:
    text = html.escape(' '.join(str(value or '—').split()), quote=False).replace('\\', '\\\\')
    return re.sub(r'([|\[\]*_`])', r'\\\1', text)


def link(label: str, url: str) -> str:
    url = safe_source(url)
    return '[' + cell(label) + '](' + quote(url, safe=":/?#[]@!$&'*+,;=%") + ')' if url else '—'


def company_anchor(domain: str) -> str:
    return re.sub(r'[^a-z0-9_-]', '', domain.casefold())


def diff_cell(item: dict, side: str) -> str:
    def fragment(part):
        # Unlike a complete cell, a diff segment must keep boundary spaces.
        text = html.escape(re.sub(r'\s+', ' ', part['text']), quote=False).replace('\\', '\\\\')
        text = re.sub(r'([|\[\]*_`])', r'\\\1', text)
        return '<strong>' + text + '</strong>' if part['changed'] and text.strip() else text
    return ''.join(fragment(part) for part in item['readout'][side])


def change_row(item: dict) -> str:
    label = item['business_type'] + ' · ' + item['readout']['title']
    if item.get('context') and item['context'] not in {'Strona główna', 'Karta projektu'}:
        label += ' · ' + item['context']
    return '| ' + ' | '.join([cell(label), diff_cell(item, 'before'), diff_cell(item, 'after'), link('Otwórz stronę', item['source'])]) + ' |'


def proof_pair(evidence: dict, previews: dict, before_at: str, after_at: str) -> list[str]:
    keys = ['fragment_przed', 'fragment_po'] if all(evidence.get(k) in previews for k in ['fragment_przed', 'fragment_po']) else ['przed', 'po']
    if not all(evidence.get(k) in previews for k in keys):
        return []
    images = ['![' + label + '](' + quote(safe_source(previews[evidence[k]]), safe=":/?#[]@!$&'*+,;=%") + ')' for k, label in zip(keys, ['Przed', 'Po'], strict=True)]
    return ['<details><summary>Zrzuty przed / po — rozwiń porównanie</summary>', '',
            '| Przed · ' + cell(when(before_at)) + ' | Po · ' + cell(when(after_at)) + ' |', '| --- | --- |',
            '| ' + ' | '.join(images) + ' |', '',
            'Fragment uchwyconego widoku; może nie obejmować wszystkich opisanych komunikatów. Kliknij obraz, aby powiększyć.', '', '</details>', '']


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
    groups = digest_groups(data['items'])
    # The overview links to the page containing the representative change.
    targets = {}
    for domain, entries in domains.items():
        for index, item in enumerate(entries):
            suffix = f'-{index // 25 + 1}' if index >= 25 else ''
            anchor = 'strona-główna' if item['page'] == 'glowna' else 'karta-projektu'
            targets[item['id']] = folder + '/' + names[domain] + suffix + '.md#' + anchor
    lines = ['# Co zmieniło się u pracowni?', '', f"**{cell(view['comparison']['before_day'])} → {cell(view['day'])}** · strona główna i ta sama karta projektu.", '',
             f"**Różnice w zapisach {data['metrics']['communication']} pracowni** · **Obie strony porównane: {complete_firms}/{len(view['rows'])} pracowni.**", '']
    if observed:
        lines += [f"Odczyty: {when(observed[0])} – {when(observed[-1])}, czas polski.", '']
    lines += ['[Zmiany](#zmiany-oferty-i-komunikacji) · [Grafika i wygląd](#grafika-i-wygląd) · [Wszystkie pracownie](#wszystkie-pracownie) · ' + link('Historia dni', history), '',
              f"Zakres: strony główne **{home_complete}/{len(view['rows'])}**, stałe projekty **{project_complete}/{len(view['rows'])}**. Pełne porównanie: **{complete}/{len(pages)} stron**. Brakujące dane nie oznaczają braku zmian.", '',
              '## Zmiany oferty i komunikacji', '',
              'Krótki opis poniżej; pełne teksty **przed → po** i dostępne zrzuty pod linkiem „Porównaj”. Opis dotyczy zapisów z podanych dni.', '']
    header = ['| Pracownia / strona | Co zauważono | Sprawdź |', '| --- | --- | --- |']
    digest_documents = {}
    for detailed in (False, True):
        selected = [g for g in groups if g['overview'] != detailed]
        if detailed:
            lines += ['', '<details><summary>Pozostałe różnice do przejrzenia · tematy: ' + str(len(selected)) + '</summary>', '',
                      'Krótkie etykiety, przesunięcia sekcji i różny zakres zapisanych akapitów. Same nie potwierdzają zmiany oferty.', '']
        lines += header
        digest_pages, digest_rows, digest_bytes = [], [], 0
        for group in selected:
            entry = group['lead']
            label = f"[{cell(group['domain'])}]({targets[group['id']]})<br>" + ('Strona główna' if group['page'] == 'glowna' else 'Karta projektu')
            description = '**' + cell(group['business_type']) + '**<br>' + cell(entry['readout']['sentence'])
            if entry['readout']['digest_note']:
                description += '<br><em>' + cell(entry['readout']['digest_note']) + '</em>'
            more = f"<br>Pozostałe różnice tego tematu: {group['count'] - 1}" if group['count'] > 1 else ''
            evidence = '[Porównaj →](' + targets[group['id']] + ')' + more + '<br>' + link('Otwórz stronę', entry['source'])
            for source in entry.get('commercial_check', {}).get('sources', [])[:2]:
                evidence += '<br>' + link('Sprawdzone warunki', source['url'])
            digest_row = '| ' + ' | '.join([label, description, evidence]) + ' |'
            if digest_rows and digest_bytes + len(digest_row.encode()) > 16_000:
                digest_pages.append(digest_rows)
                digest_rows, digest_bytes = [], 0
            digest_rows.append(digest_row)
            digest_bytes += len(digest_row.encode())
        digest_pages.append(digest_rows)
        lines += digest_pages[0]
        if len(digest_pages) > 1:
            stem = 'drobne' if detailed else 'zmiany'
            navigation = ' · '.join('[Dalsze tematy ' + str(i + 1) + '](' + folder + f'/{stem}-{i + 1}.md)' for i in range(1, len(digest_pages)))
            lines += ['', f"Pokazano **{len(digest_pages[0])}/{len(selected)} tematów**. " + navigation, '']
            for index, rows in enumerate(digest_pages[1:], 2):
                digest_documents[folder + f'/{stem}-{index}.md'] = '\n'.join([
                    '# Dalsze obserwacje — ' + cell(view['day']), '', '[← Podsumowanie dnia](../' + filename + ')', '',
                    f"**{cell(view['comparison']['before_day'])} → {cell(view['day'])}** · część {index}/{len(digest_pages)}", '',
                    *header, *[r.replace('](' + folder + '/', '](') for r in rows], '',
                    navigation.replace('](' + folder + '/', ']('), ''])
        if not selected:
            lines += ['| ' + ('Brak drobnych obserwacji w tym zakresie.' if detailed else 'Nie ustalono konkretnych zmian biznesowych dzień do dnia w tej części zestawienia.') + ' | | |']
        if detailed:
            lines += ['', '</details>', '']
    lines += ['', '„Nie odnotowano w tym odczycie” oznacza brak tekstu w zapisanym widoku. Nie oznacza wycofania oferty ani zakończenia promocji.', '',
              '## Grafika i wygląd', '',
              'Opisane zmiany wyglądu są powyżej; przesunięcia sekcji w rozwijanych szczegółach. Poniżej dodatkowe różnice zrzutów, dla których nie ustalono zmiany komunikatu lub oferty.', '',
              f"różnice obrazu bez jednoznacznego opisu: **{len({e['domain'] for e in visual_reviews})} pracowni**.", '',
              '<details><summary>Rozwiń dodatkowe obserwacje wyglądu</summary>', '', '| Pracownia / strona | Co wykryto | Podstawa |', '| --- | --- | --- |']
    seen_visual = set()
    for item in visual_reviews:
        key = item['domain'], item['page']
        if key in seen_visual:
            continue
        seen_visual.add(key)
        anchor = 'strona-główna' if item['page'] == 'glowna' else 'karta-projektu'
        lines += ['| ' + ' | '.join([f"[{cell(item['domain'])}]({folder}/{names[item['domain']]}.md#{anchor}) · " + ('główna' if item['page'] == 'glowna' else 'stały projekt'), cell(item['description']), 'Różnica zrzutów; przyczyna niepotwierdzona. ' + proof_links(item['evidence'], previews)]) + ' |']
    if not seen_visual:
        lines += ['| Brak dodatkowych różnic obrazu w porównaniu dzień do dnia. | | |']
    lines += ['', '</details>', '']
    lines += ['', '## Wszystkie pracownie', '', 'Kliknij pracownię, aby zobaczyć porównanie obu stron i dowody. „Bez ustalonej zmiany” dotyczy wyłącznie zapisanego zakresu.', '', '<details><summary>Rozwiń listę wszystkich pracowni i kompletność odczytów</summary>', '', '| Pracownia | Strona główna | Stała karta projektu |', '| --- | --- | --- |']
    ordered = sorted(view['rows'], key=lambda row: (not domains[row['domain']], row['domain']))
    documents = digest_documents
    for row in ordered:
        items = domains[row['domain']]
        labels = []
        for page in row['pages']:
            changes = [item for item in items if item['page'] == page['page']]
            supporting = [e for e in data['secondary'] if e['domain'] == row['domain'] and e['page'] == page['page'] and e['daily'] and e['category'] != 'ceny']
            review = any(e['domain'] == row['domain'] and e['page'] == page['page'] for e in visual_reviews)
            label = (str(len(changes)) + ' zmian · ' + ', '.join(dict.fromkeys(e['business_type'] for e in changes))) if changes else page_finding(page, [], supporting)
            labels += [cell(label + (' · obraz do obejrzenia' if review else ''))]
        lines += [f"| [{cell(row['domain'])}]({folder}/{names[row['domain']]}.md) | " + ' | '.join(labels) + ' |']
        chunks = [items[i:i + 25] for i in range(0, len(items), 25)] or [[]]
        paths = [folder + '/' + names[row['domain']] + (f'-{i + 1}' if i else '') + '.md' for i in range(len(chunks))]
        for index, chunk in enumerate(chunks):
            navigation = ' · '.join((f'**{i + 1}**' if i == index else f'[{i + 1}]({path.rsplit("/", 1)[-1]})') for i, path in enumerate(paths))
            content = ['# ' + cell(row['domain']), '', '[← Wszystkie pracownie](../' + filename + ')', '', f"**{cell(view['comparison']['before_day'])} → {cell(view['day'])}**", '', '**Ten sam projekt:** ' + link(row['name'], row['url']), '', '**' + (str(len(items)) + ' zmian w zapisanym zakresie.' if items else 'Bez ustalonych zmian biznesowych w zapisanym zakresie.' if all(p.get('communication', {}).get('daily') for p in row['pages']) else 'Niepełne porównanie — sprawdź zakres obu stron.') + '**', '', 'Pogrubione fragmenty wskazują różnicę. Dłuższe teksty pokazują otoczenie zmiany. Pełny zapis pozostaje w HTML i dzienniku CSV.', '']
            if len(chunks) > 1:
                content += ['Strony porównania: ' + navigation, '']
            for page in row['pages']:
                page_items = [item for item in chunk if item['page'] == page['page']]
                total = sum(item['page'] == page['page'] for item in items)
                content += ['## ' + cell(page['label']), '', link('Otwórz stronę źródłową', page['url']), '', '**Odczyty:** ' + when(page['compared_at']) + ' → ' + when(page['observed_at']) + ' (czas polski).', '']
                if page_items:
                    content += ['| Zmiana / miejsce | Było | Jest | Źródło |', '| --- | --- | --- | --- |', *[change_row(item) for item in page_items], '']
                    for item in page_items:
                        check = item.get('commercial_check', {})
                        if check:
                            content += ['**Wynik sprawdzenia oferty:** ' + cell(check['summary']), '', '<details><summary>Źródła i zakres weryfikacji</summary>', '']
                            for source in check.get('sources', []):
                                content += ['- ' + link('Warunki oferty', source['url']) + ': ' + cell(brief(source['text'], 600))]
                            for checked in check.get('checked_pages', []):
                                content += ['- ' + link('Sprawdzona strona', checked['url']) + ' · ' + when(checked.get('observed_at')) + ' · ' + cell('odczyt poprawny' if checked.get('complete') else checked.get('error') or 'odczyt częściowy')]
                            content += ['', cell(check.get('note', '')), '', '</details>', '']
                    long_items = [e for e in page_items if max(len(str(e['before'])), len(str(e['after']))) > 220]
                    if long_items:
                        content += ['<details><summary>Rozwinięte teksty — do 600 znaków; pełna treść w plikach raportu</summary>', '']
                        for e in long_items:
                            content += ['**' + cell(e['readout']['title']) + '**', '', '**Było:** ' + cell(brief(e['before'], 600)), '', '**Jest:** ' + cell(brief(e['after'], 600)), '']
                        content += ['</details>', '']
                elif total:
                    content += [f'Pozostałe strony tego porównania zawierają {total} różnic tej strony; użyj numerów stron powyżej.', '']
                else:
                    supporting = [e for e in data['secondary'] if e['domain'] == row['domain'] and e['page'] == page['page'] and e['daily'] and e['category'] != 'ceny']
                    content += ['**' + cell(page_finding(page, [], supporting)) + '**', '']
                if page.get('error_text'):
                    content += ['Powód braku odczytu: ' + cell(page['error_text']), '']
                if index == 0:
                    witness = next((e for e in items if e['page'] == page['page'] and proof_links(e['evidence'], previews)), None)
                    evidence = witness['evidence'] if witness else page.get('evidence', {})
                    proofs = proof_links(evidence, previews)
                    if proofs:
                        content += ['**Zapisane zrzuty:** ' + proofs, '']
                        content += proof_pair(evidence, previews, witness['before_at'] if witness else page['compared_at'], witness['after_at'] if witness else page['observed_at'])
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
                            content += [proof_links(item['evidence'], previews), '']
            if downloads.get('html'):
                content += [link('Zrzuty przed / po — pobierz pełne porównanie HTML', downloads['html']), '']
            if len(chunks) > 1:
                content += ['Strony porównania: ' + navigation, '']
            documents[paths[index]] = '\n'.join(content) + '\n'
    lines += ['', '</details>', '', link('Pliki raportu i pełne zrzuty', report_url), '']
    documents[filename] = '\n'.join(lines) + '\n'
    return documents


def render_dashboard(view: dict, report_url: str, downloads: dict | None = None, previews: dict | None = None) -> str:
    return render_dashboard_documents(view, report_url, downloads, previews)['DASHBOARD.md']
