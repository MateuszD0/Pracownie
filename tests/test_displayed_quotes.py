import copy
from dataclasses import replace

import pytest

from pracownie.extract import extract_fields
from pracownie.model import Result, Snapshot
from pracownie.offers import price_delta, primary_offer
from pracownie.rebuild import repair_archived_dom_quotes


def captured(text, at="2026-11-21T10:00:00+00:00", *, context=None, price_class="BDI"):
    fields, sections = extract_fields({"prices": [
        {"text": text, "context": context or text, "primary": True, "type": price_class}
    ]}, at)
    return Snapshot("test.pl", "projekt", "podstawowy", "https://test.pl/dawid", at, "Dawid", fields, sections, "", "test")


@pytest.mark.parametrize(("text", "expected"), [
    ("4,400zł", "4400.00"), ("4.400 zł", "4400.00"), ("1.200.000 zł", "1200000.00"),
    ("4.40 zł", "4.40"), ("4,40 zł", "4.40"), ("0.999 zł", "1.00"),
])
def test_visible_currency_groups_and_grosze(text, expected):
    assert primary_offer(captured(text))["amount"] == expected


def test_json_decimal_remains_decimal():
    fields, _ = extract_fields({"products": [{"name": "Dawid", "offers": {"price": "4.400", "priceCurrency": "PLN"}}]}, "")
    assert fields["oferta:dawid:price"].amount == "4.40"


def test_discount_badge_is_not_a_price_fallback():
    shot = captured("-200 zł", context="-200 zł Eurokody", price_class="DIV priceDiscount none")
    field = next(iter(shot.fields.values()))
    assert field.role == "discount" and field.category == "promocje"
    assert primary_offer(shot) == {}
    raw = shot.to_dict()
    raw_field = next(iter(raw["fields"].values()))
    raw_field.update(category="ceny", role="current", label="Cena widoczna: -[cena] Eurokody")
    assert primary_offer(Snapshot.from_dict(raw)) == {}


def test_rebuild_and_tomorrows_scan_correct_both_legacy_quotes_from_the_source():
    old = captured("4,400zł", "2026-11-20T10:00:00+00:00")
    new = captured("4,400zł")
    old_quote = {**primary_offer(old), "amount": "4.40", "low": "4.40", "high": "4.40"}
    new_quote = {**old_quote, "observed_at": new.observed_at}
    row = Result(new.domain, new.page, new.scenario, "unchanged", new.url, observed_at=new.observed_at,
                 offer=new_quote, before_offer=old_quote, compared_at=old.observed_at)
    sources = [shot.to_dict() for shot in (old, new)]
    for raw in sources:
        next(iter(raw["fields"].values()))["amount"] = "4.40"
    audit = repair_archived_dom_quotes(row, sources)
    assert len(audit) == 2
    assert row.offer["amount"] == row.before_offer["amount"] == "4400.00"
    assert price_delta(row.before_offer, row.offer) == ("0.00", "0.00")
    assert not repair_archived_dom_quotes(row, sources)
    assert price_delta(primary_offer(Snapshot.from_dict(sources[0])), primary_offer(new)) == ("0.00", "0.00")
    # Wrong domain with a matching timestamp is never evidence for yesterday.
    incomplete = replace(row, offer=new_quote, before_offer=old_quote)
    mismatched = copy.deepcopy(sources[0])
    mismatched["domain"] = "other.pl"
    repair_archived_dom_quotes(incomplete, [mismatched, sources[1]])
    assert incomplete.offer["amount"] == "4400.00" and not incomplete.before_offer
