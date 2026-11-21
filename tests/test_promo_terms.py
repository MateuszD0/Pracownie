import json
from types import SimpleNamespace

from test_commercial_verification import AT, BEFORE, DAY, URL, shot

from pracownie.commercial import verify_offers
from pracownie.model import Result, Site
from pracownie.promo_terms import compare_promo_terms, terms

VIEW = {"day": DAY, "rows": [{"domain": "test.pl"}]}
PACKAGE = ("Kod BF20: rabat 20% na wszystkie projekty domów. Minimalna wartość zamówienia: 4 000 zł. "
           "Nie łączy się z innymi promocjami. Do 30.11.2026. Cena po rabacie: 3 200 zł.")


def state(old, new):
    return {"anchor": {old.key: old.to_dict()}, "snapshots": {new.key: new.to_dict()}}


def test_same_code_with_reduced_scope_and_new_threshold_compares_customer_terms():
    before = PACKAGE.replace("20%", "10%").replace("4 000 zł", "3 000 zł").replace("30.11.2026", "29.11.2026")
    after = PACKAGE.replace("na wszystkie projekty", "na wybrane projekty")
    row, = compare_promo_terms(state(shot([before], at=BEFORE), shot([after])), VIEW)
    assert row["status"] == "changed" and row["page"] == "projekt"
    assert row["code"] == "BF20"
    assert set(row["changed_fields"]) == {"value", "minimum", "expiry", "scope"}
    assert row["before"]["value"] == "10%" and row["after"]["value"] == "20%"
    assert row["after"]["effective_price"] == "3 200 zł"
    assert row["after"]["stacking"] == "Nie łączy się z innymi promocjami"
    assert row["after"]["observed_at"] == AT and row["after"]["source"] == URL
    assert row["before"]["quote"] == before and row["after"]["quote"] == after


def test_partial_gaps_conflicts_and_different_urls_do_not_establish_an_offer_change():
    previous = shot([PACKAGE], at=BEFORE)
    for old, new in [
        (previous, shot([PACKAGE.replace("20%", "50%")], quality="partial")),
        (shot([PACKAGE], at="2026-10-23T08:00:00Z"), shot([PACKAGE.replace("20%", "50%")])),
        (previous, shot([PACKAGE.replace("20%", "50%")], url=URL+"/other")),
        (previous, shot([PACKAGE, PACKAGE.replace("20%", "50%")])),
        (previous, shot(["Brak szczegółów"], quality="partial")),
    ]:
        assert all(r["status"] == "observed" for r in compare_promo_terms(state(old, new), VIEW))
    assert terms("20% rabatu na projekt, 50% rabatu na garaż") is None
    assert terms("Kod BF20, cena regularna 5 000 zł, do 25% rabatu")["effective_price"] == ""
    assert terms("Kody pocztowe do 40-000 Kraków") is None


def test_missing_and_appearing_language_describes_observations_on_one_page():
    prev, now = shot([PACKAGE], at=BEFORE), shot(["Tekst podstawowy"])
    missing, = compare_promo_terms(state(prev, now), VIEW)
    assert missing["status"] == "missing" and missing["after"] is None
    added, = compare_promo_terms(state(shot(["Tekst podstawowy"], at=BEFORE), shot([PACKAGE])), VIEW)
    assert added["status"] == "appeared" and added["before"] is None


async def test_unchanged_banner_links_to_new_terms_and_rebuild_replays_recorded_sources(tmp_path):
    reg = "https://test.pl/regulamin-promocji"
    links = [{"url": reg, "text": "Regulamin promocji"}]
    old, new = shot(["Kod BF20"], at=BEFORE, links=links), shot(["Kod BF20"], links=links)
    current_state = state(old, new)
    calls = []
    folder = tmp_path/"test.pl"

    class Scanner:
        async def capture(self, site, page, url, scenario, path):
            calls.append(url)
            return SimpleNamespace(snapshot=shot([PACKAGE], url=reg))

    result = Result(new.domain, new.page, new.scenario, "unchanged", new.url, [], observed_at=AT)
    await verify_offers(Site("test.pl", "https://test.pl/"), [SimpleNamespace(snapshot=new)], [result],
                        [old], Scanner(), tmp_path, folder)
    assert calls == [reg]
    verification = folder/"weryfikacja-oferty.json"
    report = json.loads(verification.read_text())
    earlier = json.loads(json.dumps(report).replace(AT, BEFORE).replace("20%", "10%"))
    verification.write_text(json.dumps(earlier))
    compare_promo_terms(current_state, {**VIEW, "day": "2026-10-25"}, tmp_path)
    verification.write_text(json.dumps(report))
    rows = compare_promo_terms(current_state, VIEW, tmp_path)
    linked, = [r for r in rows if r["page"] == "terms"]
    assert linked["status"] == "changed" and linked["source"] == reg
    assert linked["before"]["value"] == "10%" and linked["after"]["value"] == "20%"
    assert rows == compare_promo_terms(current_state, VIEW, tmp_path)


def test_currency_code_on_homepage_retains_cap_and_fixed_card_quotes_offer_separately():
    from pracownie.commercial import document

    home = "Wszystkie projekty domów taniej nawet o 1100 zł z kodem BLACK500 🔥"
    project = "Kup ten projekt jeszcze taniej o 500 zł z kodem „BLACK500” 🔥"
    for quote, value, scope in [(home, "do 1100 zł", "Wszystkie projekty domów"), (project, "500 zł", "ten projekt")]:
        assert quote in document(shot([quote]))["claims"]
        item = terms(quote)
        assert item["code"] == "BLACK500" and item["value"] == value and item["scope"] == scope
        assert item["effective_price"] == ""
    assert terms("Płatność kodem BLIK") is None
    assert terms("BLACK WEEK -10% na wybrane projekty do końca listopada!")["expiry"] == "do końca listopada"
    assert terms("BLACK WEEK -400 zł na projekty w dniach 20-30.11.2026")["expiry"] == "30.11.2026"


def test_coupon_with_additional_reduction_is_not_compared_to_new_combined_ceiling():
    old = "Projekty domów taniej o 600 zł, a z kodem BLACK500 jeszcze o 500 zł 🔥"
    new = "Wszystkie projekty domów taniej nawet o 1100 zł z kodem BLACK500 🔥"
    row, = compare_promo_terms(state(shot([old], at=BEFORE), shot([new])), VIEW)
    assert row["status"] == "observed" and row["changed_fields"] == []
    assert row["before"]["value"] == "" and row["before"]["quote"] == old
    assert row["after"]["value"] == "do 1100 zł"


def test_nonstackable_coupon_is_a_condition_not_the_benefit_of_the_current_campaign():
    item = terms("Promocja nie łączy się z kodem rabatowym 5% za wypełnienie ankiety.")
    assert item["value"] == item["code"] == item["effective_price"] == ""
    assert item["stacking"] == "nie łączy się z kodem rabatowym 5% za wypełnienie ankiety"


def test_long_stacking_exception_retains_its_decisive_final_words():
    sentence = ("Bon nie łączy się z innymi rabatami procentowymi oraz innymi akcjami promocyjnymi "
                "Organizatora, chyba że regulamin danej promocji stanowi inaczej.")
    assert terms(sentence)["stacking"].endswith("chyba że regulamin danej promocji stanowi inaczej")
