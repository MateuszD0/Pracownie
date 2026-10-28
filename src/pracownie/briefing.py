"""Evidence-backed business events, shared by every daily reading surface."""
from __future__ import annotations

import hashlib
import html
import re
from datetime import date, datetime, timedelta
from urllib.parse import urldefrag
from zoneinfo import ZoneInfo

EMPTY = {'', 'brak', '—'}
LABELS = {'glowna': 'Strona główna', 'projekt': 'Karta projektu'}
VERIFIED = {'added', 'changed', 'scheduled', 'ended', 'elsewhere'}
COMMERCIAL = {'promotions', 'extras', 'terms'}


def normalized(value) -> str:
    return ' '.join(str(value or '').split()).casefold()


def short(value, limit=180) -> str:
    value = ' '.join(str(value or '').split())
    return value if len(value) <= limit else value[:limit - 1].rstrip() + '…'


def technical(item: dict) -> bool:
    text = normalized(item.get('description'))
    if item['category'] == 'obraz' and re.match(r'(przesunięcie|położenie|rozmiar|czcionka|kolor|odstęp)', text):
        return True
    texts = [normalized(item.get(k)) for k in ('before', 'after') if normalized(item.get(k)) not in EMPTY]
    if item['business_bucket'] == 'copy' and any(re.search(r'pierwotna cena wynosiła|aktualna cena wynosi', t) for t in texts):
        return True
    if item['category'] == 'obraz' and text.startswith('widoczny nagłówek:') and all(len(t) < 24 for t in texts):
        return True
    return bool(texts) and all(re.fullmatch(r'zaloguj się|zobacz koszyk|nie pamiętasz hasła\??|(?:woj\.? )?(?:kujawsko-pomorskie|mazowieckie)', t) for t in texts)


def event_sentence(item: dict) -> str:
    check = item.get('commercial_check', {})
    if check:
        if normalized(item['after']) in EMPTY and check['status'] in {'other_offers', 'unverified', 'probably_ended', 'unstable'}:
            # The checking result is context, not a replacement for the
            # disappeared offer. Keep its discount/code in the daily summary.
            observation = 'Nie odnotowano wcześniejszego komunikatu: „' + short(item['before'], 140) + '”. '
            return observation + check['summary'].removeprefix('Komunikat zniknął. ')
        if check['status'] == 'scheduled':
            dates = re.findall(r'\d{4}-\d{2}-\d{2}', str(item['after']))
            if len(set(dates)) == 1:
                return 'Zapowiedź promocji od ' + dates[0] + '.'
        return check['summary']
    if normalized(item['after']) in EMPTY:
        return 'W nowym zapisie nie ma komunikatu: „' + short(item['before']) + '”.'
    if normalized(item['before']) in EMPTY:
        return 'Pojawił się komunikat: „' + short(item['after']) + '”.'
    return '„' + short(item['before'], 110) + '” → „' + short(item['after'], 110) + '”.'


def event_key(item: dict) -> tuple:
    # Identical terms can be observed on home and project pages; distinct
    # amounts, codes and dates must never merge merely because a topic matches.
    return item['domain'], item['business_bucket'], normalized(item['before']), normalized(item['after'])


def build_briefing(view: dict, management: dict | None = None) -> dict:
    from .commercial import generic_offer_label
    from .gaps import page_gap
    from .management import build_management
    from .relationships import group_for

    management = management or build_management(view)
    groups = {}
    for item in management['items']:
        groups.setdefault(event_key(item), []).append(item)
    # A paired heading is independent evidence connecting an addition and a
    # removal. Require the same source page, capture times and unique matches.
    for key, members in list(groups.items()):
        item = members[0]
        if item['category'] != 'obraz' or not item['description'].startswith('Widoczny nagłówek:') or any(normalized(item[k]) in EMPTY for k in ('before', 'after')):
            continue
        matching = []
        for other_key, entries in groups.items():
            candidate = entries[0]
            if other_key == key or candidate['category'] != 'komunikacja':
                continue
            if (candidate['domain'], candidate['page'], candidate['before_at'], candidate['after_at'], urldefrag(candidate['source'])[0]) != (item['domain'], item['page'], item['before_at'], item['after_at'], urldefrag(item['source'])[0]):
                continue
            if (normalized(candidate['before']) in EMPTY and normalized(candidate['after']) == normalized(item['after'])) or (normalized(candidate['after']) in EMPTY and normalized(candidate['before']) == normalized(item['before'])):
                matching.append(other_key)
        if len(matching) == 2 and len({normalized(groups[k][0]['before']) in EMPTY for k in matching}) == 2:
            for other_key in matching:
                members.extend(groups.pop(other_key))
    # A generic "not started" message can explain one dated announcement on
    # the SAME verified page/capture. Ambiguous multiple campaigns stay apart.
    for key, members in list(groups.items()):
        item = members[0]
        check = item.get('commercial_check', {})
        if check.get('status') != 'scheduled' or not re.fullmatch(r'promocja jeszcze się nie rozpoczęła\.?', normalized(item['after'])):
            continue
        candidates = [k for k, entries in groups.items() if k != key and entries[0]['domain'] == item['domain']
                      and entries[0].get('commercial_check', {}).get('status') == 'scheduled'
                      and re.search(r'\d{4}-\d{2}-\d{2}', str(entries[0]['after']))
                      and entries[0]['after_at'] == item['after_at']
                      and urldefrag(entries[0]['source'])[0] == urldefrag(item['source'])[0]]
        if len(candidates) == 1:
            groups[candidates[0]].extend(groups.pop(key))
    events = []
    for key, items in groups.items():
        lead = min(items, key=lambda e: (any(normalized(e[k]) in EMPTY for k in ('before', 'after')), e['readout']['lead_rank']))
        heading = lead['description'].startswith('Widoczny nagłówek:')
        check = lead.get('commercial_check', {})
        status = check.get('status', '')
        commercial = lead['business_bucket'] in COMMERCIAL
        removed = normalized(lead['after']) in EMPTY
        texts = [lead[k] for k in ('before', 'after') if normalized(lead[k]) not in EMPTY]
        label_only = commercial and bool(texts) and all(generic_offer_label(text) for text in texts)
        noise = all(technical(e) for e in items)
        review = commercial and (status in {'unverified', 'probably_ended', 'other_offers', 'unstable'} or removed and status not in VERIFIED)
        review = review or label_only
        tier = 'technical' if noise or status in {'still_present', 'expired'} else 'review' if review else 'technical' if status == 'label_only' else 'main' if any(e['readout']['overview'] for e in items) else 'technical'
        confidence = 'Do sprawdzenia' if review else 'Potwierdzona zapowiedź' if status == 'scheduled' else 'Sprawdzono w serwisie' if status in VERIFIED else 'Zaobserwowana zmiana'
        note = 'Monitor sprawdzi ofertę ponownie; brak baneru nie potwierdza jej zakończenia.' if review and removed else check.get('note', '')
        if label_only:
            note = 'Sama etykieta nie określa warunków ani nie potwierdza nowej lub zakończonej promocji.'
        if status == 'scheduled':
            note = 'Zapowiedź; nie oznacza aktywnego rabatu w dniu odczytu.'
        important = commercial or bool(re.search(r'nagłówek|baner|wezwanie', lead['description'], re.I))
        identifier = hashlib.sha256(repr(key).encode()).hexdigest()[:16]
        feedback = view.get('metadata', {}).get('feedback', {})
        rating = feedback.get('ratings', {}).get(view['day'] + '/' + identifier, {})
        priority_reason = ('promocja, dodatek lub warunki oferty' if commercial else
                           'nagłówek, baner lub wezwanie do działania' if important else 'pozostała obserwacja')
        events.append({'id': identifier, 'domain': lead['domain'], 'group':group_for(view,lead['domain']), 'kind': 'Komunikacja sprzedażowa' if heading else lead['business_type'],
                       'bucket': 'copy' if heading else lead['business_bucket'], 'tier': tier, 'confidence': confidence,
                       'importance': 'ważne' if important else 'do przeglądu',
                       'priority': 'Wysoki' if important else 'Standardowy', 'priority_reason': priority_reason,
                       'rating': rating, 'feedback_repo': feedback.get('repository', ''), 'day': view['day'],
                       'sentence': (('W nowym zapisie nie ma etykiety: ' if removed else 'Zauważono etykietę: ') + '„' + short(texts[-1]) + '”.' if label_only else event_sentence(lead)), 'note': note,
                       'next_check': (date.fromisoformat(view['day']) + timedelta(days=1)).isoformat() if review or status == 'scheduled' else '',
                       'pages': sorted({e['page'] for e in items}), 'lead': lead,
                       'items': items, 'observation_ids': list(dict.fromkeys(i for e in items for i in e['observation_ids']))})
    events.sort(key=lambda e: (e['importance'] != 'ważne', {'promotions': 0, 'extras': 1, 'terms': 2, 'copy': 3, 'functions': 4, 'design': 5}[e['bucket']], e['domain'], e['id']))
    # Show the breadth of communication changes before a studio's repeated
    # secondary messages. Concrete offer changes retain their first priority.
    seen, preferred, remaining = set(), [], []
    for event in events:
        if event['tier'] == 'main' and (event['domain'] not in seen or event['bucket'] in COMMERCIAL):
            preferred.append(event)
            seen.add(event['domain'])
        else:
            remaining.append(event)
    events = preferred + remaining
    pages = [p for r in view['rows'] for p in r['pages']]
    complete = [r['domain'] for r in view['rows'] if len(r['pages']) == 2 and all(p.get('communication', {}).get('daily') for p in r['pages'])]
    gaps = []
    for row in view['rows']:
        issues = []
        for p in row['pages']:
            if p.get('communication', {}).get('daily'):
                continue
            issues.append(page_gap(p, view['day']))
        if issues:
            gaps.append({'domain': row['domain'], 'issues': issues})
    return {'events': events, 'total': len(view['rows']), 'complete_domains': complete, 'gaps': gaps,
            'pending_domains':[r['domain'] for r in view['rows'] if r.get('scan_pending')],
            'paired_pages': sum(bool(p.get('communication', {}).get('daily')) for p in pages),
            'expected_pages': len(pages)}


def delivery_text(view: dict) -> str:
    delivery = view.get('metadata', {}).get('delivery', {})
    at = delivery.get('first_published_at')
    parts = []
    if at:
        local = datetime.fromisoformat(at.replace('Z', '+00:00')).astimezone(ZoneInfo('Europe/Warsaw'))
        late = local > local.replace(hour=8, minute=0, second=0, microsecond=0)
        parts.append('Pierwsza publikacja: ' + local.strftime('%H:%M') + (' — po terminie 08:00' if late else ' — przed 08:00'))
    else:
        parts.append('Termin publikacji: brak potwierdzonej godziny')
    parts.append('E-mail: ' + {'sent': 'przyjęty przez SMTP', 'pending': 'wynik wysyłki niepotwierdzony', 'not_configured': 'wysyłka niewłączona', 'waiting': 'oczekuje na wysyłkę'}.get(delivery.get('email'), 'brak potwierdzenia wysyłki'))
    return ' · '.join(parts)


def render_intelligence(view: dict) -> str:
    from .journal import safe_source
    from .presentation import when

    data = view.get('metadata', {}).get('intelligence', {})
    esc = html.escape
    output = []
    old_pending = [q for q in data.get('pending', []) if q['first_seen'] < view['day']]
    if old_pending:
        output += ['<section class="box"><h3>Ważne do sprawdzenia — z poprzednich dni</h3><ul>']
        for q in old_pending:
            output += ['<li data-intelligence-domain="' + esc(q['domain'], quote=True) + '"><strong>' + esc(q['domain']) + '</strong>: ' + esc(short(q['before'] or q['after'])) + ' · nierozstrzygnięte od ' + q['first_seen'] + ', następna próba: ' + q['next_check'] + '</li>']
        output += ['</ul></section>']
    output += ['<details id="offer-register"><summary>Komunikaty ofert w ostatnim odczycie (' + str(len(data.get('offers', []))) + ')</summary><p class="small">Obecność komunikatu nie potwierdza dostępności oferty w koszyku. Data przy źródle wskazuje ostatni poprawny zapis; starszy zapis nie jest dzisiejszą weryfikacją.</p><div class="table-box"><table><thead><tr><th>Pracownia</th><th>Komunikat oferty</th><th>Stan / źródło</th></tr></thead><tbody>']
    for offer in data.get('offers', []):
        output += ['<tr data-intelligence-domain="' + esc(offer['domain'], quote=True) + '"><td>' + esc(offer['domain']) + '</td><td>' + esc(short(offer['text'], 400)) + '</td><td>' + esc(offer['status']) + '<br>' + '<br>'.join('<a href="' + esc(safe_source(s['url']), quote=True) + '">' + LABELS[s['page']] + '</a> · ' + esc(when(s['observed_at'])) for s in offer['sources']) + '</td></tr>']
    output += ['</tbody></table></div></details><details id="event-history"><summary>Historia zdarzeń (' + str(len(data.get('history', []))) + ')</summary><p class="small">Rejestr gromadzony od wdrożenia odprawy. Starsze raporty są w historii dni.</p><div class="table-box"><table><thead><tr><th>Dzień / pracownia</th><th>Zdarzenie</th><th>Status przy zapisie</th></tr></thead><tbody>']
    for e in data.get('history', []):
        output += ['<tr data-intelligence-domain="' + esc(e['domain'], quote=True) + '"><td>' + e['day'] + '<br>' + esc(e['domain']) + '</td><td>' + esc(e['sentence']) + '</td><td>' + esc(e['confidence']) + '</td></tr>']
    output += ['</tbody></table></div></details>']
    return ''.join(output)


def render_briefing(view: dict, data: dict | None = None) -> str:
    from .journal import relative_proof, safe_source
    from .presentation import when

    data = data or build_briefing(view)
    def esc(value):
        return html.escape(str(value), quote=True)
    out = ['<section id="briefing" aria-labelledby="brief-title"><h2 id="brief-title">Odprawa dnia</h2>',
           '<p class="brief-coverage" id="brief-coverage">Porównano obie strony: <strong>' + str(len(data['complete_domains'])) + '/' + str(data['total']) + ' pracowni</strong> · <a href="#brief-gaps">' + str(len(data['gaps'])) + ' wymaga uwagi</a></p>',
           '<p class="small" id="brief-delivery">' + esc(delivery_text(view)) + ' · czas polski</p>']
    if data['pending_domains']:
        pending = len(data['pending_domains'])
        out[1] = '<p class="brief-coverage" id="brief-coverage">Porównano obie strony: <strong>' + str(len(data['complete_domains'])) + '/' + str(data['total']) + ' pracowni</strong> · ' + str(pending) + ' oczekuje na pierwszy skan · <a href="#brief-gaps">Pozostałe braki: ' + str(len(data['gaps'])-pending) + '</a></p>'
    feedback = view.get('metadata', {}).get('feedback')
    if feedback:
        from .feedback import summary_text
        out += ['<p class="small">' + esc(summary_text(feedback)) + ' Wynik dotyczy tylko ocenionych alertów; nie mierzy pominiętych zmian. Oceny są publicznymi zgłoszeniami GitHub i pojawiają się w kolejnym raporcie.</p>']
    reviews = [e for e in data['events'] if e['tier'] == 'review']
    out += ['<p id="brief-review-cue"' + (' hidden' if not reviews else '') + '><a href="#brief-review">Ważne do sprawdzenia: ' + str(len(reviews)) + '</a></p>']
    for tier, title in [('main', 'Najważniejsze zmiany'), ('review', 'Ważne do sprawdzenia')]:
        selected = [e for e in data['events'] if e['tier'] == tier]
        out += ['<section class="brief-section" id="brief-' + tier + '" data-brief-section="' + tier + '"><h3>' + title + '</h3><div class="table-box"><table class="business-table brief-table"><thead><tr><th>Pracownia / miejsce</th><th>Co się zmieniło</th><th>Priorytet i pewność</th><th>Dowód</th></tr></thead><tbody>']
        for index, event in enumerate(selected):
            out += ['<tr data-brief-id="' + event['id'] + '"' + (' hidden data-brief-extra' if tier == 'main' and index >= 5 else '') + '><td><strong>' + esc(event['domain']) + '</strong><br><span data-brief-places class="small">' + ' · '.join(LABELS[p] for p in event['pages']) + '</span></td><td><span class="topic">' + esc(event['kind']) + '</span><p>' + esc(event['sentence']) + '</p></td><td><strong>Priorytet: ' + esc(event['priority']) + '</strong><p class="small">' + esc(event['priority_reason']) + '</p><strong class="certainty ' + tier + '">' + esc(event['confidence']) + '</strong><p class="small">' + esc(event['note']) + '</p></td><td><a href="#zdarzenie-' + event['id'] + '">Przed / po →</a></td></tr>']
        out += ['<tr data-brief-empty="' + tier + '"' + (' hidden' if selected else '') + '><td colspan="4">' + ('Nie ustalono istotnych zmian w porównanym zakresie.' if tier == 'main' else 'Brak ważnych nierozstrzygniętych sygnałów w tym zakresie.') + '</td></tr></tbody></table></div>']
        if tier == 'main':
            out += ['<button type="button" id="brief-more"' + (' hidden' if len(selected) <= 5 else '') + '>Pozostałe ważne zmiany (' + str(max(0, len(selected)-5)) + ')</button>']
        out += ['</section>']
    out += ['<details id="brief-gaps"><summary>Braki porównania · ' + str(len(data['gaps'])) + ' pracowni</summary><p>Osobno pokazujemy działające odczyty bez historii i problemy wymagające naprawy.</p><div class="table-box"><table class="business-table"><thead><tr><th>Pracownia / strona</th><th>Stan odczytu</th><th>Co dalej</th></tr></thead><tbody>']
    for gap in data['gaps']:
        for issue in gap['issues']:
            out += ['<tr data-gap-domain="' + esc(gap['domain']) + '"><td><a href="#pracownia-' + esc(gap['domain']) + '">' + esc(gap['domain']) + '</a><br>' + LABELS[issue['page']] + '</td><td data-label="Stan odczytu"><strong>' + esc(issue['status']) + '</strong><br>' + esc(issue['reason']) + '</td><td data-label="Co dalej">' + esc(issue['action']) + '</td></tr>']
    out += ['</tbody></table></div><p class="small">Brak porównania nie oznacza „bez zmian”. Daty zapisów i dostępne dowody znajdują się w szczegółach pracowni.</p></details></section><details id="brief-proofs"><summary>Dowody zdarzeń — tekst i zrzuty przed / po</summary>']
    for event in data['events']:
        if event['tier'] == 'technical':
            continue
        lead = event['lead']
        out += ['<article class="brief-proof" id="zdarzenie-' + event['id'] + '" data-brief-proof="' + event['id'] + '"><h3>' + esc(event['domain']) + ' · ' + esc(event['kind']) + '</h3><p>' + esc(event['sentence']) + '</p><p><strong>' + esc(event['confidence']) + '</strong> · ' + esc(event['note']) + '</p><div class="values">']
        for side, label, at in [('before', 'Wczoraj', lead['before_at']), ('after', 'Dziś', lead['after_at'])]:
            text = lead[side] if normalized(lead[side]) not in EMPTY else 'Nie odnotowano w tym zapisie'
            out += ['<div class="value"><small>' + label + ' · ' + esc(when(at)) + '</small>' + esc(text) + '</div>']
        out += ['</div><p>' + ' · '.join('<a href="' + esc(safe_source(e['source'])) + '" target="_blank" rel="noopener">' + LABELS[e['page']] + '</a>' for e in { (e['page'], e['source']):e for e in event['items']}.values()) + '</p>']
        evidence = lead.get('evidence', {})
        keys = [('fragment_przed', 'Przed', lead['before_at']), ('fragment_po', 'Po', lead['after_at'])] if all(evidence.get(k) for k in ['fragment_przed', 'fragment_po']) else [('przed', 'Przed', lead['before_at']), ('po', 'Po', lead['after_at'])]
        out += ['<div class="proofs">']
        for key, label, at in keys:
            path = relative_proof(view['day'], evidence.get(key, ''))
            if path:
                out += ['<figure><a href="' + esc(path) + '" target="_blank" rel="noopener"><img loading="lazy" src="' + esc(path) + '" alt="' + label + ' — ' + esc(event['domain']) + '"></a><figcaption>' + label + ' · ' + esc(when(at)) + '</figcaption></figure>']
        out += ['</div><p class="small">Zrzut jest dowodem uchwyconego obszaru; pełny tekst może pochodzić również z interakcji.</p>']
        if event['feedback_repo']:
            from .feedback import LABELS as FEEDBACK_LABELS
            from .feedback import feedback_links
            rating = event['rating']
            out += ['<p><strong>Twoja ocena:</strong> ' + esc(FEEDBACK_LABELS.get(rating.get('verdict'), 'brak oceny')) + '. Oceń: '
                    + ' · '.join('<a href="' + esc(url) + '" target="_blank" rel="noopener">' + esc(label) + '</a>' for label, url in feedback_links(event['feedback_repo'], event['day'], event)) + '</p>']
        out += ['<a href="#briefing">↑ Powrót do odprawy</a></article>']
    out += ['</details>']
    return ''.join(out)


def markdown_briefing(view: dict, data: dict, targets: dict[str, str], extra_documents: dict, folder: str, filename: str) -> list[str]:
    from .dashboard import cell, link
    from .relationships import groups

    lines = ['## Zmiany oferty i komunikacji', '', 'Najważniejsze zdarzenia; datowane teksty i zrzuty pod linkiem „Przed / po”.', '']
    header = ['| Pracownia / miejsce | Co się zmieniło | Priorytet i pewność | Dowód |', '| --- | --- | --- | --- |']

    def row(event):
        checked = event['lead'].get('commercial_check', {}).get('sources', [])
        return '| ' + ' | '.join([
            '**' + cell(event['domain']) + '**<br>' + ' · '.join(LABELS[p] for p in event['pages']),
            cell(event['sentence']), '**Priorytet: ' + cell(event['priority']) + '**<br>' + cell(event['priority_reason']) + '<br>**' + cell(event['confidence']) + '**' + ('<br>' + cell(event['note']) if event['note'] else ''),
            '[Przed / po →](' + targets[event['id']] + ')<br>' + link('Otwórz stronę', event['lead']['source']) + ('<br>' + link('Sprawdzone warunki', checked[0]['url']) if checked else ''),
        ]) + ' |'

    def paged(events, stem):
        chunks = [events[i:i + 20] for i in range(0, len(events), 20)]
        if len(chunks) <= 1:
            return [row(e) for e in events]
        navigation = []
        for i, chunk in enumerate(chunks[1:], 2):
            path = folder + '/' + stem + '-' + str(i) + '.md'
            navigation.append('[Część ' + str(i) + '](' + path + ')')
            extra_documents[path] = '\n'.join(['# Zdarzenia · ' + view['day'], '', '[← Odprawa dnia](../' + filename + ')', '', *header, *[row(e).replace('](' + folder + '/', '](') for e in chunk], ''])
        return [*[row(e) for e in chunks[0]], '', 'Dalsze zdarzenia: ' + ' · '.join(navigation)]

    main = [e for e in data['events'] if e['tier'] == 'main']
    review = [e for e in data['events'] if e['tier'] == 'review']
    for group, label in groups(view):
        selected = [e for e in main if group == 'all' or e['group'] == group]
        if label:
            lines += ['### ' + label, '']
        lines += header + ([row(e) for e in selected[:5]] or ['| Nie ustalono konkretnych zmian biznesowych w porównanym zakresie. | | | |'])
        if len(selected) > 5:
            lines += ['', '<details><summary>Pozostałe ważne zmiany (' + str(len(selected)-5) + ')</summary>', '', *header, *paged(selected[5:], 'zmiany' + ('-'+group if label else '')), '', '</details>']
        lines += ['']
    lines += ['', '## Ważne do sprawdzenia', '']
    for group, label in groups(view):
        if label:
            lines += ['### ' + label, '']
        selected = [e for e in review if group == 'all' or e['group'] == group]
        lines += header + (paged(selected, 'weryfikacja' + ('-'+group if label else '')) or ['| Brak ważnych nierozstrzygniętych sygnałów w tym zakresie. | | | |']) + ['']
    gap_summary = '**' + str(len(data['gaps'])) + ' pracowni bez pełnego porównania obu stron.**'
    if data['pending_domains']:
        gap_summary = 'Bez pełnego porównania: **' + str(len(data['gaps'])) + '**, w tym **' + str(len(data['pending_domains'])) + ' oczekuje na pierwszy skan**.'
    lines += ['', '## Braki porównania', '', gap_summary + ' Brak porównania nie oznacza „bez zmian”.', '']
    from .dashboard import company_anchor
    for category, title in [('history', 'Odczyt działa — potrzebna historia'), ('repair', 'Problemy wymagające naprawy')]:
        issues = [(gap['domain'], issue) for gap in data['gaps'] for issue in gap['issues'] if issue['category'] == category]
        if not issues:
            continue
        gap_header = ['| Pracownia / strona | Stan odczytu | Co dalej |', '| --- | --- | --- |']
        gap_rows = []
        for domain, issue in issues:
            target = folder + '/' + company_anchor(domain) + '.md#' + ('strona-główna' if issue['page'] == 'glowna' else 'karta-projektu')
            gap_rows += ['| [' + cell(domain) + '](' + target + ')<br>' + LABELS[issue['page']] + ' | **' + cell(issue['status']) + '**<br>' + cell(short(issue['reason'], 260)) + ' | ' + cell(issue['action']) + ' |']
        lines += ['### ' + title + ' · ' + str(len(issues)) + ' stron', '', *gap_header, *gap_rows[:12]]
        navigation = []
        for offset in range(12, len(gap_rows), 24):
            path = folder + '/odczyty-' + category + '-' + str(offset // 24 + 2) + '.md'
            navigation.append('[Dalsze strony ' + str(offset + 1) + '–' + str(min(offset + 24, len(gap_rows))) + '](' + path + ')')
            extra_documents[path] = '\n'.join(['# ' + title + ' · ' + view['day'], '', '[← Odprawa dnia](../' + filename + ')', '', *gap_header, *[r.replace('](' + folder + '/', '](') for r in gap_rows[offset:offset + 24]], ''])
        if navigation:
            lines += ['', ' · '.join(navigation)]
        lines += ['']
    return lines + ['']


def markdown_event(event: dict, previews: dict) -> list[str]:
    from .dashboard import cell, change_row, link, proof_pair

    lead = event['lead']
    lines = ['## Zdarzenie ' + event['id'], '', '**' + cell(event['sentence']) + '**', '',
             '**' + cell(event['confidence']) + '** · ' + cell(event['note']), '',
             '| Zmiana / miejsce | Było | Jest | Źródło |', '| --- | --- | --- | --- |',
             change_row(lead), '',
             ' · '.join(link(LABELS[page], source) for page, source in dict.fromkeys((e['page'], e['source']) for e in event['items'])), '',
             'Liczba źródłowych obserwacji: ' + str(len(event['observation_ids'])) + '. Pełne zapisy pozostają w szczegółach pracowni.', '']
    lines += proof_pair(lead.get('evidence', {}), previews, lead['before_at'], lead['after_at'])
    if event['feedback_repo']:
        from .feedback import LABELS as FEEDBACK_LABELS
        from .feedback import feedback_links

        current = FEEDBACK_LABELS.get(event['rating'].get('verdict'), 'brak oceny')
        lines += ['**Twoja ocena:** ' + cell(current) + '. Oceń alert: ' + ' · '.join(link(label, url) for label, url in feedback_links(event['feedback_repo'], event['day'], event)), '',
                  'Wybór otwiera publiczne zgłoszenie GitHub; zapisz je przyciskiem „Submit new issue”. Oceny pojawią się w kolejnym raporcie.', '']
    return lines
