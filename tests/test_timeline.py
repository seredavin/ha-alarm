"""Unit tests for the pure timeline math."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from custom_components.wakeup_alarm.timeline import brightness_at, build_timeline, volume_at, wake_candidates

TZ = ZoneInfo("Europe/Moscow")
WEEKDAYS = [True, True, True, True, True, False, False]


def dt(day: int, hour: int, minute: int = 0) -> datetime:
    # 2026-11-09 is a Monday
    return datetime(2026, 11, day, hour, minute, tzinfo=TZ)


def test_weekday_today() -> None:
    assert wake_candidates(dt(10, 6), time(7), WEEKDAYS)[0] == dt(10, 7)


def test_weekend_skipped() -> None:
    # Friday 08:00 -> Monday 07:00
    assert wake_candidates(dt(13, 8), time(7), WEEKDAYS)[0] == dt(16, 7)


def test_one_shot_any_day() -> None:
    assert wake_candidates(dt(14, 23), time(7), [False] * 7)[0] == dt(15, 7)


def test_second_candidate_for_skip() -> None:
    first, second = wake_candidates(dt(9, 22), time(7), WEEKDAYS)
    assert (first, second) == (dt(10, 7), dt(11, 7))


def test_not_after_excludes_handled() -> None:
    assert wake_candidates(dt(10, 6, 50), time(7), WEEKDAYS, not_after=dt(10, 7))[0] == dt(11, 7)


def test_exact_now_is_not_a_candidate() -> None:
    assert wake_candidates(dt(10, 7), time(7), WEEKDAYS)[0] == dt(11, 7)


def test_timeline_windows_and_start() -> None:
    tl = build_timeline(dt(10, 7), 15, 2, 20)
    assert tl.light.start == dt(10, 6, 45)
    assert tl.media.start == dt(10, 6, 58)
    assert tl.start == dt(10, 6, 40)


def test_timeline_scale() -> None:
    tl = build_timeline(dt(10, 7), 15, 2, 15, scale=60 / 900)
    assert tl.light.start == dt(10, 7) - timedelta(seconds=60)
    assert tl.media.start == dt(10, 7) - timedelta(seconds=8)


def test_start_in_the_past_brightness() -> None:
    tl = build_timeline(dt(10, 7), 15, 2, 15)
    value = brightness_at(tl.light.progress(dt(10, 6, 55)))
    assert 100 <= value <= 110  # ~41% of 255


def test_brightness_monotonic_and_bounds() -> None:
    values = [brightness_at(i / 100) for i in range(101)]
    assert values == sorted(values)
    assert values[0] == 1
    assert values[-1] == 255


def test_zero_length_window() -> None:
    tl = build_timeline(dt(10, 7), 0, 0, 0)
    assert tl.light.progress(dt(10, 6, 59)) == 0.0
    assert tl.light.progress(dt(10, 7)) == 1.0


def test_volume_interpolation() -> None:
    assert volume_at(0, 0.05, 0.4) == 0.05
    assert volume_at(0.5, 0.05, 0.4) == 0.23
    assert volume_at(1, 0.05, 0.4) == 0.4
    assert volume_at(0.5, 0.6, 0.4) == 0.4  # start above max is clamped
