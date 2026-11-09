"""Bounded confirmation of changed copy; it never writes a comparison baseline."""
from __future__ import annotations

import asyncio
import shutil
from datetime import datetime
from pathlib import Path

from .communication import clean, records
from .extract import page_identity
from .model import Scenario, json_bytes, local_day, now_iso
from .quality import communication_usable


def candidate(change) -> bool:
    return (change.details.get('communication') and change.category in {'komunikacja', 'warunki', 'funkcje'}
            and not change.details.get('supporting_reason') and not change.details.get('commercial_check'))


def assess_copy(change, snapshot, url: str) -> dict:
    checked_at = snapshot.observed_at
    result = {'status': 'unverified', 'checked_at': checked_at, 'url': snapshot.url,
              'summary': 'Nie uzyskano porównywalnego ponownego odczytu komunikacji.'}
    if (page_identity(snapshot.url) != page_identity(url)
            or local_day(datetime.fromisoformat(checked_at)) != local_day(datetime.fromisoformat(change.after_at))
            or datetime.fromisoformat(checked_at) <= datetime.fromisoformat(change.after_at)
            or not communication_usable(snapshot)
            or snapshot.document.get('communication', {}).get('truncated')):
        return result
    inventory = records(snapshot)
    if not inventory:
        return result
    texts = {i['text'] for i in inventory if not i.get('unstable')}
    all_texts = {i['text'] for i in inventory}
    old, new = clean(change.before or ''), clean(change.after or '')
    # An old message still present in a changing widget is not evidence of
    # withdrawal, even when the new message is stable elsewhere on the page.
    confirms = (bool(new) and new in texts and (not old or old not in all_texts)
                or not new and bool(old) and old not in all_texts)
    if confirms:
        result.update(status='confirmed', summary='Zmianę komunikatu potwierdzono w dodatkowym odczycie tej samej strony.')
    else:
        result.update(status='unstable', summary='Komunikat nie powtórzył się jednoznacznie w dodatkowym odczycie.')
    return result


async def verify_copy(site, results: list, scanner, work: Path, archive: Path, *, budget: float = 30) -> None:
    targets = []
    for row in results:
        if row.domain != site.domain or row.scenario != 'podstawowy' or not row.observed_at or row.error:
            continue
        changes = [c for c in row.changes if candidate(c)]
        if changes:
            targets.append((row, changes))
    if not targets:
        return
    for _, changes in targets:
        for change in changes:
            change.details['communication_check'] = {'status': 'unverified', 'summary': 'Nie zakończono dodatkowego odczytu komunikacji.'}
    checks = []
    try:
        async with asyncio.timeout(budget):
            for row, changes in targets:
                try:
                    captured = await scanner.capture(site, row.page, row.url,
                        Scenario('weryfikacja-komunikacji', 'Potwierdzenie komunikacji'), work / f'copy-check-{row.page}.png')
                    for change in changes:
                        change.details['communication_check'] = assess_copy(change, captured.snapshot, row.url)
                    screenshot = getattr(captured, 'screenshot', None)
                    if screenshot and screenshot.is_file():
                        archive.mkdir(parents=True, exist_ok=True)
                        proof = archive / f'potwierdzenie-komunikacji-{row.page}.png'
                        shutil.copy2(screenshot, proof)
                        for change in changes:
                            change.evidence = {**change.evidence, 'potwierdzenie': proof.relative_to(archive.parents[1]).as_posix()}
                    checks.append({'page': row.page, 'url': row.url, 'snapshot': captured.snapshot.to_dict()})
                except Exception as exc:
                    message = str(exc).splitlines()[0][:250]
                    for change in changes:
                        change.details['communication_check'].update(error=message, checked_at=now_iso())
                    checks.append({'page': row.page, 'url': row.url, 'error': message})
    except TimeoutError:
        checks.append({'error': 'Wyczerpano czas dodatkowej weryfikacji komunikacji.'})
    finally:
        archive.mkdir(parents=True, exist_ok=True)
        (archive / 'weryfikacja-komunikacji.json').write_bytes(json_bytes({
            'checked_at': now_iso(), 'documents': checks,
            'assessments': [{'field_key': c.field_key, 'before': c.before, 'after': c.after,
                             'check': c.details['communication_check']} for _, changes in targets for c in changes]}))
