"""Business relationships supplied by the owner, independent of scan results."""
from __future__ import annotations

import json
from pathlib import Path

from bs4 import BeautifulSoup

LABELS = {'partner': 'Współpracujące z nami', 'other': 'Niewspółpracujące z nami'}


def relationship_snapshot(domains: list[str], directory: Path = Path('config')) -> dict:
    registry_path, sites_path = directory/'partners.json', directory/'sites.json'
    if not registry_path.is_file() or not sites_path.is_file():
        return {}
    configured = {s['domain'] for s in json.loads(sites_path.read_text())['sites']}
    # Separate experiments and synthetic fixtures must not acquire production
    # partner identities merely because they use the same rendering code.
    if not domains or not set(domains) <= configured:
        return {}
    registry = json.loads(registry_path.read_text())
    if registry.get('schema') != 1 or not registry['source'].get('complete'):
        raise ValueError('Podział wymaga potwierdzonej pełnej listy współpracujących pracowni')
    partners = {p['domain']: p for p in registry['partners'] if p.get('domain')}
    return {'source': registry['source'],
            'domains': {d: {'group': 'partner' if d in partners else 'other',
                            'name': partners[d]['name'] if d in partners else d,
                            'code': partners[d]['code'] if d in partners else ''} for d in domains},
            'without_website': [p for p in registry['partners'] if not p.get('domain')]}


def apply_relationships(view: dict) -> None:
    context = view.get('metadata', {}).get('relationships', {})
    if not context:
        return
    for row in view['rows']:
        item = context['domains'].get(row['domain'], {})
        row.update(relationship=item.get('group', 'other'), studio_name=item.get('name', row['domain']),
                   partner_code=item.get('code', ''))


def groups(view: dict) -> list[tuple[str, str]]:
    return list(LABELS.items()) if view.get('metadata', {}).get('relationships') else [('all', '')]


def group_for(view: dict, domain: str) -> str:
    return view.get('metadata', {}).get('relationships', {}).get('domains', {}).get(domain, {}).get('group', 'all')


def registry_markdown(view: dict) -> list[str]:
    context = view.get('metadata', {}).get('relationships', {})
    if not context:
        return []
    from .dashboard import cell

    rows = context.get('without_website', [])
    lines = ['', 'Podział według pełnej listy współpracujących pracowni z ' + context['source']['as_of'] + '.', '']
    if rows:
        lines += ['<details><summary>Współpracujące bez strony WWW (' + str(len(rows)) + ')</summary>', '',
                  'Te pracownie nie mają stron WWW; są w wykazie partnerów i nie są skanowane.', '',
                  '| Kod | Pracownia | Status |', '| --- | --- | --- |']
        lines += ['| ' + cell(p['code']) + ' | ' + cell(p['name']) + ' | Bez strony WWW |' for p in rows]
        lines += ['', '</details>', '']
    return lines


def group_html(document: str, view: dict) -> str:
    """Group existing evidence in place; keep its IDs, dates and source links."""
    context = view.get('metadata', {}).get('relationships', {})
    if not context:
        return document
    soup = BeautifulSoup(document, 'html.parser')

    def heading(group: str, tag: str = 'tr', columns: int = 4):
        node = soup.new_tag(tag, attrs={'data-relationship-heading': group})
        content = soup.new_tag('th', colspan=str(columns)) if tag == 'tr' else node
        content.append(LABELS[group] + ' · ')
        count = soup.new_tag('span', attrs={'data-relationship-count': group})
        count.string = str(sum(group_for(view, r['domain']) == group for r in view['rows']))
        content.append(count)
        content.append(' serwisów')
        if tag == 'tr':
            node.append(content)
        return node

    events = {e['id']:e for e in view['briefing']['events']}
    for tier in ('main', 'review'):
        body = soup.select_one('#brief-' + tier + ' tbody')
        entries = list(body.select('[data-brief-id]'))
        original_empty = body.select_one('[data-brief-empty]')
        body.clear()
        for group in LABELS:
            body.append(heading(group))
            selected = [tr for tr in entries if group_for(view, events[tr['data-brief-id']]['domain']) == group]
            for index, tr in enumerate(selected):
                tr['data-rel-group'] = group
                tr.attrs.pop('hidden', None)
                tr.attrs.pop('data-brief-extra', None)
                if tier == 'main' and index >= 5:
                    tr['hidden'], tr['data-brief-extra'] = '', ''
                body.append(tr)
            empty = soup.new_tag('tr', attrs={'data-relationship-empty':group, 'data-relationship-area':tier})
            if selected:
                empty['hidden'] = ''
            cell = soup.new_tag('td', colspan='4')
            cell.string = 'Nie ustalono zmian w tej grupie.' if tier == 'main' else 'Brak ważnych nierozstrzygniętych sygnałów w tej grupie.'
            empty.append(cell)
            body.append(empty)
        original_empty['hidden'] = ''
        body.append(original_empty)
    extra = sum(max(0, sum(e['tier']=='main' and group_for(view,e['domain'])==group for e in events.values())-5) for group in LABELS)
    more = soup.select_one('#brief-more')
    more.string = 'Pozostałe ważne zmiany (' + str(extra) + ')'
    if extra:
        more.attrs.pop('hidden', None)
    else:
        more['hidden'] = ''

    company_rows = list(soup.select('[data-communication-domain]'))
    if company_rows:
        body = company_rows[0].find_parent('tbody')
        body.clear()
        for group in LABELS:
            body.append(heading(group, columns=len(body.parent.select('thead th'))))
            for tr in company_rows:
                if group_for(view,tr['data-communication-domain']) == group:
                    info = context['domains'].get(tr['data-communication-domain'], {})
                    if info.get('code'):
                        identity = soup.new_tag('p', attrs={'class':'small'})
                        identity.string = info['name'] + ' · ' + info['code']
                        tr.find('td').append(identity)
                    body.append(tr)
    daily = soup.select_one('#daily')
    details = list(daily.select('.day-domain'))
    daily.clear()
    for group in LABELS:
        daily.append(heading(group, tag='h3'))
        for item in details:
            if group_for(view,item['data-domain']) == group:
                daily.append(item)

    label = soup.new_tag('label', attrs={'class':'relationship-select'})
    label.append('Współpraca ')
    select = soup.new_tag('select', id='relationship-filter', attrs={'aria-label':'Współpraca z pracownią'})
    for value, text in [('all','Obie grupy'), *LABELS.items()]:
        option = soup.new_tag('option', value=value)
        option.string = text
        select.append(option)
    label.append(select)
    soup.select_one('.filter-disclosure').insert_before(label)
    note = soup.new_tag('p', id='relationship-no-web-note', attrs={'class':'small','role':'status','hidden':''})
    soup.select_one('.quick-filters').insert_after(note)
    without = context.get('without_website', [])
    if without:
        block = soup.new_tag('details', id='without-websites', attrs={'class':'disclosure'})
        summary = soup.new_tag('summary')
        summary.append('Współpracujące bez strony WWW (')
        count = soup.new_tag('span', id='without-websites-count')
        count.string = str(len(without))
        summary.extend([count, ')'])
        block.append(summary)
        paragraph = soup.new_tag('p', attrs={'class':'small'})
        paragraph.string = 'Firmy potwierdzone jako współpracujące; nie mają stron WWW i nie są skanowane.'
        block.append(paragraph)
        listing = soup.new_tag('ul')
        for p in without:
            item = soup.new_tag('li', attrs={'data-no-website-partner':(p['name']+' '+p['code']).casefold()})
            item.string = p['name'] + ' · ' + p['code'] + ' · Bez strony WWW'
            listing.append(item)
        block.append(listing)
        soup.select_one('.directory').insert_after(block)
    style = soup.new_tag('style')
    style.string = '[data-relationship-heading] th{background:#e8f1ed;padding:12px;text-align:left;font-size:14px;text-transform:none;letter-spacing:0}[data-relationship-heading] span{font-weight:400}.relationship-select{display:grid;gap:5px;font-size:12px}.relationship-select select{max-width:100%;padding:10px;border:1px solid var(--line);border-radius:7px;background:white;color:var(--ink)}@media(max-width:760px){.business-table tr[data-relationship-heading] th{display:block;width:100%!important}}'
    soup.head.append(style)
    return str(soup)
