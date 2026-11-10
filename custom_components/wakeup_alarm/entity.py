"""Base entity for the Wake-up Alarm integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .controller import AlarmController


class AlarmEntity(Entity):
    """An entity that mirrors part of an alarm controller."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller: AlarmController, key: str) -> None:
        self.controller = controller
        entry = controller.entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="Wake-up Alarm",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to controller updates."""
        self.async_on_remove(self.controller.add_listener(self.async_write_ha_state))
