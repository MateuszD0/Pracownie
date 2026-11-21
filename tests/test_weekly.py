from datetime import datetime, timedelta

from test_management_dashboard import management_view

from pracownie.briefing import build_briefing
from pracownie.weekly import SEED_REPO, _period, day_record, seed_weekly_history, weekly_summary


def view_for_groups():
    view = management_view()
    view['metadata']['relationships'] = {'domains': {
        'test.pl': {'group': 'partner'}, 'blocked.pl': {'group': 'other'},
    }}
    return view


def test_same_day_revision_replaces_signal_and_absent_days_are_not_zero():
    view = view_for_groups()
    state = {}
    data = weekly_summary(state, view, build_briefing(view))
    group = data['current']['groups']['partner']
    assert group['metrics']['price_cut']['count'] == 1
    assert len(data['current']['days']) == 1 and len(data['current']['missing_days']) == 6
    assert data['current']['groups']['other']['metrics']['price_cut']['count'] is None
    assert len(data['previous']['missing_days']) == 7
    view['rows'][0]['delta'] = '0'
    revised = weekly_summary(state, view, build_briefing(view))
    assert revised['current']['groups']['partner']['metrics']['price_cut']['count'] == 0
    assert len(state['weekly_days']) == 1


def test_distinct_studios_across_pages_and_days_and_new_promo_vs_changed_wording():
    view = view_for_groups()
    for page in view['rows'][0]['pages']:
        page.setdefault('communication', {})['daily'] = True
    sample = view['journal'][0]
    view['journal'] = [
        dict(sample, before='brak', after='Rabat 20% z kodem DOM20', id='home',
             commercial_check={'status': 'added', 'summary': 'Dodano komunikat'}),
        dict(sample, before='brak', after='Rabat 20% z kodem DOM20', id='card', page='projekt',
             commercial_check={'status': 'added', 'summary': 'Dodano komunikat'}),
        dict(sample, before='Skorzystaj z rabatu z kodem STALY50', after='Odbierz rabat z kodem STALY50',
             id='copy', commercial_check={'status': 'changed', 'summary': 'Zmieniono komunikat'}),
        dict(sample, before='brak', after='Rabat 30% z kodem WKRÓTCE', id='future',
             commercial_check={'status': 'scheduled', 'summary': 'Zapowiedź'}),
    ]
    # The earlier report compared both pages and contained no matching campaign.
    previous = {'partner': {'compared_both': ['test.pl']}}
    history = {view['day']: day_record(view, build_briefing(view), previous)}
    # A second day carries verified daily comparisons from the same studio.
    next_day = '2026-10-21'
    view['day'] = next_day
    for item in view['journal']:
        for key in ('before_at', 'after_at'):
            item[key] = (datetime.fromisoformat(item[key]) + timedelta(days=1)).isoformat()
    history[next_day] = day_record(view, build_briefing(view), history['2026-10-20'])
    output = _period(history, datetime.fromisoformat(next_day).date())
    stats = output['groups']['partner']
    assert stats['monitored'] == 1 and stats['compared_price'] == 1
    assert stats['metrics']['promotion_added']['count'] == 1 and stats['metrics']['wording']['count'] == 1
    example, = stats['metrics']['promotion_added']['examples']
    assert example['source'].startswith('https://test.pl/') and 'DOM20' in example['after']
    assert 'WKRÓTCE' not in example['after']


def test_bootstrap_includes_both_full_archived_weeks_and_preserves_newer_editions():
    for repo, namespace in [('example/fork', 'monitor'), (SEED_REPO, 'pilot')]:
        state = {}
        seed_weekly_history(state, '2026-11-21', repo, namespace)
        assert not state
    state = {}
    seed_weekly_history(state, '2026-11-21', SEED_REPO, 'monitor')
    start, end = min(state['weekly_days']), max(state['weekly_days'])
    assert (start, end, len(state['weekly_days'])) == ('2026-11-08', '2026-11-21', 14)
    current = _period(state['weekly_days'], datetime.fromisoformat(end).date())
    assert len(current['days']) == 7 and not current['missing_days']
    assert current['groups']['partner']['monitored'] == 80 and current['groups']['other']['monitored'] == 32
    state['weekly_days'][end] = {'repaired': True}
    seed_weekly_history(state, end, SEED_REPO, 'monitor')
    assert state['weekly_days'][end] == {'repaired': True}
    expired = {}
    seed_weekly_history(expired, '2027-11-21', SEED_REPO, 'monitor')
    assert not expired.get('weekly_days')


def test_same_campaign_republication_and_material_term_changes_are_not_counted_as_launch_or_wording():
    view = view_for_groups()
    for page in view['rows'][0]['pages']:
        page.setdefault('communication', {})['daily'] = True
    base = view['journal'][0]
    view['journal'] = [
        dict(base, id='again', before='brak', after='Rabat 20% z kodem JUZ20',
             commercial_check={'status': 'added', 'summary': 'Dodano'}),
        dict(base, id='more', before='Rabat 10% z kodem JUZ20', after='Rabat 25% z kodem JUZ20',
             commercial_check={'status': 'changed', 'summary': 'Zmieniono'}),
        dict(base, id='reading', before='9 min czytania', after='10 min czytania', category='komunikacja',
             communication_check={'status': 'confirmed'}),
    ]
    prior = {'partner': {'compared_both': ['test.pl'], 'markers': {'test.pl': ['code:juz20']}}}
    signals = day_record(view, build_briefing(view), prior)['partner']['signals']
    assert 'promotion_added' not in signals and 'wording' not in signals


def test_previous_state_without_campaign_basis_keeps_coverage_without_promoting_legacy_signals():
    view = view_for_groups()
    old = day_record(view, build_briefing(view))
    for group in old.values():
        del group['compared_promo']
        del group['compared_project']
    old['partner']['signals']['wording'] = {'test.pl': {'domain': 'test.pl', 'day': view['day']}}
    week = _period({view['day']: old}, datetime.fromisoformat(view['day']).date())
    counts = week['groups']['partner']['metrics']
    assert counts['price_cut']['count'] == 1
    assert all(counts[k]['count'] is None and not counts[k]['examples']
               for k in ('promotion_added', 'wording', 'extras'))


def test_homepage_only_does_not_contribute_to_project_package_denominator():
    view = view_for_groups()
    row = next(r for r in view['rows'] if r['domain'] == 'test.pl')
    row['project_selected'] = True
    for page in row['pages']:
        page['communication']['daily'] = page['page'] == 'glowna'
        page['daily'] = page['page'] == 'glowna'
    perspective = weekly_summary({}, view, build_briefing(view))['current']['groups']['partner']
    assert perspective['compared_any'] == 1
    assert perspective['metrics']['extras'] == {'count': None, 'compared': 0, 'examples': []}
