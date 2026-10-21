import json

import pytest
from bs4 import BeautifulSoup
from PIL import Image

from pracownie.browser import BrowserScanner
from pracownie.extract import extract_fields
from pracownie.model import Change, Result
from pracownie.presentation import (
    assessment,
    build_view,
    render_html,
    render_markdown,
    render_text,
    scan_comparison,
)
from pracownie.report import verify_outputs, write_outputs
from pracownie.web import export_standalone, prepare_web

DAY = "2026-10-20"
BEFORE = "2026-10-19T06:00:00+00:00"
AFTER = "2026-10-20T06:00:00+00:00"


def daily_results():
    entries = []
    for page, category, old, new in [
        ("glowna", "promocje", "Rabat 10%", "Rabat 20%"),
        ("projekt", "dodatki", "Kosztorys 150 zł", "Kosztorys gratis"),
    ]:
        url = "https://test.pl/" + ("dom" if page == "projekt" else "")
        change = Change("changed", category, "Oferta", old, new, BEFORE, AFTER, url, "podstawowy")
        evidence = {name: f"{DAY}/test.pl/{page}/{name}.png" for name in ["przed", "po"]}
        entries.append(Result("test.pl", page, "podstawowy", "changed", url, [change], observed_at=AFTER, compared_at=BEFORE, data_quality="ok", evidence=evidence))
    return entries


def make_view(entries):
    return build_view(DAY, entries, {"finished_at": AFTER}, {}, ["test.pl"])


def test_each_page_exposes_its_dates_differences_and_historical_gap():
    entries = daily_results()
    entries[0].compared_at = "2026-10-16T06:00:00+00:00"
    report = make_view(entries)
    home, card = report["rows"][0]["pages"]
    assert home["gap_days"] == 4 and not home["daily"]
    assert card["daily"] and card["gap_days"] == 1
    assert home["events"][0]["after"] == "Rabat 20%"
    assert card["events"][0]["after"] == "Kosztorys gratis"
    assert "Luka 4 dni" in render_text(report)
    assert report["comparison"]["paired_pages"] == 1
    assert report["comparison"]["paired_home"] == 0
    assert report["comparison"]["paired_project"] == 1


def test_scan_connection_counts_only_real_captures_from_both_days():
    report = make_view(daily_results())
    pair = report["comparison"]
    assert pair["before_day"] == "2026-10-19" and pair["after_day"] == DAY
    assert pair["paired_pages"] == 2 and pair["screenshot_pairs"] == 2
    assert pair["paired_home"] == pair["paired_project"] == 1
    # A stale capture or failed current read cannot masquerade as today's scan.
    report["rows"][0]["pages"][0]["observed_at"] = BEFORE
    report["rows"][0]["pages"][1]["observed_at"] = None
    assert scan_comparison(DAY, report["rows"])["paired_pages"] == 0


def test_matched_changes_survive_parser_migration_and_distinct_promos_share_an_amount():
    entries = daily_results()
    entries[0].changes[0].kind = "review"
    entries[0].changes[0].note = "Zmieniono reguły odczytu"
    entries[0].changes[0].evidence = {"przed": DAY + "/option-before.png", "po": DAY + "/option-after.png"}
    entries[0].changes += [
        Change("review", "funkcje", "Nowe pole", None, "Nowy sposób odczytu", BEFORE, AFTER, entries[0].url, "podstawowy", note="Zmieniono reguły odczytu"),
        Change("changed", "promocje", "Transport", "Dostawa 150 zł", "Dostawa gratis", BEFORE, AFTER, entries[0].url, "podstawowy"),
        Change("changed", "promocje", "Dodatek", "Dodatek 150 zł", "Dodatek gratis", BEFORE, AFTER, entries[0].url, "podstawowy"),
    ]
    row = make_view(entries)["rows"][0]
    assert len(row["reviews"]) == 1
    assert row["reviews"][0]["after"] == "Rabat 20%"
    assert len(row["pages"][0]["events"]) == 2
    assert row["pages"][0]["extraction_changes"] == 2


@pytest.mark.browser
async def test_connected_scans_show_observations_and_open_their_own_evidence(executable):
    entries = daily_results()
    entries[0].changes[0].kind = "review"
    entries[0].changes[0].note = "Niepełny odczyt sekcji"
    entries[0].changes[0].evidence = {"przed": DAY + "/option-before.png", "po": DAY + "/option-after.png"}
    report = make_view(entries)
    document = render_html(report)
    assert '19.10.2026 → 20.10.2026' in document
    assert '1 stron głównych i 1 kart projektów' in document
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        context = await scanner.browser.new_context(viewport={"width": 390, "height": 844})
        page = await context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.set_content(document)
        assert not await page.locator('#observations .event').is_visible()
        await page.locator('#diagnostic-observations > summary').click()
        assert 'Rabat 10%' in await page.locator('#observations').inner_text()
        assert 'Rabat 20%' in await page.locator('#observations').inner_text()
        assert 'niezweryfikowany odczyt' in await page.locator('#observations').inner_text()
        # Review cards must open the review's images, not an unrelated confirmed event.
        await page.locator('#observations [data-open]').click()
        assert await page.locator('dialog').is_visible()
        assert await page.locator('dialog img[src="option-before.png"]').count() == 1
        assert 'Rabat 20%' in await page.locator('dialog').inner_text()
        await page.locator('#close').click()
        await page.locator('#page-filter').select_option('projekt')
        assert not await page.locator('#observations .event:visible').count()
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors
        await context.close()


def test_uncategorized_visible_copy_is_monitored():
    fields, _ = extract_fields({"blocks": [{"heading": "Witamy", "text": "Buduj razem z nami"}]}, AFTER)
    assert fields["tekst:witamy:tresc"].value == "Buduj razem z nami"


def test_technical_uncertainty_is_owned_by_monitor_and_preserved_outside_business_findings():
    entries = daily_results()
    entries[0].changes[0].kind = "review"
    entries[0].changes[0].note = "Zmieniono reguły odczytu"
    entries[1].changes = [Change("review", "ceny", "Termin", "2026-10-20", "2026-10-21", BEFORE, AFTER, entries[1].url, "podstawowy", field_key="oferta:dom:priceValidUntil")]
    report = make_view(entries)
    conclusion = assessment(report)
    assert conclusion["title"] == "Zakres porównania komunikacji"
    assert conclusion["unchanged"] == 0 and conclusion["uncompared"] == 1
    assert report["counts"]["events"] == 0
    soup = BeautifulSoup(render_html(report), "html.parser")
    assert "Nie masz niczego potwierdzać" in soup.select_one('#assessment').get_text()
    assert not soup.select('#observations .event')
    # Preserve the source evidence, but do not promote technical noise to findings.
    assert 'Rabat 10%' in soup.select_one('details.reviews').get_text()
    assert soup.select('details.reviews:not([open])')
    markdown = render_markdown(report)
    headline = markdown.split('<details>')[0]
    assert 'Zakres porównania komunikacji' in headline
    assert 'Pełne porównanie zapisanego zakresu: 0/2 stron' in headline
    assert 'Rabat 10%' not in headline
    assert 'Nie masz niczego potwierdzać' in render_text(report)


def test_price_conclusion_counts_only_comparable_prices_captured_on_both_days():
    entries = daily_results()
    for entry in entries:
        entry.changes = []
    quote = {"kind": "price", "amount": "3500.00", "currency": "PLN", "field_key": "oferta:dom:price", "quality": "ok"}
    entries[1].offer = {**quote, "observed_at": AFTER}
    entries[1].before_offer = {**quote, "observed_at": BEFORE}
    report = make_view(entries)
    assert assessment(report)["prices"] == assessment(report)["unchanged"] == 1
    assert assessment(report)["uncompared"] == 0
    assert '| test.pl | 3 500,00 zł | 3 500,00 zł | bez zmiany ceny |' in render_markdown(report)
    assert '3 500,00 zł' not in render_markdown(report).split('<details>')[0]
    entries[1].before_offer["observed_at"] = "2026-10-18T06:00:00+00:00"
    conclusion = assessment(make_view(entries))
    assert conclusion["prices"] == conclusion["unchanged"] == 0
    assert conclusion["uncompared"] == 1


def test_web_uses_verified_images_and_does_not_modify_archive(tmp_path):
    source, target = tmp_path / "report", tmp_path / "web"
    entries = daily_results()
    for entry in entries:
        for path in entry.evidence.values():
            image = source / path
            image.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (100, 120), "white").save(image)
    metadata = {"finished_at": AFTER, "started_at": AFTER, "elapsed_seconds": 0, "run_id": "test"}
    write_outputs(source, DAY, entries, metadata, {}, ["test.pl"])
    summary = prepare_web(source, DAY, target)
    assert summary["images"] == 1
    assert len(list(target.rglob("*.jpg"))) == 1
    assert "__REPORT_DATA__" not in (target / DAY / "index.html").read_text()
    assert 'src="screenshots/' in (target / DAY / "index.html").read_text()
    assert (target / f"{DAY}.txt").is_file()
    standalone = BeautifulSoup((target / f"porownanie-{DAY}.html").read_text(), "html.parser")
    assert not standalone.select('script, button, select')
    assert standalone.select('img') and all(i['src'].startswith('data:image/jpeg;base64,') for i in standalone.select('img'))
    verify_outputs(source, DAY)
    view = json.loads((source / DAY / "oferty.json").read_text())
    view["rows"][0]["evidence"]["po"] = "../../unowned.png"
    (source / DAY / "oferty.json").write_text(json.dumps(view))
    with pytest.raises(ValueError, match="Uszkodzony wynik"):
        prepare_web(source, DAY, tmp_path / "unsafe")


@pytest.mark.browser
async def test_report_renders_both_pages_with_and_without_javascript(executable):
    report = make_view(daily_results())
    report["rows"][0]["name"] = '</script><img src=x onerror="window.injected=true">'
    report["rows"][0]["previous_text"] = "4 590,00 zł"
    report["rows"][0]["current_text"] = "4 290,00 zł"
    document = render_html(report)
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        for scripts in [False, True]:
            context = await scanner.browser.new_context(java_script_enabled=scripts, viewport={"width": 390, "height": 844})
            page = await context.new_page()
            errors = []
            page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
            await page.set_content(document)
            assert await page.locator(".daily-page").count() == 2
            assert not await page.locator('.daily-page').first.is_visible()
            await page.locator('.day-domain > summary').click()
            assert "Rabat 10%" in await page.locator('.daily-page[data-page="glowna"]').inner_text()
            assert "Rabat 20%" in await page.locator('.daily-page[data-page="glowna"]').inner_text()
            assert "Kosztorys gratis" in await page.locator('.daily-page[data-page="projekt"]').inner_text()
            await page.locator('.daily-page[data-page="projekt"] .project-prices > summary').click()
            assert "4 290,00 zł" in await page.locator('.daily-page[data-page="projekt"]').inner_text()
            assert not await page.locator('.day-domain img[src="x"]').count()
            if scripts:
                await page.locator("#page-filter").select_option("glowna")
                assert not await page.locator('.daily-page[data-page="projekt"]').is_visible()
                await page.locator("#search").fill("brak-domeny")
                assert not await page.locator(".day-domain").is_visible()
                assert not await page.evaluate("Boolean(window.injected)")
                assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors
            await context.close()


def test_review_comparisons_are_saved_in_html_and_open_without_scripts():
    entries = daily_results()
    entries[0].changes[0].kind = "review"
    report = make_view(entries)
    soup = BeautifulSoup(render_html(report), 'html.parser')
    assert 'Rabat 10%' in soup.select_one('#observations').get_text()
    assert 'Rabat 20%' in soup.select_one('#observations').get_text()
    assert soup.select_one('#observations del').text == '10%'
    assert soup.select_one('#observations ins').text == '20%'
    assert soup.select_one('#observations img')
    assert soup.select('details.page-proofs:not([open])')
    assert soup.select('#diagnostic-observations:not([open]), .day-domain:not([open])')


@pytest.mark.browser
async def test_portable_comparison_displays_text_and_images_without_scripts_or_side_files(executable, tmp_path):
    entries = daily_results()
    entries[0].changes[0].kind = "review"
    for entry in entries:
        for relative in entry.evidence.values():
            path = tmp_path / relative.removeprefix(DAY + '/')
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new('RGB', (80, 100), 'white').save(path)
    document = tmp_path / 'index.html'
    document.write_text(render_html(make_view(entries)))
    standalone = tmp_path / 'portable.html'
    export_standalone(document, standalone, archive_url='https://example.com/report.zip')
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        context = await scanner.browser.new_context(java_script_enabled=False, viewport={'width': 390, 'height': 844})
        page = await context.new_page()
        network = []
        page.on('request', lambda request: network.append(request.url))
        await page.set_content(standalone.read_text())
        await page.locator('#diagnostic-observations > summary').click()
        assert await page.locator('#observations .event').is_visible()
        assert 'Rabat 10%' in await page.locator('#observations').inner_text()
        assert 'Rabat 20%' in await page.locator('#observations').inner_text()
        assert await page.locator('#observations del').is_visible()
        assert await page.locator('#observations ins').is_visible()
        assert not await page.locator('script, button').count()
        await page.locator('#observations img').last.scroll_into_view_if_needed()
        await page.wait_for_function("[...document.querySelectorAll('#observations img')].every(i=>i.complete&&i.naturalWidth>0)")
        assert not network
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await context.close()
