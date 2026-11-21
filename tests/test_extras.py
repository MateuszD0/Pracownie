from copy import deepcopy

import pytest
from test_management_dashboard import management_view

from pracownie.extras import mark_package_context, package_changes
from pracownie.model import Change, Result, Snapshot
from pracownie.presentation import build_view


def extra_view(before='Kosztorys 150 zł', after='Kosztorys w cenie projektu'):
    view = management_view()
    row = view['rows'][0]
    row['url'] = 'https://test.pl/dom'
    row['name'] = 'Dom A'
    row['current']['amount'] = row['previous']['amount']
    row['delta'] = '0.00'
    event = next(e for e in view['journal'] if e['category'] == 'dodatki')
    event.update(before=before, after=after, project='Dom A', source='https://test.pl/dom#dodatki',
                 evidence={'przed': 'before.webp', 'po': 'after.webp'})
    view['journal'] = [event]
    return view


def test_unchanged_project_price_and_dated_change_in_extra():
    view = extra_view()
    original = deepcopy(view)
    change, = package_changes(view)
    assert (change['before_state'], change['after_state']) == ('paid', 'included')
    assert change['name'] == 'Kosztorys' and change['project'] == 'Dom A'
    assert change['unchanged_price'] == '5 000,00 zł'
    assert (change['before_at'], change['after_at']) == (view['journal'][0]['before_at'], view['journal'][0]['after_at'])
    assert change['source'].endswith('/dom#dodatki') and change['observation_id'] == view['journal'][0]['id']
    assert view == original
    view['rows'][0]['current']['amount'] = '4700'
    assert package_changes(view)[0]['unchanged_price'] == ''
    view['rows'][0]['current']['amount'] = '5000'
    view['comparison']['price_domains'] = []
    assert package_changes(view)[0]['unchanged_price'] == ''


@pytest.mark.parametrize(('before', 'after', 'expected'), [
    ('Przedmiar robót: niedostępny', 'Przedmiar robót: 0 zł', ('unavailable', 'included')),
    ('Pakiet Premium gratis', 'Pakiet Premium — 246,00 zł netto + VAT', ('included', 'paid')),
    ('Kosztorys za dopłatą', 'Kosztorys wycofany z oferty', ('paid', 'unavailable')),
    ('Kosztorys 0 zł', 'Kosztorys w cenie', None),
    ('brak', 'Kosztorys gratis', None),
    ('Kosztorys gratis', 'brak', None),
    ('Kosztorys gratis', 'Kosztorys płatny w wybranych wariantach', None),
    ('Kosztorys gratis', 'Kosztorys -150 zł', None),
    ('Kosztorys 150 zł', 'Kosztorys gratis przy zakupie pakietu', None),
    ('Kosztorys uproszczony gratis', 'Kosztorys inwestorski 100 zł', None),
    ('Kosztorys 150 zł i dziennik gratis', 'Kosztorys gratis', None),
])
def test_only_unambiguous_terms_for_same_named_extra(before, after, expected):
    changes = package_changes(extra_view(before, after))
    assert [(c['before_state'], c['after_state']) for c in changes] == ([expected] if expected else [])


@pytest.mark.parametrize('reason', ['home', 'different_card', 'stale', 'partial', 'unselected', 'unverified', 'another_variant'])
def test_only_trustworthy_frozen_card_daily_evidence(reason):
    view = extra_view()
    row, event = view['rows'][0], view['journal'][0]
    if reason == 'home':
        event['page'] = 'glowna'
    elif reason == 'different_card':
        event['source'] = 'https://test.pl/drugi-dom'
    elif reason == 'stale':
        event['before_at'] = '2026-10-18T06:00:00+00:00'
    elif reason == 'partial':
        row['pages'][1]['data_quality'] = 'partial'
    elif reason == 'unselected':
        row['project_selected'] = False
    elif reason == 'unverified':
        event['commercial_check'] = {'status': 'unverified'}
    else:
        event['scenario'] = 'opcja-premium'
    assert not package_changes(view)


def test_structured_label_identifies_value_and_conflicting_quotes_do_not_override_it():
    view = extra_view(before='150 zł', after='gratis')
    view['journal'][0]['description'] = 'Kosztorys'
    assert package_changes(view)[0]['name'] == 'Kosztorys'
    view['journal'].append(dict(view['journal'][0], id='another', before='200 zł'))
    assert not package_changes(view)


@pytest.mark.parametrize('problem', [None, 'renamed_option', 'different_variant', 'missing_history', 'partial', 'different_scenario'])
def test_interactive_named_field_survives_snapshot_to_journal_only_for_the_same_tab_and_variant(problem):
    url = 'https://test.pl/dom'
    old_at, new_at = '2026-10-19T06:00:00+00:00', '2026-10-20T06:00:00+00:00'
    scenario, label = 'tab-10a4', 'Dodatki do wersji murowanej'

    def snapshot(at):
        return Snapshot('test.pl', 'projekt', scenario, url, at, 'Dom A', {}, [], '', 'renderer',
                        document={'payload': {'scenario_label': label, 'variant': ''}})

    old, new = snapshot(old_at), snapshot(new_at)
    if problem == 'renamed_option':
        old.document['payload']['scenario_label'] = 'Dodatki do wersji szkieletowej'
    elif problem == 'different_variant':
        old.document['payload']['variant'] = 'Szkieletowa'
    elif problem == 'missing_history':
        old.document['payload'] = {}
    elif problem == 'partial':
        old.quality = 'partial'
    elif problem == 'different_scenario':
        old.scenario = 'tab-b18d'
    change = Change('changed', 'dodatki', 'Kosztorys', '150 zł', 'gratis', old_at, new_at, url + '#panel', scenario,
                    field_key='adapter:estimate')
    mark_package_context(old, new, [change])
    result = Result('test.pl', 'projekt', scenario, 'changed', url, [change],
                    observed_at=new_at, compared_at=old_at, data_quality='ok', scenario_label=label)
    view = build_view('2026-10-20', [result], {'finished_at': new_at}, {'test.pl': {'url': url, 'name': 'Dom A'}}, ['test.pl'])
    changes = package_changes(view)
    if problem:
        assert not changes
    else:
        item, = changes
        assert item['name'] == 'Kosztorys' and item['before'] == '150 zł' and item['after_state'] == 'included'
        assert (item['scenario'], item['context']) == (scenario, label)
        assert item['source'] == url + '#panel' and item['unchanged_price'] == ''
