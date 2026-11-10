"""Buttons: stop, snooze, test."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WakeupAlarmConfigEntry
from .const import StopReason
from .controller import AlarmController
from .entity import AlarmEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WakeupAlarmConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up buttons."""
    controller = entry.runtime_data
    async_add_entities(
        [
            AlarmButton(controller, "stop", "mdi:alarm-off"),
            AlarmButton(controller, "snooze", "mdi:alarm-snooze"),
            AlarmButton(controller, "test", "mdi:play-circle-outline"),
        ]
    )


class AlarmButton(AlarmEntity, ButtonEntity):
    """A control button of the alarm."""

    def __init__(self, controller: AlarmController, key: str, icon: str) -> None:
        super().__init__(controller, key)
        self._key = key
        self._attr_icon = icon

    async def async_press(self) -> None:
        """Handle the press."""
        if self._key == "stop":
            self.controller.async_stop(StopReason.BUTTON)
        elif self._key == "snooze":
            self.controller.async_snooze()
        else:
            self.controller.async_trigger()
