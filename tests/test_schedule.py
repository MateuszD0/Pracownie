from datetime import UTC, date, datetime, time, timedelta

import pytest

from pracownie import schedule
from pracownie.model import WARSAW
from pracownie.schedule import PRIMARY_CRON, RECOVERY_CRON, STARTS, daily_gate


class Publication:
    def __init__(self, published=False):
        self.published = published
        self.calls = []

    def published_report(self, day):
        self.calls.append(day)
        return {"day": day, "readiness": {"retry_domains": []}} if self.published else None


def invocations(day):
    # Expand the local cron expressions and feed the gate UTC timestamps.
    for cron in STARTS:
        minute, hour, *calendar = cron.split()
        assert calendar == ["*", "*", "*"]
        yield datetime.combine(day, time(int(hour), int(minute)), WARSAW).astimezone(UTC), cron


def test_daily_start_and_fallbacks_across_dst_and_weekends():
    for offset in range(730):
        day = date(2026, 1, 1) + timedelta(days=offset)
        published = Publication(published=True)
        slots = list(invocations(day))
        assert [now.astimezone(WARSAW).time() for now, _ in slots] == [
            time(9), time(9, 7), time(9, 17), time(10, 30),
        ]
        for now, cron in slots:
            decision = daily_gate(cron, now, Publication())
            assert decision["day"] == day.isoformat()
            assert decision["run_scan"] and not decision["late"]
            assert not daily_gate(cron, now, published)["run_scan"]


def test_early_utc_invocation_never_reads_or_writes_remote_history():
    remote = Publication()
    result = daily_gate(PRIMARY_CRON, datetime(2026, 12, 5, 7, 59, tzinfo=UTC), remote)
    assert not result["run_scan"] and remote.calls == []


def test_backup_sees_completed_report_after_waiting_for_the_shared_writer_lock():
    remote = Publication(published=True)
    # Primary finished at 10:32 after the 10:30 backup was queued.
    result = daily_gate(RECOVERY_CRON, datetime(2026, 10, 24, 10, 32, tzinfo=WARSAW), remote)
    assert not result["run_scan"] and remote.calls == ["2026-10-24"]


def test_late_delivery_runs_instead_of_losing_another_day():
    result = daily_gate(PRIMARY_CRON, datetime(2026, 10, 25, 10, 30, tzinfo=WARSAW), Publication())
    assert result["run_scan"] and result["late"] and result["day"] == "2026-10-25"


def test_failed_read_does_not_become_a_successful_skip():
    class Unavailable:
        def published_report(self, day):
            raise RuntimeError("GitHub unavailable")

    with pytest.raises(RuntimeError, match="GitHub unavailable"):
        daily_gate(PRIMARY_CRON, datetime(2026, 10, 22, 9, 0, tzinfo=WARSAW), Unavailable())


def test_unknown_schedule_and_naive_clock_fail_visibly():
    with pytest.raises(ValueError, match="Nieznany"):
        daily_gate("changed cron without updating guard", datetime.now(UTC), Publication())
    with pytest.raises(ValueError, match="strefą"):
        daily_gate(PRIMARY_CRON, datetime(2026, 10, 22, 5, 17), Publication())


@pytest.mark.parametrize("published", [False, True])
def test_actions_gate_exports_decision_and_summary(tmp_path, monkeypatch, published):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 22, 10, 30, tzinfo=WARSAW).astimezone(tz)

    remote = Publication(published)
    closed = []
    remote.close = lambda: closed.append(True)
    monkeypatch.setattr(schedule, "GitHubStore", lambda *args: remote)
    monkeypatch.setattr(schedule, "datetime", Clock)
    monkeypatch.setenv("GITHUB_REPOSITORY", "test/monitor")
    monkeypatch.setenv("SCHEDULE_EXPRESSION", RECOVERY_CRON)
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "output"))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary"))
    schedule.main()
    expected = "false" if published else "true"
    assert (tmp_path / "output").read_text() == f"run_scan={expected}\nday=2026-10-22\n"
    assert "09:00 Europe/Warsaw" in (tmp_path / "summary").read_text()
    assert closed == [True]


@pytest.mark.parametrize('cron', [key for key in STARTS if key != RECOVERY_CRON])
def test_delayed_start_skips_a_published_report_even_if_it_needs_repairs(cron):
    class Partial(Publication):
        def published_report(self, day):
            return {"day": day, "readiness": {"retry_domains": ["test.pl"]}}

    now = datetime(2026, 12, 5, 10, 32, tzinfo=WARSAW)
    assert not daily_gate(cron, now, Partial())["run_scan"]
    assert daily_gate(RECOVERY_CRON, now, Partial())["repair_domains"] == ["test.pl"]


def test_queued_missing_report_scan_checks_the_published_day_and_local_clock_again():
    day = '2026-11-21'
    remote = Publication()
    late = datetime.fromisoformat(day + 'T20:59:59').replace(tzinfo=WARSAW)
    assert schedule.missing_report_gate(day, late, remote)['run_scan']
    remote.published = True
    assert not schedule.missing_report_gate(day, late, remote)['run_scan']
    assert remote.calls == [day, day]
    for delayed in [late.replace(hour=21), late + timedelta(days=1)]:
        assert not schedule.missing_report_gate(day, delayed, Publication())['run_scan']
