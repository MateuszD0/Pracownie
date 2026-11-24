"""Cheap, read-only daily gate, executed inside the report writer's Actions lock."""
from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, time
from pathlib import Path
from time import sleep

import httpx

from .github import GitHubStore
from .model import WARSAW
from .readiness import repair_domains
from .timing import BACKUP_START, MISSING_REPORT_CUTOFF, PRIMARY_START

PRIMARY_CRON = "0 9 * * *"
RECOVERY_CRON = "30 10 * * *"
PREPARATION_CRONS = {"24 8 * * *": time(8, 24), "44 8 * * *": time(8, 44)}
STARTS = {**PREPARATION_CRONS, PRIMARY_CRON: PRIMARY_START, "7 9 * * *": time(9, 7),
          "17 9 * * *": time(9, 17), RECOVERY_CRON: BACKUP_START}

def daily_gate(expression: str, now: datetime, remote: GitHubStore) -> dict:
    if expression not in STARTS:
        raise ValueError("Nieznany harmonogram; nie pominięto skanu")
    if now.utcoffset() is None:
        raise ValueError("Harmonogram wymaga daty ze strefą czasową")
    local = now.astimezone(WARSAW)
    day = local.date().isoformat()
    planned = datetime.combine(local.date(), STARTS[expression], WARSAW)
    scan_time = max(STARTS[expression], PRIMARY_START)
    result = {"day": day, "run_scan": False, "late": local.time().replace(second=0, microsecond=0) > scan_time}
    if local < planned:
        return dict(result, reason="Właściwa pora uruchomienia w Europe/Warsaw jest jeszcze przed nami.")
    record = remote.published_report(day)
    if record and expression != RECOVERY_CRON:
        return dict(result, reason="Dzisiejszy raport jest już opublikowany.")
    if record and "readiness" not in record:
        return dict(result, run_scan=True, reason="Starszy manifest nie potwierdza świeżych odczytów; sprawdzam brakujący zakres.")
    if record and (retry := repair_domains(record.get("readiness", {}))):
        return dict(result, run_scan=True, repair_domains=retry, reason="Ponawiam brakujące lub częściowe odczyty; zachowuję wyniki pozostałych pracowni.")
    if record:
        return dict(result, reason="Dzisiejszy raport jest zapisany; brak błędów zakwalifikowanych do automatycznego ponowienia. Trwałe blokady pozostają widoczne w raporcie.")
    if expression in PREPARATION_CRONS and local.time() < PRIMARY_START:
        return dict(result, run_scan=True, wait_until_start=True,
                    reason="Przygotowuję skan. Odczyty ruszą po 09:00 czasu warszawskiego.")
    return dict(result, run_scan=True, reason="Brak zatwierdzonego dzisiejszego raportu. Uruchamiam pełny skan.")


def missing_report_gate(day: str, now: datetime, remote: GitHubStore) -> dict:
    if now.utcoffset() is None:
        raise ValueError("Harmonogram wymaga daty ze strefą czasową")
    local = now.astimezone(WARSAW)
    today = local.date().isoformat()
    result = {"day": today, "run_scan": False, "late": local.time() > PRIMARY_START}
    if day != today or not PRIMARY_START <= local.time() < MISSING_REPORT_CUTOFF:
        return dict(result, reason="Minęło okno odzyskania raportu dla wskazanego dnia.")
    if remote.published_report(day):
        return dict(result, reason="Dzisiejszy raport opublikowano w czasie oczekiwania na uruchomienie.")
    return dict(result, run_scan=True, reason="Odzyskuję brakujący dzisiejszy raport.")


def wait_for_scan(day: str) -> None:
    now = datetime.now(WARSAW)
    if day != now.date().isoformat():
        raise ValueError("Zmieniła się data skanu. Potrzebne jest uruchomienie dla bieżącego dnia.")
    target = datetime.combine(now.date(), PRIMARY_START, WARSAW)
    while now < target:
        sleep(min((target - now).total_seconds(), 60))
        now = datetime.now(WARSAW)


def main() -> None:
    if sys.argv[1:] == ["--wait"]:
        wait_for_scan(os.environ["SCAN_DAY"])
        return
    remote = GitHubStore(os.environ["GITHUB_REPOSITORY"], os.environ.get("GITHUB_TOKEN", ""))
    try:
        now = datetime.now(UTC)
        if day := os.environ.get("MISSING_REPORT_DAY"):
            result = missing_report_gate(day, now, remote)
        else:
            result = daily_gate(os.environ.get("SCHEDULE_EXPRESSION", ""), now, remote)
        message = f"{result['day']}: {result['reason']}"
        print(message)
        if result["late"] and result["run_scan"]:
            print("Planowany start skanu: 09:00 Europe/Warsaw; ponowienie: 10:30. Przygotowanie środowiska lub kolejka zakończyły się później; uruchamiam brakujący zakres teraz.")
        if output := os.environ.get("GITHUB_OUTPUT"):
            with Path(output).open("a") as stream:
                stream.write(f"run_scan={str(result['run_scan']).lower()}\nday={result['day']}\n")
                if result.get("wait_until_start"):
                    stream.write("wait_until_start=true\n")
                if result.get("repair_domains"):
                    stream.write("repair_domains=" + ",".join(result["repair_domains"]) + "\n")
        if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
            with Path(summary).open("a") as stream:
                stream.write(f"### Start skanu: 09:00 Europe/Warsaw\n\n{message}\n")
    except (ValueError, RuntimeError, OSError, httpx.HTTPError) as exc:
        # A failed read must fail visibly and leave the next attempt eligible.
        message = str(exc).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print("::error title=Kontrola gotowości raportu::" + message, file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        remote.close()


if __name__ == "__main__":
    main()
