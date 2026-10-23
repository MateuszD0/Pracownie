"""Cheap, read-only daily gate, executed inside the report writer's Actions lock."""
from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, time
from pathlib import Path

import httpx

from .github import GitHubStore
from .model import WARSAW
from .readiness import repair_domains

PRIMARY_CRON = "17 2,3 * * *"
RECOVERY_CRON = "7 3,4 * * *"
PRIMARY_START = time(4, 17)
STARTS = {PRIMARY_CRON: PRIMARY_START, RECOVERY_CRON: time(5, 7)}


def daily_gate(expression: str, now: datetime, remote: GitHubStore) -> dict:
    if expression not in STARTS:
        raise ValueError("Nieznany harmonogram; nie pominięto skanu")
    if now.utcoffset() is None:
        raise ValueError("Harmonogram wymaga daty ze strefą czasową")
    local = now.astimezone(WARSAW)
    day = local.date().isoformat()
    result = {"day": day, "run_scan": False, "late": local.time() >= time(8)}
    if local.time() < STARTS[expression]:
        return dict(result, reason="Wywołanie UTC przed polską porą startu; właściwy termin jest jeszcze przed nami.")
    record = remote.published_report(day)
    if record and "readiness" not in record:
        return dict(result, run_scan=True, reason="Starszy manifest nie potwierdza świeżych odczytów; sprawdzam brakujący zakres.")
    if record and (retry := repair_domains(record.get("readiness", {}))):
        return dict(result, run_scan=True, repair_domains=retry, reason="Ponawiam brakujące lub częściowe odczyty; zachowuję wyniki pozostałych pracowni.")
    if record:
        return dict(result, reason="Dzisiejszy raport jest zapisany; brak błędów zakwalifikowanych do automatycznego ponowienia. Trwałe blokady pozostają widoczne w raporcie.")
    return dict(result, run_scan=True, reason="Brak zatwierdzonego dzisiejszego raportu. Uruchamiam pełny skan.")


def main() -> None:
    remote = GitHubStore(os.environ["GITHUB_REPOSITORY"], os.environ.get("GITHUB_TOKEN", ""))
    try:
        result = daily_gate(os.environ.get("SCHEDULE_EXPRESSION", ""), datetime.now(UTC), remote)
        message = f"{result['day']}: {result['reason']}"
        print(message)
        if result["late"] and result["run_scan"]:
            print("::warning title=Raport po terminie::Brak dzisiejszego raportu na 08:00 Europe/Warsaw; uruchamiam go teraz.")
        if output := os.environ.get("GITHUB_OUTPUT"):
            with Path(output).open("a") as stream:
                stream.write(f"run_scan={str(result['run_scan']).lower()}\nday={result['day']}\n")
                if result.get("repair_domains"):
                    stream.write("repair_domains=" + ",".join(result["repair_domains"]) + "\n")
        if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
            with Path(summary).open("a") as stream:
                stream.write(f"### Gotowość raportu na 08:00 Europe/Warsaw\n\n{message}\n")
    except (ValueError, RuntimeError, OSError, httpx.HTTPError) as exc:
        # A failed read must fail visibly and leave the next attempt eligible.
        message = str(exc).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print("::error title=Kontrola gotowości raportu::" + message, file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        remote.close()


if __name__ == "__main__":
    main()
