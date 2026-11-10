"""Switches: enabled, skip next, weekdays."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WakeupAlarmConfigEntry
from .const import SET_ENABLED, SET_SKIP_NEXT, SET_WEEKDAYS, WEEKDAY_KEYS
from .controller import AlarmController
from .entity import AlarmEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WakeupAlarmConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches."""
    controller = entry.runtime_data
    entities: list[SwitchEntity] = [
        SettingSwitch(controller, SET_ENABLED),
        SettingSwitch(controller, SET_SKIP_NEXT),
    ]
    entities += [WeekdaySwitch(controller, index) for index in range(7)]
    async_add_entities(entities)


class SettingSwitch(AlarmEntity, SwitchEntity):
    """A boolean setting."""

    def __init__(self, controller: AlarmController, key: str) -> None:
        super().__init__(controller, key)
        self._key = key
        if key == SET_ENABLED:
            self._attr_icon = "mdi:alarm"

    @property
    def is_on(self) -> bool:
        """Return the setting value."""
        return bool(self.controller.settings[self._key])

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the setting on."""
        self.controller.set_setting(self._key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the setting off."""
        self.controller.set_setting(self._key, False)


class WeekdaySwitch(AlarmEntity, SwitchEntity):
    """Whether the alarm fires on a weekday."""

    _attr_icon = "mdi:calendar-week"

    def __init__(self, controller: AlarmController, index: int) -> None:
        super().__init__(controller, f"weekday_{WEEKDAY_KEYS[index]}")
        self._index = index

    @property
    def is_on(self) -> bool:
        """Return True if the weekday is selected."""
        return bool(self.controller.settings[SET_WEEKDAYS][self._index])

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Select the weekday."""
        self.controller.set_weekday(self._index, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deselect the weekday."""
        self.controller.set_weekday(self._index, False)
