"""Numeric alarm settings."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WakeupAlarmConfigEntry
from .const import SET_AUTO_STOP, SET_COVER_LEAD, SET_FADE, SET_MAX_VOLUME, SET_MEDIA_LEAD, SET_SNOOZE
from .controller import AlarmController
from .entity import AlarmEntity

DESCRIPTIONS: tuple[NumberEntityDescription, ...] = (
    NumberEntityDescription(
        key=SET_FADE,
        native_min_value=1,
        native_max_value=60,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:weather-sunset-up",
    ),
    NumberEntityDescription(
        key=SET_MEDIA_LEAD,
        native_min_value=0,
        native_max_value=60,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:speaker-play",
    ),
    NumberEntityDescription(
        key=SET_MAX_VOLUME,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:volume-high",
    ),
    NumberEntityDescription(
        key=SET_COVER_LEAD,
        native_min_value=0,
        native_max_value=60,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:curtains",
    ),
    NumberEntityDescription(
        key=SET_SNOOZE,
        native_min_value=1,
        native_max_value=30,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:alarm-snooze",
    ),
    NumberEntityDescription(
        key=SET_AUTO_STOP,
        native_min_value=0,
        native_max_value=120,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-off-outline",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WakeupAlarmConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities."""
    async_add_entities(SettingNumber(entry.runtime_data, description) for description in DESCRIPTIONS)


class SettingNumber(AlarmEntity, NumberEntity):
    """A numeric setting."""

    _attr_mode = NumberMode.BOX

    def __init__(self, controller: AlarmController, description: NumberEntityDescription) -> None:
        super().__init__(controller, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float:
        """Return the setting value."""
        return self.controller.settings[self.entity_description.key]

    async def async_set_native_value(self, value: float) -> None:
        """Change the setting."""
        self.controller.set_setting(self.entity_description.key, int(value))
