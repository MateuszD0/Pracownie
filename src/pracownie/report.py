from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .extract import is_listing_title
from .model import WARSAW, Change, Result, Site, digest, json_bytes, safe_path
from .presentation import build_view, render_csv, render_html, render_markdown, render_text
from .state import atomic_write

STATUS = {
    "baseline": "punkt odniesienia", "changed": "zmiany", "unchanged": "bez zmian",
    "partial": "częściowe sprawdzenie", "error": "błąd odczytu", "review": "wymaga oceny",
    "unavailable": "niedostępna funkcja",
}
CATEGORY = {"ceny": "CENY", "promocje": "PROMOCJE", "dodatki": "DODATKI", "pakiety": "PAKIETY", "warunki": "WARUNKI", "funkcje": "FUNKCJONALNOŚCI", "parametry": "PARAMETRY", "komunikacja": "KOMUNIKACJA", "obraz": "OBRAZ"}
COVERAGE_STATUS = {"complete": "pełny", "partial": "częściowy", "error": "błąd"}
CHANGE_STATUS = {"added": "dodano", "removed": "usunięto", "changed": "zmieniono", "review": "wymaga oceny"}


def display_time(value: str | None) -> str:
    return datetime.fromisoformat(value).astimezone(WARSAW).strftime("%Y-%m-%d %H:%M:%S %Z") if value else "brak wcześniejszego odczytu"


def coverage(results: list[Result], domains: list[str]) -> dict:
    output = {}
    for domain in domains:
        entries = [r for r in results if r.domain == domain]
        successes = [r for r in entries if r.observed_at]
        missing = [r for r in entries if r.status in {"error", "unavailable", "partial", "review"} or r.warnings]
        status = "error" if not successes else "partial" if missing else "complete"
        output[domain] = {
            "status": status,
            "scenarios": [{"page": r.page, "scenario": r.scenario, "status": r.status, "url": r.url,
                           "warnings": r.warnings, "error": r.error} for r in entries],
        }
    return output


def render_diagnostics(day: str, results: list[Result], metadata: dict, selections: dict, domains: list[str]) -> str:
    covered = coverage(results, domains)
    counts = Counter(item["status"] for item in covered.values())
    total_changes = sum(len(r.changes) for r in results)
    end = datetime.fromisoformat(metadata["finished_at"]).astimezone(WARSAW)
    deadline = datetime.fromisoformat(day + "T08:00:00").replace(tzinfo=WARSAW)
    lines = [
        f"MONITORING PRACOWNI — {day}",
        f"Rozpoczęcie: {display_time(metadata['started_at'])}",
        f"Zakończenie skanowania: {display_time(metadata['finished_at'])}",
        f"Raport: {'kompletny' if counts['complete'] == len(domains) else 'częściowy'}",
        f"Domeny: {len(domains)}; w pełni: {counts['complete']}; częściowo: {counts['partial']}; błędy: {counts['error']}",
        f"Liczba różnic i obserwacji wymagających oceny: {total_changes}",
        f"Czas przebiegu: {metadata['elapsed_seconds']:.1f} s (bez instalacji i publikacji GitHub)",
        f"Obrazy w archiwum dnia: {metadata.get('evidence_bytes', 0)} B; bieżące obrazy stanu: {metadata.get('snapshot_bytes', 0)} B.",
        "Cel gotowości: 08:00 Europe/Warsaw. " + ("Skan zakończono po celu." if end > deadline else "Skan zakończono przed celem; publikacja może zakończyć się później."),
        "Porównanie: ostatni poprawny odczyt danego scenariusza sprzed dnia raportu.",
        "UWAGA: brak zmian dotyczy wyłącznie poprawnie odczytanego zakresu. Skan raz dziennie nie wykrywa zmian pomiędzy skanami.",
        "", "NAJWAŻNIEJSZE ZMIANY", "",
    ]
    if metadata.get("reused_domains"):
        lines.insert(10, f"Tryb naprawczy: wykorzystano poprawne odczyty {len(metadata['reused_domains'])} domen z tego samego dnia; przy wpisach podano ich rzeczywiste godziny.")
    for correction in metadata.get("selection_corrections", []):
        lines.insert(10, f"Korekta początkowego wyboru ({correction['domain']}): {correction['reason']} Punkt odniesienia karty utworzono ponownie.")
    highlights = []
    for result in results:
        for change in result.changes:
            if change.category not in {"ceny", "promocje", "dodatki", "pakiety"}:
                continue
            prefix = "DO OCENY: " if change.kind == "review" else ""
            if change.delta is not None:
                delta = float(change.delta)
                if delta == 0:
                    detail = "bez zmiany wartości kwoty"
                else:
                    direction = "spadek" if delta < 0 else "wzrost"
                    detail = f"{direction} o {abs(delta):.2f} ({change.percent or '—'}%)"
                highlights.append(f"{prefix}{result.domain}: {change.label}: {change.before} → {change.after}; {detail}.")
            else:
                highlights.append(f"{prefix}{result.domain}: {change.label} — szczegóły poniżej.")
    lines.extend(list(dict.fromkeys(highlights))[:30] or ["Brak potwierdzonych zmian w najważniejszych kategoriach."])
    lines.extend(["", "SZCZEGÓŁY WEDŁUG DOMEN", ""])
    for domain in domains:
        lines.extend(["=" * 72, f"DOMENA: {domain} | zakres: {COVERAGE_STATUS[covered[domain]['status']]}"])
        selection = selections.get(domain)
        if selection:
            lines.extend([f"PROJEKT: {selection.get('name', '')}", f"WYBÓR: {selection.get('basis', '')}", f"ŹRÓDŁO WYBORU: {selection.get('source', '')}"])
        for result in [r for r in results if r.domain == domain]:
            lines.extend(["", f"STRONA: {result.page} | SCENARIUSZ: {result.scenario}", f"STATUS: {STATUS.get(result.status, result.status)}", f"ADRES: {result.url}"])
            if result.observed_at:
                lines.append(f"ODCZYT: {display_time(result.observed_at)}")
            if result.error:
                lines.append(f"BŁĄD: {result.error}")
            for warning in dict.fromkeys(result.warnings):
                lines.append(f"OGRANICZENIE: {warning}")
            for change in result.changes:
                lines.extend([
                    f"  [{CATEGORY.get(change.category, change.category)}] {change.label}",
                    f"  OCENA: {CHANGE_STATUS.get(change.kind, change.kind)}",
                    f"  PORÓWNANIE: {display_time(change.before_at)} → {display_time(change.after_at)}",
                    f"  PRZED: {change.before if change.before is not None else '(brak)'}",
                    f"  PO: {change.after if change.after is not None else '(nie odnaleziono)'}",
                ])
                if change.delta is not None:
                    lines.append(f"  RÓŻNICA CENY: {change.delta}; procentowo: {change.percent or 'nie obliczono'}%")
                if change.note:
                    lines.append(f"  UWAGA: {change.note}")
            if result.evidence:
                lines.append("DOWODY:")
                lines.extend(f"  {kind}: {path}" for kind, path in result.evidence.items())
    unchanged = [r for r in results if r.status == "unchanged" and not r.warnings]
    problems = [r for r in results if r.status in {"partial", "error", "review", "unavailable"} or r.warnings]
    lines.extend(["", "POPRAWNIE SPRAWDZONE SCENARIUSZE BEZ ZMIAN"])
    lines.extend([f"{r.domain} / {r.page} / {r.scenario}" for r in unchanged] or ["Brak."])
    lines.extend(["", "BŁĘDY I NIEPEŁNY ZAKRES"])
    lines.extend([f"{r.domain} / {r.page} / {r.scenario}: {r.error or '; '.join(r.warnings) or STATUS.get(r.status, r.status)}" for r in problems] or ["Brak."])
    return "\n".join(lines) + "\n"


def render_report(day: str, results: list[Result], metadata: dict, selections: dict, domains: list[str]) -> str:
    return render_text(build_view(day, results, metadata, selections, domains))


def write_outputs(staging: Path, day: str, results: list[Result], metadata: dict, selections: dict, domains: list[str]) -> Path:
    directory = staging / day
    directory.mkdir(parents=True, exist_ok=True)
    atomic_write(directory / "zmiany.json", json_bytes({"schema": 1, "metadata": metadata, "results": [asdict(r) for r in results]}))
    atomic_write(directory / "pokrycie.json", json_bytes(coverage(results, domains)))
    atomic_write(directory / "wybrane-projekty.json", json_bytes(selections))
    report = staging / f"{day}.txt"
    view = build_view(day, results, metadata, selections, domains)
    atomic_write(report, render_text(view).encode())
    atomic_write(directory / "index.html", render_html(view).encode())
    atomic_write(directory / "oferty.json", json_bytes(view))
    atomic_write(directory / "oferty.csv", render_csv(view).encode())
    atomic_write(directory / "podsumowanie.md", render_markdown(view).encode())
    atomic_write(directory / "diagnostyka.txt", render_diagnostics(day, results, metadata, selections, domains).encode())
    files = [report, *sorted(p for p in directory.rglob("*") if p.is_file() and p != directory / "manifest.json")]
    manifest = {"schema": 1, "owner": "pracownie-monitor:v1", "run_id": metadata["run_id"], "day": day, "files": {
        p.relative_to(staging).as_posix(): {"sha256": digest(p), "bytes": p.stat().st_size} for p in files
    }}
    atomic_write(directory / "manifest.json", json_bytes(manifest))
    return report


def verify_outputs(root: Path, day: str):
    from .model import safe_path
    manifest = json.loads((root / day / "manifest.json").read_text())
    for name, record in manifest["files"].items():
        if digest(safe_path(root, name)) != record["sha256"]:
            raise ValueError(f"Uszkodzony wynik: {name}")


def install_outputs(staging: Path, destination: Path, day: str, run_id: str):
    destination.mkdir(parents=True, exist_ok=True)
    previous = destination / f".previous-{run_id}"
    current = destination / day
    if current.exists():
        manifest_path = current / "manifest.json"
        if not manifest_path.is_file() or json.loads(manifest_path.read_text()).get("owner") != "pracownie-monitor:v1":
            raise ValueError("Istniejący folder dnia nie jest oznaczony jako wynik monitora; wybierz osobny --output")
        verify_outputs(destination, day)
        owned_files = set(json.loads(manifest_path.read_text())["files"]) | {f"{day}/manifest.json"}
        if any(p.relative_to(destination).as_posix() not in owned_files for p in current.rglob("*") if p.is_file()):
            raise ValueError("Folder raportu zawiera dodane pliki użytkownika; nie zastąpiono go")
        current.rename(previous)
    elif (destination / f"{day}.txt").exists():
        raise ValueError("Plik TXT dnia już istnieje bez własnego manifestu; nie nadpisano go")
    try:
        (staging / day).rename(current)
        atomic_write(destination / f"{day}.txt", (staging / f"{day}.txt").read_bytes())
    except BaseException:
        if previous.exists():
            if current.exists():
                shutil.rmtree(current)
            previous.rename(current)
        raise
    if previous.exists():
        shutil.rmtree(previous)


def bundle_report(root: Path, day: str, destination: Path):
    verify_outputs(root, day)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in [root / f"{day}.txt", *sorted(p for p in (root / day).rglob("*") if p.is_file())]:
            archive.write(path, "raporty/" + path.relative_to(root).as_posix())


def restore_report(archive_path: Path, destination: Path, day: str, expected_run: str):
    """Restore only a verified report bound to the committed state record."""
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination) as temporary:
        staging = Path(temporary)
        with zipfile.ZipFile(archive_path) as archive:
            if sum(info.file_size for info in archive.infolist()) > 1_500_000_000:
                raise ValueError("Archiwum raportu jest zbyt duże")
            if len(archive.namelist()) != len(set(archive.namelist())):
                raise ValueError("Powtórzone ścieżki w raporcie")
            for info in archive.infolist():
                if not info.filename.startswith("raporty/"):
                    raise ValueError("Nieoczekiwany katalog w archiwum raportu")
                relative = info.filename.removeprefix("raporty/")
                if not relative and info.is_dir():
                    continue
                target = safe_path(staging, relative)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Dowiązania w raporcie są niedozwolone")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as stream:
                    shutil.copyfileobj(source, stream)
        verify_outputs(staging, day)
        manifest_path = staging / day / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        if manifest["run_id"] != expected_run or manifest["day"] != day:
            raise ValueError("Raport nie odpowiada zatwierdzonemu stanowi")
        allowed = set(manifest["files"]) | {f"{day}/manifest.json"}
        if any(p.relative_to(staging).as_posix() not in allowed for p in staging.rglob("*") if p.is_file()):
            raise ValueError("Archiwum zawiera pliki spoza manifestu")
        # Earlier v1 archives had no owner field. Their ownership is proven by the
        # owned release, committed asset ID, run ID and verified per-file hashes.
        manifest["owner"] = "pracownie-monitor:v1"
        atomic_write(manifest_path, json_bytes(manifest))
        install_outputs(staging, destination, day, "restore")


def resume_data(root: Path, day: str, sites: list[Site], state: dict, repair_domains: list[str] | None = None) -> tuple[set[str], list[Result], dict]:
    path = root / day / "zmiany.json"
    if state.get("day") != day or not path.is_file():
        return set(), [], {}
    verify_outputs(root, day)
    data = json.loads(path.read_text())
    if data.get("schema") != 1:
        raise ValueError("Nieobsługiwana wersja raportu do wznowienia")
    results = []
    for entry in data["results"]:
        entry = dict(entry)
        entry["changes"] = [Change(**change) for change in entry["changes"]]
        results.append(Result(**entry))
    if {r.domain for r in results} != {s.domain for s in sites}:
        raise ValueError("Istniejący raport ma inny zakres domen; wybierz osobny --output")
    if repair_domains:
        if set(repair_domains) - {s.domain for s in sites}:
            raise ValueError("Nieznane domeny do naprawy")
        retained = {s.domain for s in sites} - set(repair_domains)
        # Preserve earlier observations AND their errors verbatim. They are not
        # relabeled as successful just because another domain is repaired.
        return retained, [r for r in results if r.domain in retained], data["metadata"]
    completed = set()
    for site in sites:
        if is_listing_title(state["selections"].get(site.domain, {}).get("name", "")):
            continue
        rows = [r for r in results if r.domain == site.domain]
        if any(r.error for r in rows):
            continue
        observed = [r for r in rows if r.observed_at]
        if any(r.data_quality == "unknown" for r in observed):
            # Old reports did not preserve typed quotes for the offers table.
            continue
        pages = {r.page for r in observed if r.scenario == "podstawowy"}
        if not {"glowna", "projekt"} <= pages:
            continue
        if site.project_url and state["selections"].get(site.domain, {}).get("url") != site.project_url:
            continue
        if any(f"{site.domain}/{scenario.page}/{scenario.id}" not in state["snapshots"] for scenario in site.scenarios):
            continue
        if any("adapter:" + rule["key"] not in state["snapshots"].get(f"{site.domain}/{rule.get('page', 'projekt')}/podstawowy", {}).get("fields", {}) for rule in site.field_selectors):
            continue
        valid = all(state["snapshots"].get(f"{r.domain}/{r.page}/{r.scenario}", {}).get("observed_at") == r.observed_at for r in observed)
        if valid:
            completed.add(site.domain)
    return completed, [r for r in results if r.domain in completed], data["metadata"]
