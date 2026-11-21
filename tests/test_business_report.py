from bs4 import BeautifulSoup
from test_extras import extra_view

from pracownie.business_report import html_report, markdown_documents, text_report
from pracownie.dashboard import render_dashboard_documents
from pracownie.extras import package_changes
from pracownie.presentation import render_html, render_markdown, render_text


def test_offer_comparison_reaches_all_published_formats_and_links_both_captures():
    view = extra_view()
    view['metadata']['intelligence'] = {'promo_terms': [], 'package_changes': package_changes(view)}
    docs = render_dashboard_documents(view, 'https://github.com/test/repo/releases/tag/day')
    overview = docs['DASHBOARD.md']
    detail = docs['dashboard/porownanie-ofert.md']
    assert 'Kosztorys' in overview and '(dashboard/porownanie-ofert.md)' in overview
    for content in [detail, render_text(view), render_markdown(view), BeautifulSoup(render_html(view), 'html.parser').get_text()]:
        assert 'za dopłatą → w cenie' in content
        assert 'Kosztorys 150 zł' in content and 'Kosztorys w cenie projektu' in content
        assert '5 000,00 zł' in content
    panel = BeautifulSoup(html_report(view), 'html.parser').select_one('#offer-comparison')
    assert panel.select_one('a[href="https://test.pl/dom#dodatki"]')
    assert 'Brak pary pomiarów położenia' in panel.get_text()
    assert 'Widoczność tej samej oferty (brak porównania)' in panel.get_text()


def test_one_day_offer_register_keeps_baseline_out_of_alerts_and_escapes_quotes():
    view = extra_view()
    record = {'quote': 'Rabat do 50% <em>x</em>', 'source': 'https://test.pl/regulamin#warunki',
              'value': 'do 50%', 'observed_at': view['journal'][0]['after_at'], 'unavailable': True}
    view['metadata']['intelligence'] = {'promo_terms': [
        {'domain': 'test.pl', 'code': 'RABAT50', 'campaign': '', 'status': 'observed', 'page': 'terms',
         'before': None, 'after': record, 'changed_fields': []}]}
    summary, docs = markdown_documents(view, 'dashboard', 'DASHBOARD.md', {})
    assert 'RABAT50' not in ''.join(summary)
    register = docs['dashboard/porownanie-ofert-register-1.md']
    assert 'Pracownia oznacza tę ofertę jako niedostępną.' in register and '&lt;em&gt;' in register
    assert 'RABAT50' in register and 'https://test.pl/regulamin#warunki' in register
    assert 'RABAT50' in ' '.join(text_report(view))
    assert '<em>x</em>' not in html_report(view)


def test_web_export_preserves_campaign_scope_quotes_in_archive_and_portable_html(tmp_path):
    import json

    from test_campaign_card import AFTER, DAY, inputs, term

    from pracownie.campaign_card import build_campaign_cards
    from pracownie.report import write_outputs
    from pracownie.web import prepare_web

    state, view = inputs()
    quote = 'Kod BLACK500 obejmuje projekt Jantar VII.'
    cards = build_campaign_cards(state, view, [term(quote)])
    assert cards[0]['scope']['evidence'][0]['quote'] == quote
    meta = {'finished_at': AFTER, 'started_at': AFTER, 'elapsed_seconds': 0, 'run_id': 'test',
            'intelligence': {'promo_terms': [], 'campaign_cards': cards}}
    source, target = tmp_path / 'source', tmp_path / 'publish'
    write_outputs(source, DAY, [], meta, {}, ['test.pl'])
    prepare_web(source, DAY, target)
    page = BeautifulSoup((target / DAY / 'index.html').read_text(), 'html.parser')
    saved = json.loads(page.select_one('#data').string)['metadata']['intelligence']['campaign_cards'][0]
    assert saved['scope']['evidence'] == cards[0]['scope']['evidence']
    portable = BeautifulSoup((target / f'porownanie-{DAY}.html').read_text(), 'html.parser')
    assert quote in portable.select_one('#offer-comparison').get_text()
