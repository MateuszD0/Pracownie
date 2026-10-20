import csv
import io

import pytest
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw

from pracownie.browser import BrowserScanner
from pracownie.compare import compare
from pracownie.images import image_difference, visual_evidence
from pracownie.journal import render_journal_csv
from pracownie.model import Change, Field, Result, Snapshot
from pracownie.observations import visual_description
from pracownie.presentation import build_view, render_html

BEFORE = "2026-10-20T06:00:00+00:00"
AFTER = "2026-10-21T06:00:00+00:00"


def shot(at=BEFORE):
    return Snapshot("test.pl", "projekt", "podstawowy", "https://test.pl/dom", at, "Dom", {"promo": Field("Promocja", "Rabat 10%", "promocje", observed_at=at)}, ["oferta"], "", "chrome-old|extractor=72356a749d038e0b-abc")


def test_reviewed_addition_of_general_text_does_not_disable_existing_sales_fields():
    old, new = shot(), shot(AFTER)
    new.renderer = "chrome-new|extractor=dba81208d46a4f37-abc"
    new.contract = "sales-v2:abc"
    new.fields["promo"].value = "Rabat 20%"
    new.fields["new-copy"] = Field("Treść", "Zapraszamy", "tresc")
    changes, _ = compare(old, new)
    assert next(c for c in changes if c.field_key == "promo").kind == "changed"
    assert next(c for c in changes if c.field_key == "new-copy").kind == "review"
    old.renderer = "chrome-old|extractor=unknown-abc"
    assert all(c.kind == "review" for c in compare(old, new)[0])
    old.renderer = "chrome-old|extractor=72356a749d038e0b-different-adapter"
    assert all(c.kind == "review" for c in compare(old, new)[0])


def test_archived_raw_captures_can_be_replayed_without_relabelling_their_dates():
    old, new = shot(), shot(AFTER)
    for s, text, contract in [(old, "Rabat 10%", "previous:abc"), (new, "Rabat 20%", "sales-v2:abc")]:
        s.contract = contract
        s.document = {"raw_schema": "visible-v2", "adapter": "abc", "observed_at": s.observed_at, "ignore_patterns": [], "payload": {"blocks": [{"heading": "oferta", "text": text}]}}
    changes, retained = compare(old, new)
    assert len(changes) == 1 and changes[0].kind == "changed"
    assert changes[0].before == "Rabat 10%" and changes[0].after == "Rabat 20%"
    assert changes[0].before_at == BEFORE and retained.observed_at == AFTER
    new.document["observed_at"] = BEFORE
    assert all(c.kind == "review" for c in compare(old, new)[0])


def test_real_pixel_change_gets_a_crop_and_specific_style_and_asset_facts(tmp_path):
    before, after = tmp_path / "before.png", tmp_path / "after.png"
    image = Image.new("RGB", (1280, 3000), "white")
    image.save(before)
    ImageDraw.Draw(image).rectangle((40, 1800, 500, 1900), fill="red")
    image.save(after)
    diff = image_difference(before, after, tmp_path / "diff.png")
    proofs = visual_evidence(before, after, tmp_path, diff)
    assert set(proofs) == {"fragment_przed", "fragment_po", "zmieniony_obszar"}
    with Image.open(proofs["fragment_po"]) as crop:
        assert crop.height <= 1000 and crop.getpixel((crop.width // 2, crop.height // 2)) == (255, 0, 0)
    old, new = shot(), shot(AFTER)
    element = {"key": "#hero", "label": "baner", "src": "https://test.pl/old.jpg", "background": "white", "rect": [0, 0, 1280, 400]}
    old.document = {"visual": {"schema": 1, "elements": [element]}}
    new.document = {"visual": {"schema": 1, "elements": [{**element, "src": "https://test.pl/new.jpg", "background": "red"}]}}
    details = visual_description(old, new, diff)
    assert any("grafiki" in f["what"] for f in details["facts"])
    assert any("Kolor tła" in f["what"] for f in details["facts"])


def journal_view():
    changes = [Change("changed", "promocje", "Promocja", "Rabat 10%", "Rabat 20%", BEFORE, AFTER, "https://test.pl/dom#promocja", "podstawowy")]
    visual = Change("visual", "obraz", "Zmiana banera", None, "", BEFORE, AFTER, "https://test.pl/dom", "podstawowy", details={"description": "Kolor tła banera", "facts": [{"what": "Kolor tła: baner", "before": "biały", "after": "czerwony", "url": "https://test.pl/dom#hero"}]})
    changes += [visual, Change("review", "dodatki", "Niepewne", "150 zł", "gratis", BEFORE, AFTER, "https://test.pl/dom", "podstawowy", note="Zmieniono reguły odczytu")]
    result = Result("test.pl", "projekt", "podstawowy", "changed", "https://test.pl/dom", changes, observed_at=AFTER, compared_at=BEFORE, data_quality="ok", evidence={"przed": "2026-10-21/before.png", "po": "2026-10-21/after.png"})
    return build_view("2026-10-21", [result], {"finished_at": AFTER}, {}, ["test.pl"])


def test_daily_table_separates_offer_and_visual_facts_and_excludes_uncertain_reads():
    view = journal_view()
    assert [r["type"] for r in view["journal"]] == ["Promocja", "Wygląd"]
    assert all(r["daily"] and r["gap_days"] == 1 for r in view["journal"])
    assert view["journal"][1]["source"] == "https://test.pl/dom#hero"
    assert len(view["rows"][0]["reviews"]) == 1
    rows = list(csv.DictReader(io.StringIO(render_journal_csv(view).lstrip("\ufeff")), delimiter=";"))
    assert len(rows) == 2 and rows[0]["Było"] == "Rabat 10%" and rows[0]["Jest"] == "Rabat 20%"
    soup = BeautifulSoup(render_html(view), "html.parser")
    assert len(soup.select('#journal [data-journal-domain]')) == 2
    assert len(soup.select('#journal .journal-proof')) == 1
    assert "https://test.pl/dom#promocja" in str(soup.select_one('#journal'))


@pytest.mark.browser
async def test_change_table_filters_and_native_proof_links(executable):
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        for scripts in (True, False):
            context = await scanner.browser.new_context(java_script_enabled=scripts, viewport={"width": 390, "height": 844})
            page = await context.new_page()
            await page.set_content(render_html(journal_view()))
            if scripts:
                await page.locator('#journal-category').select_option('obraz')
                assert await page.locator('#journal tr[data-category="obraz"]').is_visible()
                assert not await page.locator('#journal tr[data-category="promocje"]').is_visible()
            await page.locator('#journal a[href^="#dowod-"]').last.click()
            assert await page.locator('#journal .journal-proof').get_attribute('open') is not None
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await context.close()
