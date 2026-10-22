"""Business conclusions must not be inferred from DOM slots or asset URLs."""

from copy import deepcopy

import pytest

from pracownie.communication import CONTRACT, category, clean, measure
from pracownie.model import Snapshot

BEFORE = "2026-10-21T06:00:00+00:00"
AFTER = "2026-10-22T06:00:00+00:00"


def snapshot(at, text, *, key="#main > p:nth-of-type(1)", role="text"):
    return Snapshot(
        "test.pl", "glowna", "podstawowy", "https://test.pl/", at, "Oferta", {}, [], "", "chromium",
        document={"communication": {
            "contract": CONTRACT, "observed_at": at, "adapter": "same-scope",
            "items": [{"key": key, "role": role, "text": text, "url": "https://test.pl/#main"}],
        }},
    )


def test_unrelated_paragraphs_at_the_same_dom_position_are_not_presented_as_an_edit():
    old = snapshot(BEFORE, "Klienci bardzo rzadko informują nas o miejscach realizacji swoich domów.")
    new = snapshot(AFTER, "Adaptacja gotowego projektu polega na prawidłowym umiejscowieniu budynku na działce.")
    before, after = deepcopy(old), deepcopy(new)
    status, changes = measure(old, new)
    assert status["comparable"]
    assert {change.kind for change in changes} == {"added", "removed"}
    assert not any(change.before and change.after for change in changes)
    assert all(change.details["unmatched"] and change.details["pairing"] == "inventory" for change in changes)
    assert changes[0].details["element_before"] == "#main > p:nth-of-type(1)"
    assert old == before and new == after


def test_rewritten_message_with_explicit_element_identity_remains_an_edit():
    old = snapshot(BEFORE, "Zbuduj dom swoich marzeń", key="#campaign-title", role="heading")
    new = snapshot(AFTER, "Projekty z pełnym wsparciem architekta", key="#campaign-title", role="heading")
    changes = measure(old, new)[1]
    assert len(changes) == 1 and changes[0].kind == "changed"
    assert changes[0].before == "Zbuduj dom swoich marzeń"
    assert changes[0].after == "Projekty z pełnym wsparciem architekta"
    assert changes[0].details["pairing"] == "identity" and not changes[0].details["unmatched"]


def test_same_offer_with_changed_terms_can_be_matched_at_a_positional_selector():
    changes = measure(
        snapshot(BEFORE, "Kosztorys gratis do każdego projektu przy zakupie do 31.10.2026"),
        snapshot(AFTER, "Kosztorys gratis do każdego projektu przy zakupie do 07.11.2026"),
    )[1]
    assert len(changes) == 1 and changes[0].kind == "changed"
    assert changes[0].category == "dodatki"
    assert changes[0].details["pairing"] == "similarity"


def test_cdn_hash_change_is_a_visual_review_not_a_new_function_or_sales_message():
    old_url = "https://extradom.wpcdn.pl/assets/cbe39bf/images/home/category-icon-ready-configurator.webp"
    new_url = old_url.replace("cbe39bf", "50d928a")
    old = snapshot(BEFORE, "Konfigurator domu gotowego · " + old_url, role="image")
    new = snapshot(AFTER, "Konfigurator domu gotowego · " + new_url, role="image")
    old.document["communication"]["items"][0]["asset"] = old_url
    new.document["communication"]["items"][0]["asset"] = new_url
    status, changes = measure(old, new)
    assert status["comparable"] and status["changes"] == 0 and status["asset_reviews"] == 1
    assert len(changes) == 1
    change = changes[0]
    assert change.kind == "review" and change.category == "obraz"
    assert change.details["communication_asset"] and change.details["specific"] is False
    assert change.details["asset_before"] == old_url and change.details["asset_after"] == new_url
    assert "Konfigurator domu gotowego" in change.before and "Konfigurator domu gotowego" in change.after


@pytest.mark.parametrize("unit", ["godz.", "min.", "sek."])
def test_isolated_ticking_timer_units_do_not_create_communication_changes(unit):
    status, changes = measure(
        snapshot(BEFORE, "38 " + unit), snapshot(AFTER, "15 " + unit),
    )
    assert not changes
    assert not status["comparable"]  # A timer alone is not a communication inventory.


@pytest.mark.parametrize("text", ["Wysyłka w 24 godz.", "Konsultacja potrwa 30 min.", "Promocja do 31.10.2026"])
def test_timer_filter_keeps_offer_deadlines_and_delivery_promises(text):
    assert clean(text) == text


def test_delivery_promise_change_remains_a_real_offer_change():
    changes = measure(snapshot(BEFORE, "Wysyłka w 24 godz."), snapshot(AFTER, "Wysyłka w 48 godz."))[1]
    assert len(changes) == 1 and changes[0].category == "warunki"
    assert changes[0].before == "Wysyłka w 24 godz." and changes[0].after == "Wysyłka w 48 godz."


@pytest.mark.parametrize("text", [
    "Dodatkowo salon znajduje się od strony ogrodu",
    "Klienci, którzy zakupili dokumentację, rzadko informują nas o miejscu realizacji domu",
])
def test_ordinary_copy_does_not_invent_a_new_extra_or_package(text):
    assert category("", text) == "komunikacja"


@pytest.mark.parametrize("text", ["Nowe dodatki do projektu", "Dodatek: projekt garażu", "Kosztorys gratis"])
def test_explicit_extra_remains_an_extra(text):
    assert category("", text) == "dodatki"


def test_explicit_package_remains_a_package():
    assert category("", "Pakiet dokumentacji dla inwestora") == "pakiety"


@pytest.mark.parametrize("text", ["1 dni14:24:5", "01 dni14h23min18s", "02 dni02 godz.03 min.11 sek."])
def test_full_timer_variants_are_not_offer_copy(text):
    assert clean(text) == ""


def test_compact_timer_masks_only_duration_retaining_promotion_and_deadline():
    old = snapshot(BEFORE, "Rabat 15% do 31.10.2026. 01 dni14h23min18s")
    new = snapshot(AFTER, "Rabat 15% do 31.10.2026. 00 dni14h22min17s")
    assert not measure(old, new)[1]
    new.document["communication"]["items"][0]["text"] = "Rabat 20% do 07.11.2026. 00 dni14h22min17s"
    changes = measure(old, new)[1]
    assert len(changes) == 1 and changes[0].category == "promocje"
    assert "31.10.2026" in changes[0].before and "07.11.2026" in changes[0].after


@pytest.mark.parametrize("old,new", [
    ("13191 odsłon projektu", "13251 odsłon projektu"),
    ("21 osób przegląda ten projekt", "14 osób przegląda ten projekt"),
])
def test_numeric_only_activity_changes_are_supporting_observations(old, new):
    status, changes = measure(snapshot(BEFORE, old), snapshot(AFTER, new))
    assert len(changes) == 1 and changes[0].details["supporting_reason"]
    assert status["changes"] == 0 and status["supporting_reviews"] == 1
    assert changes[0].before == old and changes[0].after == new


def test_real_text_change_in_activity_message_is_not_discarded_as_a_counter():
    old = snapshot(BEFORE, "21 osób przegląda ten projekt", key="#proof")
    new = snapshot(AFTER, "21 osób kupiło ten projekt", key="#proof")
    changes = measure(old, new)[1]
    assert len(changes) == 1 and not changes[0].details.get("supporting_reason")


def test_exact_stored_catalogue_link_is_supporting_but_contact_link_is_not():
    def with_link(at, text, href):
        shot = snapshot(at, text, key="main:nth-of-type(1) > a:nth-of-type(1)", role="cta")
        shot.document["payload"] = {"controls": [{
            "selector": "body > main:nth-of-type(1) > a:nth-of-type(1)", "href": href,
        }]}
        return shot
    old = with_link(BEFORE, "Projekt domu Amoniusz", "https://test.pl/projekt/amoniusz")
    new = with_link(AFTER, "Projekt domu Jantar", "https://test.pl/projekt/jantar")
    status, changes = measure(old, new)
    assert all(change.details.get("supporting_reason") for change in changes)
    assert status["changes"] == 0
    old = with_link(BEFORE, "Porozmawiaj z architektem", "https://test.pl/kontakt")
    new = with_link(AFTER, "Zapytaj architekta o rabat", "https://test.pl/kontakt")
    assert all(not change.details.get("supporting_reason") for change in measure(old, new)[1])


@pytest.mark.parametrize("key", [
    "#similar-projects > h3:nth-of-type(1)",
    "container:nth-of-type(1) > project-list:nth-of-type(2) > a:nth-of-type(1)",
])
def test_explicit_catalogue_container_is_supporting_without_guessing_from_title(key):
    status, changes = measure(snapshot(BEFORE, "Dom Alfa", key=key), snapshot(AFTER, "Dom Beta", key=key))
    assert changes and all(change.details.get("supporting_reason") for change in changes)
    assert status["changes"] == 0
