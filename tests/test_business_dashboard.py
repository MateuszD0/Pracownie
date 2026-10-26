import copy
import csv
import io
import json
import os
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from test_management_dashboard import management_view

from pracownie.briefing import build_briefing
from pracownie.browser import BrowserScanner
from pracownie.management import build_management, business_highlights, group_changes
from pracownie.presentation import render_html, render_markdown, render_text


@pytest.mark.browser
@pytest.mark.parametrize("scripts", [False, True])
async def test_business_dashboard_hierarchy_links_and_mobile_layout(executable, scripts):
    view = json.loads(Path(os.environ['MONITOR_REVIEW_VIEW']).read_text()) if os.environ.get('MONITOR_REVIEW_VIEW') else management_view()
    if not os.environ.get('MONITOR_REVIEW_VIEW'):
        home = next(e for e in view['journal'] if e['page'] == 'glowna' and e['category'] == 'promocje')
        home['evidence'] = {'przed': view['day'] + '/before.png', 'po': view['day'] + '/after.png'}
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        context = await scanner.browser.new_context(java_script_enabled=scripts, viewport={'width': 1440, 'height': 1000})
        page = await context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.set_content(render_html(view))
        if scripts and (output := os.environ.get('MONITOR_REVIEW_SCREENSHOT')):
            await page.screenshot(path=output, full_page=False)
        assert await page.locator('#business-summary').count() == 1
        assert await page.locator('#business-summary').evaluate("e=>Boolean(e.compareDocumentPosition(document.getElementById('executive')) & Node.DOCUMENT_POSITION_PRECEDING)")
        assert await page.locator('#business-summary').evaluate("e=>Boolean(e.compareDocumentPosition(document.getElementById('communication-coverage')) & Node.DOCUMENT_POSITION_FOLLOWING)")
        assert await page.locator('#communication-coverage').evaluate("e=>Boolean(e.compareDocumentPosition(document.getElementById('daily')) & Node.DOCUMENT_POSITION_FOLLOWING)")
        assert await page.locator('#briefing').is_visible()
        assert not await page.locator('#business-summary').is_visible()
        expected = [e for e in build_briefing(view)['events'] if e['tier'] != 'technical']
        assert await page.locator('[data-brief-id]:visible').count() == len(expected)
        assert await page.locator('#briefing').evaluate("e=>Boolean(e.compareDocumentPosition(document.getElementById('technical-summary')) & Node.DOCUMENT_POSITION_FOLLOWING)")
        proof = page.locator('[data-brief-id]:visible a').first
        if await proof.count():
            target = await proof.get_attribute('href')
            await proof.click()
            assert await page.locator(target).is_visible()
            proof_text = (await page.locator(target).inner_text()).casefold()
            assert 'wczoraj' in proof_text and 'dziś' in proof_text
        assert await page.locator('[data-communication-domain]').count() == len(view['rows'])
        await page.locator('#technical-summary > summary').click()
        link = page.locator('#business-highlights a[data-company-link]').first
        if await link.count():
            target = await link.get_attribute('href')
            await link.click()
            assert await page.locator(target).is_visible()
            assert await page.locator('.day-domain[open]').count() >= 1
            proof_link = page.locator(target + ' a[href^="#firma-dowod-"]')
            if await proof_link.count():
                await proof_link.click()
                assert await page.locator('.firm-proof[open]').count() == 1
                assert await page.locator('.firm-proof[open] img:visible').count() == 2
        await page.set_viewport_size({'width': 390, 'height': 844})
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        if scripts and (output := os.environ.get('MONITOR_REVIEW_SCREENSHOT')):
            await page.screenshot(path=str(Path(output).with_stem(Path(output).stem + '-mobile')), full_page=False)
        assert not errors
        await context.close()


def test_repeated_interactions_are_grouped_per_firm_and_page_with_full_source_history():
    view = management_view()
    original = next(e for e in view['journal'] if e['page'] == 'glowna' and e['category'] == 'promocje')
    original['scenario'] = 'podstawowy'
    repeated = {**original, 'id': original['id'] + '-tab', 'scenario': 'tab', 'context': 'Zakładka z ofertą', 'after': 'Rabat  20%'}
    view['journal'].append(repeated)
    data = build_management(view)
    group = next(e for e in data['items'] if e['page'] == 'glowna')
    assert len(data['items']) == 3 and data['source_count'] == 4
    assert group['scenario'] == 'podstawowy' and group['observation_count'] == 2
    assert set(group['observation_ids']) == {original['id'], repeated['id']}
    assert 'Zakładka z ofertą' in group['contexts']
    # Identical values for differently named offers must remain separate.
    assert len(group_changes([original, dict(original, id='another-offer', description='Inny dodatek')])) == 2
    assert repeated['id'] not in {e['id'] for e in data['secondary']}
    soup = BeautifulSoup(render_html(view), 'html.parser')
    assert len(soup.select('#journal [data-journal-domain]')) == 4
    assert len(soup.select('.firm-change')) == 3
    assert '2 odczytach' in soup.select_one('.firm-change').text
    assert len(soup.select('[id]')) == len({e['id'] for e in soup.select('[id]')})


def test_highlights_prioritize_concrete_offers_and_keep_each_company_once():
    original = copy.deepcopy(management_view()['management']['items'][0])
    entries = [dict(original, id='a', category='dodatki', before='brak', after='Dodatkowy'),
               dict(original, id='b', category='dodatki', before='brak', after='Do projektu domu dodano projekt pompy ciepła gratis')]
    entries.extend(dict(original, id=f'p{i}', domain=f'{i}.pl') for i in range(10))
    # The same offer in a second firm is a separate finding.
    groups = group_changes(entries)
    top = business_highlights(groups)
    assert len(top) == len({e['domain'] for e in top}) == 6
    assert not any(e['after'] == 'Dodatkowy' for e in top)
    assert next(e for e in business_highlights(groups, 20) if e['domain'] == original['domain'])['id'] == 'b'
    promotion = group_changes([dict(original, category='funkcje', before='Pakiet dodatków za 69 zł', after='PROMOCJA - Pakiet dodatków za 39 zł')])[0]
    assert promotion['business_bucket'] == 'promotions'
    assert promotion['category'] == 'funkcje'  # The original evidence remains intact.


def test_daily_business_summary_is_present_in_all_report_formats():
    view = management_view()
    for report in [render_html(view), render_text(view), render_markdown(view)]:
        assert 'Zmiany oferty i komunikacji' in report or 'ZMIANY OFERTY I KOMUNIKACJI' in report
        assert 'Rabat 10%' in report and 'Rabat 20%' in report
        assert 'https://test.pl/#oferta' in report


@pytest.mark.browser
async def test_promotional_controls_follow_business_filters_and_csv(executable):
    view = management_view()
    home = next(e for e in view['journal'] if e['page'] == 'glowna' and e['category'] == 'promocje')
    home.update(category='funkcje', before='Pakiet dodatków za 69 zł', after='PROMOCJA - Pakiet dodatków za 39 zł')
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        context = await scanner.browser.new_context(accept_downloads=True)
        page = await context.new_page()
        await page.set_content(render_html(view))
        await page.locator('.filter-disclosure > summary').click()
        await page.locator('#page-filter').select_option('glowna')
        await page.locator('#journal-category').select_option('sales')
        assert await page.locator('[data-brief-id]:visible').count() == 1
        assert 'Pakiet dodatków' in await page.locator('#brief-main').inner_text()
        await page.locator('[data-brief-id]:visible a').click()
        assert await page.locator('.brief-proof:visible').count() == 1
        await page.locator('#full-journal > summary').click()
        assert await page.locator('#journal [data-journal-domain]:visible').count() == 1
        async with page.expect_download() as download_event:
            await page.locator('#export-visible').click()
        download = await download_event.value
        rows = list(csv.DictReader(io.StringIO((await download.path()).read_text(encoding='utf-8-sig')), delimiter=';'))
        assert len(rows) == 1 and rows[0]['Status'] == 'Zaobserwowana zmiana'
        assert 'Pakiet dodatków' in rows[0]['Co się zmieniło']
        assert rows[0]['Strona'] == 'glowna' and rows[0]['Źródło'] == home['source']
        assert rows[0]['Było'] == home['before'] and rows[0]['Jest'] == home['after']
        await context.close()


@pytest.mark.browser
@pytest.mark.parametrize('scripts', [False, True])
async def test_compact_summary_and_minor_details_keep_sources_and_filters(executable, scripts):
    view = management_view()
    base = view['journal'][0]
    view['journal'].append(dict(base, id='layout', category='obraz', description='Przesunięcie: sekcja oferty (900 px w dół)', before='0', after='900', specific=True))
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        context = await scanner.browser.new_context(java_script_enabled=scripts, viewport={'width': 390, 'height': 844})
        page = await context.new_page()
        await page.set_content(render_html(view))
        assert await page.locator('[data-brief-id]:visible').count() == 2
        assert '900 px' not in await page.locator('#briefing').inner_text()
        assert not await page.locator('#business-minor').is_visible()
        await page.locator('#technical-summary > summary').click()
        await page.locator('.minor-changes > summary').click()
        assert '900 px' in await page.locator('#business-minor').inner_text()
        target = await page.locator('#business-minor a[data-company-link]').get_attribute('href')
        await page.locator('#business-minor a[data-company-link]').click()
        assert await page.locator(target).is_visible()
        if scripts:
            await page.locator('.filter-disclosure > summary').click()
            await page.locator('#page-filter').select_option('projekt')
            assert await page.locator('#business-minor [data-business-domain]').count() == 0
            assert await page.locator('#minor-count').inner_text() == '0'
            assert await page.locator('#business-highlights [data-business-domain]').count() == 2
            assert await page.locator('[data-brief-id]:visible').count() == 2
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await context.close()
