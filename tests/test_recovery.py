import copy
import json
from datetime import UTC, datetime

import httpx
import pytest

from pracownie.model import WARSAW
from pracownie.recovery import RECOVERY_TITLE, recover

NOW = datetime(2026, 10, 22, 9, 30, tzinfo=WARSAW)


class Remote:
    prefix = 'https://api.github.com/repos/test/monitor'
    namespace = 'monitor'

    def __init__(self, record=None):
        self.record = record
        self.records = {'monitor.yml': [], 'rebuild-report.yml': [], 'email.yml': []}
        self.jobs = {}
        self.writes = []
        self.calls = []
        self.markers = []
        self.reads = 0

    def request(self, method, url, **kwargs):
        self.calls.append((method, url))
        if method == 'POST':
            self.writes.append((url, kwargs['json']))
            return httpx.Response(204)
        if '/actions/workflows/' in url:
            name = url.split('/actions/workflows/')[1].split('/')[0]
            return httpx.Response(200, json={'workflow_runs': self.records[name]})
        return httpx.Response(200, json={'jobs': self.jobs[url.split('/actions/runs/')[1].split('/')[0]]})

    def published_report(self, day):
        self.reads += 1
        return self.record

    def release(self, tag):
        return {'id': 1}

    def assets(self, release):
        return self.markers

    def download(self, asset, path):
        path.write_text(json.dumps(asset['data']))


def published(retry=None):
    return {'day': '2026-10-22', 'run_id': 'r', 'readiness': {'retry_domains': retry or [], 'expected': 130, 'fresh': 123}}


def run(number='1', title='Codzienny monitoring pracowni', status='completed', at='2026-10-22T03:17:00Z'):
    return {'id': number, 'display_title': title, 'created_at': at, 'status': status}


def test_missing_daily_cron_is_recovered_as_full_resumable_scan():
    remote = Remote()
    result = recover(remote, NOW, False)
    assert result['action'] == 'scan-dispatched'
    url, payload = remote.writes[0]
    assert url.endswith('/monitor.yml/dispatches')
    assert payload == {'ref': 'main', 'inputs': {'scope': 'full', 'rescan': 'false', 'automatic_recovery': 'true'}}


def test_transient_failures_only_retry_affected_domains_and_cap_attempts():
    remote = Remote(published(['hbstudio.pl']))
    remote.records['monitor.yml'] = [run(title=RECOVERY_TITLE)]
    result = recover(remote, NOW, True)
    assert result['automatic_attempt'] == 2
    assert remote.writes[0][1]['inputs']['repair_domains'] == 'hbstudio.pl'
    remote.records['monitor.yml'].append(run('2', RECOVERY_TITLE))
    remote.writes = []
    result = recover(remote, NOW, True)
    assert result['action'] == 'mail-dispatched'
    assert all('monitor.yml' not in url for url, _ in remote.writes)


@pytest.mark.parametrize('workflow,producer', [('monitor.yml', 'scan'), ('rebuild-report.yml', 'rebuild')])
def test_active_scan_or_publication_prevents_duplicate_and_mid_publication_reads(workflow, producer):
    remote = Remote()
    remote.records[workflow] = [run(status='in_progress')]
    remote.jobs['1'] = [{'name': producer, 'status': 'in_progress'}]
    assert recover(remote, NOW, True)['action'] == 'busy'
    assert remote.reads == 0 and not remote.writes


def test_queued_run_without_jobs_is_already_active():
    remote = Remote()
    remote.records['monitor.yml'] = [run(status='queued')]
    remote.jobs['1'] = []
    assert recover(remote, NOW, True)['action'] == 'busy'


def test_pending_optional_pages_does_not_block_ready_report_or_mail():
    remote = Remote(published())
    remote.records['monitor.yml'] = [run(status='waiting')]
    remote.jobs['1'] = [{'name': 'scan', 'status': 'completed'}, {'name': 'pages', 'status': 'waiting'}]
    assert recover(remote, NOW, True)['action'] == 'mail-dispatched'


def test_missing_credentials_are_not_reported_as_sent_and_later_configuration_is_retried():
    remote = Remote(published())
    assert recover(remote, NOW, False)['action'] == 'mail-unconfigured'
    assert not remote.writes
    assert recover(remote, NOW, True)['action'] == 'mail-dispatched'
    assert remote.writes == [(remote.prefix + '/actions/workflows/email.yml/dispatches',
                              {'ref': 'main', 'inputs': {'day': '2026-10-22'}})]


@pytest.mark.parametrize('status,action', [('sent', 'done'), ('pending', 'mail-uncertain')])
def test_mail_receipts_block_duplicates_including_uncertain_smtp_acceptance(status, action):
    remote = Remote(published())
    remote.markers = [{'name': f'email-2026-10-22-{status}.json', 'data': {'owner': 'pracownie-email:v1', 'day': '2026-10-22', 'status': status}}]
    assert recover(remote, NOW, True)['action'] == action
    assert not remote.writes


def test_existing_email_job_is_not_dispatched_again():
    remote = Remote(published())
    remote.records['email.yml'] = [run(status='in_progress')]
    remote.jobs['1'] = [{'name': 'email', 'status': 'in_progress'}]
    assert recover(remote, NOW, True)['action'] == 'mail-busy'
    assert not remote.writes


def test_no_blind_scan_after_noon_but_late_mail_can_be_sent():
    remote = Remote()
    late = NOW.replace(hour=18)
    assert recover(remote, late, True)['action'] == 'report-missing'
    assert not remote.writes
    remote.record = published(['hbstudio.pl'])
    assert recover(remote, late, True)['action'] == 'mail-dispatched'


def test_dry_run_is_read_only():
    for record in [None, published()]:
        remote = Remote(record)
        result = recover(remote, NOW, True, dry_run=True)
        assert result['dry_run'] and not remote.writes
        assert all(method == 'GET' for method, _ in remote.calls)


def test_polish_date_and_dst_used_for_attempt_limits():
    remote = Remote()
    remote.records['monitor.yml'] = [run(title=RECOVERY_TITLE, at='2026-10-21T23:30:00Z'),
                                    run('2', RECOVERY_TITLE, at='2026-10-22T03:30:00Z')]
    assert recover(remote, NOW, True)['action'] == 'report-missing'
    remote = Remote()
    assert recover(remote, datetime(2026, 12, 1, 4, 0, tzinfo=UTC), True)['action'] == 'early'
    assert not remote.calls
    assert recover(Remote(), datetime(2026, 12, 1, 4, 30, tzinfo=UTC), True)['action'] == 'scan-dispatched'
    with pytest.raises(ValueError, match='strefą'):
        recover(Remote(), datetime(2026, 10, 22, 6), True)


def test_only_automatic_attempts_today_count_and_unrelated_runs_are_preserved():
    remote = Remote()
    remote.records['monitor.yml'] = [run(), run('2', RECOVERY_TITLE, at='2026-10-21T03:17:00Z')]
    original = copy.deepcopy(remote.records)
    assert recover(remote, NOW, True)['automatic_attempt'] == 1
    assert remote.records == original
