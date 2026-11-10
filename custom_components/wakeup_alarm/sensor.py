"""Sensors: next wake and alarm state."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WakeupAlarmConfigEntry
from .const import AlarmState
from .entity import AlarmEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WakeupAlarmConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    controller = entry.runtime_data
    async_add_entities([NextWakeSensor(controller, "next_wake"), StateSensor(controller, "status")])


class NextWakeSensor(AlarmEntity, SensorEntity):
    """When the alarm fires next."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:alarm-check"

    @property
    def native_value(self) -> datetime | None:
        """Return the next wake moment."""
        return self.controller.next_wake


class StateSensor(AlarmEntity, SensorEntity):
    """Current alarm state."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options: ClassVar[list[str]] = [state.value for state in AlarmState]
    _attr_icon = "mdi:alarm-panel-outline"

    @property
    def native_value(self) -> str:
        """Return the alarm state."""
        return self.controller.state.value
