import copy

import pytest
from test_communication import AFTER, BEFORE, capture

from pracownie.extract import extract_fields
from pracownie.model import Result, Snapshot
from pracownie.offers import primary_offer
from pracownie.rebuild import annotate_archived_tax


def source(at=AFTER, price="4593.50", flag="false"):
    payload = {
        "page": "projekt",
        "products": [
            {
                "name": "Projekt Testowy",
                "sku": "5314",
                "offers": {
                    "price": price,
                    "priceCurrency": "PLN",
                    "priceSpecification": {
                        "price": price,
                        "priceCurrency": "PLN",
                        "valueAddedTaxIncluded": flag,
                    },
                },
            }
        ],
    }
    shot = capture(at, [])
    shot.page = "projekt"
    shot.title = "Projekt Testowy"
    shot.fields, _ = extract_fields(payload, at)
    shot.document["payload"] = payload
    return shot


@pytest.mark.parametrize(
    "flag,tax", [(False, "net"), ("false", "net"), (True, "gross"), ("true", "gross"), ("unknown", "")]
)
def test_explicit_schema_flag_is_preserved_without_assuming_vat_rate(flag, tax):
    shot = source(flag=flag)
    assert shot.fields["oferta:5314:price"].tax == tax
    assert primary_offer(shot)["tax"] == tax


def test_legacy_unit_annotation_does_not_mutate_or_relabel_a_different_quote():
    raw = source().to_dict()
    raw["fields"]["oferta:5314:price"]["tax"] = ""
    original = copy.deepcopy(raw)
    restored = Snapshot.from_dict(raw)
    assert primary_offer(restored)["tax"] == "net"
    assert raw == original
    raw["fields"]["oferta:5314:price"]["amount"] = "9999.00"
    assert Snapshot.from_dict(raw).fields["oferta:5314:price"].tax == ""


def test_rebuild_uses_the_original_capture_for_each_sides_tax(tmp_path):
    old, new = source(BEFORE, "5000.00"), source()
    old_quote, new_quote = primary_offer(old), primary_offer(new)
    old_quote["tax"] = new_quote["tax"] = ""
    row = Result(
        new.domain,
        "projekt",
        "podstawowy",
        "changed",
        new.url,
        [],
        observed_at=AFTER,
        offer=new_quote,
        before_offer=old_quote,
        compared_at=BEFORE,
    )
    state = {"snapshots": {new.key: new.to_dict()}, "anchor": {old.key: old.to_dict()}}
    assert len(annotate_archived_tax([row], tmp_path, "2026-10-21", state)) == 2
    assert row.offer["tax"] == row.before_offer["tax"] == "net"
    assert row.offer["amount"] == "4593.50" and row.before_offer["amount"] == "5000.00"
    row.before_offer["tax"] = ""
    old.observed_at = AFTER
    state["anchor"][old.key] = old.to_dict()
    assert not annotate_archived_tax([row], tmp_path, "2026-10-21", state)
    assert row.before_offer["tax"] == ""
