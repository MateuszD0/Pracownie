import copy

from test_management_dashboard import management_view

from pracownie.dashboard import render_dashboard_documents
from pracownie.management import build_management
from pracownie.signals import classify, supporting_reason


def event(**values):
    original = copy.deepcopy(management_view()['journal'][0])
    return {**original, **values}


def test_same_control_value_moving_context_is_not_a_new_promotion():
    value = 'PROMOCJA - Pakiet dodatków za 69 zł'
    entries = [event(id='add', category='funkcje', before='brak', after=value),
               event(id='remove', category='funkcje', before=value, after='brak')]
    primary, supporting = classify(entries)
    assert not primary and len(supporting) == 2
    # A genuinely different new benefit must not be discarded with the move.
    primary, _ = classify(entries + [event(id='new', category='funkcje', before='brak', after='Kosztorys gratis')])
    assert [e['id'] for e in primary] == ['new']


def test_other_selected_project_cannot_be_attributed_to_the_frozen_project():
    wrong = event(project='E-268a Dom parterowy', context='ZAMÓW PROJEKT / Projekt:: E-101', before='brak', after='Pakiet dodatków gratis')
    correct = dict(wrong, context='ZAMÓW PROJEKT / Projekt:: E-268a')
    assert 'inny projekt' in supporting_reason(wrong)
    assert not supporting_reason(correct)


def test_supporting_observations_preserved_and_not_reported_as_unchanged():
    view = management_view()
    original = next(e for e in view['journal'] if e['category'] == 'promocje')
    view['journal'] = [dict(original, description='Źródło grafiki w zestawie banerów',
                            before='https://site.test/v1/banner.webp', after='https://site.test/v2/banner.webp')]
    for row in view['rows']:
        for page in row['pages']:
            if row['domain'] == original['domain']:
                page['communication'].update(daily=True, label='Zmiany komunikacji: 1')
    data = build_management(view)
    assert not data['items'] and data['secondary'][0]['id'] == original['id']
    docs = render_dashboard_documents(view, 'https://github.com/test/monitor/releases/tag/day')
    assert 'Brak ustalonej zmiany biznesowej' in docs['DASHBOARD.md']
    assert 'nie ustalono zmiany wyglądu' in docs['dashboard/testpl.md']
    assert 'https://site.test/v1/banner.webp' in docs['dashboard/testpl.md']


def test_daily_table_contains_the_finding_and_matching_before_after_links():
    view = management_view()
    first = next(e for e in view['journal'] if e['category'] == 'promocje')
    first['evidence'] = {'przed': '2026-10-20/before.webp', 'po': '2026-10-20/after.webp'}
    previews = {first['evidence']['przed']: 'https://example.com/before.jpg', first['evidence']['po']: 'https://example.com/after.jpg'}
    docs = render_dashboard_documents(view, 'https://github.com/test/monitor/releases/tag/day', previews=previews)
    root = docs['DASHBOARD.md']
    assert 'Rabat 10%' in root.split('## Wszystkie pracownie')[1]
    assert '[Przed](https://example.com/before.jpg)' in root
    assert '[Po](https://example.com/after.jpg)' in root
    assert 'Obie strony porównane:' in root


def test_price_and_unmatched_faq_are_not_sales_changes_but_offer_edit_is():
    assert supporting_reason(event(description='Treść', communication_role='text', unmatched=True, before='brak', after='Jak uzyskać warunki zabudowy?'))
    assert supporting_reason(event(before='brak', after='5 490 zł najniższa cena'))
    assert not supporting_reason(event(before='Darmowy projekt ogrzewania', after='Darmowy projekt ogrzewania i wentylacji', description='Nagłówek'))


def test_export_carries_the_business_vs_supporting_classification():
    import csv
    import io

    from pracownie.journal import render_journal_csv

    view = management_view()
    view['journal'][0].update(description='Źródło grafiki', before='https://a.test/v1.png', after='https://a.test/v2.png')
    rows = list(csv.DictReader(io.StringIO(render_journal_csv(view).lstrip('\ufeff')), delimiter=';'))
    first = next(r for r in rows if r['Co się zmieniło'] == 'Źródło grafiki')
    assert first['Ocena'] == 'Obserwacja pomocnicza'
    assert 'nie ustalono zmiany wyglądu' in first['Wyjaśnienie']
