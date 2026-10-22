"""Recover missed Actions events without duplicating producers or daily mail."""
from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime, time
from pathlib import Path

import httpx

from .github import GitHubStore
from .mailer import receipt
from .model import WARSAW

RECOVERY_TITLE = 'Automatyczna naprawa odczytów'
ACTIVE = {'queued', 'in_progress', 'waiting', 'pending', 'requested'}


def runs(remote: GitHubStore, workflow: str) -> list[dict]:
    return remote.request('GET', f'{remote.prefix}/actions/workflows/{workflow}/runs',
                          params={'per_page': 100, 'branch': 'main'}).json()['workflow_runs']


def producer_running(remote: GitHubStore, records: list[dict], producer: str) -> bool:
    for run in records:
        if run['status'] not in ACTIVE:
            continue
        jobs = remote.request('GET', f"{remote.prefix}/actions/runs/{run['id']}/jobs",
                              params={'per_page': 100}).json()['jobs']
        if not jobs or any(j['name'] == producer and j['status'] in ACTIVE for j in jobs):
            return True
    return False


def same_day(run: dict, day: str) -> bool:
    return datetime.fromisoformat(run['created_at'].replace('Z', '+00:00')).astimezone(WARSAW).date().isoformat() == day


def dispatch(remote: GitHubStore, workflow: str, inputs: dict, dry_run: bool):
    if not dry_run:
        remote.request('POST', f'{remote.prefix}/actions/workflows/{workflow}/dispatches',
                       json={'ref': 'main', 'inputs': inputs})


def recover(remote: GitHubStore, now: datetime, email_configured: bool, *, dry_run=False, max_auto_scans=2) -> dict:
    if now.utcoffset() is None:
        raise ValueError('Kontrola wymaga daty ze strefą czasową.')
    local = now.astimezone(WARSAW)
    day = local.date().isoformat()

    def result(action, reason, **extra):
        return dict(day=day, action=action, reason=reason, dry_run=dry_run, **extra)

    if local.time() < time(5, 17):
        return result('early', 'Przed polską godziną startu skanu.')
    scans = runs(remote, 'monitor.yml')
    rebuilds = runs(remote, 'rebuild-report.yml')
    if producer_running(remote, scans, 'scan') or producer_running(remote, rebuilds, 'rebuild'):
        return result('busy', 'Skan lub publikacja już trwa; nie uruchomiono drugiej kopii.')
    record = remote.published_report(day)
    retry = (record or {}).get('readiness', {}).get('retry_domains', [])
    needs_scan = not record or not record.get('readiness', {}).get('expected') or bool(retry)
    automatic = sum(r.get('display_title') == RECOVERY_TITLE and same_day(r, day) for r in scans)
    if needs_scan and local.time() < time(12) and automatic < max_auto_scans:
        inputs = {'scope': 'full', 'rescan': 'false', 'automatic_recovery': 'true'}
        if record and retry:
            inputs['repair_domains'] = ','.join(retry)
        dispatch(remote, 'monitor.yml', inputs, dry_run)
        return result('scan-dispatched', 'Nadrabiam brakujący raport lub odczyty; zachowuję poprawne wyniki.',
                      repair_domains=retry, automatic_attempt=automatic + 1)
    if not record:
        return result('report-missing', 'Nie ma dzisiejszego raportu; limit prób naprawczych lub poranne okno zostały wyczerpane.')
    if not email_configured:
        return result('mail-unconfigured', 'Raport jest dostępny. Wysyłka wymaga sekretów REPORT_EMAIL_TO i SMTP_PASSWORD.',
                      scan_retries_exhausted=needs_scan and automatic >= max_auto_scans)
    release = remote.release(f'{remote.namespace}-report-{day}')
    if not release:
        raise ValueError('Zatwierdzony raport nie ma wydania.')
    assets = {a['name']: a for a in remote.assets(release)}
    sent, pending = f'email-{day}-sent.json', f'email-{day}-pending.json'
    if sent in assets:
        if receipt(remote, assets[sent], day).get('status') != 'sent':
            raise ValueError('Niepoprawne potwierdzenie wysyłki.')
        return result('done', 'Dzisiejszy raport został już wysłany; pominięto duplikat.')
    if pending in assets:
        receipt(remote, assets[pending], day)
        return result('mail-uncertain', 'Wysyłka nie ma końcowego potwierdzenia; sprawdź skrzynkę przed ponowieniem.')
    if producer_running(remote, runs(remote, 'email.yml'), 'email'):
        return result('mail-busy', 'Wysyłka poczty już trwa.')
    dispatch(remote, 'email.yml', {'day': day}, dry_run)
    return result('mail-dispatched', 'Zlecono wysyłkę dzisiejszego raportu. Potwierdzenie SMTP pojawi się w zadaniu poczty.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    remote = GitHubStore(os.environ['GITHUB_REPOSITORY'], os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN', ''))
    try:
        result = recover(remote, datetime.now(UTC), os.environ.get('EMAIL_CONFIGURED', '').lower() == 'true', dry_run=args.dry_run)
        message = f"{result['day']}: {result['reason']}"
        if args.dry_run:
            message = "Tryb sprawdzenia, bez uruchamiania zadań. " + message
        print(message)
        if path := os.environ.get('GITHUB_STEP_SUMMARY'):
            with Path(path).open('a') as stream:
                stream.write('## Automatyczne nadrabianie raportu i poczty\n\n' + message + '\n')
        if result['action'] in {'report-missing', 'mail-uncertain'}:
            print('::error title=Raport wymaga uwagi::' + result['reason'])
            raise SystemExit(1)
        if result['action'] == 'mail-unconfigured':
            print('::warning title=Poczta nie jest skonfigurowana::' + result['reason'])
    except (ValueError, RuntimeError, OSError, httpx.HTTPError) as exc:
        print(f'::error title=Nie udało się sprawdzić raportu::{type(exc).__name__}')
        raise SystemExit(1) from None
    finally:
        remote.close()


if __name__ == '__main__':
    main()
