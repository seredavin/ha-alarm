"""Wake time entity."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WakeupAlarmConfigEntry
from .const import SET_WAKE_TIME
from .entity import AlarmEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WakeupAlarmConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the wake time entity."""
    async_add_entities([WakeTime(entry.runtime_data, SET_WAKE_TIME)])


class WakeTime(AlarmEntity, TimeEntity):
    """Time the alarm should have the lights at 100%."""

    _attr_icon = "mdi:alarm"

    @property
    def native_value(self) -> time:
        """Return the wake time."""
        return self.controller.wake_time

    async def async_set_value(self, value: time) -> None:
        """Change the wake time."""
        self.controller.set_setting(SET_WAKE_TIME, value)
