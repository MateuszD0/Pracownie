"""Public delivery facts; never expose mail credentials or recipient addresses."""
import base64
import json
import os
import re
from pathlib import Path

from .model import digest, json_bytes, now_iso
from .presentation import render_html, render_markdown, render_text
from .report import verify_outputs
from .state import atomic_write


def refresh_email_status(remote, day: str) -> bool:
    """Update only today's delivery line with a SHA guard, never an old report."""
    from .briefing import delivery_text
    from .github import OWNER_MARKER

    record = remote.published_report(day)
    if not record:
        return False
    status = delivery_status(remote, day, record)
    pattern = re.compile(r'<!-- delivery:' + re.escape(day) + r' -->.*?<!-- /delivery -->', re.S)
    for _attempt in range(3):
        response = remote.request('GET', remote.prefix + '/contents/' + remote.dashboard_filename, accepted_statuses=(404,))
        if response.status_code == 404:
            return False
        file = response.json()
        content = base64.b64decode(file['content']).decode()
        if OWNER_MARKER not in content or not pattern.search(content):
            return False
        line = '<!-- delivery:' + day + ' -->' + delivery_text({'metadata': {'delivery': status}}) + ' · czas polski.<!-- /delivery -->'
        updated = pattern.sub(lambda _, replacement=line: replacement, content)
        if updated == content:
            return True
        result = remote.request('PUT', remote.prefix + '/contents/' + remote.dashboard_filename,
                                json={'message': 'Update daily email delivery status', 'sha': file['sha'],
                                      'content': base64.b64encode(updated.encode()).decode()}, accepted_statuses=(409,))
        if result.status_code != 409:
            return True
    return False


def delivery_status(remote, day: str, previous: dict | None) -> dict:
    configured = os.environ.get('REPORT_EMAIL_CONFIGURED', '').lower()
    status = 'waiting' if configured == 'true' else 'not_configured' if configured == 'false' else 'unknown'
    editions = list((previous or {}).get('editions', []))
    release = remote.release(f'{remote.namespace}-report-{day}')
    if release:
        from .mailer import receipt

        assets = {a['name']: a for a in remote.assets(release)}
        if previous and not editions:
            old_html = next((a for a in assets.values() if a['id'] == previous['report_files']['html']), None)
            if old_html:
                editions.append({'run_id': previous['run_id'], 'created_at': old_html.get('created_at') or previous.get('publication_started_at') or previous.get('first_published_at'), 'html': old_html['browser_download_url']})
        for suffix, label in [('sent', 'sent'), ('pending', 'pending')]:
            name = f'email-{day}-{suffix}.json'
            if name in assets:
                verified = receipt(remote, assets[name], day)
                if verified.get('status') == label:
                    status = label
                    break
    return {'first_published_at': (previous or {}).get('first_published_at'), 'email': status,
            'checked_at': now_iso(), 'editions': editions}


def annotate_report(root: Path, day: str, delivery: dict, intelligence: dict | None = None) -> None:
    """Add delivery facts without changing any source capture or its timestamp."""
    verify_outputs(root, day)
    directory = root / day
    view = json.loads((directory / 'oferty.json').read_text())
    raw = json.loads((directory / 'zmiany.json').read_text())
    view['metadata']['delivery'] = raw['metadata']['delivery'] = delivery
    if intelligence is not None:
        view['metadata']['intelligence'] = raw['metadata']['intelligence'] = intelligence
    outputs = {directory / 'oferty.json': json_bytes(view), directory / 'zmiany.json': json_bytes(raw),
               directory / 'index.html': render_html(view).encode(), root / f'{day}.txt': render_text(view).encode(),
               directory / 'podsumowanie.md': render_markdown(view).encode()}
    manifest = json.loads((directory / 'manifest.json').read_text())
    for path, content in outputs.items():
        atomic_write(path, content)
        manifest['files'][path.relative_to(root).as_posix()] = {'sha256': digest(path), 'bytes': len(content)}
    atomic_write(directory / 'manifest.json', json_bytes(manifest))
    verify_outputs(root, day)
