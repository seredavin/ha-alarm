"""Alarm controller: schedule, wake-up sequence and manual-change detection."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
import logging
import math
from typing import Any

from homeassistant.components.cover import ATTR_POSITION, CoverEntityFeature
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_SUPPORTED_COLOR_MODES,
    ATTR_TRANSITION,
    ColorMode,
    LightEntityFeature,
)
from homeassistant.components.media_player import (
    ATTR_MEDIA_CONTENT_ID,
    ATTR_MEDIA_CONTENT_TYPE,
    ATTR_MEDIA_VOLUME_LEVEL,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ASSUMED_STATE,
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    STATE_OFF,
    STATE_ON,
    STATE_PLAYING,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CALLBACK_TYPE, Context, Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_point_in_time,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ACTIVE_STATES,
    BRIGHTNESS_TOLERANCE,
    CLOUD_COMMAND_GAP,
    CLOUD_MIN_INTERVAL,
    CLOUD_VOLUME_STEP,
    CONF_COVER_POSITION,
    CONF_COVERS,
    CONF_MEDIA_ID,
    CONF_MEDIA_PLAYER,
    CONF_MEDIA_TYPE,
    CONF_SOURCES,
    CONF_START_VOLUME,
    CONF_STOP_ON_CHANGE,
    CONF_SUN_ELEVATION,
    CONF_WEATHER,
    DEFAULT_COVER_POSITION,
    DEFAULT_MEDIA_ID,
    DEFAULT_MEDIA_TYPE,
    DEFAULT_SETTINGS,
    DEFAULT_START_VOLUME,
    DEFAULT_STOP_ON_CHANGE,
    DEFAULT_SUN_ELEVATION,
    DOMAIN,
    ECHO_WINDOW,
    EVENT_RINGING,
    EVENT_SNOOZED,
    EVENT_STOPPED,
    EVENT_SUNRISE_STARTED,
    GREETING_DELAY,
    MEDIA_DEBOUNCE,
    MEDIA_GRACE,
    PRESET_COMMANDS,
    PRESET_CUSTOM,
    SCHEDULE_SETTINGS,
    SET_AUTO_STOP,
    SET_COVER_LEAD,
    SET_COVER_SUN_ONLY,
    SET_ENABLED,
    SET_FADE,
    SET_GREETING,
    SET_MAX_VOLUME,
    SET_MEDIA_CUSTOM,
    SET_MEDIA_LEAD,
    SET_MEDIA_PRESET,
    SET_SKIP_NEXT,
    SET_SNOOZE,
    SET_WAKE_TIME,
    SET_WEEKDAYS,
    STORAGE_VERSION,
    TICK_INTERVAL,
    AlarmState,
    StopReason,
)
from .greeting import build_greeting
from .timeline import Timeline, brightness_at, build_timeline, volume_at, wake_candidates

_LOGGER = logging.getLogger(__name__)

SUN_ENTITY = "sun.sun"
NOT_PLAYING = frozenset({"paused", "idle", STATE_OFF, "standby"})
GREETING_REASONS = frozenset({StopReason.BUTTON, StopReason.SERVICE, StopReason.MANUAL})
FORECAST_TYPES = ("daily", "twice_daily", "hourly")
IGNORED_STATES = frozenset({STATE_UNAVAILABLE, STATE_UNKNOWN})


def is_dimmable(state: State | None) -> bool:
    """Return True if the entity is a light that supports brightness."""
    if state is None or state.domain != "light":
        return False
    modes = state.attributes.get(ATTR_SUPPORTED_COLOR_MODES) or []
    return any(mode != ColorMode.ONOFF for mode in modes)


@dataclass
class SourceTrack:
    """What the alarm did to a light source and what it expects from it."""

    entity_id: str
    dimmable: bool
    was_on: bool
    initial_brightness: int | None
    expect_on: bool
    last_set: int | None = None
    turned_on_at: datetime | None = None
    recent: deque[int] = field(default_factory=lambda: deque(maxlen=3))


@dataclass
class AlarmRun:
    """State of one execution of the wake-up sequence."""

    wake_at: datetime
    scale: float = 1.0
    test: bool = False
    sources: dict[str, SourceTrack] = field(default_factory=dict)
    saved_volume: float | None = None
    media_started: bool = False
    media_expect_playing: bool = False
    media_started_at: datetime | None = None
    last_volume: float | None = None
    cover_opened: bool = False
    woke: bool = False
    unsubs: list[CALLBACK_TYPE] = field(default_factory=list)
    media_debounce: CALLBACK_TYPE | None = None
    ticking: bool = False
    cloud: bool = False  # speaker reachable only through the Yandex cloud
    player_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_player_command: datetime | None = None
    volume_retry: CALLBACK_TYPE | None = None


class AlarmController:
    """Owns settings, schedule and the running sequence of one alarm."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.settings: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self._handled_wake: datetime | None = None
        self.state = AlarmState.OFF
        self.next_wake: datetime | None = None
        self.run: AlarmRun | None = None
        self._listeners: list[Callable[[], None]] = []
        self._schedule_unsubs: list[CALLBACK_TYPE] = []
        self._context = Context()

    # ------------------------------------------------------------------ setup

    @property
    def name(self) -> str:
        """Return the alarm name."""
        return self.entry.title

    @property
    def options(self) -> dict[str, Any]:
        """Return config entry options."""
        return dict(self.entry.options)

    async def async_load(self) -> None:
        """Load persisted settings."""
        data = await self._store.async_load() or {}
        for key, default in DEFAULT_SETTINGS.items():
            if key in data:
                self.settings[key] = data[key]
            else:
                self.settings[key] = default
        if handled := data.get("handled_wake"):
            self._handled_wake = dt_util.parse_datetime(handled)
        if SET_MEDIA_PRESET not in data:
            # 0.2.x kept the speaker command in options ("media_id").
            legacy = (self.options.get(CONF_MEDIA_ID) or "").strip()
            if legacy and legacy != DEFAULT_MEDIA_ID:
                self.settings[SET_MEDIA_PRESET] = PRESET_CUSTOM
                self.settings[SET_MEDIA_CUSTOM] = legacy

    @callback
    def async_start(self) -> None:
        """Start scheduling."""
        self._reschedule()

    @callback
    def async_shutdown(self) -> None:
        """Cancel everything without touching devices."""
        self._cancel_schedule()
        if self.run:
            self._release_run(self.run)
            self.run = None

    async def async_save_now(self) -> None:
        """Write pending settings immediately (on unload)."""
        await self._store.async_save(self._data_to_save())

    async def async_remove_store(self) -> None:
        """Delete persisted settings."""
        await self._store.async_remove()

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(self._data_to_save, 1)

    @callback
    def _data_to_save(self) -> dict[str, Any]:
        return {
            **self.settings,
            "handled_wake": self._handled_wake.isoformat() if self._handled_wake else None,
        }

    # -------------------------------------------------------------- listeners

    @callback
    def add_listener(self, update: Callable[[], None]) -> CALLBACK_TYPE:
        """Subscribe an entity to controller updates."""
        self._listeners.append(update)

        @callback
        def remove() -> None:
            self._listeners.remove(update)

        return remove

    @callback
    def _notify(self) -> None:
        for update in list(self._listeners):
            update()

    # --------------------------------------------------------------- settings

    @property
    def wake_time(self) -> time:
        """Return the configured wake time."""
        return time.fromisoformat(self.settings[SET_WAKE_TIME])

    @callback
    def set_setting(self, key: str, value: Any) -> None:
        """Change a runtime setting and apply it immediately."""
        if isinstance(value, time):
            value = value.replace(microsecond=0).isoformat()
        if self.settings.get(key) == value:
            return
        self.settings[key] = value
        self._save()
        if key == SET_ENABLED and not value and self.run and not self.run.test:
            self._stop(StopReason.DISABLED)
            return
        if key in SCHEDULE_SETTINGS:
            self._reschedule()
        else:
            self._notify()

    @callback
    def set_weekday(self, index: int, value: bool) -> None:
        """Toggle one weekday."""
        weekdays = list(self.settings[SET_WEEKDAYS])
        weekdays[index] = value
        self.set_setting(SET_WEEKDAYS, weekdays)

    # --------------------------------------------------------------- schedule

    @callback
    def _cancel_schedule(self) -> None:
        while self._schedule_unsubs:
            self._schedule_unsubs.pop()()

    def _timeline(self, wake_at: datetime, scale: float = 1.0) -> Timeline:
        return build_timeline(
            wake_at,
            self.settings[SET_FADE],
            self.settings[SET_MEDIA_LEAD],
            self.settings[SET_COVER_LEAD],
            scale,
        )

    @callback
    def _reschedule(self) -> None:
        """Recompute the next wake moment and arm timers."""
        self._cancel_schedule()
        now = dt_util.now()
        run = self.run

        if not self.settings[SET_ENABLED]:
            self.next_wake = None
            if run is None:
                self.state = AlarmState.OFF
            self._notify()
            return

        candidates = wake_candidates(now, self.wake_time, self.settings[SET_WEEKDAYS], self._handled_wake)
        if not candidates:
            self.next_wake = None
            self._notify()
            return

        if self.settings[SET_SKIP_NEXT] and len(candidates) > 1:
            skipped, wake_at = candidates[0], candidates[1]
            self._schedule_unsubs.append(async_track_point_in_time(self.hass, self._make_skip_reset(skipped), skipped))
        else:
            wake_at = candidates[0]
        self.next_wake = wake_at

        # A scheduled run in its sunrise phase follows schedule changes.
        if run and not run.test and self.state == AlarmState.SUNRISE and run.wake_at != wake_at:
            _LOGGER.debug("%s: schedule changed during sunrise, restarting run", self.name)
            self._end_run(None)
            run = None

        if run and not run.test and run.wake_at == wake_at:
            self._notify()
            return

        start = self._timeline(wake_at).start
        if now >= start and (run is None or run.test or run.woke):
            self._start_run(wake_at)
            return
        self._schedule_unsubs.append(async_track_point_in_time(self.hass, self._make_scheduled_start(wake_at), start))
        if run is None:
            self.state = AlarmState.SCHEDULED
        self._notify()

    def _make_skip_reset(self, skipped: datetime) -> Callable[[datetime], None]:
        @callback
        def reset(_now: datetime) -> None:
            _LOGGER.debug("%s: skipped wake at %s", self.name, skipped)
            self._handled_wake = skipped
            self.settings[SET_SKIP_NEXT] = False
            self._save()
            self._reschedule()

        return reset

    def _make_scheduled_start(self, wake_at: datetime) -> Callable[[datetime], None]:
        @callback
        def start(_now: datetime) -> None:
            if self.run and not self.run.test and not self.run.woke:
                return
            self._start_run(wake_at)

        return start

    # ------------------------------------------------------------------- runs

    @callback
    def async_trigger(self, duration: float | None = None) -> None:
        """Start a test run that ends `duration` seconds from now."""
        if self.run and not self.run.test:
            _LOGGER.info("%s: test ignored, alarm is already running", self.name)
            return
        if self.run:
            self._end_run(None)
        longest = max(self.settings[SET_FADE], self.settings[SET_MEDIA_LEAD], self.settings[SET_COVER_LEAD])
        if duration is None:
            duration = longest * 60
        duration = max(1.0, float(duration))
        scale = duration / (longest * 60) if longest else 1.0
        self._start_run(dt_util.now() + timedelta(seconds=duration), scale=scale, test=True)

    @callback
    def _start_run(self, wake_at: datetime, scale: float = 1.0, test: bool = False) -> None:
        if self.run:
            self._end_run(None)
        run = AlarmRun(wake_at=wake_at, scale=scale, test=test)
        self.run = run
        for entity_id in self.options.get(CONF_SOURCES, []):
            state = self.hass.states.get(entity_id)
            on = state is not None and state.state == STATE_ON
            brightness = state.attributes.get(ATTR_BRIGHTNESS) if on and state else None
            run.sources[entity_id] = SourceTrack(
                entity_id=entity_id,
                dimmable=is_dimmable(state),
                was_on=on,
                initial_brightness=brightness,
                expect_on=on,
            )
            if state is None or state.state in IGNORED_STATES:
                _LOGGER.warning("%s: source %s is unavailable", self.name, entity_id)

        if self.options.get(CONF_STOP_ON_CHANGE, DEFAULT_STOP_ON_CHANGE):
            watched = list(run.sources)
            if player := self.options.get(CONF_MEDIA_PLAYER):
                watched.append(player)
            if watched:
                run.unsubs.append(async_track_state_change_event(self.hass, watched, self._on_device_change))
        if self.options.get(CONF_COVERS):
            run.unsubs.append(async_track_state_change_event(self.hass, [SUN_ENTITY], self._on_sun_change))

        interval = max(1.0, min(TICK_INTERVAL, TICK_INTERVAL * scale))
        run.unsubs.append(async_track_time_interval(self.hass, self._on_tick, timedelta(seconds=interval)))
        run.unsubs.append(async_track_point_in_time(self.hass, self._on_wake, wake_at))

        self.state = AlarmState.SUNRISE
        _LOGGER.debug("%s: sunrise started, wake at %s (scale %.3f)", self.name, wake_at, scale)
        self._fire(EVENT_SUNRISE_STARTED)
        self._notify()
        self.hass.async_create_task(self._async_tick(), eager_start=True)

    @callback
    def _release_run(self, run: AlarmRun) -> None:
        while run.unsubs:
            run.unsubs.pop()()
        if run.media_debounce:
            run.media_debounce()
            run.media_debounce = None
        if run.volume_retry:
            run.volume_retry()
            run.volume_retry = None

    @callback
    def _end_run(self, reason: StopReason | None) -> None:
        """Finish the current run, restoring the player. `None` = silent abort."""
        run = self.run
        if run is None:
            return
        self._release_run(run)
        self.run = None
        greet = reason in GREETING_REASONS and self.settings[SET_GREETING] and bool(self.options.get(CONF_MEDIA_PLAYER))
        self.hass.async_create_background_task(self._async_finish_media(run, greet), f"{DOMAIN} finish media")
        if reason is not None and not run.test:
            self._handled_wake = run.wake_at
            self._save()
        if reason is not None:
            self._fire(EVENT_STOPPED, reason=str(reason))

    @callback
    def _stop(self, reason: StopReason) -> None:
        run = self.run
        if run is None or self.state not in ACTIVE_STATES:
            return
        _LOGGER.debug("%s: stopped (%s)", self.name, reason)
        self._end_run(reason)
        if not run.test and not any(self.settings[SET_WEEKDAYS]) and self.settings[SET_ENABLED]:
            # One-shot alarm switches itself off after it has fired.
            self.settings[SET_ENABLED] = False
            self._save()
        self.state = AlarmState.SCHEDULED if self.settings[SET_ENABLED] else AlarmState.OFF
        self._reschedule()

    @callback
    def async_stop(self, reason: StopReason = StopReason.SERVICE) -> None:
        """Stop the current run (button or service)."""
        self._stop(reason)

    @callback
    def async_snooze(self) -> None:
        """Snooze a ringing alarm."""
        run = self.run
        if run is None or self.state != AlarmState.RINGING:
            return
        self.state = AlarmState.SNOOZED
        run.media_expect_playing = False
        self._cancel_media_debounce(run)
        if run.media_started and self.options.get(CONF_MEDIA_PLAYER):
            self.hass.async_create_background_task(self._player_call(run, "media_pause"), f"{DOMAIN} pause")
        delay = self.settings[SET_SNOOZE] * 60 * run.scale
        run.unsubs.append(async_call_later(self.hass, delay, self._on_snooze_end))
        self._fire(EVENT_SNOOZED)
        self._notify()

    @callback
    def _on_snooze_end(self, _now: datetime) -> None:
        run = self.run
        if run is None or self.state != AlarmState.SNOOZED:
            return
        self.state = AlarmState.RINGING
        self._fire(EVENT_RINGING)
        self._notify()
        self.hass.async_create_background_task(self._async_start_media(run, self._max_volume), f"{DOMAIN} resume media")

    # --------------------------------------------------------------- sequence

    @property
    def _max_volume(self) -> float:
        return self.settings[SET_MAX_VOLUME] / 100

    @callback
    def _on_tick(self, _now: datetime) -> None:
        self.hass.async_create_task(self._async_tick(), eager_start=True)

    async def _async_tick(self) -> None:
        run = self.run
        if run is None or self.state != AlarmState.SUNRISE or run.ticking:
            return
        run.ticking = True
        try:
            now = dt_util.now()
            timeline = self._timeline(run.wake_at, run.scale)
            if timeline.light.active(now):
                await self._async_fade(run, brightness_at(timeline.light.progress(now)))
            if self.run is not run:
                return
            await self._async_media_step(run, timeline, now)
            if self.run is not run:
                return
            if timeline.cover.active(now) and self.settings[SET_COVER_LEAD] > 0:
                await self._async_maybe_open_covers(run)
        finally:
            run.ticking = False

    async def _async_fade(self, run: AlarmRun, target: int) -> None:
        for track in list(run.sources.values()):
            if not track.dimmable or self.run is not run:
                continue
            state = self.hass.states.get(track.entity_id)
            current = 0
            if state is not None and state.state == STATE_ON:
                current = state.attributes.get(ATTR_BRIGHTNESS) or 0
            if target <= max(track.last_set or 0, current):
                continue
            data: dict[str, Any] = {ATTR_BRIGHTNESS: target}
            if state is not None and state.attributes.get(ATTR_SUPPORTED_FEATURES, 0) & LightEntityFeature.TRANSITION:
                data[ATTR_TRANSITION] = max(1.0, min(TICK_INTERVAL, TICK_INTERVAL * run.scale))
            self._mark_command(track, target, current)
            await self._call("light", "turn_on", track.entity_id, data)

    @callback
    def _mark_command(self, track: SourceTrack, brightness: int | None, current: int = 0) -> None:
        if not track.expect_on:
            track.turned_on_at = dt_util.utcnow()
        track.expect_on = True
        if brightness is not None:
            if not track.recent:
                # Starting point, so values reported mid-transition are accepted.
                track.recent.append(current)
            track.last_set = brightness
            track.recent.append(brightness)

    async def _async_media_step(self, run: AlarmRun, timeline: Timeline, now: datetime) -> None:
        player = self.options.get(CONF_MEDIA_PLAYER)
        if not player or self.settings[SET_MEDIA_LEAD] <= 0 or not timeline.media.active(now):
            return
        volume = volume_at(timeline.media.progress(now), self._start_volume, self._max_volume)
        if not run.media_started:
            run.media_started = True  # the start sequence below takes a few seconds on cloud speakers
            self.hass.async_create_background_task(self._async_start_media(run, volume), f"{DOMAIN} start media")
        elif run.media_expect_playing:
            await self._async_set_volume(run, volume)

    @property
    def _start_volume(self) -> float:
        return self.options.get(CONF_START_VOLUME, DEFAULT_START_VOLUME) / 100

    @property
    def media_command(self) -> str:
        """Return the speaker command for the selected preset."""
        preset = self.settings[SET_MEDIA_PRESET]
        if preset == PRESET_CUSTOM:
            custom = (self.settings[SET_MEDIA_CUSTOM] or "").strip()
            if custom:
                return custom
            _LOGGER.warning("%s: custom speaker command is empty, playing the default", self.name)
            return DEFAULT_MEDIA_ID
        return PRESET_COMMANDS.get(preset, DEFAULT_MEDIA_ID)

    async def _async_start_media(self, run: AlarmRun, volume: float) -> None:
        player = self.options.get(CONF_MEDIA_PLAYER)
        if not player:
            return
        state = self.hass.states.get(player)
        if state is None or state.state in IGNORED_STATES:
            _LOGGER.warning("%s: media player %s is unavailable", self.name, player)
            run.media_started = True  # do not retry every tick
            return
        if run.saved_volume is None and run.media_started_at is None:
            run.saved_volume = state.attributes.get(ATTR_MEDIA_VOLUME_LEVEL)
            run.cloud = state.attributes.get(ATTR_ASSUMED_STATE) is True
            if run.cloud:
                _LOGGER.debug("%s: %s is a cloud-only speaker", self.name, player)
        run.media_started = True
        run.media_expect_playing = True
        await self._async_set_volume(run, volume, force=True)
        if self.run is not run:
            return
        await self._player_call(
            run,
            "play_media",
            {
                ATTR_MEDIA_CONTENT_TYPE: self.options.get(CONF_MEDIA_TYPE, DEFAULT_MEDIA_TYPE),
                ATTR_MEDIA_CONTENT_ID: self.media_command,
            },
        )
        run.media_started_at = dt_util.utcnow()

    def _cloud_volume(self, volume: float) -> float:
        """Round up to a whole speaker step, never 0 (that would mute it)."""
        steps = math.ceil(round(volume / CLOUD_VOLUME_STEP, 6))
        return round(max(1, min(10, steps)) * CLOUD_VOLUME_STEP, 2)

    async def _async_set_volume(self, run: AlarmRun, volume: float, force: bool = False) -> bool:
        """Send a volume change; cloud speakers get whole steps and rate limiting.

        Returns False when a cloud step had to wait for the rate limit.
        """
        if run.cloud:
            volume = self._cloud_volume(volume)
            if volume == run.last_volume:
                return True
            if not force and run.last_player_command is not None:
                elapsed = (dt_util.utcnow() - run.last_player_command).total_seconds()
                if elapsed < CLOUD_MIN_INTERVAL:
                    return False
        elif volume == run.last_volume:
            return True
        run.last_volume = volume
        await self._player_call(run, "volume_set", {ATTR_MEDIA_VOLUME_LEVEL: volume})
        return True

    async def _player_call(self, run: AlarmRun, service: str, data: dict[str, Any] | None = None) -> None:
        """Call the speaker one command at a time; space out commands to cloud speakers."""
        player = self.options.get(CONF_MEDIA_PLAYER)
        if not player:
            return
        async with run.player_lock:
            if run.cloud and run.last_player_command is not None:
                wait = CLOUD_COMMAND_GAP - (dt_util.utcnow() - run.last_player_command).total_seconds()
                if wait > 0:
                    await asyncio.sleep(wait)
            await self._call("media_player", service, player, data)
            run.last_player_command = dt_util.utcnow()

    async def _async_maybe_open_covers(self, run: AlarmRun) -> None:
        covers = self.options.get(CONF_COVERS) or []
        if not covers or run.cover_opened:
            return
        if self.settings[SET_COVER_SUN_ONLY]:
            sun = self.hass.states.get(SUN_ENTITY)
            elevation = sun.attributes.get("elevation") if sun else None
            threshold = self.options.get(CONF_SUN_ELEVATION, DEFAULT_SUN_ELEVATION)
            if elevation is None or elevation < threshold:
                return
        run.cover_opened = True
        position = int(self.options.get(CONF_COVER_POSITION, DEFAULT_COVER_POSITION))
        for cover in covers:
            state = self.hass.states.get(cover)
            features = state.attributes.get(ATTR_SUPPORTED_FEATURES, 0) if state else 0
            if features & CoverEntityFeature.SET_POSITION:
                await self._call("cover", "set_cover_position", cover, {ATTR_POSITION: position})
            else:
                await self._call("cover", "open_cover", cover)

    @callback
    def _on_wake(self, _now: datetime) -> None:
        run = self.run
        if run is None or self.state != AlarmState.SUNRISE:
            return
        run.woke = True
        self.state = AlarmState.RINGING
        if self.settings[SET_AUTO_STOP] > 0:
            delay = self.settings[SET_AUTO_STOP] * 60 * run.scale
            run.unsubs.append(async_call_later(self.hass, delay, self._on_auto_stop))
        self._fire(EVENT_RINGING)
        if not run.test:
            # The next occurrence can be armed while this one is ringing.
            self._handled_wake = run.wake_at
            self._save()
            self._reschedule()
        self._notify()
        self.hass.async_create_task(self._async_wake_actions(run), eager_start=True)

    async def _async_wake_actions(self, run: AlarmRun) -> None:
        for track in list(run.sources.values()):
            if self.run is not run:
                return
            state = self.hass.states.get(track.entity_id)
            if track.dimmable:
                current = state.attributes.get(ATTR_BRIGHTNESS) or 0 if state and state.state == STATE_ON else 0
                if current < 255 or (track.last_set or 0) < 255:
                    self._mark_command(track, 255, current)
                    await self._call("light", "turn_on", track.entity_id, {ATTR_BRIGHTNESS: 255})
            elif not (state and state.state == STATE_ON):
                self._mark_command(track, None)
                await self._call(track.entity_id.split(".", 1)[0], "turn_on", track.entity_id)
            else:
                track.expect_on = True
        if self.run is not run:
            return
        if self.options.get(CONF_MEDIA_PLAYER):
            if not run.media_started:
                run.media_started = True
                # Cloud speakers need pauses between commands; keep them off the light/cover path.
                self.hass.async_create_background_task(
                    self._async_start_media(run, self._max_volume), f"{DOMAIN} start media"
                )
            elif run.media_expect_playing:
                await self._async_volume_to_max(run)
        if self.run is run:
            await self._async_maybe_open_covers(run)

    async def _async_volume_to_max(self, run: AlarmRun) -> None:
        """Reach the maximum volume; a cloud speaker may have to wait for its next step."""
        if self.run is not run or not run.media_expect_playing:
            return
        if await self._async_set_volume(run, self._max_volume) or run.last_player_command is None:
            return
        elapsed = (dt_util.utcnow() - run.last_player_command).total_seconds()

        @callback
        def retry(_now: datetime) -> None:
            run.volume_retry = None
            self.hass.async_create_background_task(self._async_volume_to_max(run), f"{DOMAIN} volume")

        run.volume_retry = async_call_later(self.hass, max(0.5, CLOUD_MIN_INTERVAL - elapsed), retry)

    @callback
    def _on_auto_stop(self, _now: datetime) -> None:
        self._stop(StopReason.AUTO)

    async def _async_finish_media(self, run: AlarmRun, greet: bool) -> None:
        """Stop what the alarm played, restore the volume and optionally say good morning."""
        player = self.options.get(CONF_MEDIA_PLAYER)
        if not player:
            return
        if run.media_started:
            state = self.hass.states.get(player)
            # A cloud speaker's state is not reliable, so always ask it to stop.
            if run.cloud or (state is not None and state.state in (STATE_PLAYING, "paused", "buffering")):
                await self._player_call(run, "media_stop")
        if run.saved_volume is not None:
            await self._player_call(run, "volume_set", {ATTR_MEDIA_VOLUME_LEVEL: run.saved_volume})
        elif greet:
            await self._player_call(run, "volume_set", {ATTR_MEDIA_VOLUME_LEVEL: self._max_volume})
        if not greet:
            return
        await asyncio.sleep(GREETING_DELAY)
        phrase = await self._async_greeting_phrase()
        _LOGGER.debug("%s: greeting: %s", self.name, phrase)
        await self._player_call(run, "play_media", {ATTR_MEDIA_CONTENT_TYPE: "text", ATTR_MEDIA_CONTENT_ID: phrase})

    def _weather_entity(self) -> str | None:
        if configured := self.options.get(CONF_WEATHER):
            return configured
        return next(iter(sorted(self.hass.states.async_entity_ids("weather"))), None)

    async def _async_greeting_phrase(self) -> str:
        entity_id = self._weather_entity()
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in IGNORED_STATES:
            return build_greeting(None, None, None)
        return build_greeting(state.state, state.attributes.get("temperature"), await self._async_today_high(entity_id))

    async def _async_today_high(self, entity_id: str) -> float | None:
        """Return today's maximum temperature from the forecast, if any."""
        today = dt_util.now().date()
        for forecast_type in FORECAST_TYPES:
            try:
                response = await self.hass.services.async_call(
                    "weather",
                    "get_forecasts",
                    {ATTR_ENTITY_ID: entity_id, "type": forecast_type},
                    blocking=True,
                    return_response=True,
                )
            except Exception:  # noqa: BLE001 - unsupported type or broken weather entity
                continue
            forecast = ((response or {}).get(entity_id) or {}).get("forecast") or []
            entries = []
            for item in forecast:
                moment = dt_util.parse_datetime(str(item.get("datetime", "")))
                if item.get("temperature") is None or moment is None:
                    continue
                entries.append((dt_util.as_local(moment).date(), item["temperature"]))
            if not entries:
                continue
            todays = [temp for day, temp in entries if day == today]
            if forecast_type == "hourly":
                return max(todays) if todays else None
            return todays[0] if todays else entries[0][1]
        return None

    # ------------------------------------------------------- change detection

    @callback
    def _on_sun_change(self, _event: Event[EventStateChangedData]) -> None:
        run = self.run
        if run is None or self.state != AlarmState.SUNRISE or self.settings[SET_COVER_LEAD] <= 0:
            return
        if self._timeline(run.wake_at, run.scale).cover.active(dt_util.now()):
            self.hass.async_create_task(self._async_maybe_open_covers(run), eager_start=True)

    @callback
    def _on_device_change(self, event: Event[EventStateChangedData]) -> None:
        run = self.run
        if run is None or self.state not in ACTIVE_STATES:
            return
        entity_id = event.data["entity_id"]
        old, new = event.data["old_state"], event.data["new_state"]
        if new is None or new.state in IGNORED_STATES or old is None or old.state in IGNORED_STATES:
            return
        if entity_id == self.options.get(CONF_MEDIA_PLAYER):
            self._check_media_change(run, old, new)
        elif (track := run.sources.get(entity_id)) and self._is_manual_light_change(track, old, new):
            _LOGGER.info("%s: %s changed by someone, stopping", self.name, entity_id)
            self._stop(StopReason.MANUAL)

    def _is_manual_light_change(self, track: SourceTrack, old: State, new: State) -> bool:
        if new.state == STATE_OFF:
            if track.turned_on_at is not None and (
                (dt_util.utcnow() - track.turned_on_at).total_seconds() < ECHO_WINDOW
            ):
                return False  # stale "off" right after we switched it on
            return track.expect_on
        if new.state != STATE_ON:
            return False
        if old.state != STATE_ON:
            return not track.expect_on
        if not track.dimmable:
            return False
        brightness = new.attributes.get(ATTR_BRIGHTNESS)
        if brightness is None or brightness == old.attributes.get(ATTR_BRIGHTNESS):
            return False
        expected = list(track.recent) or ([track.initial_brightness] if track.initial_brightness else [])
        if not expected:
            return False
        # Accept anything between recent commands (late echoes, transitions) plus rounding tolerance.
        low, high = min(expected) - BRIGHTNESS_TOLERANCE, max(expected) + BRIGHTNESS_TOLERANCE
        return not low <= brightness <= high

    @callback
    def _check_media_change(self, run: AlarmRun, old: State, new: State) -> None:
        if run.cloud:
            return  # a cloud speaker's state does not reflect what it plays
        if new.state == STATE_PLAYING:
            self._cancel_media_debounce(run)
            return
        if (
            old.state != STATE_PLAYING
            or new.state not in NOT_PLAYING
            or not run.media_expect_playing
            or run.media_started_at is None
            or (dt_util.utcnow() - run.media_started_at).total_seconds() < MEDIA_GRACE
            or run.media_debounce is not None
        ):
            return

        @callback
        def confirm(_now: datetime) -> None:
            run.media_debounce = None
            state = self.hass.states.get(self.options.get(CONF_MEDIA_PLAYER, ""))
            if self.run is run and run.media_expect_playing and state and state.state in NOT_PLAYING:
                _LOGGER.info("%s: media stopped by someone, stopping", self.name)
                self._stop(StopReason.MANUAL)

        run.media_debounce = async_call_later(self.hass, MEDIA_DEBOUNCE, confirm)

    @callback
    def _cancel_media_debounce(self, run: AlarmRun) -> None:
        if run.media_debounce:
            run.media_debounce()
            run.media_debounce = None

    # ---------------------------------------------------------------- helpers

    async def _call(self, domain: str, service: str, entity_id: str, data: dict[str, Any] | None = None) -> None:
        """Call a device service; failures are logged and never abort the sequence."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state == STATE_UNAVAILABLE:
            _LOGGER.warning("%s: %s is unavailable, skipping %s.%s", self.name, entity_id, domain, service)
            return
        try:
            await self.hass.services.async_call(
                domain,
                service,
                {**(data or {}), ATTR_ENTITY_ID: entity_id},
                blocking=True,
                context=self._context,
            )
        except Exception:
            _LOGGER.warning("%s: %s.%s failed for %s", self.name, domain, service, entity_id, exc_info=True)

    @callback
    def _fire(self, event_type: str, **data: Any) -> None:
        self.hass.bus.async_fire(event_type, {"entry_id": self.entry.entry_id, "name": self.name, **data})
