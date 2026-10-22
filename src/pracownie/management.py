"""Management view: communication first, with page-level measurement coverage."""

from __future__ import annotations

import hashlib
import html
import re
from collections import Counter
from decimal import Decimal
from urllib.parse import urldefrag

from .journal import capture_day, relative_proof, safe_source
from .readout import digest_groups, readout
from .signals import classify, implication, summary

BUSINESS_BUCKETS = [
    ('promotions', 'Promocje i rabaty'), ('extras', 'Dodatki i pakiety'),
    ('copy', 'Komunikacja sprzedażowa'), ('terms', 'Warunki oferty'),
    ('functions', 'Funkcjonalności'), ('design', 'Zmiany wyglądu'),
]


def business_bucket(item: dict) -> str:
    # Purchase controls may carry the entire offer label. Classify the
    # business meaning without changing the original observation category.
    if item['category'] == 'funkcje':
        text = (str(item['before']) + ' ' + str(item['after'])).casefold()
        if re.search(r'\bpromocj|\brabat|p\s+r\s+o\s+m\s+o\s+c\s+j\s+a', text):
            return 'promotions'
        if re.search(r'\bpakiet|\bdodatk|\bgratis', text):
            return 'extras'
    return {'promocje': 'promotions', 'dodatki': 'extras', 'pakiety': 'extras',
            'warunki': 'terms', 'funkcje': 'functions', 'obraz': 'design'}.get(item['category'], 'copy')


def business_priority(item: dict) -> tuple:
    primary = {'promotions': 0, 'extras': 1, 'terms': 2, 'functions': 3, 'copy': 4, 'design': 6}
    rank = primary[business_bucket(item)]
    if rank == 4 and not any(word in item['description'].casefold() for word in ['nagłówek', 'baner', 'wezwanie', 'cta']):
        rank = 5
    return rank, not highlight_eligible(item), item['domain'], item['page'], item['id']


def group_changes(entries: list[dict]) -> list[dict]:
    groups = {}
    for item in entries:
        # One business change can be seen again in tabs, carousel steps or cart.
        # Keep home and the fixed project separate; retain every original ID.
        key = (item['domain'], item['page'], item['category'], item['description'],
               ' '.join(str(item['before']).split()), ' '.join(str(item['after']).split()))
        groups.setdefault(key, []).append(item)
    output = []
    for entries in groups.values():
        representative = min(entries, key=lambda e: (e.get('scenario') != 'podstawowy', e['after_at'], e['id']))
        item = dict(representative)
        item['observation_ids'] = list(dict.fromkeys(e['id'] for e in entries))
        item['contexts'] = list(dict.fromkeys(e.get('context', '') for e in entries if e.get('context')))
        item['observation_count'] = len(item['observation_ids'])
        item['business_bucket'] = business_bucket(item)
        item['business_type'] = dict(BUSINESS_BUCKETS)[item['business_bucket']]
        item['summary'] = summary(item)
        item['implication'] = implication(item)
        item['highlight_eligible'] = highlight_eligible(item)
        item['readout'] = readout(item)
        output.append(item)
    # A heading can be captured by both the copy and visual extractors.
    # Merge only exact content, time, scenario and source-page matches.
    copies = {}
    def same_capture(item):
        return (item['domain'], item['page'], item.get('scenario'), item['before_at'], item['after_at'],
                urldefrag(item['source'])[0], item['before'], item['after'])
    for item in output:
        if item['category'] != 'obraz':
            copies.setdefault(same_capture(item), []).append(item)
    merged = []
    for item in output:
        matches = copies.get(same_capture(item), [])
        if item['category'] == 'obraz' and item['description'].startswith('Widoczny nagłówek:') and len(matches) == 1:
            match = matches[0]
            match['observation_ids'].extend(item['observation_ids'])
            match['observation_count'] = len(match['observation_ids'])
        else:
            merged.append(item)
    return sorted(merged, key=business_priority)


def build_management(view: dict) -> dict:
    journal = view['journal']
    candidates = [e for e in journal if e['daily'] and e['category'] != 'ceny' and e.get('specific', e['category'] != 'obraz')]
    original, supporting = classify(candidates)
    supporting_by_id = {e['id']: e for e in supporting}
    original_ids = {e['id'] for e in original}
    meaningful = group_changes(original)
    domains = []
    for row in view['rows']:
        problems = []
        for page in row['pages']:
            communication = page.get('communication', {})
            if not page.get('current_read'):
                reason = page.get('error_text') or 'brak odczytu z dnia raportu'
            elif communication.get('daily'):
                continue
            elif page.get('data_quality', 'ok') not in {'ok', 'visual'}:
                reason = 'odczyt częściowy' + (' — ' + '; '.join(page.get('quality_notes', [])) if page.get('quality_notes') else '')
            else:
                reason = communication.get('reason') or communication.get('label') or 'brak porównywalnej bazy komunikacji'
            problems.append(page['label'] + ': ' + reason)
        domains.append({'domain': row['domain'], 'problems': problems,
                        'interaction_issues': [i for i in row['issues'] if i.startswith('Dodatkowe interakcje')],
                        'price_pair': row['domain'] in view['comparison']['price_domains']})
    all_daily = [e for e in journal if e['daily'] and e.get('specific', e['category'] != 'obraz')]
    sales = [e for e in meaningful if e['category'] != 'obraz']
    return {
        'items': meaningful,
        'source_ids': sorted(original_ids),
        'source_count': len(original),
        'secondary': [supporting_by_id.get(e['id'], e) for e in journal if e['id'] not in original_ids],
        'supporting': supporting,
        'business_buckets': [{'key': key, 'label': label,
                             'domains': len({e['domain'] for e in meaningful if e['business_bucket'] == key})}
                            for key, label in BUSINESS_BUCKETS],
        'domains': domains,
        'metrics': {
            'communication': len({e['domain'] for e in meaningful}),
            'home_changes': len({e['domain'] for e in meaningful if e['page'] == 'glowna'}),
            'project_changes': len({e['domain'] for e in meaningful if e['page'] == 'projekt'}),
            'price_cuts': len({e['domain'] for e in all_daily if e.get('selected_price') and Decimal(e.get('delta') or '0') < 0}),
            'promotions': len({e['domain'] for e in meaningful if e['business_bucket'] == 'promotions'}),
            'extras': len({e['domain'] for e in meaningful if e['business_bucket'] == 'extras'}),
            'sales': len(sales), 'changed_domains': len({e['domain'] for e in sales}),
            'visual_facts': sum(e['category'] == 'obraz' for e in meaningful),
        },
    }


def communication_summary(view: dict) -> str:
    data = build_management(view)
    pages = [p for row in view['rows'] for p in row['pages']]
    complete = sum(bool(p.get('communication', {}).get('daily')) for p in pages)
    partial = sum(p.get('current_read', False) and p.get('daily', False) and not p.get('communication', {}).get('daily') and p.get('communication', {}).get('shared_unchanged', 0) > 0 for p in pages)
    finding = ("Brakuje pełnej bazy do dziennej oceny komunikacji. " if not complete and not data['items'] else f"Ustalono {len(data['items'])} różnych zmian komunikacji w {data['metrics']['communication']} pracowniach. ")
    return (finding +
            f'Pełne porównanie zapisanego zakresu: {complete}/{len(pages)} stron. '
            f'Dla {partial} stron sprawdzono zgodność fragmentów ze starszego skanu; to porównanie częściowe.')


def page_finding(page: dict, items: list[dict], supporting: list[dict]) -> str:
    if items:
        return ' · '.join(item['summary'] for item in items[:2]) + (f' · i {len(items) - 2} dalszych zmian' if len(items) > 2 else '')
    if not page.get('current_read') or not page.get('communication', {}).get('daily'):
        return page.get('communication', {}).get('label', 'Brak porównania')
    if supporting or page.get('communication', {}).get('asset_reviews'):
        return 'Bez ustalonej zmiany · obserwacje w szczegółach'
    return 'Bez zmian w zapisanej komunikacji'


def render_management(view: dict) -> str:
    metrics = build_management(view)['metrics']
    measured = any(p.get('communication', {}).get('daily') for r in view['rows'] for p in r['pages'])
    pages = [p for row in view['rows'] for p in row['pages']]
    complete = sum(bool(p.get('communication', {}).get('daily')) for p in pages)
    overview = f"Pełne porównanie: {complete}/{len(pages)} stron. Brakujące dane nie oznaczają braku zmian."
    content = '<section class="box executive" id="executive" aria-labelledby="summary-title"><h2 id="summary-title">Podsumowanie dnia</h2><p id="management-summary" aria-live="polite">' + html.escape(overview) + '</p>'
    content += '<p class="small" id="management-scope">' + html.escape(view['comparison']['before_day']) + ' → ' + html.escape(view['day']) + ' · strona główna i ta sama karta projektu.</p></section>'
    content += '<div class="stats management-stats" id="management-stats">'
    for key, label, note in [('communication', 'Pracownie ze zmianą', 'potwierdzone komunikaty lub opisane zmiany wyglądu'), ('home_changes', 'Strony główne', 'pracowni · nagłówki, banery, CTA i treść'), ('project_changes', 'Karty projektów', 'pracowni · opis, argumenty oferty, dodatki i CTA')]:
        value = str(metrics[key]) if measured or metrics[key] else '—'
        content += '<div class="stat"><span>' + label + '</span><strong id="metric-' + key + '">' + value + '</strong><span>' + note + '</span></div>'
    content += '</div>'
    return content + render_business_summary(view)


def render_quality_panel(view: dict) -> str:
    return '<details class="box disclosure" id="measurement-scope"><summary><strong>Zakres i kompletność porównań</strong></summary><div id="quality-summary">' + render_quality_summary(view) + '</div><p class="small">Pełne = zgodne zapisy z kolejnych dni. Brak odczytu i częściowa historia nie oznaczają braku zmian.</p></details>'


def brief(value, limit=140) -> str:
    text = ' '.join(str(value or 'brak').split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def highlight_eligible(item: dict) -> bool:
    """Keep isolated navigation labels out of the executive selection only."""
    texts = [str(item[k]).strip() for k in ('before', 'after') if str(item[k]).strip().casefold() not in {'', 'brak', '—'}]
    normalized = [re.sub(r'\b(dzisiaj|dziś|jutro|wczoraj)\b', '<dzień>', text.casefold()) for text in texts]
    if len(normalized) == 2 and normalized[0] == normalized[1]:
        return False
    if item['category'] == 'obraz' and item.get('description', '').startswith('Przesunięcie:'):
        distances = [int(n) for n in re.findall(r'(\d+) px (?:w dół|w górę|w lewo|w prawo)', item['description'])]
        if distances and max(distances) < 40:
            return False
    if item['category'] in {'promocje', 'obraz'}:
        return bool(texts)
    if item['category'] in {'dodatki', 'pakiety'} and any(re.search(r'\d|\bgratis\b|w cenie|bezpłatn', text, re.I) for text in texts):
        return True
    return any(len(text) >= 24 and len(text.split()) >= 4 for text in texts)


def business_highlights(items: list[dict], limit=6) -> list[dict]:
    selected, seen = [], set()
    for item in items:
        if highlight_eligible(item) and item['domain'] not in seen:
            selected.append(item)
            seen.add(item['domain'])
        if len(selected) == limit:
            break
    return selected


def parts_html(parts: list[dict]) -> str:
    return ''.join(('<strong class="changed-token">' + html.escape(p['text']) + '</strong>') if p['changed'] else html.escape(p['text']) for p in parts)


def render_business_summary(view: dict) -> str:
    esc = html.escape
    data = build_management(view)
    groups = digest_groups(data['items'])
    measured = any(p.get('communication', {}).get('daily') for row in view['rows'] for p in row['pages'])
    content = '<section id="business-summary" class="box"><h2>Najważniejsze różnice biznesowe dzień do dnia</h2><p class="small">' + esc(view['comparison']['before_day']) + ' → ' + esc(view['day']) + ' · strona główna i ten sam projekt. Pogrubienie wskazuje zmienione słowa.</p>'
    content += '<div id="business-buckets" class="business-buckets">'
    for bucket in data['business_buckets']:
        content += '<span><strong data-business-metric="' + bucket['key'] + '">' + (str(bucket['domains']) if measured or bucket['domains'] else '—') + '</strong> ' + bucket['label'] + '</span>'
    content += '</div><div class="table-box"><table class="business-table"><thead><tr><th>Pracownia / temat</th><th>Wczoraj</th><th>Dzisiaj</th><th>Dowód i szczegóły</th></tr></thead><tbody id="business-highlights">'
    for group in groups:
        entries = group['items'][:3]
        content += '<tr data-business-domain="' + esc(group['domain'], quote=True) + '"><td data-label="Pracownia / temat"><strong>' + esc(group['domain']) + '</strong><br><span class="small">' + ('Strona główna' if group['page'] == 'glowna' else 'Stała karta projektu') + '</span><br><span class="topic">' + esc(group['business_type']) + '</span></td>'
        for side, label in [('before', 'Wczoraj'), ('after', 'Dzisiaj')]:
            content += '<td data-label="' + label + '">' + ''.join('<div class="digest-value"><small>' + (str(index + 1) + '. ' if group['count'] > 1 else '') + esc(e['readout']['title']) + '</small>' + parts_html(e['readout'][side]) + '</div>' for index, e in enumerate(entries)) + '</td>'
        content += '<td data-label="Dowód i szczegóły"><a data-company-link href="#firma-' + group['id'] + '">Porównaj przed / po</a><br><a href="' + esc(safe_source(entries[0]['source']), quote=True) + '" target="_blank" rel="noopener">Otwórz stronę</a>'
        if group['count'] > 3:
            content += '<p class="small">+' + str(group['count'] - 3) + ' dalszych zmian w szczegółach</p>'
        content += '</td></tr>'
    if not groups:
        content += '<tr><td colspan="4">Nie ustalono konkretnych zmian biznesowych dzień do dnia w sprawdzonym zakresie.</td></tr>'
    return content + '</tbody></table></div><p class="small" id="business-count">Tematy zmian: ' + str(len(groups)) + ' · pracownie: ' + str(data['metrics']['communication']) + '. Każda strona i temat ze zmianą są ujęte w tabeli.</p><p class="small">„Nie odnotowano” oznacza brak tekstu w zapisie, nie wycofanie oferty. Zrzut przedstawia uchwycony widok; jego fragment może nie obejmować wszystkich komunikatów.</p></section>'


def render_business_change(item: dict) -> str:
    esc = html.escape

    def value(side):
        text = str(item[side])
        rendered = parts_html(item['readout'][side])
        return rendered + ('<details class="long-value"><summary>Pełna treść</summary><div>' + esc(text) + '</div></details>' if len(text) > 220 else '')

    result = '<article class="firm-change daily-event" id="firma-' + item['id'] + '" data-firm-domain="' + esc(item['domain'], quote=True) + '" data-page="' + item['page'] + '" data-category="' + item['category'] + '"><strong>' + esc(item.get('business_type', item['type']) + ' · ' + item['readout']['title']) + '</strong><div class="values"><div class="value"><small>Było · ' + esc(capture_day(item['before_at'])) + '</small>' + value('before') + '</div><div class="value after"><small>Jest · ' + esc(capture_day(item['after_at'])) + '</small>' + value('after') + '</div></div><p><a href="' + esc(safe_source(item['source']), quote=True) + '" target="_blank" rel="noopener">Otwórz zmienione miejsce</a>'
    if any(item['evidence'].get(k) for k in ('przed', 'po', 'fragment_przed', 'fragment_po')):
        result += ' · <a href="#firma-dowod-' + evidence_id(item['evidence'], item['domain'], item['page']) + '">Zrzuty przed / po</a>'
    result += '</p>'
    if item['readout']['note']:
        result += '<p class="small">' + esc(item['readout']['note']) + '</p>'
    if item['observation_count'] > 1:
        result += '<details class="contexts"><summary>Ten sam komunikat w ' + str(item['observation_count']) + ' odczytach</summary><p class="small">' + esc(' · '.join(item['contexts'])) + '</p></details>'
    return result + '</article>'


def evidence_id(evidence: dict, domain: str, page: str) -> str:
    return hashlib.sha256(repr((domain, page, sorted(evidence.items()))).encode()).hexdigest()[:14]


def render_business_proofs(day: str, items: list[dict]) -> str:
    parts, seen = [], set()
    for item in items:
        key = evidence_id(item['evidence'], item['domain'], item['page'])
        if not item['evidence'] or key in seen:
            continue
        seen.add(key)
        evidence = item['evidence']
        cropped = evidence.get('fragment_przed') and evidence.get('fragment_po')
        pictures = []
        for field, label in [('fragment_przed' if cropped else 'przed', 'Przed'), ('fragment_po' if cropped else 'po', 'Po')]:
            path = relative_proof(day, evidence.get(field, ''))
            if path:
                pictures.append('<figure><a href="' + html.escape(path, quote=True) + '" target="_blank" rel="noopener"><img loading="lazy" src="' + html.escape(path, quote=True) + '" alt="' + label + ' — ' + html.escape(item['domain'], quote=True) + '"><figcaption>' + label + '</figcaption></a></figure>')
        if pictures:
            parts.append('<details class="firm-proof"><summary>Zrzuty: ' + html.escape(brief(item['description'], 70)) + '</summary><div class="proofs" id="firma-dowod-' + key + '">' + ''.join(pictures) + '</div></details>')
    return ''.join(parts)


def render_quality_summary(view: dict) -> str:
    total = len(view['rows'])
    pages = [p for row in view['rows'] for p in row['pages']]
    content = '<div class="quality-grid">'
    for page, label in [('glowna', 'Strony główne'), ('projekt', 'Karty projektów')]:
        scoped = [p for p in pages if p['page'] == page]
        complete = sum(bool(p.get('communication', {}).get('daily')) for p in scoped)
        partial = sum(p.get('daily', False) and p.get('current_read', False) and not p.get('communication', {}).get('daily') and p.get('communication', {}).get('shared_unchanged', 0) > 0 for p in scoped)
        fresh = sum(bool(p.get('current_read')) for p in scoped)
        content += f'<p><strong>{complete}/{total}</strong> {label}: pełne porównanie<br><span class="small">Fragmenty: {partial}/{total} · odczyt dzisiaj: {fresh}/{total}</span></p>'
    ready = sum(bool(p.get('current_read')) and bool(p.get('communication', {}).get('ready')) for p in pages)
    equal = sum(bool(p.get('current_read')) and bool(p.get('daily')) and bool(p.get('communication', {}).get('same_visible_image')) for p in pages)
    return content + f'<p><strong>{ready}/{total * 2}</strong> Nowa baza komunikacji<br><span class="small">Strony gotowe do kolejnego porównania</span></p></div><p class="small">Identyczne zrzuty z obu dni: {equal} stron. Potwierdzają tylko brak różnic w uchwyconym widoku, z uwzględnieniem masek i limitu wysokości.</p>'


def render_communication_table(view: dict) -> str:
    esc = html.escape
    content = '<section id="communication-coverage" class="box"><h2>Porównanie dzień do dnia — każda pracownia</h2><p class="small">Jedna stała karta projektu i strona główna. Wybierz pracownię, aby zobaczyć treści przed / po i zrzuty. „Częściowe” nie oznacza „bez zmian”.</p><div class="table-box" tabindex="0" role="region" aria-label="Komunikacja we wszystkich pracowniach"><table class="communication-table"><thead><tr><th>Pracownia / stały projekt</th><th data-communication-header="glowna">Strona główna</th><th data-communication-header="projekt">Stała karta projektu</th><th>Porównanie i źródła</th></tr></thead><tbody>'
    management = build_management(view)
    items = management['items']
    for row in sorted(view['rows'], key=lambda r: (not any(e['domain'] == r['domain'] for e in items), r['domain'])):
        content += '<tr data-communication-domain="' + esc(row['domain'], quote=True) + '"><td><strong>' + esc(row['domain']) + '</strong><br><span class="small">Stały projekt: ' + ('<a href="' + esc(safe_source(row['url']), quote=True) + '" target="_blank" rel="noopener">' + esc(row['name']) + '</a>' if safe_source(row['url']) else esc(row['name'])) + '</span></td>'
        for page in row['pages']:
            stamp = (capture_day(page['compared_at']) or 'brak bazy') + ' → ' + (capture_day(page['observed_at']) or 'brak odczytu')
            page_items = [e for e in items if e['domain'] == row['domain'] and e['page'] == page['page']]
            supporting = [e for e in management['secondary'] if e['domain'] == row['domain'] and e['page'] == page['page'] and e['daily'] and e['category'] != 'ceny']
            label = page_finding(page, page_items, supporting)
            content += '<td data-communication-page="' + page['page'] + '"><strong data-change-label data-fallback="' + esc(page_finding(page, [], supporting), quote=True) + '">' + esc(label) + '</strong><br><span class="small">' + esc(stamp) + '</span>'
            categories = Counter(e['business_bucket'] for e in page_items)
            for key, title in BUSINESS_BUCKETS:
                if categories[key]:
                    content += '<span class="category-count" data-communication-change-page="' + page['page'] + '" data-business-bucket="' + key + '">' + esc(title) + ': ' + str(categories[key]) + '</span>'
            content += '</td>'
        content += '<td><p><a class="company-link" data-company-link href="#pracownia-' + esc(row['domain'], quote=True) + '">Porównaj obie strony</a></p>'
        for p in row['pages']:
            if p['url']:
                content += '<a data-communication-source-page="' + p['page'] + '" href="' + esc(p['url'], quote=True) + '" target="_blank" rel="noopener">' + ('Główna' if p['page'] == 'glowna' else 'Projekt') + '</a> · '
        content += '</td></tr>'
    return content + '</tbody></table></div></section>'


def render_availability(view: dict) -> str:
    esc = html.escape
    data = build_management(view)
    missing = sum(not r['home_read'] or not r['project_read'] for r in view['rows'])
    content = '<details class="box disclosure" id="availability"><summary><strong>Dlaczego brakuje pełnego porównania?</strong><span class="small">Brak odczytu: ' + str(missing) + ' pracowni</span></summary><p class="small">Starsze, węższe skany nie zawierają pełnej historii komunikacji. Nowy zapis naprawia kolejne porównania; nie odtwarza brakujących treści z przeszłości. Blokada witryny ani błąd skanu nie oznaczają braku zmian.</p><div class="table-box"><table class="availability-table"><thead><tr><th>Pracownia</th><th>Przyczyna / zakres</th></tr></thead><tbody>'
    for domain in sorted(data['domains'], key=lambda d: (not bool(d['problems']), d['domain'])):
        d = esc(domain['domain'], quote=True)
        content += '<tr data-availability-domain="' + d + '"><td><strong>' + d + '</strong><br><button class="watch-button" data-watch="' + d + '" aria-pressed="false" aria-label="Obserwuj ' + d + '">☆ Obserwuj</button></td><td><ul class="quality-reasons">' + ''.join('<li>' + esc(p) + '</li>' for p in domain['problems'] + domain['interaction_issues']) + '</ul><a href="#pracownia-' + d + '">Szczegóły i zapisane dowody</a></td></tr>'
    return content + '</tbody></table></div></details>'
