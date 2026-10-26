import copy
import json
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup
from test_commercial_verification import AT, BEFORE, URL, shot
from test_management_dashboard import management_view

from pracownie.briefing import build_briefing
from pracownie.browser import BrowserScanner
from pracownie.commercial import verify_offers
from pracownie.dashboard import render_dashboard_documents
from pracownie.intelligence import update_intelligence
from pracownie.model import Result, Site
from pracownie.presentation import render_html
from pracownie.web import export_standalone


def test_one_campaign_has_one_event_and_both_source_places_without_merging_other_terms():
    view = management_view()
    briefing = build_briefing(view)
    campaign = next(e for e in briefing['events'] if e['bucket'] == 'promotions')
    assert len([e for e in briefing['events'] if e['bucket'] == 'promotions']) == 1
    assert campaign['pages'] == ['glowna', 'projekt']
    assert len(campaign['observation_ids']) == 2
    view['journal'][1]['after'] = 'Rabat 30%'
    assert len([e for e in build_briefing(view)['events'] if e['bucket'] == 'promotions']) == 2


def test_missing_promotion_is_visible_but_geometry_and_price_blobs_are_not_business_alerts():
    view = management_view()
    base = view['journal'][0]
    view['journal'] = [dict(base, after='brak'),
        dict(base, id='pixels', category='obraz', specific=True, description='Położenie i rozmiar: treść strony (18 px w dół)', before='300 × 225', after='300 × 188'),
        dict(base, id='price-copy', category='komunikacja', before='Pierwotna cena wynosiła: 5000 zł. Aktualna cena wynosi: 4500 zł.', after='brak')]
    data = build_briefing(view)
    assert [e['tier'] for e in data['events']].count('review') == 1
    assert all(e['tier'] == 'technical' for e in data['events'] if e['bucket'] != 'promotions')
    soup = BeautifulSoup(render_html(view), 'html.parser')
    assert 'Rabat 10%' in soup.select_one('[data-brief-section=review]').text
    assert '18 px' not in soup.select_one('#briefing').text
    assert 'nie potwierdza' in soup.select_one('[data-brief-section=review]').text
    docs = render_dashboard_documents(view, 'https://github.com/test/monitor/releases/tag/day')
    review = docs['DASHBOARD.md'].split('## Ważne do sprawdzenia')[1].split('## Braki porównania')[0]
    assert 'Rabat 10%' in review and 'Do sprawdzenia' in review


def test_unique_dated_announcement_absorbs_generic_not_started_message():
    view = management_view()
    base = view['journal'][0]
    view['journal'] = [dict(base, id=str(i), before='brak', after=text,
        commercial_check={'status':'scheduled','summary':text,'note':''})
        for i,text in enumerate(['Promocja od 2026-10-27, koniec za:', 'Promocja jeszcze się nie rozpoczęła.'])]
    events = build_briefing(view)['events']
    assert len(events) == 1 and len(events[0]['observation_ids']) == 2
    view['journal'].append(dict(view['journal'][0], id='another', after='Promocja od 2026-10-30'))
    assert len(build_briefing(view)['events']) == 3


def test_registry_is_idempotent_preserves_last_capture_date_and_retains_history():
    view = management_view()
    view['journal'][0]['after'] = 'brak'
    snapshot = shot(['Kosztorys gratis do każdego projektu'], at=BEFORE)
    state = {'snapshots':{snapshot.key:snapshot.to_dict()}}
    first = update_intelligence(state, view)
    second = update_intelligence(state, view)
    assert len(first['history']) == len(second['history'])
    assert len(second['pending']) == 1
    assert second['offers'][0]['sources'][0]['observed_at'] == BEFORE
    future = copy.deepcopy(view)
    future['day'] = '2027-05-01'
    future['journal'] = []
    assert not update_intelligence(state, future)['history']


async def test_pending_offer_is_rechecked_even_without_a_new_dom_change(tmp_path):
    before = 'Promocja JESIEŃ -20%'
    project = shot([before])
    home = shot(['Opis oferty pracowni.'], url='https://test.pl/')
    result = Result('test.pl', 'projekt', 'podstawowy', 'unchanged', URL, [], observed_at=AT, compared_at=BEFORE)
    pending = {'id': {'id':'id','domain':'test.pl','page':'projekt','url':URL,'before':before,'after':'brak',
        'category':'promocje','label':'Baner','first_seen':'2026-10-25','before_at':BEFORE,
        'next_check':'2026-10-26','status':'open'}}
    calls = []

    class Scanner:
        async def capture(self, site, page, url, scenario, dest):
            calls.append(url)
            return SimpleNamespace(snapshot=project)

    await verify_offers(Site('test.pl', 'https://test.pl/'), [SimpleNamespace(snapshot=s) for s in [home, project]],
                        [result], [], Scanner(), tmp_path, tmp_path/'archive', pending=pending)
    assert calls == [URL]
    assert pending['id']['status'] == 'resolved'
    assert pending['id']['check']['status'] == 'still_present'
    assert result.changes == []  # A follow-up must never invent a daily delta.


@pytest.mark.browser
async def test_published_portable_file_search_filters_reset_and_evidence_work(tmp_path, executable):
    document = tmp_path/'index.html'
    view = management_view()
    document.write_text(render_html(view))
    standalone = tmp_path/'portable.html'
    export_standalone(document, standalone)
    soup = BeautifulSoup(standalone.read_text(), 'html.parser')
    assert len(json.loads(soup.select_one('#data').string)['events']) == 2
    async with BrowserScanner(executable) as scanner:
        context = await scanner.browser.new_context(viewport={'width':390,'height':844})
        page = await context.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        await page.set_content(standalone.read_text())
        await page.locator('#search').fill('blocked.pl')
        assert await page.locator('.day-domain:visible').count() == 1
        assert 'Brak pracowni' not in await page.locator('#portable-status').inner_text()
        await page.locator('#search').fill('nieistniejaca')
        assert await page.locator('.day-domain:visible').count() == 0
        assert 'Brak pracowni' in await page.locator('#portable-status').inner_text()
        await page.locator('.filter-disclosure > summary').click()
        await page.locator('#reset-filters').click()
        assert await page.locator('.day-domain:visible').count() == 2
        await page.locator('#page-filter').select_option('glowna')
        assert await page.locator('[data-brief-id]:visible').count() == 1
        await page.locator('[data-brief-id]:visible a').click()
        assert await page.locator('#brief-proofs').get_attribute('open') is not None
        assert await page.locator('.brief-proof:visible').count() == 1
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors
        await context.close()
