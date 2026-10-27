import csv
import io
import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from pracownie.browser import BrowserScanner
from pracownie.dashboard import render_dashboard_documents
from pracownie.model import Change, Result, load_sites
from pracownie.presentation import build_view, render_html, render_text
from pracownie.relationships import relationship_snapshot
from pracownie.web import export_standalone


def relationship_view():
    before, after = '2026-10-26T05:00:00+00:00', '2026-10-27T05:00:00+00:00'
    results = []
    for domain, discount in [('partner.pl','20%'), ('other.pl','30%')]:
        for page in ['glowna','projekt']:
            url = f'https://{domain}/' + ('dom' if page=='projekt' else '')
            changes = [Change('changed','promocje','Promocja','Rabat 10%','Rabat '+discount,before,after,url,'podstawowy')]
            results.append(Result(domain,page,'podstawowy','changed',url,changes,
                observed_at=after,compared_at=before,data_quality='ok',
                communication={'comparable':True,'ready':True,'changes':1}))
    context = {'source':{'as_of':'2026-10-27','complete':True},
               'domains':{'partner.pl':{'group':'partner','name':'Partner Sp. z o.o.','code':'PAR'},
                          'other.pl':{'group':'other','name':'other.pl','code':''}},
               'without_website':[{'code':'OFF','name':'Pracownia bez WWW','domain':None,'website':None}]}
    return build_view('2026-10-27',results,{'finished_at':after,'relationships':context},{},['partner.pl','other.pl'])


def test_reviewed_registry_matches_the_uploaded_complete_list_and_retains_exclusion():
    registry = json.loads(Path('config/partners.json').read_text())
    sites = load_sites(Path('config/sites.json'))
    assert len(registry['partners']) == 98 and registry['source']['complete']
    assert registry['source']['no_website_confirmed']
    assert len({p['code'] for p in registry['partners']}) == 98
    assert sum(not p['domain'] for p in registry['partners']) == 18
    context = relationship_snapshot([s.domain for s in sites])
    assert len(sites) == 112 and 'extradom.pl' not in context['domains']
    assert sum(p['group']=='partner' for p in context['domains'].values()) == 80
    assert sum(p['group']=='other' for p in context['domains'].values()) == 32
    assert context['domains']['planujdom.pl']['group'] == 'partner'
    assert '@' not in json.dumps(registry)


def test_both_groups_have_changes_in_html_markdown_text_and_no_website_is_not_a_scan_error():
    view = relationship_view()
    html = BeautifulSoup(render_html(view),'html.parser')
    assert len(html.select('#brief-main [data-rel-group=partner]')) == 1
    assert len(html.select('#brief-main [data-rel-group=other]')) == 1
    assert html.select_one('#without-websites [data-no-website-partner]').text.endswith('Bez strony WWW')
    assert len(html.select('[data-communication-domain]')) == 2
    assert len(html.select('[id]')) == len({n['id'] for n in html.select('[id]')})
    docs = render_dashboard_documents(view,'https://github.com/test/repo/releases/tag/day')
    for report in [docs['DASHBOARD.md'],render_text(view)]:
        assert 'Współpracujące z nami'.casefold() in report.casefold()
        assert 'Niewspółpracujące z nami'.casefold() in report.casefold()
        assert 'Rabat 20%' in report and 'Rabat 30%' in report
    assert 'Bez strony WWW' in docs['DASHBOARD.md'] and 'Pracownia bez WWW' in docs['DASHBOARD.md']
    assert view['counts']['domains'] == 2 and len(view['rows']) == 2


@pytest.mark.browser
@pytest.mark.parametrize('portable',[False,True])
async def test_groups_filter_counts_evidence_reset_and_export_together(tmp_path,executable,portable):
    view = relationship_view()
    index = tmp_path/'index.html'
    index.write_text(render_html(view))
    if portable:
        target = tmp_path/'portable.html'
        export_standalone(index,target)
    else:
        target = index
    async with BrowserScanner(executable,settle_ms=0) as scanner:
        context = await scanner.browser.new_context(viewport={'width':390,'height':844},accept_downloads=True)
        page = await context.new_page()
        errors = []
        page.on('pageerror',lambda e:errors.append(str(e)))
        await page.set_content(target.read_text())
        assert await page.locator('[data-brief-id]:visible').count() == 2
        await page.locator('#relationship-filter').select_option('partner')
        assert await page.locator('[data-brief-id]:visible').count() == 1
        assert await page.locator('.day-domain:visible').count() == 1
        assert '1/1' in await page.locator('#brief-coverage').inner_text()
        assert not await page.locator('[data-relationship-heading=other]').first.is_visible()
        await page.locator('[data-brief-id]:visible a').click()
        assert 'partner.pl' in await page.locator('.brief-proof:visible').inner_text()
        await page.locator('#search').fill('PAR')
        assert await page.locator('.day-domain:visible').count() == 1
        await page.locator('#search').fill('')
        await page.locator('#relationship-filter').select_option('other')
        assert await page.locator('[data-brief-id]:visible').count() == 1
        assert not await page.locator('#without-websites').is_visible()
        if not portable:
            async with page.expect_download() as event:
                await page.locator('#export-visible').click()
            download = await event.value
            records = list(csv.DictReader(io.StringIO((await download.path()).read_text(encoding='utf-8-sig')),delimiter=';'))
            assert len(records) == 1 and records[0]['Pracownia'] == 'other.pl'
            assert records[0]['Współpraca'] == 'Niewspółpracujące z nami'
        await page.locator('.filter-disclosure > summary').click()
        await page.locator('#reset-filters').click()
        assert await page.locator('#relationship-filter').input_value() == 'all'
        assert await page.locator('[data-brief-id]:visible').count() == 2
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert await page.locator('#brief-main [data-relationship-heading]:visible th').evaluate_all('(els)=>els.every(e=>e.getBoundingClientRect().width>=e.closest("table").getBoundingClientRect().width*.9)')
        assert not errors
        await context.close()


@pytest.mark.browser
@pytest.mark.parametrize('portable',[False,True])
async def test_both_groups_keep_five_changes_visible_before_expanding(tmp_path,executable,portable):
    view = relationship_view()
    for domain in ['partner.pl','other.pl']:
        base = next(e for e in view['journal'] if e['domain']==domain)
        view['journal'] += [dict(base,id=domain+str(i),after=f'Rabat {21+i}% z kodem OFERTA{i}') for i in range(5)]
    document = tmp_path/'index.html'
    document.write_text(render_html(view))
    if portable:
        target=tmp_path/'portable.html'
        export_standalone(document,target)
        document=target
    async with BrowserScanner(executable,settle_ms=0) as scanner:
        page=await scanner.browser.new_page()
        await page.set_content(document.read_text())
        assert await page.locator('#brief-main [data-rel-group=partner]:visible').count()==5
        assert await page.locator('#brief-main [data-rel-group=other]:visible').count()==5
        await page.locator('#brief-more').click()
        assert await page.locator('#brief-main [data-brief-id]:visible').count()==12
        await page.locator('#relationship-filter').select_option('partner')
        assert await page.locator('#brief-main [data-brief-id]:visible').count()==5
        await page.close()
