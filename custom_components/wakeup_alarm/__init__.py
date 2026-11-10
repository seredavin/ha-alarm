"""Wake-up Alarm: sunrise alarm clock with lights, speaker and covers."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_extract_config_entry_ids
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .card import async_register_card, async_unregister_card_resource
from .const import ATTR_DURATION, DOMAIN, SERVICE_SNOOZE, SERVICE_STOP, SERVICE_TRIGGER, StopReason
from .controller import AlarmController

PLATFORMS = [
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
    Platform.TIME,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type WakeupAlarmConfigEntry = ConfigEntry[AlarmController]

TARGET_SCHEMA = vol.Schema(cv.ENTITY_SERVICE_FIELDS)
TRIGGER_SCHEMA = TARGET_SCHEMA.extend(
    {vol.Optional(ATTR_DURATION): vol.All(vol.Coerce(float), vol.Range(min=1, max=7200))}
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services and the dashboard card."""

    async def controllers(call: ServiceCall) -> list[AlarmController]:
        result = []
        for entry_id in await async_extract_config_entry_ids(hass, call):
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry and entry.domain == DOMAIN and entry.state is ConfigEntryState.LOADED:
                result.append(entry.runtime_data)
        return result

    async def handle_stop(call: ServiceCall) -> None:
        for controller in await controllers(call):
            controller.async_stop(StopReason.SERVICE)

    async def handle_snooze(call: ServiceCall) -> None:
        for controller in await controllers(call):
            controller.async_snooze()

    async def handle_trigger(call: ServiceCall) -> None:
        for controller in await controllers(call):
            controller.async_trigger(call.data.get(ATTR_DURATION))

    hass.services.async_register(DOMAIN, SERVICE_STOP, handle_stop, TARGET_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SNOOZE, handle_snooze, TARGET_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_TRIGGER, handle_trigger, TRIGGER_SCHEMA)
    await async_register_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: WakeupAlarmConfigEntry) -> bool:
    """Set up an alarm from a config entry."""
    controller = AlarmController(hass, entry)
    await controller.async_load()
    entry.runtime_data = controller
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    controller.async_start()
    entry.async_on_unload(controller.async_shutdown)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: WakeupAlarmConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: WakeupAlarmConfigEntry) -> bool:
    """Unload an alarm."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_save_now()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: WakeupAlarmConfigEntry) -> None:
    """Delete persisted settings when the alarm is removed."""
    await AlarmController(hass, entry).async_remove_store()
    if not [e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id]:
        await async_unregister_card_resource(hass)
