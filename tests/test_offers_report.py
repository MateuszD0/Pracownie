import json
from dataclasses import replace

import pytest

from pracownie.browser import EXTRACT, BrowserScanner, infer_scenarios
from pracownie.compare import compare
from pracownie.extract import extract_fields
from pracownie.model import Change, Field, Result, Snapshot
from pracownie.offers import price_delta, primary_offer
from pracownie.presentation import build_view, money, render_csv, render_html, render_text

AT = "2026-10-20T06:00:00+00:00"


def snap(fields):
    return Snapshot("test.pl", "projekt", "podstawowy", "https://test.pl/dom", AT,
                    "Projekt domu Dom A", fields, ["oferta"], "", "chromium|extractor=v2")


@pytest.mark.parametrize("text,expected", [("zł 499.00", "499.00"), ("1.950,00 zł", "1950.00"), ("3800, 00 PLN", "3800.00")])
def test_public_price_formats(text, expected):
    fields, _ = extract_fields({"prices": [{"text": text, "primary": True}]}, AT)
    assert {f.amount for f in fields.values()} == {expected}
    assert primary_offer(snap(fields))["amount"] == expected


def test_primary_project_price_is_not_the_cheapest_addon():
    fields, _ = extract_fields({"prices": [{"text": "30 zł"}, {"text": "5000 zł + VAT", "primary": True}], "page": "projekt"}, AT)
    fields["adapter:cena"] = Field("Cena projektu netto", "5000 zł + VAT", "ceny", amount="5000.00", currency="PLN", source="adapter", role="current", primary=True, tax="net")
    offer = primary_offer(snap(fields))
    assert offer["amount"] == "5000.00"
    assert money(offer) == "5 000,00 zł netto + VAT"
    assert price_delta(offer, {**offer, "tax": "gross", "amount": "6150.00"}) == (None, None)


def test_explicit_gross_price_takes_precedence_over_net_and_addons():
    fields = {
        "oferta:dom:price": Field("Dom A — cena", "1178.86 PLN", "ceny", amount="1178.86", currency="PLN", source="jsonld", role="current"),
        "adapter:cena": Field("Cena projektu brutto", "1450 zł", "ceny", amount="1450.00", currency="PLN", source="adapter", role="current", primary=True, tax="gross"),
    }
    offer = primary_offer(snap(fields))
    assert offer["amount"] == "1450.00"
    assert money(offer) == "1 450,00 zł brutto"
    only_schema = snap({"oferta:dom:price": fields["oferta:dom:price"]})
    assert primary_offer(only_schema, ["oferta:dom:price"]) == {}


def test_aggregate_price_is_range_and_not_a_single_discount():
    fields, _ = extract_fields({"page": "projekt", "products": [{"name": "Dom A", "offers": {"lowPrice": 12500, "highPrice": 13750, "priceCurrency": "PLN"}}]}, AT)
    offer = primary_offer(snap(fields))
    assert offer["kind"] == "range"
    assert money(offer) == "12 500,00–13 750,00 zł"
    assert price_delta(offer, offer) == (None, None)


def test_partial_exact_price_is_provisional_and_never_a_confirmed_delta():
    fields = {"adapter:cena": Field("Cena projektu", "1450 zł", "ceny", amount="1450.00", currency="PLN", source="adapter", role="current", primary=True)}
    provisional = primary_offer(replace(snap(fields), quality="partial"))
    assert provisional["amount"] == "1450.00"
    assert money(provisional) == "1 450,00 zł *"
    assert price_delta({**provisional, "amount": "1600.00", "quality": "ok"}, provisional) == (None, None)


def test_structured_price_with_stable_identity_survives_browser_handler_update():
    old, _ = extract_fields({"products": [{"name": "Dom A", "offers": {"price": 4590, "priceCurrency": "PLN"}}]}, AT)
    new, _ = extract_fields({"products": [{"name": "Dom A", "offers": {"price": 4290, "priceCurrency": "PLN"}}]}, AT)
    before, after = snap(old), replace(snap(new), renderer="chromium|extractor=v3")
    changes, _ = compare(before, after)
    assert changes[0].kind == "changed" and changes[0].delta == "-300.00"


def view():
    fields, _ = extract_fields({"products": [{"name": "Dom A", "offers": {"price": 4290, "priceCurrency": "PLN"}}]}, AT)
    offer = primary_offer(snap(fields))
    previous = {**offer, "amount": "4590.00", "low": "4590.00", "high": "4590.00"}
    duplicate = Change("changed", "ceny", "Cena", "4590 PLN", "4290 PLN", AT, AT, "https://test.pl/dom", "podstawowy", delta="-300.00")
    migration = Change("review", "funkcje", "Kontrolki", None, "Nowe reguły", AT, AT, "https://test.pl/dom", "podstawowy", note="Zmieniono reguły odczytu")
    results = [Result("test.pl", "glowna", "podstawowy", "unchanged", "https://test.pl", observed_at=AT),
               Result("test.pl", "projekt", "podstawowy", "changed", "https://test.pl/dom", [duplicate, migration], observed_at=AT, offer=offer, before_offer=previous),
               Result("test.pl", "projekt", "opcja", "unavailable", "https://test.pl/dom", error="Timeout: INTERNAL TRACE")]
    return build_view("2026-10-20", results, {"finished_at": AT}, {"test.pl": {"name": "Dom A", "url": "https://test.pl/dom"}}, ["test.pl"])


def test_report_deduplicates_prices_and_separates_browser_diagnostics():
    report = view()
    assert report["counts"]["events"] == 1
    assert not report["rows"][0]["reviews"]
    assert report["rows"][0]["migration"]
    text = render_text(report)
    assert "4 590,00 zł → 4 290,00 zł" in text
    assert "INTERNAL TRACE" not in text
    assert "Dzień;Domena;Projekt" in render_csv(report)


def test_report_can_be_reformatted_without_invalidating_its_manifest(tmp_path):
    from pracownie.report import verify_outputs, write_outputs
    metadata = {"run_id": "same-read", "started_at": AT, "finished_at": AT, "elapsed_seconds": 0}
    for _ in range(2):
        write_outputs(tmp_path, "2026-10-20", [], metadata, {}, [])
        verify_outputs(tmp_path, "2026-10-20")


def test_selective_repair_preserves_other_domains_errors(tmp_path):
    from pracownie.model import Site
    from pracownie.report import resume_data, write_outputs
    sites = [Site(d, "https://" + d) for d in ["a.pl", "b.pl"]]
    metadata = {"run_id": "prior-read", "started_at": AT, "finished_at": AT, "elapsed_seconds": 0}
    rows = [Result(s.domain, "glowna", "podstawowy", "error", s.home_url, error="HTTP 403") for s in sites]
    write_outputs(tmp_path, "2026-10-20", rows, metadata, {}, [s.domain for s in sites])
    reused, results, _ = resume_data(tmp_path, "2026-10-20", sites, {"day": "2026-10-20"}, ["b.pl"])
    assert reused == {"a.pl"}
    assert len(results) == 1 and results[0].error == "HTTP 403"
    assert results[0].observed_at is None


@pytest.mark.browser
async def test_visible_woo_price_hidden_radio_and_related_products(executable):
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        page = await scanner.browser.new_page()
        await page.set_content('''<h1>Projekt domu Dom A</h1><div class="summary"><p class="price"><del><bdi>946 <span>zł</span></bdi></del> <ins><bdi>499 <span>zł</span></bdi></ins></p></div>
          <input id="extra" name="extra" type="checkbox" style="display:none"><label for="extra">Kosztorys 100 zł</label>
          <div class="related"><h2>Polecane projekty</h2><p class="price">2500 zł</p></div>
          <div style="position:absolute;left:-9999px"><button>Dodaj do koszyka</button></div>''')
        payload = await page.evaluate(EXTRACT, "projekt")
        fields, _ = extract_fields(payload, AT)
        assert primary_offer(snap(fields))["amount"] == "499.00"
        assert not any(f.amount == "2500.00" for f in fields.values())
        controls = payload["controls"]
        assert [c["name"] for c in controls] == ["extra"]
        scenarios, _ = infer_scenarios(payload, "projekt")
        await scanner.operate(page, scenarios[0].actions[0])
        assert await page.locator("#extra").is_checked()


@pytest.mark.browser
async def test_necessary_only_shoper_consent_and_sticky_header(executable):
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        page = await scanner.browser.new_page(viewport={"width": 1280, "height": 900})
        await page.set_content('''<div role="dialog">Dbamy o Twoją prywatność. Pliki cookies.
          <button onclick="window.submitted=true">Zaakceptuj wszystkie</button>
          <button onclick="this.parentNode.remove()">Zaakceptuj tylko niezbędne</button></div>''')
        await scanner.cookies(page)
        assert not await page.locator('div[role=dialog]').count()
        assert not await page.evaluate("Boolean(window.submitted)")
        await page.set_content('''<style>body{margin:0;height:3000px}header{position:fixed;top:0;height:200px;width:100%;background:white;z-index:9}button{margin-top:1200px}</style><header>Stały nagłówek</header><button id="tab" onclick="window.clicked=true">Warunki</button>''')
        await page.evaluate("scrollTo(0,1180)")
        await scanner.operate(page, {"action": "click", "selector": "#tab"})
        assert await page.evaluate("window.clicked")


@pytest.mark.browser
async def test_html_search_filter_dialog_and_embedded_content(executable, tmp_path):
    report = view()
    report["rows"][0]["name"] = 'Dom </script><img src=x onerror="window.injected=true">'
    target = tmp_path / "index.html"
    target.write_text(render_html(report))
    async with BrowserScanner(executable, settle_ms=0) as scanner:
        page = await scanner.browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.set_content(target.read_text())
        await page.locator('[data-filter="price"]').click()
        assert await page.locator("#rows tr").count() == 1
        await page.locator("#search").fill("nieistnieje")
        assert "Brak domen" in await page.locator("#rows").inner_text()
        await page.locator("#search").fill("test.pl")
        await page.locator('#rows [data-open="test.pl"]').click()
        assert await page.locator("dialog").is_visible()
        assert not await page.evaluate("Boolean(window.injected)")
        assert not errors
        assert json.loads(await page.locator('#data').text_content())["day"] == report["day"]
