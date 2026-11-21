"""Price comparisons and literal discount evidence, independent of copy alerts."""

from __future__ import annotations

import html
import re
from decimal import Decimal

from .journal import capture_day, safe_source
from .relationships import group_for, groups

CODE = re.compile(
    r'\bkod(?:em|u)?\b\s*(?:(?:rabatow|promocyjn)(?:y|ego|ym)\s*)?[:=–-]?\s*[„"\']?([A-Za-z0-9][A-Za-z0-9_-]{2,30})',
    re.I,
)
STOP = {
    "rabatowy",
    "rabatowego",
    "promocyjny",
    "promocyjnego",
    "rabat",
    "koszyku",
    "tutaj",
    "kliknij",
    "wpisz",
    "pocztowy",
    "pocztowego",
    "oraz",
    "jest",
    "otrzymasz",
    "otrzymania",
    "uzyskasz",
    "brak",
    "blik",
    "ean",
    "isbn",
    "iban",
    "swift",
}


def codes(text: str) -> list[str]:
    # Require a literal token rather than a sentence such as "kod znajdziesz
    # w koszyku". Lowercase quoted codes are retained exactly as published.
    return list(
        dict.fromkeys(
            m[1]
            for m in CODE.finditer(text)
            if m[1].casefold() not in STOP
            and (
                m[1].isupper()
                or re.search(r"\d", m[1])
                or text[m.start(1) - 1 : m.start(1)] in {'"', "'", "„"}
            )
        )
    )


def meaningful_discount(text: str) -> bool:
    return bool(
        codes(text)
        or re.search(r"promoc|rabat|kupon|oszczęd", text, re.I)
        and re.search(r"\d+(?:[.,]\d+)?\s*(?:%|zł|PLN)", text, re.I)
    )


def financial_data(view: dict) -> dict:
    paired = set(view["comparison"]["price_domains"])
    prices = [
        r
        for r in view["rows"]
        if r.get("project_selected", True)
        and r.get("current", {}).get("kind") == "price"
        and r["current"].get("quality") == "ok"
        and capture_day(r["current"].get("observed_at")) == view["day"]
    ]
    changes = [
        r for r in prices if r["domain"] in paired and r.get("delta") is not None and Decimal(r["delta"]) != 0
    ]
    changes.sort(key=lambda r: (r.get("relationship") != "partner", Decimal(r["delta"]), r["domain"]))
    # The register supplies dated quotes. Presence alone is never a campaign launch.
    offers = []
    for offer in view.get("metadata", {}).get("intelligence", {}).get("offers", []):
        sources = [s for s in offer["sources"] if capture_day(s["observed_at"]) == view["day"]]
        if sources and meaningful_discount(offer["text"]):
            offers.append(
                {
                    **offer,
                    "sources": sources,
                    "codes": codes(offer["text"]),
                    "group": group_for(view, offer["domain"]),
                }
            )
    offers.sort(key=lambda o: (o["group"] != "partner", not o["codes"], o["domain"], o["text"]))
    graphics = [
        g
        for g in view.get("metadata", {}).get("intelligence", {}).get("graphics", [])
        if capture_day(g["observed_at"]) == view["day"]
    ]
    return {"prices": prices, "changes": changes, "paired": paired, "offers": offers, "graphics": graphics}


def markdown_financial(view: dict, folder: str, data: dict | None = None) -> tuple[list[str], dict[str, str]]:
    from .dashboard import cell, link
    from .presentation import money, when

    if data is None:
        data = financial_data(view)
    path = folder + "/ceny-i-rabaty.md"
    root = [
        "## Ceny, kody i rabaty",
        "",
        f"Porównywalne ceny dzień do dnia: **{len(data['paired'])}/{len(view['rows'])} projektów**. "
        f"Dzisiejsze jednoznaczne ceny: **{len(data['prices'])}**. Brak ceny nie oznacza braku zmian.",
        "",
    ]
    root += [
        "| Pracownia / ten sam projekt | Cena wczoraj | Cena dziś | Zmiana zł / % | Źródło |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in data["changes"]:
        root += [
            "| "
            + " | ".join(
                [
                    cell(row["domain"]) + "<br>" + cell(row["name"]),
                    cell(money(row["previous"])),
                    cell(money(row["current"])),
                    cell(row["delta"]) + " / " + cell(row["percent"]) + "%",
                    link("Karta projektu", row["url"]),
                ]
            )
            + " |"
        ]
    if not data["changes"]:
        root += [
            "| Nie wykryto zmiany w porównywalnych cenach."
            if data["paired"]
            else "| Brak porównywalnych par cen."
        ]
        root[-1] += " | | | | |"
    root += ["", "[Wszystkie odczytane ceny, kody i warunki rabatów](" + path + ")", ""]
    doc = [
        "# Ceny, kody i rabaty · " + view["day"],
        "",
        "[← Dashboard](../" + folder.upper() + ".md)",
        "",
        "Cena dotyczy jednego zapamiętanego projektu. Kody i rabaty pochodzą z publicznych komunikatów; nie sprawdzano ich użycia w koszyku.",
        "",
    ]
    for group, label in groups(view):
        doc += [
            "## " + (label or "Monitorowane pracownie"),
            "",
            "| Pracownia / projekt | Cena | Odczyt | Źródło |",
            "| --- | --- | --- | --- |",
        ]
        selected = [r for r in data["prices"] if group_for(view, r["domain"]) == group]
        doc += [
            "| "
            + cell(r["domain"])
            + "<br>"
            + cell(r["name"])
            + " | "
            + cell(money(r["current"]))
            + " | "
            + cell(when(r["current"]["observed_at"]))
            + " | "
            + link("Karta projektu", r["url"])
            + " |"
            for r in selected
        ]
        if not selected:
            doc += ["| Brak jednoznacznej ceny z dnia raportu. | | | |"]
    offer_lines = [
        "### Kody i konkretne rabaty odczytane w dniu raportu",
        "",
        "Obecność komunikatu nie oznacza, że promocja rozpoczęła się dzisiaj. Daty ważności i ograniczenia pozostają w cytacie.",
        "",
        "| Pracownia | Kod | Rabat / warunki — cytat | Stan / odczyt | Źródło |",
        "| --- | --- | --- | --- | --- |",
    ]
    for offer in data["offers"]:
        s = offer["sources"][0]
        offer_lines += [
            "| "
            + " | ".join(
                [
                    cell(offer["domain"]),
                    cell(", ".join(offer["codes"]) or "Nie podano"),
                    cell(offer["text"]),
                    cell(offer["status"]) + "<br>" + cell(when(s["observed_at"])),
                    link("Oferta", s["url"]),
                ]
            )
            + " |"
        ]
    if not data["offers"]:
        offer_lines += [
            "| Brak zapisanych konkretnych kodów lub rabatów z tego dnia; nie oznacza to braku promocji w serwisach. | | | | |"
        ]
    doc += ["", *offer_lines]
    # Keep the executive page short; full quotes and dates are one click away.
    root += [
        f"Zapisane komunikaty z kodem lub konkretnym rabatem: **{len(data['offers'])}**. "
        "Dostępne w tabeli pod linkiem powyżej; sama obecność nie potwierdza nowej promocji.",
        "",
    ]
    if data["offers"]:
        root += ["<details><summary>Komunikaty obecne dziś w ofertach</summary>", ""]
    for group, label in groups(view):
        chosen = [o for o in data["offers"] if o["group"] == group][:5]
        if not chosen:
            continue
        root += ["### " + (label or "Kody i rabaty"), "", *offer_lines[4:6]]
        for o in chosen:
            s = o["sources"][0]
            root += [
                "| "
                + " | ".join(
                    [
                        cell(o["domain"]),
                        cell(", ".join(o["codes"]) or "Nie podano"),
                        cell(o["text"][:500] + ("…" if len(o["text"]) > 500 else "")),
                        cell(o["status"]) + "<br>" + cell(when(s["observed_at"])),
                        link("Oferta", s["url"]),
                    ]
                )
                + " |"
            ]
        root += [""]
    if data["offers"]:
        root += ["</details>", ""]
    if data["graphics"]:
        media = [
            "### Grafiki z okien na stronie — sprawdź warunki",
            "",
            "Zachowano grafikę przed zamknięciem okna. Kwoty i kody z obrazu wymagają odczytania; nie zastąpiono ich domysłem.",
            "",
            "| Pracownia | Odczyt | Grafika | Strona |",
            "| --- | --- | --- | --- |",
        ]
        media += [
            "| "
            + cell(g["domain"])
            + " | "
            + cell(when(g["observed_at"]))
            + " | "
            + link("Otwórz grafikę", g["image"])
            + " | "
            + link("Strona", g["url"])
            + " |"
            for g in data["graphics"]
        ]
        root += media + [""]
        doc += media
    return root, {path: "\n".join(doc) + "\n"}


def render_financial(view: dict) -> str:
    from .presentation import money, when

    data = financial_data(view)
    esc = html.escape
    out = [
        '<section id="financial"><h2>Ceny, kody i rabaty</h2><p>Porównywalne ceny dzień do dnia: <strong>'
        + str(len(data["paired"]))
        + "/"
        + str(len(view["rows"]))
        + "</strong>. Dzisiejsze jednoznaczne ceny: <strong>"
        + str(len(data["prices"]))
        + "</strong>. Brak ceny nie oznacza braku zmian.</p>"
    ]
    out += [
        '<div class="table-box"><table><thead><tr><th>Pracownia / projekt</th><th>Cena wczoraj</th><th>Cena dziś</th><th>Zmiana zł / %</th><th>Źródło</th></tr></thead><tbody>'
    ]
    for r in data["changes"]:
        out += [
            '<tr data-intelligence-domain="'
            + esc(r["domain"])
            + '"><td>'
            + esc(r["domain"])
            + "<br>"
            + esc(r["name"])
            + "</td><td>"
            + esc(money(r["previous"]))
            + "</td><td>"
            + esc(money(r["current"]))
            + "</td><td>"
            + esc(r["delta"])
            + " / "
            + esc(r["percent"])
            + '%</td><td><a href="'
            + esc(safe_source(r["url"]), quote=True)
            + '">Karta projektu</a></td></tr>'
        ]
    if not data["changes"]:
        out += [
            '<tr><td colspan="5">'
            + (
                "Nie wykryto zmiany w porównywalnych cenach."
                if data["paired"]
                else "Brak porównywalnych par cen."
            )
            + "</td></tr>"
        ]
    out += [
        "</tbody></table></div><details><summary>Wszystkie dzisiejsze ceny ("
        + str(len(data["prices"]))
        + ')</summary><div class="table-box"><table><thead><tr><th>Pracownia / projekt</th><th>Cena</th><th>Odczyt</th><th>Źródło</th></tr></thead><tbody>'
    ]
    for r in data["prices"]:
        out += [
            '<tr data-intelligence-domain="'
            + esc(r["domain"])
            + '"><td>'
            + esc(r["domain"])
            + "<br>"
            + esc(r["name"])
            + "</td><td>"
            + esc(money(r["current"]))
            + "</td><td>"
            + esc(when(r["current"]["observed_at"]))
            + '</td><td><a href="'
            + esc(safe_source(r["url"]), quote=True)
            + '">Karta projektu</a></td></tr>'
        ]
    out += [
        "</tbody></table></div></details><details><summary>Kody i konkretne rabaty ("
        + str(len(data["offers"]))
        + ')</summary><p>Publiczne komunikaty z dnia raportu; sama obecność nie oznacza nowej promocji. Nie sprawdzano użycia kodu w koszyku.</p><div class="table-box"><table><thead><tr><th>Pracownia</th><th>Kod</th><th>Rabat / warunki — cytat</th><th>Stan / odczyt</th><th>Źródło</th></tr></thead><tbody>'
    ]
    for o in data["offers"]:
        s = o["sources"][0]
        out += [
            '<tr data-intelligence-domain="'
            + esc(o["domain"])
            + '"><td>'
            + esc(o["domain"])
            + "</td><td>"
            + esc(", ".join(o["codes"]) or "Nie podano")
            + "</td><td>"
            + esc(o["text"])
            + "</td><td>"
            + esc(o["status"])
            + "<br>"
            + esc(when(s["observed_at"]))
            + '</td><td><a href="'
            + esc(safe_source(s["url"]), quote=True)
            + '">Oferta</a></td></tr>'
        ]
    out += ["</tbody></table></div></details>"]
    if data["graphics"]:
        out += [
            "<h3>Grafiki z okien na stronie — sprawdź warunki</h3><p>Grafikę zachowano przed zamknięciem okna; kwoty i kody wymagają odczytania.</p><ul>"
        ]
        for g in data["graphics"]:
            out += [
                '<li data-intelligence-domain="'
                + esc(g["domain"])
                + '">'
                + esc(g["domain"])
                + " · "
                + esc(when(g["observed_at"]))
                + ' · <a href="'
                + esc(safe_source(g["image"]), quote=True)
                + '">Otwórz grafikę</a></li>'
            ]
        out += ["</ul>"]
    out += ["</section>"]
    return "".join(out)
