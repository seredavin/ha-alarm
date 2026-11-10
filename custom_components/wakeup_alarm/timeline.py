"""Pure scheduling math for the wake-up alarm (no Home Assistant dependencies)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from .const import GAMMA


def wake_candidates(
    now: datetime,
    wake_time: time,
    weekdays: Sequence[bool],
    not_after: datetime | None = None,
    count: int = 2,
) -> list[datetime]:
    """Return the next `count` wake moments strictly after `now` (and after `not_after`).

    With no weekday selected the alarm is one-shot and every day is a candidate.
    `now` must be timezone-aware; results share its tzinfo.
    """
    floor = max(now, not_after) if not_after else now
    any_day = not any(weekdays)
    result: list[datetime] = []
    day = floor.date()
    for _ in range(15):
        candidate = datetime.combine(day, wake_time, tzinfo=now.tzinfo)
        if candidate > floor and (any_day or weekdays[candidate.weekday()]):
            result.append(candidate)
            if len(result) == count:
                break
        day += timedelta(days=1)
    return result


@dataclass(frozen=True, slots=True)
class Window:
    """A time window of a sequence stage."""

    start: datetime
    end: datetime

    def progress(self, now: datetime) -> float:
        """Return 0..1 position of `now` inside the window."""
        span = (self.end - self.start).total_seconds()
        if span <= 0:
            return 1.0 if now >= self.end else 0.0
        return min(1.0, max(0.0, (now - self.start).total_seconds() / span))

    def active(self, now: datetime) -> bool:
        """Return True if `now` is at or after the window start."""
        return now >= self.start


@dataclass(frozen=True, slots=True)
class Timeline:
    """Stage windows for one wake moment."""

    wake_at: datetime
    light: Window
    media: Window
    cover: Window

    @property
    def start(self) -> datetime:
        """Return the moment the first stage begins."""
        return min(self.light.start, self.media.start, self.cover.start)


def build_timeline(
    wake_at: datetime,
    fade_min: float,
    media_lead_min: float,
    cover_lead_min: float,
    scale: float = 1.0,
) -> Timeline:
    """Build stage windows ending at `wake_at`; `scale` compresses all leads (test runs)."""

    def window(minutes: float) -> Window:
        return Window(wake_at - timedelta(minutes=max(0.0, minutes) * scale), wake_at)

    return Timeline(wake_at, window(fade_min), window(media_lead_min), window(cover_lead_min))


def brightness_at(progress: float) -> int:
    """Return brightness 1..255 for a sunrise progress 0..1 on a perceptual curve."""
    return max(1, min(255, round(255 * max(0.0, min(1.0, progress)) ** GAMMA)))


def volume_at(progress: float, start: float, maximum: float) -> float:
    """Return volume 0..1 interpolated linearly from `start` to `maximum`."""
    start = min(start, maximum)
    value = start + (maximum - start) * max(0.0, min(1.0, progress))
    return round(value, 2)
