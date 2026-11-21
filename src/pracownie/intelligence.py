"""Retained business evidence and a bounded follow-up queue, not inferred sales."""
from __future__ import annotations

import hashlib
from datetime import date, timedelta

from .briefing import build_briefing
from .commercial import document, expired_end, future_start, not_started
from .communication import COUNTDOWN
from .contexts import REASONS, observation_reason
from .model import Snapshot
from .signals import normalized, supporting_reason


def update_intelligence(state: dict, view: dict) -> dict:
    day = view['day']
    cutoff = (date.fromisoformat(day) - timedelta(days=180)).isoformat()
    domains = {r['domain'] for r in view['rows']}
    ledger = {k: v for k, v in state.get('business_ledger', {}).items() if v['day'] > cutoff and v['domain'] in domains}
    queue = {k: v for k, v in state.get('verification_queue', {}).items() if v['first_seen'] > cutoff and v['domain'] in domains}
    briefing = build_briefing(view)
    for event in briefing['events']:
        if event['tier'] == 'technical':
            continue
        item = event['lead']
        record = {k: event[k] for k in ('id', 'domain', 'pages', 'kind', 'sentence', 'confidence', 'tier')}
        record.update(day=day, before=item['before'], after=item['after'], before_at=item['before_at'], after_at=item['after_at'], source=item['source'])
        ledger[day + '/' + event['id']] = record
        if event['tier'] == 'review':
            key = hashlib.sha256((event['domain'] + str(item['before']) + str(item['after'])).encode()).hexdigest()[:20]
            prior = queue.get(key, {})
            queue[key] = {**prior, 'id': key, 'event_id': event['id'], 'domain': event['domain'], 'page': item['page'],
                          'url': item['source'], 'before': item['before'], 'after': item['after'], 'category': item['category'],
                          'label': item['description'], 'before_at': item['before_at'], 'first_seen': prior.get('first_seen', day), 'last_seen': day,
                          'next_check': event['next_check'], 'status': prior.get('status', 'open') if prior.get('last_seen') == day else 'open'}
    # Reclassify stale follow-ups only when the same recorded text on the same
    # page is now source-backed peripheral context. Absence from today's scan
    # never resolves a queue item, and the original record remains retained.
    from urllib.parse import urldefrag
    def identity(item, source):
        return (item['domain'], item['page'], urldefrag(item[source])[0],
                normalized(item['before']), normalized(item['after']))
    observations = {}
    for item in view.get('journal', []):
        observations.setdefault(identity(item, 'source'), []).append(item)
    for item in queue.values():
        matches = observations.get(identity(item, 'url'), [])
        reasons = []
        for match in matches:
            context = observation_reason(match)
            reason = supporting_reason(match)
            # Unmatched/unstable copy is still unresolved; it must not close
            # a commercial follow-up merely because it is outside the digest.
            reasons.append(context if context in {REASONS[k] for k in ('testimonials','editorial','catalogue')}
                           else reason if reason.startswith('Kontrolka zgód') else '')
        if item['status'] == 'open' and reasons and all(reasons):
            item.update(status='supporting', supporting_reason=reasons[0], reclassified_at=day)
    offers, graphics = {}, []
    for key, raw in state.get('snapshots', {}).items():
        if raw['domain'] not in domains or not key.endswith('/podstawowy') or raw.get('page') not in {'glowna', 'projekt'}:
            continue
        snap = Snapshot.from_dict(raw)
        for popup in snap.document.get('popups', []):
            for image in popup.get('images', []):
                item = {'domain':snap.domain, 'url':popup['url'], 'image':image['url'], 'observed_at':popup['observed_at']}
                if item not in graphics:
                    graphics.append(item)
        for claim in document(snap)['claims']:
            offer_text = COUNTDOWN.sub('', claim).replace('[licznik]', '')
            identity = snap.domain, ' '.join(offer_text.split()).casefold()
            start = future_start(claim, day)
            status = 'Zapowiedziana' if start or not_started(claim) else 'Termin minął' if expired_end(claim, day) else 'Obecna w zapisie'
            offer = offers.setdefault(identity, {'domain': snap.domain, 'text': claim, 'status': status, 'start': start, 'sources': []})
            source = {'page': snap.page, 'url': snap.url, 'observed_at': snap.observed_at}
            if source not in offer['sources']:
                offer['sources'].append(source)
    state['business_ledger'], state['verification_queue'] = ledger, queue
    return {'offers': list(offers.values()), 'graphics':graphics, 'history': sorted(ledger.values(), key=lambda r: (r['day'], r['domain']), reverse=True),
            'pending': [q for q in queue.values() if q['status'] == 'open'],
            'checks': [q for q in queue.values() if q.get('check')]}
