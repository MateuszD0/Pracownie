from __future__ import annotations

import json
import shutil
import zipfile
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .model import WARSAW, Result, digest, json_bytes
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


def render_report(day: str, results: list[Result], metadata: dict, selections: dict, domains: list[str]) -> str:
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
        "Cel gotowości: 08:00 Europe/Warsaw. " + ("Skan zakończono po celu." if end > deadline else "Skan zakończono przed celem; publikacja może zakończyć się później."),
        "Porównanie: ostatni poprawny odczyt danego scenariusza sprzed dnia raportu.",
        "UWAGA: brak zmian dotyczy wyłącznie poprawnie odczytanego zakresu. Skan raz dziennie nie wykrywa zmian pomiędzy skanami.",
        "", "NAJWAŻNIEJSZE ZMIANY", "",
    ]
    highlights = []
    for result in results:
        for change in result.changes:
            if change.category not in {"ceny", "promocje", "dodatki", "pakiety"}:
                continue
            if change.delta is not None:
                delta = float(change.delta)
                direction = "spadek" if delta < 0 else "wzrost"
                highlights.append(f"{result.domain}: {change.label}: {change.before} → {change.after}; {direction} o {abs(delta):.2f} ({change.percent or '—'}%).")
            else:
                highlights.append(f"{result.domain}: {change.label} — szczegóły poniżej.")
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


def write_outputs(staging: Path, day: str, results: list[Result], metadata: dict, selections: dict, domains: list[str]) -> Path:
    directory = staging / day
    directory.mkdir(parents=True, exist_ok=True)
    atomic_write(directory / "zmiany.json", json_bytes({"schema": 1, "metadata": metadata, "results": [asdict(r) for r in results]}))
    atomic_write(directory / "pokrycie.json", json_bytes(coverage(results, domains)))
    atomic_write(directory / "wybrane-projekty.json", json_bytes(selections))
    report = staging / f"{day}.txt"
    atomic_write(report, render_report(day, results, metadata, selections, domains).encode())
    files = [report, *sorted(p for p in directory.rglob("*") if p.is_file())]
    manifest = {"schema": 1, "run_id": metadata["run_id"], "day": day, "files": {
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
        current.rename(previous)
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
