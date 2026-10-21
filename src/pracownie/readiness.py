"""Publication availability is distinct from fresh base-page coverage."""
import re
from datetime import datetime

from .model import local_day


def base_readiness(day: str, results: list[dict], domains: list[str]) -> dict:
    fresh, missing, blocked, limited, retry = [], [], [], [], set()
    for domain in domains:
        for page in ('glowna', 'projekt'):
            rows = [r for r in results if r['domain'] == domain and r['page'] == page and r['scenario'] == 'podstawowy']
            key = f'{domain}/{page}'
            if any(r.get('observed_at') and local_day(datetime.fromisoformat(r['observed_at'])) == day
                   and not r.get('error') and r.get('data_quality') in {'ok', 'partial', 'visual'} for r in rows):
                fresh.append(key)
                if not any(r.get("data_quality") in {"ok", "visual"} and r.get("observed_at")
                           and local_day(datetime.fromisoformat(r["observed_at"])) == day and not r.get("error") for r in rows):
                    limited.append(key)
                continue
            missing.append(key)
            errors = ' '.join(str(r.get('error') or '') for r in rows)
            if re.search(r'\bHTTP\s+(?:401|403|404|410)\b|Nie ustalono karty projektu', errors, re.I):
                blocked.append(key)
            else:
                retry.add(domain)
    return {'expected': len(domains) * 2, 'fresh': len(fresh), 'missing': missing,
            'blocked': blocked, 'retry_domains': sorted(retry), 'limited': limited, 'complete': not missing and not limited}


def check_ready(record: dict | None) -> tuple[bool, str]:
    quality = (record or {}).get('readiness', {})
    ready = bool(quality.get('expected', 0) and quality.get('complete')
                 and quality.get('fresh') == quality['expected'])
    if not record:
        return False, 'Brak zatwierdzonego raportu z dzisiejszą datą.'
    return ready, f"Świeże odczyty podstawowe: {quality.get('fresh', 0)}/{quality.get('expected', '?')}; brakujące: {', '.join(quality.get('missing', [])) or 'brak'}; odczyty częściowe: {', '.join(quality.get('limited', [])) or 'brak'}."


def main():
    import os
    from datetime import UTC, time
    from pathlib import Path

    from .github import GitHubStore
    from .model import WARSAW

    now = datetime.now(UTC).astimezone(WARSAW)
    # Two UTC slots cover DST; the earlier winter slot is deliberately inert.
    if now.time() < time(7, 50):
        print('Kontrola gotowości odbędzie się o 07:50 czasu polskiego.')
        return
    remote = GitHubStore(os.environ['GITHUB_REPOSITORY'], os.environ.get('GITHUB_TOKEN', ''))
    try:
        ready, message = check_ready(remote.published_report(now.date().isoformat()))
        print(message)
        if summary := os.environ.get('GITHUB_STEP_SUMMARY'):
            with Path(summary).open('a') as stream:
                stream.write('## Kontrola raportu na 08:00\n\n' + message + '\n')
        if not ready:
            print('::error title=Niepełny raport poranny::' + message)
            raise SystemExit(1)
    finally:
        remote.close()


if __name__ == '__main__':
    main()
