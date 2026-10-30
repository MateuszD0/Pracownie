"""Wait for an explicitly requested scan time; no recurring schedule or dependencies."""
from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

MAX_WAIT = timedelta(hours=2)
MAX_LATENESS = timedelta(minutes=10)


def seconds_until(start_at: str, now: datetime) -> float:
    target = datetime.fromisoformat(start_at)
    if target.utcoffset() is None or now.utcoffset() is None:
        raise ValueError("Podaj datę i godzinę ze strefą, np. 2026-10-30T09:00:00+01:00.")
    remaining = target.astimezone(UTC) - now.astimezone(UTC)
    if remaining > MAX_WAIT:
        raise ValueError("Jednorazowe oczekiwanie obsługuje terminy do dwóch godzin naprzód.")
    if remaining < -MAX_LATENESS:
        raise ValueError("Termin minął ponad 10 minut temu; ustaw nowy termin zamiast uruchamiać spóźniony skan.")
    return max(0.0, remaining.total_seconds())


def wait_until(start_at: str) -> None:
    remaining = seconds_until(start_at, datetime.now(UTC))
    local = datetime.fromisoformat(start_at).astimezone(ZoneInfo("Europe/Warsaw"))
    message = f"Pełny skan zaplanowany na {local:%Y-%m-%d %H:%M:%S %Z} (Europe/Warsaw)."
    print(message, flush=True)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a") as stream:
            stream.write(message + "\n\nPo oczekiwaniu osobne zadanie uruchomi pełny skan i opublikuje wynik w dashboardzie.\n")
    while remaining > 0:
        time.sleep(min(remaining, 60))
        remaining = seconds_until(start_at, datetime.now(UTC))
    print("Nadszedł termin — można uruchomić pełny skan.", flush=True)


if __name__ == "__main__":
    wait_until(os.environ["SCAN_START_AT"])
