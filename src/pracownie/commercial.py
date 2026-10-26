"""Follow up offer changes with bounded, read-only checks of the same studio."""
from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urldefrag, urlsplit

from .browser import allowed_url
from .communication import records
from .model import Change, Scenario, Site, Snapshot, json_bytes, local_day, now_iso

TOPICS = {'promocje', 'dodatki', 'pakiety'}
CLAIM = re.compile(r'promoc|rabat|kupon|gratis|bezpłat|za darmo|pakiet|w cenie|kosztorys|\bdodat(?:ek|ki|ków|ku|kiem|kami|kach)\b', re.I)
NAVIGATION = re.compile(r'^(?:regulamin(?:em)?(?: promocji)?|promocj[ae!]*|promocyjne projekty domów|pakiet|(?:bezpłatne |płatne )?dodatki(?: do projektu)?|(?:masz|wpisz|zastosuj) kod(?: rabatowy)?|powiadom o promocji|sprawdź promocje|zobacz promocje|więcej)[\s!?.:»>→]*$', re.I)
UNSAFE = re.compile(r'add.to.cart|wc-ajax|checkout|koszyk|zam[oó]wienie|zamow|kontakt|logowanie|logout|newsletter|subscribe|unsubscribe', re.I)


def normalized(value: str | None) -> str:
    return ' '.join((value or '').casefold().split())


def concrete(text: str) -> bool:
    return bool(CLAIM.search(text) and not NAVIGATION.fullmatch(text.strip())
                and not re.search(r'<\s*/?\s*(?:img|div|script|span|iframe)\b', text, re.I))


def relevant(change: Change) -> bool:
    values = [v for v in (change.before, change.after) if v]
    meaningful = any(concrete(v) or re.fullmatch(r'promocja[ !?.]*', v, re.I) for v in values)
    if not change.details.get('communication') and change.field_key and all(len(v) <= 60 for v in values):
        meaningful |= any(re.search(r'\d|gratis|bezpłat', v, re.I) and concrete(change.label + ' ' + v) for v in values)
    return (change.category in TOPICS and change.kind in {'added', 'removed', 'changed'}
            and not change.details.get('supporting_reason')
            and meaningful)


def document(snapshot: Snapshot, *, repeated: bool = False) -> dict:
    items = records(snapshot)
    context = snapshot.document.get('payload', {}).get('commercial_context', {})
    all_items = items + context.get('items', [])
    # Keep exact, bounded quotes and source/time. A failed or truncated capture
    # can provide context but cannot establish absence.
    corpus = '\n'.join(dict.fromkeys(i['text'] for i in all_items))
    claims = list(dict.fromkeys(i['text'] for i in all_items if concrete(i['text'])))
    return {'url': snapshot.url, 'observed_at': snapshot.observed_at, 'repeated': repeated,
            'complete': snapshot.quality in {'ok', 'visual'} and bool(items)
                        and not snapshot.document.get('communication', {}).get('truncated')
                        and context.get('contract') == 'commercial-v1' and not context.get('truncated'),
            'text': corpus, 'claims': claims, 'quality': snapshot.quality,
            'fields': {key: field.value for key, field in snapshot.fields.items() if field.category in TOPICS},
            'claim_urls': {i['text']: i.get('url') or snapshot.url for i in all_items}}


def linked_pages(site: Site, snapshots: list[Snapshot], base_urls: set[str]) -> tuple[list[str], int]:
    candidates = {}
    for snapshot in snapshots:
        payload = snapshot.document.get('payload', {})
        for link in payload.get('links', []) + payload.get('commercial_context', {}).get('links', []):
            url = urldefrag(link.get('url', ''))[0]
            label = link.get('text', '')
            if not allowed_url(site, url) or url in base_urls or UNSAFE.search(url):
                continue
            # Follow public offer/terms sections, not unrelated project cards.
            if not re.search(r'promoc|rabat|kupon|gratis|pakiet|dodatk', label + ' ' + urlsplit(url).path, re.I):
                continue
            if re.search(r'/produkt/|/projekt(?:y)?/|projekt-domu-', urlsplit(url).path, re.I):
                continue
            candidates[url] = 0 if re.search(r'promoc|rabat|kupon', label, re.I) else 1
    ordered = sorted(candidates, key=lambda u: (candidates[u], u))
    html = [u for u in ordered if not re.search(r'\.(pdf|zip|jpe?g|png|webp)(?:\?|$)', u, re.I)]
    return html[:2], len(ordered) - len(html[:2])


def future_start(text: str, day: str) -> str:
    match = re.search(r'(?:promocj\w*\s+od|od dnia|start(?:uje)?(?:\s+promocji)?|pocz[aą]tek(?:\s+promocji)?)\s*:?\s*(\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})', text, re.I)
    if not match:
        return ''
    raw = match[1]
    try:
        value = date.fromisoformat(raw if '-' in raw else '-'.join(reversed(raw.split('.')))).isoformat()
    except ValueError:
        return ''
    return value if value > day else ''


def announces_end(text: str) -> bool:
    return bool(re.fullmatch(r'(?:promocja(?: [\w-]+){0,5} (?:zakończona|nie obowiązuje)|koniec promocji(?: [\w-]+){0,5})[.!]?', text.strip(), re.I))


def not_started(text: str) -> bool:
    return bool(re.search(r'promocj\w*.{0,35}nie rozpoczę|promocj\w*.{0,15}wkrótce|wkrótce.{0,15}promocj', text, re.I))


def exact_record(doc: dict, text: str) -> bool:
    return any(normalized(line).rstrip('!?.,:;') == text.rstrip('!?.,:;') for line in doc['text'].splitlines())


def expired_end(text: str, day: str) -> str:
    match = re.search(r'\bdo(?: dnia)?\s*:?\s*(\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})', text, re.I)
    if not match:
        return ''
    raw = match[1]
    try:
        value = date.fromisoformat(raw if '-' in raw else '-'.join(reversed(raw.split('.')))).isoformat()
    except ValueError:
        return ''
    return value if value < day else ''


def assess(change: Change, url: str, documents: list[dict], *, complete: bool) -> dict:
    successful = [d for d in documents if d.get('complete')]
    repeats = [d for d in successful if d.get('repeated') and urldefrag(d['url'])[0] == urldefrag(url)[0]]
    repeat = repeats[-1] if repeats else None
    if repeat and local_day_from(repeat['observed_at']) != local_day_from(change.after_at):
        repeat = None
    # Compare the *same* campaign text. Other promotions are context, never
    # proof that a removed campaign still applies to the monitored project.
    old, new = normalized(change.before), normalized(change.after)
    status, summary = 'unverified', 'Nie udało się zweryfikować zmiany oferty w serwisie.'
    proof = []
    if repeat:
        text = normalized(repeat['text'])
        field_matches = (change.details.get('communication') or not change.field_key
                         or normalized(repeat.get('fields', {}).get(change.field_key)) == new)
        if new and new in text and field_matches:
            start = future_start(change.after or '', local_day_from(repeat['observed_at']))
            expired = expired_end(change.after or '', local_day_from(repeat['observed_at']))
            code = re.search(r'kod\s+(?:rabatowy|promocyjny)|kupon', change.label + ' ' + (change.after or ''), re.I)
            topic = 'kod rabatowy' if code else 'dodatek lub pakiet' if change.category in {'dodatki', 'pakiety'} else 'promocja'
            status = 'scheduled' if start else 'added' if not old else 'changed'
            summary = (f'Zapowiedź promocji od {start}: ' if start else
                       f'Nowy {topic}: ' if topic != 'promocja' and not old else
                       'Nowa promocja w komunikacji: ' if not old else 'Zmiana warunków lub komunikatu oferty: ') + quote(change.after)
            if old and not start:
                summary = 'Zmiana komunikatu oferty: ' + quote(change.before, 120) + ' → ' + quote(change.after, 160)
                if not change.details.get('communication'):
                    summary = change.label + ': ' + quote(change.before, 120) + ' → ' + quote(change.after, 160)
            if announces_end(change.after or ''):
                status, summary = 'ended', 'Serwis informuje o zakończeniu promocji: ' + quote(change.after)
            if not_started(change.after or '') and not start:
                status, summary = 'scheduled', 'Zapowiedź promocji — jeszcze nieaktywna: ' + quote(change.after)
            if expired:
                status, summary = 'expired', f'Komunikat z minionym terminem oferty ({expired}): ' + quote(change.after)
            proof = [{'url': repeat['url'], 'text': change.after, 'observed_at': repeat['observed_at']}]
            if NAVIGATION.fullmatch((change.after or '').strip()):
                status, summary = 'label_only', 'Zmiana etykiety na stronie; nie ustalono nowych warunków oferty: ' + quote(change.after)
        elif old and exact_record(repeat, old):
            status, summary = 'still_present', 'Komunikat nadal występuje po ponownym odczycie: ' + quote(change.before)
            proof = [{'url': repeat['url'], 'text': change.before, 'observed_at': repeat['observed_at']}]
        elif new:
            status, summary = 'unstable', 'Nowy komunikat nie powtórzył się w drugim odczycie; zmiana oferty niepotwierdzona.'
        else:
            matching = [d for d in successful if old and exact_record(d, old) and concrete(change.before or '')]
            if matching:
                status, summary = 'elsewhere', 'Komunikat zniknął z tego miejsca, ale nadal występuje w serwisie: ' + quote(change.before)
                proof = [{'url': d['url'], 'text': change.before, 'observed_at': d['observed_at']} for d in matching[:2]]
            else:
                facts = [(d, t) for d in successful for t in d['claims']]
                # Prefer concise statements from the rechecked fixed page.
                facts.sort(key=lambda pair: (
                    not bool(re.search(r'promoc|rabat|kupon|kod', pair[1], re.I)) if change.category == 'promocje' else False,
                    not pair[0].get('repeated'), len(pair[1])))
                if facts:
                    status = 'other_offers'
                    proof = [{'url': d.get('claim_urls', {}).get(t, d['url']), 'text': t, 'observed_at': d['observed_at']} for d, t in facts[:3]]
                    summary = 'Komunikat zniknął. W sprawdzonym serwisie znaleziono również: ' + quote(facts[0][1])
                elif complete:
                    status = 'probably_ended'
                    summary = ('Prawdopodobnie zakończono promocję w tym miejscu: ' if change.category == 'promocje' else
                               'Prawdopodobnie wycofano dodatek lub pakiet w tym miejscu: ') + quote(change.before)
    if not new and NAVIGATION.fullmatch((change.before or '').strip()) and not re.fullmatch(r'promocja[ !?.]*', change.before or '', re.I):
        status, summary = 'label_only', 'Zniknęła etykieta lub link, bez ustalonej zmiany warunków oferty: ' + quote(change.before)
    return {'status': status, 'summary': summary, 'checked_at': now_iso(), 'complete': complete,
            'sources': proof, 'checked_pages': [{k: d.get(k) for k in ('url', 'observed_at', 'complete', 'error', 'repeated')} for d in documents],
            'note': ('To inne lub dodatkowe komunikaty; nie potwierdzają zakończenia ani dalszego obowiązywania konkretnej wcześniejszej promocji.' if status == 'other_offers' else
                     'Nie znaleziono warunków w ponownym odczycie ani w sprawdzonych miejscach serwisu. To ocena prawdopodobna, nie potwierdzenie sprzedawcy.' if status == 'probably_ended' else
                     'Kod lub oferta są opublikowane w serwisie; nie sprawdzano realizacji zamówienia.' if status in {'added', 'changed'} else '')}


def local_day_from(value: str) -> str:
    return local_day(datetime.fromisoformat(value))


def quote(value: str | None, limit: int = 220) -> str:
    text = ' '.join((value or '').split())
    return '„' + (text if len(text) <= limit else text[:limit - 1] + '…') + '”'


async def verify_offers(site: Site, captures: list, results: list, previous: list[Snapshot], scanner,
                        work: Path, archive: Path, *, budget: float = 45, pending: dict | None = None) -> None:
    scoped = [r for r in results if r.domain == site.domain and r.scenario == 'podstawowy']
    targets = [(r, c) for r in scoped for c in r.changes if relevant(c)]
    followups = []
    for item in (pending or {}).values():
        row = next((r for r in scoped if r.page == item['page'] and r.observed_at and not r.error), None)
        if item['domain'] != site.domain or item['status'] != 'open' or not row or item['next_check'] > local_day_from(row.observed_at) or not allowed_url(site, item['url']):
            continue
        change = Change('removed' if not item['after'] or item['after'] == 'brak' else 'changed', item['category'], item['label'],
                        item['before'], item['after'], item['before_at'], row.observed_at, item['url'], 'weryfikacja-oferty')
        targets.append((row, change))
        followups.append((item, change))
    if not targets:
        return
    current = [c.snapshot for c in captures if c is not None]
    documents = [document(s) for s in current]
    base_urls = {urldefrag(s.url)[0] for s in current}
    linked, omitted = linked_pages(site, current + previous, base_urls)
    urls = list(dict.fromkeys((r.url, r.page) for r, _ in targets)) + [(u, 'glowna') for u in linked]
    completed = 0
    try:
        async with asyncio.timeout(budget):
            for index, (url, page) in enumerate(urls):
                try:
                    captured = await scanner.capture(site, page, url, Scenario('weryfikacja-oferty', 'Weryfikacja oferty'), work / f'offer-check-{index}.png')
                    doc = document(captured.snapshot, repeated=url in {r.url for r, _ in targets})
                    if urldefrag(doc['url'])[0] != urldefrag(url)[0]:
                        doc['complete'] = False
                        doc['error'] = 'Adres przekierował na inną stronę.'
                    documents.append(doc)
                except Exception as exc:
                    documents.append({'url': url, 'complete': False, 'error': str(exc).splitlines()[0][:250]})
                completed += 1
    except TimeoutError:
        documents.append({'url': site.home_url, 'complete': False, 'error': 'Wyczerpano czas dodatkowej weryfikacji oferty.'})
    finally:
        complete = (completed == len(urls) and not omitted and len(current) == 2
                    and all(d.get('complete') for d in documents))
        for result, change in targets:
            change.details['commercial_check'] = assess(change, result.url, documents, complete=complete)
        for item, change in followups:
            check = change.details['commercial_check']
            item['check'] = check
            item['status'] = 'resolved' if check['status'] in {'ended', 'elsewhere', 'still_present', 'added', 'changed', 'scheduled', 'label_only'} else 'open'
            item['next_check'] = (date.fromisoformat(local_day_from(change.after_at)) + timedelta(days=1)).isoformat()
        archive.mkdir(parents=True, exist_ok=True)
        (archive / 'weryfikacja-oferty.json').write_bytes(json_bytes({
            'checked_at': now_iso(), 'omitted_links': omitted, 'complete': complete,
            'documents': documents, 'assessments': [c.details['commercial_check'] for _, c in targets]}))
