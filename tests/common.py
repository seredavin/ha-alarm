"""Test helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.wakeup_alarm.config_flow import DEFAULT_OPTIONS
from custom_components.wakeup_alarm.const import (
    CONF_COVERS,
    CONF_MEDIA_PLAYER,
    CONF_SOURCES,
    DOMAIN,
    EVENT_RINGING,
    EVENT_SNOOZED,
    EVENT_STOPPED,
    EVENT_SUNRISE_STARTED,
    SET_ENABLED,
)
from custom_components.wakeup_alarm.controller import AlarmController

DIMMER = "light.dimmer"
ONOFF_LIGHT = "light.onoff"
PLUG = "switch.plug"
STATION = "media_player.station"
COVER = "cover.curtain"

SERVICES = [
    ("light", "turn_on"),
    ("switch", "turn_on"),
    ("media_player", "volume_set"),
    ("media_player", "play_media"),
    ("media_player", "media_stop"),
    ("media_player", "media_pause"),
    ("cover", "set_cover_position"),
    ("cover", "open_cover"),
]


@dataclass
class Recorder:
    """Captured service calls and events."""

    calls: dict[str, list[ServiceCall]] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)

    def __call__(self, key: str, entity_id: str | None = None) -> list[ServiceCall]:
        result = self.calls[key]
        if entity_id:
            result = [c for c in result if entity_id in _ids(c)]
        return result

    def brightness(self, entity_id: str = DIMMER) -> list[int]:
        return [c.data["brightness"] for c in self("light.turn_on", entity_id) if "brightness" in c.data]

    def event_types(self) -> list[str]:
        return [e.event_type for e in self.events]


def _ids(call: ServiceCall) -> list[str]:
    value = call.data.get("entity_id", [])
    return [value] if isinstance(value, str) else list(value)


async def setup_world(hass: HomeAssistant, freezer: FrozenDateTimeFactory, start: datetime) -> Recorder:
    """Moscow time zone, frozen clock, fake devices and service mocks."""
    await hass.config.async_set_time_zone("Europe/Moscow")
    freezer.move_to(start)
    hass.states.async_set(DIMMER, "off", {"supported_color_modes": ["brightness"], "supported_features": 0})
    hass.states.async_set(ONOFF_LIGHT, "off", {"supported_color_modes": ["onoff"]})
    hass.states.async_set(PLUG, "off")
    hass.states.async_set(STATION, "idle", {"volume_level": 0.2})
    hass.states.async_set(COVER, "closed", {"supported_features": 15})
    hass.states.async_set("sun.sun", "above_horizon", {"elevation": 10.0})
    # Load real platforms first so their services do not replace the mocks later.
    for domain in ("switch", "light", "cover", "media_player"):
        assert await async_setup_component(hass, domain, {})
    recorder = Recorder()
    for domain, service in SERVICES:
        recorder.calls[f"{domain}.{service}"] = async_mock_service(hass, domain, service)
    for event_type in (EVENT_SUNRISE_STARTED, EVENT_RINGING, EVENT_SNOOZED, EVENT_STOPPED):
        hass.bus.async_listen(event_type, recorder.events.append)
    return recorder


def msk(day: int, hour: int, minute: int = 0, second: int = 0) -> datetime:
    """Moscow time in November 2026 (the 9th is a Monday)."""
    return datetime(2026, 11, day, hour, minute, second, tzinfo=dt_util.get_time_zone("Europe/Moscow"))


async def setup_alarm(
    hass: HomeAssistant,
    title: str = "Bedroom",
    enabled: bool = True,
    **options: Any,
) -> MockConfigEntry:
    """Create and load an alarm entry with all fake devices by default."""
    entry_options = {
        **DEFAULT_OPTIONS,
        CONF_SOURCES: [DIMMER, ONOFF_LIGHT, PLUG],
        CONF_MEDIA_PLAYER: STATION,
        CONF_COVERS: [COVER],
        **options,
    }
    entry = MockConfigEntry(domain=DOMAIN, title=title, data={}, options=entry_options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    if enabled:
        controller(entry).set_setting(SET_ENABLED, True)
        await hass.async_block_till_done()
    return entry


def controller(entry: MockConfigEntry) -> AlarmController:
    """Return the controller of an entry."""
    return entry.runtime_data


def entity_id(hass: HomeAssistant, entry: MockConfigEntry, domain: str, key: str) -> str:
    """Resolve an entity id by unique id."""
    result = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")
    assert result, key
    return result


async def advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, until: datetime, step: float = 1.0) -> None:
    """Move the clock forward in small steps, firing timers on the way."""
    while dt_util.now() < until:
        delta = min(timedelta(seconds=step), until - dt_util.now())
        freezer.tick(delta)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
