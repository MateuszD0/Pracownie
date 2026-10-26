"""Send a short, dated report; SMTP credentials never enter report assets."""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import smtplib
import ssl
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from .github import GitHubStore
from .journal import safe_source
from .model import WARSAW, json_bytes, local_day, now_iso

OWNER = 'pracownie-email:v1'


@dataclass
class MailConfig:
    recipient: str
    username: str
    password: str = field(repr=False)
    host: str = 'smtp.gmail.com'
    port: int = 587

    @classmethod
    def from_env(cls):
        recipient = os.environ.get('REPORT_EMAIL_TO', '').strip()
        username = os.environ.get('SMTP_USERNAME', '').strip() or recipient
        password = os.environ.get('SMTP_PASSWORD', '')
        if not recipient or not username or not password:
            raise ValueError('Brak konfiguracji REPORT_EMAIL_TO lub SMTP_PASSWORD w sekretach Actions.')
        Address(addr_spec=recipient)
        Address(addr_spec=username)
        return cls(recipient, username, password, os.environ.get('SMTP_HOST') or 'smtp.gmail.com',
                   int(os.environ.get('SMTP_PORT') or '587'))


def safe_cell(cell) -> str:
    """Keep readable text and HTTP links, without copying source HTML styles."""
    parts = []
    for child in cell.children:
        if getattr(child, 'name', None) == 'a':
            url = safe_source(child.get('href', ''))
            label = html.escape(child.get_text(' ', strip=True))
            parts.append(f'<a href="{html.escape(url, quote=True)}">{label}</a>' if url else label)
        else:
            parts.append(html.escape(child.get_text(' ', strip=True) if hasattr(child, 'get_text') else str(child)))
    return ' '.join(parts)


def compose(day: str, document: str, readiness: dict, repo: str, report_url: str, config: MailConfig) -> EmailMessage:
    soup = BeautifulSoup(document, 'html.parser')
    intro = soup.find('p')
    comparison = re.search(r'(\d{4}-\d{2}-\d{2})\s*→\s*(\d{4}-\d{2}-\d{2})', intro.get_text(' ', strip=True) if intro else '')
    if not comparison or comparison[2] != day:
        raise ValueError('Dashboard nie dotyczy dnia raportu; nie wysłano starego porównania.')
    from urllib.parse import urljoin
    for a in soup.select('a[href]'):
        a['href'] = urljoin(f'https://github.com/{repo}/blob/main/DASHBOARD.md', a['href'])
    tables = soup.find_all('table')
    if len(tables) < 2:
        raise ValueError('Brak tabel porównania; nie wysłano pustego raportu.')
    dashboard = f'https://github.com/{repo}/blob/main/DASHBOARD.md'
    title = f'Pracownie: zmiany {comparison[1]} → {day}'
    limited = readiness.get('limited', [])
    missing = readiness.get('missing', [])
    coverage = f"Świeże odczyty: {readiness.get('fresh', '?')}/{readiness.get('expected', '?')}; częściowe: {len(limited)}; brakujące: {len(missing)}."
    text = [title, coverage]
    sections = [f'<h1>{html.escape(title)}</h1><p>{html.escape(coverage)}</p>']
    def section_table(title: str, legacy_index: int):
        heading = next((h for h in soup.find_all(['h2', 'h3']) if title in h.get_text(' ', strip=True) or title == 'Zmiany oferty i komunikacji' and 'Najważniejsze różnice biznesowe' in h.get_text(' ', strip=True)), None)
        return heading.find_next('table') if heading else tables[legacy_index]

    groups = [('Zmiany oferty i komunikacji', section_table('Zmiany oferty i komunikacji', 0), 6)]
    review_heading = next((h for h in soup.find_all(['h2', 'h3']) if h.get_text(' ', strip=True) == 'Ważne do sprawdzenia'), None)
    if review_heading:
        groups.append(('Ważne do sprawdzenia', review_heading.find_next('table'), 10))
    elif len(tables) >= 3:
        groups.append(('Grafika i wygląd — wybrane obserwacje', section_table('Grafika i wygląd', 1), 3))
    for heading, table, limit in groups:
        if table is None:
            raise ValueError('Brak tabel w wymaganej sekcji porównania.')
        headers = table.select('thead th')
        rows = table.select('tbody tr')[:limit]
        if not rows:
            raise ValueError('Pusta tabela raportu; nie wysłano wiadomości.')
        sections.append(f'<h2>{html.escape(heading)}</h2><table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;font-size:14px">')
        sections.append('<tr>' + ''.join(f'<th>{html.escape(c.get_text(" ", strip=True))}</th>' for c in headers) + '</tr>')
        text += ['', heading]
        for row in rows:
            cells = row.find_all(['td', 'th'], recursive=False)
            sections.append('<tr>' + ''.join('<td>' + safe_cell(cell) + '</td>' for cell in cells) + '</tr>')
            text.append(' | '.join(cell.get_text(' ', strip=True) for cell in cells))
            text.extend(a['href'] for a in row.select('a[href]') if safe_source(a['href']))
        sections.append('</table>')
    if missing or limited:
        note = 'Brak odczytu lub częściowe dane nie oznaczają braku zmian.'
        text += ['', note, 'Brakujące: ' + (', '.join(missing) or 'brak'), 'Częściowe: ' + (', '.join(limited) or 'brak')]
        sections.append('<p><strong>' + note + '</strong><br>Brakujące: ' + html.escape(', '.join(missing) or 'brak') + '<br>Częściowe: ' + html.escape(', '.join(limited) or 'brak') + '</p>')
    for label, url in [('Otwórz pełne porównanie', dashboard), ('Pliki i zrzuty przed / po', report_url)]:
        if not safe_source(url):
            raise ValueError('Niepoprawny adres raportu.')
        text += ['', label + ': ' + url]
        sections.append(f'<p><a href="{html.escape(url, quote=True)}">{label}</a></p>')
    message = EmailMessage()
    message['Subject'] = title + (' — dane częściowe' if missing or limited else '')
    message['From'] = Address('Monitoring pracowni', addr_spec=config.username)
    message['To'] = Address(addr_spec=config.recipient)
    message['Date'] = formatdate(localtime=False, usegmt=True)
    message['Message-ID'] = make_msgid(domain=Address(addr_spec=config.username).domain)
    message.set_content('\n'.join(text))
    message.add_alternative('<!doctype html><html lang="pl"><body style="font-family:Arial,sans-serif;color:#222">' + ''.join(sections) + '</body></html>', subtype='html')
    return message


def receipt(remote: GitHubStore, asset: dict, day: str) -> dict:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'receipt.json'
        remote.download(asset, path)
        data = json.loads(path.read_text())
    if data.get('owner') != OWNER or data.get('day') != day:
        raise ValueError('Niepoprawne potwierdzenie e-mail; wstrzymano wysyłkę.')
    return data


def deliver(remote: GitHubStore, day: str, config: MailConfig, smtp_factory=smtplib.SMTP) -> str:
    record = remote.published_report(day)
    if not record or not record.get('readiness'):
        raise ValueError('Brak zatwierdzonego raportu z informacją o jakości; e-mail nie został wysłany.')
    release = remote.release(f'{remote.namespace}-report-{day}')
    assert release is not None
    assets = {a['name']: a for a in remote.assets(release)}
    sent_name, pending_name = f'email-{day}-sent.json', f'email-{day}-pending.json'
    if sent_name in assets:
        if receipt(remote, assets[sent_name], day).get('status') != 'sent':
            raise ValueError('Niepoprawny status potwierdzenia e-mail.')
        return 'already-sent'
    if pending_name in assets:
        receipt(remote, assets[pending_name], day)
        raise ValueError('Poprzednia wysyłka nie ma potwierdzenia; sprawdź skrzynkę przed ręcznym ponowieniem.')
    response = remote.request('GET', f'{remote.prefix}/contents/{remote.dashboard_filename}',
                              params={'ref': 'main'}, headers={'Accept': 'application/vnd.github.html+json'})
    message = compose(day, response.text, record['readiness'], remote.repo, release['html_url'], config)
    with tempfile.TemporaryDirectory() as directory, smtp_factory(config.host, config.port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(config.username, config.password)
        path = Path(directory) / 'receipt.json'
        data = {'owner': OWNER, 'day': day, 'run_id': record['run_id'], 'status': 'pending', 'started_at': now_iso()}
        path.write_bytes(json_bytes(data))
        pending = remote.upload(release, pending_name, path)
        # Do not retry an uncertain SMTP acceptance: that can duplicate mail.
        try:
            refused = smtp.send_message(message)
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError):
            remote.request('DELETE', f"{remote.prefix}/releases/assets/{pending['id']}")
            raise
        data.update(status='sent', sent_at=now_iso())
        path.write_bytes(json_bytes(data))
        remote.upload(release, sent_name, path)
        remote.request('DELETE', f"{remote.prefix}/releases/assets/{pending['id']}")
    return 'sent'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--day', default='')
    parser.add_argument('--scan-started-at', default='')
    args = parser.parse_args()
    day = args.day or (datetime.fromisoformat(args.scan_started_at.replace('Z', '+00:00')).astimezone(WARSAW).date().isoformat() if args.scan_started_at else local_day())
    remote = GitHubStore(os.environ['GITHUB_REPOSITORY'], os.environ.get('GITHUB_TOKEN', ''))
    try:
        result = deliver(remote, day, MailConfig.from_env())
        from .delivery import refresh_email_status
        try:
            refreshed = refresh_email_status(remote, day)
        except (ValueError, RuntimeError, OSError, httpx.HTTPError):
            refreshed = False
        if not refreshed:
            print('Potwierdzenie SMTP zapisano; aktualizacja statusu dashboardu wymaga ponowienia.')
        print('Wysłano raport e-mail.' if result == 'sent' else 'Raport tego dnia został już wysłany; pominięto duplikat.')
    except (ValueError, RuntimeError, OSError, smtplib.SMTPException, httpx.HTTPError) as exc:
        # SMTP errors can contain the recipient; keep those out of public logs.
        reason = "Gmail odrzucił logowanie; sprawdź hasło aplikacji." if isinstance(exc, smtplib.SMTPAuthenticationError) else "Sprawdź konfigurację oraz potwierdzenie poprzedniej wysyłki."
        print(f"::error title=Raport e-mail nie został potwierdzony::{type(exc).__name__}: {reason}")
        raise SystemExit(1) from None
    finally:
        remote.close()


if __name__ == '__main__':
    main()
