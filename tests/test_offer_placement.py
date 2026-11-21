from copy import deepcopy

import pytest
from PIL import Image
from playwright.async_api import async_playwright

from pracownie.browser import COMMUNICATION
from pracownie.communication import mark_unstable, measure
from pracownie.model import Result, Snapshot
from pracownie.presentation import build_view
from pracownie.prominence import attach_placement_crops, placement_coverage

OLD = "2026-11-20T08:00:00+00:00"
NEW = "2026-11-21T08:00:00+00:00"
OFFER = "Rabat 500 zł z kodem BLACK500"


def sample(zone, rect, *, role="heading", text=OFFER):
    entry = {"text": text, "key": "#offer", "zone": zone, "rect": rect}
    return {
        "contract": "communication-v1",
        "items": [{"key": "#offer", "role": role, "text": text, "url": "https://test.pl/#offer"}],
        "placement_sample": {"viewport": [1280, 900, 1], "items": [entry], "truncated": False},
    }


def shot(at, first, second=None):
    doc = mark_unstable(deepcopy(first), deepcopy(second if second is not None else first), 350)
    doc.update(observed_at=at, adapter="scope")
    return Snapshot(
        "test.pl",
        "glowna",
        "podstawowy",
        "https://test.pl/",
        at,
        "Oferta",
        {},
        [],
        "",
        "chromium",
        document={"communication": doc},
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_stable_offer_move_reaches_the_journal_with_a_dated_crop_pair(tmp_path, reverse):
    low = sample("lower", [40, 1200, 240, 30])
    first = sample("first", [120, 50, 240, 30], role="text")
    a, b = (first, low) if reverse else (low, first)
    old, new = shot(OLD, a), shot(NEW, b)
    status, changes = measure(old, new)
    assert status["changes"] == 1
    (c,) = changes
    assert c.label == "Zmiana ekspozycji promocji" and c.kind == "changed"
    expected = ("first", "lower") if reverse else ("lower", "first")
    data = c.details["offer_placement"]
    assert (data["before"], data["after"]) == expected
    assert data["text"] == OFFER and c.url.endswith("#offer")
    folder = tmp_path / "2026-11-21"
    folder.mkdir()
    for side, rect in [("przed", data["before_rect"]), ("po", data["after_rect"])]:
        image = Image.new("RGB", (1280, 1800), "white")
        x, y, w, h = rect
        image.paste("red", (x, y, x + w, y + h))
        image.save(folder / (side + ".png"))
    c.evidence = {"przed": "2026-11-21/przed.png", "po": "2026-11-21/po.png"}
    attach_placement_crops(c, tmp_path)
    for key in ("fragment_przed", "fragment_po"):
        with Image.open(tmp_path / c.evidence[key]) as image:
            assert image.width < 1280 and image.getpixel((image.width // 2, image.height // 2)) == (255, 0, 0)
    r = Result(
        "test.pl",
        "glowna",
        "podstawowy",
        "changed",
        new.url,
        changes,
        observed_at=NEW,
        compared_at=OLD,
        communication=status,
        data_quality="ok",
    )
    view = build_view("2026-11-21", [r], {"finished_at": NEW}, {}, ["test.pl"])
    (item,) = view["journal"]
    assert item["offer_placement"] == data and item["daily"]
    assert item["evidence"]["fragment_przed"] != item["evidence"]["fragment_po"]


@pytest.mark.parametrize(
    "condition",
    [
        "no_position",
        "carousel",
        "partial",
        "layout_shift",
        "duplicate",
        "responsive",
        "gap",
        "truncated",
        "changed_offer",
        "broken_images",
        "other_url",
        "context_scope",
    ],
)
def test_noncomparable_positions_never_establish_a_placement_change(condition):
    low = sample("lower", [20, 1500, 240, 40])
    high = sample("first", [20, 50, 240, 40])
    repeated = deepcopy(high)
    if condition == "no_position":
        low.pop("placement_sample")
    elif condition == "carousel":
        low["placement_sample"]["items"][0]["zone"] = "unknown"
    elif condition == "layout_shift":
        repeated["placement_sample"]["items"][0]["rect"][1] += 100
    elif condition == "duplicate":
        repeated["placement_sample"]["items"].append(
            dict(repeated["placement_sample"]["items"][0], key="#copy")
        )
    elif condition == "responsive":
        low["placement_sample"]["viewport"][0] = 390
    elif condition == "truncated":
        low["placement_sample"]["truncated"] = True
    elif condition == "changed_offer":
        high = repeated = sample("first", [20, 50, 240, 40], text="Rabat 700 zł z kodem BLACK700")
    old = shot("2026-11-19T08:00:00+00:00" if condition == "gap" else OLD, low)
    new = shot(NEW, high, repeated)
    if condition == "partial":
        new.quality = "partial"
    if condition == "broken_images":
        new.warnings.append("Wykryto niezaładowane obrazy; porównanie wizualne może być niepełne.")
    if condition == "context_scope":
        new.document["communication"]["context_selectors"] = {"editorial": ["#blog"]}
    if condition == "other_url":
        new.url = "https://test.pl/inny"
    changes = measure(old, new)[1]
    assert not any(c.details.get("offer_placement") for c in changes)
    if condition == "changed_offer":
        assert changes and any("BLACK700" in str(c.after) for c in changes)


@pytest.mark.browser
async def test_actual_browser_captures_a_stable_visible_offer_but_excludes_rotating_slides_and_overlays(
    executable,
    tmp_path,
):
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=executable)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.set_content("""<main><h2 id="offer" style="margin:1200px 0 0">Rabat 500 zł z kodem BLACK500</h2>
          <div class="swiper"><p class="swiper-slide">Gratis kosztorys</p></div></main>""")

        options = {"page": "glowna"}

        old = shot(
            OLD, await page.evaluate(COMMUNICATION, options), await page.evaluate(COMMUNICATION, options)
        )
        await page.screenshot(path=tmp_path / "before.png", full_page=True)
        await page.locator("#offer").evaluate("e=>e.style.marginTop='30px'")
        high = await page.evaluate(COMMUNICATION, options)
        new = shot(NEW, high, await page.evaluate(COMMUNICATION, options))
        (change,) = measure(old, new)[1]
        assert change.details["offer_placement"]["text"] == OFFER
        await page.screenshot(path=tmp_path / "after.png", full_page=True)
        change.evidence = {"przed": "before.png", "po": "after.png"}
        attach_placement_crops(change, tmp_path)
        for key in ("fragment_przed", "fragment_po"):
            with Image.open(tmp_path / change.evidence[key]) as crop:
                assert crop.height < 150 and crop.convert("L").getextrema()[0] < 20
        await page.evaluate(
            """()=>{const d=document.createElement('div');d.style='position:fixed;inset:0;background:white;z-index:10';document.body.append(d)}"""
        )
        blocked = shot(
            NEW, await page.evaluate(COMMUNICATION, options), await page.evaluate(COMMUNICATION, options)
        )
        assert not measure(old, blocked)[1]
        await browser.close()


def test_coverage_distinguishes_legacy_baseline_empty_inventory_and_matched_offers():
    low = sample("lower", [20, 1500, 240, 40])
    old = shot(OLD, low)
    current = shot(NEW, low)
    generic = sample("lower", [20, 1500, 240, 40], text="Zobacz wybrany projekt")

    def page(before, after):
        status, _ = measure(before, after)
        return {"current_read": True, "communication": {**status, "daily": before is not None}}

    baseline = page(None, current)
    shared = page(old, current)
    no_offers = page(shot(OLD, generic), shot(NEW, generic))
    legacy = deepcopy(current)
    legacy.document["communication"].pop("placement")
    assert placement_coverage(
        {
            "rows": [
                {"pages": [baseline, shared]},
                {"pages": [no_offers, page(old, legacy)]},
                {"pages": [dict(shared, current_read=False)]},
            ]
        }
    ) == {"expected": 6, "measured": 3, "compared": 2, "matched": 1}
