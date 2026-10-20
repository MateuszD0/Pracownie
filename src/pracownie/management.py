"""Management view: communication first, with page-level measurement coverage."""

from __future__ import annotations

import html
from decimal import Decimal

from .journal import capture_day


def build_management(view: dict) -> dict:
    journal = view['journal']
    meaningful = [e for e in journal if e['daily'] and e['category'] != 'ceny' and e.get('specific', e['category'] != 'obraz')]
    priority = {'promocje': 0, 'komunikacja': 1, 'tresc': 1, 'dodatki': 2, 'pakiety': 2, 'warunki': 3, 'funkcje': 3, 'obraz': 4, 'parametry': 5}
    meaningful.sort(key=lambda e: (priority.get(e['category'], 5), e['domain'], e['page'], e['id']))
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
        'secondary': [e for e in journal if e not in meaningful],
        'domains': domains,
        'metrics': {
            'communication': len({e['domain'] for e in meaningful}),
            'home_changes': len({e['domain'] for e in meaningful if e['page'] == 'glowna'}),
            'project_changes': len({e['domain'] for e in meaningful if e['page'] == 'projekt'}),
            'price_cuts': len({e['domain'] for e in all_daily if e.get('selected_price') and Decimal(e.get('delta') or '0') < 0}),
            'promotions': len({e['domain'] for e in meaningful if e['category'] == 'promocje'}),
            'extras': len({e['domain'] for e in meaningful if e['category'] in {'dodatki', 'pakiety'}}),
            'sales': len(sales), 'changed_domains': len({e['domain'] for e in sales}),
            'visual_facts': sum(e['category'] == 'obraz' for e in meaningful),
        },
    }


def communication_summary(view: dict) -> str:
    data = build_management(view)
    pages = [p for row in view['rows'] for p in row['pages']]
    complete = sum(bool(p.get('communication', {}).get('daily')) for p in pages)
    partial = sum(p.get('current_read', False) and p.get('daily', False) and not p.get('communication', {}).get('daily') and p.get('communication', {}).get('shared_unchanged', 0) > 0 for p in pages)
    finding = ("Brakuje pełnej bazy do dziennej oceny komunikacji. " if not complete and not data['items'] else f"Ustalono {len(data['items'])} zmian komunikacji w {data['metrics']['communication']} pracowniach. ")
    return (finding +
            f'Pełne porównanie zapisanego zakresu: {complete}/{len(pages)} stron. '
            f'Dla {partial} stron sprawdzono zgodność fragmentów ze starszego skanu; to porównanie częściowe.')


def render_management(view: dict) -> str:
    metrics = build_management(view)['metrics']
    measured = any(p.get('communication', {}).get('daily') for r in view['rows'] for p in r['pages'])
    content = '<section class="box executive" id="executive" aria-labelledby="summary-title"><h2 id="summary-title">Zmiany komunikacji</h2><p id="management-summary" aria-live="polite">' + html.escape(communication_summary(view)) + '</p>'
    content += '<p class="small" id="management-scope">' + html.escape(view['comparison']['before_day']) + ' → ' + html.escape(view['day']) + '. Brak porównywalnego zapisu nie oznacza braku zmian. Ceny nie ograniczają porównania komunikatów.</p></section>'
    content += '<div class="stats management-stats" id="management-stats">'
    for key, label, note in [('communication', 'Pracownie ze zmianą komunikacji', 'potwierdzone komunikaty lub opisane zmiany wyglądu'), ('home_changes', 'Zmiany na stronach głównych', 'pracowni · nagłówki, banery, CTA i treść'), ('project_changes', 'Zmiany na kartach projektów', 'pracowni · opis, argumenty oferty, dodatki i CTA')]:
        value = str(metrics[key]) if measured or metrics[key] else '—'
        content += '<div class="stat"><span>' + label + '</span><strong id="metric-' + key + '">' + value + '</strong><span>' + note + '</span></div>'
    content += '</div><section class="box quality-overview" aria-labelledby="quality-title"><h2 id="quality-title">Zakres porównania komunikacji</h2><div id="quality-summary">' + render_quality_summary(view) + '</div><p class="small">Pełne = dwa zgodne zapisy monitorowanego zakresu z kolejnych dni. Fragmenty = zgodne teksty zachowane w starszym, węższym skanie; nagłówki i banery nie mają wtedy pełnej bazy. Nowa baza = dzisiejszy poprawny zapis gotowy do następnego porównania.</p></section>'
    return content


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
    content = '<section id="communication-coverage" class="box"><h2>Dzienny przegląd wszystkich pracowni</h2><p class="small">Obie strony każdej pracowni: wynik porównania komunikatów, zakres oraz źródło. „Częściowe” nie oznacza „bez zmian”.</p><div class="table-box" tabindex="0" role="region" aria-label="Komunikacja we wszystkich pracowniach"><table class="communication-table"><thead><tr><th>Pracownia / stały projekt</th><th data-communication-header="glowna">Strona główna</th><th data-communication-header="projekt">Karta projektu</th><th>Zmiany i źródła</th></tr></thead><tbody>'
    items = build_management(view)['items']
    for row in sorted(view['rows'], key=lambda r: (not any(e['domain'] == r['domain'] for e in items), r['domain'])):
        content += '<tr data-communication-domain="' + esc(row['domain'], quote=True) + '"><td><strong>' + esc(row['domain']) + '</strong><br><span class="small">' + esc(row['name']) + '</span></td>'
        for page in row['pages']:
            c = page.get('communication', {})
            stamp = (capture_day(page['compared_at']) or 'brak bazy') + ' → ' + (capture_day(page['observed_at']) or 'brak odczytu')
            content += '<td data-communication-page="' + page['page'] + '"><strong>' + esc(c.get('label', 'Brak porównania')) + '</strong><br><span class="small">' + esc(stamp) + ('<br>Nowa baza gotowa' if c.get('ready') and page.get('current_read') else '') + '</span></td>'
        changes = [e for e in items if e['domain'] == row['domain']]
        content += '<td>' + ''.join('<p data-communication-change-page="' + e['page'] + '" data-category="' + e['category'] + '"><a href="#' + e['id'] + '">' + esc(e['description']) + '</a></p>' for e in changes)
        for p in row['pages']:
            if p['url']:
                content += '<a data-communication-source-page="' + p['page'] + '" href="' + esc(p['url'], quote=True) + '" target="_blank" rel="noopener">' + ('Główna' if p['page'] == 'glowna' else 'Projekt') + '</a> · '
        content += '<a href="#pracownia-' + esc(row['domain'], quote=True) + '">Odczyty i zrzuty</a></td></tr>'
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
