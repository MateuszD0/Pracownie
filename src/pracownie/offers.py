"""Comparable quotes from the selected product, never the cheapest number on a page."""

from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal

from .extract import MONEY, amount, currency_code, money_text
from .model import Snapshot


def _name(value: str) -> str:
    value = re.sub(r"projekt(?:y)?\s+dom(?:u|ów)?", "", value, flags=re.I)
    return re.sub(r"[^\w]", "", value).casefold()


def primary_offer(snapshot: Snapshot | None, excluded_keys: list[str] | None = None) -> dict:
    if snapshot is None or snapshot.quality not in {"ok", "partial"}:
        return {}
    rows = [
        (key, field)
        for key, field in snapshot.fields.items()
        if field.category == "ceny" and field.amount is not None and field.currency and key not in (excluded_keys or [])
    ]
    if snapshot.domain == "projektyszkieletowe.pl" and snapshot.page == "projekt":
        repaired = []
        for key, field in rows:
            if key == "adapter:cena-projektu" and field.source == "adapter":
                # The former broad header pattern joined the unit's "2" in
                # "m2" to the price on the next line. The archived field text
                # contains one explicit currency amount; validate against it.
                values = {(amount(m[1]), currency_code(m[2])) for m in MONEY.finditer(money_text(field.value))}
                if len(values) != 1 or next(iter(values))[1] != field.currency:
                    continue
                field = replace(field, amount=next(iter(values))[0])
            repaired.append((key, field))
        rows = repaired
    explicit = [
        (key, field)
        for key, field in rows
        if field.primary and field.role == "current" and field.source == "adapter"
    ]
    # A verified visible field remains informative when a stylesheet or a CMP
    # fails. Show it provisionally; never confirm a delta from a partial read.
    if snapshot.quality == "partial" and not explicit:
        return {}
    structured = [(key, field) for key, field in rows if key.startswith("oferta:") and key.endswith(":price")]
    title = _name(snapshot.title)
    matched = [
        (key, field)
        for key, field in structured
        if len(_name(field.label.split(" — ")[0])) >= 3 and _name(field.label.split(" — ")[0]) in title
    ]
    metadata = [(key, field) for key, field in rows if field.source == "meta" and field.primary]
    dom = [
        (key, field)
        for key, field in rows
        if field.primary and field.role == "current" and field.source == "dom"
    ]
    ranges = [(key, field) for key, field in rows if key.startswith("oferta:") and key.endswith((":lowPrice", ":highPrice"))]
    candidates = explicit or metadata or matched or (structured if len(structured) == 1 else []) or ranges or dom
    if not candidates:
        # A unique visible current price is usable when no product metadata is
        # published. Several different numbers do not identify a base price.
        visible = [(key, field) for key, field in rows if field.role == "current" and field.source == "dom"]
        if len({(field.amount, field.currency) for _, field in visible}) == 1:
            candidates = visible
    if not candidates:
        return {}
    currencies = {field.currency for _, field in candidates}
    if len(currencies) != 1:
        return {}
    values = sorted({Decimal(field.amount) for _, field in candidates})
    key, field = candidates[0]
    return {
        "kind": "price" if len(values) == 1 else "range",
        "amount": str(values[0]) if len(values) == 1 else None,
        "low": str(values[0]),
        "high": str(values[-1]),
        "currency": field.currency,
        "label": field.label,
        "field_key": key,
        "source": field.source or "jsonld",
        "observed_at": field.observed_at or snapshot.observed_at,
        "tax": field.tax or ("net" if re.search(r"\bnetto\b|\+\s*VAT", field.label + " " + field.value, re.I) else ""),
        "unit": field.unit,
        "quality": snapshot.quality,
    }


def price_delta(before: dict, after: dict) -> tuple[str | None, str | None]:
    if (
        not before
        or not after
        or before.get("kind") != "price"
        or after.get("kind") != "price"
        or before.get("currency") != after.get("currency")
        or before.get("tax", "") != after.get("tax", "")
        or before.get("unit", "") != after.get("unit", "")
        or before.get("quality", "ok") != "ok"
        or after.get("quality", "ok") != "ok"
    ):
        return None, None
    # The selected product and variant must retain their identity.
    if before.get("field_key") != after.get("field_key"):
        return None, None
    old, new = Decimal(before["amount"]), Decimal(after["amount"])
    delta = new - old
    percent = (delta / old * 100).quantize(Decimal("0.01")) if old else None
    return str(delta.quantize(Decimal("0.01"))), str(percent) if percent is not None else None
