from datetime import UTC, date, datetime, time, timedelta

import pytest

from pracownie import schedule
from pracownie.model import WARSAW
from pracownie.schedule import PRIMARY_CRON, PRIMARY_WINTER_CRON, RECOVERY_CRON, STARTS, daily_gate


class Publication:
    def __init__(self, published=False):
        self.published = published
        self.calls = []

    def published_report(self, day):
        self.calls.append(day)
        return {"day": day, "readiness": {"retry_domains": []}} if self.published else None


def invocations(day):
    # Expand the actual numeric UTC expressions, rather than an assumed timetable.
    events = []
    for cron in STARTS:
        minute, hours, *calendar = cron.split()
        assert calendar == ["*", "*", "*"]
        for hour in hours.split(","):
            events.append((datetime.combine(day, time(int(hour), int(minute)), UTC), cron))
    return sorted(events)


def test_every_day_including_dst_and_weekends_starts_at_0900_with_recovery_at_1030():
    for offset in range(730):
        day = date(2026, 1, 1) + timedelta(days=offset)
        remote = Publication()
        primary = []
        recovery = []
        for now, cron in invocations(day):
            result = daily_gate(cron, now, remote)
            assert result["day"] == day.isoformat()
            if result["run_scan"]:
                primary.append(now.astimezone(WARSAW).time())
                remote.published = True
            # Simulate a missing/failed first invocation; backup must be independent.
            if STARTS[cron] == time(10,30) and daily_gate(cron, now, Publication())["run_scan"]:
                recovery.append(now.astimezone(WARSAW).time())
        assert primary == [time(9)], day
        assert recovery == [time(10,30)], day


def test_early_utc_invocation_never_reads_or_writes_remote_history():
    remote = Publication()
    result = daily_gate(PRIMARY_WINTER_CRON, datetime(2026, 12, 5, 7, 59, tzinfo=UTC), remote)
    assert not result["run_scan"] and remote.calls == []


def test_backup_sees_completed_report_after_waiting_for_the_shared_writer_lock():
    remote = Publication(published=True)
    # Primary finished at 10:32 after the 10:30 backup was queued.
    result = daily_gate(RECOVERY_CRON, datetime(2026, 10, 24, 10, 32, tzinfo=WARSAW), remote)
    assert not result["run_scan"] and remote.calls == ["2026-10-24"]


def test_late_delivery_runs_instead_of_losing_another_day():
    result = daily_gate(PRIMARY_WINTER_CRON, datetime(2026, 10, 25, 10, 30, tzinfo=WARSAW), Publication())
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


@pytest.mark.parametrize('day,unused', [('2026-07-05',PRIMARY_WINTER_CRON),('2026-12-05',PRIMARY_CRON)])
def test_other_seasons_event_is_inert_even_if_delayed_and_report_needs_repair(day,unused):
    class Partial(Publication):
        def published_report(self, day):
            raise AssertionError('Wrong seasonal event must not read or rescan partial history')
    result=daily_gate(unused,datetime.fromisoformat(day+'T11:00:00').replace(tzinfo=WARSAW),Partial())
    assert not result['run_scan']


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
