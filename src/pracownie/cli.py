from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

from .github import GitHubStore
from .model import load_sites, local_day
from .pipeline import RunOptions, run_scan
from .report import bundle_report, coverage, verify_outputs
from .state import StateStore


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Monitoring ofert pracowni projektowych")
    commands = result.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Wykonaj skan i raport")
    run.add_argument("--config", type=Path, default=Path("config/sites.json"))
    run.add_argument("--state-dir", type=Path, default=Path(".monitor"))
    run.add_argument("--output", type=Path, default=Path("raporty"))
    run.add_argument("--day", default="", help="Data YYYY-MM-DD, domyślnie dziś w Warszawie")
    run.add_argument("--scope", choices=["full", "pilot"], default="full")
    run.add_argument("--domains", help="Lista domen oddzielona przecinkami")
    run.add_argument("--concurrency", type=int, default=3)
    run.add_argument("--domain-timeout", type=float, default=150)
    run.add_argument("--budget-seconds", type=float, default=1800)
    run.add_argument("--navigation-timeout", type=int, default=25000)
    run.add_argument("--settle-ms", type=int, default=500)
    run.add_argument("--max-scenarios", type=int, default=30)
    run.add_argument("--retries", type=int, default=1)
    run.add_argument("--browser-executable")
    run.add_argument("--no-ocr", action="store_true")
    run.add_argument("--github", action="store_true", help="Pobierz stan i zapisz wyniki w GitHub Releases")
    run.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "MateuszD0/Pracownie"))
    run.add_argument("--namespace", default="monitor")
    verify = commands.add_parser("verify", help="Zweryfikuj sumy kontrolne lokalnego raportu")
    verify.add_argument("--output", type=Path, default=Path("raporty"))
    verify.add_argument("--day", default=local_day())
    doctor = commands.add_parser("doctor", help="Sprawdź konfigurację i dostęp GitHub, bez zapisu")
    doctor.add_argument("--config", type=Path, default=Path("config/sites.json"))
    doctor.add_argument("--github", action="store_true")
    doctor.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "MateuszD0/Pracownie"))
    cleanup = commands.add_parser("cleanup", help="Lista/usunięcie własnych wydań starszych niż 180 dni")
    cleanup.add_argument("--day", default=local_day())
    cleanup.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "MateuszD0/Pracownie"))
    cleanup.add_argument("--namespace", default="monitor")
    cleanup.add_argument("--apply", action="store_true")
    return result


def token() -> str:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""


def execute(args) -> int:
    if args.command == "verify":
        verify_outputs(args.output, args.day)
        print("Sumy kontrolne raportu poprawne.")
        return 0
    if args.command == "cleanup":
        remote = GitHubStore(args.repository, token(), args.namespace)
        try:
            print(json.dumps(remote.cleanup(args.day, dry_run=not args.apply), ensure_ascii=False, indent=2))
        finally:
            remote.close()
        return 0
    sites = load_sites(args.config)
    if args.command == "doctor":
        print(f"Konfiguracja: {len(sites)} unikalnych domen; adaptery po inspekcji: {sum(s.inspection == 'verified' for s in sites)}")
        print("Token GitHub: " + ("obecny" if token() else "brak"))
        if args.github:
            remote = GitHubStore(args.repository, token())
            try:
                print(json.dumps(remote.preflight(), ensure_ascii=False))
            finally:
                remote.close()
        return 0
    config = json.loads(args.config.read_text())
    namespace = args.namespace
    if args.scope == "pilot":
        selected = set(config.get("pilot", []))
        if not selected:
            raise ValueError("Brak listy pilot w konfiguracji")
        sites = [s for s in sites if s.domain in selected]
        if namespace == "monitor":
            namespace = "monitor-pilot"
        # A pilot must not alter production local state either.
        args.state_dir = args.state_dir / "pilot"
    if args.domains:
        selected = set(args.domains.split(","))
        unknown = selected - {s.domain for s in sites}
        if unknown:
            raise ValueError("Nieznane domeny: " + ", ".join(sorted(unknown)))
        sites = [s for s in sites if s.domain in selected]
        if args.github and namespace == "monitor":
            raise ValueError("Podzbiór domen wymaga osobnego --namespace, aby nie nadpisać pełnego raportu")
    if not sites:
        raise ValueError("Wybrano zero domen")
    if not 1 <= args.concurrency <= 8 or args.domain_timeout <= 0 or args.budget_seconds <= 0 or args.max_scenarios < 1 or args.retries < 0:
        raise ValueError("Niepoprawne limity skanu")
    options = RunOptions(
        day=args.day, concurrency=args.concurrency, domain_timeout=args.domain_timeout,
        budget_seconds=args.budget_seconds, max_scenarios=args.max_scenarios,
        retries=args.retries, browser_executable=args.browser_executable,
        navigation_timeout=args.navigation_timeout, settle_ms=args.settle_ms, ocr=not args.no_ocr,
    )
    store = StateStore(args.state_dir)
    remote = None
    try:
        with store.lock():
            if args.github:
                remote = GitHubStore(args.repository, token(), namespace)
                print(json.dumps(remote.preflight(), ensure_ascii=False))
                record = remote.pull(store)
                if record is None and store.read()["snapshots"]:
                    raise ValueError("Brak zdalnego stanu, a katalog lokalny zawiera historię; użyj czystego katalogu do pierwszego uruchomienia GitHub")
            outcome = asyncio.run(run_scan(sites, store, args.output, options))
            metadata = outcome["metadata"]
            day = metadata["day"]
            archive = args.output / f"{day}.zip"
            bundle_report(args.output, day, archive)
            print(f"Raport: {args.output / (day + '.txt')}; archiwum: {archive.stat().st_size} B")
            covered = coverage(outcome["results"], [s.domain for s in sites])
            counts = {status: sum(item["status"] == status for item in covered.values()) for status in ["complete", "partial", "error"]}
            print(json.dumps({"coverage": counts, "elapsed_seconds": metadata["elapsed_seconds"], "snapshot_bytes": metadata["snapshot_bytes"]}, ensure_ascii=False))
            if remote:
                published = remote.publish(store, args.output, day, archive, metadata["run_id"])
                print(json.dumps(published, ensure_ascii=False))
                remote.cleanup(day, dry_run=False)
                summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
                if summary_path:
                    with Path(summary_path).open("a") as stream:
                        stream.write(f"### Raport {day}\n\n[Wyniki]({published['report_url']})\n\nPokrycie: {counts}\n\nPublikacja: {published['published_at']}\n")
            # All errors fail the job after saving diagnostics; partial coverage is explicitly reported.
            if counts["error"] == len(sites):
                return 2
            return 0
    finally:
        if remote:
            remote.close()


def main():
    args = parser().parse_args()
    try:
        code = execute(args)
    except (ValueError, RuntimeError, OSError, httpx.HTTPError) as exc:
        message = str(exc)
        print("BŁĄD: " + message, file=sys.stderr)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print("::error title=Pracownie Monitor::" + escaped, file=sys.stderr)
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()
