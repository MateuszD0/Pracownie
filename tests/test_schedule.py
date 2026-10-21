from datetime import UTC, date, datetime, time, timedelta

import pytest

from pracownie import schedule
from pracownie.model import WARSAW
from pracownie.schedule import PRIMARY_CRON, RECOVERY_CRON, daily_gate


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
    for cron in [PRIMARY_CRON, RECOVERY_CRON]:
        minute, hours, *calendar = cron.split()
        assert calendar == ["*", "*", "*"]
        for hour in hours.split(","):
            events.append((datetime.combine(day, time(int(hour), int(minute)), UTC), cron))
    return sorted(events)


def test_every_day_including_dst_and_weekends_starts_at_0517_with_recovery_at_0607():
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
            if cron == RECOVERY_CRON and daily_gate(cron, now, Publication())["run_scan"]:
                recovery.append(now.astimezone(WARSAW).time())
        assert primary == [time(5, 17)], day
        assert recovery[0] == time(6, 7), day


def test_early_utc_invocation_never_reads_or_writes_remote_history():
    remote = Publication()
    result = daily_gate(PRIMARY_CRON, datetime(2026, 12, 5, 3, 17, tzinfo=UTC), remote)
    assert not result["run_scan"] and remote.calls == []


def test_backup_sees_completed_report_after_waiting_for_the_shared_writer_lock():
    remote = Publication(published=True)
    # Primary finished at 06:32 after the 06:07 backup was queued.
    result = daily_gate(RECOVERY_CRON, datetime(2026, 10, 24, 6, 32, tzinfo=WARSAW), remote)
    assert not result["run_scan"] and remote.calls == ["2026-10-24"]


def test_late_delivery_runs_instead_of_losing_another_day():
    result = daily_gate(PRIMARY_CRON, datetime(2026, 10, 25, 8, 30, tzinfo=WARSAW), Publication())
    assert result["run_scan"] and result["late"] and result["day"] == "2026-10-25"


def test_failed_read_does_not_become_a_successful_skip():
    class Unavailable:
        def published_report(self, day):
            raise RuntimeError("GitHub unavailable")

    with pytest.raises(RuntimeError, match="GitHub unavailable"):
        daily_gate(PRIMARY_CRON, datetime(2026, 10, 22, 5, 17, tzinfo=WARSAW), Unavailable())


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
            return datetime(2026, 10, 22, 6, 7, tzinfo=WARSAW).astimezone(tz)

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
    assert "08:00 Europe/Warsaw" in (tmp_path / "summary").read_text()
    assert closed == [True]
