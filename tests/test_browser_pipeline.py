import json
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
async def test_functional_baseline_change_same_day_and_failure(sample_site, executable, tmp_path):
    site = site_config(sample_site)
    store = StateStore(tmp_path / "state")
    output = tmp_path / "raporty"
    first = await run_scan([site], store, output, options(executable, "2026-10-18"))
    assert not any(result.changes for result in first["results"])
    assert store.read()["selections"]["test.pl"]["url"].endswith("/projekt-domu-testowy")
    assert "bestseller" in store.read()["selections"]["test.pl"]["basis"].lower()
    assert len(store.read()["snapshots"]) >= 5
    assert any("nested-" in key for key in store.read()["snapshots"])
    sample_site.price = 4290
    sample_site.bonus = "Kosztorys gratis"
    second = await run_scan([site], store, output, options(executable, "2026-10-19"))
    price_changes = [change for result in second["results"] for change in result.changes if change.delta == "-300.00"]
    assert price_changes
    assert all(change.percent == "-6.54" for change in price_changes)
    assert all(Path(output / change.evidence["przed"]).is_file() for change in price_changes)
    assert all(Path(output / change.evidence["po"]).is_file() for change in price_changes)
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


def test_scenarios_have_stable_ids_when_option_price_changes():
    payload = {"controls": [{"kind": "select", "label": "Pakiet 4590 zł", "selector": "#pakiet", "name": "pakiet", "value": "base", "options": [{"value": "plus", "label": "Plus 4790 zł"}]}]}
    first, _ = infer_scenarios(payload, "projekt")
    payload["controls"][0]["label"] = "Pakiet 4290 zł"
    payload["controls"][0]["options"][0]["label"] = "Plus 4490 zł"
    second, _ = infer_scenarios(payload, "projekt")
    assert first[0].id == second[0].id


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
    assert workflow["permissions"] == {"contents": "write"}
    assert not workflow["concurrency"]["cancel-in-progress"]
    assert json.loads((root / "config/sites.json").read_text())["schema"] == 1
