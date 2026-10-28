"""Missing-page repairs must improve access without inventing daily pairs."""
from types import SimpleNamespace

import pytest

from pracownie.browser import EXTRACT, BrowserScanner, discovery_catalogues, project_candidates
from pracownie.model import Site


def test_catalogue_discovery_is_bounded_and_rejects_external_navigation():
    site = Site('test.pl', 'https://test.pl/')
    payload = {'links': [], 'discovery_links': [
        {'text': 'Katalog projektów', 'url': 'https://test.pl/katalog/'},
        {'text': 'Bestsellery', 'url': 'https://test.pl/hity/'},
        {'text': 'Katalog projektów', 'url': 'https://external.pl/'},
        {'text': 'Projekty', 'url': 'https://test.pl/'},
        {'text': 'Katalog projektów', 'url': 'https://test.pl/katalog/#oferta'},
        {'text': 'Projekty gotowe', 'url': 'https://test.pl/gotowe/'},
    ]}
    assert discovery_catalogues(site, payload) == ['https://test.pl/hity/', 'https://test.pl/katalog/']


def test_cart_and_advertisement_links_are_never_project_candidates():
    site = Site('test.pl', 'https://test.pl/')
    payload = {'links': [{'url': 'https://test.pl' + path, 'text': 'Dom Nowoczesny',
                          'image': True, 'context': '120 m2 4000 zł'}
                         for path in ['/pl/basket', '/pl/banner/9', '/kategoria/nowoczesna-stodola', '/projekt/dom-testowy']]}
    assert [x['url'] for _, x in project_candidates(site, payload)] == ['https://test.pl/projekt/dom-testowy']


async def test_discovery_follows_catalogue_from_navigation_and_keeps_failure_reason(tmp_path):
    site = Site('test.pl', 'https://test.pl/')
    home = SimpleNamespace(payload={'discovery_links': [{'text': 'Katalog projektów', 'url': 'https://test.pl/katalog/'}]}, snapshot=SimpleNamespace(url=site.home_url))
    calls = []
    class Scanner(BrowserScanner):
        async def capture(self, site, page, url, *args):
            calls.append(url)
            if page == 'glowna':
                return SimpleNamespace(snapshot=SimpleNamespace(title='Katalog'), payload={'url': url, 'links': [
                    {'url': 'https://test.pl/produkt/listing', 'text': 'Niepoprawny'},
                    {'url': 'https://test.pl/produkt/dom', 'text': 'Dom'}]})
            if url.endswith('listing'):
                raise ValueError('Adres prowadzi do kategorii zamiast pojedynczego projektu')
            return SimpleNamespace(snapshot=SimpleNamespace(url=url, title='Dom Testowy'))
    selected, _, warnings = await Scanner().discover_project(site, home, tmp_path)
    assert selected['url'] == 'https://test.pl/produkt/dom'
    assert len(calls) == 3 and 'kategorii' in warnings[0]


@pytest.mark.browser
async def test_navigation_catalogue_is_extracted_separately_from_offer(executable):
    from playwright.async_api import async_playwright
    async with async_playwright() as manager:
        browser = await manager.chromium.launch(executable_path=executable)
        page = await browser.new_page()
        await page.set_content('<nav><a href="https://test.pl/katalog/">Katalog projektów</a></nav><main><h1>Pracownia testowa</h1><p>Projektujemy domy z pełnym wsparciem architekta.</p></main>')
        payload = await page.evaluate(EXTRACT, 'glowna')
        assert payload['discovery_links'] == [{'url': 'https://test.pl/katalog/', 'text': 'Katalog projektów'}]
        assert not payload['links']
        assert not any('Katalog' in x['text'] for x in payload['blocks'])
        await browser.close()


def test_partial_first_read_is_a_repair_not_a_promise_of_tomorrows_comparison():
    from pracownie.gaps import page_gap
    from pracownie.model import Result
    from pracownie.presentation import build_view
    result = Result('test.pl', 'glowna', 'podstawowy', 'partial', 'https://test.pl/',
                    observed_at='2026-10-28T06:00:00+00:00', data_quality='partial',
                    warnings=['Widoczny panel cookies może zasłaniać ofertę.'],
                    communication={'status': 'baseline', 'comparable': False, 'ready': False})
    view = build_view('2026-10-28', [result], {}, {}, ['test.pl'])
    page = view['rows'][0]['pages'][0]
    assert 'Pierwszy zapis' not in page['communication']['label']
    gap = page_gap(page, '2026-10-28')
    assert gap['category'] == 'repair' and 'cookies' in gap['reason']
    assert not page['communication']['daily']


def test_first_usable_read_and_old_history_remain_distinct_from_failed_reads():
    from pracownie.gaps import page_gap
    page = {'page': 'glowna', 'current_read': True, 'data_quality': 'ok', 'communication': {'ready': True}}
    first = page_gap(page, '2026-10-28')
    assert first['category'] == 'history' and '2026-10-29' in first['action']
    gap = page_gap(dict(page, compared_at='2026-10-26T06:00:00+00:00', gap_days=2), '2026-10-28')
    assert gap['category'] == 'history' and 'sprzed 2 dni' in gap['reason']
    failed = page_gap(dict(page, current_read=False, error_text='Witryna blokuje dostęp (403).'), '2026-10-28')
    assert failed['category'] == 'repair' and 'odrzucony' in failed['status']


def test_search_page_with_project_words_in_navigation_is_not_a_project():
    from pracownie.extract import validate_payload
    with pytest.raises(ValueError, match='kategorii'):
        validate_payload({'h1': 'szukaj', 'text': 'Projekt domu w nawigacji, powierzchnia i katalog projektów gotowych.'}, product=True)
