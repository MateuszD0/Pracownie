from __future__ import annotations

import copy
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .extract import canonical_url
from .model import Change, Snapshot
from .observations import location_url, replay_pair, signature


def compare(before: Snapshot | None, after: Snapshot, excluded_keys: list[str] | None = None) -> tuple[list[Change], Snapshot]:
    if before is None:
        return [], after
    before, after = replay_pair(before, after)
    same_identity = (before.domain, before.page, before.scenario, canonical_url(before.url)) == (
        after.domain, after.page, after.scenario, canonical_url(after.url)
    )
    changes = []
    retained = copy.deepcopy(after)
    if not same_identity:
        changes.append(Change(
            "review", "komunikacja", "Niezgodna tożsamość porównywanych stron",
            before.url, after.url, before.observed_at, after.observed_at, after.url, after.scenario,
            field_key="identity", note="Zmieniono adres, pracownię, stronę lub scenariusz. Nie ustalono zmiany oferty tego samego projektu.",
        ))
    for key in sorted(set(before.fields) | set(after.fields)):
        if key in (excluded_keys or []):
            continue
        old, new = before.fields.get(key), after.fields.get(key)
        if old and new and old.value == new.value:
            continue
        if old and new and old.amount is not None and new.amount is not None and old.currency == new.currency and Decimal(old.amount) == Decimal(new.amount):
            continue
        current = new or old
        assert current is not None
        missing_section = old is not None and new is None and old.section not in after.sections
        method_changed = signature(before, current.category) != signature(after, current.category)
        # A browser/cookie-handler update does not alter a direct JSON-LD price
        # with the same product/offer identity. Text and inferred DOM mappings
        # still require review when their extraction rules change.
        authoritative_pair = old is not None and new is not None and key.startswith("oferta:") and key.endswith((":price", ":lowPrice", ":highPrice")) and old.amount is not None and new.amount is not None
        uncertain = not same_identity or missing_section or after.quality != "ok" or before.quality != "ok" or method_changed and not authoritative_pair
        if old and new is None and uncertain and same_identity:
            retained.fields[key] = old
        destination_text = new.value if new else None
        if old and new:
            previous_lines = set(old.value.splitlines())
            destination_text = "\n".join(line for line in new.value.splitlines() if line not in previous_lines) or new.value
        change = Change(
            kind="review" if uncertain else ("added" if old is None else "removed" if new is None else "changed"),
            category=current.category,
            label=current.label,
            before=old.value if old else None,
            after=new.value if new else None,
            before_at=(old.observed_at or before.observed_at) if old else before.observed_at,
            after_at=after.observed_at,
            url=location_url(after, current.section, destination_text),
            scenario=after.scenario,
            note="Nie odnaleziono poprzedniej sekcji; wymaga oceny, nie potwierdzono usunięcia." if missing_section else "",
            field_key=key,
        )
        if method_changed and not authoritative_pair:
            change.note += " Zmieniono wersję przeglądarki lub reguły odczytu; różnica wymaga potwierdzenia w źródle."
        if not same_identity:
            change.note += " Porównywane zapisy mają inną tożsamość; nie ustalono zmiany oferty tego samego projektu."
        if same_identity and old and new and old.amount is not None and new.amount is not None and old.currency == new.currency:
            try:
                old_amount, new_amount = Decimal(old.amount), Decimal(new.amount)
                change.delta = str((new_amount - old_amount).quantize(Decimal("0.01")))
                if old_amount > 0:
                    change.percent = str(
                        ((new_amount - old_amount) / old_amount * 100).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                    )
            except InvalidOperation:
                change.note = "Nie udało się obliczyć różnicy ceny."
        changes.append(change)
    return changes, retained
