import csv
import io
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from pracownie.browser import BrowserScanner, TransientFetchError, retry_after_seconds
from pracownie.model import Change, Result, Scenario, Site
from pracownie.offers import primary_offer
from pracownie.presentation import build_view, render_html, render_markdown

BEFORE = "2026-10-19T06:00:00+00:00"
AFTER = "2026-10-20T06:00:00+00:00"


def management_view():
    entries = []
    for page in ["glowna", "projekt"]:
        changes = [Change("changed", "promocje", "Promocja", "Rabat 10%", "Rabat 20%", BEFORE, AFTER, "https://test.pl/#oferta", "podstawowy")]
        if page == "projekt":
            changes += [Change("changed", "dodatki", "Kosztorys", "150 zł", "gratis", BEFORE, AFTER, "https://test.pl/dom", "podstawowy")]
        changes += [Change("visual", "obraz", "Obraz", None, None, BEFORE, AFTER, "https://test.pl/", "podstawowy", details={"description": "Zmienił się obraz strony: górna część strony"})]
        result = Result("test.pl", page, "podstawowy", "changed", "https://test.pl/", changes, observed_at=AFTER, compared_at=BEFORE, data_quality="ok")
        if page == "projekt":
            quote = {"kind": "price", "currency": "PLN", "quality": "ok", "field_key": "adapter:cena", "source": "adapter", "role": "current"}
            result.offer = {**quote, "amount": "4500", "observed_at": AFTER}
            result.before_offer = {**quote, "amount": "5000", "observed_at": BEFORE}
        entries.append(result)
    entries += [Result("blocked.pl", p, "podstawowy", "error", "https://blocked.pl", error="Odpowiedź HTTP 403") for p in ["glowna", "projekt"]]
    return build_view("2026-10-20", entries, {"finished_at": AFTER}, {}, ["test.pl", "blocked.pl"])


def test_management_counts_firms_once_and_does_not_promote_pixel_noise_or_missing_data():
    view = management_view()
    data = view["management"]
    assert data["metrics"]["price_cuts"] == data["metrics"]["promotions"] == data["metrics"]["extras"] == 1
    assert len(data["items"]) == 3 and len(data["secondary"]) == 3
    assert data["metrics"]["communication"] == data["metrics"]["home_changes"] == data["metrics"]["project_changes"] == 1
    assert any(e["selected_price"] and e["delta"] == "-500.00" for e in data["secondary"])
    soup = BeautifulSoup(render_html(view), "html.parser")
    assert "0/4" in soup.select_one('#executive').text
    assert len(soup.select('#journal [data-journal-domain]')) == 3
    assert len(soup.select('#secondary-journal [data-journal-domain]')) == 3
    assert '403' in soup.select_one('#availability').text
    assert not soup.select('#secondary[open], #diagnostic-observations[open], .day-domain[open]')
    assert 'Zmienił się obraz' not in render_markdown(view).split('<details>')[0]
    assert not [s for s in soup.select('[id]') if len(soup.select('[id="'+s['id']+'"]')) > 1]


def test_management_excludes_gaps_and_stale_captures_from_daily_kpis():
    entries = [Result("test.pl", "projekt", "podstawowy", "changed", "https://test.pl/dom", [Change("changed", "promocje", "Promocja", "10%", "20%", "2026-10-17T06:00:00+00:00", AFTER, "https://test.pl/dom", "podstawowy")], observed_at=BEFORE, compared_at="2026-10-17T06:00:00+00:00", data_quality="ok")]
    view = build_view("2026-10-20", entries, {"finished_at": AFTER}, {}, ["test.pl"])
    assert view["management"]["metrics"]["promotions"] == 0
    assert not view["management"]["items"]
    assert len(view["management"]["secondary"]) == 1
    assert view["counts"]["project"] == 0 and not view["rows"][0]["pages"][1]["daily"]


def test_retry_after_supports_origin_seconds_and_dates_without_early_retry():
    assert retry_after_seconds("90") == 90
    assert retry_after_seconds("-5") == 0
    assert retry_after_seconds("invalid") == 0
    delay = retry_after_seconds(format_datetime(datetime.now(UTC) + timedelta(seconds=60)))
    assert 58 <= delay <= 60


@pytest.mark.browser
async def test_management_filters_export_watchlist_and_mobile_layout(executable):
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        context = await scanner.browser.new_context(viewport={"width": 390, "height": 844})
        page = await context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.set_content(render_html(management_view()))
        assert await page.locator('#metric-communication').text_content() == '1'
        assert await page.locator('#briefing').is_visible()
        assert not await page.locator('#secondary-journal').is_visible()
        await page.locator('.filter-disclosure > summary').click()
        await page.locator('[data-filter="price"]').click()
        assert await page.locator('[data-filter="price"]').evaluate('e=>e===document.activeElement')
        await page.locator('[data-filter="all"]').click()
        await page.locator('#page-filter').select_option('glowna')
        assert await page.locator('#metric-project_changes').text_content() == '—'
        assert await page.locator('#metric-home_changes').text_content() == '1'
        await page.locator('#full-journal > summary').click()
        assert await page.locator('#journal tr[data-journal-domain]:visible').count() == 1
        assert await page.locator('[data-brief-id]:visible').count() == 1
        await page.locator('.directory > summary').click()
        assert await page.locator('[data-communication-page=projekt]:visible').count() == 0
        assert await page.locator('[data-communication-domain]:visible').count() == 2
        async with page.expect_download() as download_event:
            await page.locator('#export-visible').click()
        download = await download_event.value
        rows = list(csv.DictReader(io.StringIO((await download.path()).read_text(encoding='utf-8-sig')), delimiter=';'))
        assert len(rows) == 1 and rows[0]['Strona'] == 'glowna'
        await page.locator('#availability > summary').click()
        await page.locator('[data-watch="test.pl"]').click()
        await page.locator('#watch-only').check()
        assert not await page.locator('[data-availability-domain="blocked.pl"]').is_visible()
        await page.locator('#search').fill('brak')
        assert 'Brak pracowni' in await page.locator('#summary-title').text_content()
        assert await page.locator('#metric-home_changes').text_content() == '—'
        await page.locator('#reset-filters').click()
        assert await page.locator('#metric-communication').text_content() == '1'
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors
        await context.close()


@pytest.mark.browser
async def test_refusal_link_is_used(executable):
    # Exercise the real scanner with local public HTML, including the CMP
    # semantics that its former button-only handler missed.
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        page = await scanner.browser.new_page()
        await page.set_content('<div role="dialog">Cookies <a href="#" onclick="this.parentElement.remove();return false">Tylko niezbędne</a></div>')
        await scanner.cookies(page)
        assert await page.locator('[role=dialog]').count() == 0
        await page.close()


@pytest.mark.browser
@pytest.mark.parametrize(('style', 'quality'), [('opacity:0', 'ok'), ('position:fixed;left:-10000px', 'ok'), ('position:fixed;top:20px;opacity:1', 'partial')])
async def test_only_a_rendered_cookie_panel_degrades_offer_quality(executable, sample_site, tmp_path, style, quality):
    sample_site.cookie_panel = '<div role="dialog" style="' + style + '">Pliki cookies <button>Ustawienia</button></div>'
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        site = Site("test.pl", sample_site.url, sample_site.url + '/projekt-domu-testowy')
        capture = await scanner.capture(site, 'projekt', site.project_url, Scenario('podstawowy', 'Karta'), tmp_path / 'shot.png')
        assert capture.snapshot.quality == quality
        assert 'consent' in capture.snapshot.document


@pytest.mark.browser
async def test_origin_rate_limit_stops_subsequent_domain_reads(executable, sample_site, tmp_path):
    sample_site.rate_limited = True
    site = Site("test.pl", sample_site.url, sample_site.url + '/projekt-domu-testowy')
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        with pytest.raises(TransientFetchError) as first:
            await scanner.capture(site, 'projekt', site.project_url, Scenario('podstawowy', 'Karta'), tmp_path / 'shot.png')
        assert first.value.retry_after == 90
        requests = sample_site.requests
        with pytest.raises(TransientFetchError) as next_read:
            await scanner.capture(site, 'glowna', site.home_url, Scenario('podstawowy', 'Główna'), tmp_path / 'home.png')
        assert next_read.value.retry_after > 85
        assert sample_site.requests == requests


@pytest.mark.browser
@pytest.mark.parametrize(('domain', 'text', 'expected', 'tax'), [('projektyka.pl', '5649,-', '5649.00', ''), ('projektyszkieletowe.pl', 'DOM—B55 pow. użytkowa 121,30 m2 \n4899 zł\nZAMAWIAM\n(w tym 23% VAT)', '4899.00', 'gross')])
async def test_nonstandard_project_prices_use_verified_field_instead_of_other_amounts(executable, sample_site, tmp_path, domain, text, expected, tax):
    sites = json.loads(Path('config/sites.json').read_text())['sites']
    rule = next(s for s in sites if s['domain'] == domain)['field_selectors'][0]
    sample_site.cookie_panel = '<div id="quoted">' + text + '</div><footer>Kapitał zakładowy: 187 200 zł</footer>'
    site = Site('test.pl', sample_site.url, sample_site.url + '/projekt-domu-testowy', field_selectors=[{**rule, 'selector': '#quoted'}])
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        captured = await scanner.capture(site, 'projekt', site.project_url, Scenario('podstawowy', 'Karta'), tmp_path / 'shot.png')
    quote = primary_offer(captured.snapshot)
    assert quote['amount'] == expected and quote['currency'] == 'PLN'
    assert quote['tax'] == tax and quote['field_key'] == 'adapter:cena-projektu'


@pytest.mark.browser
@pytest.mark.parametrize('panel', [
    '<div id="cookiescript_badge" role="dialog" style="position:fixed;bottom:10px;width:31px;height:31px">Cookies</div>',
    '<script>setTimeout(()=>{const d=document.createElement("div");d.id="cookie-notice";d.style="position:fixed;inset:0;background:white;z-index:1000";d.setAttribute("role","dialog");d.innerHTML=\'Cookies <button id="cn-close-notice" onclick="this.parentElement.remove()">Nie wyrażam zgody</button>\';document.body.append(d)},150)</script>',
])
async def test_cookie_badge_and_late_refusal_do_not_invalidate_public_offer(executable, sample_site, tmp_path, panel):
    sample_site.cookie_panel = panel
    site = Site('test.pl', sample_site.url, sample_site.url + '/projekt-domu-testowy')
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        capture = await scanner.capture(site, 'projekt', site.project_url, Scenario('podstawowy', 'Karta'), tmp_path / 'shot.png')
    assert capture.snapshot.quality == 'ok'
    assert not any('Widoczny panel cookies' in w for w in capture.snapshot.warnings)
    if 'cookiescript_badge' not in panel:
        assert not capture.snapshot.document['consent']
