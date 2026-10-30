from datetime import UTC, datetime

import pytest

from pracownie import one_off


@pytest.mark.parametrize(
    ("target", "now"),
    [
        ("2026-10-30T09:00:00+01:00", datetime(2026, 10, 30, 7, 15, tzinfo=UTC)),
        ("2026-07-30T09:00:00+02:00", datetime(2026, 7, 30, 6, 15, tzinfo=UTC)),
    ],
)
def test_polish_start_time_in_winter_and_summer(target, now):
    assert one_off.seconds_until(target, now) == 45 * 60


@pytest.mark.parametrize("target", ["2026-10-30T09:00:00", "2026-10-30", "not-a-date"])
def test_no_implicit_timezone_or_invalid_date(target):
    with pytest.raises(ValueError):
        one_off.seconds_until(target, datetime(2026, 10, 30, 7, tzinfo=UTC))


@pytest.mark.parametrize("hour,minute", [(5, 59), (8, 11)])
def test_reject_excessive_wait_and_expired_request(hour, minute):
    with pytest.raises(ValueError):
        one_off.seconds_until("2026-10-30T09:00:00+01:00", datetime(2026, 10, 30, hour, minute, tzinfo=UTC))


def test_minor_runner_delay_does_not_skip_requested_scan():
    assert one_off.seconds_until("2026-10-30T09:00:00+01:00", datetime(2026, 10, 30, 8, 2, tzinfo=UTC)) == 0


def test_wait_rechecks_clock_and_never_returns_before_target(monkeypatch):
    class Clock:
        now_value = datetime(2026, 10, 30, 7, 58, 45, tzinfo=UTC)

        @classmethod
        def now(cls, _tz):
            return cls.now_value

        fromisoformat = datetime.fromisoformat

    sleeps = []

    def sleep(seconds):
        from datetime import timedelta

        sleeps.append(seconds)
        Clock.now_value += timedelta(seconds=seconds)

    monkeypatch.setattr(one_off, "datetime", Clock)
    monkeypatch.setattr(one_off.time, "sleep", sleep)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    one_off.wait_until("2026-10-30T09:00:00+01:00")
    assert sleeps == [60, 15]
    assert Clock.now_value == datetime(2026, 10, 30, 8, tzinfo=UTC)
