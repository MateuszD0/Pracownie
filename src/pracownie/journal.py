"""The daily action table: offer facts and separately labelled visual observations."""

from __future__ import annotations

import csv
import hashlib
import html
import io
from datetime import datetime
from decimal import Decimal
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit

from .model import WARSAW

LABELS = {
    "ceny": "Cena",
    "promocje": "Promocja",
    "dodatki": "Dodatek",
    "pakiety": "Pakiet",
    "warunki": "Warunki zakupu",
    "funkcje": "Funkcja",
    "parametry": "Parametry",
    "komunikacja": "Komunikat",
    "tresc": "Treść",
    "obraz": "Wygląd",
}


def capture_day(value: str | None) -> str:
    return datetime.fromisoformat(value).astimezone(WARSAW).date().isoformat() if value else ""


def build_journal(day: str, rows: list[dict]) -> list[dict]:
    output = []

    def add(row, event, category, description, before, after, source, evidence, basis, specific=True):
        # Older last-good captures are useful evidence, but cannot be labelled
        # as a change between yesterday and today.
        before_at, after_at = event.get("before_at"), event.get("after_at")
        if not before_at or capture_day(after_at) != day:
            return
        from datetime import date

        gap = (date.fromisoformat(day) - date.fromisoformat(capture_day(before_at))).days
        if gap <= 0:
            return
        identity = hashlib.sha256(
            repr(
                (row["domain"], event["page"], category, description, before, after, before_at, after_at)
            ).encode()
        ).hexdigest()[:14]
        output.append(
            {
                "id": "zmiana-" + identity,
                "day": day,
                "domain": row["domain"],
                "page": event["page"],
                "project": row["name"] if event["page"] == "projekt" else "",
                "context": event.get("variant") or event.get("context", ""),
                "scenario": event.get("scenario", ""),
                "category": category,
                "type": LABELS.get(category, category),
                "description": description,
                "before": before or "brak",
                "after": after or "brak",
                "source": source,
                "evidence": evidence,
                "basis": basis,
                "before_at": before_at,
                "after_at": after_at,
                "gap_days": gap,
                "daily": gap == 1,
                "specific": specific,
                "delta": event.get("delta"),
                "percent": event.get("percent"),
                "selected_price": category == "ceny" and event.get("label") == "Cena projektu" and not event.get("variant") and event["page"] == "projekt",
            }
        )

    for row in rows:
        for event in row["events"]:
            description = event["label"]
            if event.get("delta") is not None and Decimal(event["delta"]):
                value = Decimal(event["delta"])
                description += (
                    (": spadek o " if value < 0 else ": wzrost o ")
                    + str(abs(value))
                    + " ("
                    + str(event.get("percent") or "—")
                    + "%)"
                )
            elif event.get("kind") == "added":
                description = "Dodano: " + description
            elif event.get("kind") == "removed":
                description = "Usunięto: " + description
            add(
                row,
                event,
                event["category"],
                description,
                event.get("before_full") or event["before"],
                event.get("after_full") or event["after"],
                event["source"],
                event["evidence"],
                event.get("basis") or "Porównanie tego samego pola oferty",
            )
        for visual in row["visuals"]:
            if visual.get("unreliable"):
                continue
            details = visual.get("details", {})
            facts = details.get("facts", [])
            if facts:
                add(
                    row,
                    visual,
                    "obraz",
                    details.get("description") or "; ".join(f["what"] for f in facts[:3]),
                    "\n".join(f["what"] + ": " + f["before"] for f in facts),
                    "\n".join(f["what"] + ": " + f["after"] for f in facts),
                    facts[0]["url"],
                    visual["evidence"],
                    "Zmieniony obraz i odczyt właściwości widocznego elementu",
                )
            else:
                ocr = details.get("ocr", {})
                add(
                    row,
                    visual,
                    "obraz",
                    details.get("description") or "Zmienił się obraz strony — zobacz zaznaczony fragment",
                    ocr.get("before") or "Poprzedni wygląd zaznaczonego obszaru",
                    ocr.get("after") or "Aktualny wygląd zaznaczonego obszaru",
                    visual["source"],
                    visual["evidence"],
                    details.get("basis", "Porównanie zrzutów; nie ustala zmiany ceny ani promocji")
                    + (" Tekst pomocniczy: OCR." if ocr else ""),
                    specific=False,
                )
    return sorted(
        output, key=lambda r: (not r["daily"], r["category"] == "obraz", r["domain"], r["page"], r["id"])
    )


def safe_source(url: str) -> str:
    return url if urlsplit(url).scheme in {"http", "https"} else ""


def relative_proof(day: str, path: str) -> str:
    p = PurePosixPath(path)
    return (
        "/".join(quote(v, safe="") for v in p.parts[1:])
        if p.parts and p.parts[0] == day and ".." not in p.parts
        else ""
    )


def render_journal_html(view: dict, *, rows: list[dict] | None = None, secondary: bool = False) -> str:
    esc = html.escape

    def value(text):
        text = str(text)
        if len(text) <= 480:
            return esc(text)
        return esc(text[:220]) + '…<details class="long-value"><summary>Pełna treść (' + str(len(text)) + ' znaków)</summary><div>' + esc(text) + '</div></details>'

    rows = rows if rows is not None else view.get("journal") or build_journal(view["day"], view["rows"])
    section_id = "secondary-journal" if secondary else "journal"
    title = "Pozostałe porównania i różnice obrazu" if secondary else "Najważniejsze zmiany dzień do dnia"
    head = '<section id="' + section_id + '" class="box"><h2>' + title + '</h2><p class="small">' + ("Ceny, same różnice obrazu i porównania po luce. Zmieniony zrzut sam nie ustala nowej kampanii ani przebudowy strony." if secondary else "Komunikaty, nagłówki, promocje, dodatki i opisane zmiany wyglądu. Każdy wpis ma treść przed / po, źródło i daty odczytów. Ceny są w szczegółach.") + '</p><div class="table-box" tabindex="0" role="region" aria-label="' + title + '"><table class="journal-table"><thead><tr><th>Pracownia</th><th>Strona</th><th>Rodzaj / priorytet</th><th>Co się zmieniło</th><th>Było</th><th>Jest</th><th>Źródło i dowód</th></tr></thead><tbody>'
    body = []
    proof_blocks = {}
    for item in rows:
        page = "Strona główna" if item["page"] == "glowna" else "Karta projektu"
        context = (
            ("Dzień do dnia" if item["daily"] else f"Ostatni odczyt sprzed {item['gap_days']} dni")
            + ": "
            + capture_day(item["before_at"])
            + " → "
            + capture_day(item["after_at"])
        )
        proofs = ""
        keys = (
            [("fragment_przed", "Przed"), ("fragment_po", "Po")]
            if item["evidence"].get("fragment_przed")
            else [("przed", "Przed"), ("po", "Po")]
        )
        for key, label in keys:
            path = relative_proof(view["day"], item["evidence"].get(key, ""))
            if path:
                proofs += (
                    '<figure><a href="'
                    + esc(path, quote=True)
                    + '" target="_blank" rel="noopener"><img loading="lazy" src="'
                    + esc(path, quote=True)
                    + '" alt="'
                    + label
                    + " — "
                    + esc(item["domain"], quote=True)
                    + '"><figcaption>'
                    + label
                    + "</figcaption></a></figure>"
                )
        proof_id = ("archiwum-" if secondary else "dowod-") + hashlib.sha256(repr(sorted(item["evidence"].items())).encode()).hexdigest()[:14]
        if proofs:
            proof_blocks[proof_id] = (
                '<details class="journal-proof"><summary>'
                + esc(item["domain"])
                + " · "
                + page
                + ' · zaznaczony fragment</summary><div id="'
                + proof_id
                + '" class="proofs">'
                + proofs
                + "</div></details>"
            )
        proof = '<br><a href="#' + proof_id + '">Zobacz przed / po</a>' if proofs else ""
        body.append(
            '<tr id="'
            + item["id"]
            + '" data-journal-domain="'
            + esc(item["domain"], quote=True)
            + '" data-page="'
            + item["page"]
            + '" data-category="'
            + item["category"]
            + '"><td>'
            + "<strong>"
            + esc(item["domain"])
            + "</strong></td><td>"
            + page
            + '<br><span class="small">'
            + esc(item["project"])
            + ("<br>" + esc(item.get("context", "")) if item.get("context") and item["context"] != page else "")
            + "</span></td><td>"
            + esc(item["type"])
            + ('<br><span class="badge">Wysoki</span>' if not secondary and item["category"] in {"ceny", "promocje", "dodatki", "pakiety"} else '')
            + "</td><td>"
            + esc(item["description"])
            + '<p class="small">'
            + esc(context)
            + '</p><span class="small">'
            + esc(item["basis"])
            + '</span></td><td class="journal-value">'
            + value(item["before"])
            + '</td><td class="journal-value">'
            + value(item["after"])
            + '</td><td><a href="'
            + esc(safe_source(item["source"]), quote=True)
            + '" target="_blank" rel="noopener">Zobacz na stronie</a>'
            + proof
            + "</td></tr>"
        )
    return (
        head
        + (
            "".join(body)
            or '<tr><td colspan="7">Brak potwierdzonych zmian w tym zakresie. Przy niepełnych danych nie oznacza to braku zmian na wszystkich stronach.</td></tr>'
        )
        + "</tbody></table></div>"
        + '<p id="' + section_id + '-empty" class="empty" hidden>Brak ustalonych zmian dla wybranego filtru. Zakres danych i przyczyny braków są pokazane osobno.</p>'
        + "".join(proof_blocks.values())
        + "</section>"
    )


def render_journal_csv(view: dict) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=";")
    writer.writerow(
        [
            "Dzień",
            "Pracownia",
            "Strona",
            "Projekt",
            "Kontekst / wariant",
            "Rodzaj",
            "Co się zmieniło",
            "Było",
            "Jest",
            "Źródło",
            "Odczyt przed",
            "Odczyt po",
            "Luka dni",
            "Podstawa",
        ]
    )
    for item in view.get("journal", []):
        values = [
            item[k]
            for k in [
                "day",
                "domain",
                "page",
                "project",
                "context",
                "type",
                "description",
                "before",
                "after",
                "source",
                "before_at",
                "after_at",
                "gap_days",
                "basis",
            ]
        ]
        writer.writerow(
            ["'" + str(v) if str(v).startswith(("=", "+", "-", "@", "\t", "\r")) else v for v in values]
        )
    return "\ufeff" + stream.getvalue()
