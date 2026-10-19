import copy
import json
import zipfile
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from PIL import Image

from pracownie.compare import compare
from pracownie.extract import MONEY, amount, canonical_url, extract_fields, normalize, validate_payload
from pracownie.model import Field, Snapshot, local_day
from pracownie.state import StateStore, atomic_write


def snapshot(price="4590.00", when="2026-10-18T06:00:00+00:00"):
    return Snapshot("test.pl", "projekt", "base", "https://test.pl/projekt", when, "Dom", {
        "price": Field("Cena", price + " PLN", "ceny", "oferta", price, "PLN", when)
    }, ["oferta"], "", "test")


def test_price_promotions_and_removal():
    before, after = snapshot(), snapshot("4290.00", "2026-10-19T06:00:00+00:00")
    before.fields["promo"] = Field("Promocja", "Rabat 10% do 20.10", "promocje")
    after.fields["bonus"] = Field("Kosztorys", "Gratis", "dodatki")
    changes, _ = compare(before, after)
    price = next(c for c in changes if c.label == "Cena")
    assert price.delta == "-300.00" and price.percent == "-6.54"
    assert {c.kind for c in changes} == {"changed", "added", "removed"}
    assert compare(after, after)[0] == []
    assert compare(None, after)[0] == []


def test_missing_section_is_review_and_retained():
    before, after = snapshot(), snapshot()
    before.fields["bonus"] = Field("Dodatek", "Kosztorys gratis", "dodatki", "dodatki")
    changes, retained = compare(before, after)
    assert changes[0].kind == "review"
    assert "bonus" in retained.fields


def test_money_and_normalization():
    assert MONEY.findall("4 590,00 zł, 4290 PLN; 100 m²") == [("4 590,00", "zł"), ("4290", "PLN")]
    assert amount("4\u202f590,00") == "4590.00"
    assert normalize("Promocja do 20.10.2026, 01:02:03, cena 4590 zł") == "Promocja do 20.10.2026, [licznik], cena 4590 zł"
    assert canonical_url("https://test.pl/p?utm_source=x&wariant=pdf#abc") == "https://test.pl/p?wariant=pdf"
    with pytest.raises(ValueError):
        validate_payload({"title": "Just a moment", "text": "Verify you are human"})


def test_variants_are_separate():
    fields, _ = extract_fields({"products": [{"name": "Dom", "offers": [
        {"name": "PDF", "price": "4590", "priceCurrency": "PLN"},
        {"name": "Papier", "price": "4790", "priceCurrency": "PLN"}]}]}, "2026-10-19T06:00:00+00:00")
    assert {Decimal(f.amount) for f in fields.values()} == {Decimal(4590), Decimal(4790)}
    assert len(fields) == 2


def seed(store, day="2026-10-18"):
    path = store.root / "test.png"
    Image.new("RGB", (100, 100), "white").save(path)
    data = store.begin(day)
    item = snapshot()
    item.image = store.image(path)
    data["snapshots"][item.key] = item.to_dict()
    store.commit(data)
    return data


def test_same_day_rerun_and_fresh_store(tmp_path):
    store = StateStore(tmp_path / "one")
    seed(store)
    today = store.begin("2026-10-19")
    today["snapshots"] = copy.deepcopy(today["snapshots"])
    today["snapshots"]["test.pl/projekt/base"]["fields"]["price"]["value"] = "4290 PLN"
    store.commit(today)
    again = store.begin("2026-10-19")
    assert again["anchor"]["test.pl/projekt/base"]["fields"]["price"]["value"] == "4590.00 PLN"
    archive = tmp_path / "state.zip"
    store.export(archive)
    fresh = StateStore(tmp_path / "two")
    fresh.restore(archive)
    assert fresh.read() == store.read()
    with pytest.raises(ValueError):
        fresh.begin("2026-10-17")
    with pytest.raises(ValueError):
        fresh.restore(archive, "bad-checksum")


def test_retention_and_archive_traversal(tmp_path):
    store = StateStore(tmp_path / "state")
    seed(store)
    assert store.begin("2027-10-19")["snapshots"] == {}
    malicious = tmp_path / "bad.zip"
    with zipfile.ZipFile(malicious, "w") as archive:
        archive.writestr("../escape.txt", "bad")
    with pytest.raises(ValueError):
        store.restore(malicious)
    assert not (tmp_path / "escape.txt").exists()


def test_atomic_failure_and_lock(tmp_path, monkeypatch):
    import pracownie.state as module
    path = tmp_path / "state.json"
    atomic_write(path, b'{"ok": true}')
    def broken(*args):
        raise OSError("simulated interruption")
    monkeypatch.setattr(module.os, "replace", broken)
    with pytest.raises(OSError):
        atomic_write(path, b"broken")
    assert json.loads(path.read_text()) == {"ok": True}
    store = StateStore(tmp_path)
    with store.lock(), pytest.raises(RuntimeError), store.lock():
        pass


def test_warsaw_dst_and_weekend():
    assert local_day(datetime(2026, 3, 28, 23, 30, tzinfo=UTC)) == "2026-03-29"
    assert local_day(datetime(2026, 10, 24, 22, 30, tzinfo=UTC)) == "2026-10-25"
    assert datetime.fromisoformat("2026-10-25").weekday() == 6
