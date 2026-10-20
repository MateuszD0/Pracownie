from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")
SCHEMA = 1


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def local_day(value: datetime | None = None) -> str:
    return (value or datetime.now(UTC)).astimezone(WARSAW).date().isoformat()


def slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.replace("ł", "l").replace("Ł", "L"))
    value = value.encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9.-]+", "-", value).strip("-.")[:100] or "element"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def safe_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError(f"Niebezpieczna ścieżka: {relative!r}")
    return path


@dataclass
class Field:
    label: str
    value: str
    category: str
    section: str = "oferta"
    amount: str | None = None
    currency: str | None = None
    observed_at: str = ""
    source: str = ""
    role: str = ""
    primary: bool = False
    tax: str = ""
    unit: str = ""


@dataclass
class Snapshot:
    domain: str
    page: str
    scenario: str
    url: str
    observed_at: str
    title: str
    fields: dict[str, Field]
    sections: list[str]
    image: str
    renderer: str
    warnings: list[str] = field(default_factory=list)
    quality: str = "ok"
    contract: str = ""
    document: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.domain}/{self.page}/{self.scenario}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Snapshot:
        values = dict(data)
        values["fields"] = {key: Field(**value) for key, value in values["fields"].items()}
        return cls(**values)


@dataclass
class Change:
    kind: str
    category: str
    label: str
    before: str | None
    after: str | None
    before_at: str | None
    after_at: str
    url: str
    scenario: str
    delta: str | None = None
    percent: str | None = None
    evidence: dict[str, str] = field(default_factory=dict)
    note: str = ""
    field_key: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class Result:
    domain: str
    page: str
    scenario: str
    status: str
    url: str
    changes: list[Change] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    observed_at: str | None = None
    evidence: dict[str, str] = field(default_factory=dict)
    data_quality: str = "unknown"
    scenario_label: str = ""
    offer: dict = field(default_factory=dict)
    before_offer: dict = field(default_factory=dict)
    compared_at: str | None = None
    variant: str = ""
    communication: dict = field(default_factory=dict)


@dataclass
class Scenario:
    id: str
    label: str
    actions: list[dict] = field(default_factory=list)
    required: list[str] = field(default_factory=list)
    page: str = "projekt"


@dataclass
class Site:
    domain: str
    home_url: str
    project_url: str | None = None
    project_name: str | None = None
    selection: dict = field(default_factory=dict)
    required: dict[str, list[str]] = field(default_factory=dict)
    scenarios: list[Scenario] = field(default_factory=list)
    masks: list[str] = field(default_factory=list)
    ignore_patterns: list[str] = field(default_factory=list)
    allowed_hosts: list[str] = field(default_factory=list)
    discovery_links: list[str] = field(default_factory=list)
    field_selectors: list[dict] = field(default_factory=list)
    unreliable_price_keys: list[str] = field(default_factory=list)
    product_url_pattern: str | None = None
    ignore_resource_hosts: list[str] = field(default_factory=list)
    inspection: str = "pending"
    communication_ignore_selectors: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> Site:
        data = dict(data)
        data["scenarios"] = [Scenario(**item) for item in data.get("scenarios", [])]
        return cls(**data)


def load_sites(path: Path) -> list[Site]:
    data = json.loads(path.read_text())
    sites = [Site.from_dict(item) for item in data["sites"]]
    domains = [site.domain for site in sites]
    if len(set(domains)) != len(domains):
        raise ValueError("Powtórzone domeny w konfiguracji")
    for domain in domains:
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", domain):
            raise ValueError("Niepoprawny identyfikator domeny")
    return sites
