import csv
import io
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw

from pracownie.browser import VISUALS, BrowserScanner
from pracownie.compare import compare
from pracownie.images import image_difference, visual_evidence
from pracownie.journal import render_journal_csv
from pracownie.model import Change, Field, Result, Snapshot
from pracownie.observations import visual_description
from pracownie.presentation import build_view, render_html
from pracownie.rebuild import enrich_visual_results

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


def test_source_text_fragment_targets_changed_line_instead_of_unchanged_copy():
    old, new = shot(), shot(AFTER)
    old.fields["promo"].value = "Stałe warunki\nRabat 10%"
    new.fields["promo"].value = "Stałe warunki\nRabat 20%"
    new.document = {"payload": {"blocks": [{"text": text} for text in new.fields["promo"].value.splitlines()]}}
    change = compare(old, new)[0][0]
    assert change.url.endswith("#:~:text=Rabat%2020%25")


def test_known_savings_metadata_cannot_generate_a_project_price_alert():
    old, new = shot(), shot(AFTER)
    bad = "oferta:dom-projekt-1840:price"
    for snapshot, savings in [(old, "200"), (new, "300")]:
        snapshot.fields[bad] = Field("Błędna cena w JSON-LD", savings + " PLN", "ceny", amount=savings, currency="PLN")
        snapshot.fields["adapter:cena-projektu"] = Field("Cena projektu", "5000 PLN", "ceny", amount="5000", currency="PLN")
    assert compare(old, new, [bad])[0] == []
    new.fields["adapter:cena-projektu"].value = "4500 PLN"
    new.fields["adapter:cena-projektu"].amount = "4500"
    changes = compare(old, new, [bad])[0]
    assert len(changes) == 1 and changes[0].field_key == "adapter:cena-projektu" and changes[0].delta == "-500.00"


def test_ocr_literal_quotes_do_not_merge_distinct_tsv_rows(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from pracownie.images import visual_text

    monkeypatch.setattr("pracownie.images.ocr_language", lambda: "pol")
    header = "conf\ttext\n"
    texts = iter([header + '95\t"Rabat\n95\tna\n95\tprojekt\n', header + '95\t"Dodatek\n95\tw\n95\tcenie\n'])
    monkeypatch.setattr("pracownie.images.subprocess.run", lambda *a, **kw: SimpleNamespace(stdout=next(texts), returncode=0))
    context = visual_text({"fragment_przed": tmp_path / "old.png", "fragment_po": tmp_path / "new.png"})
    assert context["before"] == '"Rabat na projekt' and context["after"] == '"Dodatek w cenie'


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


def test_archived_visual_enrichment_accepts_relative_report_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("pracownie.rebuild.visual_text", lambda _: {})
    root = Path("reports")
    folder = root / "2026-10-21/test.pl/projekt/podstawowy"
    folder.mkdir(parents=True)
    image = Image.new("RGB", (200, 300), "white")
    image.save(folder / "przed.png")
    ImageDraw.Draw(image).rectangle((30, 40, 130, 90), fill="red")
    image.save(folder / "po.png")
    evidence = {key: (folder / (key + ".png")).relative_to(root).as_posix() for key in ("przed", "po")}
    result = Result("test.pl", "projekt", "podstawowy", "review", "https://test.pl/dom", [Change("review", "obraz", "Wygląd", None, "", BEFORE, AFTER, "https://test.pl/dom", "podstawowy")], observed_at=AFTER, compared_at=BEFORE, evidence=evidence)
    enrich_visual_results([result], root)
    assert result.changes[0].kind == "visual"
    assert (root / result.evidence["zmieniony_obszar"]).is_file()


def test_banner_description_compares_actual_labels_when_asset_url_is_reused():
    from pracownie.images import VisualDiff

    old, new = shot(), shot(AFTER)
    element = {"key": "#hero", "src": "https://test.pl/banner.jpg", "label": "Rabat 10%"}
    old.document = {"visual": {"schema": 1, "elements": [element]}}
    new.document = {"visual": {"schema": 1, "elements": [{**element, "label": "Rabat 20%"}]}}
    facts = visual_description(old, new, VisualDiff(True, 0.1, (0, 0, 100, 100)))["facts"]
    assert facts == [{"what": "Opis grafiki", "before": "Rabat 10%", "after": "Rabat 20%", "url": new.url, "element": element["key"]}]


def test_reordered_project_images_are_matched_by_asset_instead_of_css_slot():
    from pracownie.images import VisualDiff

    old, new = shot(), shot(AFTER)
    images = [{"key": f"#slot-{i}", "label": name, "src": f"https://test.pl/{i}.webp", "rect": [i * 300, 0, 300, 200]} for i, name in enumerate(["Dom przy Bukowej 40", "Dom przy Bukowej 27"])]
    old.document = {"visual": {"schema": 1, "elements": images}}
    new.document = {"visual": {"schema": 1, "elements": [{**image, "key": images[1 - i]["key"], "rect": images[1 - i]["rect"]} for i, image in enumerate(images)]}}
    details = visual_description(old, new, VisualDiff(True, .1, (0, 0, 600, 200)))
    assert not details['facts'] and details['rotation']
    assert 'istniejących grafik' in details['description']
    # A genuinely new project inserted ahead of old ones must still be found.
    new.document['visual']['elements'] = [{**image, 'key': f'#slot-{i + 1}'} for i, image in enumerate(images)] + [{'key': '#slot-0', 'label': 'Nowy dom', 'src': 'https://test.pl/new.webp'}]
    details = visual_description(old, new, VisualDiff(True, .1, (0, 0, 600, 200)))
    assert len(details['facts']) == 1
    assert details['facts'][0]['what'] == 'Dodana grafika: Nowy dom'
    assert details['facts'][0]['after'] == 'https://test.pl/new.webp'


def test_visual_style_changes_get_separate_readable_rows_with_their_own_sources():
    from pracownie.images import VisualDiff

    old, new = shot(), shot(AFTER)
    element = {'key': '#cta', 'label': 'Zamów projekt', 'background': 'rgb(255, 255, 255)', 'font_size': '16px', 'url': 'https://test.pl/dom#cta'}
    old.document = {'visual': {'schema': 1, 'elements': [element]}}
    new.document = {'visual': {'schema': 1, 'elements': [{**element, 'background': 'rgb(0, 0, 0)', 'font_size': '20px'}]}}
    details = visual_description(old, new, VisualDiff(True, .1, (0, 0, 600, 200)))
    result = Result('test.pl', 'projekt', 'podstawowy', 'changed', new.url, [Change('visual', 'obraz', details['description'], None, None, BEFORE, AFTER, new.url, 'podstawowy', details=details)], observed_at=AFTER, compared_at=BEFORE, data_quality='ok')
    journal = build_view('2026-10-21', [result], {}, {}, ['test.pl'])['journal']
    assert len(journal) == 2 and len({item['id'] for item in journal}) == 2
    color = next(item for item in journal if 'Kolor tła' in item['description'])
    assert color['before'] == 'biały (#FFFFFF)' and color['after'] == 'czarny (#000000)'
    size = next(item for item in journal if 'Rozmiar tekstu' in item['description'])
    assert size['before'] == '16px' and size['after'] == '20px'
    assert all(item['source'] == 'https://test.pl/dom#cta' for item in journal)


def test_archive_rebuild_replaces_stale_positional_image_facts(tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr('pracownie.rebuild.visual_text', lambda _: {})
    folder = tmp_path / '2026-10-21/test.pl/projekt/podstawowy'
    folder.mkdir(parents=True)
    image = Image.new('RGB', (200, 300), 'white')
    image.save(folder / 'przed.png')
    ImageDraw.Draw(image).rectangle((20, 40, 120, 100), fill='red')
    image.save(folder / 'po.png')
    old, new = shot(), shot(AFTER)
    elements = [{'key': '#a', 'src': 'https://test.pl/a.webp'}, {'key': '#b', 'src': 'https://test.pl/b.webp'}]
    old.document = {'visual': {'schema': 1, 'elements': elements}}
    new.document = {'visual': {'schema': 1, 'elements': [{**elements[1], 'key': '#a'}, {**elements[0], 'key': '#b'}]}}
    evidence = {key: (folder / (key + '.png')).relative_to(tmp_path).as_posix() for key in ('przed', 'po')}
    stale = {'description': 'Rzekoma wymiana zdjęcia', 'facts': [{'what': 'Źródło grafiki', 'before': 'a.webp', 'after': 'b.webp', 'url': new.url}], 'basis': 'Stary odczyt'}
    result = Result('test.pl', 'projekt', 'podstawowy', 'changed', new.url, [Change('visual', 'obraz', stale['description'], None, None, BEFORE, AFTER, new.url, 'podstawowy', details=stale)], observed_at=AFTER, compared_at=BEFORE, data_quality='ok', evidence=evidence)
    store = SimpleNamespace(read=lambda: {'anchor': {old.key: old.to_dict()}, 'snapshots': {new.key: new.to_dict()}})
    enrich_visual_results([result], tmp_path, store)
    assert not result.changes[0].details['facts']
    assert result.changes[0].details['rotation']
    assert 'Rzekoma' not in result.changes[0].label


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


def test_change_in_an_interactive_variant_keeps_context_in_table_and_csv():
    view = journal_view()
    view["rows"][0]["events"][0]["variant"] = "Pakiet dokumentacji: Rozszerzony"
    from pracownie.journal import build_journal

    view["journal"] = build_journal(view["day"], view["rows"])
    assert "Pakiet dokumentacji: Rozszerzony" in BeautifulSoup(render_html(view), "html.parser").select_one('#journal').get_text()
    rows = list(csv.DictReader(io.StringIO(render_journal_csv(view).lstrip("\ufeff")), delimiter=";"))
    assert rows[0]["Kontekst / wariant"] == "Pakiet dokumentacji: Rozszerzony"


@pytest.mark.browser
async def test_cookie_state_class_on_body_does_not_hide_visual_metadata(executable):
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        page = await scanner.browser.new_page()
        await page.set_content('<body class="cookies-accepted"><h1>Oferta projektów</h1><div id="cookie-consent"><h2>Zgoda cookies</h2></div></body>')
        visual = await page.evaluate(VISUALS)
        assert any(e["text"] == "Oferta projektów" for e in visual["elements"])
        assert not any(e["text"] == "Zgoda cookies" for e in visual["elements"])
        await page.close()


@pytest.mark.browser
async def test_visual_metadata_includes_sales_button_appearance(executable):
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        page = await scanner.browser.new_page()
        await page.set_content('<a id="buy" class="btn" style="display:inline-block;background:#f00;font-size:20px;font-weight:700;border-radius:8px" href="/koszyk">Zamów projekt</a>')
        visual = await page.evaluate(VISUALS)
        button = next(e for e in visual['elements'] if e['key'] == '#buy')
        assert button['label'] == 'Zamów projekt'
        assert button['background'] == 'rgb(255, 0, 0)'
        assert button['font_size'] == '20px' and button['font_weight'] == '700'
        assert button['border_radius'] == '8px'
        await page.close()


@pytest.mark.browser
async def test_change_table_filters_and_native_proof_links(executable):
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        for scripts in (True, False):
            context = await scanner.browser.new_context(java_script_enabled=scripts, viewport={"width": 390, "height": 844})
            page = await context.new_page()
            await page.set_content(render_html(journal_view()))
            await page.locator('#full-journal > summary').click()
            if scripts:
                await page.locator('#journal-category').select_option('obraz')
                assert await page.locator('#journal tr[data-category="obraz"]').is_visible()
                assert not await page.locator('#journal tr[data-category="promocje"]').is_visible()
                await page.locator('#journal-category').select_option('extras')
                assert await page.locator('#journal-empty').is_visible()
                await page.locator('#journal-category').select_option('all')
                assert not await page.locator('#journal-empty').is_visible()
            await page.locator('#journal a[href^="#dowod-"]').last.click()
            assert await page.locator('#journal .journal-proof').get_attribute('open') is not None
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await context.close()
