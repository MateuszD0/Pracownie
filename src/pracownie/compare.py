from __future__ import annotations

import copy
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .model import Change, Snapshot


def compare(before: Snapshot | None, after: Snapshot) -> tuple[list[Change], Snapshot]:
    if before is None:
        return [], after
    changes = []
    retained = copy.deepcopy(after)
    for key in sorted(set(before.fields) | set(after.fields)):
        old, new = before.fields.get(key), after.fields.get(key)
        if old and new and old.value == new.value and old.amount == new.amount and old.currency == new.currency:
            continue
        current = new or old
        assert current is not None
        missing_section = old is not None and new is None and old.section not in after.sections
        uncertain = missing_section or after.quality != "ok"
        if old and new is None and uncertain:
            retained.fields[key] = old
        change = Change(
            kind="review" if uncertain else ("added" if old is None else "removed" if new is None else "changed"),
            category=current.category,
            label=current.label,
            before=old.value if old else None,
            after=new.value if new else None,
            before_at=(old.observed_at or before.observed_at) if old else before.observed_at,
            after_at=after.observed_at,
            url=after.url,
            scenario=after.scenario,
            note="Nie odnaleziono poprzedniej sekcji; wymaga oceny, nie potwierdzono usunięcia." if missing_section else "",
        )
        if old and new and old.amount is not None and new.amount is not None and old.currency == new.currency:
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
