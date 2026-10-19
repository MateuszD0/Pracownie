import copy
import json
import zipfile
from datetime import UTC, date, datetime, timedelta
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


@pytest.mark.parametrize("title", ["Projekty dużych domów jednorodzinnych", "Najnowsze projekty domów", "PROJEKTY DOMÓW", "Projekty domów do 100m2", "Jak mądrze wybrać projekt domu?", "Pompy ciepła", "DOMY DLA DEWELOPERÓW"])
def test_category_or_article_is_not_a_project_even_with_product_schema(title):
    with pytest.raises(ValueError, match="kategorii"):
        validate_payload({"h1": title, "text": "Projekt domu, opis projektu i powierzchnia. Cena 4500 PLN. " * 3, "products": [{"name": "Dom A"}]}, product=True)
    validate_payload({"h1": "Projekt domu Lolek II N", "text": "Opis projektu domu, powierzchnia 100 m2. Cena 4500 PLN."}, product=True)


def test_changed_extractor_requires_review_and_ignores_derived_only_change():
    before, after = snapshot(), snapshot("4290.00")
    before.renderer = "chromium-1|extractor=old"
    after.renderer = "chromium-1|extractor=new"
    changes, _ = compare(before, after)
    assert changes[0].kind == "review"
    assert "reguły odczytu" in changes[0].note
    after.fields["price"].value = before.fields["price"].value
    assert compare(before, after)[0] == []


def test_uncertain_price_change_is_labeled_in_report_highlights():
    from pracownie.model import Result
    from pracownie.report import render_report
    before, after = snapshot(), snapshot("4290.00")
    after.quality = "partial"
    changes, _ = compare(before, after)
    report = render_report("2026-10-19", [Result("test.pl", "projekt", "base", "review", after.url, changes)], {"started_at": "2026-10-19T04:00:00+00:00", "finished_at": "2026-10-19T04:01:00+00:00", "elapsed_seconds": 60}, {}, ["test.pl"])
    highlights = report.split("NAJWAŻNIEJSZE ZMIANY")[1].split("SZCZEGÓŁY WEDŁUG DOMEN")[0]
    assert "DO OCENY: test.pl" in highlights
    assert "spadek o 300.00" in highlights


def test_variants_are_separate():
    fields, _ = extract_fields({"products": [{"name": "Dom", "offers": [
        {"name": "PDF", "price": "4590", "priceCurrency": "PLN"},
        {"name": "Papier", "price": "4790", "priceCurrency": "PLN"}]}]}, "2026-10-19T06:00:00+00:00")
    assert {Decimal(f.amount) for f in fields.values()} == {Decimal(4590), Decimal(4790)}
    assert len(fields) == 2


def test_crossed_price_and_uppercase_currency():
    fields, _ = extract_fields({"prices": [
        {"text": "6900 zł", "context": "Cena regularna 6900 zł", "type": "SPAN line-through"},
        {"text": "5520 ZŁ", "context": "Cena projektu 5520 ZŁ", "type": "SPAN"},
    ]}, "2026-10-19T06:00:00+00:00")
    assert {f.currency for f in fields.values()} == {"PLN"}
    assert any("poprzednia" in f.label for f in fields.values())


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


def test_retention_uses_warsaw_calendar_day(tmp_path):
    store = StateStore(tmp_path)
    data = seed(store, "2026-10-19")
    data["snapshots"]["test.pl/projekt/base"]["observed_at"] = "2026-10-18T22:30:00+00:00"
    store.commit(data)
    day = (date(2026, 10, 19) + timedelta(days=179)).isoformat()
    assert store.begin(day)["snapshots"]


def test_output_does_not_replace_user_folder(tmp_path):
    from pracownie.report import install_outputs
    staging, output = tmp_path / "staging", tmp_path / "output"
    (staging / "2026-10-19").mkdir(parents=True)
    (staging / "2026-10-19.txt").write_text("generated")
    (output / "2026-10-19").mkdir(parents=True)
    (output / "2026-10-19" / "user.txt").write_text("preserve")
    with pytest.raises(ValueError, match="osobny"):
        install_outputs(staging, output, "2026-10-19", "test")
    assert (output / "2026-10-19" / "user.txt").read_text() == "preserve"


def test_output_preserves_notes_added_to_generated_report(tmp_path):
    from pracownie.report import install_outputs, write_outputs
    day = "2026-10-19"
    first, second, output = tmp_path / "first", tmp_path / "second", tmp_path / "output"
    metadata = {"run_id": "test", "started_at": day + "T04:00:00+00:00", "finished_at": day + "T04:01:00+00:00", "elapsed_seconds": 60}
    write_outputs(first, day, [], metadata, {}, [])
    install_outputs(first, output, day, "one")
    notes = output / day / "notatki.txt"
    notes.write_text("Notatki użytkownika")
    write_outputs(second, day, [], metadata, {}, [])
    with pytest.raises(ValueError, match="użytkownika"):
        install_outputs(second, output, day, "two")
    assert notes.read_text() == "Notatki użytkownika"


def test_verified_daily_archive_restore_and_wrong_run(tmp_path):
    from pracownie.report import bundle_report, restore_report, verify_outputs, write_outputs
    day = "2026-10-19"
    root = tmp_path / "source"
    metadata = {"run_id": "expected", "started_at": day + "T04:00:00+00:00", "finished_at": day + "T04:01:00+00:00", "elapsed_seconds": 60}
    write_outputs(root, day, [], metadata, {}, [])
    archive = tmp_path / "report.zip"
    bundle_report(root, day, archive)
    restored = tmp_path / "restored"
    restore_report(archive, restored, day, "expected")
    verify_outputs(restored, day)
    with pytest.raises(ValueError, match="zatwierdzonemu"):
        restore_report(archive, tmp_path / "wrong", day, "other-run")
