from dataclasses import replace

import pytest
from test_compare_state import snapshot

from pracownie.browser import infer_scenarios
from pracownie.compare import compare
from pracownie.model import Field


@pytest.mark.parametrize("changed", [
    {"url": "https://test.pl/projekt-inny"},
    {"url": "https://test.pl/projekt?ID=2"},
    {"domain": "other.pl"},
    {"page": "glowna"},
    {"scenario": "other-option"},
])
def test_different_project_or_capture_scope_cannot_establish_offer_change(changed):
    old = snapshot()
    old.fields["old-extra"] = Field("Dodatek", "Kosztorys gratis", "dodatki")
    new = replace(snapshot("4290.00", "2026-10-19T06:00:00+00:00"), **changed)
    changes, retained = compare(old, new)
    assert changes and all(change.kind == "review" for change in changes)
    assert all(change.delta is None and change.percent is None for change in changes)
    assert any(change.field_key == "identity" for change in changes)
    assert "old-extra" not in retained.fields
    assert "old-extra" in old.fields  # Original evidence is preserved.


def test_tracking_fragment_does_not_change_project_identity():
    old = snapshot()
    new = snapshot("4290.00", "2026-10-19T06:00:00+00:00")
    new.url += "?utm_source=mail#offer"
    changes, _ = compare(old, new)
    assert len(changes) == 1 and changes[0].delta == "-300.00"


def test_project_picker_does_not_scan_other_projects_but_variants_remain_available():
    def select(label, name):
        return {"kind": "select", "label": label, "selector": "#" + name, "name": name,
                "value": "current", "options": [{"value": "current", "label": "E-268a"},
                                                {"value": "next", "label": "E-101"}]}
    scenarios, warnings = infer_scenarios({"controls": [
        select("Projekt:", "project"), select("Wybierz projekt domu", "catalogue"),
        select("Wersja projektu", "version"), select("Ogrzewanie", "heating"),
    ]}, "projekt")
    assert [s.actions[0]["selector"] for s in scenarios] == ["#version", "#heating"]
    assert any("innego projektu" in warning for warning in warnings)
