import copy

from bs4 import BeautifulSoup
from test_management_dashboard import management_view

from pracownie.dashboard import render_dashboard_documents
from pracownie.management import build_management
from pracownie.presentation import render_html
from pracownie.readout import comparison_parts, digest_groups
from pracownie.signals import classify


def test_digest_keeps_both_pages_and_multiple_business_topics_per_studio():
    view = management_view()
    data = build_management(view)
    groups = digest_groups(data['items'])
    assert {(g['domain'], g['page'], g['business_bucket']) for g in groups} == {
        ('test.pl', 'glowna', 'promotions'), ('test.pl', 'projekt', 'promotions'), ('test.pl', 'projekt', 'extras')}
    assert sum(g['count'] for g in groups) == len(data['items'])
    soup = BeautifulSoup(render_html(view), 'html.parser')
    assert len(soup.select('#business-highlights tr')) == 3
    assert 'gratis' in soup.select_one('#business-highlights').text
    assert not soup.select('.directory[open]')
    assert soup.select_one('#business-highlights .changed-token').text == '10'


def test_differences_at_end_of_long_copy_are_visible_with_exact_values_retained():
    prefix = 'Informacja o projekcie i warunkach oferty. ' * 20
    before, after = prefix + 'Kosztorys za 150 zł.', prefix + 'Kosztorys gratis.'
    left, right = comparison_parts(before, after)
    assert '150' in ''.join(p['text'] for p in left)
    assert 'gratis' in ''.join(p['text'] for p in right if p['changed'])
    assert ''.join(p['text'] for p in right).startswith('…')
    assert all(len(''.join(p['text'] for p in side)) <= 222 for side in [left, right])
    view = management_view()
    view['journal'][0].update(before=before, after=after)
    docs = render_dashboard_documents(view, 'https://github.com/test/monitor/releases/tag/day')
    assert 'do 600 znaków' in docs['dashboard/testpl.md']
    assert before in render_html(view) and after in render_html(view)


def test_identical_heading_observations_merge_without_losing_source_ids():
    view = management_view()
    original = view['journal'][0]
    original.update(category='komunikacja', description='Nagłówek', before='Dom na lata', after='Dom dla rodziny')
    visual = {**original, 'id': 'visual-heading', 'category': 'obraz', 'description': 'Widoczny nagłówek: Dom dla rodziny', 'specific': True}
    view['journal'].append(visual)
    data = build_management(view)
    item = next(e for e in data['items'] if e['id'] == original['id'])
    assert item['observation_count'] == 2
    assert set(item['observation_ids']) == {original['id'], visual['id']}
    assert len(data['items']) == 3
    visual['after'] = 'Dom dla Ciebie'
    assert len(build_management(view)['items']) == 4


def test_cookie_buttons_and_verified_animation_do_not_become_business_alerts():
    original = management_view()['journal'][0]
    entries = [dict(original, id='cookie', category='komunikacja', before='brak', after='Akceptuj wszystko'),
               dict(original, id='counter', domain='hexagreen.pl', category='komunikacja', before='18+ autorskich projektów domów', after='17+ autorskich projektów domów'),
               dict(original, id='real', domain='hexagreen.pl', category='komunikacja', before='Projekty domów', after='Projekty domów z pakietem gratis')]
    primary, supporting = classify(entries)
    assert [e['id'] for e in primary] == ['real']
    assert {e['id'] for e in supporting} == {'cookie', 'counter'}


def test_company_proof_pairs_have_dates_inline_images_and_no_single_page_navigation():
    view = copy.deepcopy(management_view())
    first = view['journal'][0]
    first['evidence'] = {'przed': '2026-10-20/before.webp', 'po': '2026-10-20/after.webp'}
    previews = {'2026-10-20/before.webp': 'https://example.com/before.jpg', '2026-10-20/after.webp': 'https://example.com/after.jpg'}
    docs = render_dashboard_documents(view, 'https://github.com/test/monitor/releases/tag/day', previews=previews)
    company = docs['dashboard/testpl.md']
    assert 'Strony porównania:' not in company and '1/1' not in company
    assert '![Przed](https://example.com/before.jpg)' in company
    assert '![Po](https://example.com/after.jpg)' in company
    assert '| Przed · 19.10.2026' in company and '| Po · 20.10.2026' in company
    assert 'Niepełne porównanie' in docs['dashboard/blockedpl.md']
    assert 'dashboard/testpl.md#karta-projektu' in docs['DASHBOARD.md']


def test_large_repeated_capture_keeps_changed_tail_visible():
    # Captured pages can repeat the same navigation thousands of times.
    prefix = 'Powtarzany tekst. ' * 10000
    before, after = comparison_parts(prefix + '150 zł', prefix + 'gratis')
    assert '150' in ''.join(p['text'] for p in before)
    assert 'gratis' in ''.join(p['text'] for p in after if p['changed'])
