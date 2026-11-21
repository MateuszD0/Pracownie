from copy import deepcopy

import pytest

from pracownie.campaign_card import build_campaign_cards, daily_price_fact
from pracownie.communication import CONTRACT
from pracownie.model import Snapshot

DAY = "2026-11-21"
BEFORE = "2026-11-20T06:00:00+00:00"
AFTER = "2026-11-21T06:00:00+00:00"
PROJECT = "https://test.pl/projekt/jantar-vii"


def capture(page, text, at=AFTER, url=None):
    return Snapshot("test.pl", page, "podstawowy", url or (PROJECT if page == "projekt" else "https://test.pl/"),
                    at, "Projekt domu Jantar VII", {}, [], "", "chromium", document={"communication": {
                        "contract": CONTRACT, "observed_at": at, "adapter": "same",
                        "items": [{"role": "banner", "text": text, "key": "#campaign"}],
                    }}).to_dict()


def inputs(home="Rabat 500 zł z kodem BLACK500", project="Projekt domu Jantar VII"):
    state = {"snapshots": {"test.pl/glowna/podstawowy": capture("glowna", home),
                           "test.pl/projekt/podstawowy": capture("projekt", project)},
             "anchor": {"test.pl/projekt/podstawowy": capture("projekt", project, BEFORE)}}
    quote = {"kind": "price", "quality": "ok", "amount": "5000.00", "currency": "PLN", "tax": "gross",
             "unit": "", "field_key": "price", "observed_at": BEFORE}
    row = {"domain": "test.pl", "name": "Projekt domu Jantar VII", "url": PROJECT, "project_selected": True,
           "previous": quote, "current": {**quote, "amount": "4500.00", "observed_at": AFTER}}
    return state, {"day": DAY, "rows": [row], "comparison": {"price_domains": ["test.pl"]}}


def term(quote, *, code="BLACK500", at=AFTER, source="https://test.pl/regulamin", **fields):
    return {"domain": "test.pl", "page": "terms", "source": source, "code": code,
            "status": "observed", "before": None,
            "after": {"quote": quote, "source": source, "observed_at": at, "value": "500 zł", "scope": "",
                      "minimum": "", "stacking": "", "expiry": "", "effective_price": "", **fields}}


def test_home_campaign_does_not_establish_fixed_project_eligibility_or_price_cause():
    state, view = inputs()
    original = deepcopy((state, view))
    card = build_campaign_cards(state, view)[0]
    assert card["scope"]["status"] == "unconfirmed"
    assert card["price"]["status"] == "changed" and card["price"]["delta"] == "-500.00"
    assert card["price"]["before_text"] == "5 000,00 zł brutto"
    assert card["price"]["after_text"] == "4 500,00 zł brutto"
    assert "-500,00 zł / -10,00%" == card["price"]["delta_text"]
    assert "nie dowodzi" in card["price"]["note"]
    assert not card["effective_price"]
    assert (state, view) == original


def test_same_code_in_project_header_is_only_evidence_of_publication():
    state, view = inputs(project="Rabat 500 zł z kodem BLACK500")
    card = build_campaign_cards(state, view)[0]
    assert card["scope"]["status"] == "mentioned_on_card"
    assert card["project"][0]["source"] == PROJECT
    assert "zakres niepotwierdzony" in card["scope"]["text"]


def test_terms_match_literal_code_and_preserve_unknown_conditions():
    state, view = inputs()
    terms = [term("Kod BLACK500: rabat 500 zł tylko na wybrane projekty", scope="wybrane projekty"),
             term("Kod INNY500 obejmuje wszystkie projekty", code="INNY500"),
             term("Kod BLACK500 obejmuje wszystkie projekty", at=BEFORE),
             term("Kod BLACK500 obejmuje wszystkie projekty", source="https://obcy.pl/regulamin")]
    card = build_campaign_cards(state, view, terms)[0]
    assert len(card["terms"]) == 1 and card["terms"][0]["scope"] == "wybrane projekty"
    assert card["scope"]["status"] == "unconfirmed" and not card["effective_price"]


def test_universal_scope_with_minimum_is_not_blanket_eligibility():
    state, view = inputs()
    card = build_campaign_cards(state, view, [term("Kod BLACK500 obejmuje wszystkie projekty przy zakupie od 6000 zł", minimum="6000 zł")])[0]
    assert card["scope"]["status"] == "conditional"
    assert not card["effective_price"]


def test_explicit_selected_project_and_effective_price_are_cited_not_computed():
    state, view = inputs()
    quote = "Kod BLACK500 obejmuje projekt Jantar VII. Cena po kodzie: 4400 zł."
    card = build_campaign_cards(state, view, [term(quote, effective_price="4400 zł")])[0]
    assert card["scope"]["status"] == "explicitly_included"
    assert card["effective_price"] == [{"value": "4400 zł", "quote": quote, "source": "https://test.pl/regulamin", "observed_at": AFTER}]
    assert card["price"]["after"]["amount"] == "4500.00"


@pytest.mark.parametrize("wording", ["nie dotyczy projektu", "nie obowiązuje na projekt", "obejmuje wszystkie projekty z wyjątkiem projektu"])
def test_explicit_exclusion_wins_over_general_campaign(wording):
    state, view = inputs()
    card = build_campaign_cards(state, view, [term("Kod BLACK500 " + wording + " Jantar VII.")])[0]
    assert card["scope"]["status"] == "explicitly_excluded" and not card["effective_price"]


def test_other_project_variant_is_not_an_explicit_match():
    state, view = inputs()
    view["rows"][0]["name"] = "Projekt domu Jantar"
    card = build_campaign_cards(state, view, [term("Kod BLACK500 obejmuje projekt Jantar VII. Cena po kodzie: 4400 zł.", effective_price="4400 zł")])[0]
    assert card["scope"]["status"] == "unconfirmed" and not card["effective_price"]


@pytest.mark.parametrize("change", ["old_day", "tax", "field", "not_paired", "wrong_project"])
def test_price_delta_requires_consecutive_dates_quote_scope_and_fixed_project(change):
    state, view = inputs()
    row = view["rows"][0]
    if change == "old_day":
        row["previous"]["observed_at"] = "2026-11-19T06:00:00+00:00"
    elif change == "tax":
        row["previous"]["tax"] = "net"
    elif change == "field":
        row["current"]["field_key"] = "another-price"
    elif change == "not_paired":
        view["comparison"]["price_domains"] = []
    else:
        state["snapshots"]["test.pl/projekt/podstawowy"]["url"] = "https://test.pl/projekt/inny"
    price = daily_price_fact(state, view, row)
    assert price["status"] in {"missing", "unpaired"} and price["delta"] is None
    if change == "wrong_project":
        assert price["after"] is None


def test_stale_homepage_is_not_published_as_todays_campaign():
    state, view = inputs()
    state["snapshots"]["test.pl/glowna/podstawowy"]["observed_at"] = BEFORE
    assert not build_campaign_cards(state, view)


def test_missing_project_does_not_imply_campaign_exclusion():
    state, view = inputs()
    del state["snapshots"]["test.pl/projekt/podstawowy"]
    card = build_campaign_cards(state, view)[0]
    assert card["scope"]["status"] == "missing_project"
    assert card["price"]["status"] == "missing"


def test_identical_benefit_with_different_code_is_not_matched():
    state, view = inputs(project="Rabat 500 zł z kodem WIOSNA500")
    card = build_campaign_cards(state, view, [term("Rabat 500 zł z kodem WIOSNA500", code="WIOSNA500")])[0]
    assert not card["terms"] and not card["project"]
    assert card["scope"]["status"] == "unconfirmed"


@pytest.mark.parametrize("date_phrase,status", [
    ("Promocja do 20.11.2026.", "expired"),
    ("Promocja od 25.11.2026.", "scheduled"),
])
def test_named_project_in_expired_or_future_terms_does_not_establish_current_price(date_phrase, status):
    state, view = inputs()
    quote = "Kod BLACK500 obejmuje projekt Jantar VII. " + date_phrase + " Cena po kodzie: 4400 zł."
    card = build_campaign_cards(state, view, [term(quote, effective_price="4400 zł")])[0]
    assert card["scope"]["status"] == status and not card["effective_price"]


def test_conflicting_named_scope_is_exposed_and_never_used_to_claim_effective_price():
    state, view = inputs()
    terms = [term("Kod BLACK500 obejmuje projekt Jantar VII. Cena po kodzie: 4400 zł.", effective_price="4400 zł"),
             term("Kod BLACK500 nie dotyczy projektu Jantar VII.")]
    card = build_campaign_cards(state, view, terms)[0]
    assert card["scope"]["status"] == "conflicting" and not card["effective_price"]


@pytest.mark.parametrize("text", [
    "Sprytny projekt: Dom w cenie mieszkania", "W cenie projektu", "Gratis", "Pobierz bezpłatny katalog",
    "Maksymalna ilość produktów w porównywarce Maksymalna ilość produktów w ulubionychRabat 650 zł",
    "Nowość Tylko u Autora Promocja domidea 1 w6 127.65 m2 4 3 0 6150,00 zł 5150,00 zł",
])
def test_labels_editorial_wordplay_and_catalogue_prices_are_not_campaigns(text):
    state, view = inputs(home=text)
    assert not build_campaign_cards(state, view)


def test_literal_code_headline_without_the_word_promotion_is_recovered_from_source():
    state, view = inputs(home="Wszystkie projekty domów taniej nawet o 1100 zł z kodem BLACK500 🔥",
                         project="Kup ten projekt jeszcze taniej o 500 zł z kodem „BLACK500” 🔥")
    card = build_campaign_cards(state, view)[0]
    assert card["home"][0]["codes"] == ["BLACK500"]
    assert card["scope"]["status"] == "explicitly_included"
    assert not card["effective_price"]
    assert card["project"][0]["source"] == PROJECT


def test_home_capture_does_not_relabel_a_project_link_as_homepage_evidence():
    state, view = inputs()
    state["snapshots"]["test.pl/glowna/podstawowy"]["document"]["communication"]["items"][0]["url"] = PROJECT
    assert not build_campaign_cards(state, view)


def test_unselected_project_has_no_project_link_or_project_eligibility():
    state, view = inputs()
    view["rows"][0].update(project_selected=False, url="https://test.pl/")
    card = build_campaign_cards(state, view)[0]
    assert card["project_url"] == "" and card["project_name"] == "Brak stałego projektu"
    assert card["scope"]["status"] == "missing_project" and card["price"]["status"] == "missing"


def test_countdown_suffix_does_not_duplicate_one_homepage_campaign():
    state, view = inputs(home="PROMOCJA -250 zł")
    shot = state["snapshots"]["test.pl/glowna/podstawowy"]
    shot["document"]["communication"]["items"].append({"role": "banner", "text": "PROMOCJA -250 zł DO KOŃCA PROMOCJI POZOSTAŁO: 01 dni14h23min18s", "key": "#another"})
    cards = build_campaign_cards(state, view)
    assert len(cards) == 1 and len(cards[0]["home"]) == 2


def test_source_backed_article_carousel_is_not_a_current_campaign_card():
    state, view = inputs(home="Projekt kwietnia w promocji 20%")
    shot = state["snapshots"]["test.pl/glowna/podstawowy"]
    shot["document"]["communication"]["items"][0]["key"] = "#slide-article > h3:nth-of-type(1)"
    shot["document"]["communication"]["items"].append({"key": "#slide-article > p:nth-of-type(1)", "role": "banner", "text": "Projekt kwietnia kosztuje teraz 20% taniej."})
    shot["document"]["payload"] = {"commercial_context": {
        "links": [{"text": "Projekt kwietnia w promocji 20%", "url": "https://test.pl/aktualnosci/projekt-kwietnia"}],
        "items": [{"text": "PROJEKT KWIETNIA W PROMOCJI 20%", "url": "https://test.pl/#slide-article"}],
    }}
    assert not build_campaign_cards(state, view)


def test_other_month_without_year_is_uncertain_not_invented_as_expired():
    state, view = inputs(home="Projekt czerwca taniej o 20%")
    card = build_campaign_cards(state, view)[0]
    assert card["scope"]["status"] == "unverified_period"
    assert "nie potwierdzono" in card["scope"]["text"] and not card["effective_price"]


def test_heading_and_description_from_one_recorded_carousel_slide_form_one_card():
    state, view = inputs(home="Projekt czerwca taniej o 20%")
    items = state["snapshots"]["test.pl/glowna/podstawowy"]["document"]["communication"]["items"]
    items[0]["url"] = "https://test.pl/#slick-slide04"
    items.append({"key": "#slick-slide04 > p:nth-of-type(1)", "role": "banner", "text": "Avalon V: do końca czerwca kupisz go 20% taniej.", "url": "https://test.pl/#slick-slide04"})
    cards = build_campaign_cards(state, view)
    assert len(cards) == 1 and len(cards[0]["home"]) == 2
