import json
import smtplib

import httpx
import pytest
from bs4 import BeautifulSoup
from test_github import FakeGitHub, prepare

from pracownie.github import GitHubStore
from pracownie.mailer import MailConfig, compose, deliver
from pracownie.state import StateStore

DAY = '2026-10-22'
DOCUMENT = '''<h1>Dzienny dashboard pracowni</h1><p><strong>2026-10-21 → 2026-10-22</strong></p>
<table><thead><tr><th>Pracownia</th><th>Zmiana</th><th>Było</th><th>Jest</th><th>Źródło</th></tr></thead>
<tbody><tr><td>test.pl</td><td>Promocja</td><td>10%</td><td>20%<script>evil()</script></td><td><a href="https://test.pl/oferta">Otwórz</a><a href="javascript:evil()">Zły</a></td></tr></tbody></table>
<table><thead><tr><th>Pracownia</th><th>Grafika</th></tr></thead><tbody><tr><td>test.pl</td><td>Nowy baner</td></tr></tbody></table>
<table><tbody><tr><td>test.pl</td></tr></tbody></table>'''
CONFIG = MailConfig('reader@example.com', 'sender@example.com', 'private-app-password')
QUALITY = {'expected': 130, 'fresh': 127, 'missing': ['test.pl/projekt'], 'limited': ['other.pl/glowna']}


class SMTP:
    sent = []
    error = None
    calls = []

    def __init__(self, host, port, timeout):
        assert host == 'smtp.gmail.com' and port == 587 and timeout == 30

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def ehlo(self):
        self.calls.append('ehlo')

    def starttls(self, context):
        assert context.check_hostname
        self.calls.append('tls')

    def login(self, username, password):
        assert (username, password) == (CONFIG.username, CONFIG.password)
        self.calls.append('login')

    def send_message(self, message):
        self.calls.append('send')
        if self.error:
            raise self.error
        self.sent.append(message)
        return {}


@pytest.fixture
def delivery(tmp_path):
    SMTP.calls, SMTP.sent, SMTP.error = [], [], None
    fake = FakeGitHub()
    def respond(request):
        if request.url.path.endswith('/contents/DASHBOARD.md'):
            assert request.headers['accept'] == 'application/vnd.github.html+json'
            assert request.url.params['ref'] == fake.git_head
            return httpx.Response(200, text=DOCUMENT)
        return fake.request(request)
    remote = GitHubStore('test/monitor', 'fake', client=httpx.Client(transport=httpx.MockTransport(respond)))
    store, output = StateStore(tmp_path / 'state'), tmp_path / 'output'
    archive = prepare(store, output, DAY, '2026-10-22t064000-source')
    remote.publish(store, output, DAY, archive, '2026-10-22t064000-source')
    return remote, fake


def test_email_contains_dated_comparison_links_quality_and_no_attachments():
    message = compose(DAY, DOCUMENT, QUALITY, 'test/monitor', 'https://github.com/test/monitor/releases/tag/report', CONFIG)
    assert message['Subject'] == 'Pracownie: zmiany 2026-10-21 → 2026-10-22 — dane częściowe'
    plain = message.get_body(preferencelist=('plain',)).get_content()
    assert all(t in plain for t in ['127/130', '10%', '20%', 'Nowy baner', 'test.pl/projekt', 'other.pl/glowna'])
    content = message.get_body(preferencelist=('html',)).get_content()
    html = BeautifulSoup(content, 'html.parser')
    assert not html.select('script') and 'javascript:' not in content
    assert 'https://github.com/test/monitor/blob/main/DASHBOARD.md' in content
    assert not list(message.iter_attachments())
    assert CONFIG.password not in message.as_string() and CONFIG.password not in repr(CONFIG)


def test_stale_or_empty_comparison_is_rejected():
    with pytest.raises(ValueError, match='starego'):
        compose('2026-10-23', DOCUMENT, QUALITY, 'test/monitor', 'https://github.com', CONFIG)
    with pytest.raises(ValueError, match='tabel'):
        compose(DAY, DOCUMENT.split('<table>')[0], QUALITY, 'test/monitor', 'https://github.com', CONFIG)


def test_email_evidence_keeps_the_edition_when_tomorrows_dashboard_changes():
    links = '<a href="dashboard/zdarzenia-testpl.md#zdarzenie-1">Przed / po</a><a href="https://github.com/test/monitor/blob/main/dashboard/testpl.md">Odczyty</a>'
    document = DOCUMENT.replace('<a href="javascript:evil()">Zły</a>', links)
    message = compose(DAY, document, QUALITY, 'test/monitor', 'https://github.com/test/monitor/releases/tag/report', CONFIG, revision='abc123')
    content = message.get_body(preferencelist=('html',)).get_content()
    assert '/blob/abc123/dashboard/zdarzenia-testpl.md#zdarzenie-1' in content
    assert '/blob/abc123/dashboard/testpl.md' in content
    assert '/blob/abc123/DASHBOARD.md' in content
    assert '/blob/main/' not in content
    assert 'https://test.pl/oferta' in content


def test_successful_delivery_is_encrypted_deduplicated_and_receipt_has_no_personal_data(delivery):
    remote, fake = delivery
    edition = fake.git_head
    assert deliver(remote, DAY, CONFIG, SMTP) == 'sent'
    assert SMTP.calls == ['ehlo', 'tls', 'ehlo', 'login', 'send']
    assert deliver(remote, DAY, CONFIG, SMTP) == 'already-sent'
    assert len(SMTP.sent) == 1
    assert f'/blob/{edition}/DASHBOARD.md' in SMTP.sent[0].get_body(preferencelist=('html',)).get_content()
    receipts = [fake.contents[a['id']] for a in fake.assets.values() if a['name'].startswith('email-')]
    assert len(receipts) == 1
    text = receipts[0].decode()
    assert CONFIG.recipient not in text and CONFIG.username not in text and CONFIG.password not in text
    assert json.loads(text)['status'] == 'sent'


def test_uncertain_smtp_acceptance_blocks_automatic_duplicate(delivery):
    remote, _ = delivery
    SMTP.error = smtplib.SMTPServerDisconnected('lost acceptance')
    with pytest.raises(smtplib.SMTPServerDisconnected):
        deliver(remote, DAY, CONFIG, SMTP)
    SMTP.error = None
    with pytest.raises(ValueError, match='sprawdź skrzynkę'):
        deliver(remote, DAY, CONFIG, SMTP)
    assert not SMTP.sent


def test_explicit_smtp_rejection_allows_later_retry(delivery):
    remote, _ = delivery
    SMTP.error = smtplib.SMTPRecipientsRefused({'reader@example.com': (550, 'rejected')})
    with pytest.raises(smtplib.SMTPRecipientsRefused):
        deliver(remote, DAY, CONFIG, SMTP)
    SMTP.error = None
    assert deliver(remote, DAY, CONFIG, SMTP) == 'sent'


def test_rebuild_preserves_email_receipt_so_report_is_not_sent_twice(delivery, tmp_path):
    remote, _ = delivery
    assert deliver(remote, DAY, CONFIG, SMTP) == 'sent'
    store, output = StateStore(tmp_path / 'second-state'), tmp_path / 'second-output'
    archive = prepare(store, output, DAY, '2026-10-22t064100-rebuild')
    remote.publish(store, output, DAY, archive, '2026-10-22t064100-rebuild')
    assert deliver(remote, DAY, CONFIG, SMTP) == 'already-sent'
    assert len(SMTP.sent) == 1


def test_missing_credentials_and_header_injection_are_rejected(monkeypatch):
    monkeypatch.delenv('REPORT_EMAIL_TO', raising=False)
    monkeypatch.delenv('SMTP_PASSWORD', raising=False)
    with pytest.raises(ValueError, match='konfiguracji'):
        MailConfig.from_env()
    monkeypatch.setenv('REPORT_EMAIL_TO', 'reader@example.com\nBcc: victim@example.com')
    monkeypatch.setenv('SMTP_PASSWORD', 'private')
    with pytest.raises(ValueError):
        MailConfig.from_env()


def test_email_uses_named_sections_when_another_table_precedes_highlights():
    document = DOCUMENT.replace('<table>', '<h2>Najważniejsze różnice biznesowe</h2><table>', 1)
    insert = '<table><tbody><tr><td>UNRELATED_COVERAGE_TABLE</td></tr></tbody></table>'
    document = document.replace('<h2>', insert + '<h2>', 1)
    message = compose(DAY, document, QUALITY, 'test/monitor', 'https://github.com/test/monitor/releases/tag/report', CONFIG)
    plain = message.get_body(preferencelist=('plain',)).get_content()
    assert 'UNRELATED_COVERAGE_TABLE' not in plain
    assert '10%' in plain and '20%' in plain


def test_grouped_dashboard_keeps_both_relationship_groups_in_the_summary():
    first = DOCUMENT.split('<table>',1)[1].split('</table>',1)[0]
    tables = '<h2>Zmiany oferty i komunikacji</h2><h3>Współpracujące z nami</h3><table>'+first+'</table>'
    tables += '<h3>Niewspółpracujące z nami</h3><table>'+first.replace('test.pl','other.pl').replace('20%','30%')+'</table>'
    document = DOCUMENT.split('<table>',1)[0]+tables
    message = compose(DAY,document,QUALITY,'test/monitor','https://github.com/test/monitor/releases/tag/report',CONFIG)
    plain = message.get_body(preferencelist=('plain',)).get_content()
    assert 'Współpracujące z nami' in plain and 'Niewspółpracujące z nami' in plain
    assert 'test.pl' in plain and 'other.pl' in plain and '20%' in plain and '30%' in plain
