"""Owner-reviewed alert feedback. Public GitHub issues are the source of truth."""
from __future__ import annotations

import re
from datetime import date, timedelta
from urllib.parse import urlencode

import httpx

ALERT = re.compile(r'^Ocena alertu \[(\d{4}-\d{2}-\d{2})/([a-f0-9]{16})\] (TRAFNY|NIETRAFNY|NIE WIEM)$')
MISSED = re.compile(r'^Pominięta zmiana \[(\d{4}-\d{2}-\d{2})/([a-z0-9.-]+)/((?:glowna|projekt))\]$')
TRUSTED = {'OWNER', 'MEMBER', 'COLLABORATOR'}
LABELS = {'TRAFNY': 'Trafny', 'NIETRAFNY': 'Nietrafny', 'NIE WIEM': 'Nie wiem'}


def issue_url(repo: str, title: str, body: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        return ''
    return 'https://github.com/' + repo + '/issues/new?' + urlencode({'title': title, 'body': body})


def feedback_links(repo: str, day: str, event: dict) -> list[tuple[str, str]]:
    body = ('Ocena alertu z dashboardu. Po sprawdzeniu kliknij „Submit new issue”.\n\n'
            + 'Pracownia: ' + event['domain'] + '\nZdarzenie: ' + event['sentence']
            + '\nŹródło: ' + event['lead']['source'] + '\n\nOpcjonalny komentarz:')
    return [(label, issue_url(repo, f"Ocena alertu [{day}/{event['id']}] {value}", body))
            for value, label in LABELS.items()]


def missed_link(repo: str, day: str, domain: str, page: str, source: str) -> str:
    return issue_url(repo, f'Pominięta zmiana [{day}/{domain}/{page}]',
                     'Opisz zmianę, którą monitor pominął, oraz kiedy ją zauważono.\n\nŹródło: ' + source + '\n\nOpis:')


def summarize(issues: list[dict], day: str, ledger: dict, domains: set[str]) -> dict:
    cutoff = (date.fromisoformat(day) - timedelta(days=180)).isoformat()
    ratings, misses = {}, {}
    for issue in issues:
        if 'pull_request' in issue or issue.get('author_association') not in TRUSTED:
            continue
        title, number = issue.get('title', ''), issue.get('number')
        match = ALERT.fullmatch(title)
        if match:
            observed_day, identifier, verdict = match.groups()
            key = observed_day + '/' + identifier
            if not cutoff < observed_day <= day or key not in ledger or not isinstance(number, int):
                continue
            rank = (issue.get('updated_at', ''), number)
            if key not in ratings or rank > ratings[key]['rank']:
                ratings[key] = {'verdict': verdict, 'number': number, 'rank': rank}
        elif match := MISSED.fullmatch(title):
            observed_day, domain, _page = match.groups()
            if cutoff < observed_day <= day and domain in domains and isinstance(number, int):
                misses[number] = True
    counts = {key: sum(v['verdict'] == key for v in ratings.values()) for key in LABELS}
    tracked = sum(cutoff < key.split('/', 1)[0] <= day for key in ledger)
    return {'status': 'ok', 'ratings': {key: {'verdict': item['verdict'], 'number': item['number']}
                                       for key, item in ratings.items()},
            'counts': counts, 'tracked': tracked, 'missed_reports': len(misses), 'as_of': day}


def read_feedback(remote, day: str, ledger: dict, domains: set[str]) -> dict:
    """A read failure is reported as unknown and cannot fail the daily scan."""
    cutoff = (date.fromisoformat(day) - timedelta(days=180)).isoformat()
    records = []
    try:
        for page in range(1, 101):
            response = remote.request('GET', remote.prefix + '/issues', params={
                'state': 'all', 'since': cutoff + 'T00:00:00Z', 'per_page': 100, 'page': page})
            batch = response.json()
            if not isinstance(batch, list):
                raise ValueError('Niepoprawny wykaz ocen')
            records.extend(batch)
            if len(batch) < 100:
                return {**summarize(records, day, ledger, domains), 'repository': remote.repo}
        raise ValueError('Zbyt wiele zgłoszeń do pełnego odczytu ocen')
    except (RuntimeError, ValueError, OSError, httpx.HTTPError):
        return {'status': 'unavailable', 'repository': remote.repo, 'as_of': day}


def summary_text(data: dict) -> str:
    if data.get('status') != 'ok':
        return 'Oceny alertów: nie udało się odczytać ocen z GitHub.'
    c = data['counts']
    judged = c['TRAFNY'] + c['NIETRAFNY']
    score = f"{c['TRAFNY']}/{judged} trafnych ({round(100 * c['TRAFNY'] / judged)}%)" if judged else 'brak ocen trafny/nietrafny'
    coverage = f"oceniono {sum(c.values())}/{data.get('tracked', 0)} zapisanych alertów"
    return (f"Oceny alertów z ostatnich 180 dni: {score}; {coverage}; nie wiem: {c['NIE WIEM']}; "
            f"zgłoszenia pominiętych zmian: {data['missed_reports']}.")
