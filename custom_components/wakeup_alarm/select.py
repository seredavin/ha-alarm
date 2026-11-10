"""What the speaker plays."""

from __future__ import annotations

from typing import ClassVar

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WakeupAlarmConfigEntry
from .const import MEDIA_PRESETS, SET_MEDIA_PRESET
from .entity import AlarmEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WakeupAlarmConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the content select."""
    async_add_entities([MediaPresetSelect(entry.runtime_data, SET_MEDIA_PRESET)])


class MediaPresetSelect(AlarmEntity, SelectEntity):
    """Preset the speaker plays when the alarm goes off."""

    _attr_icon = "mdi:music-box-multiple"
    _attr_options: ClassVar[list[str]] = list(MEDIA_PRESETS)

    @property
    def current_option(self) -> str:
        """Return the selected preset."""
        return self.controller.settings[SET_MEDIA_PRESET]

    async def async_select_option(self, option: str) -> None:
        """Select a preset."""
        self.controller.set_setting(SET_MEDIA_PRESET, option)
