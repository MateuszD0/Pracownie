from types import SimpleNamespace

from PIL import Image

from pracownie.compare import compare
from pracownie.images import ocr_context
from pracownie.model import Field, Snapshot


def test_ocr_low_confidence_remains_evidence(tmp_path, monkeypatch):
    import pracownie.images as module
    source = tmp_path / "banner.png"
    Image.new("RGB", (600, 300), "white").save(source)
    monkeypatch.setattr(module, "ocr_language", lambda: "eng")
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="conf\ttext\n32\t9990\n35\tzl\n"))
    text, note = ocr_context(source, tmp_path / "crop.png")
    assert "9990" in text and "wymaga oceny" in note
    assert (tmp_path / "crop.png").is_file()


def test_partial_read_cannot_confirm_removed_price():
    old = Snapshot("test.pl", "projekt", "base", "https://test.pl/projekt", "2026-10-18T06:00:00+00:00", "Dom", {"price": Field("Cena", "4590 PLN", "ceny", amount="4590", currency="PLN")}, ["oferta"], "", "test")
    new = Snapshot("test.pl", "projekt", "base", old.url, "2026-10-19T06:00:00+00:00", "Dom", {}, ["oferta"], "", "test", quality="partial")
    changes, retained = compare(old, new)
    assert changes[0].kind == "review"
    assert "price" in retained.fields
