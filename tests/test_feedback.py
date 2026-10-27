from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from bs4 import BeautifulSoup
from test_management_dashboard import management_view

from pracownie.briefing import build_briefing
from pracownie.dashboard import render_dashboard_documents
from pracownie.feedback import feedback_links, read_feedback, summarize, summary_text
from pracownie.presentation import render_html

DAY = '2026-10-20'
IDENTIFIER = '0123456789abcdef'
LEDGER = {DAY + '/' + IDENTIFIER: {'domain': 'test.pl'}}


def issue(title, number, *, association='OWNER', updated='2026-10-21T09:00:00Z', **extra):
    return {'title': title, 'number': number, 'updated_at': updated, 'author_association': association, **extra}


def test_feedback_counts_only_latest_trusted_reviews_of_real_alerts():
    title = f'Ocena alertu [{DAY}/{IDENTIFIER}] '
    records = [issue(title + 'TRAFNY', 1, updated='2026-10-20T09:00:00Z'),
               issue(title + 'NIETRAFNY', 2), issue(title + 'TRAFNY', 3, association='NONE', updated='2026-10-22T00:00:00Z'),
               issue(f'Ocena alertu [{DAY}/fedcba9876543210] TRAFNY', 4),
               issue(f'Pominięta zmiana [{DAY}/test.pl/glowna]', 5),
               issue(f'Pominięta zmiana [{DAY}/other.pl/projekt]', 6),
               issue(title + 'TRAFNY', 7, pull_request={})]
    result = summarize(records, DAY, LEDGER, {'test.pl'})
    assert result['counts'] == {'TRAFNY': 0, 'NIETRAFNY': 1, 'NIE WIEM': 0}
    assert result['ratings'][DAY + '/' + IDENTIFIER]['number'] == 2
    assert result['missed_reports'] == 1
    assert '0/1 trafnych (0%)' in summary_text(result)
    assert 'brak ocen' in summary_text(summarize([], DAY, LEDGER, {'test.pl'}))


def test_issue_links_preserve_daily_event_identity_and_explicit_user_submission():
    event = {'id': IDENTIFIER, 'domain': 'test.pl', 'sentence': 'Nowy rabat -20%', 'lead': {'source': 'https://test.pl/?a=1&b=2'}}
    links = feedback_links('test/monitor', DAY, event)
    for value, (label, url) in zip(('TRAFNY', 'NIETRAFNY', 'NIE WIEM'), links, strict=True):
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        assert parsed.netloc == 'github.com' and parsed.path == '/test/monitor/issues/new'
        assert query['title'] == [f'Ocena alertu [{DAY}/{IDENTIFIER}] {value}']
        assert 'Submit new issue' in query['body'][0] and 'https://test.pl/?a=1&b=2' in query['body'][0]
        assert label


def test_priority_certainty_and_human_review_are_separate_on_both_report_surfaces():
    view = management_view()
    view['metadata']['feedback'] = {'repository': 'test/monitor', 'status': 'ok', 'ratings': {},
        'counts': {'TRAFNY': 0, 'NIETRAFNY': 0, 'NIE WIEM': 0}, 'missed_reports': 0}
    event = next(e for e in build_briefing(view)['events'] if e['bucket'] == 'promotions')
    assert event['priority'] == 'Wysoki'
    assert event['confidence'] == 'Zaobserwowana zmiana'
    docs = render_dashboard_documents(view, 'https://github.com/test/monitor/releases/tag/day')
    assert 'Priorytet: Wysoki' in docs['DASHBOARD.md']
    detail = next(text for path, text in docs.items() if path.startswith('dashboard/zdarzenia-') and event['id'] in text)
    assert 'Trafny' in detail and 'Nietrafny' in detail and 'Nie wiem' in detail
    assert 'publiczne zgłoszenie' in detail and 'Submit new issue' in detail
    assert 'Zgłoś pominiętą zmianę' not in docs['dashboard/testpl.md']  # no comparable captures in this fixture
    soup = BeautifulSoup(render_html(view), 'html.parser')
    assert 'Priorytet: Wysoki' in soup.select_one('#briefing').get_text()
    assert len(soup.select(f'#zdarzenie-{event["id"]} a[href*="issues/new"]')) == 3
    view['rows'][0]['pages'][0]['communication']['daily'] = True
    docs = render_dashboard_documents(view, 'https://github.com/test/monitor/releases/tag/day')
    assert 'Zgłoś pominiętą zmianę' in docs['dashboard/testpl.md']
    assert 'Pomini%C4%99ta+zmiana' in docs['dashboard/testpl.md']
    assert 'Zgłoś pominiętą zmianę' in render_html(view)


def test_feedback_read_failure_is_visible_and_does_not_report_zero_accuracy():
    class Remote:
        repo, prefix = 'test/monitor', '/repos/test/monitor'

        def request(self, *args, **kwargs):
            raise httpx.ConnectError('offline')

    result = read_feedback(Remote(), DAY, LEDGER, {'test.pl'})
    assert result['status'] == 'unavailable'
    assert 'nie udało się' in summary_text(result)


def test_feedback_reads_all_pages_and_safely_handles_a_later_reassessment():
    first = [issue('Niezwiązane zgłoszenie', i) for i in range(1, 100)]
    first.append(issue(f'Ocena alertu [{DAY}/{IDENTIFIER}] TRAFNY', 100, updated='2026-10-20T10:00:00Z'))
    second = [issue(f'Ocena alertu [{DAY}/{IDENTIFIER}] NIETRAFNY', 101, updated='2026-10-20T11:00:00Z')]

    class Remote:
        repo, prefix = 'test/monitor', '/repos/test/monitor'

        def request(self, method, path, *, params):
            assert method == 'GET' and path.endswith('/issues')
            assert params['state'] == 'all' and params['per_page'] == 100
            return httpx.Response(200, json=first if params['page'] == 1 else second)

    result = read_feedback(Remote(), DAY, LEDGER, {'test.pl'})
    assert result['status'] == 'ok' and result['counts']['NIETRAFNY'] == 1
    assert result['counts']['TRAFNY'] == 0 and result['tracked'] == 1


@pytest.mark.browser
async def test_reader_can_open_evidence_and_review_form_on_mobile(executable):
    from pracownie.browser import BrowserScanner

    view = management_view()
    view['metadata']['feedback'] = {'repository': 'test/monitor', 'status': 'ok', 'ratings': {},
        'counts': {'TRAFNY': 0, 'NIETRAFNY': 0, 'NIE WIEM': 0}, 'missed_reports': 0}
    event = next(e for e in build_briefing(view)['events'] if e['bucket'] == 'promotions')
    async with BrowserScanner(executable) as scanner:
        page = await scanner.browser.new_page(viewport={'width': 390, 'height': 844})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.set_content(render_html(view))
        await page.locator(f'[data-brief-id="{event["id"]}"] a').click()
        proof = page.locator(f'#zdarzenie-{event["id"]}')
        assert await proof.is_visible()
        assert 'Twoja ocena' in await proof.inner_text()
        href = await proof.get_by_role('link', name='Trafny', exact=True).get_attribute('href')
        assert parse_qs(urlsplit(href).query)['title'] == [f'Ocena alertu [{DAY}/{event["id"]}] TRAFNY']
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors
        await page.close()
