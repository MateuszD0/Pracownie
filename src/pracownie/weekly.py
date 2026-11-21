"""Rolling weeks of verified daily observations, grouped by the relationship on the observation date."""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from decimal import Decimal
from importlib.resources import files

from .briefing import EMPTY, normalized, short
from .extract import page_identity
from .financial import codes, financial_data, meaningful_discount
from .journal import capture_day, safe_source
from .promo_terms import CAMPAIGN, VALUE_FIELDS, terms
from .relationships import LABELS, group_for

METRICS = {
    'price_cut': 'Obniżka ceny projektu',
    'price_rise': 'Podwyżka ceny projektu',
    'promotion_added': 'Nowy komunikat z rozpoznanym kodem lub nazwą kampanii',
    'wording': 'Zmiana treści przy tych samych odczytanych warunkach',
    'extras': 'Zmiana warunków dodatku na karcie projektu',
}
BASIS = {'price_cut': 'compared_price', 'price_rise': 'compared_price', 'promotion_added': 'compared_promo',
         'wording': 'compared_any', 'extras': 'compared_project'}


def _markers(quote: str) -> set[str]:
    values = {'code:' + code.casefold() for code in codes(quote)}
    values.update('campaign:' + match[0].casefold() for match in CAMPAIGN.finditer(quote))
    return values


def _wording(before: str, after: str) -> bool:
    first, second = terms(before), terms(after)
    if not first or not second or _markers(before) != _markers(after):
        return False
    # Treat changing numbers, dates and offer terms conservatively. The
    # business wording counter requires evidence beyond a date/countdown tick.
    if re.findall(r'\d+(?:[,.]\d+)?', before) != re.findall(r'\d+(?:[,.]\d+)?', after):
        return False
    return (all(normalized(first[k]) == normalized(second[k]) for k in (*VALUE_FIELDS, 'unavailable'))
            and normalized(before) != normalized(after))


def _category(event: dict, previous_markers: set[str], prior_comparable: bool) -> str:
    lead = event['lead']
    before, after = lead['before'], lead['after']
    status = lead.get('commercial_check', {}).get('status')
    if (event['tier'] != 'main' or not lead.get('daily') or normalized(after) in EMPTY
            or lead.get('offer_placement') or lead.get('communication_role') == 'placement'
            or lead.get('field_key', '').startswith('communication:placement:')):
        return ''
    if status in {'scheduled', 'ended', 'elsewhere', 'expired', 'still_present'}:
        return ''
    ids = _markers(after)
    if (event['bucket'] == 'promotions' and status == 'added' and normalized(before) in EMPTY
            and meaningful_discount(after) and prior_comparable and ids and not ids & previous_markers):
        return 'promotion_added'
    checked_copy = lead.get('communication_check', {}).get('status') == 'confirmed'
    if (checked_copy or event['bucket'] == 'promotions' and status == 'changed') and _wording(before, after):
        return 'wording'
    # Explicit changes to the terms of a named extra are handled by package_changes.
    return ''


def day_record(view: dict, briefing: dict, previous: dict | None = None, *, offers=None, terms_rows=None) -> dict:
    """Return compact evidence from one edition. A rerun replaces the day's record."""
    from .presentation import money

    day = view['day']
    yesterday = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    groups = {key: {'monitored': [], 'compared_any': [], 'compared_both': [], 'compared_price': [], 'compared_promo': [], 'compared_project': [], 'markers': {}, 'signals': {}}
              for key in LABELS}
    previous = previous or {}
    saved = view.get('metadata', {}).get('intelligence', {})
    offers = saved.get('offers', []) if offers is None else offers
    terms_rows = saved.get('promo_terms', []) if terms_rows is None else terms_rows
    changed_quotes = {(r['domain'], normalized(r['after']['quote'])) for r in terms_rows
                      if r.get('status') == 'changed' and r.get('after')}
    for offer in offers:
        if not any(capture_day(s.get('observed_at')) == day for s in offer.get('sources', [])):
            continue
        group = groups.get(group_for(view, offer['domain']))
        if group is not None:
            group['markers'].setdefault(offer['domain'], set()).update(_markers(offer['text']))
    finance = financial_data(view)
    for row in view['rows']:
        cohort = group_for(view, row['domain'])
        group = groups.get(cohort)
        if group is None:
            continue
        domain = row['domain']
        group['monitored'].append(domain)
        paired_pages = {p['page'] for p in row['pages'] if p.get('communication', {}).get('daily')}
        if paired_pages:
            group['compared_any'].append(domain)
        if {'glowna', 'projekt'} <= paired_pages:
            group['compared_both'].append(domain)
            if domain in previous.get(cohort, {}).get('compared_both', []):
                group['compared_promo'].append(domain)
        card = safe_source(row.get('url', ''))
        if row.get('project_selected') and card and any(
            p.get('page') == 'projekt' and p.get('daily') and p.get('data_quality') == 'ok'
            and page_identity(p.get('url', '')) == page_identity(card)
            and capture_day(p.get('compared_at')) == yesterday and capture_day(p.get('observed_at')) == day
            for p in row['pages']
        ):
            group['compared_project'].append(domain)
        if domain in finance['paired']:
            group['compared_price'].append(domain)

    def add(domain, category, source, before, after):
        group = groups.get(group_for(view, domain))
        if group is None or not safe_source(source):
            return
        # Denominators and signals must describe the same measured population.
        if domain not in group[BASIS[category]]:
            return
        group['signals'].setdefault(category, {}).setdefault(domain, {
            'category': category, 'domain': domain, 'day': day, 'source': source,
            'before': short(before, 220), 'after': short(after, 220),
        })

    for row in finance['changes']:
        category = 'price_cut' if Decimal(row['delta']) < 0 else 'price_rise'
        add(row['domain'], category, row['url'], money(row['previous']), money(row['current']))
    from .extras import package_changes
    for extra in package_changes(view):
        # A verified dated change in the same project option also proves a
        # comparable card, even if its basic scenario was incomplete.
        group = groups.get(group_for(view, extra['domain']))
        if group is not None and extra['domain'] not in group['compared_project']:
            group['compared_project'].append(extra['domain'])
        add(extra['domain'], 'extras', extra['source'], extra['before'], extra['after'])
    before_markers = {}
    for observation in view.get('journal', []):
        if capture_day(observation.get('before_at')) == yesterday:
            before_markers.setdefault(observation['domain'], set()).update(_markers(observation.get('before') or ''))
        group = groups.get(group_for(view, observation['domain']))
        if group is not None and capture_day(observation.get('after_at')) == day:
            group['markers'].setdefault(observation['domain'], set()).update(_markers(observation.get('after') or ''))
    for event in briefing['events']:
        lead = event['lead']
        domain, cohort = event['domain'], group_for(view, event['domain'])
        if cohort not in groups or (domain, normalized(lead['after'])) in changed_quotes:
            continue
        prior = previous.get(cohort, {})
        ids = set(prior.get('markers', {}).get(domain, []))
        # Also check yesterday's quotes from this day's comparisons, including
        # other placements of the same code on either monitored page.
        ids.update(before_markers.get(domain, ()))
        category = _category(event, ids, domain in prior.get('compared_both', []))
        if not category or capture_day(lead.get('before_at')) != yesterday or capture_day(lead.get('after_at')) != day:
            continue
        add(event['domain'], category, lead['source'], lead['before'], lead['after'])
    for group in groups.values():
        group['markers'] = {domain: sorted(ids) for domain, ids in group['markers'].items() if ids}
    return groups


def _period(history: dict, end: date) -> dict:
    dates = [(end - timedelta(days=offset)).isoformat() for offset in reversed(range(7))]
    days = [day for day in dates if day in history]
    output = {}
    for name in LABELS:
        records = [history[day].get(name, {}) for day in days]
        coverage = {key: len({domain for record in records for domain in record.get(key, ())})
                    for key in ('monitored', 'compared_any', 'compared_both', 'compared_price', 'compared_promo', 'compared_project')}
        metrics = {}
        for category in METRICS:
            examples = {}
            eligible_domains = set()
            for record in records:
                if category in {'promotion_added', 'wording'} and 'compared_promo' not in record:
                    continue  # Earlier formats used broader promotion and wording rules.
                eligible = set(record.get(BASIS[category], ()))
                eligible_domains.update(eligible)
                examples.update({domain: item for domain, item in record.get('signals', {}).get(category, {}).items()
                                 if domain in eligible})
            denominator = len(eligible_domains)
            metrics[category] = {'count': len(examples) if denominator else None, 'compared': denominator,
                                 'examples': sorted(examples.values(), key=lambda e: (e['domain'], e['day']))}
        output[name] = {**coverage, 'metrics': metrics}
    return {'start': dates[0], 'end': dates[-1], 'days': days,
            'missing_days': [day for day in dates if day not in history], 'groups': output}


def weekly_summary(state: dict, view: dict, briefing: dict, *, offers=None, terms_rows=None) -> dict:
    end = date.fromisoformat(view['day'])
    cutoff = (end - timedelta(days=180)).isoformat()
    history = {k: v for k, v in state.get('weekly_days', {}).items() if cutoff < k <= view['day']}
    # A legacy view lacking relationship metadata cannot supply either group's measurements.
    if view.get('metadata', {}).get('relationships', {}).get('domains'):
        prior = history.get((end - timedelta(days=1)).isoformat())
        history[view['day']] = day_record(view, briefing, prior, offers=offers, terms_rows=terms_rows)
    state['weekly_days'] = history
    return {'current': _period(history, end), 'previous': _period(history, end - timedelta(days=7))}


# One compact import of previously published full-scope reports. Keep fixtures and
# pilot runs independent of the production cohort, even when domains overlap.
SEED_REPO = 'MateuszD0/Pracownie'
SEED_END = '2026-11-21'


def seed_weekly_history(state: dict, day: str, repository: str, namespace: str) -> None:
    if (repository.casefold() != SEED_REPO.casefold() or namespace != 'monitor'
            or day < SEED_END or state.get('weekly_seed') == SEED_END):
        return
    cutoff = (date.fromisoformat(day) - timedelta(days=180)).isoformat()
    if SEED_END > cutoff:
        seed = json.loads(files('pracownie').joinpath('weekly_seed_2026_11_21.json').read_text(encoding='utf-8'))
        history = state.setdefault('weekly_days', {})
        for key, entry in seed['days'].items():
            if cutoff < key <= day:
                history.setdefault(key, entry['groups'])
    state['weekly_seed'] = SEED_END
