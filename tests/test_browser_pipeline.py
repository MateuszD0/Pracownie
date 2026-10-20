import json
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from pracownie.browser import BrowserScanner, infer_scenarios, project_candidates
from pracownie.images import image_difference
from pracownie.model import Scenario, Site
from pracownie.pipeline import RunOptions, run_scan
from pracownie.report import bundle_report, verify_outputs
from pracownie.state import StateStore


def site_config(fixture):
    return Site("test.pl", fixture.url, inspection="verified")


def options(executable, day):
    return RunOptions(day=day, browser_executable=executable, settle_ms=10, retries=0, ocr=False, max_scenarios=12, budget_seconds=120, domain_timeout=60)


@pytest.mark.browser
async def test_functional_baseline_change_same_day_and_failure(sample_site, executable, tmp_path, monkeypatch):
    site = site_config(sample_site)
    store = StateStore(tmp_path / "state")
    output = tmp_path / "raporty"
    monkeypatch.setattr("pracownie.browser.now_iso", lambda: "2026-10-18T06:00:00+00:00")
    first = await run_scan([site], store, output, options(executable, "2026-10-18"))
    assert not any(result.changes for result in first["results"])
    assert store.read()["selections"]["test.pl"]["url"].endswith("/projekt-domu-testowy")
    assert "bestseller" in store.read()["selections"]["test.pl"]["basis"].lower()
    assert len(store.read()["snapshots"]) >= 5
    assert any("nested-" in key for key in store.read()["snapshots"])
    sample_site.price = 4290
    sample_site.bonus = "Kosztorys gratis"
    sample_site.banner = "Promocja zimowa"
    monkeypatch.setattr("pracownie.browser.now_iso", lambda: "2026-10-19T06:00:00+00:00")
    second = await run_scan([site], store, output, options(executable, "2026-10-19"))
    price_changes = [change for result in second["results"] for change in result.changes if change.delta == "-300.00"]
    assert price_changes
    assert all(change.percent == "-6.54" for change in price_changes)
    assert all(Path(output / change.evidence["przed"]).is_file() for change in price_changes)
    assert all(Path(output / change.evidence["po"]).is_file() for change in price_changes)
    view = json.loads((output / "2026-10-19" / "oferty.json").read_text())
    pages = {p["page"]: p for p in view["rows"][0]["pages"]}
    assert set(pages) == {"glowna", "projekt"}
    assert all(p["daily"] and p["gap_days"] == 1 for p in pages.values())
    assert any("Promocja zimowa" in e["after"] for e in pages["glowna"]["events"])
    assert any(e["delta"] == "-300.00" for e in pages["projekt"]["events"])
    assert any("gratis" in e["after"] for e in pages["projekt"]["events"])
    for page in pages.values():
        assert all(Path(output / page["evidence"][key]).is_file() for key in ["przed", "po"])
    text = (output / "2026-10-19.txt").read_text()
    assert "Strona główna: Zmiany:" in text and "Karta projektu: Zmiany:" in text
    verify_outputs(output, "2026-10-19")
    bundle_report(output, "2026-10-19", tmp_path / "report.zip")
    repeated = await run_scan([site], store, output, options(executable, "2026-10-19"))
    assert any(change.delta == "-300.00" for result in repeated["results"] for change in result.changes)
    sample_site.unavailable = True
    failed = await run_scan([site], store, output, options(executable, "2026-10-20"))
    assert any(result.page == "projekt" and result.status == "error" for result in failed["results"])
    assert not any(change.kind == "removed" for result in failed["results"] for change in result.changes)
    latest = store.read()["snapshots"]["test.pl/projekt/podstawowy"]
    assert any(value["amount"] == "4290.00" for value in latest["fields"].values())
    assert not sample_site.submitted


@pytest.mark.browser
async def test_guard_against_order_submission(sample_site, executable, tmp_path):
    site = site_config(sample_site)
    async with BrowserScanner(executable, settle_ms=10) as scanner:
        with pytest.raises(ValueError, match="poza zakresem"):
            await scanner.capture(site, "glowna", sample_site.url + "/cart", Scenario("bad", "Bad", [{"action": "click", "selector": "#order"}]), tmp_path / "cart.png")
    assert not sample_site.submitted


@pytest.mark.browser
async def test_cookie_refusal_is_applied_and_excluded(sample_site, executable, tmp_path):
    sample_site.cookies = True
    async with BrowserScanner(executable, settle_ms=10) as scanner:
        capture = await scanner.capture(site_config(sample_site), "glowna", sample_site.url, Scenario("podstawowy", "Start"), tmp_path / "cookie.png")
    assert not any("cookies" in warning for warning in capture.snapshot.warnings)
    assert not any("Cookiebot" in c["selector"] for c in capture.controls)


@pytest.mark.browser
@pytest.mark.parametrize("settings_delay", [0, 650])
async def test_wp_cookie_settings_lead_to_refusal(sample_site, executable, tmp_path, settings_delay):
    sample_site.wp_cookies = True
    sample_site.wp_settings_delay = settings_delay
    async with BrowserScanner(executable, settle_ms=10) as scanner:
        captured = await scanner.capture(site_config(sample_site), "glowna", sample_site.url, Scenario("podstawowy", "Start"), tmp_path / "cookie.png")
    assert not any("cookies" in warning for warning in captured.snapshot.warnings), captured.snapshot.warnings
    assert not sample_site.submitted


@pytest.mark.browser
async def test_duplicate_dom_ids_have_unambiguous_selectors(sample_site, executable, tmp_path):
    sample_site.duplicate_cart = True
    site = site_config(sample_site)
    async with BrowserScanner(executable, settle_ms=10) as scanner:
        base = await scanner.capture(site, "projekt", sample_site.url + "/projekt-domu-testowy", Scenario("podstawowy", "Base"), tmp_path / "base.png")
        scenarios, _ = infer_scenarios(base.payload, "projekt")
        cart = [s for s in scenarios if any(a.get("cart") for a in s.actions)]
        assert len(cart) == 1  # Duplicate buttons must not repeat the same purchase flow.
        controls = [c for c in base.controls if c["kind"] == "cart"]
        assert len(controls) == 2 and len({c["selector"] for c in controls}) == 2
        for index, control in enumerate(controls):
            scenario = Scenario(f"cart-{index}", "Koszyk", [{"action": "click", "selector": control["selector"], "cart": True}])
            captured = await scanner.capture(site, "projekt", sample_site.url + "/projekt-domu-testowy", scenario, tmp_path / f"cart-{index}.png")
            assert captured.snapshot.url.endswith("/cart")


@pytest.mark.browser
async def test_visual_monitoring_without_recognized_sales_text(sample_site, executable, tmp_path):
    sample_site.no_sales = True
    site, store, output = site_config(sample_site), StateStore(tmp_path / "state"), tmp_path / "reports"
    await run_scan([site], store, output, options(executable, "2026-10-18"))
    assert store.read()["snapshots"]["test.pl/glowna/podstawowy"]["quality"] == "ok"
    sample_site.background = "#ccddff"
    outcome = await run_scan([site], store, output, options(executable, "2026-10-19"))
    changes = [change for result in outcome["results"] for change in result.changes]
    assert changes and all(change.kind == "visual" for change in changes)
    assert all(change.evidence.get("przed") and change.evidence.get("po") for change in changes)


@pytest.mark.browser
async def test_resume_uses_valid_same_day_reads_without_requests(sample_site, executable, tmp_path):
    site, store, output = site_config(sample_site), StateStore(tmp_path / "state"), tmp_path / "reports"
    settings = options(executable, "2026-10-19")
    # Exercise reuse of both pages and interactions within a small scan.
    settings.max_scenarios = 2
    first = await run_scan([site], store, output, settings)
    assert not [r.error for r in first["results"] if r.error]
    assert any(r.scenario != "podstawowy" and r.observed_at for r in first["results"])
    requests = sample_site.requests
    sample_site.unavailable = True
    settings.resume = True
    second = await run_scan([site], store, output, settings)
    assert second["metadata"]["reused_domains"] == ["test.pl"], [(r.page, r.scenario, r.error, r.warnings) for r in first["results"]]
    assert sample_site.requests == requests
    assert len(second["results"]) == len(first["results"])
    verify_outputs(output, "2026-10-19")


@pytest.mark.browser
async def test_explicit_correction_of_invalid_initial_choice_resets_only_project(sample_site, executable, tmp_path):
    site, store, output = site_config(sample_site), StateStore(tmp_path / "state"), tmp_path / "reports"
    await run_scan([site], store, output, options(executable, "2026-10-18"))
    state = store.read()
    state["selections"][site.domain].update(url=sample_site.url + "/category", name="Projekty domów", selected_at="2026-10-18T06:00:00+00:00")
    store.commit(state)
    corrected = replace(site, project_url=sample_site.url + "/projekt-domu-testowy", selection={"initial_choice_correction": {"from_url": sample_site.url + "/category", "selected_day": "2026-10-18", "reason": "Kategoria zamiast karty"}})
    sample_site.price = 4290
    sample_site.banner = "Promocja zimowa"
    outcome = await run_scan([corrected], store, output, options(executable, "2026-10-19"))
    assert outcome["metadata"]["selection_corrections"][0]["domain"] == site.domain
    assert store.read()["selections"][site.domain]["url"].endswith("/projekt-domu-testowy")
    assert all(not r.changes for r in outcome["results"] if r.page == "projekt")
    assert any(r.changes for r in outcome["results"] if r.page == "glowna")


def test_scenarios_have_stable_ids_when_option_price_changes():
    payload = {"controls": [{"kind": "select", "label": "Pakiet 4590 zł", "selector": "#pakiet", "name": "pakiet", "value": "base", "options": [{"value": "plus", "label": "Plus 4790 zł"}]}]}
    first, _ = infer_scenarios(payload, "projekt")
    payload["controls"][0]["label"] = "Pakiet 4290 zł"
    payload["controls"][0]["options"][0]["label"] = "Plus 4490 zł"
    second, _ = infer_scenarios(payload, "projekt")
    assert first[0].id == second[0].id


def test_project_permission_addon_is_separate_from_privacy_and_checkout_controls():
    controls = [
        {"kind": "checkbox", "label": "Zgoda na zmiany w projekcie 100 zł", "selector": "#addon", "name": "permission"},
        {"kind": "checkbox", "label": "Wyrażam sprzeciw wobec przetwarzania danych osobowych", "selector": "#privacy", "name": "objection"},
        {"kind": "checkbox", "label": "Zgoda na newsletter", "selector": "#newsletter", "name": "newsletter"},
        {"kind": "select", "label": "Kraj", "selector": "#country", "name": "billing_country", "options": [{"value": "PL", "label": "Polska"}]},
    ]
    scenarios, _ = infer_scenarios({"controls": controls}, "projekt")
    assert [a["selector"] for s in scenarios for a in s.actions] == ["#addon"]


def test_project_ranking_is_deterministic():
    site = Site("test.pl", "https://test.pl")
    payload = {"links": [
        {"url": "https://test.pl/projekt-domu-a", "text": "Dom A", "context": "Polecany", "image": True},
        {"url": "https://test.pl/projekt-domu-b", "text": "Dom B", "context": "Bestseller", "image": True},
        {"url": "https://outside.pl/projekt-domu-c", "text": "Dom C", "context": "Bestseller", "image": True},
    ]}
    candidates = project_candidates(site, payload)
    assert candidates[0][1]["url"].endswith("-b")
    assert len(candidates) == 2
    catalog = project_candidates(site, {"url": "https://test.pl/katalog", "links": [payload["links"][0]]})
    assert catalog[0][1]["source"] == "https://test.pl/katalog"
    assert "katalogu" in catalog[0][1]["basis"]


def test_visual_difference_and_no_difference(tmp_path):
    first, second = tmp_path / "before.png", tmp_path / "after.png"
    Image.new("RGB", (400, 300), "white").save(first)
    Image.new("RGB", (400, 300), "white").save(second)
    assert not image_difference(first, second, tmp_path / "diff.png").changed
    Image.new("RGB", (400, 300), "blue").save(second)
    assert image_difference(first, second, tmp_path / "diff.png").changed
    assert (tmp_path / "diff.png").is_file()


def test_small_banner_change_on_long_page(tmp_path):
    from PIL import ImageDraw
    first, second = tmp_path / "before.png", tmp_path / "after.png"
    image = Image.new("RGB", (800, 12000), "white")
    image.save(first)
    ImageDraw.Draw(image).rectangle((100, 100, 120, 115), fill="black")
    image.save(second)
    result = image_difference(first, second, tmp_path / "diff.png")
    assert result.ratio < 0.001
    assert result.changed


def test_registry_and_workflow_contract():
    import yaml

    from pracownie.model import load_sites
    root = Path(__file__).parents[1]
    sites = load_sites(root / "config/sites.json")
    assert len(sites) == 65
    workflow = yaml.safe_load((root / ".github/workflows/monitor.yml").read_text())
    # PyYAML's YAML 1.1 recognizes the key 'on' as boolean true.
    events = workflow.get("on", workflow.get(True))
    assert events["schedule"][0] == {"cron": "17 6 * * *", "timezone": "Europe/Warsaw"}
    assert workflow["permissions"] == {"contents": "write", "pages": "read"}
    assert workflow["jobs"]["pages"]["permissions"] == {"contents": "read", "pages": "write", "id-token": "write"}
    assert not workflow["jobs"]["scan"]["concurrency"]["cancel-in-progress"]
    assert json.loads((root / "config/sites.json").read_text())["schema"] == 1
