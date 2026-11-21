"""The same offer evidence in the GitHub dashboard, printable text and web report."""
from __future__ import annotations

import html
from dataclasses import dataclass, field

from .journal import relative_proof, safe_source
from .relationships import LABELS, group_for
from .weekly import METRICS

FIELDS = {'value': 'Rabat', 'scope': 'Zakres', 'minimum': 'Minimum zakupu',
          'stacking': 'Łączenie promocji', 'expiry': 'Termin', 'effective_price': 'Cena po rabacie',
          'unavailable': 'Dostępność'}
PAGES = {'glowna': 'Strona główna', 'projekt': 'Karta projektu', 'terms': 'Strona warunków'}
STATES = {'included': 'w cenie', 'paid': 'za dopłatą', 'unavailable': 'niedostępny'}
ZONES = {'first': 'pierwszy ekran', 'lower': 'poniżej pierwszego ekranu'}
TITLES = {'terms': 'Zmiany warunków promocji', 'extras': 'Co klient dostaje w cenie projektu',
          'placement': 'Widoczność tej samej oferty', 'cards': 'Od baneru do ceny projektu',
          'register': 'Odczytane warunki ofert'}


@dataclass
class Finding:
    domain: str
    title: str
    lines: list[str] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)


def _quote(record):
    from .presentation import when
    return '„' + record['quote'] + '” · ' + when(record['observed_at'])


def _term_value(key, record):
    if key == 'unavailable':
        return 'źródło oznacza ofertę jako niedostępną' if record[key] else 'brak oznaczenia niedostępności'
    return record.get(key, '')


def findings(view: dict) -> dict[str, list[Finding]]:
    items = {name: [] for name in TITLES}
    data = view.get('metadata', {}).get('intelligence', {})
    for entry in data.get('promo_terms', []):
        before, after = entry.get('before'), entry.get('after')
        observed = after or before
        status = entry['status']
        name = entry['code'] or entry['campaign'] or 'Oferta'
        place = PAGES[entry['page']]
        if status in {'changed', 'appeared', 'missing'}:
            title = {'changed': 'Zmiana warunków', 'appeared': 'Pojawił się komunikat',
                     'missing': 'Komunikat zniknął z tej strony'}[status]
            row = Finding(entry['domain'], title + ' · ' + name)
            row.lines.extend(FIELDS[k] + ' · ' + _term_value(k, before) + ' → ' + _term_value(k, after)
                             for k in entry['changed_fields'])
            if before:
                row.lines.append('Wczoraj · ' + _quote(before))
            if after:
                row.lines.append('Dziś · ' + _quote(after))
            if status == 'missing':
                row.lines.append('Dostępność promocji w pozostałych miejscach wymaga odrębnego potwierdzenia.')
            row.links.append((place, observed['source']))
            items['terms'].append(row)
        if after:
            row = Finding(entry['domain'], name + ' · ' + place)
            row.lines += [FIELDS[k] + ' · ' + after[k] for k in FIELDS if k != 'unavailable' and after.get(k)]
            if after.get('unavailable'):
                row.lines.insert(0, 'Pracownia oznacza tę ofertę jako niedostępną.')
            row.lines.append(_quote(after))
            row.links.append((place, after['source']))
            items['register'].append(row)
    for extra in data.get('package_changes', []):
        row = Finding(extra['domain'], extra['name'] + ' · ' + STATES[extra['before_state']] + ' → ' + STATES[extra['after_state']])
        row.lines.append(extra['project'] + (' · ' + extra['context'] if extra.get('context') else ''))
        from .presentation import when
        row.lines += ['Wczoraj · ' + extra['before'] + ' · ' + when(extra['before_at']),
                      'Dziś · ' + extra['after'] + ' · ' + when(extra['after_at'])]
        if extra.get('unchanged_price'):
            row.lines.append('Cena bazowa projektu w obu dniach · ' + extra['unchanged_price'])
        row.links.append(('Otwórz kartę projektu', extra['source']))
        row.evidence = extra['evidence']
        items['extras'].append(row)
    for item in view.get('journal', []):
        placement = item.get('offer_placement')
        if not placement or not item.get('daily'):
            continue
        items['placement'].append(Finding(item['domain'], ZONES[placement['before']].capitalize() + ' → ' + ZONES[placement['after']],
                                          ['„' + placement['text'] + '”'], [(PAGES[item['page']], item['source'])], item['evidence']))
    for card in data.get('campaign_cards', []):
        home = card['home'][0]
        row = Finding(card['domain'], ' · '.join(home['codes']) or 'Oferta na stronie głównej')
        row.lines.append('Strona główna · ' + _quote(home))
        row.links.append(('Baner lub komunikat', home['source']))
        linked = [t for t in card['terms'] if t['page'] == 'terms']
        if not linked:
            row.lines.append('Osobna strona warunków · brak dopasowanego zapisu z tego dnia.')
        for term in linked:
            row.lines.append('Warunki · ' + _quote(term))
            row.links.append(('Warunki promocji', term['source']))
        row.lines += [card['project_name'] + ' · ' + card['scope']['label']]
        if card['project']:
            specific = card['project'][0]
            row.lines.append('Komunikat na karcie · ' + _quote(specific))
            row.links.append(('Komunikat na karcie', specific['source']))
        cited = {(r['source'], r['quote']) for r in [home, *linked, *card['project'][:1]]}
        for record in card['scope']['evidence']:
            identity = record['source'], record['quote']
            if identity not in cited:
                cited.add(identity)
                row.lines.append('Zapis zakresu · ' + _quote(record))
                row.links.append(('Źródło zakresu', record['source']))
        row.lines.append('Cena na karcie · ' + card['price']['text'])
        if card['project_url']:
            row.links.append(('Stała karta projektu', card['project_url']))
        for effective in card['effective_price']:
            row.lines.append('Cena po kodzie podana przez pracownię · ' + effective['value'])
            row.links.append(('Źródło ceny po kodzie', effective['source']))
        items['cards'].append(row)
    code_domains = {c['domain'] for c in data.get('campaign_cards', []) if c['home'][0]['codes']}
    for key, rows in items.items():
        rows.sort(key=lambda r: (group_for(view, r.domain) != 'partner', key == 'cards' and r.domain not in code_domains, r.domain))
    return items


def availability(view, key):
    data = view.get('metadata', {}).get('intelligence', {})
    if key == 'placement':
        coverage = data.get('placement_pages', {})
        n = coverage.get('compared', 0)
        return (f"Porównano położenie na {n} stronach. Ten sam komunikat ofertowy udało się zlokalizować w obu dniach na {coverage.get('matched', 0)}." if n else
                'Brak pary pomiarów położenia. Pierwsze porównanie wymaga odczytu tej samej strony i rozmiaru okna w dwóch kolejnych dniach.')
    return {'extras': 'Brak udokumentowanego przejścia między dopłatą, dostępnością i wliczeniem dodatku w cenę.',
            'terms': 'Brak udokumentowanej różnicy warunków w porównanych cytatach.',
            'cards': 'Brak odczytanego komunikatu ofertowego na stronie głównej spełniającego kryteria zestawienia.',
            'register': 'Brak warunków przypisanych do konkretnego kodu lub oferty.'}[key]


def _who(view, row):
    group = {'partner': 'współpracująca', 'other': 'niewspółpracująca'}.get(group_for(view, row.domain), '')
    return row.domain + (' · ' + group if group else '')


def _weekly_tables(weekly):
    for group, label in LABELS.items():
        cells = {name: period['groups'][group] for name, period in weekly.items() if name in {'previous', 'current'}}
        rows = []
        for key, metric in METRICS.items():
            values = []
            for name in ('previous', 'current'):
                result = cells[name]['metrics'][key]
                denominator = result['compared']
                values.append(f"{result['count']} / {denominator}" if result['count'] is not None and denominator else 'brak pomiaru')
            rows.append((metric, *values))
        yield group, label, rows


def _week_title(period):
    return period['start'] + ' – ' + period['end'] + f" ({len(period['days'])}/7 dni)"


def _weekly_notes(weekly):
    notes = ['Każda pracownia liczy się raz w danym wierszu i tygodniu. Po ukośniku podano liczbę pracowni z odpowiednim porównaniem przynajmniej jednego dnia.']
    for name in ('previous', 'current'):
        period = weekly[name]
        if period['missing_days']:
            notes.append('Brak zachowanych pomiarów · ' + ', '.join(period['missing_days']))
    return notes


def _week_examples(weekly):
    for period in ('current', 'previous'):
        for group, label in LABELS.items():
            for metric, metric_label in METRICS.items():
                for example in weekly[period]['groups'][group]['metrics'][metric]['examples']:
                    yield Finding(example['domain'], metric_label, [example['day'] + ' · ' + label,
                                  example['before'] + ' → ' + example['after']], [('Źródło', example['source'])])


def _md_row(view, row, previews):
    from .dashboard import cell, link, proof_links
    lines = ['**' + cell(_who(view, row)) + '** · ' + cell(row.title)]
    lines.extend(cell(line) for line in row.lines)
    links = [link(label, url) for label, url in dict.fromkeys(row.links) if safe_source(url)]
    proof = proof_links(row.evidence, previews)
    if proof:
        links.append(proof)
    if links:
        lines.append(' · '.join(links))
    return '- ' + '<br>'.join(lines)


def featured_campaign(data):
    coded = next((c for c in data.get('campaign_cards', []) if c['home'][0]['codes'] and c['price']['status'] == 'changed'
                  and c['scope']['status'] not in {'expired', 'scheduled', 'unverified_period', 'conflicting',
                                                  'explicitly_excluded', 'missing_project'}), None)
    if not coded:
        return None
    home = coded['home'][0]
    benefit = next((r['value'] for r in coded['terms'] if r['page'] == 'projekt' and r.get('value')), '')
    statement = 'Karta ' + coded['project_name'] + ' · ' + coded['price']['text']
    note = 'Komunikat na karcie podaje rabat ' + benefit + '.' if benefit else coded['scope']['label']
    return Finding(coded['domain'], ' · '.join(home['codes']), [home['quote'], note, statement],
                   [('Strona główna', home['source']), ('Karta projektu', coded['project_url'])])


def markdown_documents(view, folder, filename, previews, shown=()):
    """Keep the overview short; separate large quote registers into small GitHub files."""
    from .dashboard import cell
    data = view.get('metadata', {}).get('intelligence', {})
    if 'promo_terms' not in data:
        return [], {}
    items = findings(view)
    base = 'porownanie-ofert'
    weekly = data.get('weekly')
    title = 'Promocje, dodatki i ceny projektu'
    summary = []
    coded = featured_campaign(data)
    if coded and coded.domain not in shown:
        summary += [_md_row(view, coded, previews)]
    for key in ('terms', 'extras', 'placement'):
        candidate = next((r for r in items[key] if r.domain not in shown and (not coded or r.domain != coded.domain)
                          and (key != 'terms' or r.title.startswith('Zmiana warunków'))), None)
        if candidate:
            summary.append(_md_row(view, candidate, previews))
            if len(summary) == 2:
                break
    summary += ['', f'[**{title}**]({folder}/{base}.md) · [Tydzień do tygodnia]({folder}/{base}.md#tydzień-do-tygodnia)', '']
    heading = ['# ' + title, '', '**' + view['comparison']['before_day'] + ' → ' + view['day'] + '**',
               '', '[← Dashboard](../' + filename + ')', '']
    index, documents = list(heading), {}
    for key, rows in items.items():
        index += ['## ' + TITLES[key], '']
        if key == 'cards' and rows:
            example = next((r for r in rows if coded and r.domain == coded.domain and r.title == coded.title), rows[0])
            index += [_md_row(view, example, previews), '']
        if not rows or key == 'placement':
            index += [availability(view, key), '']
        if not rows:
            continue
        if key == 'cards':
            index += ['Zestawienie dotyczy ofert obecnych w dzisiejszym odczycie. Cena na karcie pochodzi z osobnego pomiaru.', '']
        if key == 'register':
            index += ['Każdy wpis podaje warunki widoczne w cytacie. Skan sprawdza stronę główną, kartę projektu i maksymalnie dwie powiązane strony HTML. Warunki dostępne wyłącznie w PDF lub koszyku pozostają niezweryfikowane.', '']
        if key not in ('cards', 'register') and len(rows) <= 8:
            index += [_md_row(view, r, previews) + '\n' for r in rows]
            continue
        for start in range(0, len(rows), 10):
            chunk = rows[start:start+10]
            part = f'{base}-{key}-{start // 10 + 1}.md'
            documents[folder + '/' + part] = '\n'.join(['# ' + TITLES[key], '', '[← Porównanie ofert](' + base + '.md)', '', view['day'], '',
                                                          *[_md_row(view, r, previews) + '\n' for r in chunk]])
            studios = ', '.join(dict.fromkeys(r.domain for r in chunk))
            index += [f'- [Wpisy {start+1}–{start+len(chunk)} · {cell(studios)}]({part})']
        index.append('')
    index += ['## Tydzień do tygodnia', '']
    if weekly:
        prev, cur = _week_title(weekly['previous']), _week_title(weekly['current'])
        index += [*_weekly_notes(weekly), '']
        for _group, label, rows in _weekly_tables(weekly):
            index += ['### ' + label, '', f'| Liczba pracowni | {prev} | {cur} |', '| --- | ---: | ---: |',
                      *['| ' + ' | '.join(row) + ' |' for row in rows], '']
        examples = list(_week_examples(weekly))
        for start in range(0, len(examples), 30):
            part = f'{base}-tydzien-{start // 30 + 1}.md'
            chunk = examples[start:start+30]
            index += [f'[Pracownie, daty i źródła · wpisy {start+1}–{start+len(chunk)}]({part})', '']
            documents[folder + '/' + part] = '\n'.join(['# Pracownie w zestawieniu tygodniowym', '', '[← Porównanie tygodni](' + base + '.md#tydzień-do-tygodnia)', '',
                                                        *[_md_row(view, row, previews) + '\n' for row in chunk]])
    else:
        index += ['Brak archiwalnych pomiarów tygodniowych.', '']
    documents[folder + '/' + base + '.md'] = '\n'.join(index) + '\n'
    return summary, documents



def offer_overview(view):
    data = view.get('metadata', {}).get('intelligence', {})
    if 'promo_terms' not in data:
        return []
    items = findings(view)
    weekly = data.get('weekly', {})
    if not any(items.values()) and not any(period['days'] for period in weekly.values()):
        return []
    lines = ['### Promocje, dodatki i ceny projektu', '']
    for key in ('terms', 'extras', 'placement'):
        if items[key]:
            lines.append(_md_row(view, items[key][0], {}) + '\n')
    if weekly := data.get('weekly'):
        lines += ['Porównanie tygodni · ' + _week_title(weekly['previous']) + ' → ' + _week_title(weekly['current']) + '.', '']
    lines += ['Szczegółowe warunki, ceny na stałych kartach i podział pracowni są w raporcie HTML i TXT.', '']
    return lines

def text_report(view):
    data = view.get('metadata', {}).get('intelligence', {})
    if 'promo_terms' not in data:
        return []
    lines = ['PROMOCJE, DODATKI I CENY PROJEKTU', '']
    for key, rows in findings(view).items():
        lines += [TITLES[key].upper()]
        if not rows or key == 'placement':
            lines += [availability(view, key)]
        for row in rows:
            lines += [_who(view, row) + ' | ' + row.title, *row.lines,
                      *[label + ' · ' + url for label, url in dict.fromkeys(row.links) if safe_source(url)], '']
        lines.append('')
    if weekly := data.get('weekly'):
        lines += ['TYDZIEŃ DO TYGODNIA', *_weekly_notes(weekly), '']
        for _group, label, rows in _weekly_tables(weekly):
            lines += [label, ' | '.join(['Liczba pracowni', _week_title(weekly['previous']), _week_title(weekly['current'])]),
                      *[' | '.join(row) for row in rows], '']
        for row in _week_examples(weekly):
            lines += [row.domain + ' · ' + row.title, *row.lines, row.links[0][1]]
    return lines


def _html_row(view, row):
    esc = html.escape
    links = ['<a href="' + esc(url) + '">' + esc(label) + '</a>' for label, url in dict.fromkeys(row.links) if safe_source(url)]
    pictures = []
    fields = ('fragment_przed', 'fragment_po') if all(row.evidence.get(k) for k in ('fragment_przed', 'fragment_po')) else ('przed', 'po')
    for key, label in zip(fields, ('Przed', 'Po'), strict=True):
        path = relative_proof(view['day'], row.evidence.get(key, ''))
        if path:
            pictures.append('<figure><a href="' + path + '"><img loading="lazy" src="' + path + '" alt="' + label
                            + '"></a><figcaption>' + label + '</figcaption></figure>')
    return ('<li data-intelligence-domain="' + esc(row.domain) + '"><strong>' + esc(_who(view, row)) + '</strong> · ' + esc(row.title)
            + ''.join('<div>' + esc(line) + '</div>' for line in row.lines) + '<div>' + ' · '.join(links) + '</div>'
            + ('<details><summary>Porównaj zrzuty</summary>' + ''.join(pictures) + '</details>' if len(pictures) == 2 else '') + '</li>')


def html_report(view):
    data = view.get('metadata', {}).get('intelligence', {})
    if 'promo_terms' not in data:
        return ''
    blocks = ['<section id="offer-comparison" class="box"><h2>Promocje, dodatki i ceny projektu</h2>']
    items = findings(view)
    top = featured_campaign(data) or next((r for key in ('terms', 'extras', 'placement') for r in items[key]), None)
    if top:
        blocks += ['<ul class="offer-headline">', _html_row(view, top), '</ul>']
    if data.get('weekly'):
        blocks.append('<p><a href="#business-week">Porównaj dwa ostatnie tygodnie</a></p>')
    for key, rows in items.items():
        blocks += ['<details data-offer-section><summary>' + TITLES[key] + f' (<span data-offer-count>{len(rows)}</span>)</summary>']
        if rows:
            blocks += ['<p data-offer-empty hidden>Brak wpisów dla wybranych pracowni.</p>']
        if not rows or key == 'placement':
            blocks += ['<p>' + availability(view, key) + '</p>']
        blocks += ['<ul>' + ''.join(_html_row(view, row) for row in rows) + '</ul></details>']
    if weekly := data.get('weekly'):
        blocks += ['<details id="business-week"><summary>Tydzień do tygodnia</summary><p>Liczby obejmują całą grupę pracowni w danym tygodniu.</p>', *['<p>' + s + '</p>' for s in _weekly_notes(weekly)]]
        for group, label, rows in _weekly_tables(weekly):
            blocks += ['<div data-week-group="' + group + '"><h3>' + label + '</h3><div class="table-box"><table><thead><tr><th>Liczba pracowni</th><th>'
                       + _week_title(weekly['previous']) + '</th><th>' + _week_title(weekly['current']) + '</th></tr></thead><tbody>',
                       *['<tr>' + ''.join('<td>' + cell + '</td>' for cell in row) + '</tr>' for row in rows], '</tbody></table></div></div>']
        blocks += ['<details><summary>Pracownie i źródła</summary><ul>', *[_html_row(view, row) for row in _week_examples(weekly)], '</ul></details></details>']
    return ''.join(blocks) + '</section>'
