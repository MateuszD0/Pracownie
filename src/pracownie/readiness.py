"""Publication availability is distinct from fresh base-page coverage."""
import re
from datetime import UTC, datetime, time
from pathlib import Path

from .model import WARSAW, local_day


def repair_domains(quality: dict) -> list[str]:
    # Also repair partial reads in manifests produced before this was persisted.
    return sorted(set(quality.get('retry_domains', [])) | {
        key.split('/')[0] for key in quality.get('limited', [])
    })


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
                    retry.add(domain)
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
    return ready, (f"Raport dostępny. Świeże odczyty: {quality.get('fresh', 0)}/{quality.get('expected', '?')} "
                   f"(w tym częściowe: {len(quality.get('limited', []))}). "
                   f"Bez odczytu: {len(quality.get('missing', []))}.")


def assess(record: dict | None, now: datetime, repo: str) -> dict:
    """Keep availability, coverage and the publication deadline independent."""
    local = now.astimezone(WARSAW)
    ready, message = check_ready(record)
    quality = (record or {}).get('readiness', {})
    published = (record or {}).get('first_published_at')
    when = datetime.fromisoformat(published).astimezone(WARSAW) if published else None
    deadline = datetime.combine(local.date(), time(8), WARSAW)
    on_time = when <= deadline if when else None
    if when:
        timing = ('Termin dotrzymany' if on_time else 'Termin 08:00 przekroczony') + f" — pierwsza potwierdzona publikacja: {when:%H:%M:%S}."
    elif record:
        timing = 'Nie ustalono godziny pierwszej publikacji; nie potwierdzono terminu 08:00.'
    else:
        timing = 'Termin 08:00 przekroczony.' if local >= deadline else 'Raport jeszcze nie powstał; termin upływa o 08:00.'
    url = f'https://github.com/{repo}/blob/main/DASHBOARD.md'
    lines = [f'# Stan raportu — {local:%Y-%m-%d}', '', message, '',
             f'[Otwórz dashboard]({url})', '',
             f'Kontrolę wykonano: **{local:%H:%M:%S} czasu polskiego**. {timing}', '',
             '| Obszar | Stan |', '| --- | --- |',
             f"| Raport | {'Dostępny' if record else 'Brak'} |",
             f"| Odczyty stron | {quality.get('fresh', 0)}/{quality.get('expected', '?')} |",
             f"| Bez odczytu | {len(quality.get('missing', []))} |",
             f"| Odczyty częściowe | {len(quality.get('limited', []))} |", '']
    for label, key in [('Bez odczytu', 'missing'), ('Odczyty częściowe', 'limited')]:
        if quality.get(key):
            lines += [f'**{label}:**', '']
            for item in quality[key]:
                domain, page = item.split('/', 1)
                lines.append(f"- {domain}: {'strona główna' if page == 'glowna' else 'karta projektu'}")
            lines.append('')
    retries = repair_domains(quality)
    if retries:
        lines += ['Do ponowienia: ' + ', '.join(retries) + '. Automatyczna naprawa ma limit dwóch prób dziennie.', '']
    if quality.get('blocked'):
        lines += ['Odmowa dostępu lub brak ustalonej karty projektu wymagają osobnej diagnostyki; nie są traktowane jako brak zmian.', '']
    return {'ready': ready, 'on_time': on_time, 'message': message,
            'timing': timing, 'summary': '\n'.join(lines) + '\n'}


def main():
    import os

    from .github import GitHubStore

    now = datetime.now(UTC).astimezone(WARSAW)
    # Two UTC slots cover DST; the earlier winter slot is deliberately inert.
    if now.time() < time(7, 50):
        print('Kontrola gotowości odbędzie się o 07:50 czasu polskiego.')
        return
    remote = GitHubStore(os.environ['GITHUB_REPOSITORY'], os.environ.get('GITHUB_TOKEN', ''))
    try:
        record = remote.published_report(now.date().isoformat())
        status = assess(record, now, os.environ['GITHUB_REPOSITORY'])
        print(status['message'] + ' ' + status['timing'])
        if summary := os.environ.get('GITHUB_STEP_SUMMARY'):
            with Path(summary).open('a') as stream:
                stream.write(status['summary'])
        if not status['ready']:
            title = 'Raport dostępny, ale dane są niekompletne' if record else 'Brak dzisiejszego raportu'
            print('::error title=' + title + '::' + status['message'])
        if status['on_time'] is False:
            print('::error title=Przekroczony termin publikacji::' + status['timing'])
        elif status['on_time'] is None and record:
            print('::warning title=Termin niepotwierdzony::' + status['timing'])
        if not status['ready'] or status['on_time'] is False:
            raise SystemExit(1)
    finally:
        remote.close()


if __name__ == '__main__':
    main()
