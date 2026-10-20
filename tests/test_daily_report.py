import json

import pytest
from PIL import Image

from pracownie.browser import BrowserScanner
from pracownie.extract import extract_fields
from pracownie.model import Change, Result
from pracownie.presentation import build_view, render_html, render_text
from pracownie.report import verify_outputs, write_outputs
from pracownie.web import prepare_web

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


def test_matched_changes_survive_parser_migration_and_distinct_promos_share_an_amount():
    entries = daily_results()
    entries[0].changes[0].kind = "review"
    entries[0].changes[0].note = "Zmieniono reguły odczytu"
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


def test_uncategorized_visible_copy_is_monitored():
    fields, _ = extract_fields({"blocks": [{"heading": "Witamy", "text": "Buduj razem z nami"}]}, AFTER)
    assert fields["tekst:witamy:tresc"].value == "Buduj razem z nami"


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
            assert "Rabat 10%" in await page.locator('[data-page="glowna"]').inner_text()
            assert "Rabat 20%" in await page.locator('[data-page="glowna"]').inner_text()
            assert "Kosztorys gratis" in await page.locator('[data-page="projekt"]').inner_text()
            assert "4 290,00 zł" in await page.locator('[data-page="projekt"]').inner_text()
            assert not await page.locator('.day-domain img[src="x"]').count()
            if scripts:
                await page.locator("#page-filter").select_option("glowna")
                assert not await page.locator('[data-page="projekt"]').is_visible()
                await page.locator("#search").fill("brak-domeny")
                assert not await page.locator(".day-domain").is_visible()
                assert not await page.evaluate("Boolean(window.injected)")
                assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors
            await context.close()
