import base64
import copy
import json
import re

import httpx
import pytest
from test_github import FakeGitHub, prepare
from test_management_dashboard import management_view

from pracownie.dashboard import company_anchor, render_dashboard, render_dashboard_documents
from pracownie.github import OWNER_MARKER, GitHubStore
from pracownie.state import StateStore


def test_readable_dashboard_has_all_firms_both_pages_and_business_changes():
    view = management_view()
    text = render_dashboard(view, 'https://github.com/test/monitor/releases/tag/monitor-report-2026-10-20')
    assert text.index('## Najważniejsze różnice biznesowe') < text.index('## Wszystkie pracownie')
    docs = render_dashboard_documents(view, 'https://github.com/test/monitor/releases/tag/day')
    assert len(docs) == 3
    assert '[test.pl](dashboard/testpl.md)' in text
    text = '\n'.join(docs.values())
    assert text.count('## Strona główna') == text.count('## Karta projektu') == len(view['rows'])
    assert 'Rabat 10%' in text and 'Rabat 20%' in text and 'gratis' in text
    assert 'Brak odczytu' in text and '403' in text
    assert '[test.pl](dashboard/testpl.md)' in text and '# test.pl' in text
    assert '19.10.2026' in text and '20.10.2026' in text
    assert 'Nie ustalono konkretnych zmian biznesowych' not in text
    assert 'https://test.pl/#oferta' in text
    assert company_anchor('archi-projekt.com.pl') == 'archi-projektcompl'


def test_dashboard_escapes_source_text_and_distinguishes_gaps():
    view = copy.deepcopy(management_view())
    for e in view['journal']:
        e['daily'] = False
        e['after'] = '<script>alert(1)</script> | [x](javascript:bad)'
    text = render_dashboard(view, 'https://github.com/test/monitor/releases/tag/monitor-report-2026-10-20')
    assert 'Nie ustalono konkretnych zmian biznesowych' in text
    assert '<script>' not in text and 'javascript:bad' not in text
    view = management_view()
    view['journal'][0]['after'] = '<script>alert(1)</script> | [x]'
    text = render_dashboard(view, 'https://github.com/test/monitor/releases/tag/day')
    assert '&lt;script&gt;' in text and '\\|' in text and '\\[x\\]' in text


def test_dashboard_publication_preserves_user_files_and_retries_a_sha_conflict():
    fake = FakeGitHub()
    remote = GitHubStore('test/monitor', 'not-a-real-token', client=httpx.Client(transport=httpx.MockTransport(fake.request)))
    fake.repo_files['DASHBOARD.md'] = {'content': base64.b64encode(b'User notes').decode(), 'sha': 'old'}
    with pytest.raises(ValueError, match='nie należy'):
        remote.update_dashboard(management_view(), 'https://github.com/test/monitor/releases/tag/day')
    assert base64.b64decode(fake.repo_files['DASHBOARD.md']['content']) == b'User notes'
    del fake.repo_files['DASHBOARD.md']
    url = remote.update_dashboard(management_view(), 'https://github.com/test/monitor/releases/tag/day')
    assert url.endswith('/DASHBOARD.md')
    assert OWNER_MARKER in base64.b64decode(fake.repo_files['DASHBOARD.md']['content']).decode()
    original = fake.request
    writes = []

    def conflict_once(request):
        if request.method == 'PATCH' and request.url.path.endswith('/git/refs/heads/main'):
            writes.append(json.loads(request.content))
            if len(writes) == 1:
                return httpx.Response(409, json={'message': 'sha conflict'})
        return original(request)

    remote.client = httpx.Client(transport=httpx.MockTransport(conflict_once))
    remote.update_dashboard(management_view(), 'https://github.com/test/monitor/releases/tag/new-day')
    assert len(writes) == 2 and writes[-1]['force'] is False
    assert 'dashboard/testpl.md' in fake.repo_files and 'dashboard/blockedpl.md' in fake.repo_files
    pilot = GitHubStore('test/monitor', 'not-a-real-token', namespace='pilot', client=httpx.Client(transport=httpx.MockTransport(fake.request)))
    assert pilot.update_dashboard(management_view(), 'https://github.com/test/monitor/releases/tag/day').endswith('/DASHBOARD-PILOT.md')


def test_dashboard_failure_cannot_mark_the_daily_report_as_ready(tmp_path):
    fake = FakeGitHub()
    original = fake.request

    def fail_dashboard(request):
        if request.method == 'POST' and request.url.path.endswith('/git/trees'):
            return httpx.Response(403, json={'message': 'dashboard write failed'})
        return original(request)

    remote = GitHubStore('test/monitor', 'not-a-real-token', client=httpx.Client(transport=httpx.MockTransport(fail_dashboard)))
    store = StateStore(tmp_path / 'state')
    output = tmp_path / 'reports'
    output.mkdir()
    archive = prepare(store, output, '2026-10-20', '2026-10-20T060000-dashboard')
    with pytest.raises(RuntimeError, match='dashboard write failed'):
        remote.publish(store, output, '2026-10-20', archive, '2026-10-20T060000-dashboard')
    assert remote.published_report('2026-10-20') is None


def test_company_pagination_keeps_every_difference_and_avoids_false_unchanged_labels():
    view = management_view()
    original = copy.deepcopy(view['journal'][0])
    view['journal'].extend(dict(original, id=f'item-{i}', description=f'Komunikat {i}') for i in range(70))
    docs = render_dashboard_documents(view, 'https://github.com/test/monitor/releases/tag/day')
    company = [text for name, text in docs.items() if name.startswith('dashboard/testpl')]
    assert len(company) == 3
    for i in range(70):
        assert sum(f'Komunikat {i} ·' in text for text in company) == 1
    assert all('Ten sam projekt:' in text and '## Strona główna' in text and '## Karta projektu' in text for text in company)
    assert all(len(text.encode()) < 64_000 for text in docs.values())
    assert '[2](testpl-2.md)' in docs['dashboard/testpl.md']


def test_every_markdown_table_has_matching_header_and_separator_columns():
    docs = render_dashboard_documents(management_view(), 'https://github.com/test/monitor/releases/tag/day')
    for text in docs.values():
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if re.fullmatch(r'[| :\-]+', line) and '---' in line:
                assert len(re.split(r'(?<!\\)\|', line)) == len(re.split(r'(?<!\\)\|', lines[index - 1]))


def test_screenshot_only_differences_remain_visible_without_becoming_business_facts():
    view = management_view()
    docs = render_dashboard_documents(view, 'https://github.com/test/monitor/releases/tag/day', {'html': 'https://test.pl/report.html'})
    assert '## Grafika i wygląd' in docs['DASHBOARD.md']
    assert 'różnice obrazu bez jednoznacznego opisu: **1 pracowni**' in docs['DASHBOARD.md']
    assert 'Różnica zrzutów; przyczyna niepotwierdzona' in docs['DASHBOARD.md']
    company = docs['dashboard/testpl.md']
    assert company.count('### Grafika i wygląd — różnica do obejrzenia') == 2
    assert 'Zrzuty przed / po' in company
    assert 'Zmienił się obraz strony' not in docs['DASHBOARD.md'].split('## Grafika i wygląd')[0]
    # An older comparison must never masquerade as a daily graphic change.
    for item in view['journal']:
        if item['category'] == 'obraz':
            item['daily'] = False
    docs = render_dashboard_documents(view, 'https://github.com/test/monitor/releases/tag/day')
    assert 'różnice obrazu bez jednoznacznego opisu: **0 pracowni**' in docs['DASHBOARD.md']
    assert 'różnica do obejrzenia' not in docs['dashboard/testpl.md']
