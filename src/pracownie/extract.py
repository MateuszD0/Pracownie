from __future__ import annotations

import hashlib
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .model import Field, slug

MONEY = re.compile(r"(?<![\w.,])(\d{1,3}(?:[ \u00a0\u202f.]\d{3})+(?:[,.]\s*\d{1,2})?|\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:[,.]\s*\d{1,2})?)\s*(zł|PLN|EUR|€|USD|\$)(?!\w)", re.I)


def money_text(value: str) -> str:
    # WooCommerce can put the currency before the amount ("zł 499.00").
    return re.sub(r"(zł|PLN|EUR|€|USD|\$)\s*(\d+(?:[ \u00a0\u202f.,]\d+)*)(?!\w)", r"\2 \1", value, flags=re.I)
CATEGORIES = [
    ("promocje", r"promoc|rabat|gratis|kod\s|wyprzeda|najniższ|najniższ|oszczęd|przecen|bestseller"),
    ("dodatki", r"kosztorys|adaptac|konsultac|instalac|dodatk|zgod[ayę]\sna\szmian|bezpłat|za darmo"),
    ("pakiety", r"pakiet|dokumentac|egzemplarz|elektroniczn|papierow|zawiera|w cenie"),
    ("warunki", r"dostaw|wysył|dostępno|realizac|raty|płatno|zwrot|gwaranc|wsparci|termin"),
    ("funkcje", r"konfigur|kalkulator|personaliz|wybierz|porównaj|dopasuj|koszyk"),
    ("parametry", r"powierzch|technologi|garaż|lustrzan|\bm²\b|\bm2\b"),
    ("komunikacja", r"opini|poleca|kup teraz|zamów|najpopular|nowoś|nowy projekt|ofert|ostatni"),
]


def normalize(text: str, ignore_patterns: list[str] | None = None) -> str:
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ").replace("\u202f", " ")).strip()
    text = re.sub(r"\b\d{1,2}:\d{2}:\d{2}\b", "[licznik]", text)
    text = re.sub(r"\b\d+\s*(?:dni|days)\s*\[licznik\]", "[licznik]", text, flags=re.I)
    for pattern in ignore_patterns or []:
        text = re.sub(pattern, "[pominięto]", text)
    return text


def amount(value: str) -> str | None:
    text = re.sub(r"\s", "", value)
    if "." in text and "," in text:
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        return str(Decimal(text).quantize(Decimal("0.01")))
    except InvalidOperation:
        return None


def currency_code(value: str) -> str:
    return {"zł": "PLN", "€": "EUR", "$": "USD"}.get(value.casefold(), value.upper())


def category(text: str) -> str | None:
    lowered = text.lower()
    for name, pattern in CATEGORIES:
        if re.search(pattern, lowered):
            return name
    return "ceny" if MONEY.search(money_text(text)) else None


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_") and k not in {"fbclid", "gclid"}]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def is_listing_title(title: str) -> bool:
    pattern = r"^(projekty\b|wszystkie projekty|najnowsze projekty|polecane projekty|najpopularniejsze projekty|nasze projekty|nowo[śs]ci\b|nasz katalog|bestsell|top\s*\d+|hity\b|domy\s+(dla|do|z\b|parterowe|piętrowe|nowoczesne|energooszczędne)|z poddaszem|parterowe\b|piętrowe\b|logowanie\b|rejestracja\b|pompy ciepła|jak\s|dlaczego\s|poradnik\b|katalog\b|lista projektów)"
    return bool(re.search(pattern, normalize(title), re.I))


def page_identity(url: str) -> tuple:
    parts = urlsplit(canonical_url(url))
    return ((parts.hostname or "").removeprefix("www."), parts.path.rstrip("/"), parts.query)


def extract_fields(payload: dict, observed_at: str, ignore_patterns: list[str] | None = None) -> tuple[dict[str, Field], list[str]]:
    fields: dict[str, Field] = {}
    sections = list(dict.fromkeys(["oferta"] + [slug(x) for x in payload.get("sections", [])]))
    grouped: dict[tuple[str, str], list[str]] = {}
    for block in payload.get("blocks", []):
        text = normalize(block["text"], ignore_patterns)
        if re.search(r"cookies|ciastecz|danych osobowych|sales intelligence|digitree|zarządzaj zgod", text, re.I):
            continue
        group = category(text) or "tresc"
        if len(text) < 3:
            continue
        section = slug(block.get("heading", "oferta"))
        grouped.setdefault((section, group), [])
        if text not in grouped[(section, group)]:
            grouped[(section, group)].append(text)
    for (section, group), lines in grouped.items():
        fields[f"tekst:{section}:{group}"] = Field(
            label=f"{group.capitalize()} — {section}", value="\n".join(sorted(lines)),
            category=group, section=section, observed_at=observed_at,
        )
    price_keys: dict[str, int] = {}
    for entry in payload.get("prices", []):
        for match in MONEY.finditer(money_text(entry["text"])):
            label = normalize(money_text(entry.get("context") or entry["text"]), ignore_patterns)
            role = "poprzednia" if re.search(r"DEL|^S\b|old|regular|previous|line-through", entry.get("type", ""), re.I) else "widoczna"
            if "najniższa" in label.casefold() and len(MONEY.findall(label)) == 1:
                role = "najniższa z 30 dni"
            stable_label = MONEY.sub("[cena]", label)
            identifier = f"cena:{slug(stable_label)}:{role}"
            price_keys[identifier] = price_keys.get(identifier, 0) + 1
            if price_keys[identifier] > 1:
                identifier += f":{price_keys[identifier]}"
            currency = currency_code(match[2])
            fields[identifier] = Field(
                label=f"Cena {role}: {stable_label}", value=match[0], category="ceny", amount=amount(match[1]),
                currency=currency, section="oferta", observed_at=observed_at,
                source="dom", role="regular" if role == "poprzednia" else "lowest30" if role == "najniższa z 30 dni" else "current",
                primary=bool(entry.get("primary")),
            )
    for product in payload.get("products", []):
        offers = product.get("offers", [])
        if not isinstance(offers, list):
            offers = [offers]
        for index, offer in enumerate(offers):
            if not isinstance(offer, dict):
                continue
            label = str(offer.get("name") or product.get("name") or product.get("sku") or "podstawowy")
            identity = slug(str(offer.get("sku") or offer.get("name") or product.get("sku") or label))
            if index:
                identity += ":" + hashlib.sha256(str(offer.get("url", index)).encode()).hexdigest()[:8]
            for key, description in (("price", "cena"), ("lowPrice", "cena od"), ("highPrice", "cena do")):
                if offer.get(key) is not None:
                    currency = str(offer.get("priceCurrency", ""))
                    raw = str(offer[key])
                    fields[f"oferta:{identity}:{key}"] = Field(
                        label=f"{label} — {description}", value=f"{raw} {currency}".strip(), category="ceny",
                        amount=amount(raw), currency=currency or None, observed_at=observed_at,
                        source="jsonld", role={"price": "current", "lowPrice": "range_low", "highPrice": "range_high"}[key],
                        primary=payload.get("page") == "projekt" or len(payload.get("products", [])) == 1,
                    )
            for key in ("availability", "priceValidUntil", "shippingDetails", "hasMerchantReturnPolicy"):
                if offer.get(key):
                    fields[f"oferta:{identity}:{key}"] = Field(
                        label=f"{label} — {key}", value=str(offer[key]), category="warunki", observed_at=observed_at,
                    )
    meta = payload.get("meta_price")
    if meta and amount(str(meta.get("amount", ""))) is not None and meta.get("currency"):
        fields["meta:product-price"] = Field("Cena projektu", f"{meta['amount']} {meta['currency']}", "ceny", amount=amount(str(meta['amount'])), currency=currency_code(meta['currency']), observed_at=observed_at, source="meta", role="current", primary=True)
    for control in payload.get("controls", []):
        if control.get("scope", "offer") != "offer":
            continue
        label = normalize(control["label"], ignore_patterns)
        if not label or control["kind"] == "unknown" and not category(label):
            continue
        options = [normalize(o["label"]) for o in control.get("options", [])]
        key = "funkcja:" + slug(control.get("name") or label)
        fields[key] = Field(
            label=f"Opcja: {label}", value=label + (" | " + " | ".join(options) if options else ""),
            category="funkcje", observed_at=observed_at,
        )
    return fields, sections


def validate_payload(payload: dict, product: bool = False) -> None:
    text = payload.get("text", "")
    challenge = r"just a moment|access denied|attention required|verify you are human|sprawdź.*człowiekiem"
    if re.search(challenge, payload.get("title", ""), re.I) or len(text) < 80 and re.search(challenge, text, re.I):
        raise ValueError("Strona blokady lub weryfikacji zamiast oferty")
    if len(text) < 40:
        raise ValueError("Pusta lub niekompletna strona")
    if product:
        title = normalize(payload.get("h1") or payload.get("title", ""))
        if is_listing_title(title) or re.fullmatch(r"szukaj|wyszukiwarka|wyniki wyszukiwania|oferta|projekt indywidualny", title, re.I):
            raise ValueError("Adres prowadzi do kategorii, poradnika lub dodatku, a nie pojedynczego projektu")
        identity = payload.get('verified_project_identity', {})
        verified = bool(identity.get('selector') and identity.get('name') == title and identity.get('url') == payload.get('url'))
        if not (verified or payload.get("products") or title and re.search(r"powierzch|projekt domu|opis projektu|rzuty|kosztorys|do koszyka", text, re.I)):
            raise ValueError("Nie potwierdzono, że wybrany adres jest kartą projektu")
