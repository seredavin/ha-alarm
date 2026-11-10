"""Custom speaker command."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WakeupAlarmConfigEntry
from .const import SET_MEDIA_CUSTOM
from .entity import AlarmEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WakeupAlarmConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the custom command text."""
    async_add_entities([MediaCustomText(entry.runtime_data, SET_MEDIA_CUSTOM)])


class MediaCustomText(AlarmEntity, TextEntity):
    """Command sent to the speaker when the preset is 'custom'."""

    _attr_icon = "mdi:text-to-speech"
    _attr_native_max = 255

    @property
    def native_value(self) -> str:
        """Return the command."""
        return self.controller.settings[SET_MEDIA_CUSTOM]

    async def async_set_value(self, value: str) -> None:
        """Change the command."""
        self.controller.set_setting(SET_MEDIA_CUSTOM, value.strip())
